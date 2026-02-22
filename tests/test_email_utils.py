"""Tests for core/email_utils.py"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.email_utils import build_digest_text, extract_up_to_tldr

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
