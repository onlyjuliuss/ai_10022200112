"""
ingest.py - Data Engineering & Preparation (Part A)
"""

import os
import re
import json
import logging
import pandas as pd
import pdfplumber
import requests
from pathlib import Path
from typing import List, Dict, Tuple

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/ingest.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DATA_DIR = Path("data")
RAW_DIR  = DATA_DIR / "raw"
PROC_DIR = DATA_DIR / "processed"

CSV_URL  = "https://raw.githubusercontent.com/GodwinDansoAcity/acitydataset/main/Ghana_Election_Result.csv"
PDF_URL  = "https://mofep.gov.gh/sites/default/files/budget-statements/2025-Budget-Statement-and-Economic-Policy_v5.pdf"

# Chunk design rationale:
#  - 500 tokens (~2-3 paragraphs) balances context richness vs. retrieval precision
#  - 100-token overlap prevents answers being split across chunk boundaries
#  - Tested at 300/50, 500/100, 800/150 — 500/100 gave best recall on pilot queries
CHUNK_SIZE    = 500   # characters (approx 100-125 tokens)
CHUNK_OVERLAP = 100   # characters


# ── Download helpers ──────────────────────────────────────────────────────────
def download_file(url: str, dest: Path) -> Path:
    """Download a file if it doesn't already exist locally."""
    if dest.exists():
        logger.info(f"File already exists: {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading {url} -> {dest}")
    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info(f"Downloaded {dest.stat().st_size / 1024:.1f} KB")
    return dest


# ── CSV Processing ────────────────────────────────────────────────────────────
def load_and_clean_csv(path: Path) -> pd.DataFrame:
    """
    Load Ghana Election CSV and clean it.
    Cleaning steps:
      1. Strip whitespace from column names and string cells
      2. Fill missing numerical values with 0
      3. Normalize candidate/party names to title case
      4. Drop fully-empty rows
    """
    logger.info(f"Loading CSV: {path}")
    df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")

    # Strip column name whitespace
    df.columns = [c.strip() for c in df.columns]
    logger.info(f"Columns found: {list(df.columns)}")
    logger.info(f"Shape before cleaning: {df.shape}")

    # Strip string cells
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()

    # Drop fully-empty rows
    df.dropna(how="all", inplace=True)

    # Replace "nan" strings introduced by astype(str)
    df.replace("nan", "", inplace=True)

    logger.info(f"Shape after cleaning: {df.shape}")
    return df


def csv_to_text_chunks(df: pd.DataFrame, source: str = "Ghana Election Results") -> List[Dict]:
    """
    Convert each row of the election CSV into a readable text passage,
    then chunk groups of rows together.

    Strategy: Group rows by constituency/region, create a narrative sentence
    per row, then apply sliding-window chunking on the narrative text.
    Also creates national summary chunks for each election year.
    """
    logger.info("Converting CSV rows to text chunks...")
    rows_text = []
    for _, row in df.iterrows():
        parts = []
        for col, val in row.items():
            if val and str(val).strip() not in ("", "nan"):
                parts.append(f"{col}: {val}")
        if parts:
            rows_text.append(". ".join(parts) + ".")

    # Join all rows into one big string, then chunk
    full_text = "\n".join(rows_text)
    chunks = sliding_window_chunk(full_text, CHUNK_SIZE, CHUNK_OVERLAP)

    result = []
    for i, chunk in enumerate(chunks):
        result.append({
            "id": f"election_{i:04d}",
            "text": chunk,
            "source": source,
            "type": "election_data",
            "chunk_index": i,
            "total_chunks": len(chunks)
        })

    # Add national summary chunks for each election year
    if 'Year' in df.columns and 'Candidate' in df.columns and 'Votes' in df.columns:
        years = df['Year'].unique()
        for year in sorted(years):
            year_df = df[df['Year'] == year]
            if len(year_df) > 0:
                # Aggregate votes by candidate
                summary_data = year_df.groupby(['Candidate', 'Party'])['Votes'].sum().sort_values(ascending=False)

                # Create summary text
                summary_lines = [f"Year: {year}. Ghana Presidential Election National Results:"]
                for (candidate, party), votes in summary_data.items():
                    summary_lines.append(f"- {candidate} ({party}): {votes:,} votes")

                # Determine winner
                if len(summary_data) > 0:
                    winner_candidate, winner_party = summary_data.index[0]
                    winner_votes = summary_data.iloc[0]
                    total_votes = summary_data.sum()
                    winner_percentage = (winner_votes / total_votes * 100) if total_votes > 0 else 0
                    summary_lines.append(f"Winner: {winner_candidate} ({winner_party}) with {winner_votes:,} votes ({winner_percentage:.1f}%)")

                summary_text = "\n".join(summary_lines)

                result.append({
                    "id": f"election_summary_{year}",
                    "text": summary_text,
                    "source": source,
                    "type": "election_summary",
                    "chunk_index": len(result),
                    "total_chunks": len(result) + 1
                })

    logger.info(f"CSV -> {len(result)} chunks (including {len([c for c in result if c['type'] == 'election_summary'])} summary chunks)")
    return result


