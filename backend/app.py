from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from datetime import datetime, timezone
from docx import Document
import requests
import faiss
import numpy as np
import pickle
import os
import re
import glob
import json
import uuid
import hashlib
import PyPDF2
from sentence_transformers import SentenceTransformer

load_dotenv()

app = Flask(__name__)
CORS(app)

# ── Config ────────────────────────────────────────────────────
MODEL_PATH      = os.getenv("MODEL_PATH", "all-MiniLM-L6-v2")
API_KEY         = os.getenv("GROQ_API_KEY")
BASE_URL        = "https://api.groq.com/openai/v1"
GROQ_HEADERS    = {"Authorization": f"Bearer {API_KEY}"}

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN")
GITHUB_REPO     = os.getenv("GITHUB_REPO")   # e.g. "KPkm25/gyaan-bhandar"

DOCUMENTS_FOLDER      = "documents"
HISTORY_FOLDER        = "chat_history"
INDEX_PATH            = "faiss.index"
CHUNKS_PATH           = "chunks.pkl"
HASH_PATH             = "documents.hash"
ALLOWED_EXT           = {"pdf", "txt", "docx", "mdx"}
LOW_CONFIDENCE_THRESHOLD = 0.35

os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(HISTORY_FOLDER, exist_ok=True)

# ── Load model ────────────────────────────────────────────────
print("Loading embedding model...")
model = SentenceTransformer(MODEL_PATH)
print("Model loaded.")

