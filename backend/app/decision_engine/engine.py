"""The decision engine.

Pipeline implemented here
-------------------------
business rows
  -> structured analytics (pandas)
  -> weighted deterministic signals
  -> RAG evidence retrieval over notes/tickets
  -> signal fusion (score, confidence, banding)
  -> priority + reason strings (generated from the numbers)
  -> evidence trace (verified citations only)
  -> recommended action (rule-based, optionally LLM-phrased)
  -> persisted decision awaiting HUMAN APPROVAL

The score is deterministic. The LLM never influences the number, the band, the
reasons or the evidence — it may only rephrase the explanation sentence.
"""
from __future__ import annotations

import datetime as dt
import statistics
import uuid
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics.metrics import compute_all_metrics, load_frames, reference_date
from ..config import settings
from ..data.models import Customer, Decision, DecisionEvidence, DecisionEvent
from ..llm import explainer
from ..rag.retriever import (
    EvidenceItem,
    analytics_evidence,
    get_index,
    merge_evidence,
)
from .signals import (
    Signal,
    compute_signals,
    positive_signals,
    score_signals,
    top_risk_signals,
)

PRIORITY_BANDS = ("HIGH", "MEDIUM", "LOW")
BAND_INDEX = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

ACTION_LABELS = {
    "critical_escalation": "Critical support escalation",
    "account_review": "Executive account review",
    "adoption_recovery": "Adoption recovery session",
    "commercial_review": "Commercial position review",
    "stakeholder_checkin": "Stakeholder check-in",
    "monitor": "Monitor — no action required",
    "data_collection": "Gather missing data before deciding",
}

ACTION_OWNERS = {
    "critical_escalation": "Support Lead + Account Executive",
    "account_review": "Account Executive",
    "adoption_recovery": "Customer Success Manager",
    "commercial_review": "Account Executive",
    "stakeholder_checkin": "Customer Success Manager",
    "monitor": "Account Executive",
    "data_collection": "Sales Operations",
}

ACTION_SLA = {
    "critical_escalation": 4,
    "account_review": 40,
    "adoption_recovery": 72,
    "commercial_review": 48,
    "stakeholder_checkin": 72,
    "monitor": 240,
    "data_collection": 96,
}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def band_for(score: float) -> str:
    if score >= settings.PRIORITY_HIGH_THRESHOLD:
        return "HIGH"
    if score >= settings.PRIORITY_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def compute_confidence(metrics: dict[str, Any], signals: list[Signal], evidence: list[EvidenceItem]) -> float:
    """How much the engine trusts its own score.

    Confidence is driven by data completeness, how many signals were actually
    measurable, and how much evidence was retrieved and verified.
    """
    measurable = len([s for s in signals if s.has_data])
    signal_coverage = measurable / max(1, len(signals))
    verified = len([e for e in evidence if e.verified])
    evidence_factor = min(1.0, verified / 4.0)
    completeness = float(metrics.get("data_completeness", 0.0))
    confidence = 0.45 * completeness + 0.30 * signal_coverage + 0.25 * evidence_factor
    return round(max(0.05, min(0.98, confidence)), 3)


def confidence_label(confidence: float) -> str:
    if confidence >= 0.72:
        return "high"
    if confidence >= 0.5:
        return "moderate"
    return "low"


def is_insufficient(metrics: dict[str, Any], signals: list[Signal], evidence: list[EvidenceItem]) -> bool:
    """Insufficient evidence: not enough history/records to responsibly decide."""
    verified = [e for e in evidence if e.verified]
    measurable = len([s for s in signals if s.has_data])
    if not verified:
        return True
    if metrics.get("history_days", 0) < 45 and metrics.get("sales_points", 0) < 4:
        return True
    if measurable <= 2 and float(metrics.get("data_completeness", 0)) < 0.45:
        return True
    return False


