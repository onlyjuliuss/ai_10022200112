# Architecture & System Design - CS4241 RAG Project

## System Architecture Overview

### High-Level Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      USER INTERACTION LAYER                     │
│                    (Streamlit Web Interface)                    │
│                                                                 │
│  Input Box: "What are main revenue sources in 2025 budget?"   │
│           ↓                                                     │
│     User Query                                                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ↓
┌──────────────────────────────────────────────────────────────────┐
│                   QUERY PROCESSING LAYER                        │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. Query Expansion Module                               │   │
│  │    Input: "revenue sources budget 2025"                │   │
│  │    Expansion Dict: {                                    │   │
│  │      "revenue": [...],                                 │   │
│  │      "budget": [...],                                  │   │
│  │      "2025": [...]                                     │   │
│  │    }                                                    │   │
│  │    Output: "revenue sources budget 2025 tax fiscal..." │   │
│  └────────────┬────────────────────────────────────────────┘   │
│               ↓                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 2. Embedding Generation (TF-IDF + SVD)                 │   │
│  │    Input: Expanded query text                           │   │
│  │    Dimension: 384                                       │   │
│  │    Output: Query embedding vector [0.2, 0.5, ...]     │   │
│  └────────────┬────────────────────────────────────────────┘   │
└───────────────┼──────────────────────────────────────────────────┘
                │
                ↓
┌──────────────────────────────────────────────────────────────────┐
│                   RETRIEVAL LAYER                               │
│                                                                  │
│  ┌──────────────────────┬──────────────────────┐               │
│  │                      │                      │               │
│  ↓                      ↓                      ↓               │
│ FAISS Index         BM25 Index          Query Vector          │
│ (2143 vectors)      (2143 docs)         (384 dims)            │
│                                                                 │
│  ┌──────────────────────────────────────────────┐             │
│  │ Vector Search (FAISS)                        │             │
│  │ - Find k=10 nearest neighbors                │             │
│  │ - Similarity scores: [0.92, 0.87, 0.85...] │             │
│  └──────────────────────────────────────────────┘             │
│                        │                                       │
│  ┌──────────────────────────────────────────────┐             │
│  │ Keyword Search (BM25)                        │             │
│  │ - Find k=10 matching documents               │             │
│  │ - BM25 scores: [0.88, 0.82, 0.79...]       │             │
│  └──────────────────────────────────────────────┘             │
│                        │                                       │
│                        ↓                                       │
│  ┌──────────────────────────────────────────────┐             │
│  │ Reciprocal Rank Fusion (RRF)                 │             │
│  │ - Combine vector + keyword scores             │             │
│  │ - Weights: 70% vector, 30% keyword            │             │
│  │ - Formula: RRF_score = 0.7*(1/(60+v_rank))  │             │
│  │            + 0.3*(1/(60+k_rank))             │             │
│  │ - Output: Top 5 ranked chunks with scores    │             │
│  └──────────────────────────────────────────────┘             │
└─────────────────────────┬──────────────────────────────────────┘
                          │
                          ↓
┌──────────────────────────────────────────────────────────────────┐
│                  RANKING & FILTERING LAYER                      │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Domain-Aware Chunk Type Boosting                        │   │
│  │                                                          │   │
│  │ Query keywords: {"budget", "revenue", "fiscal"}         │   │
│  │                                                          │   │
│  │ For each chunk:                                         │   │
│  │   if chunk_type == "budget_data":                      │   │
│  │     score *= 50.0  (BOOST)                            │   │
│  │   else if chunk_type == "election_data":              │   │
│  │     score *= 1.0   (NEUTRAL)                          │   │
│  │                                                          │   │
│  │ Output: Re-ranked chunks by boosted scores              │   │
│  └────────────┬──────────────────────────────────────────┘   │
│               │                                                │
│  ┌────────────┴──────────────────────────────────────────┐   │
│  │ Context Window Management (Max 3000 chars)            │   │
│  │                                                         │   │
│  │ Input: [chunk1: 520 chars, chunk2: 480 chars,         │   │
│  │         chunk3: 450 chars, ...]                       │   │
│  │                                                         │   │
│  │ Algorithm:                                             │   │
│  │   total_chars = 0                                      │   │
│  │   for chunk in ranked_chunks:                          │   │
│  │     if total_chars + len(chunk) > 3000:               │   │
│  │       break                                            │   │
│  │     selected.append(chunk)                             │   │
│  │     total_chars += len(chunk)                          │   │
│  │                                                         │   │
│  │ Output: 5 selected chunks (total: 2498 chars)         │   │
│  └─────────────────────────────────────────────────────┬──┘   │
│                                                         │       │
└─────────────────────────────────────────────────────────┼───────┘
                                                          │
                                                          ↓
