"""Structured analytics layer.

Every business number surfaced anywhere in DeciTrace AI is produced here, with
pandas, from rows stored in the operational database. The LLM layer never
computes a metric — it only receives values that this module already produced.

Public API
----------
``load_frames``            : materialise the five datasets as DataFrames
``reference_date``         : the "today" of the dataset (max observed activity)
``compute_all_metrics``    : per-customer metric bundle for the whole book
``compute_customer_metrics``: metric bundle for one customer
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from ..data.models import BusinessNote, Customer, Sale, SupportTicket, UsageRecord

# Windows (days) used by the analytics layer
RECENT_WINDOW = 30
PRIOR_WINDOW = 30
USAGE_RECENT_WINDOW = 14
USAGE_PRIOR_WINDOW = 14

RISK_NOTE_TYPES = {"risk", "escalation"}
POSITIVE_KEYWORDS = [
    "seasonal", "no churn", "steady", "stable", "expansion", "budget approval",
    "went well", "critical infrastructure", "successful pilot", "renew", "commit",
]
RISK_KEYWORDS = [
    "churn", "evaluating competitors", "not renew", "escalated", "outage",
    "failure", "failures", "downtime", "dropped sharply", "champion left",
    "slower than before", "beyond the contractual", "remediation plan",
    "executive sponsor", "risk", "unresolved", "delayed", "inconsistent",
]


# ---------------------------------------------------------------------------
# Frame loading
# ---------------------------------------------------------------------------
def load_frames(db: Session) -> dict[str, pd.DataFrame]:
    """Load the five datasets into pandas DataFrames."""

    def _frame(rows: list[dict], columns: list[str], date_cols: list[str]) -> pd.DataFrame:
        frame = pd.DataFrame(rows, columns=columns)
        for col in date_cols:
            if col in frame.columns:
                frame[col] = pd.to_datetime(frame[col], errors="coerce")
        return frame

    customers = [
        {
            "customer_id": c.customer_id,
            "customer_name": c.customer_name,
            "industry": c.industry,
            "region": c.region,
            "segment": c.segment,
            "account_value": float(c.account_value),
            "owner": c.owner,
            "status": c.status,
            "onboarded_on": c.onboarded_on,
            "archetype": c.archetype,
        }
        for c in db.query(Customer).all()
    ]
    sales = [
        {
            "transaction_id": s.transaction_id,
            "customer_id": s.customer_id,
            "date": s.date,
            "amount": float(s.amount),
            "product": s.product,
            "quantity": int(s.quantity),
            "channel": s.channel,
        }
        for s in db.query(Sale).all()
    ]
    usage = [
        {
            "customer_id": u.customer_id,
            "date": u.date,
            "active_users": int(u.active_users),
            "sessions": int(u.sessions),
            "usage_minutes": int(u.usage_minutes),
        }
        for u in db.query(UsageRecord).all()
    ]
    tickets = [
        {
            "ticket_id": t.ticket_id,
            "customer_id": t.customer_id,
            "issue": t.issue,
            "description": t.description,
            "severity": t.severity,
            "status": t.status,
            "created_at": t.created_at,
            "resolved_at": t.resolved_at,
            "assignee": t.assignee,
        }
        for t in db.query(SupportTicket).all()
    ]
    notes = [
        {
            "note_id": n.note_id,
            "customer_id": n.customer_id,
            "note_text": n.note_text,
            "author_role": n.author_role,
            "note_type": n.note_type,
            "date": n.date,
        }
        for n in db.query(BusinessNote).all()
    ]

    return {
        "customers": _frame(
            customers,
            ["customer_id", "customer_name", "industry", "region", "segment",
             "account_value", "owner", "status", "onboarded_on", "archetype"],
            ["onboarded_on"],
        ),
        "sales": _frame(
            sales,
            ["transaction_id", "customer_id", "date", "amount", "product", "quantity", "channel"],
            ["date"],
        ),
        "usage": _frame(
            usage, ["customer_id", "date", "active_users", "sessions", "usage_minutes"], ["date"]
        ),
        "tickets": _frame(
            tickets,
            ["ticket_id", "customer_id", "issue", "description", "severity", "status",
             "created_at", "resolved_at", "assignee"],
            ["created_at", "resolved_at"],
        ),
        "notes": _frame(
            notes,
            ["note_id", "customer_id", "note_text", "author_role", "note_type", "date"],
            ["date"],
        ),
    }


def reference_date(frames: dict[str, pd.DataFrame]) -> dt.date:
    """The latest date observed anywhere — the dataset's own 'today'."""
    latest: dt.Timestamp | None = None
    for key, col in (("sales", "date"), ("usage", "date"), ("notes", "date"), ("tickets", "created_at")):
        frame = frames.get(key)
        if frame is None or frame.empty or col not in frame.columns:
            continue
        value = frame[col].max()
        if pd.isna(value):
            continue
        latest = value if latest is None else max(latest, value)
    if latest is None:
        return dt.date.today()
    return latest.date()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pct_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None if current <= 0 else 100.0
    return (current - previous) / previous * 100.0


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


