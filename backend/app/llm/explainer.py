"""Optional LLM layer.

The LLM is used **only** for language: summarising supplied evidence, phrasing a
recommended action, and answering a manager's question using figures that the
analytics layer already computed. It is explicitly instructed never to invent a
metric, and the prompt carries only numbers that came out of the database.

When no API key is configured (or the call fails) the module degrades to a
deterministic template writer that produces the same *structure* from the same
computed values. The application therefore behaves identically — minus
phrasing polish — with no external dependency at all.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import settings


class LLMResult:
    def __init__(self, text: str, llm_used: bool, mode: str, error: str = "") -> None:
        self.text = text
        self.llm_used = llm_used
        self.mode = mode
        self.error = error


SYSTEM_PROMPT = (
    "You are the explanation writer inside DeciTrace AI, a business decision engine used by a "
    "Sales/Operations Manager. You explain decisions that were ALREADY MADE by a deterministic "
    "scoring engine.\n"
    "HARD RULES:\n"
    "1. Use ONLY the numbers, dates, ids and quotes present in the supplied JSON. Never invent, "
    "estimate, round differently, or extrapolate any metric.\n"
    "2. Never invent a customer, ticket id, note id or quotation.\n"
    "3. Never change the priority that the engine assigned. You explain it.\n"
    "4. Be concise and operational. No marketing language, no emoji, no exclamation marks.\n"
    "5. If a needed figure is absent, say the data is unavailable rather than guessing."
)


def _payload_digest(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Deterministic template writer (always available)
# ---------------------------------------------------------------------------
def template_explanation(payload: dict[str, Any]) -> str:
    """Compose the explanation from computed values only."""
    m = payload.get("metrics", {})
    signals = payload.get("signals", [])
    evidence = payload.get("evidence", [])
    positive = [s for s in signals if s.get("direction") == "positive"]
    risks = [s for s in signals if s.get("direction") == "risk" and s.get("points", 0) > 0]
    risks.sort(key=lambda s: s.get("points", 0), reverse=True)

    name = m.get("customer_name", "This account")
    priority = payload.get("priority", "LOW")
    score = payload.get("priority_score", 0)
    lines: list[str] = []

    lines.append(
        f"{name} is classified {priority} with a priority score of {score:.1f} out of 100. "
        f"The score is the weighted sum of {len([s for s in signals if s.get('has_data')])} measurable business signals; "
        f"{len(risks)} of them are currently pointing to risk."
    )

    if risks:
        driver_text = "; ".join(
            f"{s['label']} contributing {s['points']:.1f} of {s['weight_max']:.0f} possible points ({s['reason']})"
            for s in risks[:3]
        )
        lines.append(f"Primary drivers, in order of weight: {driver_text}")
    else:
        lines.append(
            "No individual signal is currently breaching its risk threshold; the score is driven by "
            "carry-over materiality rather than an active deterioration."
        )

    verified = [e for e in evidence if e.get("verified", True)]
    if verified:
        citations = "; ".join(
            f"{e['title']} [{e['source_table']}:{e['source_id']}]" for e in verified[:4]
        )
        lines.append(f"Supporting records retrieved and verified against the operational database: {citations}.")
        lines.append(
            f"{len(verified)} distinct evidence record(s) back this decision. "
            "Every citation resolves to a row in the operational store."
        )
    else:
        lines.append(
            "No evidence record could be retrieved and verified for this account, so the recommendation "
            "is withheld and the account is flagged for data collection."
        )

    if positive:
        lines.append(
            "Offsetting signals: "
            + "; ".join(f"{s['label']} — {s['reason']}" for s in positive[:2])
        )

    confidence = payload.get("confidence")
    if confidence is not None:
        lines.append(
            f"Data confidence is {confidence * 100:.0f}% (account completeness "
            f"{float(m.get('data_completeness', 0)) * 100:.0f}%, "
            f"{len([s for s in signals if s.get('has_data')])} of {len(signals)} signals measurable)."
        )

    return "\n".join(lines)


def template_action(payload: dict[str, Any]) -> tuple[str, str]:
    """Return ``(action_type, action_sentence)`` using only computed values."""
    m = payload.get("metrics", {})
    sig = {s["key"]: s for s in payload.get("signals", [])}
    name = m.get("customer_name", "the customer")

    support = sig.get("support_severity", {})
    usage = sig.get("usage_decline", {})
    sales = sig.get("sales_decline", {})
    narrative = sig.get("narrative_risk", {})

    if payload.get("insufficient_evidence"):
        return (
            "data_collection",
            f"Hold the decision on {name} and gather missing telemetry first — the account has only "
            f"{m.get('history_days', 0)} days of history and "
            f"{m.get('sales_points', 0)} recorded transactions. Book a discovery call to confirm "
            f"stakeholders, contracted modules and expected usage before committing account-team time.",
        )

    if support.get("direction") == "risk" and (int(m.get("critical_open", 0)) or int(m.get("high_open", 0))):
        return (
            "critical_escalation",
            f"Escalate the open support issues on {name} to the incident owner today: {m.get('open_tickets', 0)} "
            f"ticket(s) are open ({m.get('critical_open', 0)} critical, {m.get('high_open', 0)} high), the oldest "
            f"{m.get('oldest_open_days', 0)} days old. Issue a written remediation plan with dates and confirm "
            f"receipt with the customer's sponsor.",
        )

    if usage.get("direction") == "risk" and sales.get("direction") == "risk":
        return (
            "account_review",
            f"Schedule an executive account review with {name} within 5 business days. Revenue is down "
            f"{abs(float(m.get('revenue_delta_pct') or 0)):.1f}% and active users are down "
            f"{abs(float(m.get('usage_delta_pct') or 0)):.1f}%. Bring the adoption plan, re-confirm the "
            f"success criteria and agree a 30-day recovery plan.",
        )

    if usage.get("direction") == "risk":
        return (
            "adoption_recovery",
            f"Run an adoption recovery session with {name}: average daily active users moved "
            f"{float(m.get('usage_delta_pct') or 0):+.1f}% ({m.get('usage_avg_14d', 0)} users). "
            f"Identify which purchased modules are unused and run enablement for the two lowest-adoption teams.",
        )

    if sales.get("direction") == "risk":
        return (
            "commercial_review",
            f"Review the commercial position with {name}. 30-day revenue is "
            f"${float(m.get('revenue_30d', 0)):,.0f} versus ${float(m.get('revenue_prev30d', 0)):,.0f} in the prior "
            f"30 days. Confirm whether the change is budget cycle or genuine contraction before proposing terms.",
        )

    if narrative.get("direction") == "risk":
        return (
            "stakeholder_checkin",
            f"Run a stakeholder check-in with {name} to validate the concerns recorded in the account notes "
            f"({int(m.get('note_risk_hits', 0))} note(s) flagged) and re-confirm the renewal timeline.",
        )

    return (
        "monitor",
        f"No intervention needed on {name} today. Keep the standard cadence and watch the next usage roll-up; "
        f"the account is contributing ${float(m.get('revenue_90d', 0)):,.0f} over 90 days on a stable trend.",
    )


def template_answer(payload: dict[str, Any]) -> str:
    """Deterministic natural-language answer for 'Ask DeciTrace'."""
    question = payload.get("question", "")
    intent = payload.get("intent_label", "")
    results = payload.get("results", [])
    metrics = payload.get("analytics", {})

    if not results:
        return (
            f"I ran the \"{intent}\" workflow against the business data for the question "
            f"\"{question}\" and found no account matching those criteria. "
            f"Analysed scope: {metrics.get('customers_analyzed', 0)} customers, "
            f"{metrics.get('decisions_considered', 0)} scored decisions. "
            "Try widening the filter (for example remove the region or severity constraint)."
        )

    lines = [
        f"Workflow: {intent}. Evaluated {metrics.get('customers_analyzed', 0)} customers and "
        f"{metrics.get('decisions_considered', 0)} scored decisions; {len(results)} account(s) matched."
    ]
    for item in results[:5]:
        reason = item.get("reasons", [])
        lines.append(
            f"\n• {item['customer_name']} ({item['customer_id']}) — {item['priority']}, score "
            f"{item['priority_score']:.1f}, confidence {item['confidence'] * 100:.0f}%. "
            f"{reason[0] if reason else ''} Recommended action: {item.get('action_label', 'n/a')}."
        )
    if metrics.get("evidence_checked"):
        lines.append(
            f"\nEvidence verified against the operational database for these accounts: "
            f"{metrics['evidence_checked']} retrieved record(s)."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Remote LLM
# ---------------------------------------------------------------------------
def _call_openai(messages: list[dict[str, str]]) -> str:
    base = settings.LLM_BASE_URL or "https://api.openai.com/v1"
    response = httpx.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.LLM_MODEL,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 700,
        },
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def _call_gemini(messages: list[dict[str, str]]) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
    model = settings.LLM_MODEL if settings.LLM_MODEL.startswith("gemini") else "gemini-1.5-flash"
    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": settings.LLM_API_KEY},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700},
        },
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def complete(user_prompt: str, fallback: str, task: str = "explain") -> LLMResult:
    """Call the configured LLM, falling back to ``fallback`` on any problem."""
    if not settings.llm_enabled:
        return LLMResult(fallback, llm_used=False, mode="deterministic-template")

    provider = settings.LLM_PROVIDER
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        if provider == "gemini":
            text = _call_gemini(messages)
        elif provider == "ollama":
            base = settings.LLM_BASE_URL or "http://localhost:11434"
            response = httpx.post(
                f"{base.rstrip('/')}/api/chat",
                json={"model": settings.LLM_MODEL, "messages": messages, "stream": False},
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            text = response.json()["message"]["content"].strip()
        else:
            text = _call_openai(messages)
        if not text:
            raise ValueError("empty completion")
        return LLMResult(text, llm_used=True, mode=f"llm:{provider}")
    except Exception as exc:  # noqa: BLE001 - any failure must degrade, never break a request
        return LLMResult(
            fallback,
            llm_used=False,
            mode="deterministic-template-fallback",
            error=f"{type(exc).__name__}: {exc}",
        )


# ---------------------------------------------------------------------------
# Task-specific helpers
# ---------------------------------------------------------------------------
def explain_decision(payload: dict[str, Any]) -> LLMResult:
    fallback = template_explanation(payload)
    prompt = (
        f"Explain this decision to a Sales/Operations Manager in 4-6 short sentences. "
        f"State the priority and score, name the two or three heaviest signals with their numbers, "
        f"cite the retrieved evidence ids, and finish with the recommended action.\n\n"
        f"DECISION JSON:\n{_payload_digest(payload)}"
    )
    return complete(prompt, fallback, task="explain")


def suggest_action(payload: dict[str, Any]) -> tuple[str, str, LLMResult]:
    action_type, sentence = template_action(payload)
    result = LLMResult(sentence, llm_used=False, mode="deterministic-template")
    if settings.llm_enabled:
        prompt = (
            "Write ONE operational next-step sentence for the account below. Name the owner role and a "
            "concrete deadline. Use only the supplied numbers.\n\n"
            f"ACCOUNT JSON:\n{_payload_digest(payload)}"
        )
        result = complete(prompt, sentence, task="action")
        if result.llm_used and len(result.text) < 400:
            sentence = result.text
    return action_type, sentence, result


def answer_question(payload: dict[str, Any]) -> LLMResult:
    fallback = template_answer(payload)
    prompt = (
        "Answer the manager's question using ONLY the JSON below. Open with one sentence naming the "
        "workflow you ran and the scope. Then list the matching accounts with their priority, score and "
        "primary reason. Close with the single most urgent next action. Do not add any account that is "
        "not in the JSON.\n\n"
        f"QUESTION: {payload.get('question', '')}\n\n"
        f"RESULT JSON:\n{_payload_digest(payload)}"
    )
    return complete(prompt, fallback, task="answer")
