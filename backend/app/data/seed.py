"""Synthetic data generator for DeciTrace AI.

100% synthetic and public-safe — no real people, companies or accounts.
Company names are invented; every numeric value is drawn from a seeded RNG so
runs are reproducible.

Each customer is generated from an *archetype* which acts as the ground truth
for the evaluation harness (``archetype`` column on ``customers``).

Usage
-----
    python -m app.data.seed                # reset + seed
    python -m app.data.seed --keep         # seed only if empty
    python -m app.data.seed --customers 40
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
from pathlib import Path

from ..config import settings
from .db import Base, engine, session_scope
from .models import BusinessNote, Customer, Sale, SupportTicket, UsageRecord

SEED = 20260926

# ---------------------------------------------------------------------------
# Taxonomy of the synthetic world
# ---------------------------------------------------------------------------
INDUSTRIES = [
    "Manufacturing",
    "Retail & E-Commerce",
    "Logistics",
    "Financial Services",
    "Healthcare",
    "SaaS & Technology",
    "Energy & Utilities",
]
REGIONS = ["North America", "EMEA", "APAC", "LATAM"]
SEGMENTS = ["Enterprise", "Mid-Market", "SMB"]
PRODUCTS = [
    "DeciTrace Analytics Cloud",
    "Warehouse Sync",
    "Forecast Suite",
    "Automation Studio",
    "Support Desk Pro",
]
CHANNELS = ["direct", "partner", "self-serve"]

NAME_A = [
    "ACME", "Northwind", "Vertex", "Lumina", "Ironclad", "Blue Harbor", "Cobalt",
    "Everline", "Kestrel", "Solstice", "Aurora", "Pinnacle", "Ridgeway", "Helios",
    "Quanta", "Meridian", "Cardinal", "Stonebridge", "Novaris", "Fairwind",
    "Granite", "Larkspur", "Onyx", "Redwood", "Summit", "Tidewater", "Upland",
    "Vantage", "Westbrook", "Zenith", "Arbor", "Bellwether",
]
NAME_B = [
    "Corp", "Industries", "Logistics", "Holdings", "Systems", "Group", "Labs",
    "Partners", "Retail", "Manufacturing", "Health", "Energy", "Technologies",
]

# Archetype -> business behaviour. This is the deterministic "ground truth".
ARCHETYPES: dict[str, dict] = {
    # steady, healthy account
    "healthy": {"weight": 7, "sales": 1.00, "sales_recent": 1.05, "usage": 1.00,
                "usage_recent": 1.02, "tickets": [], "expected_priority": "LOW"},
    "growth": {"weight": 4, "sales": 0.85, "sales_recent": 1.30, "usage": 0.85,
               "usage_recent": 1.22, "tickets": [], "expected_priority": "LOW"},
    # full multi-signal churn risk: revenue + usage + open critical ticket
    "churn_risk": {"weight": 5, "sales": 1.00, "sales_recent": 0.52, "usage": 1.00,
                   "usage_recent": 0.62, "tickets": [("critical", "open", 26),
                                                      ("high", "open", 9)],
                   "expected_priority": "HIGH"},
    # silent churn: champion left, usage collapses, no loud support signal
    "silent_churn": {"weight": 3, "sales": 1.00, "sales_recent": 0.68, "usage": 1.00,
                     "usage_recent": 0.48, "tickets": [("medium", "resolved", 34)],
                     "expected_priority": "HIGH"},
    # usage-led decline, revenue still roughly holding
    "declining_usage": {"weight": 4, "sales": 1.00, "sales_recent": 0.88, "usage": 1.00,
                        "usage_recent": 0.55, "tickets": [("medium", "open", 12)],
                        "expected_priority": "MEDIUM"},
    # loud support escalation, commercial metrics unaffected
    "support_escalation": {"weight": 3, "sales": 1.00, "sales_recent": 0.97, "usage": 1.00,
                           "usage_recent": 0.96,
                           "tickets": [("critical", "open", 41),
                                       ("critical", "open", 18),
                                       ("high", "open", 7)],
                           "expected_priority": "MEDIUM"},
    # ambiguous: revenue dip that is plausibly seasonal, no other signal
    "seasonal_dip": {"weight": 3, "sales": 1.00, "sales_recent": 0.70, "usage": 1.00,
                     "usage_recent": 0.99, "tickets": [], "expected_priority": "LOW"},
    # brand new account: not enough history to decide
    "new_customer": {"weight": 3, "sales": 1.00, "sales_recent": 1.00, "usage": 1.00,
                     "usage_recent": 1.00, "tickets": [], "expected_priority": "LOW",
                     "history_days": 24},
    # small account, mild decline, low materiality
    "low_value": {"weight": 4, "sales": 1.00, "sales_recent": 0.80, "usage": 1.00,
                  "usage_recent": 0.94, "tickets": [], "expected_priority": "LOW"},
}

NOTE_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "healthy": [
        ("account_review", "Quarterly review went well. Adoption is steady and the account team set a follow-up on expansion into two new departments."),
        ("qbr", "Customer described the platform as critical infrastructure for their planning cycle."),
    ],
    "growth": [
        ("expansion", "Customer requested pricing for 200 additional seats after a successful pilot in the retail division."),
        ("meeting", "Champion confirmed budget approval for phase two of the rollout."),
    ],
    "churn_risk": [
        ("escalation", "Customer reported recurring sync failures during month-end close. They stated they are evaluating two competitors because of the downtime."),
        ("risk", "Finance contact flagged that they may not renew unless the open critical ticket is resolved before the contract anniversary."),
    ],
    "silent_churn": [
        ("risk", "Primary champion left the company in the last quarter. No replacement sponsor identified and login activity has dropped sharply."),
        ("meeting", "New stakeholder attended a call but did not commit to an internal rollout plan."),
    ],
    "declining_usage": [
        ("account_review", "Daily active users fell noticeably after the workflow migration. Users report the new automation step is slower than before."),
        ("onboarding", "Only two of the five purchased modules are actively used. Enablement session was rescheduled twice."),
    ],
    "support_escalation": [
        ("escalation", "Customer escalated to their executive sponsor over API latency during peak hours. They requested a written remediation plan."),
        ("support", "Two critical tickets remain open beyond the contractual service level target."),
    ],
    "seasonal_dip": [
        ("account_review", "Customer confirmed the Q3 slowdown is seasonal and consistent with their budget cycle. No churn indicators observed."),
        ("meeting", "Procurement cycle pushes spend into the next quarter as in previous years."),
    ],
    "new_customer": [
        ("onboarding", "Kickoff completed. Implementation is in progress and no billing history exists yet."),
    ],
    "low_value": [
        ("account_review", "Account is stable but small. Renewal is not due for several months."),
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _poisson(rng: random.Random, lam: float) -> int:
    """Small, dependency-free Poisson sampler (Knuth)."""
    if lam <= 0:
        return 0
    import math

    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1
        if k > 60:
            return k


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _plan_customers(total: int, rng: random.Random) -> list[str]:
    """Return a list of archetype keys with the requested distribution."""
    keys = list(ARCHETYPES)
    weights = [ARCHETYPES[k]["weight"] for k in keys]
    plan = rng.choices(keys, weights=weights, k=total)
    # Guarantee at least one of every archetype so the evaluation harness is
    # always able to build its five case types.
    for i, key in enumerate(keys):
        if i < total:
            plan[i] = key
    rng.shuffle(plan)
    return plan


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------
def generate(total_customers: int = 28, reference_date: dt.date | None = None) -> dict:
    """Build every synthetic dataset and return a manifest dict."""
    rng = random.Random(SEED)
    today = reference_date or dt.date.today()
    history_weeks = 26  # ~6 months

    archetypes = _plan_customers(total_customers, rng)
    used_names: set[str] = set()

    customers: list[Customer] = []
    sales: list[Sale] = []
    usage: list[UsageRecord] = []
    tickets: list[SupportTicket] = []
    notes: list[BusinessNote] = []
    manifest: list[dict] = []

    for idx, archetype in enumerate(archetypes, start=1):
        spec = ARCHETYPES[archetype]
        cid = f"C{idx:03d}"

        # --- name -------------------------------------------------------
        while True:
            name = f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}"
            if name not in used_names:
                used_names.add(name)
                break

        segment = rng.choices(SEGMENTS, weights=[3, 5, 3])[0]
        if segment == "Enterprise":
            base_value = rng.uniform(220_000, 900_000)
        elif segment == "Mid-Market":
            base_value = rng.uniform(60_000, 220_000)
        else:
            base_value = rng.uniform(12_000, 60_000)
        if archetype == "low_value":
            base_value = rng.uniform(9_000, 26_000)
        if archetype == "growth":
            base_value = base_value * 1.15

        history_days = int(spec.get("history_days", history_weeks * 7))
        onboarded = today - dt.timedelta(days=history_days + rng.randint(30, 700))

        status = "active"
        if archetype in {"churn_risk", "silent_churn"}:
            status = rng.choice(["at_risk", "active"])
        elif archetype == "new_customer":
            status = "onboarding"

        customers.append(
            Customer(
                customer_id=cid,
                customer_name=name,
                industry=rng.choice(INDUSTRIES),
                region=rng.choices(REGIONS, weights=[4, 3, 3, 1])[0],
                segment=segment,
                account_value=round(base_value, 2),
                owner=f"AE-{rng.randint(1, 8):02d}",
                status=status,
                onboarded_on=onboarded,
                archetype=archetype,
            )
        )

        # --- sales ------------------------------------------------------
        txn = 0
        base_txns_per_week = _clamp(base_value / 42_000, 0.6, 5.2)
        avg_order = _clamp(base_value / 26, 900, 42_000)
        weeks = max(4, int(history_days // 7))
        for w in range(weeks, -1, -1):
            is_recent = w < 4
            factor = spec["sales_recent"] if is_recent else spec["sales"]
            # gentle noise so the trend is realistic, not a staircase
            factor *= rng.uniform(0.82, 1.18)
            count = _poisson(rng, base_txns_per_week * factor)
            for _ in range(count):
                day = today - dt.timedelta(days=w * 7 + rng.randint(0, 6))
                if day > today or day < onboarded:
                    continue
                txn += 1
                sales.append(
                    Sale(
                        transaction_id=f"TX{cid[1:]}-{txn:04d}",
                        customer_id=cid,
                        date=day,
                        amount=round(avg_order * rng.uniform(0.55, 1.75), 2),
                        product=rng.choice(PRODUCTS),
                        quantity=rng.randint(1, 12),
                        channel=rng.choice(CHANNELS),
                    )
                )

        # --- usage ------------------------------------------------------
        base_users = max(3, int(base_value / 5_200))
        for w in range(weeks, -1, -1):
            is_recent = w < 2
            factor = spec["usage_recent"] if is_recent else spec["usage"]
            factor *= rng.uniform(0.9, 1.1)
            for offset in range(0, 7, 2):
                day = today - dt.timedelta(days=w * 7 + offset)
                if day > today:
                    continue
                dow = day.weekday()
                weekday_factor = 0.35 if dow >= 5 else 1.0
                users = max(0, int(base_users * factor * weekday_factor * rng.uniform(0.75, 1.25)))
                usage.append(
                    UsageRecord(
                        customer_id=cid,
                        date=day,
                        active_users=users,
                        sessions=int(users * rng.uniform(1.1, 2.6)),
                        usage_minutes=int(users * rng.uniform(18, 62)),
                    )
                )

        # --- support tickets -------------------------------------------
        for t_i, (severity, t_status, days_ago) in enumerate(spec["tickets"], start=1):
            created = today - dt.timedelta(days=days_ago)
            if created < onboarded:
                created = onboarded
            resolved = None
            if t_status == "resolved":
                resolved = created + dt.timedelta(days=rng.randint(3, 20))
                if resolved > today:
                    resolved = today
            issue = {
                "critical": rng.choice([
                    "Month-end sync failure blocks finance close",
                    "API latency spike causes checkout timeouts",
                    "Data pipeline outage during peak hours",
                ]),
                "high": rng.choice([
                    "Recurring integration errors with ERP connector",
                    "Report exports timing out for large datasets",
                    "SSO login failures for a subset of users",
                ]),
                "medium": rng.choice([
                    "Automation step runs slower than expected",
                    "Dashboard filters return inconsistent totals",
                    "Notification emails delayed by several hours",
                ]),
                "low": rng.choice(["Cosmetic label issue", "Documentation request"]),
            }[severity]
            tickets.append(
                SupportTicket(
                    ticket_id=f"T{idx:03d}{t_i}",
                    customer_id=cid,
                    issue=issue,
                    description=(
                        f"{issue}. Reported by the customer's operations team. "
                        f"Severity {severity}; current status {t_status.replace('_', ' ')}. "
                        f"Business impact: {'revenue-critical workflow' if severity == 'critical' else 'operational disruption'}."
                    ),
                    severity=severity,
                    status=t_status,
                    created_at=created,
                    resolved_at=resolved,
                    assignee=rng.choice(["Tier-3 Support", "Solutions Engineering", "Support Queue"]),
                )
            )

        # --- business notes --------------------------------------------
        for n_i, (note_type, text) in enumerate(NOTE_TEMPLATES[archetype], start=1):
            day = today - dt.timedelta(days=rng.randint(2, min(45, max(3, history_days))))
            notes.append(
                BusinessNote(
                    note_id=f"N{idx:03d}{n_i}",
                    customer_id=cid,
                    note_text=text,
                    author_role=rng.choice(
                        ["Account Manager", "Customer Success Manager", "Support Lead", "Sales Director"]
                    ),
                    note_type=note_type,
                    date=day,
                )
            )

        manifest.append(
            {
                "customer_id": cid,
                "customer_name": name,
                "archetype": archetype,
                "expected_priority": spec["expected_priority"],
                "account_value": round(base_value, 2),
                "segment": segment,
            }
        )

    return {
        "reference_date": today.isoformat(),
        "generated_at": dt.datetime.utcnow().isoformat(),
        "seed": SEED,
        "counts": {
            "customers": len(customers),
            "sales": len(sales),
            "usage": len(usage),
            "support_tickets": len(tickets),
            "business_notes": len(notes),
        },
        "customers": manifest,
    }


def reset_database() -> None:
    """Drop and recreate every table."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_database(total_customers: int = 28, reset: bool = True) -> dict:
    """Write the generated world into the database. Returns the manifest."""
    if reset:
        reset_database()
    else:
        Base.metadata.create_all(bind=engine)

    data = generate(total_customers=total_customers)

    # Re-generate the ORM objects so we can persist them.
    bundle = _build_orm(total_customers)
    with session_scope() as db:
        db.add_all(bundle["customers"])
        db.flush()
        db.add_all(bundle["sales"])
        db.add_all(bundle["usage"])
        db.add_all(bundle["tickets"])
        db.add_all(bundle["notes"])

    manifest_path = Path(settings.DATA_DIR) / "seed_manifest.json"
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    data["manifest_path"] = str(manifest_path)
    return data


