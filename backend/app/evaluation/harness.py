"""Evaluation harness.

Five synthetic case types are built from the seeded ground-truth archetypes,
then actually executed through the real decision pipeline. Every metric below
is *measured* — nothing is asserted. If the harness has never run, the API
returns ``status = "Evaluation pending"`` with no metrics at all.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..analytics.metrics import compute_all_metrics, load_frames, reference_date
from ..config import settings
from ..data.models import Customer, EvaluationRun
from ..decision_engine.engine import score_customer
from ..rag.retriever import get_index

CASE_TYPES = [
    "normal",
    "high_risk",
    "multi_signal",
    "ambiguous",
    "insufficient_evidence",
]

CASE_TYPE_LABELS = {
    "normal": "Normal case — healthy account, no intervention expected",
    "high_risk": "High-risk case — clear churn risk, must be escalated",
    "multi_signal": "Multi-signal case — several independent risk signals aligned",
    "ambiguous": "Ambiguous case — a single dip that is plausibly seasonal",
    "insufficient_evidence": "Insufficient-evidence case — new account, thin history",
}

# archetype -> case type
ARCHETYPE_CASE_MAP = {
    "healthy": "normal",
    "growth": "normal",
    "low_value": "normal",
    "churn_risk": "high_risk",
    "silent_churn": "high_risk",
    "support_escalation": "multi_signal",
    "declining_usage": "multi_signal",
    "seasonal_dip": "ambiguous",
    "new_customer": "insufficient_evidence",
}


def build_cases(db: Session, case_types: list[str] | None = None) -> list[dict[str, Any]]:
    """Select real customers from the database to act as evaluation cases."""
    wanted = case_types or CASE_TYPES
    customers = db.query(Customer).all()
    cases: list[dict[str, Any]] = []
    for c in customers:
        case_type = ARCHETYPE_CASE_MAP.get(c.archetype)
        if case_type is None or case_type not in wanted:
            continue
        cases.append(
            {
                "case_id": f"CASE-{c.customer_id}",
                "case_type": case_type,
                "customer_id": c.customer_id,
                "customer_name": c.customer_name,
                "archetype": c.archetype,
                "expected_priority": _expected(c.archetype),
                "expects_evidence": case_type != "insufficient_evidence",
            }
        )
    order = {t: i for i, t in enumerate(CASE_TYPES)}
    cases.sort(key=lambda c: (order.get(c["case_type"], 99), c["customer_id"]))
    return cases


def _expected(archetype: str) -> str:
    from ..data.seed import ARCHETYPES

    return ARCHETYPES.get(archetype, {}).get("expected_priority", "LOW")


def run_evaluation(db: Session, case_types: list[str] | None = None) -> dict[str, Any]:
    """Execute the harness against the live pipeline and measure real results."""
    run_id = f"EVAL-{dt.datetime.utcnow().strftime('%y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    started = dt.datetime.utcnow()

    frames = load_frames(db)
    if frames["customers"].empty:
        return {
            "run_id": run_id,
            "executed": False,
            "status": "Evaluation pending",
            "message": "No data in the database — run the seed command before evaluating.",
        }

    ref = reference_date(frames)
    all_metrics = compute_all_metrics(frames, ref)
    index = get_index(db, frames)
    revenue_sorted = sorted((m["revenue_90d"] for m in all_metrics.values()), reverse=True)

    def rank_pct(value: float) -> float:
        if not revenue_sorted:
            return 0.0
        rank = sum(1 for r in revenue_sorted if r > value)
        return 1.0 - (rank / len(revenue_sorted))

    cases = build_cases(db, case_types)
    results: list[dict[str, Any]] = []

    for case in cases:
        metrics = all_metrics.get(case["customer_id"])
        if metrics is None:
            continue
        t0 = dt.datetime.utcnow()
        bundle = score_customer(metrics, frames, index, ref, rank_pct(metrics["revenue_90d"]))
        latency_ms = (dt.datetime.utcnow() - t0).total_seconds() * 1000

        verified = [e for e in bundle["evidence"] if e.verified]
        predicted = bundle["priority"]
        expected = case["expected_priority"]
        correct = predicted == expected
        from ..decision_engine.engine import BAND_INDEX

        within_one = abs(BAND_INDEX[predicted] - BAND_INDEX[expected]) <= 1

        # A "failure" is a real-world miss: a case that should have been
        # escalated (HIGH) but was scored LOW, i.e. a missed escalation.
        escalated = expected == "HIGH" and predicted == "LOW"

        results.append(
            {
                "case_id": case["case_id"],
                "case_type": case["case_type"],
                "customer_id": case["customer_id"],
                "customer_name": case["customer_name"],
                "expected_priority": expected,
                "predicted_priority": predicted,
                "correct": correct,
                "within_one_band": within_one,
                "evidence_count": len(bundle["evidence"]),
                "verified_evidence_count": len(verified),
                "evidence_hit": len(verified) >= 1,
                "latency_ms": round(latency_ms, 2),
                "escalated": escalated,
                "insufficient_evidence": bool(bundle["insufficient_evidence"]),
                "score": round(float(bundle["priority_score"]), 2),
                "confidence": float(bundle["confidence"]),
                "notes": (
                    f"archetype={case['archetype']}; signals measurable="
                    f"{len([s for s in bundle['signals'] if s.has_data])}/{len(bundle['signals'])}"
                ),
            }
        )

    duration_ms = (dt.datetime.utcnow() - started).total_seconds() * 1000
    metrics_out = _aggregate(results, duration_ms)

    # --- persist the run so the UI can show genuinely-historical results ---
    row = EvaluationRun(
        run_id=run_id,
        started_at=started,
        duration_ms=round(duration_ms, 2),
        total_cases=len(results),
        metrics=metrics_out,
        results=results,
        engine_mode="deterministic",
    )
    db.add(row)
    db.commit()

    out = {
        "run_id": run_id,
        "executed": True,
        "executed_at": started,
        "duration_ms": round(duration_ms, 2),
        "engine_mode": "deterministic",
        "llm_used": settings.llm_enabled,
        "status": "Executed",
        "message": (
            f"{len(results)} cases executed against the live decision pipeline "
            f"(embedding backend: {index.embedder.name}, vector backend: {index.backend})."
        ),
        "metrics": metrics_out,
        "cases": results,
    }

    report_path = Path(settings.DATA_DIR) / f"evaluation_{run_id}.json"
    report_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    out["report_path"] = str(report_path)

    latest = Path(settings.DATA_DIR) / "evaluation_latest.json"
    latest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


def _aggregate(results: list[dict[str, Any]], duration_ms: float) -> dict[str, Any]:
    if not results:
        return {
            "total_cases": 0,
            "decision_accuracy": 0.0,
            "adjacent_accuracy": 0.0,
            "evidence_hit_rate": 0.0,
            "evidence_verification_rate": 0.0,
            "avg_response_ms": 0.0,
            "p95_response_ms": 0.0,
            "escalation_failure_rate": 0.0,
            "insufficient_evidence_rate": 0.0,
            "by_case_type": {},
        }

    n = len(results)
    latencies = [r["latency_ms"] for r in results]
    sorted_lat = sorted(latencies)
    p95_idx = max(0, min(n - 1, int(round(0.95 * (n - 1)))))
    total_evidence = sum(r["evidence_count"] for r in results)
    total_verified = sum(r["verified_evidence_count"] for r in results)

    by_type: dict[str, Any] = {}
    for case_type in CASE_TYPES:
        subset = [r for r in results if r["case_type"] == case_type]
        if not subset:
            by_type[case_type] = {
                "label": CASE_TYPE_LABELS[case_type],
                "cases": 0,
                "decision_accuracy": None,
                "evidence_hit_rate": None,
            }
            continue
        by_type[case_type] = {
            "label": CASE_TYPE_LABELS[case_type],
            "cases": len(subset),
            "decision_accuracy": round(sum(1 for r in subset if r["correct"]) / len(subset), 3),
            "evidence_hit_rate": round(sum(1 for r in subset if r["evidence_hit"]) / len(subset), 3),
            "avg_latency_ms": round(statistics.fmean(r["latency_ms"] for r in subset), 2),
            "customers": [
                {
                    "customer_id": r["customer_id"],
                    "customer_name": r["customer_name"],
                    "expected": r["expected_priority"],
                    "predicted": r["predicted_priority"],
                    "score": r["score"],
                    "correct": r["correct"],
                }
                for r in subset
            ],
        }

    return {
        "total_cases": n,
        "decision_accuracy": round(sum(1 for r in results if r["correct"]) / n, 3),
        "adjacent_accuracy": round(sum(1 for r in results if r["within_one_band"]) / n, 3),
        "evidence_hit_rate": round(sum(1 for r in results if r["evidence_hit"]) / n, 3),
        "evidence_verification_rate": (
            round(total_verified / total_evidence, 3) if total_evidence else 0.0
        ),
        "avg_response_ms": round(statistics.fmean(latencies), 2),
        "p95_response_ms": round(sorted_lat[p95_idx], 2),
        "total_pipeline_ms": round(duration_ms, 2),
        "escalation_failure_rate": round(sum(1 for r in results if r["escalated"]) / n, 3),
        "insufficient_evidence_rate": round(
            sum(1 for r in results if r["insufficient_evidence"]) / n, 3
        ),
        "avg_evidence_per_case": round(total_evidence / n, 2),
        "by_case_type": by_type,
    }


def latest_run(db: Session) -> dict[str, Any] | None:
    row = (
        db.query(EvaluationRun)
        .order_by(EvaluationRun.started_at.desc())
        .first()
    )
    if row is None:
        return None
    return {
        "run_id": row.run_id,
        "executed": True,
        "executed_at": row.started_at,
        "duration_ms": row.duration_ms,
        "engine_mode": row.engine_mode,
        "llm_used": False,
        "status": "Executed",
        "message": f"{row.total_cases} cases executed against the live decision pipeline.",
        "metrics": row.metrics,
        "cases": row.results,
    }


def main() -> None:
    """Entry point for ``python -m app.evaluation.harness``."""
    from ..data.db import init_db, session_scope

    init_db()
    with session_scope() as db:
        report = run_evaluation(db)

    if not report.get("executed"):
        print(report.get("message"))
        return

    m = report["metrics"]
    print("DeciTrace AI — evaluation harness")
    print(f"  run id                 : {report['run_id']}")
    print(f"  cases executed         : {m['total_cases']}")
    print(f"  decision accuracy      : {m['decision_accuracy'] * 100:.1f}%")
    print(f"  adjacent accuracy      : {m['adjacent_accuracy'] * 100:.1f}%")
    print(f"  evidence hit rate      : {m['evidence_hit_rate'] * 100:.1f}%")
    print(f"  evidence verification  : {m['evidence_verification_rate'] * 100:.1f}%")
    print(f"  avg response           : {m['avg_response_ms']:.0f} ms")
    print(f"  p95 response           : {m['p95_response_ms']:.0f} ms")
    print(f"  escalation failure rate: {m['escalation_failure_rate'] * 100:.1f}%")
    print(f"  insufficient-evidence  : {m['insufficient_evidence_rate'] * 100:.1f}%")
    print("\n  by case type:")
    for case_type, block in m["by_case_type"].items():
        if not block["cases"]:
            continue
        print(
            f"    {case_type:<22} n={block['cases']:<3} "
            f"accuracy={block['decision_accuracy'] * 100:5.1f}%  "
            f"evidence_hit={block['evidence_hit_rate'] * 100:5.1f}%"
        )
    print(f"\n  report: {report.get('report_path')}")


if __name__ == "__main__":
    main()


def pending_payload() -> dict[str, Any]:
    """The honest answer when the harness has never been executed."""
    return {
        "run_id": "",
        "executed": False,
        "executed_at": None,
        "duration_ms": 0.0,
        "engine_mode": "deterministic",
        "llm_used": False,
        "status": "Evaluation pending",
        "message": (
            "Evaluation pending — the harness has not been executed for this database. "
            "Run `python -m app.evaluation.harness` or POST /api/evaluate to measure real results."
        ),
        "metrics": None,
        "cases": [],
    }
