"""Prompt builders for every AI task.

Each builder returns `(prompt, facts)`:
- `prompt` is a single self-contained instruction that pins the model to a strict
  JSON schema and forbids fabrication (use null / "unknown" when unsure).
- `facts` is the exact input snapshot we fed the model — persisted on the
  `AIGeneration` audit row so every output is traceable to what it saw.

Gemma via the Generative Language API has no separate system role, so the
instruction, schema, and data all live in one user turn.
"""
from __future__ import annotations

import json
from typing import Any

_BASE_RULES = (
    "You are a precise B2B sales assistant. Do NOT think out loud, explain your reasoning, "
    "or restate the task. Your entire response must be ONLY a single JSON object — the first "
    "character is '{' and the last is '}' — with no markdown, code fences, or commentary before "
    "or after it. Use null (or \"unknown\") for any field you cannot determine from the provided "
    "facts. Never invent names, numbers, companies, or claims unsupported by the facts given."
)


def _lead_facts(lead: dict[str, Any]) -> dict[str, Any]:
    keep = ("full_name", "first_name", "title", "email", "location",
            "company_name", "industry", "company_size", "notes", "linkedin_url")
    return {k: lead.get(k) for k in keep if lead.get(k) not in (None, "")}


def _block(label: str, data: Any) -> str:
    return f"{label}:\n{json.dumps(data, ensure_ascii=False, indent=2)}"


def qualify_lead(lead: dict[str, Any], icp: dict[str, Any] | None) -> tuple[str, dict]:
    facts = {"lead": _lead_facts(lead), "icp": icp or {}}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Score how well this lead fits the ideal customer profile (ICP) for outreach.\n"
        f"{_block('Lead facts', facts['lead'])}\n"
        f"{_block('Ideal customer profile', facts['icp'])}\n\n"
        "Return JSON with exactly this shape:\n"
        '{"score": <integer 0-100>, "verdict": "strong" | "medium" | "weak" | "unknown", '
        '"rationale": <one short sentence>, "signals": [<short strings, facts that drove the score>], '
        '"assumptions": [<any assumptions you had to make>]}\n'
        "If there are too few facts to judge, use score null and verdict \"unknown\"."
    )
    return prompt, facts


def generate_email(lead: dict[str, Any], context: dict[str, Any] | None) -> tuple[str, dict]:
    ctx = context or {}
    facts = {"lead": _lead_facts(lead), "context": ctx}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Write a concise, personalized cold outreach email. 60-120 words, plain text, "
        "one clear call to action, no spammy phrasing, no fabricated specifics. Personalize only "
        "from the given facts.\n"
        f"{_block('Lead facts', facts['lead'])}\n"
        f"{_block('Sender / product context', ctx)}\n\n"
        "Return JSON: {\"subject\": <short subject line>, \"body\": <email body as plain text>, "
        "\"assumptions\": [<assumptions made>]}"
    )
    return prompt, facts


def generate_linkedin_message(lead: dict[str, Any], context: dict[str, Any] | None) -> tuple[str, dict]:
    ctx = context or {}
    facts = {"lead": _lead_facts(lead), "context": ctx}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Write a LinkedIn connection/outreach note. Max 300 characters, warm, specific, "
        "no links, one soft call to action.\n"
        f"{_block('Lead facts', facts['lead'])}\n"
        f"{_block('Sender / product context', ctx)}\n\n"
        "Return JSON: {\"body\": <message text>, \"assumptions\": [<assumptions made>]}"
    )
    return prompt, facts


def generate_follow_up(thread: list[dict[str, Any]], context: dict[str, Any] | None) -> tuple[str, dict]:
    ctx = context or {}
    facts = {"thread": thread[-8:], "context": ctx}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Write the next follow-up message in this outreach thread. Keep it short, "
        "reference the prior context, add a new angle or value, and do not repeat earlier messages.\n"
        f"{_block('Conversation so far (oldest first)', facts['thread'])}\n"
        f"{_block('Sender / product context', ctx)}\n\n"
        "Return JSON: {\"subject\": <subject or null>, \"body\": <message text>, "
        "\"assumptions\": [<assumptions made>]}"
    )
    return prompt, facts