def build_reasons(metrics: dict[str, Any], signals: list[Signal]) -> list[str]:
    """Reason strings, ordered by weight contributed. Generated from values."""
    risks = top_risk_signals(signals, limit=4)
    reasons = [f"{s.label}: {s.reason}" for s in risks]

    positives = positive_signals(signals)
    if positives:
        reasons.append(
            f"Offsetting positive signal — {positives[0].label}: {positives[0].reason}"
        )

    unmeasurable = [s for s in signals if not s.has_data]
    if unmeasurable:
        reasons.append(
            "Not measurable from available data: "
            + ", ".join(s.label for s in unmeasurable)
            + "."
        )

    if not risks and not unmeasurable:
        reasons.append(
            f"No signal is breaching its threshold; the account holds at "
            f"${float(metrics.get('revenue_90d', 0)):,.0f} of 90-day revenue on a stable trend."
        )
    return reasons


def build_decision_text(metrics: dict[str, Any], priority: str, signals: list[Signal], insufficient: bool) -> str:
    name = metrics.get("customer_name", "This account")
    if insufficient:
        return f"{name} cannot be responsibly prioritised yet — evidence is insufficient."
    risks = top_risk_signals(signals, limit=2)
    if priority == "HIGH" and risks:
        return (
            f"{name} requires attention today — "
            + " combined with ".join(s.label.lower() for s in risks)
            + "."
        )
    if priority == "MEDIUM" and risks:
        return (
            f"{name} should be reviewed this week — "
            + " and ".join(s.label.lower() for s in risks) + "."
        )
    if priority == "HIGH":
        return f"{name} is commercially material and requires an account review."
    return f"{name} is stable — no intervention required today."


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _event(db: Session, decision_id: str, event_type: str, actor: str = "system", note: str = "") -> None:
    db.add(
        DecisionEvent(
            decision_id=decision_id,
            event_type=event_type,
            actor=actor,
            note=note,
            created_at=dt.datetime.utcnow(),
        )
    )


def _next_decision_id(db: Session) -> str:
    count = db.query(Decision).count()
    stamp = dt.datetime.utcnow().strftime("%y%m%d")
    return f"DEC-{stamp}-{count + 1:04d}"


def score_customer(
    metrics: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    index,
    ref: dt.date,
    book_rank_pct: float = 0.0,
) -> dict[str, Any]:
    """Full deterministic decision bundle for one customer (no persistence)."""
    signals = compute_signals(metrics, book_rank_pct)
    score, signals = score_signals(signals)
    priority = band_for(score)

    # --- RAG: retrieve this customer's own notes/tickets ------------------
    retrieved = index.search(
        query=(
            "account risk decline churn escalation renewal blockers usage drop support issue "
            "competitor stakeholder adoption"
        ),
        k=4,
        customer_id=metrics["customer_id"],
        customer_name=metrics.get("customer_name", ""),
    )
    structured = analytics_evidence(metrics, signals, ref)
    evidence = merge_evidence(retrieved, structured, limit=8)

    confidence = compute_confidence(metrics, signals, evidence)
    insufficient = is_insufficient(metrics, signals, evidence)

    payload = {
        "metrics": metrics,
        "signals": [s.to_dict() for s in signals],
        "evidence": [e.to_dict() for e in evidence],
        "priority": priority,
        "priority_score": score,
        "confidence": confidence,
        "insufficient_evidence": insufficient,
    }
    action_type, action_sentence, action_llm = explainer.suggest_action(payload)
    explanation_llm = explainer.explain_decision({**payload, "recommended_action": action_sentence})

    return {
        "priority": priority,
        "priority_score": score,
        "confidence": confidence,
        "insufficient_evidence": insufficient,
        "signals": signals,
        "evidence": evidence,
        "reasons": build_reasons(metrics, signals),
        "decision_text": build_decision_text(metrics, priority, signals, insufficient),
        "action_type": action_type,
        "recommended_action": action_sentence,
        "explanation": explanation_llm.text,
        "llm_used": bool(explanation_llm.llm_used or action_llm.llm_used),
        "engine_mode": explanation_llm.mode if explanation_llm.llm_used else "deterministic",
        "metrics": metrics,
    }


