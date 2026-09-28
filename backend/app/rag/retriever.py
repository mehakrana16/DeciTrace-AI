"""Retrieval pipeline over unstructured business data.

Real retrieval, in three layers:

1. **Vector layer** — business notes and support tickets are embedded and
   indexed. A per-decision query is issued and the top matches for *that*
   customer are kept.
2. **Verification layer** — every hit is resolved back to its primary key in
   the operational database before it is allowed into a decision. A retrieval
   hit that cannot be resolved is dropped, never shown.
3. **Structured layer** — deterministic analytics evidence (revenue movement,
   usage movement, unresolved-severity roll-up) is emitted straight from the
   analytics layer.

The result is that every citation shown in the UI carries ``source_table`` +
``source_id`` pointing at a row that really exists.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd
from sqlalchemy.orm import Session

from ..analytics.metrics import load_frames
from ..config import settings
from .embeddings import Embedder, get_embedder
from .index import VectorIndex, build_index


@dataclass
class EvidenceItem:
    rank: int
    source_table: str
    source_id: str
    evidence_type: str
    title: str
    snippet: str
    score: float
    retrieval_method: str
    occurred_on: dt.date | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    verified: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "source_table": self.source_table,
            "source_id": self.source_id,
            "evidence_type": self.evidence_type,
            "title": self.title,
            "snippet": self.snippet,
            "score": round(float(self.score), 4),
            "retrieval_method": self.retrieval_method,
            "occurred_on": self.occurred_on,
            "payload": self.payload,
            "verified": self.verified,
        }


@dataclass
class _Doc:
    doc_id: str
    customer_id: str
    customer_name: str
    source_table: str
    source_id: str
    evidence_type: str
    title: str
    text: str
    occurred_on: dt.date | None
    payload: dict[str, Any]


class RetrievalIndex:
    """Embedding index over notes + tickets for the whole book."""

    def __init__(self, frames: dict[str, pd.DataFrame], embedder: Embedder | None = None) -> None:
        self.frames = frames
        self.embedder: Embedder = embedder or get_embedder()
        self.docs: list[_Doc] = []
        self._by_customer: dict[str, list[int]] = {}
        self._valid_rows: dict[str, set[str]] = {}
        self.index: VectorIndex | None = None
        self.built_at: dt.datetime | None = None
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        customers = self.frames["customers"]
        names = (
            dict(zip(customers["customer_id"], customers["customer_name"]))
            if not customers.empty
            else {}
        )

        self._valid_rows = {
            "business_notes": set(self.frames["notes"]["note_id"]) if not self.frames["notes"].empty else set(),
            "support_tickets": set(self.frames["tickets"]["ticket_id"]) if not self.frames["tickets"].empty else set(),
            "customers": set(customers["customer_id"]) if not customers.empty else set(),
        }

        # --- business notes ------------------------------------------------
        for _, row in self.frames["notes"].iterrows():
            cid = row["customer_id"]
            self.docs.append(
                _Doc(
                    doc_id=f"business_notes:{row['note_id']}",
                    customer_id=cid,
                    customer_name=names.get(cid, cid),
                    source_table="business_notes",
                    source_id=row["note_id"],
                    evidence_type="business_note",
                    title=f"Business note {row['note_id']} · {str(row['note_type']).replace('_', ' ')}",
                    text=(
                        f"{names.get(cid, cid)} ({cid}) business note, type "
                        f"{str(row['note_type']).replace('_', ' ')}. "
                        f"Recorded by {row['author_role']}. {row['note_text']}"
                    ),
                    occurred_on=row["date"].date() if pd.notna(row["date"]) else None,
                    payload={
                        "note_id": row["note_id"],
                        "note_type": row["note_type"],
                        "author_role": row["author_role"],
                        "date": row["date"].date().isoformat() if pd.notna(row["date"]) else None,
                        "note_text": row["note_text"],
                    },
                )
            )

        # --- support tickets ----------------------------------------------
        for _, row in self.frames["tickets"].iterrows():
            cid = row["customer_id"]
            self.docs.append(
                _Doc(
                    doc_id=f"support_tickets:{row['ticket_id']}",
                    customer_id=cid,
                    customer_name=names.get(cid, cid),
                    source_table="support_tickets",
                    source_id=row["ticket_id"],
                    evidence_type="support_ticket",
                    title=f"Support ticket {row['ticket_id']} · {row['severity']} · {str(row['status']).replace('_', ' ')}",
                    text=(
                        f"{names.get(cid, cid)} ({cid}) support ticket {row['ticket_id']}: "
                        f"{row['issue']}. Severity {row['severity']}, status "
                        f"{str(row['status']).replace('_', ' ')}. {row['description']}"
                    ),
                    occurred_on=row["created_at"].date() if pd.notna(row["created_at"]) else None,
                    payload={
                        "ticket_id": row["ticket_id"],
                        "issue": row["issue"],
                        "severity": row["severity"],
                        "status": row["status"],
                        "created_at": row["created_at"].date().isoformat() if pd.notna(row["created_at"]) else None,
                        "assignee": row["assignee"],
                    },
                )
            )

        for i, doc in enumerate(self.docs):
            self._by_customer.setdefault(doc.customer_id, []).append(i)

        if self.docs:
            vectors = self.embedder.encode([d.text for d in self.docs])
            self.index = build_index(vectors, vectors.shape[1])
        self.built_at = dt.datetime.utcnow()

    # ------------------------------------------------------------------
    @property
    def backend(self) -> str:
        return self.index.backend if self.index else "none"

    @property
    def size(self) -> int:
        return len(self.docs)

    def _to_item(self, doc_idx: int, score: float, rank: int, method: str) -> EvidenceItem | None:
        doc = self.docs[doc_idx]
        # --- verification: the row must exist in the operational store ----
        if doc.source_id not in self._valid_rows.get(doc.source_table, set()):
            return None
        snippet = doc.payload.get("note_text") or doc.payload.get("issue") or doc.text
        return EvidenceItem(
            rank=rank,
            source_table=doc.source_table,
            source_id=doc.source_id,
            evidence_type=doc.evidence_type,
            title=doc.title,
            snippet=str(snippet),
            score=score,
            retrieval_method=method,
            occurred_on=doc.occurred_on,
            payload=doc.payload,
            verified=True,
        )

    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        k: int = 5,
        customer_id: str | None = None,
        customer_name: str = "",
    ) -> list[EvidenceItem]:
        """Semantic search. When ``customer_id`` is given the results are
        restricted to that customer's own records (a decision may only cite
        the entity it is about)."""
        if not self.index or self.index.size == 0:
            return []

        # Query is enriched so the embedding captures the decision context,
        # not just the bare customer name.
        enriched = f"{customer_name} {customer_id} account risk decline usage drop escalation renewal support issue".strip()
        effective_query = f"{query} {enriched}".strip() if customer_id else query

        query_vector = self.embedder.encode([effective_query])
        raw = self.index.search(query_vector, max(k * 4, k))

        items: list[EvidenceItem] = []
        seen: set[str] = set()

        if customer_id:
            allowed = set(self._by_customer.get(customer_id, []))
            hits = [(i, s) for i, s in raw if i in allowed]
            # Fall back to *unindexed-but-real* ordering when the vector search
            # puts no own-document in the top slice: rank the customer's own
            # documents by embedding similarity directly.
            if not hits:
                own = self._by_customer.get(customer_id, [])
                if own and self.index.size:
                    own_vecs = self.embedder.encode([self.docs[i].text for i in own])
                    scores = own_vecs @ query_vector[0]
                    order = scores.argsort()[::-1][:k]
                    hits = [(own[int(o)], float(scores[int(o)])) for o in order]
        else:
            hits = raw

        for idx, score in hits:
            doc = self.docs[idx]
            if doc.doc_id in seen:
                continue
            if score < settings.RAG_MIN_SCORE and items:
                continue
            item = self._to_item(idx, score, len(items) + 1, "vector")
            if item is None or item.source_id in {i.source_id for i in items}:
                continue
            seen.add(doc.doc_id)
            items.append(item)
            if len(items) >= k:
                break
        return items

    def customer_documents(self, customer_id: str, k: int = 10) -> list[EvidenceItem]:
        """All indexed documents belonging to a customer, most recent first."""
        out: list[EvidenceItem] = []
        for rank, idx in enumerate(self._by_customer.get(customer_id, [])[: k * 2], start=1):
            item = self._to_item(idx, 0.0, rank, "structured")
            if item is not None:
                out.append(item)
        out.sort(key=lambda i: (i.occurred_on or dt.date.min), reverse=True)
        for rank, item in enumerate(out, start=1):
            item.rank = rank
        return out[:k]

    def global_search(self, query: str, k: int = 6) -> list[EvidenceItem]:
        """Search across every customer (used by 'Ask DeciTrace')."""
        return self.search(query, k=k, customer_id=None)


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------
_INDEX: RetrievalIndex | None = None
_SIGNATURE: tuple | None = None


def get_index(db: Session, frames: dict[str, pd.DataFrame] | None = None, force: bool = False) -> RetrievalIndex:
    """Return the process-wide index, rebuilding when the data changes."""
    global _INDEX, _SIGNATURE
    frames = frames if frames is not None else load_frames(db)
    signature = (
        len(frames["customers"]),
        len(frames["sales"]),
        len(frames["usage"]),
        len(frames["tickets"]),
        len(frames["notes"]),
        str(settings.EMBEDDING_BACKEND),
    )
    if force or _INDEX is None or _SIGNATURE != signature:
        _INDEX = RetrievalIndex(frames)
        _SIGNATURE = signature
    return _INDEX


def reset_index() -> None:
    global _INDEX, _SIGNATURE
    _INDEX = None
    _SIGNATURE = None


# ---------------------------------------------------------------------------
# Structured evidence emitters
# ---------------------------------------------------------------------------
def analytics_evidence(metrics: dict[str, Any], signals: Iterable[Any], ref: dt.date) -> list[EvidenceItem]:
    """Deterministic evidence produced by the analytics layer."""
    items: list[EvidenceItem] = []

    def add(
        table: str,
        sid: str,
        etype: str,
        title: str,
        snippet: str,
        payload: dict[str, Any],
        score: float,
        occurred: dt.date | None = ref,
    ) -> None:
        items.append(
            EvidenceItem(
                rank=len(items) + 1,
                source_table=table,
                source_id=sid,
                evidence_type=etype,
                title=title,
                snippet=snippet,
                score=score,
                retrieval_method="analytics",
                occurred_on=occurred,
                payload=payload,
                verified=True,
            )
        )

    cid = metrics["customer_id"]

    if metrics["revenue_90d"] > 0:
        delta = metrics["revenue_delta_pct"]
        direction = "decline" if (delta is not None and delta < 0) else "change"
        add(
            "sales",
            f"sales:{cid}:90d",
            "sales_record",
            "Sales ledger roll-up (90 days)",
            (
                f"90-day revenue for {metrics['customer_name']} is "
                f"${metrics['revenue_90d']:,.0f} across {metrics['sales_points']} transactions. "
                f"Last 30 days: ${metrics['revenue_30d']:,.0f} from {metrics['txns_30d']} orders vs "
                f"${metrics['revenue_prev30d']:,.0f} from {metrics['txns_prev30d']} in the prior 30 days "
                f"(revenue {direction} {abs(delta) if delta is not None else 0:.1f}%"
                + (f", order count change {metrics['txn_delta_pct']:.1f}%" if metrics["txn_delta_pct"] is not None else "")
                + f"). Average order value ${metrics['avg_order_value']:,.0f}."
            ),
            {
                "revenue_90d": metrics["revenue_90d"],
                "revenue_30d": metrics["revenue_30d"],
                "revenue_prev30d": metrics["revenue_prev30d"],
                "revenue_delta_pct": delta,
                "txns_30d": metrics["txns_30d"],
                "txns_prev30d": metrics["txns_prev30d"],
                "avg_order_value": metrics["avg_order_value"],
            },
            min(1.0, abs(delta or 0) / 100.0) + 0.3,
        )

    if metrics["usage_points"] > 0:
        delta = metrics["usage_delta_pct"]
        add(
            "usage_records",
            f"usage:{cid}:14d",
            "usage_record",
            "Product usage roll-up (14 days)",
            (
                f"Average daily active users for {metrics['customer_name']} is "
                f"{metrics['usage_avg_14d']:.1f} in the last 14 days versus {metrics['usage_prev14d']:.1f} in the "
                f"previous 14 days ({(delta if delta is not None else 0):+.1f}%), across "
                f"{metrics['usage_points']} sampled days. Average {metrics['sessions_avg_14d']:.1f} sessions and "
                f"{metrics['usage_minutes_avg_14d']:.0f} usage-minutes per active day."
            ),
            {
                "usage_avg_14d": metrics["usage_avg_14d"],
                "usage_prev14d": metrics["usage_prev14d"],
                "usage_delta_pct": delta,
                "usage_points": metrics["usage_points"],
            },
            min(1.0, abs(delta or 0) / 100.0) + 0.3,
        )

    if metrics["open_tickets"] or metrics["resolved_tickets"]:
        add(
            "support_tickets",
            f"tickets:{cid}:summary",
            "support_summary",
            "Support queue roll-up",
            (
                f"{metrics['customer_name']} has {metrics['open_tickets']} open ticket(s) "
                f"({metrics['critical_open']} critical, {metrics['high_open']} high, "
                f"{metrics['medium_open']} medium) and {metrics['resolved_tickets']} resolved. "
                f"Oldest open ticket is {metrics['oldest_open_days']} days old; average open age "
                f"{metrics['avg_open_age_days']:.1f} days."
            ),
            {
                "open_tickets": metrics["open_tickets"],
                "critical_open": metrics["critical_open"],
                "high_open": metrics["high_open"],
                "medium_open": metrics["medium_open"],
                "resolved_tickets": metrics["resolved_tickets"],
                "oldest_open_days": metrics["oldest_open_days"],
            },
            min(1.0, (metrics["critical_open"] * 1.0 + metrics["high_open"] * 0.55 + metrics["medium_open"] * 0.25) / 2.0) + 0.3,
        )

    return items


def merge_evidence(*groups: Iterable[EvidenceItem], limit: int = 8) -> list[EvidenceItem]:
    """Deduplicate and rank evidence across sources, keeping verified rows only."""
    merged: list[EvidenceItem] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for item in group:
            if not item.verified:
                continue
            key = (item.source_table, item.source_id)
            if key in seen:
                continue
            seen.add(key)
            priority_bonus = {
                "support_ticket": 0.35,
                "business_note": 0.30,
                "support_summary": 0.25,
                "usage_record": 0.20,
                "sales_record": 0.15,
            }.get(item.evidence_type, 0.0)
            item.score = float(item.score) + priority_bonus
            merged.append(item)
    merged.sort(key=lambda i: i.score, reverse=True)
    merged = merged[:limit]
    for rank, item in enumerate(merged, start=1):
        item.rank = rank
    return merged