# ---------------------------------------------------------------------------
# Metric bundle
# ---------------------------------------------------------------------------
@dataclass
class CustomerMetrics:
    customer_id: str
    customer_name: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.metrics.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.metrics[key]


def _empty_metrics(customer_row: pd.Series, ref: dt.date) -> dict[str, Any]:
    onboarded = customer_row.get("onboarded_on")
    history_days = (ref - onboarded.date()).days if pd.notna(onboarded) else 0
    return {
        "customer_id": customer_row["customer_id"],
        "customer_name": customer_row["customer_name"],
        "industry": customer_row["industry"],
        "region": customer_row["region"],
        "segment": customer_row["segment"],
        "owner": customer_row["owner"],
        "status": customer_row["status"],
        "archetype": customer_row["archetype"],
        "account_value": float(customer_row["account_value"]),
        "onboarded_on": onboarded.date().isoformat() if pd.notna(onboarded) else None,
        "history_days": history_days,
        "revenue_90d": 0.0,
        "revenue_30d": 0.0,
        "revenue_prev30d": 0.0,
        "revenue_delta_pct": None,
        "txns_30d": 0,
        "txns_prev30d": 0,
        "txn_delta_pct": None,
        "avg_order_value": 0.0,
        "usage_avg_14d": 0.0,
        "usage_prev14d": 0.0,
        "usage_delta_pct": None,
        "usage_minutes_avg_14d": 0.0,
        "sessions_avg_14d": 0.0,
        "days_since_last_sale": None,
        "days_since_last_usage": None,
        "open_tickets": 0,
        "critical_open": 0,
        "high_open": 0,
        "medium_open": 0,
        "resolved_tickets": 0,
        "oldest_open_days": 0,
        "avg_open_age_days": 0.0,
        "notes_count": 0,
        "note_risk_hits": 0,
        "note_positive_hits": 0,
        "note_risk_types": 0,
        "revenue_share_pct": 0.0,
        "data_completeness": 0.0,
        "sales_points": 0,
        "usage_points": 0,
        "reference_date": ref.isoformat(),
    }


def compute_all_metrics(frames: dict[str, pd.DataFrame], ref: dt.date) -> dict[str, dict[str, Any]]:
    """Compute the metric bundle for every customer in the book."""
    customers = frames["customers"]
    if customers.empty:
        return {}

    total_90d_revenue = 0.0
    out: dict[str, dict[str, Any]] = {}

    for _, row in customers.iterrows():
        m = _compute_one(frames, row, ref)
        out[row["customer_id"]] = m
        total_90d_revenue += m["revenue_90d"]

    for m in out.values():
        m["revenue_share_pct"] = (
            round(m["revenue_90d"] / total_90d_revenue * 100.0, 2) if total_90d_revenue > 0 else 0.0
        )
    return out


