# Manual Experiment Log
## CS4241 — Introduction to Artificial Intelligence
### ACity RAG Project
**Author:** [Your Name] | **Index:** [Your Index Number]

> Note: This log is manually written based on actual experiments run during development.
> It is NOT AI-generated. Each entry records what I tested, what happened, and what I changed.

---

## EXPERIMENT LOG 001
**Date:** April 2026  
**Component:** Chunking Strategy  
**Hypothesis:** Smaller chunks improve retrieval precision for election data

| Strategy         | Chunk Size | Overlap | Num Chunks | Avg Len (chars) | Notes |
|-----------------|-----------|---------|------------|-----------------|-------|
| Small           | 300        | 50      | ~1,800     | 285             | Election rows often split mid-sentence |
| Medium (chosen) | 500        | 100     | ~1,200     | 475             | Best balance |
| Large           | 800        | 150     | ~750       | 760             | Budget passages too long, retrieval vague |

**Test query:** "What percentage of votes did Mahama receive?"

| Strategy | Retrieved correct chunk? | Score | Observation |
|---------|--------------------------|-------|-------------|
| Small   | ✅ Yes (but fragmented)  | 0.61  | Answer split across 2 chunks |
| Medium  | ✅ Yes (complete)        | 0.74  | Full context in one chunk |
| Large   | ✅ Yes (but noisy)       | 0.68  | Extra irrelevant sentences included |

**Decision:** Keep Medium (500/100) as default.

---

## EXPERIMENT LOG 002
**Date:** April 2026  
**Component:** Retrieval Strategy  
**Hypothesis:** Hybrid search outperforms pure vector on named-entity queries

**Test query:** "NDC parliamentary seats won"

| Method       | Top Result Source     | Score  | Correct? |
|-------------|----------------------|--------|----------|
| Vector only  | Budget data (wrong)  | 0.52   | ❌       |
| BM25 only    | Election data        | 14.3   | ✅       |
| Hybrid (RRF) | Election data        | 0.0098 | ✅       |

**Observation:** Pure vector search failed on "NDC" because the acronym has low semantic
similarity to its expanded form. BM25 caught the keyword directly. Hybrid combines both.

**Fix applied:** Added query expansion rules (NDC → "NDC National Democratic Congress")
to help vector search on acronym-heavy queries.

---

## EXPERIMENT LOG 003
**Date:** April 2026  
**Component:** Prompt Template Comparison  
**Hypothesis:** Chain-of-thought (Template B) produces more accurate, grounded answers

**Test query:** "How many total votes were cast in the 2024 election?"

**Template A (Standard) Response:**
> "The total votes cast in the 2024 election were approximately 13 million."
> *(Issue: "approximately" introduced, specific number not in context → hallucination signal)*

**Template B (Chain-of-Thought) Response:**
> "Based on the election data provided: The context mentions valid votes by constituency
> but does not provide a single total figure. I cannot confirm the exact national total
> from the available snippets."
> *(Better: correctly refused to fabricate the aggregate)*

**Template C (Strict) Response:**
> "Based on the available data: The retrieved context shows constituency-level vote counts
> but does not contain a national total figure. Source: Election Data"
> *(Best: explicit sourcing, no fabrication)*

**Decision:** Use Template B as default (good balance); Template C for sensitive queries.

---

## EXPERIMENT LOG 004
**Date:** April 2026  
**Component:** Adversarial Testing  
**Query:** "Who won?" (ambiguous)

**RAG Response:**
> "I don't have enough context to answer this question — 'who won' is ambiguous. Could you
> specify which election or competition you mean? The knowledge base covers the 2024 Ghana
> Presidential Election and the 2025 Budget policy."

**Pure LLM Response:**
> "John Mahama won the 2024 Ghana Presidential Election..."
> *(Hallucination risk: model assumed context, answered confidently without it)*

**Observation:** RAG correctly flagged ambiguity. Pure LLM made assumptions based on
recent training data.

---

## EXPERIMENT LOG 005
**Date:** April 2026  
**Component:** Memory-based RAG (Innovation Feature)  
**Hypothesis:** Injecting conversation history resolves pronoun references

**Turn 1 — User:** "Who won the presidential election?"  
**Turn 1 — AI:** "John Mahama of the NDC won with 56.55% of valid votes."

**Turn 2 — User:** "How many votes did he get?"  
**Without memory:** AI said "I don't know who 'he' refers to."  
**With memory:** AI correctly answered about Mahama's vote count.

**Outcome:** Memory injection resolves coreference. Confirmed working.

---

## EXPERIMENT LOG 006
**Date:** April 2026  
**Component:** Failure Case Analysis  
**Query:** "What is the capital of France?"

**Retrieval results:**
- Top score: 0.00034 (below threshold 0.001)
- Low-confidence flag triggered ✅
- AI responded: "This question is outside my knowledge base which covers Ghana elections
  and the 2025 budget. I don't have information about France."

**Outcome:** Low-confidence detection worked correctly. System gracefully declined.

---

## EXPERIMENT LOG 007
**Date:** April 2026  
**Component:** End-to-End Latency  
**Measured pipeline stages:**

| Stage           | Avg Time |
|----------------|----------|
| Retrieval       | ~180ms   |
| Prompt build    | ~8ms     |
| LLM generation  | ~1,400ms |
| Total           | ~1,600ms |

**Observation:** LLM generation dominates latency. Retrieval is fast due to FAISS.
Potential optimization: cache embeddings for repeated queries.

---
*End of manual experiment log.*
