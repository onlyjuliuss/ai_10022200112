import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.pipeline import RAGPipeline

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY is not set. Set it in .env or environment variables.")

app = FastAPI(
    title="Ghana Election RAG API",
    description="Backend API for the Ghana election and budget chatbot.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"]
)

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    response: str
    trace: dict

pipeline = None

@app.on_event("startup")
def startup_event():
    global pipeline
    if not GROQ_API_KEY:
        raise RuntimeError("Missing GROQ_API_KEY environment variable.")

    logger.info("Starting server and loading RAG pipeline...")
    pipeline = RAGPipeline(api_key=GROQ_API_KEY, rebuild_index=False)
    logger.info("RAG pipeline loaded successfully.")


@app.get("/health")
def health_check():
    return {"status": "ok", "pipeline_ready": pipeline is not None}

@app.post("/api/query", response_model=QueryResponse)
def query_chat(request: QueryRequest):
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if pipeline is None:
        raise HTTPException(status_code=503, detail="RAG pipeline is not ready yet.")

    result = pipeline.query(request.query.strip(), use_memory=True)
    return {"response": result["response"], "trace": result["trace"]}

frontend_dir = Path(__file__).resolve().parent / "frontend" / "dist"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
