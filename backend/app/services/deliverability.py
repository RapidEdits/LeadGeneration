"""Deliverability checks: sender-domain authentication (SPF / DKIM / DMARC / MX) via DNS,
plus lightweight content spam heuristics. Advisory only — never blocks sending.
"""
from __future__ import annotations

import re

import dns.resolver

_COMMON_DKIM_SELECTORS = ["google", "selector1", "selector2", "default", "dkim", "k1", "mail", "s1", "s2"]

_SPAM_WORDS = [
    "free", "guarantee", "no obligation", "risk-free", "winner", "cash", "act now",
    "limited time", "click here", "buy now", "order now", "100%", "cheap", "discount",
    "urgent", "congratulations", "$$$", "earn money", "make money", "prize",
]


def _txt(name: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(name, "TXT", lifetime=5)
        return ["".join(s.decode() if isinstance(s, bytes) else s for s in r.strings) for r in answers]
    except Exception:  # noqa: BLE001 — NXDOMAIN / timeout / no records
        return []


def _has_mx(domain: str) -> bool:
    try:
        return len(dns.resolver.resolve(domain, "MX", lifetime=5)) > 0
    except Exception:  # noqa: BLE001
        return False


def check_domain(domain: str) -> dict:
    domain = (domain or "").strip().lower().lstrip("@")
    if not domain or "." not in domain:
        return {"domain": domain, "error": "Invalid domain"}

    txts = _txt(domain)
    spf = next((t for t in txts if t.lower().startswith("v=spf1")), None)
    dmarc_txts = _txt(f"_dmarc.{domain}")
    dmarc = next((t for t in dmarc_txts if t.lower().startswith("v=dmarc1")), None)

    dkim_selectors = []
    for sel in _COMMON_DKIM_SELECTORS:
        recs = _txt(f"{sel}._domainkey.{domain}")
        if any("v=dkim1" in r.lower() or "p=" in r.lower() for r in recs):
            dkim_selectors.append(sel)

    dmarc_policy = None
    if dmarc:
        m = re.search(r"p=(\w+)", dmarc)
        dmarc_policy = m.group(1) if m else None

    checks = {
        "mx": _has_mx(domain),
        "spf": spf is not None,
        "dmarc": dmarc is not None,
        # DKIM can't be proven without knowing the selector; found==True is positive,
        # False means "not found at common selectors" (unknown), not "misconfigured".
        "dkim": len(dkim_selectors) > 0,
    }
    recommendations = []
    if not checks["mx"]:
        recommendations.append("No MX records — the domain can't receive mail (incl. bounces/replies).")
    if not checks["spf"]:
        recommendations.append("Add an SPF record (v=spf1 ...) authorizing your sending service.")
    if not checks["dkim"]:
        recommendations.append("Enable DKIM signing at your provider (couldn't detect a common selector).")
    if not checks["dmarc"]:
        recommendations.append("Publish a DMARC record at _dmarc.%s (start with p=none)." % domain)
    elif dmarc_policy == "none":
        recommendations.append("DMARC policy is p=none — consider tightening to quarantine/reject once aligned.")

    score = sum(1 for k in ("spf", "dkim", "dmarc") if checks[k])
    return {
        "domain": domain,
        "checks": checks,
        "records": {"spf": spf, "dmarc": dmarc, "dkim_selectors": dkim_selectors},
        "dmarc_policy": dmarc_policy,
        "auth_score": score,          # 0..3
        "recommendations": recommendations,
    }


def check_content(subject: str, body: str) -> dict:
    subject = subject or ""
    body = body or ""
    text = f"{subject}\n{body}"
    lower = text.lower()
    issues: list[str] = []

    found_spam = sorted({w for w in _SPAM_WORDS if w in lower})
    if found_spam:
        issues.append(f"Spam-trigger phrases: {', '.join(found_spam[:8])}")

    letters = [c for c in subject if c.isalpha()]
    if len(letters) >= 6 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        issues.append("Subject is mostly uppercase (shouty).")

    if text.count("!") > 3:
        issues.append("Excessive exclamation marks.")

    links = re.findall(r"https?://", body)
    if len(links) > 8:
        issues.append("Many links — high link density hurts deliverability.")

    if "{{" in body or "}}" in body:
        issues.append("Unrendered merge tags ({{...}}) remain in the body.")

    if "unsubscribe" not in lower:
        issues.append("No unsubscribe mention — add one (auto-injected when tracking is on).")

    words = len(re.findall(r"\w+", body))
    if words < 15:
        issues.append("Very short body — thin content can look like spam.")

    # 100 minus 12 per issue, floored at 0.
    score = max(0, 100 - 12 * len(issues))
    return {"score": score, "issues": issues, "word_count": words, "link_count": len(links)}
