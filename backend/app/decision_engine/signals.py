"""Deterministic signal layer.

Six weighted signals are computed from the analytics bundle. Each one returns a
fully-formed explanation whose text is *generated from the computed number* —
never written by a language model. That is what makes the evidence trace
auditable: change the data and the reason sentence changes with it.

Signal table (max points sum to 100)
------------------------------------
sales_decline        22   revenue + order-count movement, 30d vs prior 30d
usage_decline        24   active-user movement, 14d vs prior 14d
support_severity     20   open ticket severity + age of the oldest open ticket
engagement_recency   12   days since last sale / last observed usage
revenue_materiality  12   share of book revenue and absolute account value
narrative_risk       10   rule-scanned risk language in business notes

Positive / neutral signals (growth, clean support queue, positive notes) are
reported alongside with 0 points so the UI can show what is *not* a problem.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CADENCE_DAYS = 14


@dataclass
class Signal:
    key: str
    label: str
    value: float
    unit: str
    direction: str  # risk | positive | neutral
    level: str  # critical | high | moderate | low | none
    points: float
    weight_max: float
    reason: str
    has_data: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value": round(self.value, 2),
            "unit": self.unit,
            "direction": self.direction,
            "level": self.level,
            "points": round(self.points, 2),
            "weight_max": self.weight_max,
            "reason": self.reason,
            "has_data": self.has_data,
        }


WEIGHTS = {
    "sales_decline": 22.0,
    "usage_decline": 24.0,
    "support_severity": 20.0,
    "engagement_recency": 12.0,
    "revenue_materiality": 12.0,
    "narrative_risk": 10.0,
}


def _level(severity: float) -> str:
    if severity >= 0.75:
        return "critical"
    if severity >= 0.5:
        return "high"
    if severity >= 0.25:
        return "moderate"
    if severity > 0.0:
        return "low"
    return "none"


def _money(value: float) -> str:
    return f"${value:,.0f}"


# ---------------------------------------------------------------------------
# Individual signals
# ---------------------------------------------------------------------------
def sales_decline_signal(m: dict[str, Any]) -> Signal:
    w = WEIGHTS["sales_decline"]
    delta = m.get("revenue_delta_pct")
    if delta is None or m.get("sales_points", 0) == 0:
        return Signal(
            "sales_decline", "Sales & revenue momentum", 0.0, "pct", "neutral", "none", 0.0, w,
            "No sales history is recorded for this account in the analysed window, so revenue momentum cannot be assessed.",
            has_data=False,
        )

    severity = min(1.0, max(0.0, -delta / 40.0))
    # order-count corroboration: a revenue drop with a flat order count is more
    # likely deal-mix than disengagement, so temper it slightly and vice versa.
    txn_delta = m.get("txn_delta_pct")
    if txn_delta is not None:
        if txn_delta <= -25 and delta <= -15:
            severity = min(1.0, severity * 1.15)
        elif txn_delta >= 0 > delta:
            severity *= 0.8
    points = round(severity * w, 2)

    if delta < 0:
        direction, level = "risk", _level(severity)
        sentence = (
            f"Revenue over the last 30 days is {_money(m['revenue_30d'])} from {m['txns_30d']} orders, "
            f"down {abs(delta):.1f}% versus {_money(m['revenue_prev30d'])} from {m['txns_prev30d']} orders in the "
            f"previous 30 days."
        )
        if txn_delta is not None:
            sentence += f" Order volume moved {txn_delta:+.1f}%."
        sentence += f" Lifetime 90-day revenue is {_money(m['revenue_90d'])}."
    else:
        direction, level = "positive", "none"
        sentence = (
            f"Revenue over the last 30 days is {_money(m['revenue_30d'])} ({delta:+.1f}% versus the previous 30 days) "
            f"from {m['txns_30d']} orders — commercial momentum is holding or improving."
        )

    return Signal("sales_decline", "Sales & revenue momentum", round(delta, 1), "pct", direction, level, points, w, sentence)


def usage_decline_signal(m: dict[str, Any]) -> Signal:
    w = WEIGHTS["usage_decline"]
    delta = m.get("usage_delta_pct")
    if delta is None or m.get("usage_points", 0) < 4:
        return Signal(
            "usage_decline", "Product usage trend", 0.0, "pct", "neutral", "none", 0.0, w,
            "Not enough product-telemetry history exists to establish a usage trend for this account.",
            has_data=False,
        )

    severity = min(1.0, max(0.0, -delta / 35.0))
    points = round(severity * w, 2)

    if delta < 0:
        direction, level = "risk", _level(severity)
        sentence = (
            f"Average daily active users fell to {m['usage_avg_14d']:.1f} over the last 14 days from "
            f"{m['usage_prev14d']:.1f} in the previous 14 days, a decline of {abs(delta):.1f}%. "
            f"Averaging {m['sessions_avg_14d']:.1f} sessions and {m['usage_minutes_avg_14d']:.0f} usage-minutes per active day."
        )
    else:
        direction, level = "positive", "none"
        sentence = (
            f"Average daily active users is {m['usage_avg_14d']:.1f} over the last 14 days versus "
            f"{m['usage_prev14d']:.1f} previously ({delta:+.1f}%) — adoption is stable or growing."
        )

    return Signal("usage_decline", "Product usage trend", round(delta, 1), "pct", direction, level, points, w, sentence)


def support_severity_signal(m: dict[str, Any]) -> Signal:
    w = WEIGHTS["support_severity"]
    open_tickets = int(m.get("open_tickets", 0))
    critical = int(m.get("critical_open", 0))
    high = int(m.get("high_open", 0))
    medium = int(m.get("medium_open", 0))
    oldest = int(m.get("oldest_open_days", 0))

    severity = min(1.0, (critical * 1.0 + high * 0.55 + medium * 0.25) / 2.0)
    # tickets open beyond a month escalate
    if oldest > 30 and open_tickets:
        severity = min(1.0, severity + 0.15)
    points = round(severity * w, 2)

    if open_tickets == 0:
        return Signal(
            "support_severity", "Support issue pressure", 0.0, "tickets", "positive", "none", 0.0, w,
            f"No open support tickets. {int(m.get('resolved_tickets', 0))} ticket(s) are already resolved, "
            f"so there is no unresolved service debt on this account.",
        )

    direction, level = "risk", _level(severity)
    parts = []
    if critical:
        parts.append(f"{critical} critical")
    if high:
        parts.append(f"{high} high")
    if medium:
        parts.append(f"{medium} medium")
    sentence = (
        f"{open_tickets} open support ticket(s) ({', '.join(parts) if parts else 'no severity recorded'}). "
        f"The oldest has been open for {oldest} days"
    )
    if oldest > 30:
        sentence += ", which is beyond a typical monthly service-level target"
    sentence += f". {int(m.get('resolved_tickets', 0))} ticket(s) have been resolved."
    return Signal("support_severity", "Support issue pressure", open_tickets, "tickets", direction, level, points, w, sentence)


def engagement_recency_signal(m: dict[str, Any], run_rate_days: int = CADENCE_DAYS) -> Signal:
    w = WEIGHTS["engagement_recency"]
    since_usage = m.get("days_since_last_usage")
    since_sale = m.get("days_since_last_sale")
    observed = [d for d in (since_usage, since_sale) if d is not None]
    if not observed:
        return Signal(
            "engagement_recency", "Engagement recency", 0.0, "days", "neutral", "none", 0.0, w,
            "No dated activity is available for this account, so recency of engagement cannot be measured.",
            has_data=False,
        )

    worst = max(observed)
    severity = min(1.0, max(0.0, (worst - run_rate_days) / 21.0))
    points = round(severity * w, 2)

    bits = []
    if since_usage is not None:
        bits.append(f"last product usage {since_usage} day(s) ago")
    if since_sale is not None:
        bits.append(f"last sale {since_sale} day(s) ago")
    detail = " and ".join(bits)

    if severity > 0.15:
        direction, level = "risk", _level(severity)
        sentence = f"Engagement is stalling: {detail}, against an expected interaction cadence of roughly {run_rate_days} days."
    else:
        direction, level = "positive", "none"
        sentence = f"Engagement is current: {detail}, in line with the expected {run_rate_days}-day cadence."

    return Signal("engagement_recency", "Engagement recency", float(worst), "days", direction, level, points, w, sentence)


def revenue_materiality_signal(m: dict[str, Any], book_rank_pct: float = 0.0) -> Signal:
    """Commercial consequence if this account is lost."""
    w = WEIGHTS["revenue_materiality"]
    share = float(m.get("revenue_share_pct", 0.0))
    value = float(m.get("account_value", 0.0))

    share_component = min(1.0, share / 12.0)
    value_component = min(1.0, value / 500_000.0)
    severity = max(share_component, value_component * 0.85)
    if book_rank_pct and book_rank_pct >= 0.75:
        severity = min(1.0, severity + 0.1)
    points = round(severity * w, 2)

    if severity >= 0.25:
        direction, level = "risk", _level(severity)
        sentence = (
            f"Commercially material account: {share:.2f}% of analysed book revenue over 90 days "
            f"({_money(m.get('revenue_90d', 0.0))}) on a contracted value of {_money(value)}. "
            f"Loss or contraction would be material."
        )
    else:
        direction, level = "neutral", "none"
        sentence = (
            f"Small commercial footprint: {share:.2f}% of analysed book revenue ({_money(m.get('revenue_90d', 0.0))}) "
            f"on a contracted value of {_money(value)}. Risk here is contained."
        )

    return Signal("revenue_materiality", "Revenue materiality", round(share, 2), "pct", direction, level, points, w, sentence)


def narrative_risk_signal(m: dict[str, Any]) -> Signal:
    w = WEIGHTS["narrative_risk"]
    notes = int(m.get("notes_count", 0))
    risk_hits = int(m.get("note_risk_hits", 0))
    risk_types = int(m.get("note_risk_types", 0))
    positive_hits = int(m.get("note_positive_hits", 0))

    if notes == 0:
        return Signal(
            "narrative_risk", "Account narrative risk", 0.0, "notes", "neutral", "none", 0.0, w,
            "No business notes or call records exist for this account, so qualitative risk cannot be assessed.",
            has_data=False,
        )

    ratio = risk_hits / notes
    severity = min(1.0, ratio * 0.75 + (risk_types / notes) * 0.25)
    points = round(severity * w, 2)

    if risk_hits:
        direction, level = "risk", _level(max(severity, 0.3))
        sentence = (
            f"{risk_hits} of {notes} business note(s) contain explicit risk language "
            f"({risk_types} logged as risk/escalation type). "
            f"Scanned language includes renewal doubt, competitor evaluation or unresolved escalation. "
            f"{positive_hits} note(s) contain offsetting positive language."
        )
    elif positive_hits:
        direction, level = "positive", "none"
        sentence = (
            f"{positive_hits} of {notes} business note(s) contain positive language "
            f"(reference calls, expansion intent, confirmed seasonality) and none contain risk language."
        )
    else:
        direction, level = "neutral", "none"
        sentence = f"{notes} business note(s) exist but none contain explicit risk or positive signals."

    return Signal("narrative_risk", "Account narrative risk", float(risk_hits), "notes", direction, level, points, w, sentence)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def compute_signals(m: dict[str, Any], book_rank_pct: float = 0.0) -> list[Signal]:
    return [
        sales_decline_signal(m),
        usage_decline_signal(m),
        support_severity_signal(m),
        engagement_recency_signal(m),
        revenue_materiality_signal(m, book_rank_pct),
        narrative_risk_signal(m),
    ]


def score_signals(signals: list[Signal]) -> tuple[float, list[Signal]]:
    """Sum the weighted points, then re-normalise over the signals that have data.

    Re-normalising matters: an account with no telemetry should not be pushed
    to LOW simply because three signals were unmeasurable — but its
    *confidence* must drop. That is handled separately by ``compute_confidence``.
    """
    detectable = sum(s.weight_max for s in signals if s.has_data)
    raw = sum(s.points for s in signals)
    if detectable <= 0:
        return 0.0, signals
    # scale to a comparable 0-100 space
    score = raw * (100.0 / detectable) if detectable < 100.0 else raw
    return round(min(100.0, max(0.0, score)), 2), signals


def positive_signals(signals: list[Signal]) -> list[Signal]:
    return [s for s in signals if s.direction == "positive"]


def top_risk_signals(signals: list[Signal], limit: int = 3) -> list[Signal]:
    risks = [s for s in signals if s.direction == "risk" and s.points > 0]
    risks.sort(key=lambda s: s.points, reverse=True)
    return risks[:limit]