┌──────────────────────────────────────────────────────────────────┐
│              PROMPT CONSTRUCTION & LLM LAYER                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ System Prompt                                            │  │
│  │ ────────────────────────────────────────────────────   │  │
│  │ "You are a helpful assistant answering questions about  │  │
│  │  Ghana's election results and 2025 budget. Answer based │  │
│  │  ONLY on the provided context. If not found, say so."  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Context Block (Injected)                                │  │
│  │ ────────────────────────────────────────────────────   │  │
│  │ Context from retrieved chunks (5 snippets):            │  │
│  │                                                          │  │
│  │ [Chunk 1] "Petroleum receipts estimated at US$818.69m" │  │
│  │ [Chunk 2] "Tax revenue: enhanced administration..."    │  │
│  │ [Chunk 3] "External grants: GH 2.7 billion"           │  │
│  │ [Chunk 4] "SSNIT transfers to NHIL: GH 7.9 billion"  │  │
│  │ [Chunk 5] "Fiscal consolidation program..."            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ User Prompt                                              │  │
│  │ ────────────────────────────────────────────────────   │  │
│  │ "What are the main revenue sources in the 2025         │  │
│  │  Ghana budget?"                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                        │                                        │
│                        ↓                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Groq LLM (llama-3.3-70b-versatile)                      │  │
│  │ - Model: Llama 3.3 70B parameters                        │  │
│  │ - API: https://api.groq.com/openai/v1/chat/completions│  │
│  │ - Temperature: 0.7 (balanced creativity)                │  │
│  │ - Max tokens: 1024                                      │  │
│  │ - Processing time: 1-3 seconds                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                        │                                        │
│                        ↓                                        │
│          Generated Response Text (max 1024 tokens)              │
│                                                                  │
└───────────────┬────────────────────────────────────────────────┘
                │
                ↓
┌──────────────────────────────────────────────────────────────────┐
│              OUTPUT & DISPLAY LAYER                             │
│              (Streamlit Frontend)                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Display Retrieved Chunks with Metadata                   │  │
│  │ ─────────────────────────────────────────────────────── │  │
│  │ 📄 Chunk 1 (Type: budget_data, Score: 0.98)            │  │
│  │    "Petroleum receipts estimated at US$818.69m net..."  │  │
│  │                                                           │  │
│  │ 📄 Chunk 2 (Type: budget_data, Score: 0.94)            │  │
│  │    "Tax revenue will be enhanced through..."            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Final Response in Chat Bubble                            │  │
│  │ ─────────────────────────────────────────────────────── │  │
│  │ Based on the 2025 Ghana budget, the main revenue        │  │
│  │ sources are:                                             │  │
│  │                                                           │  │
│  │ 1. Tax Revenue - enhanced through tax policy measures   │  │
│  │ 2. Petroleum Receipts - US$818.69 million              │  │
│  │ 3. Grants from Partners - GH 2.7 billion               │  │
│  │ 4. Other Revenue - GH 7.9 billion (SSNIT/ESL)         │  │
│  │                                                           │  │
│  │ These revenue sources are projected to increase...      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Component Architecture

### 1. **Data Ingestion Module** (`src/ingest.py`)

**Purpose**: Load, clean, and chunk raw data sources

**Components**:
- `load_and_clean_csv()`: Pandas DataFrame cleaning
- `csv_to_text_chunks()`: Convert rows to semantic chunks
- `load_and_clean_pdf()`: PDF text extraction via pdfplumber
- `pdf_to_text_chunks()`: Semantic chunking (500 chars / 100 overlap)
- `run_ingestion()`: Orchestrator function

**Output**: `chunks.json` (2143 chunks with metadata)
```json
{
  "id": "chunk_0001",
  "text": "...",
  "type": "budget_data" | "election_data",
  "source": "2025_Budget.pdf",
  "page": 12
}
```

### 2. **Embedding Module** (`src/embedder.py`)

**Purpose**: Generate vector representations for text

**Architecture**:
- TF-IDF vectorizer: 10,000 vocabulary
- SVD dimensionality reduction: 384 dimensions
- Batch processing: 64 texts per batch

**Methods**:
- `embed()`: Batch embedding
- `embed_single()`: Single query embedding

**Why TF-IDF + SVD?**
- Lightweight (no external API calls)
- Fast inference (<100ms for 2143 chunks)
- Deterministic (no randomness)
- Interpretable dimensions (word importance weights)

### 3. **Retrieval Module** (`src/retriever.py`)

**Components**:
- **VectorStore**: FAISS index wrapper
  - Stores 2143 embedding vectors (384 dims)
  - Implements: `add()`, `search()`, `save()`, `load()`
  
- **BM25Index**: Okapi BM25 keyword search
  - Tokenized full-text index
  - Implements: `build()`, `search()`
  
- **HybridRetriever**: Fusion orchestrator
  - RRF formula: Combine vector + keyword ranks
  - Domain boosting: Chunk type prioritization
  - Query expansion: Add synonyms

### 4. **Prompt Module** (`src/prompt.py`)

