"""Tests for core/email_utils.py"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.email_utils import (
    build_digest_text,
    extract_up_to_tldr,
    select_past_pages,
)

# ---------------------------------------------------------------------------
# Sample research text fixture
# ---------------------------------------------------------------------------

SAMPLE_RESEARCH = """\
## 1) Headline
Physical Therapy's Business Model Prevents the Stretch Lab Approach

## 2) Prompted by
Why don't PT practices follow the stretch lab model?

## 3) TL;DR
- PT clinics are reimbursement-driven, not subscription-driven.
- Stretch labs charge cash; PTs bill insurance.
- Regulatory scope limits what PTs can delegate.
- Patient outcomes data favors active rehab over passive stretching.

## 4) What I found
Physical therapy clinics operate in a fundamentally different business environment.
Insurance reimbursement drives scheduling and staffing decisions.

### 5) Open loops
- Does scope of practice vary enough by state to change the calculus?
- Are there hybrid PT/stretch models emerging?

### 6) Next rabbit holes
- Search: "direct-pay physical therapy business model"
- Review CMS reimbursement guidelines for 1:1 vs group PT sessions.

### 7) Recommended reads + More sources
- APTA business model survey 2023
- Stretch lab franchise disclosure document
"""

NO_SECTION_4_TEXT = """\
## 1) Headline
Short answer here

## 2) Prompted by
A question

## 3) TL;DR
- Bullet one
- Bullet two
"""


# ---------------------------------------------------------------------------
# extract_up_to_tldr tests
# ---------------------------------------------------------------------------


def test_extract_up_to_tldr_finds_section_4():
    """Result must not contain '## 4)' marker."""
    result = extract_up_to_tldr(SAMPLE_RESEARCH)
    assert "## 4)" not in result


def test_extract_up_to_tldr_includes_tldr_bullets():
    """TL;DR section should appear in the excerpt."""
    result = extract_up_to_tldr(SAMPLE_RESEARCH)
    assert "TL;DR" in result
    assert "PT clinics are reimbursement-driven" in result


def test_extract_up_to_tldr_fallback_on_missing_section():
    """When '## 4)' is absent, fall back to first 1000 chars."""
    result = extract_up_to_tldr(NO_SECTION_4_TEXT)
    assert len(result) <= 1000
    assert "Short answer here" in result


def test_extract_up_to_tldr_no_questions_text():
    """Works on the minimal 'no questions' output."""
    text = "No researchable questions were found in this page.\n\n*Processed: 2026-02-20 18:00 UTC*"
    result = extract_up_to_tldr(text)
    assert "No researchable questions" in result


# ---------------------------------------------------------------------------
# build_digest_text tests
# ---------------------------------------------------------------------------


def _make_record(title="Page A", url="https://notion.so/a", research_text=SAMPLE_RESEARCH,
                 cost=0.0123, any_error=None, processed_at="2026-02-20 18:00 UTC"):
    return {
        "id": "abc",
        "title": title,
        "url": url,
        "research_text": research_text,
        "cost": cost,
        "processed_at": processed_at,
        "any_error": any_error,
    }


def test_build_digest_text_contains_titles():
    """Digest includes title, URL, and cost; section 4 body should not appear."""
    queue = [_make_record("My Page", url="https://notion.so/page")]
    body = build_digest_text(queue)
    assert "My Page" in body
    assert "https://notion.so/page" in body
    assert "$0.0123" in body
    # Section 4 content should not be present (excerpt stops before it)
    assert "What I found" not in body


def test_build_digest_text_includes_errors():
    """Error string appears in the digest body for a failed record."""
    queue = [_make_record(any_error="Rate limit exceeded — will retry next cycle.")]
    body = build_digest_text(queue)
    assert "Rate limit exceeded" in body
    assert "Errors:" in body


def test_build_digest_text_total_cost():
    """Total cost is the sum of individual record costs."""
    queue = [
        _make_record("Page A", cost=0.01),
        _make_record("Page B", cost=0.03),
    ]
    body = build_digest_text(queue)
    assert "$0.0400" in body


# ---------------------------------------------------------------------------
# select_past_pages tests
# ---------------------------------------------------------------------------


def _make_page(title: str, created_time: str, url: str = "") -> dict:
    return {"title": title, "created_time": created_time, "url": url}


def test_select_past_pages_returns_all_when_fewer_than_n():
    """When there are ≤ n pages, all are returned."""
    pages = [_make_page("A", "2025-01-01"), _make_page("B", "2025-02-01")]
    result = select_past_pages(pages, n=3)
    assert len(result) == 2
    titles = {p["title"] for p in result}
    assert titles == {"A", "B"}


def test_select_past_pages_returns_n_pages():
    """Exactly n pages are returned when there are more than n."""
    pages = [_make_page(str(i), f"2025-0{i}-01") for i in range(1, 8)]
    result = select_past_pages(pages, n=3)
    assert len(result) == 3


def test_select_past_pages_no_duplicates():
    """Selected pages are distinct (no page chosen twice)."""
    pages = [_make_page(str(i), f"2025-0{i}-01") for i in range(1, 8)]
    result = select_past_pages(pages, n=3)
    titles = [p["title"] for p in result]
    assert len(titles) == len(set(titles))


def test_select_past_pages_exact_n_equals_pool():
    """When pool size == n, all pages are returned."""
    pages = [_make_page(str(i), f"2025-0{i}-01") for i in range(1, 4)]
    result = select_past_pages(pages, n=3)
    assert len(result) == 3


def test_select_past_pages_newer_bias():
    """Newer pages are selected more often than older ones across many trials."""
    import random as _random
    _random.seed(42)
    pages = [_make_page(str(i), f"2025-0{i:02d}-01") for i in range(1, 7)]
    # pages[0] is oldest, pages[5] is newest
    counts = {p["title"]: 0 for p in pages}
    for _ in range(300):
        selected = select_past_pages(pages, n=3)
        for p in selected:
            counts[p["title"]] += 1
    # The newest page should appear more than the oldest
    assert counts["6"] > counts["1"]


