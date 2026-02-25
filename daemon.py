"""Kindling Research Daemon

Background process that runs the research pipeline every N hours,
sends a nightly email digest, and persists results to a queue.
"""

import logging
import os
import signal
import socket
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
import anthropic
from openai import OpenAI

load_dotenv()

from core.config import (
    DATA_DIR,
    LOG_PATH,
    PID_PATH,
    load_config,
    write_config,
    load_queue,
    append_to_queue,
    clear_queue,
)
from core.notion_utils import (
    init_notion_client,
    fetch_research_pages,
    fetch_past_researched_pages,
    has_kindling_results_block,
    get_page_title,
    get_page_url,
    fetch_page_blocks_recursive,
    blocks_to_text,
)
from core.graph import build_research_graph
from core.email_utils import send_digest, send_past_digest, select_past_pages

# ---------------------------------------------------------------------------
# Globals for signal handling
# ---------------------------------------------------------------------------

_shutdown_requested = False
_immediate_cycle_requested = False


def _handle_sigterm(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True


def _handle_sigusr1(signum, frame):
    global _immediate_cycle_requested
    _immediate_cycle_requested = True


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging() -> logging.Logger:
    """Configure rotating file + stderr logging."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("kindling.daemon")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stderr_handler)
    return logger


# ---------------------------------------------------------------------------
# PID management
# ---------------------------------------------------------------------------


def write_pid() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))


def remove_pid() -> None:
    try:
        PID_PATH.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Connectivity check
# ---------------------------------------------------------------------------


def check_internet(host: str = "8.8.8.8", port: int = 53, timeout: float = 3.0) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout seconds."""
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Error diagnosis
# ---------------------------------------------------------------------------


def diagnose_error(exc: Exception) -> str:
    """Map common exception types to human-readable strings."""
    name = type(exc).__name__
    msg = str(exc)

    if "RateLimitError" in name or "rate_limit" in msg.lower():
        return f"Rate limit exceeded — will retry next cycle. ({msg})"
    if "AuthenticationError" in name or "authentication" in msg.lower():
        return f"API authentication failed — check your API keys. ({msg})"
    if "ConnectionError" in name or "connection" in msg.lower():
        return f"Network connection error — check internet access. ({msg})"
    if "TimeoutError" in name or "timeout" in msg.lower():
        return f"Request timed out — API may be slow. ({msg})"
    if "NotionClientError" in name or "notion" in name.lower():
        return f"Notion API error: {msg}"
    return f"Unexpected error ({name}): {msg}"


# ---------------------------------------------------------------------------
# Research cycle
# ---------------------------------------------------------------------------


def run_research_cycle(
    logger: logging.Logger,
    anthropic_client: anthropic.Anthropic,
    openai_client: OpenAI,
) -> None:
    """Fetch unresearched Notion pages and run the research pipeline on each."""
    logger.info("Starting research cycle")

    if not check_internet():
        logger.warning("No internet connectivity — skipping cycle")
        return

    try:
        notion = init_notion_client()
        pages = fetch_research_pages(notion)
    except Exception as exc:
        logger.error("Failed to fetch pages from Notion: %s", exc)
        return

    # Sort by created_time ascending (oldest first)
    pages.sort(key=lambda p: p.get("created_time", ""))

    # Filter out already-processed pages
    unprocessed = []
    for page in pages:
        try:
            if not has_kindling_results_block(notion, page["id"]):
                unprocessed.append(page)
        except Exception as exc:
            logger.warning("Could not check page %s: %s", page.get("id"), exc)

    logger.info("Found %d unprocessed page(s)", len(unprocessed))

    if not unprocessed:
        logger.info("No unprocessed pages — cycle complete")
        return

    graph = build_research_graph(anthropic_client, openai_client, notion)

    for page in unprocessed:
        page_id = page["id"]
        page_title = get_page_title(page)
        page_url = get_page_url(page)

        logger.info("Processing page: %s", page_title)

        record = {
            "id": page_id,
            "title": page_title,
            "url": page_url,
            "research_text": None,
            "cost": 0.0,
            "processed_at": datetime.utcnow().isoformat(),
            "any_error": None,
        }

        try:
            blocks = fetch_page_blocks_recursive(notion, page_id)
            page_content = blocks_to_text(blocks)

            from core.graph import ResearchState
            initial_state: ResearchState = {
                "page_id": page_id,
                "page_title": page_title,
                "page_content": page_content,
                "questions": None,
                "research_result": None,
                "has_questions": False,
                "extraction_tokens": {},
                "research_tokens": {},
                "cost_estimate": 0.0,
                "processed_at": "",
            }

            final_state = graph.invoke(initial_state)

            record["research_text"] = final_state.get("research_result")
            record["cost"] = final_state.get("cost_estimate", 0.0)
            record["processed_at"] = final_state.get("processed_at", record["processed_at"])

            logger.info(
                "Completed: %s (cost: $%.4f)",
                page_title,
                record["cost"],
            )

        except Exception as exc:
            error_msg = diagnose_error(exc)
            record["any_error"] = error_msg
            logger.error("Error processing '%s': %s", page_title, error_msg)

        append_to_queue(record)

    logger.info("Research cycle complete")


# ---------------------------------------------------------------------------
# Email digest
# ---------------------------------------------------------------------------


def maybe_send_digest(logger: logging.Logger, email_hour: int) -> None:
    """Send digest if current hour >= email_hour and not already sent today.

    If the queue has new research, sends the normal digest.
    If the queue is empty, selects 3 past researched pages and sends a reminder digest.
    """
    now = datetime.now()
    if now.hour < email_hour:
        return

    today = now.strftime("%Y-%m-%d")
    config = load_config()
    if config.get("last_digest_date") == today:
        logger.debug("Digest already sent today — skipping")
        return

    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not gmail_user or not gmail_app_password:
        logger.warning("Digest skipped: GMAIL_USER or GMAIL_APP_PASSWORD not set")
        return

    queue = load_queue()
    if queue:
        try:
            send_digest(queue, gmail_user, gmail_app_password)
            clear_queue()
            config["last_digest_date"] = today
            write_config(config)
            logger.info("Digest sent to %s, queue cleared (%d records)", gmail_user, len(queue))
        except Exception as exc:
            logger.error("Failed to send digest: %s", exc)
    else:
        # No new research today — send a past pages reminder instead
        try:
            notion = init_notion_client()
            past_pages = fetch_past_researched_pages(notion)
        except Exception as exc:
            logger.error("Failed to fetch past pages from Notion: %s", exc)
            return

        if not past_pages:
            logger.debug("Past digest skipped: no past researched pages available")
            return

        selected = select_past_pages(past_pages, n=3)
        records = []
        for p in selected:
            page_id = p["id"]
            page_title = get_page_title(p)
            page_url = get_page_url(p)
            try:
                blocks = fetch_page_blocks_recursive(notion, page_id)
                research_text = blocks_to_text(blocks)
            except Exception as exc:
                logger.warning("Could not fetch blocks for past page '%s': %s", page_title, exc)
                research_text = None
            records.append({
                "title": page_title,
                "url": page_url,
                "research_text": research_text,
                "cost": 0.0,
                "processed_at": p.get("created_time", "")[:10],
                "any_error": None,
            })
        try:
            send_past_digest(records, gmail_user, gmail_app_password)
            config["last_digest_date"] = today
            write_config(config)
            logger.info("Past digest sent to %s (%d pages)", gmail_user, len(page_dicts))
        except Exception as exc:
            logger.error("Failed to send past digest: %s", exc)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    logger = setup_logging()
    logger.info("Daemon starting (PID %d)", os.getpid())

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGUSR1, _handle_sigusr1)

    write_pid()
    try:
        anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        last_run_time: float = 0.0  # Run immediately on first iteration

        while not _shutdown_requested:
            global _immediate_cycle_requested

            config = load_config()
            interval_hours = config.get("interval_hours", 3)
            email_hour = config.get("email_hour", 18)
            interval_seconds = interval_hours * 3600

            now = time.time()
            should_run = (now - last_run_time >= interval_seconds) or _immediate_cycle_requested

            if should_run:
                _immediate_cycle_requested = False
                last_run_time = time.time()
                run_research_cycle(logger, anthropic_client, openai_client)
                maybe_send_digest(logger, email_hour)

            # Sleep in 1-second increments to stay signal-responsive
            for _ in range(60):
                if _shutdown_requested or _immediate_cycle_requested:
                    break
                time.sleep(1)

        logger.info("Daemon shutting down cleanly")

    finally:
        remove_pid()
        logger.info("Daemon stopped")


if __name__ == "__main__":
    main()
