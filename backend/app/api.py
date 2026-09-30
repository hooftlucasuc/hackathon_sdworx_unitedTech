"""Dashboard API (CONTEXT.md, 'API'). The dashboard may also read Firestore directly; writes go through here."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.deps import get_embedder, get_settings, get_store, require_api_key
from app.models import (
    ID_PATTERN,
    Call,
    CallerDetail,
    CompanyDetail,
    ResolveRequest,
    ResolveResult,
    SuggestionDetail,
    WebhookAck,
)
from app.pipeline import PayloadError, process_call
from app.store import Conflict, NotFound

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])

ENTITY_PATTERN = r"^[A-Za-z0-9_\-]{1,200}$"


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


@router.get("/calls/latest", response_model=Call, tags=["calls"])
def latest_call(store=Depends(get_store)) -> dict[str, Any]:
    call = store.latest_call()
    if call is None:
        raise _not_found("call")
    return call


@router.get("/calls/{call_id}", response_model=Call, tags=["calls"])
def get_call(call_id: str = Path(..., pattern=ID_PATTERN), store=Depends(get_store)) -> dict[str, Any]:
    call = store.get_call(call_id)
    if call is None:
        raise _not_found("call")
    return call


@router.get("/calls/{call_id}/suggestions", response_model=list[SuggestionDetail], tags=["calls"])
def get_suggestions(call_id: str = Path(..., pattern=ID_PATTERN), store=Depends(get_store)) -> list[dict[str, Any]]:
    call = store.get_call(call_id)
    if call is None:
        raise _not_found("call")
    suggestions = call.get("suggestions") or []
    details = store.get_solutions([s["solution_id"] for s in suggestions])
    out = []
    for s in suggestions:
        sol = details.get(s["solution_id"], {})
        out.append({**sol, **s})  # the stored score and reasons win over live solution fields
    return out


@router.post("/calls/{call_id}/resolve", response_model=ResolveResult, tags=["calls"])
def resolve_call(body: ResolveRequest, call_id: str = Path(..., pattern=ID_PATTERN), store=Depends(get_store)) -> dict[str, Any]:
    try:
        result = store.resolve_call(call_id, body.solution_id, body.worked, datetime.now(timezone.utc))
    except NotFound as exc:
        raise _not_found(str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    log.info("call %s resolved with %s worked=%s", call_id, body.solution_id, body.worked)
    return result


@router.get("/callers/{caller_id}", response_model=CallerDetail, tags=["history"])
def get_caller(caller_id: str = Path(..., pattern=ENTITY_PATTERN), store=Depends(get_store)) -> dict[str, Any]:
    caller = store.get_caller(caller_id)
    if caller is None:
        raise _not_found("caller")
    return {"caller": caller, "calls": store.calls_for("caller_id", caller_id)}


@router.get("/companies/{company_id}", response_model=CompanyDetail, tags=["history"])
def get_company(company_id: str = Path(..., pattern=ENTITY_PATTERN), store=Depends(get_store)) -> dict[str, Any]:
    company = store.get_company(company_id)
    if company is None:
        raise _not_found("company")
    return {"company": company, "calls": store.calls_for("company_id", company_id)}


@router.post("/demo/simulate-call", response_model=WebhookAck, tags=["demo"])
async def simulate_call(
    request: Request,
    payload: dict[str, Any] = Body(...),
    keep_id: bool = Query(False, description="true = keep conversation_id and start time from the payload"),
    settings: Settings = Depends(get_settings),
) -> WebhookAck:
    """Same body as the ElevenLabs webhook, without signature. Only with DEMO_MODE=true.

    By default every click gets a fresh conversation_id and start time, so the same sample
    payload produces a new call each time (and the caller/company history grows).
    """
    if not settings.demo_mode:
        raise _not_found("route")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "payload has no 'data' object")
    if not keep_id:
        data["conversation_id"] = f"demo-{uuid.uuid4().hex[:12]}"
        # no start time -> the pipeline uses the exact receive time, so rapid clicks never tie
        (data.get("metadata") or {}).pop("start_time_unix_secs", None)
    store = get_store(request)
    embedder = get_embedder(request)
    try:
        result = await run_in_threadpool(
            process_call, store, embedder, payload, None, settings.escalation_threshold
        )
    except PayloadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return WebhookAck(**result)
