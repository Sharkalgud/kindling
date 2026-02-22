"""Tests for daemon.py"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import daemon


# ---------------------------------------------------------------------------
# check_internet tests
# ---------------------------------------------------------------------------


def test_check_internet_success():
    """Returns True when socket connection succeeds."""
    mock_conn = MagicMock()
    with patch("daemon.socket.create_connection", return_value=mock_conn) as mock_sock:
        result = daemon.check_internet()
    assert result is True
    mock_conn.close.assert_called_once()


def test_check_internet_failure():
    """Returns False when socket raises OSError (no network)."""
    with patch("daemon.socket.create_connection", side_effect=OSError("unreachable")):
        result = daemon.check_internet()
    assert result is False


# ---------------------------------------------------------------------------
# diagnose_error tests
# ---------------------------------------------------------------------------


def test_diagnose_error_rate_limit():
    """Rate limit errors are recognized by exception name."""
    class RateLimitError(Exception):
        pass

    exc = RateLimitError("Too many requests")
    msg = daemon.diagnose_error(exc)
    assert "Rate limit" in msg


def test_diagnose_error_unknown():
    """Unknown exception types fall through to a generic message."""
    exc = ValueError("some random error")
    msg = daemon.diagnose_error(exc)
    assert "ValueError" in msg
    assert "some random error" in msg


# ---------------------------------------------------------------------------
# maybe_send_digest tests
# ---------------------------------------------------------------------------


def _make_logger():
    import logging
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())
    return logger


def test_maybe_send_digest_skips_before_email_hour():
    """Digest is not sent when current hour < email_hour."""
    logger = _make_logger()
    with (
        patch("daemon.datetime") as mock_dt,
        patch("daemon.load_queue", return_value=[{"id": "a"}]),
        patch("daemon.send_digest") as mock_send,
        patch("daemon.clear_queue") as mock_clear,
    ):
        mock_dt.now.return_value.hour = 10  # Before email_hour=18
        daemon.maybe_send_digest(logger, email_hour=18)
    mock_send.assert_not_called()
    mock_clear.assert_not_called()


def test_maybe_send_digest_sends_at_email_hour():
    """Digest is sent and queue cleared when hour >= email_hour and not yet sent today."""
    logger = _make_logger()
    queue = [{"id": "a", "title": "Test"}]
    with (
        patch("daemon.datetime") as mock_dt,
        patch("daemon.load_config", return_value={}),
        patch("daemon.write_config") as mock_write_config,
        patch("daemon.load_queue", return_value=queue),
        patch("daemon.send_digest") as mock_send,
        patch("daemon.clear_queue") as mock_clear,
        patch.dict(os.environ, {"GMAIL_USER": "test@gmail.com", "GMAIL_APP_PASSWORD": "secret"}),
    ):
        mock_dt.now.return_value.hour = 18
        mock_dt.now.return_value.strftime.return_value = "2026-02-21"
        daemon.maybe_send_digest(logger, email_hour=18)
    mock_send.assert_called_once()
    mock_clear.assert_called_once()
    mock_write_config.assert_called_once()


def test_maybe_send_digest_skips_if_already_sent_today():
    """Digest is not sent a second time on the same day."""
    logger = _make_logger()
    with (
        patch("daemon.datetime") as mock_dt,
        patch("daemon.load_config", return_value={"last_digest_date": "2026-02-21"}),
        patch("daemon.send_digest") as mock_send,
    ):
        mock_dt.now.return_value.hour = 20
        mock_dt.now.return_value.strftime.return_value = "2026-02-21"
        daemon.maybe_send_digest(logger, email_hour=18)
    mock_send.assert_not_called()


def test_maybe_send_digest_skips_empty_queue():
    """Digest is not sent when the queue is empty."""
    logger = _make_logger()
    with (
        patch("daemon.datetime") as mock_dt,
        patch("daemon.load_config", return_value={}),
        patch("daemon.load_queue", return_value=[]),
        patch("daemon.send_digest") as mock_send,
        patch("daemon.clear_queue") as mock_clear,
    ):
        mock_dt.now.return_value.hour = 20
        mock_dt.now.return_value.strftime.return_value = "2026-02-21"
        daemon.maybe_send_digest(logger, email_hour=18)
    mock_send.assert_not_called()
    mock_clear.assert_not_called()
