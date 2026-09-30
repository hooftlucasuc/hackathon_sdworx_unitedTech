"""POST /webhooks/elevenlabs — ElevenLabs post-call webhook, HMAC-verified, idempotent on conversation_id."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.deps import get_embedder, get_settings, get_store
from app.models import WebhookAck
from app.pipeline import PayloadError, process_call
from app.signature import SignatureError, verify

log = logging.getLogger(__name__)
router = APIRouter(tags=["webhook"])

HANDLED_TYPE = "post_call_transcription"


@router.post("/webhooks/elevenlabs", response_model=WebhookAck)
async def elevenlabs_webhook(request: Request, settings: Settings = Depends(get_settings)) -> WebhookAck:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.webhook_max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "payload too large")
    body = await request.body()
    if len(body) > settings.webhook_max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "payload too large")

    if not settings.elevenlabs_webhook_secret:
        log.error("ELEVENLABS_WEBHOOK_SECRET is not configured; rejecting webhook")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "webhook not configured")
    try:
        verify(
            request.headers.get("elevenlabs-signature"),
            body,
            settings.elevenlabs_webhook_secret,
            settings.webhook_tolerance_secs,
        )
    except SignatureError as exc:
        log.warning("rejected webhook: %s", exc.reason)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid signature") from exc

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body is not valid JSON") from exc

    event_type = payload.get("type") if isinstance(payload, dict) else None
    if event_type != HANDLED_TYPE:
        # post_call_audio and others: acknowledged, never stored (we keep no audio)
        log.info("ignored webhook of type %s", event_type)
        return WebhookAck(ignored=str(event_type))

    store = get_store(request)
    embedder = get_embedder(request)
    try:
        result = await run_in_threadpool(
            process_call, store, embedder, payload, None, settings.escalation_threshold
        )
    except PayloadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return WebhookAck(**result)