def persist_decision(db: Session, bundle: dict[str, Any], customer: Customer) -> Decision:
    decision = Decision(
        decision_id=bundle.get("decision_id") or _next_decision_id(db),
        customer_id=customer.customer_id,
        generated_at=dt.datetime.utcnow(),
        priority=bundle["priority"],
        priority_score=float(bundle["priority_score"]),
        decision_text=bundle["decision_text"],
        action_type=bundle["action_type"],
        recommended_action=bundle["recommended_action"],
        reasons=list(bundle["reasons"]),
        signals=[s.to_dict() for s in bundle["signals"]],
        explanation=bundle["explanation"],
        summary=bundle["decision_text"],
        llm_used=bool(bundle.get("llm_used")),
        engine_mode=bundle.get("engine_mode", "deterministic"),
        status="pending",
    )
    db.add(decision)
    db.flush()

    for item in bundle["evidence"]:
        db.add(
            DecisionEvidence(
                decision_id=decision.decision_id,
                rank=item.rank,
                source_table=item.source_table,
                source_id=item.source_id,
                evidence_type=item.evidence_type,
                title=item.title,
                snippet=item.snippet,
                score=float(item.score),
                retrieval_method=item.retrieval_method,
                occurred_on=item.occurred_on,
                payload=item.payload,
            )
        )

    _event(db, decision.decision_id, "generated", "decision-engine", f"{bundle['priority']} · score {bundle['priority_score']}")
    return decision


def generate_all(db: Session, replace: bool = True) -> dict[str, Any]:
    """Score the whole book and persist one decision per customer."""
    started = dt.datetime.utcnow()
    frames = load_frames(db)
    if frames["customers"].empty:
        return {"generated": 0, "message": "No customers in the database. Run the seed command first."}

    ref = reference_date(frames)
    all_metrics = compute_all_metrics(frames, ref)
    index = get_index(db, frames, force=True)

    # materiality percentile for the ranking boost
    revenue_sorted = sorted(
        (m["revenue_90d"] for m in all_metrics.values()), reverse=True
    )

    def rank_pct(value: float) -> float:
        if not revenue_sorted:
            return 0.0
        rank = sum(1 for r in revenue_sorted if r > value)
        return 1.0 - (rank / len(revenue_sorted))

    if replace:
        db.query(DecisionEvent).delete()
        db.query(DecisionEvidence).delete()
        db.query(Decision).delete()
        db.flush()

    customers = {c.customer_id: c for c in db.query(Customer).all()}
    created: list[Decision] = []
    for cid, metrics in all_metrics.items():
        customer = customers.get(cid)
        if customer is None:
            continue
        bundle = score_customer(metrics, frames, index, ref, rank_pct(metrics["revenue_90d"]))
        created.append(persist_decision(db, bundle, customer))

    db.commit()
    duration = (dt.datetime.utcnow() - started).total_seconds() * 1000
    return {
        "generated": len(created),
        "reference_date": ref.isoformat(),
        "duration_ms": round(duration, 2),
        "embedding_backend": index.embedder.name,
        "vector_backend": index.backend,
        "indexed_documents": index.size,
    }


def ensure_decisions(db: Session) -> None:
    """Populate decisions if the table is empty (called on first read)."""
    if db.query(Decision).count() == 0 and db.query(Customer).count() > 0:
        generate_all(db, replace=False)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
def signal_breakdown(decision: Decision) -> list[dict[str, Any]]:
    return list(decision.signals or [])


