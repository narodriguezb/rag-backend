import warnings

warnings.filterwarnings("ignore", message="resource_tracker: There appear to be.*")

import hashlib
import os
import random
import time
from typing import List, Optional

from config import config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from rag_system import RAGSystem

# Initialize FastAPI app
app = FastAPI(title="Course Materials RAG System", root_path="")

# Add trusted host middleware for proxy
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# Enable CORS with proper settings for proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Initialize RAG system
rag_system = RAGSystem(config)

# Pydantic models for request/response
class SourceItem(BaseModel):
    """Model for individual source with optional link"""
    text: str
    link: Optional[str] = None

class QueryRequest(BaseModel):
    """Request model for course queries"""
    query: str
    session_id: Optional[str] = None

class QueryResponse(BaseModel):
    """Response model for course queries"""
    answer: str
    sources: List[SourceItem]
    session_id: str

class CourseStats(BaseModel):
    """Response model for course statistics"""
    total_courses: int
    course_titles: List[str]

# API Endpoints

@app.post("/api/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """Process a query and return response with sources"""
    try:
        # Create session if not provided
        session_id = request.session_id
        if not session_id:
            session_id = rag_system.session_manager.create_session()
        
        # Process query using RAG system
        answer, sources = rag_system.query(request.query, session_id)

        # Convert sources to SourceItem objects
        formatted_sources = []
        for source in sources:
            if isinstance(source, dict) and 'text' in source:
                # New format with text and optional link
                formatted_sources.append(SourceItem(
                    text=source['text'],
                    link=source.get('link')
                ))
            else:
                # Fallback for old string format
                formatted_sources.append(SourceItem(
                    text=str(source),
                    link=None
                ))

        return QueryResponse(
            answer=answer,
            sources=formatted_sources,
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/courses", response_model=CourseStats)
async def get_course_stats():
    """Get course analytics and statistics"""
    try:
        analytics = rag_system.get_course_analytics()
        return CourseStats(
            total_courses=analytics["total_courses"],
            course_titles=analytics["course_titles"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/load")
def synthetic_load(rows: int = 800, iterations: int = 120, ms: int = 0, fail: int = 0):
    if not config.ENABLE_LOAD_ENDPOINT:
        raise HTTPException(status_code=404, detail="Not Found")

    rows = max(1, min(rows, 5000))
    iterations = max(1, min(iterations, 2000))
    ms = max(0, min(ms, 15000))
    fail = max(0, min(fail, 100))

    if fail and random.random() * 100 < fail:
        raise HTTPException(status_code=500, detail="Synthetic failure")

    start = time.perf_counter()
    data = [{"id": i, "value": random.random(), "label": f"item-{i}"} for i in range(rows)]

    checksum = 0
    sample = min(64, rows)
    for _ in range(iterations):
        data.sort(key=lambda row: row["value"])
        digest = hashlib.sha256(repr(data[:sample]).encode()).hexdigest()
        checksum ^= int(digest[:8], 16)

    if ms:
        time.sleep(ms / 1000)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "rows": rows,
        "iterations": iterations,
        "delay_ms": ms,
        "checksum": checksum,
        "elapsed_ms": elapsed_ms,
    }

@app.on_event("startup")
async def startup_event():
    """Load initial documents on startup"""
    build_version = os.getenv("BUILD_VERSION", "local")
    print(f"=== rag-backend startup OK | build={build_version} ===", flush=True)
    print("CI/CD demo: flujo completo (lint, tests, mutation, scans, deploy) OK", flush=True)
    docs_path = "../docs"
    if os.path.exists(docs_path):
        print("Loading initial documents...")
        try:
            courses, chunks = rag_system.add_course_folder(docs_path, clear_existing=False)
            print(f"Loaded {courses} courses with {chunks} chunks")
        except Exception as e:
            print(f"Error loading documents: {e}")


@app.get("/")
async def root():
    return {"status": "ok", "service": "Course Materials RAG System API"}