def _build_orm(total_customers: int) -> dict:
    """Run the generator and return raw ORM objects instead of a manifest."""
    # The generator is pure; reuse it by intercepting the returned manifest.
    # Simplest robust approach: regenerate with the same seed and rebuild.
    rng = random.Random(SEED)
    today = dt.date.today()
    history_weeks = 26
    archetypes = _plan_customers(total_customers, rng)
    used_names: set[str] = set()

    objs = {"customers": [], "sales": [], "usage": [], "tickets": [], "notes": []}

    for idx, archetype in enumerate(archetypes, start=1):
        spec = ARCHETYPES[archetype]
        cid = f"C{idx:03d}"
        while True:
            name = f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}"
            if name not in used_names:
                used_names.add(name)
                break

        segment = rng.choices(SEGMENTS, weights=[3, 5, 3])[0]
        if segment == "Enterprise":
            base_value = rng.uniform(220_000, 900_000)
        elif segment == "Mid-Market":
            base_value = rng.uniform(60_000, 220_000)
        else:
            base_value = rng.uniform(12_000, 60_000)
        if archetype == "low_value":
            base_value = rng.uniform(9_000, 26_000)
        if archetype == "growth":
            base_value = base_value * 1.15

        history_days = int(spec.get("history_days", history_weeks * 7))
        onboarded = today - dt.timedelta(days=history_days + rng.randint(30, 700))
        status = "active"
        if archetype in {"churn_risk", "silent_churn"}:
            status = rng.choice(["at_risk", "active"])
        elif archetype == "new_customer":
            status = "onboarding"

        objs["customers"].append(
            Customer(
                customer_id=cid,
                customer_name=name,
                industry=rng.choice(INDUSTRIES),
                region=rng.choices(REGIONS, weights=[4, 3, 3, 1])[0],
                segment=segment,
                account_value=round(base_value, 2),
                owner=f"AE-{rng.randint(1, 8):02d}",
                status=status,
                onboarded_on=onboarded,
                archetype=archetype,
            )
        )

        # sales
        txn = 0
        base_txns_per_week = _clamp(base_value / 42_000, 0.6, 5.2)
        avg_order = _clamp(base_value / 26, 900, 42_000)
        weeks = max(4, int(history_days // 7))
        for w in range(weeks, -1, -1):
            factor = spec["sales_recent"] if w < 4 else spec["sales"]
            factor *= rng.uniform(0.82, 1.18)
            for _ in range(_poisson(rng, base_txns_per_week * factor)):
                day = today - dt.timedelta(days=w * 7 + rng.randint(0, 6))
                if day > today or day < onboarded:
                    continue
                txn += 1
                objs["sales"].append(
                    Sale(
                        transaction_id=f"TX{cid[1:]}-{txn:04d}",
                        customer_id=cid,
                        date=day,
                        amount=round(avg_order * rng.uniform(0.55, 1.75), 2),
                        product=rng.choice(PRODUCTS),
                        quantity=rng.randint(1, 12),
                        channel=rng.choice(CHANNELS),
                    )
                )

        # usage
        base_users = max(3, int(base_value / 5_200))
        for w in range(weeks, -1, -1):
            factor = spec["usage_recent"] if w < 2 else spec["usage"]
            factor *= rng.uniform(0.9, 1.1)
            for offset in range(0, 7, 2):
                day = today - dt.timedelta(days=w * 7 + offset)
                if day > today:
                    continue
                weekday_factor = 0.35 if day.weekday() >= 5 else 1.0
                users = max(0, int(base_users * factor * weekday_factor * rng.uniform(0.75, 1.25)))
                objs["usage"].append(
                    UsageRecord(
                        customer_id=cid,
                        date=day,
                        active_users=users,
                        sessions=int(users * rng.uniform(1.1, 2.6)),
                        usage_minutes=int(users * rng.uniform(18, 62)),
                    )
                )

        # tickets
        for t_i, (severity, t_status, days_ago) in enumerate(spec["tickets"], start=1):
            created = max(onboarded, today - dt.timedelta(days=days_ago))
            resolved = None
            if t_status == "resolved":
                resolved = min(today, created + dt.timedelta(days=rng.randint(3, 20)))
            issue = {
                "critical": rng.choice([
                    "Month-end sync failure blocks finance close",
                    "API latency spike causes checkout timeouts",
                    "Data pipeline outage during peak hours",
                ]),
                "high": rng.choice([
                    "Recurring integration errors with ERP connector",
                    "Report exports timing out for large datasets",
                    "SSO login failures for a subset of users",
                ]),
                "medium": rng.choice([
                    "Automation step runs slower than expected",
                    "Dashboard filters return inconsistent totals",
                    "Notification emails delayed by several hours",
                ]),
                "low": rng.choice(["Cosmetic label issue", "Documentation request"]),
            }[severity]
            objs["tickets"].append(
                SupportTicket(
                    ticket_id=f"T{idx:03d}{t_i}",
                    customer_id=cid,
                    issue=issue,
                    description=(
                        f"{issue}. Reported by the customer's operations team. "
                        f"Severity {severity}; current status {t_status.replace('_', ' ')}. "
                        f"Business impact: {'revenue-critical workflow' if severity == 'critical' else 'operational disruption'}."
                    ),
                    severity=severity,
                    status=t_status,
                    created_at=created,
                    resolved_at=resolved,
                    assignee=rng.choice(["Tier-3 Support", "Solutions Engineering", "Support Queue"]),
                )
            )

        # notes
        for n_i, (note_type, text) in enumerate(NOTE_TEMPLATES[archetype], start=1):
            day = today - dt.timedelta(days=rng.randint(2, min(45, max(3, history_days))))
            objs["notes"].append(
                BusinessNote(
                    note_id=f"N{idx:03d}{n_i}",
                    customer_id=cid,
                    note_text=text,
                    author_role=rng.choice(
                        ["Account Manager", "Customer Success Manager", "Support Lead", "Sales Director"]
                    ),
                    note_type=note_type,
                    date=day,
                )
            )

    return objs


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed DeciTrace AI with synthetic business data.")
    parser.add_argument("--customers", type=int, default=28, help="number of customers to generate")
    parser.add_argument("--keep", action="store_true", help="do not drop existing tables")
    args = parser.parse_args()

    data = seed_database(total_customers=args.customers, reset=not args.keep)
    print("DeciTrace AI — synthetic data seeded")
    print(f"  reference date : {data['reference_date']}")
    for key, value in data["counts"].items():
        print(f"  {key:<16}: {value}")
    print(f"  manifest       : {data['manifest_path']}")


if __name__ == "__main__":
    main()
