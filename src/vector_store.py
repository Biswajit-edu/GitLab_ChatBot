import logging
import os
from pathlib import Path

import google.generativeai as genai
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)

INDEX_PATH = Path("data/faiss_index")
MAX_CHUNK_CHARS = 1500


class GeminiEmbeddings(Embeddings):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-embedding-2-preview:embedContent"
        )

    def _embed(self, text: str, task_type: str) -> list[float]:
        import requests
        import time
        
        for attempt in range(5): 
            response = requests.post(
                self.url,
                params={"key": self.api_key},
                json={
                    "model": "models/gemini-embedding-2-preview",
                    "content": {"parts": [{"text": text}]},
                    "taskType": task_type,
                },
            )
            if response.status_code == 429:
                wait = 2 ** attempt * 15 
                logger.warning(f"Rate limited. Waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()["embedding"]["values"]
        
        raise Exception("Embedding failed after 5 retries due to rate limiting.")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import time
        result = []
        for i, text in enumerate(texts):
            result.append(self._embed(text, "RETRIEVAL_DOCUMENT"))
            time.sleep(2)  
            if i % 10 == 0:
                logger.info(f"Embedded {i}/{len(texts)} documents...")
        return result

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text, "RETRIEVAL_QUERY")

def _build_documents(pages: list[dict]) -> list[Document]:
    docs: list[Document] = []
    for page in pages:
        for chunk in page.get("chunks", []):
            text = chunk.get("text", "").strip()
            if len(text) < 500:
                continue
            if len(text) > MAX_CHUNK_CHARS:
                text = text[:MAX_CHUNK_CHARS]
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "url": page["url"],
                        "title": page["title"],
                        "section": chunk.get("section", ""),
                        "source_type": page.get("source_type", "handbook"),
                    },
                )
            )
    logger.info("Built %d documents.", len(docs))
    return docs


def build_index(pages: list[dict], force: bool = False) -> FAISS:
    embeddings = GeminiEmbeddings(api_key=os.environ["GOOGLE_API_KEY"])

    if INDEX_PATH.exists() and not force:
        logger.info("Loading existing FAISS index from %s", INDEX_PATH)
        return FAISS.load_local(
            str(INDEX_PATH),
            embeddings,
            allow_dangerous_deserialization=True,
        )

    logger.info("Building FAISS index from scratch...")
    docs = _build_documents(pages)

    if not docs:
        raise ValueError("No documents to index.")

    vectorstore = FAISS.from_documents(docs, embeddings)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(INDEX_PATH))
    logger.info("FAISS index saved (%d vectors)", len(docs))
    return vectorstore


def get_retriever(vectorstore: FAISS, k: int = 6):
    return vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": k, "fetch_k": 20},
    )