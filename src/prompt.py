"""
prompt.py - Prompt Engineering & Generation (Part C)
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Maximum characters of context to inject into the prompt.
# GPT-4/Claude context windows are large, but keeping context focused
# (≤3000 chars ≈ 750 tokens) prevents the model diluting attention.
MAX_CONTEXT_CHARS = 3000

# ── Prompt Templates ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are ACity Intelligence, an AI assistant for Academic City University Ghana.
You answer questions about:
  • Ghana's 2024 Presidential and Parliamentary Election Results
  • Ghana's 2025 Budget Statement and Economic Policy

Rules you MUST follow:
1. Base your answer ONLY on the provided context snippets.
2. If the context does not contain enough information, say:
   "I don't have enough information in my knowledge base to answer that question accurately."
3. Do NOT invent figures, names, or policy details not present in the context.
4. When citing facts, reference the source (Election Data or Budget Statement).
5. Be concise but complete. Use bullet points for lists of facts.
"""

# Template A — Standard RAG prompt (baseline)
TEMPLATE_A = """[CONTEXT]
{context}

[QUESTION]
{question}

[INSTRUCTIONS]
Answer using only the context above. If the answer is not in the context, say so clearly.
"""

# Template B — Chain-of-thought prompt (more structured reasoning)
TEMPLATE_B = """[CONTEXT]
{context}

[QUESTION]
{question}

[INSTRUCTIONS]
Think step by step:
1. Identify which context snippets are relevant to the question.
2. Extract the key facts needed.
3. Construct a clear, factual answer citing those facts.
4. If the context is insufficient, state that explicitly.

Answer:
"""

# Template C — Strict grounding prompt (maximum hallucination control)
TEMPLATE_C = """[VERIFIED CONTEXT — treat as ground truth]
{context}

[USER QUESTION]
{question}

[STRICT RULES]
- You are a fact-retrieval system. Do NOT add any information beyond what is in the context above.
- If a specific number, name, or claim is not in the context, do NOT guess.
- Begin your answer with: "Based on the available data:"
- End with: "Source: [Election Data / Budget Statement / Both]"
"""


def select_template(variant: str = "A") -> str:
    """Return the named prompt template."""
    return {"A": TEMPLATE_A, "B": TEMPLATE_B, "C": TEMPLATE_C}.get(variant.upper(), TEMPLATE_A)


# ── Context Window Management ─────────────────────────────────────────────────

def rank_and_filter_chunks(
    chunks: List[Dict],
    query: str,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> List[Dict]:
    """
    Context window management:
    1. Sort chunks by similarity score (already done by retriever, but re-sort defensively)
    2. Prefer chunks that match query keywords (domain boost)
    3. Truncate to stay within max_chars budget

    Returns filtered, ordered list of chunks.
    """
    # Sort by score descending
    ranked = sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)

    # Keyword domain boost: move chunks whose source or text matches query domain to top
    query_lower = query.lower()
    election_keywords = {"election", "vote", "votes", "npp", "ndc", "presidential", "parliament", "constituency"}
    budget_keywords   = {"budget", "fiscal", "gdp", "revenue", "expenditure", "tax", "inflation", "economy"}
    education_keywords = {"education", "school", "teacher", "student", "learning", "university", "curriculum"}

    wants_election = bool(election_keywords & set(query_lower.split()))
    wants_budget   = bool(budget_keywords   & set(query_lower.split()))
    wants_education = bool(education_keywords & set(query_lower.split()))

    def domain_boost(chunk):
        t = chunk.get("type", "")
        boost = 0
        if wants_election and t == "election_data":
            boost += 1
        if wants_budget and t == "budget_data":
            boost += 1
        if wants_education:
            chunk_text = chunk.get("text", "").lower()
            if any(term in chunk_text for term in education_keywords):
                boost += 3
        return boost

    ranked.sort(key=domain_boost, reverse=True)

    # Truncate to budget
    selected = []
    total    = 0
    for chunk in ranked:
        text_len = len(chunk["text"])
        if total + text_len > max_chars:
            # Include a truncated version if we have space for at least 100 chars
            remaining = max_chars - total
            if remaining > 100:
                trunc = chunk.copy()
                trunc["text"] = chunk["text"][:remaining] + "..."
                selected.append(trunc)
            break
        selected.append(chunk)
        total += text_len

    logger.info(
        f"Context manager: {len(chunks)} chunks -> {len(selected)} selected "
        f"({total} chars, budget={max_chars})"
    )
    return selected


def build_context_string(chunks: List[Dict]) -> str:
    """
    Format selected chunks into a numbered context block for injection.
    """
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "Unknown")
        score  = chunk.get("score", 0)
        parts.append(
            f"[Snippet {i} | Source: {source} | Relevance: {score:.4f}]\n"
            f"{chunk['text']}"
        )
    return "\n\n".join(parts)


from typing import Tuple


def build_prompt(
    query: str,
    chunks: List[Dict],
    variant: str = "A",
    max_context_chars: int = MAX_CONTEXT_CHARS,
) -> Tuple[str, str, List[Dict]]:
    """
    Full prompt builder.
    Returns: (system_prompt, user_prompt, selected_chunks)
    """
    selected    = rank_and_filter_chunks(chunks, query, max_context_chars)
    context     = build_context_string(selected)
    template    = select_template(variant)
    user_prompt = template.format(context=context, question=query)

    logger.info(
        f"Prompt built [variant={variant}]: "
        f"{len(selected)} snippets, {len(user_prompt)} chars"
    )
    return SYSTEM_PROMPT, user_prompt, selected


# ── Experiment: compare prompt variants ──────────────────────────────────────

def compare_prompt_variants(query: str, chunks: List[Dict]) -> Dict[str, str]:
    """
    Part C experiment requirement:
    Build the same query with all 3 template variants.
    Returns dict of variant → user_prompt for inspection/logging.
    """
    results = {}
    for v in ["A", "B", "C"]:
        _, user_prompt, _ = build_prompt(query, chunks, variant=v)
        results[v] = user_prompt
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    sample_chunks = [
        {
            "id": "election_0001",
            "text": "John Mahama of the NDC won the 2024 presidential election with 56.55% of valid votes cast.",
            "source": "Ghana Election Results",
            "type": "election_data",
            "score": 0.92,
        },
        {
            "id": "budget_0010",
            "text": "The 2025 budget targets a GDP growth rate of 4.0% with a fiscal deficit of 3.8% of GDP.",
            "source": "Ghana 2025 Budget Statement",
            "type": "budget_data",
            "score": 0.45,
        },
    ]

    query = "Who won the 2024 Ghana election?"
    sys_p, usr_p, selected = build_prompt(query, sample_chunks, variant="B")
    print("=== SYSTEM ===")
    print(sys_p)
    print("\n=== USER PROMPT ===")
    print(usr_p)
