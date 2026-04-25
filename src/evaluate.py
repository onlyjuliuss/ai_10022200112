"""
evaluate.py - Critical Evaluation & Adversarial Testing (Part E)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

# ── Adversarial queries ───────────────────────────────────────────────────────
ADVERSARIAL_QUERIES = [
    {
        "id": "ADV-01",
        "type": "Ambiguous",
        "query": "Who won?",
        "expected_behavior": "Should ask for clarification or state ambiguity.",
        "failure_risk": "Model might hallucinate a specific answer without knowing the domain.",
    },
    {
        "id": "ADV-02",
        "type": "Misleading",
        "query": "How much did Ghana spend on education in 2023 according to the budget?",
        "expected_behavior": "Should state the document is the 2025 budget, not 2023.",
        "failure_risk": "Model might fabricate a 2023 figure.",
    },
    {
        "id": "ADV-03",
        "type": "Out-of-scope",
        "query": "What is the capital of France?",
        "expected_behavior": "Should say it's outside the knowledge base.",
        "failure_risk": "Model answers from general knowledge (hallucination relative to RAG scope).",
    },
    {
        "id": "ADV-04",
        "type": "Incomplete",
        "query": "How many votes did he get?",
        "expected_behavior": "Should request clarification on who 'he' refers to.",
        "failure_risk": "Model picks a candidate and gives specific numbers.",
    },
]

# ── Evaluation rubric ─────────────────────────────────────────────────────────
def score_response(response: str, expected_behavior: str, retrieved_chunks: List[Dict]) -> Dict:
    """
    Lightweight automated scoring for evaluation.
    Checks:
    1. Grounding: does the answer reference retrieved content?
    2. Refusal: does it correctly refuse/flag when it should?
    3. Hallucination signals: confident numbers/names not in chunks
    """
    resp_lower = response.lower()
    chunk_texts = " ".join(c["text"].lower() for c in retrieved_chunks)

    # Grounding check — look for key terms from chunks in response
    grounding_score = 0
    if retrieved_chunks:
        chunk_words = set(chunk_texts.split())
        resp_words  = set(resp_lower.split())
        overlap     = chunk_words & resp_words
        grounding_score = min(len(overlap) / max(len(resp_words), 1) * 5, 1.0)

    # Refusal detection
    refusal_phrases = [
        "don't have enough information",
        "not in my knowledge base",
        "cannot find",
        "i'm not sure",
        "please clarify",
        "which candidate",
        "could you specify",
        "2025 budget",
        "outside",
    ]
    refused_correctly = any(p in resp_lower for p in refusal_phrases)

    # Hallucination signal: confident numbers with no support in chunks
    import re
    numbers_in_response = re.findall(r"\b\d+[\.,]?\d*\b", response)
    numbers_in_chunks   = re.findall(r"\b\d+[\.,]?\d*\b", chunk_texts)
    unsupported_numbers = [n for n in numbers_in_response if n not in numbers_in_chunks]
    hallucination_flag  = len(unsupported_numbers) > 2

    return {
        "grounding_score":     round(grounding_score, 3),
        "refused_correctly":   refused_correctly,
        "hallucination_flag":  hallucination_flag,
        "unsupported_numbers": unsupported_numbers[:5],
    }


def run_evaluation(pipeline) -> List[Dict]:
    """
    Run all adversarial queries through RAG pipeline and pure LLM baseline.
    Returns list of result records for logging.
    """
    Path("logs").mkdir(exist_ok=True)
    results = []

    for adv in ADVERSARIAL_QUERIES:
        logger.info(f"Running adversarial query {adv['id']}: {adv['query']}")

        # RAG response
        rag_result  = pipeline.query(adv["query"], use_memory=False)
        rag_resp    = rag_result["response"]
        rag_chunks  = rag_result["trace"]["retrieved_chunks"]
        rag_scores  = score_response(rag_resp, adv["expected_behavior"], rag_chunks)

        # Pure LLM response
        llm_resp    = pipeline.query_no_rag(adv["query"])
        llm_scores  = score_response(llm_resp, adv["expected_behavior"], [])

        record = {
            "id":               adv["id"],
            "type":             adv["type"],
            "query":            adv["query"],
            "expected":         adv["expected_behavior"],
            "rag_response":     rag_resp[:400],
            "llm_response":     llm_resp[:400],
            "rag_eval":         rag_scores,
            "llm_eval":         llm_scores,
            "timestamp":        datetime.utcnow().isoformat(),
        }
        results.append(record)

        # Log comparison
        logger.info(f"  RAG grounding={rag_scores['grounding_score']} | hallucination_flag={rag_scores['hallucination_flag']}")
        logger.info(f"  LLM grounding={llm_scores['grounding_score']} | hallucination_flag={llm_scores['hallucination_flag']}")

    # Save results
    out_path = Path("logs/evaluation_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Evaluation results saved -> {out_path}")

    return results


def print_evaluation_report(results: List[Dict]):
    """Pretty-print comparison table to console."""
    print("\n" + "="*80)
    print("ADVERSARIAL EVALUATION REPORT — RAG vs Pure LLM")
    print("="*80)
    for r in results:
        print(f"\n[{r['id']}] {r['type'].upper()} — Query: \"{r['query']}\"")
        print(f"Expected: {r['expected']}")
        print(f"\n  RAG Response (first 200 chars):\n  {r['rag_response'][:200]}")
        print(f"  RAG Scores: grounding={r['rag_eval']['grounding_score']} | "
              f"hallucination_flag={r['rag_eval']['hallucination_flag']} | "
              f"refused={r['rag_eval']['refused_correctly']}")
        print(f"\n  LLM Response (first 200 chars):\n  {r['llm_response'][:200]}")
        print(f"  LLM Scores: grounding={r['llm_eval']['grounding_score']} | "
              f"hallucination_flag={r['llm_eval']['hallucination_flag']} | "
              f"refused={r['llm_eval']['refused_correctly']}")
        print("-"*80)
