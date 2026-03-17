from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import faiss
import numpy as np
import pickle
import os
from sentence_transformers import SentenceTransformer
from docx import Document
import PyPDF2
from dotenv import load_dotenv

load_dotenv()



app = Flask(__name__)
CORS(app)

# --- Config ---
API_KEY = os.getenv("GROQ_API_KEY")
MODEL_PATH = os.getenv("MODEL_PATH")
PDF_PATH = "k8s_doc.pdf"
INDEX_PATH = "faiss.index"
CHUNKS_PATH = "chunks.pkl"

BASE_URL = "https://api.groq.com/openai/v1"
GROQ_HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# --- Load embedding model ---
print("Loading embedding model...")
model = SentenceTransformer(MODEL_PATH)

# --- File readers ---
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

# --- Chunking ---
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
            chunk = " ".join(current_words[:chunk_size])
            chunks.append({
                "text": chunk,
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

# --- Load or build FAISS index ---
# This is the key optimization: build once, load every subsequent run.
def load_or_build_index():
    if os.path.exists(INDEX_PATH) and os.path.exists(CHUNKS_PATH):
        print("Loading existing FAISS index and chunks from disk...")
        index = faiss.read_index(INDEX_PATH)
        with open(CHUNKS_PATH, "rb") as f:
            chunks = pickle.load(f)
        print(f"Loaded {len(chunks)} chunks from disk.")
    else:
        print("Index not found. Parsing PDF and building index...")
        sentences = read_pdf(PDF_PATH)
        chunks = chunk_text(sentences, chunk_size=200, overlap=50)
        embeddings = model.encode([c["text"] for c in chunks]).astype("float32")

        index = faiss.IndexFlatL2(embeddings.shape[1])
        index.add(embeddings)

        # Save to disk for future runs
        faiss.write_index(index, INDEX_PATH)
        with open(CHUNKS_PATH, "wb") as f:
            pickle.dump(chunks, f)
        print(f"Built and saved index with {len(chunks)} chunks.")

    return index, chunks

index, chunks = load_or_build_index()

# --- FAISS search ---
def search_docs(query, k=3):
    q_emb = model.encode([query]).astype("float32")
    distances, indices = index.search(q_emb, k=k)
    return [
        {
            "text": chunks[idx]["text"],
            "source": chunks[idx]["source"],
            "page": chunks[idx]["page"]
        }
        for idx in indices[0]
    ]

# --- Groq LLM call ---
def ask_groq(query, retrieved_chunks, model_name="llama-3.1-8b-instant"):
    context = "\n\n".join([c["text"] for c in retrieved_chunks])
    prompt = f"Use the context below to answer the question.\n\nContext:\n{context}\n\nQuestion: {query}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": (
    "You are a helpful assistant. When answering, use clean markdown formatting. "
    "When including code blocks inside numbered lists, always add a blank line before "
    "and after the code fence, and do not indent the code fence itself. "
    "Keep code blocks simple and avoid nesting them deeply inside list items."
            )},
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
    else:
        return f"Error from Groq: {result}"

# --- Routes ---
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "chunks_loaded": len(chunks)})

@app.route("/query", methods=["POST"])
def query():
    data = request.get_json()
    user_query = data.get("query", "").strip()

    if not user_query:
        return jsonify({"error": "Query cannot be empty."}), 400

    retrieved = search_docs(user_query, k=3)
    answer = ask_groq(user_query, retrieved)

    return jsonify({
        "query": user_query,
        "answer": answer,
        "chunks": retrieved
    })

@app.route("/rebuild-index", methods=["POST"])
def rebuild_index():
    """Force a re-parse of the PDF and rebuild the index."""
    global index, chunks
    if os.path.exists(INDEX_PATH):
        os.remove(INDEX_PATH)
    if os.path.exists(CHUNKS_PATH):
        os.remove(CHUNKS_PATH)
    index, chunks = load_or_build_index()
    return jsonify({"status": "rebuilt", "chunks": len(chunks)})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
