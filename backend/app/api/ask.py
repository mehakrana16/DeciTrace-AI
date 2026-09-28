"""Question router for Ask DeciTrace.

A manager's question is classified into one of five *workflows*, each of which
resolves to a concrete analytics + retrieval plan. The plan is then executed
against the database. The response always advertises the workflow that ran, so
the tool never looks like a generic chatbot: it shows its own method.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from ..analytics.metrics import load_frames, reference_date
from ..data.models import Customer, Decision
from ..decision_engine.engine import (
    ACTION_LABELS,
    decision_to_dict,
    generate_all,
    signal_breakdown,
)
from ..rag.retriever import get_index

INTENTS = {
    "priority_overview": {
        "label": "Prioritised attention queue",
        "workflow": [
            "Parse question",
            "Score every customer through the decision engine",
            "Rank by weighted priority score",
            "Retrieve verified evidence for the top accounts",
            "Compose prioritised answer",
        ],
    },
    "customer_explanation": {
        "label": "Single-account explanation",
        "workflow": [
            "Resolve customer from the question",
            "Load stored decision and signal breakdown",
            "Retrieve that customer's notes and tickets",
            "Verify evidence against the operational store",
            "Explain why the priority was assigned",
        ],
    },
    "signal_filter": {
        "label": "Signal-filtered account search",
        "workflow": [
            "Extract signal constraints from the question",
            "Load structured analytics for the whole book",
            "Apply deterministic filters",
            "Attach decisions and evidence",
            "Return matching accounts",
        ],
    },
    "evidence_lookup": {
        "label": "Evidence trace lookup",
        "workflow": [
            "Identify the target account",
            "Run vector retrieval over business notes and tickets",
            "Verify every hit against the operational store",
            "Group evidence by source type",
            "Present the evidence trace",
        ],
    },
    "portfolio_summary": {
        "label": "Portfolio analytics summary",
        "workflow": [
            "Load structured analytics",
            "Aggregate portfolio-level metrics",
            "Retrieve recent evidence sample",
            "Summarise exposure and recommended actions",
        ],
    },
}

# ---------------------------------------------------------------------------
# Constraint vocabulary for the signal filter
# ---------------------------------------------------------------------------
DECLINE_PATTERNS = [
    r"declin", r"drop", r"falling", r"fall\b", r"decreas", r"slowing", r"losing",
    r"contract", r"churn", r"reduce", r"downturn",
]
USAGE_PATTERNS = [r"usage", r"adoption", r"active user", r"engagement", r"login"]
REVENUE_PATTERNS = [r"revenue", r"sales", r"spend", r"billing", r"commercial", r"payment"]
SUPPORT_PATTERNS = [
    r"support", r"ticket", r"issue", r"incident", r"escalation", r"unresolved",
    r"severity", r"critical", r"complaint",
]
RISK_PATTERNS = [r"risk", r"at risk", r"trouble", r"problem", r"concern", r"attention", r"urgent"]
STABLE_PATTERNS = [r"healthy", r"stable", r"doing well", r"safe", r"no risk"]
EXPLAIN_PATTERNS = [r"why", r"explain", r"reason", r"justify", r"high risk", r"how come"]
EVIDENCE_PATTERNS = [r"evidence", r"proof", r"citation", r"show me the record", r"trace", r"backed by"]


def _has(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def classify(question: str, db: Session) -> tuple[str, dict[str, Any], Customer | None]:
    q = question.lower()
    filters: dict[str, Any] = {}
    target: Customer | None = None

    # --- does the question name a customer? --------------------------------
    # Pass 1: an exact full-name or customer-id match is unambiguous, so it wins.
    customers = db.query(Customer).all()
    for c in customers:
        if c.customer_name.lower() in q or c.customer_id.lower() in q:
            target = c
            break
    # Pass 2: fall back to the distinctive first word, but only when that word
    # is unique across the book ("Vertex Group" vs "Vertex Retail" must not
    # resolve to whichever customer happens to be loaded first).
    if target is None:
        head_counts: dict[str, int] = {}
        for c in customers:
            head = c.customer_name.lower().split()[0]
            head_counts[head] = head_counts.get(head, 0) + 1
        for c in customers:
            head = c.customer_name.lower().split()[0]
            if (
                len(head) > 3
                and head_counts.get(head, 0) == 1
                and re.search(rf"\b{re.escape(head)}\b", q)
            ):
                target = c
                break

    # --- explicit severity / region / segment constraints ------------------
    for sev in ("critical", "high", "medium", "low"):
        if re.search(rf"\b{sev}\b", q) and _has(q, SUPPORT_PATTERNS):
            filters["severity"] = sev
            break
    for region in ("north america", "emea", "apac", "latam"):
        if region in q:
            filters["region"] = region.title() if region != "emea" else "EMEA"
    for seg in ("enterprise", "mid-market", "smb"):
        if seg in q:
            filters["segment"] = seg.title() if seg != "smb" else "SMB"

    if target is not None and _has(q, EVIDENCE_PATTERNS):
        return "evidence_lookup", filters, target
    if target is not None:
        return "customer_explanation", filters, target

    if _has(q, EVIDENCE_PATTERNS):
        return "evidence_lookup", filters, None

    if _has(q, DECLINE_PATTERNS) or _has(q, SUPPORT_PATTERNS) or filters:
        return "signal_filter", filters, None

    if _has(q, [r"how many", r"total", r"overview", r"summary", r"portfolio", r"revenue at risk", r"distribution"]):
        return "portfolio_summary", filters, None

    # default: the flagship "who needs attention today" question
    return "priority_overview", filters, None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
def _ensure_decisions(db: Session) -> None:
    if db.query(Decision).count() == 0 and db.query(Customer).count() > 0:
        generate_all(db, replace=False)


def run_ask(db: Session, question: str, customer_id: str | None = None, limit: int = 5) -> dict[str, Any]:
    started = dt.datetime.utcnow()
    frames = load_frames(db)
    if frames["customers"].empty:
        return {
            "question": question,
            "intent": "empty",
            "intent_label": "No data available",
            "workflow": ["Load business data"],
            "answer": (
                "The business database is empty. Seed it first with "
                "`python -m app.data.seed`, then ask again."
            ),
            "llm_used": False,
            "engine_mode": "deterministic",
            "resolved_customer_id": None,
            "filters": {},
            "results": [],
            "decisions": [],
            "evidence": [],
            "analytics": {"customers_analyzed": 0, "decisions_considered": 0},
            "latency_ms": round((dt.datetime.utcnow() - started).total_seconds() * 1000, 2),
        }

    _ensure_decisions(db)
    ref = reference_date(frames)
    intent, filters, target = classify(question, db)
    meta = INTENTS[intent]

    decisions = {
        d.customer_id: d
        for d in db.query(Decision).order_by(Decision.generated_at.desc()).all()
    }
    # keep only the newest decision per customer
    seen: set[str] = set()
    unique_decisions: dict[str, Decision] = {}
    for d in db.query(Decision).order_by(Decision.generated_at.desc()).all():
        if d.customer_id in seen:
            continue
        seen.add(d.customer_id)
        unique_decisions[d.customer_id] = d

    metrics_map = _metrics_for(db, frames, ref)

    if customer_id:
        target = db.get(Customer, customer_id) or target

    if intent in {"customer_explanation", "evidence_lookup"} and target is not None:
        decision = unique_decisions.get(target.customer_id)
        payload = decision_to_dict(db, decision, include_evidence=True) if decision else None

        if intent == "evidence_lookup":
            index = get_index(db, frames)
            retrieved = index.customer_documents(target.customer_id, k=8)
            evidence = [e.to_dict() for e in retrieved]
            if decision:
                evidence = _merge_unique(evidence, payload.get("evidence", []))
            analytics = {
                "customers_analyzed": len(frames["customers"]),
                "decisions_considered": len(unique_decisions),
                "evidence_checked": len(evidence),
                "source_breakdown": _source_breakdown(evidence),
            }
        else:
            evidence = payload.get("evidence", []) if payload else []
            analytics = {
                "customers_analyzed": len(frames["customers"]),
                "decisions_considered": len(unique_decisions),
                "evidence_checked": len(evidence),
                "signal_breakdown": {
                    s["label"]: s["points"] for s in (payload.get("signals", []) if payload else [])
                },
            }

        results = (
            [
                {
                    "customer_id": payload["customer"]["customer_id"],
                    "customer_name": payload["customer"]["customer_name"],
                    "priority": payload["priority"],
                    "priority_score": payload["priority_score"],
                    "confidence": payload["confidence"],
                    "reasons": payload["reasons"],
                    "action_label": payload["recommended_action"]["label"],
                    "decision_id": payload["decision_id"],
                    "status": payload["status"],
                }
            ]
            if payload
            else []
        )
        return _finalise(
            question, intent, meta, results,
            [payload] if payload else [], evidence, analytics, started,
        )

    if intent == "portfolio_summary":
        high = [d for d in unique_decisions.values() if d.priority == "HIGH"]
        medium = [d for d in unique_decisions.values() if d.priority == "MEDIUM"]
        revenue_at_risk = sum(
            metrics_map.get(d.customer_id, {}).get("revenue_90d", 0.0)
            for d in high + medium
        )
        open_issues = sum(
            int(metrics_map.get(m["customer_id"], {}).get("open_tickets", 0))
            for m in metrics_map.values()
        )
        analytics = {
            "customers_analyzed": len(frames["customers"]),
            "decisions_considered": len(unique_decisions),
            "high_priority": len(high),
            "medium_priority": len(medium),
            "low_priority": len(unique_decisions) - len(high) - len(medium),
            "revenue_at_risk_90d": round(revenue_at_risk, 2),
            "open_support_issues": open_issues,
            "reference_date": ref.isoformat(),
        }
        ordered = sorted(
            unique_decisions.values(), key=lambda d: d.priority_score, reverse=True
        )[:limit]
        payloads = [decision_to_dict(db, d, include_evidence=True) for d in ordered]
        results = [_row_from_payload(p) for p in payloads]
        evidence = _collect_evidence(payloads, limit=8)
        return _finalise(question, intent, meta, results, payloads, evidence, analytics, started)

    if intent == "signal_filter":
        matched = _apply_filters(metrics_map, filters, frames, db)
        matched.sort(
            key=lambda m: (
                unique_decisions.get(m["customer_id"]).priority_score
                if unique_decisions.get(m["customer_id"])
                else 0.0
            ),
            reverse=True,
        )
        matched = matched[:limit]
        payloads = [
            decision_to_dict(db, unique_decisions[m["customer_id"]], include_evidence=True)
            for m in matched
            if unique_decisions.get(m["customer_id"])
        ]
        results = [_row_from_payload(p) for p in payloads]
        evidence = _collect_evidence(payloads, limit=8)
        analytics = {
            "customers_analyzed": len(frames["customers"]),
            "decisions_considered": len(unique_decisions),
            "matched": len(matched),
            "filters_applied": filters or {"risk_signals": "decline | support | escalation"},
            "evidence_checked": len(evidence),
            "match_criteria": _describe_filters(filters, frames),
        }
        return _finalise(question, intent, meta, results, payloads, evidence, analytics, started)

    # ---- default: priority overview ---------------------------------------
    ordered = sorted(unique_decisions.values(), key=lambda d: d.priority_score, reverse=True)[:limit]
    payloads = [decision_to_dict(db, d, include_evidence=True) for d in ordered]
    results = [_row_from_payload(p) for p in payloads]
    evidence = _collect_evidence(payloads, limit=8)
    high = sum(1 for d in unique_decisions.values() if d.priority == "HIGH")
    analytics = {
        "customers_analyzed": len(frames["customers"]),
        "decisions_considered": len(unique_decisions),
        "high_priority": high,
        "reference_date": ref.isoformat(),
        "evidence_checked": len(evidence),
        "revenue_at_risk_90d": round(
            sum(
                metrics_map.get(d.customer_id, {}).get("revenue_90d", 0.0)
                for d in unique_decisions.values()
                if d.priority in {"HIGH", "MEDIUM"}
            ),
            2,
        ),
    }
    return _finalise(question, intent, meta, results, payloads, evidence, analytics, started)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _metrics_for(db: Session, frames: dict[str, pd.DataFrame], ref: dt.date) -> dict[str, dict]:
    from ..analytics.metrics import compute_all_metrics

    return compute_all_metrics(frames, ref)


def _apply_filters(
    metrics_map: dict[str, dict], filters: dict[str, Any], frames: dict[str, pd.DataFrame], db: Session
) -> list[dict]:
    out = []
    for m in metrics_map.values():
        if filters.get("region") and m["region"] != filters["region"]:
            continue
        if filters.get("segment") and m["segment"] != filters["segment"]:
            continue
        if filters.get("severity"):
            severity = filters["severity"]
            key = f"{severity}_open"
            if key in m and int(m.get(key, 0)) == 0:
                continue
            if severity == "low" and m["open_tickets"] == 0:
                continue

        usage_declining = m["usage_delta_pct"] is not None and m["usage_delta_pct"] <= -8
        revenue_declining = m["revenue_delta_pct"] is not None and m["revenue_delta_pct"] <= -10
        has_open_issue = m["open_tickets"] > 0
        high_severity = m["critical_open"] > 0 or m["high_open"] > 0
        narrative_risk = m["note_risk_hits"] > 0

        if filters.get("severity"):
            keep = has_open_issue or high_severity
        else:
            keep = (usage_declining and has_open_issue) or high_severity or (
                revenue_declining and (usage_declining or narrative_risk)
            ) or (usage_declining and narrative_risk)
        if keep:
            out.append(m)
    return out


def _describe_filters(filters: dict[str, Any], frames: dict[str, pd.DataFrame]) -> list[str]:
    if filters:
        return [f"{k} = {v}" for k, v in filters.items()]
    return [
        "usage_delta_pct <= -8 AND open_tickets >= 1",
        "OR critical_open >= 1 OR high_open >= 1",
        "OR revenue_delta_pct <= -10 AND (usage_delta_pct <= -8 OR narrative_risk)",
    ]


def _row_from_payload(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_id": p["customer"]["customer_id"],
        "customer_name": p["customer"]["customer_name"],
        "priority": p["priority"],
        "priority_score": p["priority_score"],
        "confidence": p["confidence"],
        "reasons": p["reasons"],
        "action_label": p["recommended_action"]["label"],
        "decision_id": p["decision_id"],
        "status": p["status"],
    }


def _collect_evidence(payloads: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for p in payloads:
        for e in p.get("evidence", []):
            key = (e["source_table"], e["source_id"])
            if key in seen:
                continue
            seen.add(key)
            out.append({**e, "decision_id": p["decision_id"], "customer_id": p["customer"]["customer_id"]})
    out.sort(key=lambda e: (e.get("score", 0), e.get("occurred_on") or ""), reverse=True)
    return out[:limit]


def _merge_unique(a: list[dict], b: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for item in a + b:
        key = (item["source_table"], item["source_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    for rank, item in enumerate(out, start=1):
        item["rank"] = rank
    return out


def _source_breakdown(evidence: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in evidence:
        out[e["source_table"]] = out.get(e["source_table"], 0) + 1
    return out


def _finalise(
    question: str,
    intent: str,
    meta: dict[str, Any],
    results: list[dict[str, Any]],
    payloads: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    analytics: dict[str, Any],
    started: dt.datetime,
) -> dict[str, Any]:
    from ..llm import explainer

    llm_payload = {
        "question": question,
        "intent_label": meta["label"],
        "results": results,
        "analytics": analytics,
    }
    llm_result = explainer.answer_question(llm_payload)

    return {
        "question": question,
        "intent": intent,
        "intent_label": meta["label"],
        "workflow": meta["workflow"],
        "answer": llm_result.text,
        "llm_used": bool(llm_result.llm_used),
        "engine_mode": llm_result.mode,
        "resolved_customer_id": (
            results[0]["customer_id"] if results and intent == "customer_explanation" else None
        ),
        "filters": analytics.get("filters_applied", {}),
        "results": results,
        "decisions": payloads,
        "evidence": evidence,
        "analytics": analytics,
        "latency_ms": round((dt.datetime.utcnow() - started).total_seconds() * 1000, 2),
    }

