# Gyaan Bhandar

> RAG-powered document assistant · Flask + React + FAISS + Groq

Ask questions about your documents in natural language. The backend retrieves the most relevant text chunks using **FAISS** vector search and answers using the **Groq LLaMA 3.1** LLM. All chat sessions and documents are managed locally — no external database required.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Flask-CORS |
| Vector Search | FAISS + sentence-transformers (all-MiniLM-L6-v2) |
| LLM | Groq API (LLaMA 3.1 8b instant) |
| Frontend | React 18, react-markdown, remark-gfm |
| Storage | Local filesystem (JSON sessions, FAISS index on disk) |

---

## Project Structure

```
gyan-bhandar/
├── backend/
│   ├── app.py                  ← Flask app — parsing, indexing, all API routes
│   ├── requirements.txt
│   ├── .env                    ← secrets (never commit)
│   ├── .env.example            ← template for teammates
│   ├── documents/              ← place your PDFs, TXTs, DOCXs, MDXs here
│   ├── chat_history/           ← one JSON file per session (auto-created)
│   ├── faiss.index             ← vector index (auto-generated, gitignored)
│   ├── chunks.pkl              ← text chunks + metadata (auto-generated, gitignored)
│   └── documents.hash          ← change detection hash (auto-generated, gitignored)
└── frontend/
    └── src/
        ├── App.jsx             ← chat UI, sidebar, document panel
        ├── App.css             ← all styles
        └── index.js            ← React 18 entry point
```

---

## Backend Setup

### 1. Environment Variables

Create `backend/.env`:

```
GROQ_API_KEY=your_groq_api_key_here
MODEL_PATH=path/to/all-MiniLM-L6-v2
```

> A `backend/.env.example` with placeholder values is committed to the repo so teammates know which variables are needed.

### 2. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Add Documents

Place your documents in `backend/documents/`. Supported formats:

- `.pdf` — PDF files
- `.txt` — plain text
- `.docx` — Word documents
- `.mdx` — MDX files (useful for Terraform / Hashicorp docs)

### 4. Run

```bash
python app.py
```

**First run:** Parses all files in `documents/`, builds the FAISS index, and saves `faiss.index`, `chunks.pkl`, and `documents.hash` to disk.

**Subsequent runs:** Detects whether documents have changed using a hash. If unchanged, loads the saved index instantly. If changed (new upload or deletion), rebuilds automatically.

---

## Frontend Setup

### 1. Install and Run

```bash
cd frontend
npm install
npm start
```

The app runs at `http://localhost:3000`. Make sure the Flask backend is running on port 5000.

### 2. Dependencies

```bash
npm install react-markdown remark-gfm
```

### 3. `src/index.js` (React 18)

Make sure it uses the React 18 `createRoot` API:

```js
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
```

---

## API Reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/health` | Backend status, chunks loaded, document count |
| `POST` | `/query` | `{ query, session_id }` → answer + retrieved chunks |
| `POST` | `/upload` | Multipart file upload → triggers index rebuild |
| `GET` | `/documents` | List all uploaded documents with size and date |
| `DELETE` | `/documents/<n>` | Delete a document and rebuild the index |
| `POST` | `/rebuild-index` | Force full re-parse and index rebuild |
| `GET` | `/sessions` | List all chat sessions (sorted by recent) |
| `POST` | `/sessions` | Create a new chat session |
| `GET` | `/sessions/<id>` | Get full message history for a session |
| `DELETE` | `/sessions/<id>` | Delete a chat session |

---

## Features

### Document Management
- Upload documents via the UI — index rebuilds automatically
- Collapsible documents panel shows filename, size, and upload date
- Delete documents from the UI — index rebuilds automatically
- Hash-based change detection — index only rebuilds when documents actually change

### Chat & Sessions
- Full chat history stored as JSON files in `backend/chat_history/`
- Sidebar lists all past sessions — click any to restore the full conversation
- Sessions are auto-titled from the first message
- Each AI response shows the retrieved source chunks with page numbers
- Copy button on every code block in AI responses

### Index Persistence

```
First run:    documents/ → parse → chunk → embed → faiss.index + chunks.pkl
Later runs:   hash match → load from disk (instant)
New file:     hash mismatch → rebuild index automatically
```

To force a full rebuild manually:

```bash
# Via API
curl -X POST http://localhost:5000/rebuild-index

# Or delete the generated files and restart
del backend\faiss.index backend\chunks.pkl backend\documents.hash   # Windows
rm backend/faiss.index backend/chunks.pkl backend/documents.hash    # Mac/Linux
```

---

## Importing Terraform Docs

The Terraform docs are at [github.com/hashicorp/web-unified-docs](https://github.com/hashicorp/web-unified-docs) under `content/terraform-docs-common`. Use sparse checkout to avoid downloading the entire repo:

```bash
# Sparse clone — only pulls the folder you need
git clone --filter=blob:none --sparse https://github.com/hashicorp/web-unified-docs.git
cd web-unified-docs
git sparse-checkout set content/terraform-docs-common

# Copy MDX files into your documents folder (subfolder name used as prefix to avoid duplicates)
find content/terraform-docs-common -name "*.mdx" | while read f; do
  relative="${f#content/terraform-docs-common/}"
  newname="${relative//\//_}"
  cp "$f" "../backend/documents/$newname"
done
```

> **Note:** The first index build may take several minutes if there are hundreds of MDX files. Subsequent restarts load instantly from the saved index.

To check for duplicate filenames before copying:

```bash
# Count duplicates
find content/terraform-docs-common -name "*.mdx" | xargs -I {} basename {} | sort | uniq -d | wc -l

# See duplicate names
find content/terraform-docs-common -name "*.mdx" | xargs -I {} basename {} | sort | uniq -d

# See full paths of all duplicates
find content/terraform-docs-common -name "*.mdx" | xargs -I {} basename {} | sort | uniq -d | while read name; do
  find content/terraform-docs-common -name "$name"
done
```

---

## Git & Deployment

### `.gitignore`

```gitignore
# Secrets
backend/.env

# Generated index files (rebuilt automatically on first run)
backend/faiss.index
backend/chunks.pkl
backend/documents.hash

# Document uploads (kept locally)
backend/documents/

# Chat history (local only)
backend/chat_history/

# Python
__pycache__/
*.pyc
.venv/
venv/

# Node
frontend/node_modules/
frontend/build/

# OS
.DS_Store
Thumbs.db
```

### First-Time Setup on a New Machine

1. Copy `.env.example` to `.env` and fill in your keys
2. Place documents in `backend/documents/`
3. Run `python app.py` — the index builds automatically on first run
4. In a separate terminal: `cd frontend && npm install && npm start`

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Backend offline (red dot in UI) | Check that `python app.py` is running on port 5000 |
| Index not updating after upload | Delete `documents.hash` and restart the backend |
| Duplicate MDX filenames | Use the prefix-copy script in the Terraform Docs section above |
| Slow first startup with many MDX files | Expected — FAISS index builds once and loads instantly on all subsequent runs |
| Code blocks not rendering | Ensure `remark-gfm` is installed and passed as `remarkPlugins={[remarkGfm]}` |