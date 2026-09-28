"""REST API routes.

Every endpoint below is exercised by ``backend/tests/test_api.py``.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..analytics.metrics import (
    compute_all_metrics,
    compute_customer_metrics,
    load_frames,
    reference_date,
)
from ..config import settings
from ..data.db import get_db
from ..data.models import Customer, Decision, DecisionEvent, DecisionEvidence, EvaluationRun
from ..decision_engine.engine import (
    ACTION_LABELS,
    ACTION_OWNERS,
    ACTION_SLA,
    decision_to_dict,
    ensure_decisions,
    generate_all,
)
from ..evaluation.harness import CASE_TYPES, latest_run, pending_payload, run_evaluation
from ..rag.retriever import get_index
from ..schemas import (
    AskRequest,
    AskResponse,
    CustomerDetailOut,
    CustomerListItem,
    DashboardOut,
    DecisionOut,
    DecisionSummary,
    EvaluateRequest,
    EvaluationOut,
    EvidenceOut,
    HealthOut,
    ReviewRequest,
    ReviewResponse,
)
from .ask import run_ask

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@router.get("/health", response_model=HealthOut, tags=["system"])
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    frames = load_frames(db)
    ref = reference_date(frames) if not frames["customers"].empty else None
    index = get_index(db, frames) if not frames["customers"].empty else None
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "database": settings.DATABASE_URL.split("://")[0],
        "rows": {
            "customers": int(len(frames["customers"])),
            "sales": int(len(frames["sales"])),
            "usage_records": int(len(frames["usage"])),
            "support_tickets": int(len(frames["tickets"])),
            "business_notes": int(len(frames["notes"])),
            "decisions": int(db.query(Decision).count()),
            "decision_evidence": int(db.query(DecisionEvidence).count()),
            "evaluation_runs": int(db.query(EvaluationRun).count()),
        },
        "embedding_backend": index.embedder.name if index else "not-built",
        "embedding_model": getattr(index.embedder, "model_name", settings.EMBEDDING_MODEL) if index else settings.EMBEDDING_MODEL,
        "vector_backend": index.backend if index else settings.VECTOR_BACKEND,
        "llm_enabled": settings.llm_enabled,
        "llm_provider": settings.LLM_PROVIDER if settings.llm_enabled else "none (deterministic template mode)",
        "engine_mode": "llm-assisted" if settings.llm_enabled else "deterministic",
        "reference_date": ref,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@router.get("/dashboard", response_model=DashboardOut, tags=["dashboard"])
def dashboard(db: Session = Depends(get_db)) -> dict[str, Any]:
    frames = load_frames(db)
    if frames["customers"].empty:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Business database is empty. Run the seed command: `python -m app.data.seed`",
        )
    ensure_decisions(db)
    ref = reference_date(frames)
    metrics_map = compute_all_metrics(frames, ref)

    decisions = _latest_decisions(db)
    by_priority = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for d in decisions:
        by_priority[d.priority] = by_priority.get(d.priority, 0) + 1

    open_issues = sum(int(m["open_tickets"]) for m in metrics_map.values())
    critical_open = sum(int(m["critical_open"]) for m in metrics_map.values())
    revenue_at_risk = sum(
        metrics_map[d.customer_id]["revenue_90d"]
        for d in decisions
        if d.priority in {"HIGH", "MEDIUM"} and d.customer_id in metrics_map
    )
    pending = sum(1 for d in decisions if d.status == "pending")
    approved = sum(1 for d in decisions if d.status == "approved")
    rejected = sum(1 for d in decisions if d.status == "rejected")

    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    queue = sorted(
        [d for d in decisions if d.priority in {"HIGH", "MEDIUM"}],
        key=lambda d: (priority_order[d.priority], -d.priority_score),
    )[:8]

    attention = []
    for d in queue:
        payload = decision_to_dict(db, d, include_evidence=False)
        reasons = list(d.reasons or [])
        attention.append(
            {
                "customer_id": d.customer_id,
                "customer_name": payload["customer"]["customer_name"],
                "priority": d.priority,
                "priority_score": round(float(d.priority_score), 2),
                "confidence": payload["confidence"],
                "headline": d.decision_text,
                "top_reason": reasons[0] if reasons else "",
                "action_label": payload["recommended_action"]["label"],
                "account_value": payload["customer"]["account_value"],
                "status": d.status,
                "decision_id": d.decision_id,
            }
        )

    action_counts: dict[str, int] = {}
    for d in decisions:
        label = ACTION_LABELS.get(d.action_type, d.action_type)
        action_counts[label] = action_counts.get(label, 0) + 1

    issue_counts = {
        "Critical": critical_open,
        "High": sum(int(m["high_open"]) for m in metrics_map.values()),
        "Medium": sum(int(m["medium_open"]) for m in metrics_map.values()),
    }

    recent_decisions = [
        {
            "decision_id": d.decision_id,
            "customer_id": d.customer_id,
            "customer_name": (d.customer.customer_name if d.customer else d.customer_id),
            "priority": d.priority,
            "priority_score": round(float(d.priority_score), 2),
            "confidence": decision_to_dict(db, d, include_evidence=False)["confidence"],
            "decision_text": d.decision_text,
            "action_type": d.action_type,
            "status": d.status,
            "generated_at": d.generated_at,
        }
        for d in sorted(decisions, key=lambda d: d.generated_at, reverse=True)[:6]
    ]

    recent_evidence = [
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
        for e in (
            db.query(DecisionEvidence)
            .join(Decision, Decision.decision_id == DecisionEvidence.decision_id)
            .filter(Decision.priority == "HIGH")
            .order_by(DecisionEvidence.score.desc())
            .limit(8)
            .all()
        )
    ]

    headline = _headline(by_priority, critical_open, revenue_at_risk)

    return {
        "generated_at": dt.datetime.utcnow(),
        "reference_date": ref,
        "headline": headline,
        "kpis": [
            {"key": "customers", "label": "Total customers", "value": int(len(frames["customers"])), "unit": "accounts",
             "hint": f"{int((frames['customers']['status'] == 'at_risk').sum())} flagged at risk"},
            {"key": "high_priority", "label": "High-priority customers", "value": by_priority["HIGH"], "unit": "accounts",
             "hint": f"{by_priority['MEDIUM']} more at medium priority"},
            {"key": "open_issues", "label": "Open business issues", "value": open_issues, "unit": "tickets",
             "hint": f"{critical_open} at critical severity"},
            {"key": "revenue_at_risk", "label": "90-day revenue in scope", "value": round(revenue_at_risk, 2), "unit": "USD",
             "hint": "Revenue on HIGH and MEDIUM accounts"},
            {"key": "recent_decisions", "label": "Recent AI decisions", "value": len(recent_decisions), "unit": "decisions",
             "hint": f"{pending} awaiting human approval"},
            {"key": "approval_rate", "label": "Human decisions recorded", "value": approved + rejected, "unit": "reviews",
             "hint": f"{approved} approved · {rejected} rejected · {pending} pending"},
        ],
        "attention_queue": attention,
        "recent_decisions": recent_decisions,
        "priority_distribution": [
            {"label": "HIGH", "value": by_priority["HIGH"]},
            {"label": "MEDIUM", "value": by_priority["MEDIUM"]},
            {"label": "LOW", "value": by_priority["LOW"]},
        ],
        "action_distribution": [
            {"label": k, "value": v}
            for k, v in sorted(action_counts.items(), key=lambda kv: kv[1], reverse=True)
        ],
        "issue_distribution": [{"label": k, "value": v} for k, v in issue_counts.items()],
        "revenue_trend": _revenue_trend(frames, ref),
        "recent_evidence": recent_evidence,
        "pipeline": [
            {"step": "1", "name": "Business data", "detail": "customers · sales · usage · tickets · notes"},
            {"step": "2", "name": "Data processing", "detail": "pandas windows: 30d/14d/90d"},
            {"step": "3", "name": "Structured analytics", "detail": "revenue, adoption & queue metrics"},
            {"step": "4", "name": "RAG evidence retrieval", "detail": "vector search over notes + tickets"},
            {"step": "5", "name": "Signal fusion", "detail": "6 weighted deterministic signals"},
            {"step": "6", "name": "Decision engine", "detail": f"HIGH ≥ {settings.PRIORITY_HIGH_THRESHOLD:.0f}, MEDIUM ≥ {settings.PRIORITY_MEDIUM_THRESHOLD:.0f}"},
            {"step": "7", "name": "Evidence trace", "detail": "every citation resolves to a database row"},
            {"step": "8", "name": "Human approval", "detail": "approve / reject with an audit trail"},
        ],
        "data_health": {
            "customers": int(len(frames["customers"])),
            "sales_rows": int(len(frames["sales"])),
            "usage_rows": int(len(frames["usage"])),
            "ticket_rows": int(len(frames["tickets"])),
            "note_rows": int(len(frames["notes"])),
            "history_days": int(
                (ref - frames["customers"]["onboarded_on"].min().date()).days
            ) if not frames["customers"].empty else 0,
            "window_start": (ref - dt.timedelta(days=90)).isoformat(),
            "window_end": ref.isoformat(),
        },
    }


def _headline(by_priority: dict[str, int], critical_open: int, revenue_at_risk: float) -> str:
    if by_priority.get("HIGH", 0) == 0:
        return "No account is breaching the HIGH priority threshold right now. Maintain standard cadence."
    return (
        f"{by_priority['HIGH']} account(s) require attention today; "
        f"{critical_open} critical support issue(s) remain open across the book, "
        f"putting ${revenue_at_risk:,.0f} of 90-day revenue in scope."
    )


def _revenue_trend(frames: dict[str, pd.DataFrame], ref: dt.date) -> list[dict[str, Any]]:
    sales = frames["sales"]
    if sales.empty:
        return []
    start = pd.Timestamp(ref) - pd.Timedelta(days=180)
    window = sales[sales["date"] > start].copy()
    if window.empty:
        return []
    window["week"] = window["date"].dt.to_period("W").dt.start_time
    grouped = window.groupby("week").agg(revenue=("amount", "sum"), orders=("transaction_id", "count"))
    return [
        {
            "week": idx.date().isoformat(),
            "revenue": round(float(row["revenue"]), 2),
            "orders": int(row["orders"]),
        }
        for idx, row in grouped.iterrows()
    ]


def _latest_decisions(db: Session) -> list[Decision]:
    seen: set[str] = set()
    out: list[Decision] = []
    for d in db.query(Decision).order_by(Decision.generated_at.desc()).all():
        if d.customer_id in seen:
            continue
        seen.add(d.customer_id)
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
@router.get("/customers", response_model=list[CustomerListItem], tags=["customers"])
def list_customers(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="free-text search over name, industry, region"),
    priority: str | None = Query(default=None, pattern="^(HIGH|MEDIUM|LOW|high|medium|low)$"),
    region: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict[str, Any]]:
    frames = load_frames(db)
    if frames["customers"].empty:
        return []
    ensure_decisions(db)
    ref = reference_date(frames)
    metrics_map = compute_all_metrics(frames, ref)
    decisions = {d.customer_id: d for d in _latest_decisions(db)}

    rows: list[dict[str, Any]] = []
    for _, c in frames["customers"].iterrows():
        cid = c["customer_id"]
        m = metrics_map.get(cid)
        d = decisions.get(cid)

        if q:
            haystack = f"{c['customer_name']} {c['industry']} {c['region']} {c['segment']} {cid}".lower()
            if q.lower() not in haystack:
                continue
        if priority and (d is None or d.priority != priority.upper()):
            continue
        if region and c["region"].lower() != region.lower():
            continue
        if status_filter and c["status"].lower() != status_filter.lower():
            continue

        rows.append(
            {
                "customer_id": cid,
                "customer_name": c["customer_name"],
                "industry": c["industry"],
                "region": c["region"],
                "segment": c["segment"],
                "account_value": float(c["account_value"]),
                "status": c["status"],
                "owner": c["owner"],
                "priority": d.priority if d else None,
                "priority_score": round(float(d.priority_score), 2) if d else None,
                "revenue_90d": round(float(m["revenue_90d"]), 2) if m else 0.0,
                "open_tickets": int(m["open_tickets"]) if m else 0,
                "usage_delta_pct": m["usage_delta_pct"] if m else None,
            }
        )

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, None: 3}
    rows.sort(key=lambda r: (order.get(r["priority"], 3), -(r["priority_score"] or 0)))
    return rows[:limit]


@router.get("/customers/{customer_id}", response_model=CustomerDetailOut, tags=["customers"])
def customer_detail(customer_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    frames = load_frames(db)
    if frames["customers"].empty:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database is empty. Seed it first.")
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

    ensure_decisions(db)
    ref = reference_date(frames)
    metrics = compute_customer_metrics(frames, customer_id, ref)
    assert metrics is not None
    decision = (
        db.query(Decision)
        .filter(Decision.customer_id == customer_id)
        .order_by(Decision.generated_at.desc())
        .first()
    )
    payload = decision_to_dict(db, decision, include_evidence=True) if decision else None

    sales = frames["sales"]
    usage = frames["usage"]
    sdf = sales[sales["customer_id"] == customer_id].sort_values("date")
    udf = usage[usage["customer_id"] == customer_id].sort_values("date")

    revenue_series = _weekly_series(sdf, "amount", "sum")
    usage_series = _daily_series(udf, "active_users", "mean")

    tickets = [
        {
            "ticket_id": t.ticket_id,
            "issue": t.issue,
            "severity": t.severity,
            "status": t.status,
            "created_at": t.created_at,
            "resolved_at": t.resolved_at,
            "assignee": t.assignee,
            "age_days": (ref - t.created_at).days,
        }
        for t in sorted(customer.tickets, key=lambda t: t.created_at, reverse=True)
    ]
    notes = [
        {
            "note_id": n.note_id,
            "note_text": n.note_text,
            "note_type": n.note_type,
            "author_role": n.author_role,
            "date": n.date,
        }
        for n in sorted(customer.notes, key=lambda n: n.date, reverse=True)
    ]

    timeline: list[dict[str, Any]] = []
    for s in sorted(sales[sales["customer_id"] == customer_id].to_dict("records"), key=lambda r: r["date"], reverse=True)[:6]:
        timeline.append({
            "date": s["date"].date().isoformat(),
            "type": "sale",
            "title": f"Order {s['transaction_id']} · {s['product']}",
            "detail": f"${float(s['amount']):,.2f} · qty {int(s['quantity'])} · {s['channel']}",
        })
    for t in tickets[:6]:
        timeline.append({
            "date": t["created_at"].isoformat(),
            "type": "ticket",
            "title": f"Ticket {t['ticket_id']} · {t['severity']}",
            "detail": f"{t['issue']} — {t['status']}",
        })
    for n in notes[:6]:
        timeline.append({
            "date": n["date"].isoformat(),
            "type": "note",
            "title": f"Note {n['note_id']} · {n['note_type']}",
            "detail": n["note_text"],
        })
    timeline.sort(key=lambda item: item["date"], reverse=True)

    return {
        "customer": {
            "customer_id": customer.customer_id,
            "customer_name": customer.customer_name,
            "industry": customer.industry,
            "region": customer.region,
            "segment": customer.segment,
            "account_value": float(customer.account_value),
            "status": customer.status,
            "owner": customer.owner,
        },
        "onboarded_on": customer.onboarded_on,
        "kpis": [
            {"key": "revenue_90d", "label": "Revenue (90d)", "value": metrics["revenue_90d"], "unit": "USD",
             "delta_pct": metrics["revenue_delta_pct"], "hint": "30d vs prior 30d"},
            {"key": "usage", "label": "Active users (14d avg)", "value": metrics["usage_avg_14d"], "unit": "users",
             "delta_pct": metrics["usage_delta_pct"], "hint": "14d vs prior 14d"},
            {"key": "open_tickets", "label": "Open tickets", "value": metrics["open_tickets"], "unit": "tickets",
             "hint": f"{metrics['critical_open']} critical · oldest {metrics['oldest_open_days']}d"},
            {"key": "account_value", "label": "Contracted value", "value": float(customer.account_value), "unit": "USD",
             "hint": f"{metrics['revenue_share_pct']:.2f}% of book revenue"},
            {"key": "history", "label": "Recorded history", "value": metrics["history_days"], "unit": "days",
             "hint": f"onboarded {customer.onboarded_on.isoformat()}"},
            {"key": "completeness", "label": "Data completeness", "value": round(metrics["data_completeness"] * 100, 1),
             "unit": "%", "hint": f"{metrics['sales_points']} sales · {metrics['usage_points']} usage samples"},
        ],
        "signals": payload["signals"] if payload else [],
        "priority": payload["priority"] if payload else "LOW",
        "priority_score": payload["priority_score"] if payload else 0.0,
        "confidence": payload["confidence"] if payload else 0.0,
        "reasons": payload["reasons"] if payload else [],
        "recommended_action": payload["recommended_action"] if payload else None,
        "timeline": timeline,
        "revenue_series": revenue_series,
        "usage_series": usage_series,
        "tickets": tickets,
        "notes": notes,
        "latest_decision_id": decision.decision_id if decision else None,
    }


def _weekly_series(df: pd.DataFrame, col: str, agg: str) -> list[dict[str, Any]]:
    if df.empty:
        return []
    data = df.copy()
    data["week"] = data["date"].dt.to_period("W").dt.start_time
    grouped = data.groupby("week")[col].agg(agg)
    return [{"date": idx.date().isoformat(), "value": round(float(v), 2)} for idx, v in grouped.items()]


def _daily_series(df: pd.DataFrame, col: str, agg: str) -> list[dict[str, Any]]:
    if df.empty:
        return []
    grouped = df.groupby("date")[col].agg(agg)
    return [{"date": idx.date().isoformat(), "value": round(float(v), 2)} for idx, v in grouped.items()]


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
@router.get("/decisions", response_model=list[DecisionSummary], tags=["decisions"])
def list_decisions(
    db: Session = Depends(get_db),
    priority: str | None = Query(default=None, pattern="^(HIGH|MEDIUM|LOW|high|medium|low)$"),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(pending|approved|rejected)$"),
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    ensure_decisions(db)
    rows = db.query(Decision).order_by(Decision.priority_score.desc()).all()
    out: list[dict[str, Any]] = []
    for d in rows:
        if priority and d.priority != priority.upper():
            continue
        if status_filter and d.status != status_filter:
            continue
        name = d.customer.customer_name if d.customer else d.customer_id
        if q and q.lower() not in f"{name} {d.customer_id} {d.decision_text}".lower():
            continue
        out.append(
            {
                "decision_id": d.decision_id,
                "customer_id": d.customer_id,
                "customer_name": name,
                "priority": d.priority,
                "priority_score": round(float(d.priority_score), 2),
                "confidence": decision_to_dict(db, d, include_evidence=False)["confidence"],
                "decision_text": d.decision_text,
                "action_type": d.action_type,
                "status": d.status,
                "generated_at": d.generated_at,
            }
        )
        if len(out) >= limit:
            break
    return out


@router.get("/decisions/{decision_id}", response_model=DecisionOut, tags=["decisions"])
def get_decision(decision_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Decision {decision_id} not found")
    return decision_to_dict(db, decision, include_evidence=True)


@router.get("/evidence/{decision_id}", response_model=list[EvidenceOut], tags=["evidence"])
def get_evidence(decision_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Decision {decision_id} not found")
    payload = decision_to_dict(db, decision, include_evidence=True)
    return payload["evidence"]


# ---------------------------------------------------------------------------
# Human in the loop
# ---------------------------------------------------------------------------
@router.post("/decisions/{decision_id}/approve", response_model=ReviewResponse, tags=["human-in-the-loop"])
def approve_decision(
    decision_id: str, body: ReviewRequest = Body(default=ReviewRequest()), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return _review(db, decision_id, "approved", body)


@router.post("/decisions/{decision_id}/reject", response_model=ReviewResponse, tags=["human-in-the-loop"])
def reject_decision(
    decision_id: str, body: ReviewRequest = Body(default=ReviewRequest()), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return _review(db, decision_id, "rejected", body)


def _review(db: Session, decision_id: str, new_status: str, body: ReviewRequest) -> dict[str, Any]:
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Decision {decision_id} not found")
    if decision.status == new_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Decision {decision_id} is already {new_status}.",
        )

    decision.status = new_status
    now = dt.datetime.utcnow()
    db.add(
        DecisionEvent(
            decision_id=decision_id,
            event_type="approved" if new_status == "approved" else "rejected",
            actor=body.actor,
            note=body.note,
            created_at=now,
        )
    )
    db.commit()
    db.refresh(decision)

    events = [
        {"event_type": e.event_type, "actor": e.actor, "note": e.note, "created_at": e.created_at}
        for e in sorted(decision.events, key=lambda e: e.created_at)
    ]
    return {
        "decision_id": decision_id,
        "status": decision.status,
        "ai_recommendation": decision.recommended_action,
        "human_decision": "APPROVED" if new_status == "approved" else "REJECTED",
        "timestamp": now,
        "events": events,
    }


# ---------------------------------------------------------------------------
# Ask DeciTrace
# ---------------------------------------------------------------------------
@router.post("/ask", response_model=AskResponse, tags=["ask"])
def ask(payload: AskRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    return run_ask(db, payload.question, payload.customer_id, payload.limit)


@router.get("/ask/examples", tags=["ask"])
def ask_examples() -> dict[str, Any]:
    return {
        "examples": [
            "Which customers should the sales team prioritize today and why?",
            "Why is ACME Corp high priority?",
            "Show customers with declining usage and open support issues.",
            "Show me the evidence behind the highest-priority account.",
            "How many customers are at risk and what is the revenue exposure?",
            "Which accounts have critical support tickets?",
        ],
        "intents": [
            "priority_overview",
            "customer_explanation",
            "signal_filter",
            "evidence_lookup",
            "portfolio_summary",
        ],
    }


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
@router.post("/evaluate", response_model=EvaluationOut, tags=["evaluation"])
def evaluate(payload: EvaluateRequest = Body(default=EvaluateRequest()), db: Session = Depends(get_db)) -> dict[str, Any]:
    case_types = payload.case_types or CASE_TYPES
    return run_evaluation(db, case_types)


@router.get("/evaluation", response_model=EvaluationOut, tags=["evaluation"])
def evaluation_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    run = latest_run(db)
    return run if run else pending_payload()


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
@router.post("/admin/regenerate-decisions", tags=["operations"])
def regenerate(db: Session = Depends(get_db)) -> dict[str, Any]:
    return generate_all(db, replace=True)