# ── File readers ──────────────────────────────────────────────
def read_txt(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return [{"text": line, "source": file_path, "page": None}
            for line in text.splitlines() if line.strip()]

def read_docx(file_path):
    doc = Document(file_path)
    return [{"text": para.text, "source": file_path, "page": None}
            for para in doc.paragraphs if para.text.strip()]

def read_pdf(file_path):
    sentences = []
    with open(file_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text:
                for line in text.splitlines():
                    if line.strip():
                        sentences.append({
                            "text": line,
                            "source": file_path,
                            "page": page_num
                        })
    return sentences

def read_mdx(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Strip YAML frontmatter
    content = re.sub(r'^---[\s\S]*?---\n', '', content, flags=re.MULTILINE)
    # Strip import statements
    content = re.sub(r'^import\s+.*$', '', content, flags=re.MULTILINE)
    # Strip JSX/HTML components (uppercase opening/self-closing tags)
    content = re.sub(r'<[A-Z][^>]*/?>', '', content)
    content = re.sub(r'</[A-Z][a-zA-Z]+>', '', content)
    # Strip known lowercase MDX components
    content = re.sub(r'</?(?:Note|Warning|Tip|Callout|Card|Tab|Tabs|CodeBlock|CodeTabs)[^>]*>', '', content)
    # Strip export statements
    content = re.sub(r'^export\s+.*$', '', content, flags=re.MULTILINE)

    return [
        {"text": line.strip(), "source": file_path, "page": None}
        for line in content.splitlines() if line.strip()
    ]

# ── Chunking ──────────────────────────────────────────────────
def chunk_text(sentences, chunk_size=200, overlap=50):
    chunks = []
    current_words = []
    current_source = None
    current_page = None

    for s in sentences:
        words = s["text"].split()
        if not current_words:
            current_source = s["source"]
            current_page = s["page"]
        current_words.extend(words)
        if len(current_words) >= chunk_size:
            chunks.append({
                "text": " ".join(current_words[:chunk_size]),
                "source": current_source,
                "page": current_page
            })
            current_words = current_words[chunk_size - overlap:]
            current_source = s["source"]
            current_page = s["page"]

    if current_words:
        chunks.append({
            "text": " ".join(current_words),
            "source": current_source,
            "page": current_page
        })
    return chunks

# ── Parse all docs in folder ──────────────────────────────────
def parse_all_documents():
    all_sentences = []
    files = (
        glob.glob(f"{DOCUMENTS_FOLDER}/*.pdf") +
        glob.glob(f"{DOCUMENTS_FOLDER}/*.txt") +
        glob.glob(f"{DOCUMENTS_FOLDER}/*.docx") +
        glob.glob(f"{DOCUMENTS_FOLDER}/*.mdx")
    )
    if not files:
        print("No documents found in documents/ folder.")
        return []
    for filepath in files:
        ext = filepath.rsplit(".", 1)[-1].lower()
        print(f"  Parsing: {os.path.basename(filepath)}")
        if ext == "pdf":
            all_sentences.extend(read_pdf(filepath))
        elif ext == "txt":
            all_sentences.extend(read_txt(filepath))
        elif ext == "docx":
            all_sentences.extend(read_docx(filepath))
        elif ext == "mdx":
            all_sentences.extend(read_mdx(filepath))
    return all_sentences

# ── Hash-based change detection ───────────────────────────────
def get_documents_hash():
    files = sorted(
        glob.glob(f"{DOCUMENTS_FOLDER}/*.pdf") +
        glob.glob(f"{DOCUMENTS_FOLDER}/*.txt") +
        glob.glob(f"{DOCUMENTS_FOLDER}/*.docx") +
        glob.glob(f"{DOCUMENTS_FOLDER}/*.mdx")
    )
    fingerprint = "|".join(
        f"{os.path.basename(f)}:{os.path.getsize(f)}" for f in files
    )
    return hashlib.md5(fingerprint.encode()).hexdigest()

# ── Load or build FAISS index ─────────────────────────────────
def load_or_build_index():
    current_hash = get_documents_hash()

    if (os.path.exists(INDEX_PATH) and
            os.path.exists(CHUNKS_PATH) and
            os.path.exists(HASH_PATH)):
        with open(HASH_PATH) as f:
            saved_hash = f.read().strip()
        if saved_hash == current_hash:
            print("Documents unchanged — loading existing index.")
            faiss_index = faiss.read_index(INDEX_PATH)
            with open(CHUNKS_PATH, "rb") as f:
                loaded_chunks = pickle.load(f)
            print(f"Loaded {len(loaded_chunks)} chunks.")
            return faiss_index, loaded_chunks

    print("Building new index...")
    sentences = parse_all_documents()
    if not sentences:
        return None, []

    loaded_chunks = chunk_text(sentences)
    embeddings = model.encode(
        [c["text"] for c in loaded_chunks]
    ).astype("float32")

    faiss_index = faiss.IndexFlatL2(embeddings.shape[1])
    faiss_index.add(embeddings)

    faiss.write_index(faiss_index, INDEX_PATH)
    with open(CHUNKS_PATH, "wb") as f:
        pickle.dump(loaded_chunks, f)
    with open(HASH_PATH, "w") as f:
        f.write(current_hash)

    doc_count = len(set(c["source"] for c in loaded_chunks))
    print(f"Index built: {len(loaded_chunks)} chunks from {doc_count} file(s).")
    return faiss_index, loaded_chunks

index, chunks = load_or_build_index()

# ── FAISS search with confidence score ───────────────────────
def search_docs(query, k=3):
    if index is None or not chunks:
        return [], 0.0

    q_emb = model.encode([query]).astype("float32")
    distances, indices = index.search(q_emb, k=k)

    results = []
    for i, idx in enumerate(indices[0]):
        if idx < len(chunks):
            results.append({
                "text": chunks[idx]["text"],
                "source": os.path.basename(chunks[idx]["source"]),
                "page": chunks[idx]["page"],
                "distance": float(distances[0][i])
            })

    if not results:
        return [], 0.0

    # Convert L2 distance → confidence score (0–1)
    # all-MiniLM-L6-v2 typical L2 range: 0 (identical) to ~2 (unrelated)
    avg_distance = sum(r["distance"] for r in results) / len(results)
    confidence = round(max(0.0, min(1.0, 1 - (avg_distance / 2.0))), 3)

    return results, confidence

# ── Groq LLM ──────────────────────────────────────────────────
def ask_groq(query, retrieved_chunks, model_name="llama-3.1-8b-instant"):
    context = "\n\n".join([c["text"] for c in retrieved_chunks])
    prompt = (
        f"Use the context below to answer the question.\n\n"
        f"Context:\n{context}\n\nQuestion: {query}"
    )
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Use clean markdown formatting. "
                    "When including code blocks inside numbered lists, always add a "
                    "blank line before and after the code fence, and do not indent "
                    "the code fence itself."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500
    }
    response = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=GROQ_HEADERS,
        json=payload,
        verify=False
    )
    result = response.json()
    if "choices" in result:
        return result["choices"][0]["message"]["content"]
    return f"Error from Groq: {result}"

# ── GitHub issue creation ─────────────────────────────────────
def create_github_issue(query, confidence, retrieved):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("GitHub not configured — skipping issue creation.")
        return None

    sources = list(set(c["source"] for c in retrieved))
    body = (
        f"## Documentation Gap Detected\n\n"
        f"**Query:** {query}\n\n"
        f"**Confidence Score:** {confidence:.0%}\n\n"
        f"**Closest sources searched:**\n"
        + "\n".join(f"- `{s}`" for s in sources)
        + f"\n\n---\n*Auto-generated by Gyaan Bhandar. "
          f"This query could not be answered confidently from the current documentation.*"
    )

    response = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        },
        json={
            "title": f"[Doc Gap] {query[:80]}",
            "body": body,
            "labels": ["documentation", "auto-generated"]
        },
        verify=False

    )

    if response.status_code == 201:
        issue_url = response.json().get("html_url")
        print(f"GitHub issue created: {issue_url}")
        return issue_url
    else:
        print(f"GitHub issue creation failed: {response.status_code} {response.text}")
        return None