def _compute_one(frames: dict[str, pd.DataFrame], row: pd.Series, ref: dt.date) -> dict[str, Any]:
    cid = row["customer_id"]
    m = _empty_metrics(row, ref)

    # ---------------- sales ------------------------------------------------
    sales = frames["sales"]
    sdf = sales[sales["customer_id"] == cid] if not sales.empty else sales
    if not sdf.empty:
        cutoff_recent = pd.Timestamp(ref) - pd.Timedelta(days=RECENT_WINDOW)
        cutoff_prior = pd.Timestamp(ref) - pd.Timedelta(days=RECENT_WINDOW + PRIOR_WINDOW)
        cutoff_90 = pd.Timestamp(ref) - pd.Timedelta(days=90)

        recent = sdf[sdf["date"] > cutoff_recent]
        prior = sdf[(sdf["date"] > cutoff_prior) & (sdf["date"] <= cutoff_recent)]
        window90 = sdf[sdf["date"] > cutoff_90]

        m["revenue_30d"] = round(float(recent["amount"].sum()), 2)
        m["revenue_prev30d"] = round(float(prior["amount"].sum()), 2)
        m["revenue_90d"] = round(float(window90["amount"].sum()), 2)
        m["txns_30d"] = int(len(recent))
        m["txns_prev30d"] = int(len(prior))
        m["avg_order_value"] = round(float(sdf["amount"].mean()), 2)
        m["sales_points"] = int(len(sdf))

        # Use transaction-count delta when revenue volume is thin, so a single
        # large order cannot be read as a trend.
        rev_delta = _pct_change(m["revenue_30d"], m["revenue_prev30d"])
        txn_delta = _pct_change(float(m["txns_30d"]), float(m["txns_prev30d"]))
        m["revenue_delta_pct"] = _round(rev_delta)
        m["txn_delta_pct"] = _round(txn_delta)

        last_sale = sdf["date"].max()
        m["days_since_last_sale"] = int((pd.Timestamp(ref) - last_sale).days)

    # ---------------- usage ------------------------------------------------
    usage = frames["usage"]
    udf = usage[usage["customer_id"] == cid] if not usage.empty else usage
    if not udf.empty:
        cutoff_recent = pd.Timestamp(ref) - pd.Timedelta(days=USAGE_RECENT_WINDOW)
        cutoff_prior = pd.Timestamp(ref) - pd.Timedelta(days=USAGE_RECENT_WINDOW + USAGE_PRIOR_WINDOW)
        urecent = udf[udf["date"] > cutoff_recent]
        uprior = udf[(udf["date"] > cutoff_prior) & (udf["date"] <= cutoff_recent)]

        m["usage_points"] = int(len(udf))
        if not urecent.empty:
            m["usage_avg_14d"] = round(float(urecent["active_users"].mean()), 1)
            m["usage_minutes_avg_14d"] = round(float(urecent["usage_minutes"].mean()), 1)
            m["sessions_avg_14d"] = round(float(urecent["sessions"].mean()), 1)
        if not uprior.empty:
            m["usage_prev14d"] = round(float(uprior["active_users"].mean()), 1)
        m["usage_delta_pct"] = _round(
            _pct_change(m["usage_avg_14d"], m["usage_prev14d"])
        )
        last_usage = udf["date"].max()
        m["days_since_last_usage"] = int((pd.Timestamp(ref) - last_usage).days)

    # ---------------- support ---------------------------------------------
    tickets = frames["tickets"]
    tdf = tickets[tickets["customer_id"] == cid] if not tickets.empty else tickets
    if not tdf.empty:
        open_df = tdf[tdf["status"].isin(["open", "in_progress"])]
        m["open_tickets"] = int(len(open_df))
        m["critical_open"] = int((open_df["severity"] == "critical").sum())
        m["high_open"] = int((open_df["severity"] == "high").sum())
        m["medium_open"] = int((open_df["severity"] == "medium").sum())
        m["resolved_tickets"] = int((tdf["status"] == "resolved").sum())
        if not open_df.empty:
            ages = (pd.Timestamp(ref) - open_df["created_at"]).dt.days.clip(lower=0)
            m["oldest_open_days"] = int(ages.max())
            m["avg_open_age_days"] = round(float(ages.mean()), 1)

    # ---------------- notes (deterministic rule scan) ----------------------
    notes = frames["notes"]
    ndf = notes[notes["customer_id"] == cid] if not notes.empty else notes
    if not ndf.empty:
        m["notes_count"] = int(len(ndf))
        risk_hits = positive_hits = risk_types = 0
        for _, note in ndf.iterrows():
            text = str(note["note_text"]).lower()
            if str(note["note_type"]).lower() in RISK_NOTE_TYPES:
                risk_types += 1
            if any(k in text for k in RISK_KEYWORDS):
                risk_hits += 1
            if any(k in text for k in POSITIVE_KEYWORDS):
                positive_hits += 1
        m["note_risk_hits"] = risk_hits
        m["note_positive_hits"] = positive_hits
        m["note_risk_types"] = risk_types

    # ---------------- data completeness ------------------------------------
    expected_sales_points = max(1, int(m["history_days"] / 7 * 2))
    sales_cov = min(1.0, m["sales_points"] / expected_sales_points) if m["sales_points"] else 0.0
    usage_cov = 1.0 if m["usage_points"] >= 20 else m["usage_points"] / 20.0
    ticket_cov = 1.0 if (m["open_tickets"] + m["resolved_tickets"]) > 0 else 0.5
    notes_cov = min(1.0, m["notes_count"] / 2.0)
    history_cov = min(1.0, m["history_days"] / 90.0)
    m["data_completeness"] = round(
        (sales_cov * 0.3 + usage_cov * 0.25 + ticket_cov * 0.1 + notes_cov * 0.1 + history_cov * 0.25), 4
    )

    return m


def compute_customer_metrics(
    frames: dict[str, pd.DataFrame], customer_id: str, ref: dt.date
) -> dict[str, Any] | None:
    customers = frames["customers"]
    match = customers[customers["customer_id"] == customer_id]
    if match.empty:
        return None
    m = _compute_one(frames, match.iloc[0], ref)
    total = sum(
        _compute_one(frames, r, ref)["revenue_90d"]
        for _, r in customers.iterrows()
    )
    m["revenue_share_pct"] = round(m["revenue_90d"] / total * 100.0, 2) if total > 0 else 0.0
    return m