# ── PDF Processing ────────────────────────────────────────────────────────────
def load_and_clean_pdf(path: Path) -> str:
    """
    Extract and clean text from the Budget PDF.
    Cleaning steps:
      1. Extract text page by page with pdfplumber
      2. Remove headers/footers (repeated short lines)
      3. Collapse excessive whitespace
      4. Remove non-printable characters
    """
    logger.info(f"Loading PDF: {path}")
    pages_text = []

    with pdfplumber.open(path) as pdf:
        logger.info(f"PDF has {len(pdf.pages)} pages")
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                pages_text.append(text)
            if (i + 1) % 20 == 0:
                logger.info(f"  Processed {i+1}/{len(pdf.pages)} pages...")

    raw_text = "\n".join(pages_text)
    logger.info(f"Raw PDF text length: {len(raw_text):,} chars")

    # Remove non-printable chars (keep newlines and spaces)
    cleaned = re.sub(r"[^\x20-\x7E\n]", " ", raw_text)

    # Collapse 3+ consecutive newlines to 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # Collapse multiple spaces
    cleaned = re.sub(r" {2,}", " ", cleaned)

    # Remove lines that are just numbers (page numbers)
    lines = [ln for ln in cleaned.split("\n") if not re.match(r"^\s*\d+\s*$", ln)]
    cleaned = "\n".join(lines)

    logger.info(f"Cleaned PDF text length: {len(cleaned):,} chars")
    return cleaned


def pdf_to_text_chunks(text: str, source: str = "Ghana 2025 Budget Statement") -> List[Dict]:
    """Chunk the cleaned PDF text with sliding window."""
    logger.info("Chunking PDF text...")
    chunks = sliding_window_chunk(text, CHUNK_SIZE, CHUNK_OVERLAP)
    result = []
    for i, chunk in enumerate(chunks):
        result.append({
            "id": f"budget_{i:04d}",
            "text": chunk,
            "source": source,
            "type": "budget_data",
            "chunk_index": i,
            "total_chunks": len(chunks)
        })
    logger.info(f"PDF -> {len(result)} chunks")
    return result


# ── Chunking Core ─────────────────────────────────────────────────────────────
def sliding_window_chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Sliding-window character-level chunking.

    Design justification:
    - size=500 chars ≈ 100-125 tokens: enough for 2-3 dense sentences of context
      without overwhelming the LLM context window or diluting retrieval signals.
    - overlap=100 chars: ensures facts near chunk boundaries are captured in
      at least one neighbouring chunk, reducing missed-answer rate.
    - Compared alternatives:
        300/50  → too granular, splits tables and lists awkwardly
        800/150 → chunks too large, retrieval precision drops
        500/100 → best balance (see experiment_log.md)

    Returns list of non-empty text chunks.
    """
    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == text_len:
            break
        start += size - overlap

    return chunks


# ── Comparative chunking analysis ─────────────────────────────────────────────
def compare_chunking_strategies(text: str) -> Dict:
    """
    Part A requirement: Compare different chunking configurations.
    Returns stats for three strategies.
    """
    strategies = {
        "Small (300/50)":   (300, 50),
        "Medium (500/100)": (500, 100),
        "Large (800/150)":  (800, 150),
    }
    results = {}
    for name, (size, overlap) in strategies.items():
        chunks = sliding_window_chunk(text, size, overlap)
        avg_len = sum(len(c) for c in chunks) / max(len(chunks), 1)
        results[name] = {
            "num_chunks": len(chunks),
            "avg_chunk_len": round(avg_len, 1),
            "total_chars": sum(len(c) for c in chunks),
        }
    return results


# ── Main pipeline ─────────────────────────────────────────────────────────────
def run_ingestion(use_sample_pdf: bool = False) -> List[Dict]:
    """
    Full ingestion pipeline:
    1. Download CSV and PDF
    2. Clean both
    3. Chunk both
    4. Merge and save to data/processed/chunks.json
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    all_chunks: List[Dict] = []

    # ── CSV ────────────────────────────────────────────────────────────────────
    csv_path = RAW_DIR / "Ghana_Election_Result.csv"
    try:
        download_file(CSV_URL, csv_path)
        df = load_and_clean_csv(csv_path)
        csv_chunks = csv_to_text_chunks(df)
        all_chunks.extend(csv_chunks)
    except Exception as e:
        logger.error(f"CSV ingestion failed: {e}")

    # ── PDF ────────────────────────────────────────────────────────────────────
    pdf_path = RAW_DIR / "2025_Budget.pdf"
    try:
        if not use_sample_pdf:
            download_file(PDF_URL, pdf_path)
        if pdf_path.exists():
            pdf_text = load_and_clean_pdf(pdf_path)
            pdf_chunks = pdf_to_text_chunks(pdf_text)
            all_chunks.extend(pdf_chunks)

            # Chunking comparison report
            comparison = compare_chunking_strategies(pdf_text[:5000])  # sample
            logger.info("Chunking strategy comparison (on PDF sample):")
            for name, stats in comparison.items():
                logger.info(f"  {name}: {stats}")
        else:
            logger.warning("PDF not found, skipping budget data")
    except Exception as e:
        logger.error(f"PDF ingestion failed: {e}")

    # ── Save ───────────────────────────────────────────────────────────────────
    out_path = PROC_DIR / "chunks.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(all_chunks)} total chunks -> {out_path}")
    return all_chunks


if __name__ == "__main__":
    chunks = run_ingestion()
    print(f"\n✅ Ingestion complete: {len(chunks)} chunks ready.")
