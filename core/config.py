"""Core configuration: constants, paths, and data I/O helpers."""

import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_PATH = DATA_DIR / "config.json"
QUEUE_PATH = DATA_DIR / "queue.json"
PID_PATH = DATA_DIR / "daemon.pid"
LOG_PATH = DATA_DIR / "daemon.log"

# ---------------------------------------------------------------------------
# LLM constants
# ---------------------------------------------------------------------------

NOTION_DB_ID = os.environ["NOTION_DB_ID"]
HAIKU_MODEL = "claude-haiku-4-5-20251001"
GPT_MODEL = "gpt-5.2"
HAIKU_COST_PER_M_INPUT = 0.80
HAIKU_COST_PER_M_OUTPUT = 4.00
GPT_COST_PER_M_INPUT = 5.00
GPT_COST_PER_M_OUTPUT = 15.00

EXTRACTION_PROMPT_TEMPLATE = """{title}
{content}

<Task>
Given the text above, extract the question or the questions the author mentioned in it. Make sure to extract any details from the text that will aid in providing as direct of an answer as possible. Write the questions as a paragraph in the first person
</Task>"""

RESEARCH_PROMPT_TEMPLATE = """{questions}

<Task>
You are an automated research assistant. Given the brief above containing one or more questions, produce a single short "article" that the user can read in ~5 minutes that achieves the following goals:

\t- Provide the best preliminary answer you can from public information.
\t- If a definitive answer is too complex/uncertain, give a high-level but useful take and clearly indicate uncertainty.
\t- Encourage further exploration with concrete next steps.
</Task>

<Tools>
- Use web research iteratively as needed: search, read, refine searches to resolve contradictions and find primary/authoritative sources.
- Stop when you reach diminishing returns (new sources are repetitive or not improving confidence).
- If the answer isn't knowable from public sources, say so and move to "Open loops" + "Next rabbit holes".
</Tools>

<Constraints>
- Target total length: ~700-900 words (approximate).
- Write in clear, direct language suitable for a daily newsletter.
- Use citations/links only to support the narrative; do not output just links.
</Constraints>

<Output Format>
You MUST provide all sections below in this order.

## 1) Headline
- Write a punchy, answer-shaped headline.
- Do NOT simply repeat the question verbatim.

## 2) Prompted by
- Include the original question(s) that triggered the research.
- Use the literal question if short; otherwise paraphrase crisply.
- If multiple questions exist, choose one primary question and optionally append "(+N related)".

## 3) TL;DR
- 4-6 decisive bullets.
- Bullet 1 should be the best direct answer or best current take.
- Include 1-2 key caveats if needed, but do not over-hedge.

## 4) What I found
**Objective:** Deliver the best preliminary answer in a way that updates the user's understanding and helps them decide what to do next.
Requirements:
- Answer-first: state the most likely answer/explanation early (even if partial).
- Explain the "why": include the minimal reasoning/mechanism that makes the answer make sense.
- Ground key claims in evidence; cite sources where relevant.
- Scope it: specify conditions/assumptions/boundaries where the answer applies.
- Surface major tradeoffs/competing views when relevant.
- Keep it digestible: typically 2-4 short paragraphs, but adapt structure to the question type.
- Avoid exhaustive background, literature-review style writing, or long tangents.
- Avoid excessive hedging; reserve most uncertainty details for "Open loops".

### 5) Open loops
- 2-4 bullets.
- Capture the most important uncertainties, disagreements, missing data, or edge cases.
- Phrase as crisp open questions when possible.

### 6) Next rabbit holes
- 3-5 items.
- Each item must include at least one of:
  - a suggested follow-up query the user could search
  - the type of source to consult (primary spec, review paper, standard, official guidance, etc.)
  - a decision criterion / test / red flag to look for
- Make these actionable, not generic.

### 7) Recommended reads + More sources
- Recommended reads: Top 3 sources the user should click first.
- More sources: Up to 7 additional sources (max total sources = 10).
- Prefer primary sources and high-quality references.
- No giant bibliography.

</Output Format>"""

# ---------------------------------------------------------------------------
# Email constants
# ---------------------------------------------------------------------------

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
DIGEST_RECIPIENT = "sarkalgud@gmail.com"

# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

_CONFIG_DEFAULTS = {"interval_hours": 3, "email_hour": 18}


def load_config() -> dict:
    """Read data/config.json; create with defaults if missing or malformed; merge missing keys."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = {}
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text())
            if not isinstance(config, dict):
                config = {}
        except (json.JSONDecodeError, OSError):
            config = {}

    # Merge any missing keys from defaults
    updated = False
    for key, value in _CONFIG_DEFAULTS.items():
        if key not in config:
            config[key] = value
            updated = True

    if updated or not CONFIG_PATH.exists():
        write_config(config)

    return config


def write_config(config: dict) -> None:
    """Atomically write config to data/config.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=2)
        os.replace(tmp_path, CONFIG_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Queue I/O
# ---------------------------------------------------------------------------

# Queue record schema:
# {id, title, url, research_text, cost, processed_at, any_error}


def load_queue() -> list:
    """Read data/queue.json; return [] if missing or malformed."""
    if not QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(QUEUE_PATH.read_text())
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def append_to_queue(record: dict) -> None:
    """Atomically append a record to data/queue.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    queue = load_queue()
    queue.append(record)
    _write_queue(queue)


def clear_queue() -> None:
    """Atomically write an empty list to data/queue.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write_queue([])


def _write_queue(queue: list) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(queue, f, indent=2)
        os.replace(tmp_path, QUEUE_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
