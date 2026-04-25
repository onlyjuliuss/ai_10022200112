# ACity Intelligence — RAG Chat System
## Detailed Technical Documentation
### CS4241 — Introduction to Artificial Intelligence | 2026
**Author:** [Your Name] | **Index:** [Your Index Number]  
**Lecturer:** Godwin N. Danso

---

## 1. Project Overview

ACity Intelligence is a Retrieval-Augmented Generation (RAG) chat assistant built for
Academic City University. It answers questions grounded in two specific datasets:
- Ghana's 2024 Presidential and Parliamentary Election Results (CSV)
- Ghana's 2025 Budget Statement and Economic Policy (PDF)

All core RAG components (retrieval, chunking, embedding, prompt construction) are
implemented manually without LangChain, LlamaIndex, or any pre-built RAG pipeline.

---

## 2. Architecture Overview

```
Data Sources → Ingestion (clean + chunk) → Embedding → FAISS + BM25 Index
                                                               ↓
User Query → Expand → Hybrid Retrieve → Rank/Filter → Prompt Build → LLM → Response
```

See `docs/architecture_diagram` for a visual representation (also in the app under
the Architecture tab).

---

## 3. Part A: Data Engineering & Preparation

### 3.1 Data Sources
- **CSV**: `Ghana_Election_Result.csv` — rows contain constituency, candidate, party,
  and vote data for the 2024 elections.
- **PDF**: `2025-Budget-Statement.pdf` — 200+ page government document with tables,
  narrative sections, and economic forecasts.

### 3.2 Cleaning Strategy
**CSV:**
1. Strip column name whitespace
2. Convert all string cells to stripped strings
3. Replace "nan" artifacts from `astype(str)` conversion
4. Drop fully-empty rows

**PDF:**
1. Extract text page-by-page using `pdfplumber`
2. Remove non-printable characters
3. Collapse 3+ consecutive newlines to 2
4. Remove standalone page number lines (regex: `^\s*\d+\s*$`)
5. Collapse multiple spaces

### 3.3 Chunking Design
**Method:** Sliding window chunking at the character level.

**Parameters chosen:** size=500 chars, overlap=100 chars

**Justification:**
- 500 chars ≈ 100-125 tokens — enough for 2-3 dense sentences of context without
  overwhelming the model's attention or diluting retrieval signals.
- 100-char overlap ensures facts near chunk boundaries appear in at least one
  neighbouring chunk, preventing split-answer failures.

**Comparison (see Experiment Log 001):**
| Strategy | Chunks | Pros | Cons |
|---------|--------|------|------|
| 300/50  | ~1800  | Precise | Splits sentences; fragmented answers |
| 500/100 | ~1200  | Balanced | Best retrieval precision |
| 800/150 | ~750   | Full context | Noisy; retrieval too broad |

---

## 4. Part B: Custom Retrieval System

### 4.1 Embedding Pipeline
**Model:** `sentence-transformers/all-MiniLM-L6-v2` via HuggingFace `transformers`

**Implementation (manual):**
1. Tokenise texts with `AutoTokenizer`
2. Forward pass through `AutoModel`
3. **Manual mean pooling** of `last_hidden_state` weighted by attention mask
4. L2 normalisation of pooled vectors
5. Output: 384-dimensional float32 vectors

No `sentence_transformers` wrapper is used — the pooling is coded from scratch.

### 4.2 Vector Storage
**FAISS IndexFlatIP** (inner product on L2-normalised vectors = cosine similarity).
Chosen because:
- No approximation (exact search) — acceptable at our scale (~1200 chunks)
- Fast: FAISS written in C++, sub-millisecond queries
- Persistent: serialised to disk with `faiss.write_index`

### 4.3 BM25 Index
Implemented using `rank_bm25.BM25Okapi` with whitespace tokenisation.
Used as the keyword component of hybrid search.

### 4.4 Hybrid Search (Extension Feature)
**Method:** Reciprocal Rank Fusion (RRF)

Formula: `score(d) = Σ 1 / (k + rank(d))` where k=60

Both vector and BM25 top-2k results are merged via RRF with configurable weights
(default: 0.7 vector, 0.3 keyword). RRF is robust to score-scale differences.

### 4.5 Query Expansion
Domain-specific synonym expansion applied before embedding:
- "npp" → adds "New Patriotic Party"
- "budget" → adds "fiscal expenditure revenue"
- "winner" → adds "won elected victory"
- etc.

### 4.6 Failure Cases
**Observed failure:** Vector search returned budget chunks for query "NDC parliamentary
seats" because "NDC" (an acronym) has low semantic overlap with related terms.

**Fix:** Query expansion adds full party name; hybrid RRF lets BM25 keyword match
compensate when vector similarity fails on acronyms.

