"""End-to-end through FastAPI with the memory store and the hash embedder. No GCP needed."""

import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.pipeline import caller_id_for, company_id_for
from app.signature import sign

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SECRET = "wsec_test"


def _payload(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def _settings(**overrides) -> Settings:
    base = dict(
        store_backend="memory",
        demo_mode=True,
        elevenlabs_webhook_secret=SECRET,
        memory_seed_file=SAMPLES / "solutions.json",
        frontend_origin="http://localhost:5173",
        api_key="",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture()
def client():
    return TestClient(create_app(_settings()))


def _post_webhook(client, payload: dict, secret: str = SECRET):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "ElevenLabs-Signature": sign(body, secret, int(time.time()))}
    return client.post("/webhooks/elevenlabs", content=body, headers=headers)


def test_ids_normalise_legal_forms_and_case():
    assert company_id_for("Bakkerij Verhulst BV") == company_id_for("bakkerij verhulst") == "bakkerij-verhulst"
    assert company_id_for("Drukkerij De Vos NV") == "drukkerij-de-vos"
    assert caller_id_for("Sofie Janssens", "bakkerij-verhulst") == "sofie-janssens--bakkerij-verhulst"
    assert company_id_for(None) is None and caller_id_for("", "x") is None


def test_webhook_stores_call_with_suggestions(client):
    r = _post_webhook(client, _payload("call_vakantiegeld.json"))
    assert r.status_code == 200, r.text
    ack = r.json()
    assert ack == {"call_id": "conv_demo_vakantiegeld_001", "created": True, "suggestions": 5, "ignored": None}

    call = client.get("/calls/conv_demo_vakantiegeld_001").json()
    assert call["caller_id"] == "sofie-janssens--bakkerij-verhulst"
    assert call["company_id"] == "bakkerij-verhulst"
    assert call["category"] == "vakantiegeld" and call["urgency"] == "hoog"
    assert "problem_embedding" not in call
    scores = [s["score"] for s in call["suggestions"]]
    assert scores == sorted(scores, reverse=True) and all(0 <= s <= 100 for s in scores)
    assert call["best_score"] == scores[0]
    assert call["suggestions"][0]["solution_id"].startswith("vakantiegeld")

    details = client.get("/calls/conv_demo_vakantiegeld_001/suggestions").json()
    assert len(details) == 5 and details[0]["solution_text"]


def test_webhook_is_idempotent(client):
    payload = _payload("call_vakantiegeld.json")
    assert _post_webhook(client, payload).json()["created"] is True
    assert _post_webhook(client, payload).json()["created"] is False
    company = client.get("/companies/bakkerij-verhulst").json()
    assert company["company"]["call_count"] == 1


def test_webhook_rejects_bad_signature(client):
    assert _post_webhook(client, _payload("call_vakantiegeld.json"), secret="wrong").status_code == 401
    r = client.post("/webhooks/elevenlabs", json=_payload("call_vakantiegeld.json"))
    assert r.status_code == 401


def test_webhook_without_secret_is_unavailable():
    c = TestClient(create_app(_settings(elevenlabs_webhook_secret="")))
    assert _post_webhook(c, _payload("call_vakantiegeld.json")).status_code == 503


def test_webhook_ignores_audio_events(client):
    r = _post_webhook(client, {"type": "post_call_audio", "data": {"conversation_id": "x", "full_audio": "AAAA"}})
    assert r.status_code == 200 and r.json()["ignored"] == "post_call_audio"
    assert client.get("/calls/latest").status_code == 404


def test_webhook_missing_fields_do_not_crash(client):
    payload = _payload("call_vakantiegeld.json")
    payload["data"]["analysis"]["data_collection_results"] = {"problem": {"value": None}}
    payload["data"]["analysis"]["transcript_summary"] = None
    r = _post_webhook(client, payload)
    assert r.status_code == 200 and r.json()["suggestions"] == 0
    call = client.get("/calls/latest").json()
    assert call["caller_id"] is None and call["category"] == "overig" and call["suggestions_status"] == "no_problem"


def test_webhook_invalid_conversation_id(client):
    payload = _payload("call_vakantiegeld.json")
    payload["data"]["conversation_id"] = "../../etc"
    assert _post_webhook(client, payload).status_code == 400


def test_history_across_callers_of_same_company(client):
    _post_webhook(client, _payload("call_vakantiegeld.json"))
    _post_webhook(client, _payload("call_zelfde_bedrijf.json"))
    company = client.get("/companies/bakkerij-verhulst").json()
    assert company["company"]["call_count"] == 2 and company["company"]["open_issues"] == 2
    assert [c["call_id"] for c in company["calls"]] == ["conv_demo_maaltijdcheques_002", "conv_demo_vakantiegeld_001"]
    assert "transcript" not in company["calls"][0]
    caller = client.get("/callers/tom-peeters--bakkerij-verhulst").json()
    assert caller["caller"]["call_count"] == 1 and len(caller["calls"]) == 1
    assert client.get("/calls/latest").json()["call_id"] == "conv_demo_maaltijdcheques_002"


def test_resolve_updates_solution_and_company(client):
    _post_webhook(client, _payload("call_vakantiegeld.json"))
    call_id = "conv_demo_vakantiegeld_001"
    top = client.get(f"/calls/{call_id}/suggestions").json()[0]

    r = client.post(f"/calls/{call_id}/resolve", json={"solution_id": top["solution_id"], "worked": True})
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    after = client.get(f"/calls/{call_id}/suggestions").json()[0]
    assert after["times_used"] == top["times_used"] + 1
    assert after["times_successful"] == top["times_successful"] + 1
    assert client.get("/companies/bakkerij-verhulst").json()["company"]["open_issues"] == 0

    again = client.post(f"/calls/{call_id}/resolve", json={"solution_id": top["solution_id"], "worked": True})
    assert again.status_code == 409


def test_resolve_unknown_solution_and_call(client):
    _post_webhook(client, _payload("call_vakantiegeld.json"))
    unknown_solution = {"solution_id": "nope", "worked": True}
    assert client.post("/calls/conv_demo_vakantiegeld_001/resolve", json=unknown_solution).status_code == 404
    assert client.post("/calls/unknown/resolve", json={"solution_id": "dimona-laattijdig", "worked": True}).status_code == 404
    bad = client.post("/calls/conv_demo_vakantiegeld_001/resolve", json={"solution_id": "a/b", "worked": True})
    assert bad.status_code == 422


def test_simulate_call_creates_fresh_calls(client):
    payload = _payload("call_vakantiegeld.json")
    first = client.post("/demo/simulate-call", json=copy.deepcopy(payload)).json()
    second = client.post("/demo/simulate-call", json=copy.deepcopy(payload)).json()
    assert first["created"] and second["created"] and first["call_id"] != second["call_id"]
    assert first["call_id"].startswith("demo-")
    caller = client.get("/callers/sofie-janssens--bakkerij-verhulst").json()
    assert caller["caller"]["call_count"] == 2


def test_simulate_call_disabled_without_demo_mode():
    c = TestClient(create_app(_settings(demo_mode=False)))
    assert c.post("/demo/simulate-call", json=_payload("call_vakantiegeld.json")).status_code == 404


def test_api_key_enforced_when_configured():
    c = TestClient(create_app(_settings(api_key="k123")))
    assert c.get("/calls/latest").status_code == 401
    assert c.get("/calls/latest", headers={"X-API-Key": "k123"}).status_code == 404  # authorised, just empty
    assert c.get("/healthz").status_code == 200
    # the webhook is authenticated by its signature, not by the API key
    assert _post_webhook(c, _payload("call_vakantiegeld.json")).status_code == 200


def test_cors_only_allows_configured_origin(client):
    ok = client.options("/calls/latest", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/calls/latest", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_unknown_entities_return_404(client):
    assert client.get("/calls/nope").status_code == 404
    assert client.get("/callers/nope").status_code == 404
    assert client.get("/companies/nope").status_code == 404


def test_escalate_flag_follows_threshold():
    strict = TestClient(create_app(_settings(escalation_threshold=101)))
    _post_webhook(strict, _payload("call_vakantiegeld.json"))
    assert strict.get("/calls/latest").json()["escalate"] is True

    lenient = TestClient(create_app(_settings(escalation_threshold=0)))
    _post_webhook(lenient, _payload("call_vakantiegeld.json"))
    call = lenient.get("/calls/latest").json()
    assert call["escalate"] is False and call["best_score"] is not None


def test_call_without_problem_escalates(client):
    payload = _payload("call_vakantiegeld.json")
    payload["data"]["analysis"]["data_collection_results"] = {}
    payload["data"]["analysis"]["transcript_summary"] = None
    _post_webhook(client, payload)
    assert client.get("/calls/latest").json()["escalate"] is True


def test_load_calls_uses_live_ids_and_resolutions():
    from app.embeddings import HashEmbedder
    from app.pipeline import load_calls
    from app.store import MemoryStore

    store, embedder = MemoryStore(), HashEmbedder()
    from app.pipeline import load_solutions

    load_solutions(store, embedder, json.loads((SAMPLES / "solutions.json").read_text(encoding="utf-8")))
    before = store.solutions["vakantiegeld-uitdienst-bediende"]["times_used"]
    old = _payload("call_vakantiegeld.json")
    old["data"]["conversation_id"] = "seed_001"
    old["resolution"] = {"solution_id": "vakantiegeld-uitdienst-bediende", "worked": True, "resolved_at": "2026-06-01T10:00:00Z"}
    broken = _payload("call_zelfde_bedrijf.json")
    broken["resolution"] = {"solution_id": "bestaat-niet", "worked": True}

    stats = load_calls(store, embedder, [old, broken, copy.deepcopy(old)])
    assert stats == {"created": 2, "skipped": 1, "resolved": 1}
    assert "sofie-janssens--bakkerij-verhulst" in store.callers  # same id as a live call
    assert store.calls["seed_001"]["status"] == "resolved"
    assert store.solutions["vakantiegeld-uitdienst-bediende"]["times_used"] == before + 1
    assert store.companies["bakkerij-verhulst"]["open_issues"] == 1
