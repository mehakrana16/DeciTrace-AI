"""SQLAlchemy models for DeciTrace AI.

Tables
------
business data   : customers, sales, usage_records, support_tickets, business_notes
decision state  : decisions, decision_events (human-in-the-loop audit trail)
eval state      : evaluation_runs
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .db import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String(16), primary_key=True)
    customer_name = Column(String(120), nullable=False, index=True)
    industry = Column(String(80), nullable=False)
    region = Column(String(80), nullable=False)
    segment = Column(String(40), nullable=False, default="Mid-Market")
    account_value = Column(Float, nullable=False, default=0.0)
    owner = Column(String(80), nullable=False, default="Unassigned")
    status = Column(String(24), nullable=False, default="active")
    onboarded_on = Column(Date, nullable=False)
    archetype = Column(String(32), nullable=False, default="healthy")  # synthetic ground truth

    sales = relationship("Sale", back_populates="customer", cascade="all, delete-orphan")
    usage = relationship("UsageRecord", back_populates="customer", cascade="all, delete-orphan")
    tickets = relationship("SupportTicket", back_populates="customer", cascade="all, delete-orphan")
    notes = relationship("BusinessNote", back_populates="customer", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="customer", cascade="all, delete-orphan")


class Sale(Base):
    __tablename__ = "sales"

    transaction_id = Column(String(24), primary_key=True)
    customer_id = Column(String(16), ForeignKey("customers.customer_id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    product = Column(String(80), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    channel = Column(String(32), nullable=False, default="direct")

    customer = relationship("Customer", back_populates="sales")

    __table_args__ = (Index("ix_sales_customer_date", "customer_id", "date"),)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String(16), ForeignKey("customers.customer_id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    active_users = Column(Integer, nullable=False, default=0)
    sessions = Column(Integer, nullable=False, default=0)
    usage_minutes = Column(Integer, nullable=False, default=0)

    customer = relationship("Customer", back_populates="usage")

    __table_args__ = (Index("ix_usage_customer_date", "customer_id", "date"),)


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    ticket_id = Column(String(20), primary_key=True)
    customer_id = Column(String(16), ForeignKey("customers.customer_id"), nullable=False, index=True)
    issue = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    severity = Column(String(16), nullable=False, default="medium")  # critical|high|medium|low
    status = Column(String(16), nullable=False, default="open")  # open|in_progress|resolved
    created_at = Column(Date, nullable=False, index=True)
    resolved_at = Column(Date, nullable=True)
    assignee = Column(String(80), nullable=False, default="Support Queue")

    customer = relationship("Customer", back_populates="tickets")


class BusinessNote(Base):
    __tablename__ = "business_notes"

    note_id = Column(String(20), primary_key=True)
    customer_id = Column(String(16), ForeignKey("customers.customer_id"), nullable=False, index=True)
    note_text = Column(Text, nullable=False)
    author_role = Column(String(60), nullable=False, default="Account Manager")
    note_type = Column(String(32), nullable=False, default="account_review")
    date = Column(Date, nullable=False, index=True)

    customer = relationship("Customer", back_populates="notes")


class Decision(Base):
    __tablename__ = "decisions"

    decision_id = Column(String(24), primary_key=True)
    customer_id = Column(String(16), ForeignKey("customers.customer_id"), nullable=False, index=True)
    generated_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow, index=True)
    priority = Column(String(8), nullable=False, index=True)  # HIGH|MEDIUM|LOW
    priority_score = Column(Float, nullable=False, default=0.0)
    decision_text = Column(Text, nullable=False, default="")
    action_type = Column(String(48), nullable=False, default="account_review")
    recommended_action = Column(Text, nullable=False, default="")
    reasons = Column(JSON, nullable=False, default=list)
    signals = Column(JSON, nullable=False, default=dict)
    explanation = Column(Text, nullable=False, default="")
    summary = Column(Text, nullable=False, default="")
    llm_used = Column(Boolean, nullable=False, default=False)
    engine_mode = Column(String(32), nullable=False, default="deterministic")
    status = Column(String(16), nullable=False, default="pending", index=True)

    customer = relationship("Customer", back_populates="decisions")
    evidence = relationship(
        "DecisionEvidence", back_populates="decision", cascade="all, delete-orphan"
    )
    events = relationship(
        "DecisionEvent", back_populates="decision", cascade="all, delete-orphan"
    )


class DecisionEvidence(Base):
    """A retrieved, verifiable evidence row attached to a decision.

    ``source_table`` + ``source_id`` always point at a real row in the
    operational database — that is what makes the citation non-fabricated.
    """

    __tablename__ = "decision_evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(String(24), ForeignKey("decisions.decision_id"), nullable=False, index=True)
    rank = Column(Integer, nullable=False, default=1)
    source_table = Column(String(48), nullable=False)
    source_id = Column(String(48), nullable=False)
    evidence_type = Column(String(32), nullable=False)
    title = Column(String(200), nullable=False)
    snippet = Column(Text, nullable=False, default="")
    score = Column(Float, nullable=False, default=0.0)
    retrieval_method = Column(String(48), nullable=False, default="vector")
    occurred_on = Column(Date, nullable=True)
    payload = Column(JSON, nullable=False, default=dict)

    decision = relationship("Decision", back_populates="evidence")


class DecisionEvent(Base):
    """Audit trail for the human-in-the-loop step."""

    __tablename__ = "decision_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(String(24), ForeignKey("decisions.decision_id"), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)  # generated|approved|rejected|reopened
    actor = Column(String(80), nullable=False, default="sales.manager@example.com")
    note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow)

    decision = relationship("Decision", back_populates="events")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    run_id = Column(String(32), primary_key=True)
    started_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow)
    duration_ms = Column(Float, nullable=False, default=0.0)
    total_cases = Column(Integer, nullable=False, default=0)
    metrics = Column(JSON, nullable=False, default=dict)
    results = Column(JSON, nullable=False, default=list)
    engine_mode = Column(String(32), nullable=False, default="deterministic")
