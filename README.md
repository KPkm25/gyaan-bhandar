# RAG App — Flask + React

## Project Structure
```
rag-app/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   └── k8s_doc.pdf          ← place your PDF here
├── frontend/
│   └── src/
│       └── App.jsx
└── README.md
```

---

## Backend Setup

### Create a `backend/.env`
```
GROQ_API_KEY=your_groq_key_here
MODEL_PATH=path/to/all-MiniLM-L6-v2

Install the dependencies and run the application
```bash
cd backend
pip install -r requirements.txt
python app.py
```

**First run**: Parses `k8s_doc.pdf`, builds the FAISS index, and saves:
- `faiss.index` — the vector index
- `chunks.pkl`  — the text chunks + metadata

**Subsequent runs**: Loads directly from disk. Fast startup, no re-parsing.

### API Endpoints
| Method | Route | Description |
|--------|-------|-------------|
| GET  | `/health`        | Check backend status + chunks count |
| POST | `/query`         | `{ "query": "..." }` → answer + chunks |
| POST | `/rebuild-index` | Force re-parse PDF and rebuild index |

---

## Frontend Setup

```bash
cd frontend
npx create-react-app . --template blank   # or use Vite
# Copy App.jsx into src/
npm start
```

Or with Vite:
```bash
npm create vite@latest . -- --template react
# Replace src/App.jsx with the provided file
npm install
npm run dev
```

---

## How the Index Persistence Works

```
First run:
  PDF → parse → chunk → embed → FAISS index
                                      ↓
                              saved to disk (faiss.index + chunks.pkl)

Every subsequent run:
  Load faiss.index + chunks.pkl from disk  ← instant, no re-parsing
```

To force a rebuild (e.g. after updating the PDF):
```bash
curl -X POST http://localhost:5000/rebuild-index
```
Or just delete `faiss.index` and `chunks.pkl` and restart the server.
