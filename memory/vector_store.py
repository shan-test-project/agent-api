import asyncio
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from config import CHROMA_DIR

logger = logging.getLogger(__name__)

_chroma_client = None
_collections = {}


def _get_client():
    global _chroma_client
    if _chroma_client is None:
        try:
            import chromadb
            _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        except ImportError:
            logger.warning("chromadb not installed — vector memory disabled")
    return _chroma_client


def _get_collection(user_id: int):
    key = f"user_{user_id}"
    if key not in _collections:
        client = _get_client()
        if client:
            try:
                _collections[key] = client.get_or_create_collection(
                    name=key,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as e:
                logger.error(f"Collection error: {e}")
                return None
    return _collections.get(key)


class VectorMemory:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.fallback: list[dict] = []

    async def add(self, content: str, memory_type: str = "general",
                  importance: int = 5, tags: list[str] = None) -> bool:
        coll = _get_collection(self.user_id)
        if not coll:
            self.fallback.append({
                "content": content, "type": memory_type,
                "importance": importance, "tags": tags or [],
                "timestamp": datetime.utcnow().isoformat(),
            })
            return True

        try:
            import uuid
            doc_id = str(uuid.uuid4())
            metadata = {
                "type": memory_type,
                "importance": importance,
                "tags": json.dumps(tags or []),
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": str(self.user_id),
            }
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: coll.add(
                    documents=[content],
                    metadatas=[metadata],
                    ids=[doc_id],
                )
            )
            return True
        except Exception as e:
            logger.error(f"Memory add error: {e}")
            self.fallback.append({"content": content, "type": memory_type})
            return False

    async def search(self, query: str, n_results: int = 5, memory_type: str = None) -> list[dict]:
        coll = _get_collection(self.user_id)
        if not coll:
            return [m for m in self.fallback[-20:] if query.lower() in m["content"].lower()][:n_results]

        try:
            where = {"type": memory_type} if memory_type else None
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: coll.query(
                    query_texts=[query],
                    n_results=min(n_results, max(1, coll.count())),
                    where=where,
                )
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            return [
                {
                    "content": doc,
                    "metadata": meta,
                    "relevance": round(1 - dist, 3),
                }
                for doc, meta, dist in zip(docs, metas, distances)
                if 1 - dist > 0.3
            ]
        except Exception as e:
            logger.error(f"Memory search error: {e}")
            return []

    async def get_recent(self, limit: int = 10) -> list[dict]:
        coll = _get_collection(self.user_id)
        if not coll:
            return self.fallback[-limit:]
        try:
            count = coll.count()
            if count == 0:
                return []
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: coll.get(limit=min(limit, count), include=["documents", "metadatas"]),
            )
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])
            pairs = list(zip(docs, metas))
            pairs.sort(key=lambda x: x[1].get("timestamp", ""), reverse=True)
            return [{"content": d, "metadata": m} for d, m in pairs[:limit]]
        except Exception as e:
            logger.error(f"Memory recent error: {e}")
            return []

    async def clear(self) -> bool:
        key = f"user_{self.user_id}"
        client = _get_client()
        if client:
            try:
                client.delete_collection(key)
                _collections.pop(key, None)
            except Exception:
                pass
        self.fallback.clear()
        return True

    async def get_context_for_prompt(self, query: str) -> str:
        memories = await self.search(query, n_results=5)
        if not memories:
            return ""
        lines = ["[Relevant memories from past interactions:]"]
        for m in memories:
            rel = m.get("relevance", "?")
            lines.append(f"- {m['content']} (relevance: {rel})")
        return "\n".join(lines)


_memory_instances: dict[int, VectorMemory] = {}


def memory_store(user_id: int) -> VectorMemory:
    if user_id not in _memory_instances:
        _memory_instances[user_id] = VectorMemory(user_id)
    return _memory_instances[user_id]