**Low-confidence detection:** If top retrieval score < 0.001, system flags the result
and warns the user rather than confidently answering from weak context.

---

## 5. Part C: Prompt Engineering

### 5.1 System Prompt
Establishes the assistant's identity, scope, and strict grounding rules:
- Answer only from provided context
- If context is insufficient, say so explicitly
- Cite sources (Election Data / Budget Statement)
- Do not invent figures

### 5.2 Template Variants
- **Template A** — Standard: minimal instruction, inject context, answer question
- **Template B** — Chain-of-thought: explicit step-by-step reasoning before answering
- **Template C** — Strict: maximum hallucination control with mandatory sourcing prefix

### 5.3 Context Window Management
1. Sort chunks by similarity score (descending)
2. Domain-priority re-rank: election chunks boosted for election queries; budget chunks boosted for budget queries
3. Truncate at 3000 chars (≈750 tokens) — keeps model attention focused
4. Partial chunks included at boundary to avoid wasted budget

### 5.4 Prompt Experiment Results
See Experiment Log 003 for detailed comparison. Summary:
- Template B showed best accuracy on factual queries
- Template C showed best hallucination control on uncertain queries
- Template A sometimes added fabricated specificity ("approximately X million")

---

## 6. Part D: Full RAG Pipeline

Pipeline stages with logging:
1. **Retrieval** — hybrid search, expand query, detect low confidence
2. **Prompt construction** — rank/filter chunks, build context string, select template
3. **Memory injection** — last 3 conversation turns added (Part G innovation)
4. **LLM generation** — Anthropic Claude Sonnet API call
5. **Trace save** — full stage log saved to `logs/traces.jsonl`

Every stage logs: timing (ms), chunk count, scores, prompt preview, and response preview.

---

## 7. Part E: Adversarial Evaluation

Four adversarial queries designed:
1. **Ambiguous** — "Who won?" → tests refusal/clarification
2. **Misleading** — asks for 2023 data in a 2025 document → tests date awareness
3. **Out-of-scope** — "Capital of France?" → tests scope enforcement
4. **Incomplete** — "How many votes did he get?" → tests coreference handling

Metrics measured:
- **Grounding score**: overlap between response vocabulary and chunk vocabulary
- **Hallucination flag**: confident numbers in response not supported by chunks
- **Correct refusal**: whether system flagged ambiguity/out-of-scope correctly

Evidence: See `logs/evaluation_results.json` after running evaluation.

---

## 8. Part F: Architecture & System Design

### Why this architecture suits the domain:
1. **Hybrid search** — election data is acronym-heavy (NPP, NDC, EC) requiring keyword
   matching, while budget data is narrative and benefits from semantic similarity.
2. **Custom chunking** — both document types vary in density; the manual chunker
   is tuned per source type.
3. **Memory-based RAG** — election Q&A naturally generates follow-up questions
   ("who won?" → "how many votes did he get?"). Memory resolves pronoun references.
4. **Strict prompt templates** — government data requires high precision; hallucinated
   vote counts or budget figures would be misinformation.

---

## 9. Part G: Innovation — Memory-Based RAG

**Feature:** Conversation history injection into the LLM context.

**Implementation:**
- `conversation_history` list maintained in `RAGPipeline`
- Last 3 turns (6 messages) injected before the current user prompt
- History capped at 20 messages to prevent context explosion
- `clear_memory()` method exposed in UI

**Evidence of improvement:** Experiment Log 005 shows that follow-up questions
using pronouns ("he", "they", "it") are correctly resolved with memory enabled
but fail without it.

---

## 10. Setup & Deployment

### Local Setup
```bash
git clone https://github.com/[username]/ai_[index_number]
cd ai_[index_number]
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
streamlit run app.py
```

### Deployment (Render)
1. Push repo to GitHub
2. Create new Web Service on render.com
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
5. Add environment variable: `ANTHROPIC_API_KEY`

---

## 11. File Structure

```
ai_[index_number]/
├── app.py                   # Streamlit UI
├── requirements.txt         # Dependencies
├── src/
│   ├── __init__.py
│   ├── ingest.py            # Part A: Data engineering
│   ├── embedder.py          # Part B: Embedding pipeline
│   ├── retriever.py         # Part B: FAISS + BM25 hybrid retrieval
│   ├── prompt.py            # Part C: Prompt engineering
│   ├── pipeline.py          # Part D: Full RAG pipeline
│   └── evaluate.py          # Part E: Adversarial evaluation
├── data/
│   ├── raw/                 # Downloaded CSV + PDF
│   └── processed/           # chunks.json + faiss.index
├── logs/
│   ├── ingest.log
│   ├── pipeline.log
│   ├── traces.jsonl
│   └── evaluation_results.json
└── docs/
    ├── README.md             # This file
    └── experiment_log.md     # Manual experiment records
```
