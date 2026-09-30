"""In-memory repository with the same interface as FirestoreRepo. Tests and offline frontend dev only."""

from __future__ import annotations

import math
from typing import Any, Optional

from app.core.models import Chunk, KnowledgeItem, Question, User


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return 1.0 - dot / (na * nb)


class MemoryRepo:
    def __init__(self) -> None:
        self.countries: dict[str, dict[str, Any]] = {}
        self.users: dict[str, User] = {}
        self.items: dict[str, KnowledgeItem] = {}
        self.chunks: dict[str, Chunk] = {}
        self.questions: dict[str, Question] = {}

    # countries
    def write_country(self, profile: dict[str, Any]) -> None:
        self.countries[profile["code"]] = profile

    # users
    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def find_user_by_username(self, username: str) -> Optional[User]:
        return next((u for u in self.users.values() if u.username == username), None)

    def upsert_user(self, user: User) -> None:
        self.users[user.user_id] = user

    def list_experts(self, country: str) -> list[User]:
        return [u for u in self.users.values() if u.role == "expert" and u.country == country]

    # items
    def get_item(self, item_id: str) -> Optional[KnowledgeItem]:
        return self.items.get(item_id)

    def get_items(self, item_ids: list[str]) -> dict[str, KnowledgeItem]:
        return {i: self.items[i] for i in item_ids if i in self.items}

    def list_items(self, countries: list[str]) -> list[KnowledgeItem]:
        out = [it for it in self.items.values() if it.country in countries]
        out.sort(key=lambda it: (it.updated_at.isoformat() if it.updated_at else ""), reverse=True)
        return out

    def upsert_item(self, item: KnowledgeItem) -> None:
        self.items[item.item_id] = item

    def set_item_status(self, item_id: str, status: str, superseded_by_id: Optional[str] = None) -> bool:
        item = self.items.get(item_id)
        if item is None:
            return False
        item.status = status
        if superseded_by_id is not None:
            item.superseded_by_id = superseded_by_id
        for ch in self.chunks.values():
            if ch.item_id == item_id:
                ch.status = status
        return True

    def delete_country_items(self, country: str) -> int:
        item_ids = [i for i, it in self.items.items() if it.country == country]
        chunk_ids = [c for c, ch in self.chunks.items() if ch.country == country]
        for i in item_ids:
            del self.items[i]
        for c in chunk_ids:
            del self.chunks[c]
        return len(item_ids) + len(chunk_ids)

    # chunks
    def replace_chunks(self, item_id: str, chunks: list[Chunk]) -> None:
        for c in [c for c, ch in self.chunks.items() if ch.item_id == item_id]:
            del self.chunks[c]
        for ch in chunks:
            self.chunks[ch.chunk_id] = ch

    def get_chunks(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        return {c: self.chunks[c] for c in chunk_ids if c in self.chunks}

    def search_chunks(self, query_vec: list[float], country: str, k: int = 8) -> list[dict[str, Any]]:
        hits = []
        for ch in self.chunks.values():
            if ch.country in (country, "ALL") and ch.status == "active":
                d = ch.to_doc()
                d["distance"] = _cosine_distance(query_vec, ch.embedding)
                hits.append(d)
        hits.sort(key=lambda h: h["distance"])
        return hits[:k]

    # questions
    def upsert_question(self, q: Question) -> None:
        self.questions[q.question_id] = q

    def get_question(self, question_id: str) -> Optional[Question]:
        return self.questions.get(question_id)

    def list_questions_by_user(self, user_id: str, limit: int = 50) -> list[Question]:
        qs = [q for q in self.questions.values() if q.asked_by == user_id]
        qs.sort(key=lambda q: q.created_at, reverse=True)
        return qs[:limit]

    def list_inbox(self, expert_id: str, limit: int = 50) -> list[Question]:
        qs = [q for q in self.questions.values() if q.assigned_expert_id == expert_id and q.status == "escalated"]
        qs.sort(key=lambda q: q.created_at, reverse=True)
        return qs[:limit]


def make_repo(settings):
    if settings.store_backend == "memory":
        return MemoryRepo()
    from app.store.firestore_repo import FirestoreRepo

    return FirestoreRepo(settings.gcp_project)
