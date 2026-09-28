"""Entry point: ``python -m app.evaluation.harness``.

Runs the harness against the configured database and prints the measured
numbers. Nothing is printed that was not computed.
"""
from __future__ import annotations

import json

from ..data.db import init_db, session_scope
from .harness import run_evaluation


def main() -> None:
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