# ── Chat history helpers ──────────────────────────────────────
def session_path(session_id):
    return os.path.join(HISTORY_FOLDER, f"{session_id}.json")

# ── Routes: System ────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "chunks_loaded": len(chunks),
        "documents": len(set(c["source"] for c in chunks)) if chunks else 0
    })

@app.route("/rebuild-index", methods=["POST"])
def rebuild_index():
    global index, chunks
    for path in [INDEX_PATH, CHUNKS_PATH, HASH_PATH]:
        if os.path.exists(path):
            os.remove(path)
    index, chunks = load_or_build_index()
    return jsonify({"status": "rebuilt", "chunks": len(chunks)})

# ── Routes: Documents ─────────────────────────────────────────
@app.route("/documents", methods=["GET"])
def list_documents():
    files = sorted(
        glob.glob(f"{DOCUMENTS_FOLDER}/*.pdf") +
        glob.glob(f"{DOCUMENTS_FOLDER}/*.txt") +
        glob.glob(f"{DOCUMENTS_FOLDER}/*.docx") +
        glob.glob(f"{DOCUMENTS_FOLDER}/*.mdx")
    )
    docs = [
        {
            "name": os.path.basename(f),
            "size_kb": round(os.path.getsize(f) / 1024, 1),
            "modified": datetime.fromtimestamp(
                os.path.getmtime(f)
            ).strftime("%b %d, %Y")
        }
        for f in files
    ]
    return jsonify(docs)

@app.route("/upload", methods=["POST"])
def upload():
    global index, chunks
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        return jsonify({"error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXT)}"}), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(DOCUMENTS_FOLDER, filename)
    file.save(save_path)
    print(f"Uploaded: {filename}")

    if os.path.exists(HASH_PATH):
        os.remove(HASH_PATH)

    index, chunks = load_or_build_index()
    return jsonify({
        "status": "uploaded",
        "filename": filename,
        "total_chunks": len(chunks)
    })

