"""
pipeline.py - Full RAG Pipeline (Part D)
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from src.embedder import Embedder
from src.retriever import VectorStore, BM25Index, HybridRetriever, build_index
from src.prompt import build_prompt
from src.ingest import run_ingestion

logger = logging.getLogger(__name__)
Path("logs").mkdir(exist_ok=True)
fh = logging.FileHandler("logs/pipeline.log")
fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.addHandler(fh)
logger.setLevel(logging.INFO)


def make_trace() -> Dict:
    return {
        "query": "", "expanded_query": "", "retrieved_chunks": [],
        "selected_chunks": [], "system_prompt": "", "user_prompt": "",
        "llm_response": "", "latency_ms": {}, "low_confidence": False,
        "timestamp": datetime.utcnow().isoformat(),
    }


class RAGPipeline:
    def __init__(self, api_key=None, prompt_variant="A", top_k=10, rebuild_index=False):
        self.api_key        = api_key or os.environ.get("GROQ_API_KEY", "")
        self.prompt_variant = prompt_variant
        self.top_k          = top_k
        self.conversation_history: List[Dict] = []
        self._ready = False
        self._setup(rebuild_index)

    def _setup(self, rebuild: bool):
        logger.info("=== RAG Pipeline Setup ===")
        self.llm = Groq(api_key=self.api_key)
        self.embedder = Embedder()

        index_path  = Path("data/processed/faiss.index")
        chunks_path = Path("data/processed/chunks.json")

        if rebuild or not index_path.exists() or not chunks_path.exists():
            chunks = run_ingestion()
            self.vector_store, self.bm25_index = build_index(chunks, self.embedder)
        else:
            self.vector_store = VectorStore.load(index_path, chunks_path)
            with open(chunks_path) as f:
                chunks = json.load(f)
            self.bm25_index = BM25Index()
            self.bm25_index.build(chunks)

        self.retriever = HybridRetriever(self.vector_store, self.bm25_index, self.embedder)
        self._ready    = True
        logger.info(f"Pipeline ready. {self.vector_store.index.ntotal} vectors indexed.")

    def _call_llm(self, system: str, user: str) -> str:
        response = self.llm.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens=1000,
            temperature=0.2,
        )
        return response.choices[0].message.content

    def query(self, user_query: str, use_memory=True, prompt_variant=None) -> Dict:
        if not self._ready:
            raise RuntimeError("Pipeline not initialised.")

        variant = prompt_variant or self.prompt_variant
        trace   = make_trace()
        trace["query"] = user_query
        t0 = time.time()

        # Stage 1: Retrieve
        retrieved = self.retriever.retrieve(user_query, k=self.top_k)
        trace["retrieved_chunks"] = retrieved
        trace["expanded_query"]   = self.retriever.expand_query(user_query)
        trace["low_confidence"]   = self.retriever.detect_low_confidence(retrieved)
        trace["latency_ms"]["retrieval"] = round((time.time() - t0) * 1000)

        # Stage 2: Build prompt
        sys_prompt, user_prompt, selected = build_prompt(user_query, retrieved, variant=variant)
        trace["system_prompt"]   = sys_prompt
        trace["user_prompt"]     = user_prompt
        trace["selected_chunks"] = selected

        # Stage 3: Memory (Part G)
        if use_memory and self.conversation_history:
            lines = []
            for m in self.conversation_history[-4:]:
                role = "User" if m["role"] == "user" else "Assistant"
                lines.append(f"{role}: {m['content'][:200]}")
            user_prompt = "\n[Previous conversation]\n" + "\n".join(lines) + "\n\n" + user_prompt

        # Stage 4: LLM
        t4 = time.time()
        try:
            llm_answer = self._call_llm(sys_prompt, user_prompt)
        except Exception as e:
            llm_answer = f"Groq API error: {str(e)}"

        trace["llm_response"]        = llm_answer
        trace["latency_ms"]["llm"]   = round((time.time() - t4) * 1000)
        trace["latency_ms"]["total"] = round((time.time() - t0) * 1000)

        # Stage 5: Update memory
        if use_memory:
            self.conversation_history.append({"role": "user",      "content": user_query})
            self.conversation_history.append({"role": "assistant",  "content": llm_answer})
            self.conversation_history = self.conversation_history[-20:]

        self._save_trace(trace)
        prefix = "⚠️ Low confidence — answer may not be fully grounded.\n\n" if trace["low_confidence"] else ""
        return {"response": prefix + llm_answer, "trace": trace}

    def _save_trace(self, trace: Dict):
        with open("logs/traces.jsonl", "a") as f:
            c = dict(trace)
            c["user_prompt"] = trace["user_prompt"][:300] + "..."
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    def clear_memory(self):
        self.conversation_history = []

    def query_no_rag(self, user_query: str) -> str:
        try:
            return self._call_llm(
                "You are a helpful assistant. Answer from general knowledge.",
                user_query
            )
        except Exception as e:
            return f"Error: {e}"

    def run_prompt_experiment(self, query: str) -> Dict:
        return {v: self.query(query, use_memory=False, prompt_variant=v)["response"] for v in ["A","B","C"]}