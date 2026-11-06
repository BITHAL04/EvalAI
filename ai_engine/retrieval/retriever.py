"""LlamaIndex retriever over the document_chunks table.

The search function is injected by the application and always applies the tenant filter, so a
caller cannot obtain cross-institution text by forgetting a filter here.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from ai_engine.providers.base import AIProvider
from ai_engine.schemas import RetrievedChunk

SearchFn = Callable[[list[float], int], list[RetrievedChunk]]
MIN_SCORE = 0.35


@dataclass
class RetrievalReport:
    chunks: list[RetrievedChunk]
    queries: int
    weak: bool
    note: str = ""


class AcademicRetriever(BaseRetriever):
    def __init__(self, provider: AIProvider, search: SearchFn, top_k: int = 8):
        super().__init__()
        self._provider, self._search, self._top_k = provider, search, top_k

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        vector = self._provider.embed([query_bundle.query_str], task="query")[0]
        return [
            NodeWithScore(node=TextNode(id_=c.chunk_id, text=c.text, metadata=c.model_dump(exclude={"text"})), score=c.score)
            for c in self._search(vector, self._top_k)
        ]


def retrieve_many(retriever: AcademicRetriever, queries: list[str], limit: int = 30) -> RetrievalReport:
    """Run several queries, dedupe, and report whether the material actually covers them."""
    best: dict[str, RetrievedChunk] = {}
    weak_queries = []
    for q in queries:
        hits = retriever.retrieve(q)
        if not hits or max(h.score or 0 for h in hits) < MIN_SCORE:
            weak_queries.append(q)
        for h in hits:
            m = h.node.metadata
            if (h.score or 0) >= MIN_SCORE and (h.node.node_id not in best or (h.score or 0) > (best[h.node.node_id].score or 0)):
                best[h.node.node_id] = RetrievedChunk(**m, text=h.node.get_content()) if "text" not in m else RetrievedChunk(**m)
    chunks = sorted(best.values(), key=lambda c: c.score or 0, reverse=True)[:limit]
    note = f"Weak coverage for: {', '.join(weak_queries)}" if weak_queries else ""
    return RetrievalReport(chunks=chunks, queries=len(queries), weak=bool(weak_queries), note=note)
