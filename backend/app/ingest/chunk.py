"""Token-based chunking: 800 tokens per chunk, 100 overlap. Falls back to whitespace tokens offline."""

from __future__ import annotations

import logging
import re
from typing import Callable

log = logging.getLogger(__name__)

MAX_TOKENS = 800
OVERLAP = 100

_encode: Callable[[str], list] = lambda s: s.split()  # noqa: E731
_decode: Callable[[list], str] = lambda toks: " ".join(toks)  # noqa: E731
_TOKENIZER = "whitespace"

try:  # tiktoken needs a one-time download of the encoding; not always possible offline
    import tiktoken

    _enc = tiktoken.get_encoding("cl100k_base")
    _encode = _enc.encode
    _decode = _enc.decode
    _TOKENIZER = "cl100k_base"
except Exception as exc:  # noqa: BLE001
    log.warning("tiktoken unavailable (%s); chunking on whitespace tokens", exc)


def split(text: str, max_tokens: int = MAX_TOKENS, overlap: int = OVERLAP) -> list[str]:
    """Split on paragraph boundaries first, then hard-cut anything longer than max_tokens with overlap."""
    if overlap >= max_tokens:
        raise ValueError("overlap must be smaller than max_tokens")
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        plen = len(_encode(para))
        if plen > max_tokens:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            chunks.extend(_hard_split(para, max_tokens, overlap))
            continue
        if current_len + plen > max_tokens and current:
            chunks.append("\n\n".join(current))
            # keep the tail of the previous chunk as overlap
            tail = _decode(_encode("\n\n".join(current))[-overlap:]) if overlap else ""
            current = [tail, para] if tail else [para]
            current_len = len(_encode("\n\n".join(current)))
        else:
            current.append(para)
            current_len += plen
    if current:
        chunks.append("\n\n".join(current))
    return [c for c in chunks if c.strip()]


def _hard_split(text: str, max_tokens: int, overlap: int) -> list[str]:
    toks = _encode(text)
    out: list[str] = []
    start = 0
    while start < len(toks):
        out.append(_decode(toks[start : start + max_tokens]))
        if start + max_tokens >= len(toks):
            break
        start += max_tokens - overlap
    return out


def tokenizer_name() -> str:
    return _TOKENIZER
