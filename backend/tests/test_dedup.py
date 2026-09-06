"""Pure-function dedup tests — no DB required."""
from dataclasses import dataclass

from app.services import dedup


@dataclass
class L:
    id: str
    email: str | None = None
    linkedin_url: str | None = None
    phone: str | None = None
    full_name: str | None = None
    company_id: str | None = None


def test_email_match_case_insensitive():
    a = L("1", email="Jane@Acme.com")
    b = L("2", email="jane@acme.com  ")
    matched, mtype = dedup.is_duplicate(a, b)
    assert matched and mtype == "email"


def test_linkedin_match_normalizes_scheme_and_www():
    a = L("1", linkedin_url="https://www.linkedin.com/in/jane/")
    b = L("2", linkedin_url="linkedin.com/in/jane")
    matched, mtype = dedup.is_duplicate(a, b)
    assert matched and mtype == "linkedin"


def test_phone_match_ignores_formatting():
    a = L("1", phone="+1 (415) 555-0100")
    b = L("2", phone="+1-415-555-0100")
    matched, mtype = dedup.is_duplicate(a, b)
    assert matched and mtype == "phone"


def test_name_company_match():
    a = L("1", full_name="Jane Doe", company_id="c1")
    b = L("2", full_name="  jane   doe ", company_id="c1")
    matched, mtype = dedup.is_duplicate(a, b)
    assert matched and mtype == "name_company"


def test_name_without_company_does_not_match():
    a = L("1", full_name="Jane Doe")
    b = L("2", full_name="Jane Doe")
    matched, _ = dedup.is_duplicate(a, b)
    assert not matched


def test_no_match_distinct_people():
    a = L("1", email="a@x.com", full_name="A", company_id="c1")
    b = L("2", email="b@y.com", full_name="B", company_id="c2")
    matched, _ = dedup.is_duplicate(a, b)
    assert not matched


def test_email_precedence_over_name():
    a = L("1", email="same@x.com", full_name="Jane", company_id="c1")
    b = L("2", email="same@x.com", full_name="John", company_id="c2")
    matched, mtype = dedup.is_duplicate(a, b)
    assert matched and mtype == "email"


def test_find_duplicate_groups_transitive():
    leads = [
        L("1", email="jane@acme.com"),
        L("2", email="jane@acme.com", phone="+1500"),
        L("3", phone="+1500"),
        L("4", email="solo@x.com"),
    ]
    groups = dedup.find_duplicate_groups(leads)
    assert len(groups) == 1
    ids = set(groups[0]["lead_ids"])
    assert ids == {"1", "2", "3"}


def test_merge_field_prefers_primary():
    assert dedup.merge_field_values("primary", "dup") == "primary"
    assert dedup.merge_field_values(None, "dup") == "dup"
    assert dedup.merge_field_values("", "dup") == "dup"
