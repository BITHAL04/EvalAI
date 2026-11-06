"""Sentence-aware chunking through LlamaIndex, keeping exact page provenance."""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from itertools import groupby

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter

from ai_engine.ingestion.parsers import PageText


@dataclass
class Chunk:
    index: int
    text: str
    page_start: int | None
    page_end: int | None
    chapter: str | None


def chunk_pages(pages: list[PageText], chunk_size: int = 512, overlap: int = 64) -> list[Chunk]:
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    chunks: list[Chunk] = []
    for chapter, group in groupby(pages, key=lambda p: p.chapter):
        text, offsets, numbers = "", [], []
        for p in group:
            if not p.text.strip():
                continue
            offsets.append(len(text)); numbers.append(p.page)
            text += p.text.rstrip() + "\n\n"
        if not text.strip():
            continue
        for node in splitter.get_nodes_from_documents([Document(text=text)]):
            body = node.get_content().strip()
            if len(body) < 20:
                continue
            start = node.start_char_idx if node.start_char_idx is not None else 0
            end = node.end_char_idx if node.end_char_idx is not None else start + len(body)
            chunks.append(Chunk(len(chunks), body, numbers[bisect_right(offsets, start) - 1],
                                numbers[bisect_right(offsets, max(start, end - 1)) - 1], chapter))
    return chunks