@app.route("/documents/<filename>", methods=["DELETE"])
def delete_document(filename):
    global index, chunks
    filepath = os.path.join(DOCUMENTS_FOLDER, secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    os.remove(filepath)
    if os.path.exists(HASH_PATH):
        os.remove(HASH_PATH)

    index, chunks = load_or_build_index()
    return jsonify({"status": "deleted", "total_chunks": len(chunks)})

# ── Routes: Query ─────────────────────────────────────────────
@app.route("/query", methods=["POST"])
def query():
    data = request.get_json()
    user_query = data.get("query", "").strip()
    session_id = data.get("session_id")
    force_answer = data.get("force_answer", False)  # ← user can override

    if not user_query:
        return jsonify({"error": "Query cannot be empty."}), 400
    if not chunks:
        return jsonify({"error": "No documents loaded. Please upload a file first."}), 400

    retrieved, confidence = search_docs(user_query, k=3)
    is_low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD

    # If low confidence and user hasn't forced an answer — skip LLM
    if is_low_confidence and not force_answer:
        issue_url = create_github_issue(user_query, confidence, retrieved)

        # Summarise what the closest chunks ARE about
        sources = list(set(c["source"] for c in retrieved))
        source_list = "\n".join(f"- `{s}`" for s in sources)

        answer = (
            f"I couldn't find documentation that closely matches your query.\n\n"
            f"**Closest topics found in your documents:**\n{source_list}\n\n"
            f"> The retrieved chunks mention: _{retrieved[0]['text'][:120]}..._\n\n"
            f"This may not be what you're looking for. You can:\n"
            f"- **Rephrase** your question if you meant something else\n"
            f"- **Ask anyway** and I'll generate a best-effort answer from the available context"
        )

        return jsonify({
            "query": user_query,
            "answer": answer,
            "chunks": retrieved,
            "confidence": confidence,
            "low_confidence": True,
            "issue_url": issue_url,
            "can_force": True   # ← tells frontend to show the "Ask anyway" button
        })

    # Normal flow — call Groq
    answer = ask_groq(user_query, retrieved)
    issue_url = None

    # Save to session
    if session_id:
        path = session_path(session_id)
        if os.path.exists(path):
            with open(path) as f:
                session = json.load(f)
            if session["title"] == "New Chat":
                session["title"] = user_query[:45] + ("…" if len(user_query) > 45 else "")
            session["messages"].append({
                "user": user_query,
                "assistant": answer,
                "chunks": retrieved,
                "confidence": confidence,
                "issue_url": issue_url,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            session["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(path, "w") as f:
                json.dump(session, f, indent=2)

    return jsonify({
        "query": user_query,
        "answer": answer,
        "chunks": retrieved,
        "confidence": confidence,
        "low_confidence": False,
        "issue_url": None,
        "can_force": False
    })
    data = request.get_json()
    user_query = data.get("query", "").strip()
    session_id = data.get("session_id")

    if not user_query:
        return jsonify({"error": "Query cannot be empty."}), 400
    if not chunks:
        return jsonify({"error": "No documents loaded. Please upload a file first."}), 400

    retrieved, confidence = search_docs(user_query, k=3)
    answer = ask_groq(user_query, retrieved)

    # Flag low confidence and prepend warning to answer
    is_low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD
    if is_low_confidence:
        answer = (
            f"> ⚠️ **Low confidence response** (score: {confidence:.0%}) — "
            f"the documentation may not cover this topic well.\n\n{answer}"
        )

    # Auto-create GitHub issue for low confidence queries
    issue_url = None
    if is_low_confidence:
        issue_url = create_github_issue(user_query, confidence, retrieved)

    # Save to session history
    if session_id:
        path = session_path(session_id)
        if os.path.exists(path):
            with open(path) as f:
                session = json.load(f)
            if session["title"] == "New Chat":
                session["title"] = user_query[:45] + ("…" if len(user_query) > 45 else "")
            session["messages"].append({
                "user": user_query,
                "assistant": answer,
                "chunks": retrieved,
                "confidence": confidence,
                "issue_url": issue_url,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            session["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(path, "w") as f:
                json.dump(session, f, indent=2)

    return jsonify({
        "query": user_query,
        "answer": answer,
        "chunks": retrieved,
        "confidence": confidence,
        "low_confidence": is_low_confidence,
        "issue_url": issue_url
    })

# ── Routes: Chat Sessions ─────────────────────────────────────
@app.route("/sessions", methods=["GET"])
def get_sessions():
    files = sorted(
        glob.glob(f"{HISTORY_FOLDER}/*.json"),
        key=os.path.getmtime,
        reverse=True
    )
    sessions = []
    for f in files:
        with open(f) as fp:
            data = json.load(fp)
            sessions.append({
                "id": data["id"],
                "title": data["title"],
                "updated_at": data.get("updated_at", "")
            })
    return jsonify(sessions)

@app.route("/sessions", methods=["POST"])
def create_session():
    session = {
        "id": str(uuid.uuid4()),
        "title": "New Chat",
        "messages": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    with open(session_path(session["id"]), "w") as f:
        json.dump(session, f, indent=2)
    return jsonify(session)

@app.route("/sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    path = session_path(session_id)
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    with open(path) as f:
        return jsonify(json.load(f))

@app.route("/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    path = session_path(session_id)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"status": "deleted"})

if __name__ == "__main__":
    app.run(debug=True, port=5000, exclude_patterns=["*.pyc", "*site-packages*"])