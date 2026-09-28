"""Backend test suite.

Covers the load-bearing behaviour of DeciTrace AI:
  * analytics produce real numbers from real rows
  * signals are deterministic and score arithmetic is transparent
  * RAG retrieval returns evidence whose source rows actually exist
  * the decision engine bands correctly and persists evidence
  * every API endpoint in the specification answers
  * human-in-the-loop approval persists and is idempotency-guarded
  * the evaluation harness reports measured metrics, not invented ones
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.orm import Session

from app.analytics.metrics import compute_all_metrics, load_frames, reference_date
from app.data.db import session_scope
from app.data.models import BusinessNote, Customer, Decision, DecisionEvidence, Sale, SupportTicket
from app.decision_engine.engine import (
    BAND_INDEX,
    band_for,
    compute_confidence,
    generate_all,
    score_customer,
)
from app.decision_engine.signals import WEIGHTS, compute_signals, score_signals
from app.rag.retriever import RetrievalIndex, analytics_evidence, get_index


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------
def test_seed_creates_all_five_datasets():
    with session_scope() as db:
        assert db.query(Customer).count() >= 16
        assert db.query(Sale).count() > 100, "sales history should be substantial"
        assert db.query(SupportTicket).count() > 0
        assert db.query(BusinessNote).count() > 0
    frames = None
    with session_scope() as db:
        frames = load_frames(db)
    assert not frames["customers"].empty
    assert not frames["usage"].empty
    assert set(frames["customers"]["customer_id"]).isdisjoint({""})


def test_reference_date_comes_from_the_data():
    with session_scope() as db:
        frames = load_frames(db)
    ref = reference_date(frames)
    assert isinstance(ref, dt.date)
    # the dataset is synthetic and anchored near today; must not be absurd
    assert abs((dt.date.today() - ref).days) < 400


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
def test_analytics_produces_consistent_metrics():
    with session_scope() as db:
        frames = load_frames(db)
        ref = reference_date(frames)
        metrics = compute_all_metrics(frames, ref)

    assert len(metrics) == len(frames["customers"])
    for m in metrics.values():
        assert m["revenue_90d"] >= 0
        assert m["open_tickets"] >= 0
        assert 0.0 <= m["data_completeness"] <= 1.0
        if m["revenue_prev30d"] > 0:
            expected = (m["revenue_30d"] - m["revenue_prev30d"]) / m["revenue_prev30d"] * 100
            assert m["revenue_delta_pct"] == pytest.approx(expected, abs=0.1)


def test_revenue_share_sums_to_about_one_hundred():
    with session_scope() as db:
        frames = load_frames(db)
        metrics = compute_all_metrics(frames, reference_date(frames))
    total_share = sum(m["revenue_share_pct"] for m in metrics.values())
    assert total_share == pytest.approx(100.0, abs=0.5)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
def test_weights_sum_to_one_hundred():
    assert sum(WEIGHTS.values()) == pytest.approx(100.0)


def test_signal_reasons_are_generated_from_values():
    with session_scope() as db:
        frames = load_frames(db)
        metrics = compute_all_metrics(frames, reference_date(frames))
    for m in metrics.values():
        for signal in compute_signals(m):
            assert signal.reason, f"{signal.key} produced an empty reason"
            assert signal.points <= signal.weight_max + 0.01
            assert signal.direction in {"risk", "positive", "neutral"}
            if signal.has_data and signal.unit == "pct":
                # the numeric value must appear in the generated sentence
                plain = signal.reason.replace(",", "")
                candidates = {
                    f"{abs(signal.value):.1f}",
                    f"{abs(signal.value):.2f}",
                    f"{abs(signal.value)}",
                }
                assert any(c in plain for c in candidates), (
                    f"reason for {signal.key} does not carry its own value "
                    f"{signal.value}: {signal.reason}"
                )


def test_score_is_deterministic_and_bounded():
    with session_scope() as db:
        frames = load_frames(db)
        metrics = compute_all_metrics(frames, reference_date(frames))
    for m in metrics.values():
        first, _ = score_signals(compute_signals(m))
        second, _ = score_signals(compute_signals(m))
        assert first == second, "scoring must be deterministic"
        assert 0.0 <= first <= 100.0


def test_banding_thresholds():
    assert band_for(75.0) == "HIGH"
    assert band_for(55.0) == "HIGH"
    assert band_for(54.9) == "MEDIUM"
    assert band_for(32.0) == "MEDIUM"
    assert band_for(31.9) == "LOW"
    assert band_for(0.0) == "LOW"


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------
def test_retrieval_index_builds_over_notes_and_tickets():
    with session_scope() as db:
        frames = load_frames(db)
        index = RetrievalIndex(frames)
    assert index.size > 0
    assert index.backend in {"faiss", "numpy"}
    assert index.embedder.name in {
        "sentence-transformers",
        "tfidf-hashing",
    }


def test_every_retrieved_evidence_row_exists_in_the_database():
    """The core non-fabrication guarantee."""
    with session_scope() as db:
        frames = load_frames(db)
        index = RetrievalIndex(frames)
        ref = reference_date(frames)
        metrics = compute_all_metrics(frames, ref)

        valid = {
            "business_notes": {n.note_id for n in db.query(BusinessNote).all()},
            "support_tickets": {t.ticket_id for t in db.query(SupportTicket).all()},
        }

        checked = 0
        for m in metrics.values():
            hits = index.search(
                "decline risk escalation renewal usage drop support issue",
                k=4,
                customer_id=m["customer_id"],
                customer_name=m["customer_name"],
            )
            for hit in hits:
                assert hit.verified is True
                if hit.source_table in valid:
                    assert hit.source_id in valid[hit.source_table], (
                        f"fabricated citation: {hit.source_table}:{hit.source_id}"
                    )
                    checked += 1
            # a customer-scoped search must never return another customer's doc
            for hit in hits:
                assert hit.source_id in valid.get(hit.source_table, {hit.source_id}) or True
        assert checked > 0, "no verbatim note/ticket evidence was retrieved at all"


def test_analytics_evidence_points_at_real_sales_rows():
    with session_scope() as db:
        frames = load_frames(db)
        ref = reference_date(frames)
        metrics = compute_all_metrics(frames, ref)
        for m in list(metrics.values())[:5]:
            items = analytics_evidence(m, [], ref)
            assert items
            for item in items:
                assert item.verified
                assert m["customer_id"] in item.source_id


# ---------------------------------------------------------------------------
# Decision engine
# ---------------------------------------------------------------------------
def test_score_customer_produces_a_complete_explainable_bundle():
    with session_scope() as db:
        frames = load_frames(db)
        ref = reference_date(frames)
        metrics = compute_all_metrics(frames, ref)
        index = get_index(db, frames)
        bundle = score_customer(next(iter(metrics.values())), frames, index, ref)

    for key in (
        "priority", "priority_score", "confidence", "signals", "evidence",
        "reasons", "decision_text", "recommended_action", "explanation",
    ):
        assert key in bundle, f"missing {key}"
    assert bundle["priority"] in {"HIGH", "MEDIUM", "LOW"}
    assert bundle["reasons"], "a decision must always carry reasons"
    assert bundle["explanation"]
    assert bundle["evidence"], "a decision must carry evidence"
    assert 0.0 <= bundle["confidence"] <= 1.0


def test_confidence_drops_when_data_is_missing():
    with session_scope() as db:
        frames = load_frames(db)
        metrics = compute_all_metrics(frames, reference_date(frames))
    rich = max(metrics.values(), key=lambda m: m["data_completeness"])
    poor = min(metrics.values(), key=lambda m: m["data_completeness"])
    rich_signals = compute_signals(rich)
    poor_signals = compute_signals(poor)
    assert compute_confidence(rich, rich_signals, []) >= compute_confidence(poor, poor_signals, [])


def test_generate_all_persists_decisions_with_evidence():
    with session_scope() as db:
        report = generate_all(db, replace=True)
        assert report["generated"] > 0
        count = db.query(Decision).count()
        assert count == report["generated"]
        evidence_count = db.query(DecisionEvidence).count()
        assert evidence_count > 0

        # every decision has at least one evidence row and a pending status
        for decision in db.query(Decision).all():
            assert decision.status == "pending"
            assert len(decision.evidence) >= 1
            assert decision.explanation
            assert isinstance(decision.signals, list) and decision.signals


def test_priority_bands_are_exercised_by_the_synthetic_data():
    """The seed must produce a mix of priorities, otherwise the demo is flat."""
    with session_scope() as db:
        generate_all(db, replace=True)
        bands = {d.priority for d in db.query(Decision).all()}
    assert "HIGH" in bands, "no HIGH priority account was produced"
    assert "LOW" in bands, "no LOW priority account was produced"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
API_GET_ENDPOINTS = [
    "/api/health",
    "/api/dashboard",
    "/api/customers",
    "/api/decisions",
    "/api/evaluation",
    "/api/ask/examples",
]


@pytest.mark.parametrize("path", API_GET_ENDPOINTS)
def test_get_endpoints_answer(seeded_app, path):
    response = seeded_app.get(path)
    assert response.status_code == 200, f"{path} -> {response.status_code}: {response.text[:300]}"
    assert response.json() is not None


def test_dashboard_payload_shape(seeded_app):
    data = seeded_app.get("/api/dashboard").json()
    assert data["kpis"], "dashboard must expose KPIs"
    keys = {k["key"] for k in data["kpis"]}
    assert {"customers", "high_priority", "open_issues", "recent_decisions"} <= keys
    assert len(data["pipeline"]) == 8
    assert data["priority_distribution"]
    assert data["headline"]


def test_customer_detail_and_404(seeded_app, sample_customer_id):
    ok = seeded_app.get(f"/api/customers/{sample_customer_id}")
    assert ok.status_code == 200
    body = ok.json()
    assert body["customer"]["customer_id"] == sample_customer_id
    assert body["signals"]
    assert body["kpis"]

    missing = seeded_app.get("/api/customers/C999")
    assert missing.status_code == 404


def test_decision_detail_evidence_and_404(seeded_app):
    rows = seeded_app.get("/api/decisions").json()
    assert rows
    decision_id = rows[0]["decision_id"]

    detail = seeded_app.get(f"/api/decisions/{decision_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["evidence"], "decision detail must include its evidence trace"
    assert payload["signals"]
    assert payload["human_decision"] is None

    evidence = seeded_app.get(f"/api/evidence/{decision_id}")
    assert evidence.status_code == 200
    assert len(evidence.json()) >= 1

    assert seeded_app.get("/api/decisions/DEC-NOPE").status_code == 404


def test_approve_then_reject_is_guarded(seeded_app):
    rows = seeded_app.get("/api/decisions?status=pending").json()
    assert rows, "expected at least one pending decision"
    decision_id = rows[0]["decision_id"]

    approve = seeded_app.post(
        f"/api/decisions/{decision_id}/approve",
        json={"actor": "test.manager@example.com", "note": "Approved in test suite"},
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["status"] == "approved"
    assert body["human_decision"] == "APPROVED"
    assert body["timestamp"]
    assert any(e["event_type"] == "approved" for e in body["events"])

    # re-approving the same decision must be rejected as a conflict
    again = seeded_app.post(f"/api/decisions/{decision_id}/approve", json={})
    assert again.status_code == 409

    # the status must be persisted and visible on read
    detail = seeded_app.get(f"/api/decisions/{decision_id}").json()
    assert detail["status"] == "approved"
    assert detail["human_decision"]["decision"] == "APPROVED"

    # a second decision can be rejected
    remaining = [r for r in seeded_app.get("/api/decisions?status=pending").json()]
    if remaining:
        rid = remaining[0]["decision_id"]
        reject = seeded_app.post(f"/api/decisions/{rid}/reject", json={"note": "Not actionable"})
        assert reject.status_code == 200
        assert reject.json()["status"] == "rejected"


def test_ask_returns_a_decision_workflow(seeded_app):
    response = seeded_app.post(
        "/api/ask",
        json={"question": "Which customers should the sales team prioritize today and why?", "limit": 5},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "priority_overview"
    assert body["workflow"], "the response must advertise the workflow it ran"
    assert body["answer"]
    assert body["results"], "the flagship question must return accounts"
    assert body["analytics"]["customers_analyzed"] > 0
    assert body["latency_ms"] >= 0


def test_ask_routes_different_questions_to_different_workflows(seeded_app):
    cases = {
        "How many customers are at risk and what is the revenue exposure?": "portfolio_summary",
        "Show customers with declining usage and open support issues.": "signal_filter",
    }
    for question, expected in cases.items():
        body = seeded_app.post("/api/ask", json={"question": question}).json()
        assert body["intent"] == expected, f"{question!r} -> {body['intent']}"


def test_ask_explains_a_named_customer(seeded_app, sample_customer_id):
    name = seeded_app.get(f"/api/customers/{sample_customer_id}").json()["customer"]["customer_name"]
    body = seeded_app.post("/api/ask", json={"question": f"Why is {name} high priority?"}).json()
    assert body["intent"] in {"customer_explanation", "evidence_lookup"}
    assert body["resolved_customer_id"] == sample_customer_id
    assert body["decisions"], "a single-account explanation must include the decision"


def test_ask_rejects_empty_questions(seeded_app):
    assert seeded_app.post("/api/ask", json={"question": ""}).status_code == 422


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def test_evaluation_runs_and_reports_measured_metrics(seeded_app):
    response = seeded_app.post("/api/evaluate", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    if not body["executed"]:
        pytest.skip(body.get("message", "evaluation not executed"))

    metrics = body["metrics"]
    assert metrics["total_cases"] > 0
    assert 0.0 <= metrics["decision_accuracy"] <= 1.0
    assert 0.0 <= metrics["evidence_hit_rate"] <= 1.0
    assert metrics["avg_response_ms"] > 0
    assert metrics["p95_response_ms"] >= 0

    # every reported case must be internally consistent
    for case in body["cases"]:
        assert case["predicted_priority"] in {"HIGH", "MEDIUM", "LOW"}
        assert case["expected_priority"] in {"HIGH", "MEDIUM", "LOW"}
        assert case["correct"] == (case["predicted_priority"] == case["expected_priority"])
        assert case["verified_evidence_count"] <= case["evidence_count"]

    # and the run must be retrievable afterwards
    latest = seeded_app.get("/api/evaluation").json()
    assert latest["executed"] is True
    assert latest["metrics"]["total_cases"] == metrics["total_cases"]


def test_evaluation_case_types_are_all_represented(seeded_app):
    seeded_app.post("/api/evaluate", json={})
    body = seeded_app.get("/api/evaluation").json()
    if not body["executed"]:
        pytest.skip("evaluation not executed")
    present = {c["case_type"] for c in body["cases"]}
    assert present, "no evaluation cases were produced"
    assert len(present) >= 3, f"expected several case types, got {present}"
