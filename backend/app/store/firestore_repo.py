"""Firestore (Native mode) repository. Collections: countries, users, knowledge_items, chunks, questions."""

from __future__ import annotations

import logging
from typing import Any, Optional

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.vector import Vector

from app.core.models import Chunk, KnowledgeItem, Question, User

log = logging.getLogger(__name__)

BATCH = 400  # Firestore write batch limit is 500
IN_LIMIT = 30  # `in` filter limit


def _chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


class FirestoreRepo:
    def __init__(self, project: str):
        self.db = firestore.Client(project=project or None)

    # ---------- countries ----------

    def write_country(self, profile: dict[str, Any]) -> None:
        self.db.collection("countries").document(profile["code"]).set(profile)

    # ---------- users ----------

    def get_user(self, user_id: str) -> Optional[User]:
        snap = self.db.collection("users").document(user_id).get()
        return User.from_doc(snap.to_dict()) if snap.exists else None

    def find_user_by_username(self, username: str) -> Optional[User]:
        q = self.db.collection("users").where(filter=FieldFilter("username", "==", username)).limit(1)
        for snap in q.stream():
            return User.from_doc(snap.to_dict())
        return None

    def upsert_user(self, user: User) -> None:
        self.db.collection("users").document(user.user_id).set(user.to_doc())

    def list_experts(self, country: str) -> list[User]:
        q = (
            self.db.collection("users")
            .where(filter=FieldFilter("role", "==", "expert"))
            .where(filter=FieldFilter("country", "==", country))
        )
        return [User.from_doc(s.to_dict()) for s in q.stream()]

    # ---------- knowledge items ----------

    def get_item(self, item_id: str) -> Optional[KnowledgeItem]:
        snap = self.db.collection("knowledge_items").document(item_id).get()
        return KnowledgeItem.from_doc(snap.to_dict()) if snap.exists else None

    def get_items(self, item_ids: list[str]) -> dict[str, KnowledgeItem]:
        out: dict[str, KnowledgeItem] = {}
        ids = list(dict.fromkeys(item_ids))
        for group in _chunked(ids, IN_LIMIT):
            q = self.db.collection("knowledge_items").where(filter=FieldFilter("item_id", "in", group))
            for snap in q.stream():
                item = KnowledgeItem.from_doc(snap.to_dict())
                out[item.item_id] = item
        return out

    def list_items(self, countries: list[str]) -> list[KnowledgeItem]:
        q = self.db.collection("knowledge_items").where(filter=FieldFilter("country", "in", countries[:IN_LIMIT]))
        items = [KnowledgeItem.from_doc(s.to_dict()) for s in q.stream()]
        items.sort(key=lambda it: (it.updated_at.isoformat() if it.updated_at else ""), reverse=True)
        return items

    def upsert_item(self, item: KnowledgeItem) -> None:
        self.db.collection("knowledge_items").document(item.item_id).set(item.to_doc())

    def set_item_status(self, item_id: str, status: str, superseded_by_id: Optional[str] = None) -> bool:
        ref = self.db.collection("knowledge_items").document(item_id)
        if not ref.get().exists:
            return False
        update: dict[str, Any] = {"status": status}
        if superseded_by_id is not None:
            update["superseded_by_id"] = superseded_by_id
        ref.update(update)
        # chunks duplicate status for the vector pre-filter
        chunks = self.db.collection("chunks").where(filter=FieldFilter("item_id", "==", item_id)).stream()
        batch = self.db.batch()
        n = 0
        for snap in chunks:
            batch.update(snap.reference, {"status": status})
            n += 1
            if n % BATCH == 0:
                batch.commit()
                batch = self.db.batch()
        batch.commit()
        return True

    def delete_country_items(self, country: str) -> int:
        n = 0
        for coll in ("chunks", "knowledge_items"):
            q = self.db.collection(coll).where(filter=FieldFilter("country", "==", country))
            batch = self.db.batch()
            k = 0
            for snap in q.stream():
                batch.delete(snap.reference)
                k += 1
                n += 1
                if k % BATCH == 0:
                    batch.commit()
                    batch = self.db.batch()
            batch.commit()
        log.info("deleted %d documents for country %s", n, country)
        return n

    # ---------- chunks ----------

    def replace_chunks(self, item_id: str, chunks: list[Chunk]) -> None:
        old = self.db.collection("chunks").where(filter=FieldFilter("item_id", "==", item_id)).stream()
        batch = self.db.batch()
        k = 0
        for snap in old:
            batch.delete(snap.reference)
            k += 1
            if k % BATCH == 0:
                batch.commit()
                batch = self.db.batch()
        batch.commit()
        for group in _chunked(chunks, BATCH):
            batch = self.db.batch()
            for ch in group:
                doc = ch.to_doc()
                doc["embedding"] = Vector(ch.embedding)
                batch.set(self.db.collection("chunks").document(ch.chunk_id), doc)
            batch.commit()

    def get_chunks(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        out: dict[str, Chunk] = {}
        refs = [self.db.collection("chunks").document(c) for c in dict.fromkeys(chunk_ids)]
        for snap in self.db.get_all(refs):
            if snap.exists:
                d = snap.to_dict()
                d.pop("embedding", None)
                out[snap.id] = Chunk.from_doc(d | {"chunk_id": snap.id})
        return out

    # ---------- questions ----------

    def upsert_question(self, q: Question) -> None:
        self.db.collection("questions").document(q.question_id).set(q.to_doc())

    def get_question(self, question_id: str) -> Optional[Question]:
        snap = self.db.collection("questions").document(question_id).get()
        return Question.from_doc(snap.to_dict()) if snap.exists else None

    def list_questions_by_user(self, user_id: str, limit: int = 50) -> list[Question]:
        q = (
            self.db.collection("questions")
            .where(filter=FieldFilter("asked_by", "==", user_id))
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [Question.from_doc(s.to_dict()) for s in q.stream()]

    def list_inbox(self, expert_id: str, limit: int = 50) -> list[Question]:
        q = (
            self.db.collection("questions")
            .where(filter=FieldFilter("assigned_expert_id", "==", expert_id))
            .where(filter=FieldFilter("status", "==", "escalated"))
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [Question.from_doc(s.to_dict()) for s in q.stream()]
