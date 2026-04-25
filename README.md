# AcityRAG — Custom RAG Chat System
**CS4241 — Introduction to Artificial Intelligence | Academic City University | End of Semester 2, 2026**

> **Author:** [Julius Selasie Kpodo]  
> **Student Index:** [10022200112]  

---

##  Project Overview

**AcityRAG** is a fully manual Retrieval-Augmented Generation (RAG) system that answers questions about:
-  **Ghana Election Results** (2020 Presidential & Parliamentary)
-  **Ghana 2025 Budget Statement & Economic Policy**

### Core Constraint
**No LangChain, LlamaIndex, or pre-built RAG pipelines** — All components implemented from scratch:
- ✅ Data cleaning & chunking strategy
- ✅ Custom embeddings (TF-IDF + SVD)
- ✅ Vector storage (FAISS)
- ✅ Keyword search (BM25)
- ✅ Retrieval fusion (RRF)
- ✅ Prompt engineering
- ✅ Full pipeline orchestration
- ✅ Adversarial evaluation

### Innovation
**Domain-Aware Chunk Boosting**: Automatic prioritization of relevant chunk types (budget vs election) without separate indices.

---

##  Architecture

```
CSV + PDF → Clean → Chunk → Embed → FAISS + BM25 → Hybrid Retrieve → Prompt → Claude → Response
```

**Key components:**
- **Embedder**: HuggingFace `all-MiniLM-L6-v2` with manual mean-pooling (no ST wrapper)
- **Vector store**: FAISS `IndexFlatIP` (cosine similarity)
- **Keyword store**: BM25Okapi
- **Fusion**: Reciprocal Rank Fusion (RRF)
- **LLM**: Anthropic Claude Sonnet
- **UI**: Streamlit

---

##  Quick Start

```bash
# 1. Clone
git clone https://github.com/[your-username]/ai_[your-index]
cd ai_[your-index]

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install frontend dependencies
cd frontend && npm install

# 4. Add your Groq API key in .env
copy .env.example .env
# then edit .env and set GROQ_API_KEY

# 5. Build the React app
cd .. && npm run build --prefix frontend

# 6. Start the backend server
uvicorn server:app --host 0.0.0.0 --port 8000
```

Then open http://127.0.0.1:8000 in your browser.

The frontend is served by the FastAPI backend and the Groq API key is loaded from the server environment, so you do not need to enter it manually in the browser.

> If you still want to use the old Streamlit app, open `app.py`, but the new production-ready frontend is recommended for deployment.

---

##  Deployment

### Render (Recommended)

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Ready for deployment"
   git push origin main
   ```

2. **Connect to Render**
   - Go to [render.com](https://render.com) and sign up/login
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Select the repository

3. **Configure Service**
   - **Name**: `acity-rag` (or your choice)
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt && cd frontend && npm install && npm run build`
   - **Start Command**: `python -m uvicorn server:app --host 0.0.0.0 --port $PORT`

4. **Environment Variables**
   - Add `GROQ_API_KEY` with your Groq API key value
   - Make sure it's set as a secret (not synced from repo)

5. **Deploy**
   - Click "Create Web Service"
   - Wait for build and deployment (5-10 minutes)
   - Your app will be live at `https://your-service-name.onrender.com`

### Other Platforms

- **Railway**: Similar to Render, supports Python + Node.js builds
- **Heroku**: Requires `Procfile` and `package.json` in root
- **Vercel**: Frontend only, would need separate backend service

---

##  Structure

```
ai_[index]/
├── app.py              # Streamlit UI
├── requirements.txt
├── src/
│   ├── ingest.py       # Data engineering (Part A)
│   ├── embedder.py     # Embedding pipeline (Part B)
│   ├── retriever.py    # Hybrid retrieval (Part B)
│   ├── prompt.py       # Prompt engineering (Part C)
│   ├── pipeline.py     # Full RAG pipeline (Part D)
│   └── evaluate.py     # Adversarial evaluation (Part E)
├── docs/
│   ├── README.md       # Detailed documentation
│   └── experiment_log.md  # Manual experiment logs
└── logs/               # Auto-generated pipeline logs
```

---

##  Parts Covered

| Part | Topic | Marks |
|------|-------|-------|
| A | Data Engineering & Chunking | 4 |
| B | Custom Retrieval (FAISS + BM25 Hybrid) | 6 |
| C | Prompt Engineering & Experiments | 4 |
| D | Full RAG Pipeline with Logging | 10 |
| E | Adversarial Evaluation | 6 |
| F | Architecture & Design | 8 |
| G | Innovation: Memory-based RAG | 6 |
| — | Application + Video + Docs + Logs | 16 |

---

##  Deployed Application

> **Live URL:** [Add your deployment URL here]

---

##  Submission

Submitted to: godwin.danso@acity.edu.gh  
Subject: `CS4241-Introduction to Artificial Intelligence-2026:[Index] [Name]`
