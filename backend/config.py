import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class Config:
    """Configuration settings for the RAG system"""
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    VERTEX_PROJECT_ID: str = os.getenv("VERTEX_PROJECT_ID", "rag-proyect-499005")
    VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "us-central1")
    
    # Embedding model settings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    
    # Document processing settings
    CHUNK_SIZE: int = 800       # Size of text chunks for vector storage
    CHUNK_OVERLAP: int = 100     # Characters to overlap between chunks
    MAX_RESULTS: int = 5         # Maximum search results to return
    MAX_HISTORY: int = 2         # Number of conversation messages to remember
    
    # Database paths
    CHROMA_PATH: str = "./chroma_db"  # ChromaDB storage location

    ENABLE_LOAD_ENDPOINT: bool = os.getenv("ENABLE_LOAD_ENDPOINT", "").lower() in ("1", "true", "yes")

config = Config()


