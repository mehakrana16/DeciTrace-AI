"""Pydantic response/request schemas — the API contract."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------
class CustomerRef(BaseModel):
    customer_id: str
    customer_name: str
    industry: str
    region: str
    segment: str
    account_value: float
    status: str
    owner: str


class SignalOut(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    direction: Literal["risk", "positive", "neutral"]
    level: Literal["critical", "high", "moderate", "low", "none"]
    points: float = Field(description="Contribution to the priority score (0-100 scale)")
    weight_max: float
    reason: str
    has_data: bool = True


class EvidenceOut(BaseModel):
    id: int | None = None
    rank: int
    source_table: str
    source_id: str
    evidence_type: str
    title: str
    snippet: str
    score: float
    retrieval_method: str
    occurred_on: dt.date | None = None
    verified: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)


class ActionOut(BaseModel):
    action_type: str
    label: str
    owner: str
    sla_hours: int
    rationale: str


class DecisionOut(BaseModel):
    decision_id: str
    customer: CustomerRef
    generated_at: dt.datetime
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    priority_score: float
    priority_score_band: str
    confidence: float
    confidence_label: str
    insufficient_evidence: bool
    decision_text: str
    summary: str
    reasons: list[str]
    signals: list[SignalOut]
    top_signals: list[str]
    recommended_action: ActionOut
    explanation: str
    engine_mode: str
    llm_used: bool
    status: Literal["pending", "approved", "rejected"]
    evidence: list[EvidenceOut] = Field(default_factory=list)
    human_decision: dict[str, Any] | None = None


class DecisionSummary(BaseModel):
    decision_id: str
    customer_id: str
    customer_name: str
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    priority_score: float
    confidence: float
    decision_text: str
    action_type: str
    status: str
    generated_at: dt.datetime


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class KpiCard(BaseModel):
    key: str
    label: str
    value: float | int | str
    unit: str = ""
    delta_pct: float | None = None
    hint: str = ""


class SliceOut(BaseModel):
    label: str
    value: float


class AttentionQueueItem(BaseModel):
    customer_id: str
    customer_name: str
    priority: str
    priority_score: float
    confidence: float
    headline: str
    top_reason: str
    action_label: str
    account_value: float
    status: str
    decision_id: str


class DashboardOut(BaseModel):
    generated_at: dt.datetime
    reference_date: dt.date
    headline: str
    kpis: list[KpiCard]
    attention_queue: list[AttentionQueueItem]
    recent_decisions: list[DecisionSummary]
    priority_distribution: list[SliceOut]
    action_distribution: list[SliceOut]
    issue_distribution: list[SliceOut]
    revenue_trend: list[dict[str, Any]]
    recent_evidence: list[EvidenceOut]
    pipeline: list[dict[str, str]]
    data_health: dict[str, Any]


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
class CustomerListItem(BaseModel):
    customer_id: str
    customer_name: str
    industry: str
    region: str
    segment: str
    account_value: float
    status: str
    owner: str
    priority: str | None = None
    priority_score: float | None = None
    revenue_90d: float = 0.0
    open_tickets: int = 0
    usage_delta_pct: float | None = None


class CustomerDetailOut(BaseModel):
    customer: CustomerRef
    onboarded_on: dt.date
    kpis: list[KpiCard]
    signals: list[SignalOut]
    priority: str
    priority_score: float
    confidence: float
    reasons: list[str]
    recommended_action: ActionOut | None
    timeline: list[dict[str, Any]]
    revenue_series: list[dict[str, Any]]
    usage_series: list[dict[str, Any]]
    tickets: list[dict[str, Any]]
    notes: list[dict[str, Any]]
    latest_decision_id: str | None


# ---------------------------------------------------------------------------
# Ask DeciTrace
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=600)
    customer_id: str | None = None
    limit: int = Field(default=5, ge=1, le=25)


class AskResultItem(BaseModel):
    customer_id: str
    customer_name: str
    priority: str
    priority_score: float
    confidence: float
    reasons: list[str]
    action_label: str
    decision_id: str
    status: str


class AskResponse(BaseModel):
    question: str
    intent: str
    intent_label: str
    workflow: list[str]
    answer: str
    llm_used: bool
    engine_mode: str
    resolved_customer_id: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    results: list[AskResultItem] = Field(default_factory=list)
    decisions: list[DecisionOut] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list)
    analytics: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Human in the loop
# ---------------------------------------------------------------------------
class ReviewRequest(BaseModel):
    actor: str = Field(default="sales.manager@example.com", max_length=120)
    note: str = Field(default="", max_length=1000)


class DecisionEventOut(BaseModel):
    event_type: str
    actor: str
    note: str
    created_at: dt.datetime


class ReviewResponse(BaseModel):
    decision_id: str
    status: str
    ai_recommendation: str
    human_decision: str
    timestamp: dt.datetime
    events: list[DecisionEventOut]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
class EvaluateRequest(BaseModel):
    case_types: list[str] | None = None
    include_llm: bool = False


class EvalCaseResult(BaseModel):
    case_id: str
    case_type: str
    customer_id: str
    customer_name: str
    expected_priority: str
    predicted_priority: str
    correct: bool
    within_one_band: bool
    evidence_count: int
    verified_evidence_count: int
    evidence_hit: bool
    latency_ms: float
    escalated: bool
    insufficient_evidence: bool
    score: float = 0.0
    confidence: float = 0.0
    notes: str = ""


class EvalMetrics(BaseModel):
    total_cases: int
    decision_accuracy: float
    adjacent_accuracy: float
    evidence_hit_rate: float
    evidence_verification_rate: float
    avg_response_ms: float
    p95_response_ms: float
    total_pipeline_ms: float | None = None
    escalation_failure_rate: float
    insufficient_evidence_rate: float
    avg_evidence_per_case: float | None = None
    by_case_type: dict[str, Any]


class EvaluationOut(BaseModel):
    run_id: str
    executed: bool
    executed_at: dt.datetime | None = None
    duration_ms: float = 0.0
    engine_mode: str = "deterministic"
    llm_used: bool = False
    status: str
    message: str = ""
    metrics: EvalMetrics | None = None
    cases: list[EvalCaseResult] = Field(default_factory=list)


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    database: str
    rows: dict[str, int]
    embedding_backend: str
    embedding_model: str
    vector_backend: str
    llm_enabled: bool
    llm_provider: str
    engine_mode: str
    reference_date: dt.date | None = None