def decision_to_dict(db: Session, decision: Decision, include_evidence: bool = True) -> dict[str, Any]:
    customer = decision.customer or db.get(Customer, decision.customer_id)
    signals = signal_breakdown(decision)
    evidence_rows = sorted(decision.evidence, key=lambda e: e.rank) if include_evidence else []

    evidence = [
        {
            "id": e.id,
            "rank": e.rank,
            "source_table": e.source_table,
            "source_id": e.source_id,
            "evidence_type": e.evidence_type,
            "title": e.title,
            "snippet": e.snippet,
            "score": round(float(e.score), 4),
            "retrieval_method": e.retrieval_method,
            "occurred_on": e.occurred_on,
            "verified": True,
            "payload": e.payload or {},
        }
        for e in evidence_rows
    ]

    confidence = _confidence_from_signals(signals, evidence)
    review_event = next(
        (e for e in sorted(decision.events, key=lambda x: x.created_at, reverse=True)
         if e.event_type in {"approved", "rejected"}),
        None,
    )
    human_decision = (
        {
            "decision": review_event.event_type.upper(),
            "actor": review_event.actor,
            "note": review_event.note,
            "timestamp": review_event.created_at,
        }
        if review_event
        else None
    )

    score = float(decision.priority_score)
    return {
        "decision_id": decision.decision_id,
        "customer": {
            "customer_id": customer.customer_id if customer else decision.customer_id,
            "customer_name": customer.customer_name if customer else "Unknown",
            "industry": customer.industry if customer else "",
            "region": customer.region if customer else "",
            "segment": customer.segment if customer else "",
            "account_value": float(customer.account_value) if customer else 0.0,
            "status": customer.status if customer else "",
            "owner": customer.owner if customer else "",
        },
        "generated_at": decision.generated_at,
        "priority": decision.priority,
        "priority_score": round(score, 2),
        "priority_score_band": _band_explainer(score),
        "confidence": confidence,
        "confidence_label": confidence_label(confidence),
        "insufficient_evidence": _insufficient_from_stored(signals, evidence),
        "decision_text": decision.decision_text,
        "summary": decision.summary or decision.decision_text,
        "reasons": list(decision.reasons or []),
        "signals": signals,
        "top_signals": [
            s["label"] for s in sorted(
                [s for s in signals if s.get("direction") == "risk" and s.get("points", 0) > 0],
                key=lambda s: s.get("points", 0),
                reverse=True,
            )[:3]
        ],
        "recommended_action": {
            "action_type": decision.action_type,
            "label": ACTION_LABELS.get(decision.action_type, decision.action_type.replace("_", " ").title()),
            "owner": ACTION_OWNERS.get(decision.action_type, "Account Executive"),
            "sla_hours": ACTION_SLA.get(decision.action_type, 48),
            "rationale": decision.recommended_action,
        },
        "explanation": decision.explanation,
        "engine_mode": decision.engine_mode,
        "llm_used": bool(decision.llm_used),
        "status": decision.status,
        "evidence": evidence,
        "human_decision": human_decision,
    }


def _insufficient_from_stored(signals: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> bool:
    """Mirror of ``is_insufficient`` using only what was persisted on the decision."""
    verified = [e for e in evidence if e.get("verified", True)]
    measurable = len([s for s in signals if s.get("has_data", True)])
    if not verified:
        return True
    return measurable <= 2


def _confidence_from_signals(signals: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> float:
    if not signals:
        return 0.0
    measurable = len([s for s in signals if s.get("has_data", True)])
    coverage = measurable / max(1, len(signals))
    ev = min(1.0, len(evidence) / 4.0)
    return round(max(0.05, min(0.98, 0.55 * coverage + 0.45 * ev)), 3)


def _band_explainer(score: float) -> str:
    high = settings.PRIORITY_HIGH_THRESHOLD
    medium = settings.PRIORITY_MEDIUM_THRESHOLD
    if score >= high:
        return f"Score {score:.1f} ≥ HIGH threshold {high:.0f}"
    if score >= medium:
        return f"Score {score:.1f} in MEDIUM band {medium:.0f}–{high:.0f}"
    return f"Score {score:.1f} < MEDIUM threshold {medium:.0f}"
