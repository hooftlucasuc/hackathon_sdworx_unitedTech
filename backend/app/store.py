"""All persistence. FirestoreStore is the only place that talks to Firestore; MemoryStore mirrors it for tests.

Collections (CONTEXT.md): callers, companies, calls, solutions. Timestamps are stored as Firestore
timestamps so the dashboard can orderBy('started_at') with onSnapshot.
"""

from __future__ import annotations

import copy
import logging
import math
from datetime import datetime
from typing import Any, Optional

log = logging.getLogger(__name__)

EMBEDDING_FIELD = "problem_embedding"
HISTORY_LIMIT = 200


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def _clean(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Drop the embedding: large, and useless to the dashboard."""
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop(EMBEDDING_FIELD, None)
    return doc


def _summary(doc: dict[str, Any]) -> dict[str, Any]:
    doc = _clean(doc) or {}
    doc.pop("transcript", None)
    doc.pop("suggestions", None)
    return doc


def _new_company(company: dict[str, Any], ts: datetime) -> dict[str, Any]:
    return {
        "company_id": company["company_id"],
        "name": company.get("name"),
        "sector": None,
        "size": None,
        "first_seen": ts,
        "last_seen": ts,
        "call_count": 1,
        "open_issues": 1,
    }


def _new_caller(caller: dict[str, Any], ts: datetime) -> dict[str, Any]:
    return {
        "caller_id": caller["caller_id"],
        "name": caller.get("name"),
        "company_id": caller.get("company_id"),
        "first_seen": ts,
        "last_seen": ts,
        "call_count": 1,
    }


def _later(a: Optional[datetime], b: datetime) -> datetime:
    return b if a is None or b > a else a


# --------------------------------------------------------------------------------------------------
# Firestore
# --------------------------------------------------------------------------------------------------


class FirestoreStore:
    def __init__(self, project: str, database: str = "(default)"):
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
        from google.cloud.firestore_v1.vector import Vector

        self._fs = firestore
        self._FieldFilter = FieldFilter
        self._Distance = DistanceMeasure
        self._Vector = Vector
        self.db = firestore.Client(project=project or None, database=database)

    # ---- calls ----

    def get_call(self, call_id: str) -> Optional[dict[str, Any]]:
        snap = self.db.collection("calls").document(call_id).get()
        return _clean(snap.to_dict()) if snap.exists else None

    def get_call_embedding(self, call_id: str) -> Optional[list[float]]:
        snap = self.db.collection("calls").document(call_id).get()
        if not snap.exists:
            return None
        vec = (snap.to_dict() or {}).get(EMBEDDING_FIELD)
        return list(vec) if vec is not None else None

    def create_call(
        self,
        call: dict[str, Any],
        company: Optional[dict[str, Any]],
        caller: Optional[dict[str, Any]],
    ) -> bool:
        """Write call + upsert company/caller in one transaction. False if the call already existed."""
        fs = self._fs
        call_ref = self.db.collection("calls").document(call["call_id"])
        comp_ref = self.db.collection("companies").document(company["company_id"]) if company else None
        caller_ref = self.db.collection("callers").document(caller["caller_id"]) if caller else None
        ts: datetime = call["started_at"]

        doc = dict(call)
        if doc.get(EMBEDDING_FIELD) is not None:
            doc[EMBEDDING_FIELD] = self._Vector(doc[EMBEDDING_FIELD])
        else:
            doc.pop(EMBEDDING_FIELD, None)

        @fs.transactional
        def _txn(transaction) -> bool:
            if call_ref.get(transaction=transaction).exists:
                return False
            comp_snap = comp_ref.get(transaction=transaction) if comp_ref else None
            caller_snap = caller_ref.get(transaction=transaction) if caller_ref else None

            if comp_ref is not None:
                if comp_snap.exists:
                    prev = comp_snap.to_dict() or {}
                    transaction.update(
                        comp_ref,
                        {
                            "last_seen": _later(prev.get("last_seen"), ts),
                            "call_count": fs.Increment(1),
                            "open_issues": fs.Increment(1),
                        },
                    )
                else:
                    transaction.set(comp_ref, _new_company(company, ts))
            if caller_ref is not None:
                if caller_snap.exists:
                    prev = caller_snap.to_dict() or {}
                    transaction.update(
                        caller_ref,
                        {"last_seen": _later(prev.get("last_seen"), ts), "call_count": fs.Increment(1)},
                    )
                else:
                    transaction.set(caller_ref, _new_caller(caller, ts))
            transaction.set(call_ref, doc)
            return True

        return _txn(self.db.transaction())

    def latest_call(self) -> Optional[dict[str, Any]]:
        q = self.db.collection("calls").order_by("started_at", direction=self._fs.Query.DESCENDING).limit(1)
        for snap in q.stream():
            return _clean(snap.to_dict())
        return None

    def calls_for(self, field: str, value: str, limit: int = HISTORY_LIMIT) -> list[dict[str, Any]]:
        """Newest first. Sorted in Python so no composite index is needed for the API."""
        q = self.db.collection("calls").where(filter=self._FieldFilter(field, "==", value)).limit(limit)
        docs = [_summary(s.to_dict()) for s in q.stream()]
        docs.sort(key=lambda d: d["started_at"], reverse=True)
        return docs

    def update_suggestions(self, call_id: str, suggestions: list[dict[str, Any]], status: str, escalate: bool) -> None:
        self.db.collection("calls").document(call_id).update(
            {
                "suggestions": suggestions,
                "suggestions_status": status,
                "best_score": suggestions[0]["score"] if suggestions else None,
                "escalate": escalate,
            }
        )

    # ---- callers / companies ----

    def get_caller(self, caller_id: str) -> Optional[dict[str, Any]]:
        snap = self.db.collection("callers").document(caller_id).get()
        return snap.to_dict() if snap.exists else None

    def get_company(self, company_id: str) -> Optional[dict[str, Any]]:
        snap = self.db.collection("companies").document(company_id).get()
        return snap.to_dict() if snap.exists else None

    # ---- solutions ----

    def nearest_solutions(self, vector: list[float], limit: int) -> list[tuple[dict[str, Any], float]]:
        q = self.db.collection("solutions").find_nearest(
            vector_field=EMBEDDING_FIELD,
            query_vector=self._Vector(vector),
            distance_measure=self._Distance.COSINE,
            limit=limit,
            distance_result_field="vector_distance",
        )
        out = []
        for snap in q.get():
            doc = _clean(snap.to_dict()) or {}
            distance = float(doc.pop("vector_distance", 1.0))
            doc["solution_id"] = snap.id
            out.append((doc, distance))
        return out

    def get_solutions(self, solution_ids: list[str]) -> dict[str, dict[str, Any]]:
        refs = [self.db.collection("solutions").document(i) for i in dict.fromkeys(solution_ids)]
        out: dict[str, dict[str, Any]] = {}
        for snap in self.db.get_all(refs):
            if snap.exists:
                out[snap.id] = (_clean(snap.to_dict()) or {}) | {"solution_id": snap.id}
        return out

    def upsert_solution(self, solution: dict[str, Any]) -> None:
        doc = dict(solution)
        doc[EMBEDDING_FIELD] = self._Vector(doc[EMBEDDING_FIELD])
        self.db.collection("solutions").document(doc["solution_id"]).set(doc)

    def delete_all_solutions(self) -> int:
        n = 0
        batch = self.db.batch()
        for snap in self.db.collection("solutions").stream():
            batch.delete(snap.reference)
            n += 1
            if n % 400 == 0:
                batch.commit()
                batch = self.db.batch()
        batch.commit()
        return n

    def count_solutions(self) -> int:
        result = self.db.collection("solutions").count().get()
        return int(result[0][0].value)

    # ---- resolve ----

    def resolve_call(self, call_id: str, solution_id: str, worked: bool, now: datetime) -> dict[str, Any]:
        fs = self._fs
        call_ref = self.db.collection("calls").document(call_id)
        sol_ref = self.db.collection("solutions").document(solution_id)

        @fs.transactional
        def _txn(transaction) -> dict[str, Any]:
            call_snap = call_ref.get(transaction=transaction)
            if not call_snap.exists:
                raise NotFound("call")
            call = call_snap.to_dict() or {}
            if call.get("status") == "resolved":
                raise Conflict("call already resolved")
            if not sol_ref.get(transaction=transaction).exists:
                raise NotFound("solution")
            transaction.update(
                sol_ref,
                {
                    "times_used": fs.Increment(1),
                    "times_successful": fs.Increment(1 if worked else 0),
                    "last_used_at": now,
                },
            )
            transaction.update(
                call_ref,
                {
                    "status": "resolved",
                    "chosen_solution_id": solution_id,
                    "solution_worked": worked,
                    "resolved_at": now,
                },
            )
            if call.get("company_id"):
                comp_ref = self.db.collection("companies").document(call["company_id"])
                transaction.update(comp_ref, {"open_issues": fs.Increment(-1)})
            return {"call_id": call_id, "status": "resolved", "chosen_solution_id": solution_id, "solution_worked": worked}

        return _txn(self.db.transaction())


# --------------------------------------------------------------------------------------------------
# Memory (tests and local dev without GCP)
# --------------------------------------------------------------------------------------------------


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return 1.0 - dot / (na * nb)


class MemoryStore:
    def __init__(self) -> None:
        self.calls: dict[str, dict[str, Any]] = {}
        self.callers: dict[str, dict[str, Any]] = {}
        self.companies: dict[str, dict[str, Any]] = {}
        self.solutions: dict[str, dict[str, Any]] = {}

    def get_call(self, call_id: str) -> Optional[dict[str, Any]]:
        return _clean(copy.deepcopy(self.calls.get(call_id)))

    def get_call_embedding(self, call_id: str) -> Optional[list[float]]:
        call = self.calls.get(call_id)
        return list(call[EMBEDDING_FIELD]) if call and call.get(EMBEDDING_FIELD) else None

    def create_call(self, call, company, caller) -> bool:
        if call["call_id"] in self.calls:
            return False
        ts = call["started_at"]
        if company:
            prev = self.companies.get(company["company_id"])
            if prev:
                prev["last_seen"] = _later(prev.get("last_seen"), ts)
                prev["call_count"] += 1
                prev["open_issues"] += 1
            else:
                self.companies[company["company_id"]] = _new_company(company, ts)
        if caller:
            prev = self.callers.get(caller["caller_id"])
            if prev:
                prev["last_seen"] = _later(prev.get("last_seen"), ts)
                prev["call_count"] += 1
            else:
                self.callers[caller["caller_id"]] = _new_caller(caller, ts)
        self.calls[call["call_id"]] = copy.deepcopy(call)
        return True

    def latest_call(self) -> Optional[dict[str, Any]]:
        if not self.calls:
            return None
        newest = max(self.calls.values(), key=lambda c: (c["started_at"], c.get("received_at") or c["started_at"]))
        return self.get_call(newest["call_id"])

    def calls_for(self, field: str, value: str, limit: int = HISTORY_LIMIT) -> list[dict[str, Any]]:
        docs = [_summary(copy.deepcopy(c)) for c in self.calls.values() if c.get(field) == value]
        docs.sort(key=lambda d: d["started_at"], reverse=True)
        return docs[:limit]

    def update_suggestions(self, call_id: str, suggestions: list[dict[str, Any]], status: str, escalate: bool) -> None:
        call = self.calls[call_id]
        call["suggestions"] = copy.deepcopy(suggestions)
        call["suggestions_status"] = status
        call["best_score"] = suggestions[0]["score"] if suggestions else None
        call["escalate"] = escalate

    def get_caller(self, caller_id: str) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self.callers.get(caller_id))

    def get_company(self, company_id: str) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self.companies.get(company_id))

    def nearest_solutions(self, vector: list[float], limit: int) -> list[tuple[dict[str, Any], float]]:
        hits = [(_clean(copy.deepcopy(s)), _cosine_distance(vector, s[EMBEDDING_FIELD])) for s in self.solutions.values()]
        hits.sort(key=lambda h: h[1])
        return hits[:limit]

    def get_solutions(self, solution_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {i: _clean(copy.deepcopy(self.solutions[i])) for i in solution_ids if i in self.solutions}

    def upsert_solution(self, solution: dict[str, Any]) -> None:
        self.solutions[solution["solution_id"]] = copy.deepcopy(solution)

    def delete_all_solutions(self) -> int:
        n = len(self.solutions)
        self.solutions.clear()
        return n

    def count_solutions(self) -> int:
        return len(self.solutions)

    def resolve_call(self, call_id: str, solution_id: str, worked: bool, now: datetime) -> dict[str, Any]:
        call = self.calls.get(call_id)
        if call is None:
            raise NotFound("call")
        if call.get("status") == "resolved":
            raise Conflict("call already resolved")
        sol = self.solutions.get(solution_id)
        if sol is None:
            raise NotFound("solution")
        sol["times_used"] = sol.get("times_used", 0) + 1
        sol["times_successful"] = sol.get("times_successful", 0) + (1 if worked else 0)
        sol["last_used_at"] = now
        call.update({"status": "resolved", "chosen_solution_id": solution_id, "solution_worked": worked, "resolved_at": now})
        if call.get("company_id") in self.companies:
            self.companies[call["company_id"]]["open_issues"] -= 1
        return {"call_id": call_id, "status": "resolved", "chosen_solution_id": solution_id, "solution_worked": worked}


def make_store(settings):
    if settings.store_backend == "memory":
        return MemoryStore()
    from app.embeddings import resolve_project

    return FirestoreStore(resolve_project(settings.gcp_project), settings.firestore_database)