**Functions**:
- `rank_and_filter_chunks()`: Context selection algorithm
  - Keyword domain detection
  - Budget vs election prioritization
  - Character budget truncation (max 3000)
  
- `build_prompt()`: Template injection
  - System prompt (identity + constraints)
  - Context block (formatted chunks)
  - User prompt (original query)

### 5. **Pipeline Module** (`src/pipeline.py`)

**Purpose**: Orchestrate complete RAG flow

**Class: RAGPipeline**
```python
class RAGPipeline:
    __init__()          # Initialize all components
    _setup()            # Load/build indices
    query()             # Main entry point (query → response)
    _call_llm()         # API call to Groq
```

**Data Flow**:
1. User query
2. Expand with synonyms
3. Retrieve top-k chunks
4. Re-rank with domain boosting
5. Select context window
6. Build prompts
7. Call LLM
8. Return response + trace

### 6. **Frontend Module** (`app.py`)

**Framework**: Streamlit

**Components**:
- Session state management
- Chat history persistence
- Creative chat bubble rendering
- Retrieved chunks display
- Similarity score visualization

---

## Design Justification

### Why This Architecture?

#### 1. **Modular Design**
- Each component independently testable
- Easy to replace embedding method (TF-IDF → Sentence Transformers)
- Supports adding new data sources (easy to extend)

#### 2. **Hybrid Retrieval Over Pure Vector Search**
- Vector search: Great for semantic similarity, weak on rare terms
- BM25: Excellent for exact matches, weak on semantics
- RRF Fusion: Combines strengths, eliminates weaknesses
- **Evidence**: Experiment 2 shows +40% accuracy with hybrid

#### 3. **Domain-Aware Boosting**
- Raw retrieval mixes election and budget chunks (equal weight)
- Query "revenue" naturally matches both domains
- Solution: Chunk type boosting based on domain keywords
- **Impact**: Resolves ambiguity without separate indices

#### 4. **Context Window Management**
- LLM context limit: ~4096 tokens
- Groq default budget: ~2000 tokens for generation
- Solution: Hard limit of 3000 chars + intelligent selection
- **Benefit**: Prevent context overflow while maintaining quality

#### 5. **Prompt Engineering Approach**
- System prompt: Sets identity + constraints
- Context injection: Provides grounding
- User prompt: Preserves original query
- **Result**: 0% hallucination rate (Experiment 5)

### Why NOT Other Approaches?

#### ❌ Why Not LangChain/LlamaIndex?
- **Exam constraint**: "NOT allowed to use end-to-end frameworks"
- **Learning**: Manual implementation teaches RAG concepts deeply
- **Control**: Full visibility into each component's behavior

#### ❌ Why Not Pure Vector Search?
- Fails on rare terms: "SSNIT", "GNPC" (budget-specific acronyms)
- Fails on numeric queries: "GH 16.5 billion" (exact matches important)
- Wastes retrieval slots on irrelevant high-similarity chunks

#### ❌ Why Not Separate Indices?
- Increases complexity (dual embedding, dual storage)
- Requires explicit domain labeling in UI
- Domain boosting solves it with simpler logic

---

## Scalability Considerations

### Current System
- **Data Size**: 2143 chunks (compact, fits in memory)
- **Embedding Dim**: 384 (fast, small)
- **Retrieval**: <100ms (interactive)
- **LLM Latency**: 1-3 seconds (network-bound)

### Scaling to 100,000 chunks
- FAISS supports GPU indexing (IVF for 100K+)
- BM25 already incremental
- Chunking strategy holds (no changes needed)

### Scaling to Real-Time
- Cache embeddings on disk (current: in-memory)
- Implement semantic caching (identical queries)
- Use batch processing for off-peak ingestion

---

## Failure Modes & Mitigations

| Failure Mode | Detection | Mitigation |
|---|---|---|
| **Empty Retrieval** | No chunks match | Ask user to clarify query |
| **Low Similarity** | Top-k score < 0.5 | Flag confidence, suggest alternatives |
| **Context Overflow** | Token count > limit | Truncate + preserve snippet markers |
| **Domain Confusion** | Mixed chunk types | Boost relevant type by 50x |
| **Hallucination** | Answer unsupported by context | "Not found in knowledge base" |
| **LLM Timeout** | API no response >10s | Retry with shorter context |

---

## Monitoring & Observability

### Logging Strategy
Every stage logs:
- Input/output
- Processing time
- Scores/metrics
- Decision points

### Trace Structure
```python
{
    "query": "...",
    "expanded_query": "...",
    "retrieved_chunks": [...],
    "selected_chunks": [...],
    "system_prompt": "...",
    "user_prompt": "...",
    "llm_response": "...",
    "latency_ms": {...},
    "low_confidence": false,
    "timestamp": "2026-04-25T..."
}
```

### Output to File
- `logs/traces.jsonl`: One JSON per query
- Enables: Debugging, analytics, quality monitoring

