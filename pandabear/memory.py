"""Organizational memory — embedded ChromaDB. Channel posts, decisions, and notes
land here; a capability queries it. Embeddings are Chroma's default local MiniLM —
nothing leaves the box to remember or recall."""

import time
import uuid

import chromadb

from .config import settings

_client: chromadb.ClientAPI | None = None


def _collection():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    return _client.get_or_create_collection("team_notes")


def add_note(text: str, source: str, author: str = "") -> str:
    note_id = uuid.uuid4().hex[:12]
    _collection().add(
        ids=[note_id],
        documents=[text],
        metadatas=[{"source": source, "author": author, "ts": int(time.time())}],
    )
    return note_id


def search_notes(query: str, top_k: int = 5) -> list[dict]:
    col = _collection()
    if col.count() == 0:
        return []
    res = col.query(query_texts=[query], n_results=min(top_k, col.count()))
    return [
        {"text": doc, "source": meta.get("source"), "author": meta.get("author")}
        for doc, meta in zip(res["documents"][0], res["metadatas"][0])
    ]