def classify_reply(message: str, context: dict[str, Any] | None) -> tuple[str, dict]:
    facts = {"message": message[:4000], "context": context or {}}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Classify this inbound reply to a sales outreach email.\n"
        f"{_block('Reply text', facts['message'])}\n\n"
        "Return JSON with exactly this shape:\n"
        '{"intent": "interested" | "not_interested" | "question" | "meeting_request" | '
        '"unsubscribe" | "out_of_office" | "wrong_person" | "other" | "unknown", '
        '"sentiment": "positive" | "neutral" | "negative" | "unknown", '
        '"confidence": <number 0-1>, "summary": <one short sentence>, '
        '"suggested_action": <one short next step>}'
    )
    return prompt, facts


def summarize_conversation(thread: list[dict[str, Any]]) -> tuple[str, dict]:
    facts = {"thread": thread[-20:]}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Summarize this outreach conversation and state the best next action.\n"
        f"{_block('Conversation (oldest first)', facts['thread'])}\n\n"
        "Return JSON: {\"summary\": <2-3 sentences>, \"next_action\": <one short step>}"
    )
    return prompt, facts


def recommend_next_action(lead: dict[str, Any], context: dict[str, Any] | None) -> tuple[str, dict]:
    facts = {"lead": _lead_facts(lead), "context": context or {}}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Recommend the single best next action for this lead in the pipeline.\n"
        f"{_block('Lead facts', facts['lead'])}\n"
        f"{_block('Context', facts['context'])}\n\n"
        "Return JSON: {\"action\": <short imperative>, \"rationale\": <one sentence>}"
    )
    return prompt, facts


def analyze_campaign(stats: dict[str, Any]) -> tuple[str, dict]:
    facts = {"stats": stats}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Analyze this campaign's performance metrics and give concrete, actionable advice. "
        "Base every observation strictly on the numbers given.\n"
        f"{_block('Campaign metrics', stats)}\n\n"
        "Return JSON: {\"summary\": <2-3 sentences>, \"strengths\": [<short strings>], "
        "\"issues\": [<short strings>], \"recommendations\": [<short imperative strings>]}"
    )
    return prompt, facts


def nl_to_filters(query: str, schema: dict[str, Any] | None) -> tuple[str, dict]:
    schema = schema or {}
    facts = {"query": query, "schema": schema}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Translate a natural-language lead-search request into a structured filter.\n"
        f"User request: {json.dumps(query)}\n"
        f"{_block('Allowed fields and operators', schema)}\n\n"
        "Return JSON with exactly this shape:\n"
        '{"match": "all" | "any", '
        '"conditions": [{"field": <one of the allowed fields>, '
        '"op": "eq"|"neq"|"contains"|"starts_with"|"in"|"gt"|"gte"|"lt"|"lte"|"is_null"|"not_null", '
        '"value": <string, number, or list>}], '
        '"sort_by": <allowed field>, "sort_dir": "asc" | "desc"}\n'
        "Only use fields from the allowed list. If the request maps to no valid field, "
        "return an empty conditions array."
    )
    return prompt, facts


def copilot(question: str, context: dict[str, Any] | None) -> tuple[str, dict]:
    ctx = context or {}
    facts = {"question": question, "context": ctx}
    prompt = (
        f"{_BASE_RULES}\n\n"
        "Task: Answer the user's question about their lead-generation workspace. Use ONLY the "
        "provided workspace context; if the answer is not supported by it, say so plainly.\n"
        f"Question: {json.dumps(question)}\n"
        f"{_block('Workspace context', ctx)}\n\n"
        "Return JSON: {\"answer\": <plain-text answer>, \"used_context\": <true|false>}"
    )
    return prompt, facts
