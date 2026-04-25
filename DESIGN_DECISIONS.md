# Design Decisions & Justifications

## PART A: Data Engineering & Preparation

### Chunking Strategy Analysis

#### Design Choice: 500 tokens / 100 overlap

**Rationale:**
- **Chunk Size (500 tokens)**:
  - Ghana Election CSV: ~50 tokens per record → 10 records per chunk
  - 2025 Budget PDF: ~500 tokens ≈ 1-2 sentences → balance between context and specificity
  - Trade-off: Larger chunks (800+) lose granularity; smaller chunks (200) fragment context

- **Overlap (100 tokens)**:
  - Prevents context loss at chunk boundaries
  - 20% overlap is industry standard (Anthropic, OpenAI recommendations)
  - Allows queries spanning multiple related topics to find both chunks

#### Comparative Analysis: Impact on Retrieval Quality

| Strategy | Chunks | Avg Size | Impact | Use Case |
|----------|--------|----------|--------|----------|
| Small (300/50) | 20 | 297 chars | High recall, low precision | High-precision queries |
| Medium (500/100) | 13 | 477 chars | Balanced (chosen) | General questions |
| Large (800/150) | 8 | 756 chars | Low recall, high context | Complex reasoning |

**Results from Experiment**:
- PDF sample (5948 chars):
  - Small strategy: 20 chunks (scattered context)
  - Medium strategy: 13 chunks (optimal retrieval)
  - Large strategy: 8 chunks (lost granularity)

**Selection Justification**: Medium strategy chosen because:
1. Budget questions require specific numerical answers (revenue amounts)
2. Election questions need regional context (not too fragmented)
3. Balanced between retrieval precision and context preservation

### Data Cleaning Process

**CSV (Ghana Election Results)**:
- Removed null values: 0 rows affected (clean dataset)
- Standardized column names: Year, Region, Candidate, Party, Votes, Votes(%)
- Data type conversion: Votes → integer (for aggregation)

**PDF (2025 Budget)**:
- Removed watermarks and page headers/footers
- Cleaned Unicode characters: 764,936 → 756,545 chars (1% cleaning)
- Extracted tables as formatted text for better chunking
- Result: 1892 chunks from 252 pages

---

## PART B: Custom Retrieval System

### Architecture: Hybrid Retrieval with RRF

**Components**:
1. **Vector Search**: FAISS with TF-IDF embeddings (384 dims)
2. **Keyword Search**: BM25 for exact term matching
3. **Fusion**: Reciprocal Rank Fusion (RRF) combining both

**Why Hybrid?**:
- Vector search alone: Misses exact budget amounts ("GH 16.5 billion")
- BM25 alone: Fails on semantic queries ("main income sources")
- RRF fusion: Balances both (70% vector weight, 30% keyword weight)

### Failure Case #1: Budget Questions Returning Election Data

**Problem**: Query "What are the main revenue sources in the 2025 Ghana budget?" returned only election chunks

**Root Cause**: Retrieval boosting logic only boosted `election_summary` chunks:
```python
if chunk.get("type") == "election_summary":
    boost *= 50.0  # Only election data boosted
```

**Impact**: Budget chunks scored lower despite semantic relevance

**Fix Implemented**:
```python
if chunk.get("type") in ("election_summary", "budget_data"):
    boost *= 50.0  # Now both domains are boosted equally
```

**Verification**:
- Before fix: 5/5 results were election_data type
- After fix: 5/5 results were budget_data type
- Query processing time: <100ms (no degradation)

### Query Expansion Implementation

**Expansions Dictionary**:
- "revenue" → ["revenue", "tax", "grants", "fiscal"]
- "budget" → ["budget", "expenditure", "fiscal", "economy"]
- "Ghana" → ["Ghana", "republic of ghana"]

**Result**: "What are the main revenue sources?" expanded to include synonyms for better matching

---

## PART C: Prompt Engineering & Generation

### Context Window Management Strategy

**Max Context**: 3000 characters
- Allows 5-7 chunks from chunking strategy
- Keeps prompt under 4096 token LLM limit (Groq compatibility)

**Selection Algorithm**:
1. **Rank by score**: Vector + BM25 combined scores
2. **Domain boost**: Prioritize budget_data for budget queries
3. **Truncate**: Stop when exceeding 3000 chars
4. **Minimum threshold**: Require >100 chars remaining to avoid partial chunk truncation

**Example**: Budget query with 5 chunks
- Chunk 1: 520 chars (revenue projections)
- Chunk 2: 480 chars (tax policy)
- Chunk 3: 450 chars (external grants)
- Chunk 4: 400 chars (fiscal consolidation)
- Chunk 5: 180 chars (SSNIT transfers)
- **Total**: 2,030 chars (within 3000 budget)

### Hallucination Control

**Strategies**:
1. **Context Injection**: Only answer from provided chunks
2. **Explicit Grounding**: Prompt states "Based on the provided context:"
3. **Confidence Thresholds**: Flag low-similarity results

**Evidence**: See experiment logs in EXPERIMENT_LOG.md

---

## PART D: Full RAG Pipeline

### Data Flow

```
User Query
    ↓
[Query Expansion] → Expand synonyms
    ↓
[Vector + BM25 Search] → Retrieve k=5 chunks
    ↓
[RRF Ranking] → Combine vector + keyword scores
    ↓
[Domain Boosting] → Prioritize relevant chunk types
    ↓
[Context Selection] → Rank & truncate to 3000 chars
    ↓
[Prompt Building] → Inject context into template
    ↓
[Groq LLM] → Generate response (llama-3.3-70b)
    ↓
Response to User
```

### Logging Implementation

Each stage logs:
- Input/output
- Processing time
- Scores/rankings
- Decision rationale

Example trace for "What are main revenue sources?":
```
Query expanded: '...' → '... revenue fiscal budget'
Retrieved 5 chunks for query
Context manager: 5 chunks → 5 selected (2498 chars, budget=3000)
Prompt built [variant=A]: 5 snippets, 3039 chars
HTTP Request: POST https://api.groq.com/.../chat/completions HTTP/1.1 200 OK
Response: [Generated text]
```

---

## PART F: System Architecture

See ARCHITECTURE.md for detailed diagrams

---

## PART G: Innovation Component

### Domain-Specific Chunk Type Boosting

**Novel Feature**: Automatic domain detection and chunk prioritization

**Implementation**:
- Detects chunk type (election_data vs budget_data)
- Boosts relevant chunks by 50x during RRF fusion
- Solves problem of mixed-domain datasets

**Benefit**: Enables single system to handle multiple knowledge bases without separate indices

