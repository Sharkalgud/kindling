"""Kindling Research Dashboard

TUI for monitoring and controlling the background daemon.
"""

import os
import signal
import subprocess
import sys
import time
from datetime import datetime

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.config import DATA_DIR, LOG_PATH, PID_PATH, load_config, write_config

console = Console()


# ---------------------------------------------------------------------------
# PID utilities
# ---------------------------------------------------------------------------


def read_pid() -> int | None:
    """Read PID from file and verify the process is alive. Returns None if not running."""
    if not PID_PATH.exists():
        return None
    try:
        pid = int(PID_PATH.read_text().strip())
        os.kill(pid, 0)  # Raises OSError if process doesn't exist
        return pid
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Log utilities
# ---------------------------------------------------------------------------


def read_last_log_lines(n: int = 15) -> list[str]:
    """Read the last N lines from the daemon log file."""
    if not LOG_PATH.exists():
        return ["(no log file found)"]
    try:
        text = LOG_PATH.read_text(errors="replace")
        lines = text.splitlines()
        return lines[-n:] if lines else ["(log file is empty)"]
    except OSError:
        return ["(could not read log file)"]


def get_last_log_timestamp() -> str:
    """Return the timestamp of the most recent log entry."""
    lines = read_last_log_lines(1)
    if lines and lines[0] and not lines[0].startswith("("):
        return lines[0][:19]  # "YYYY-MM-DD HH:MM:SS"
    return "—"


# ---------------------------------------------------------------------------
# Status panel
# ---------------------------------------------------------------------------


def render_status() -> None:
    """Print the current daemon status panel."""
    pid = read_pid()
    config = load_config()

    status_text = Text()
    if pid:
        status_text.append("● RUNNING", style="bold green")
        status_text.append(f"  (PID {pid})", style="dim")
    else:
        status_text.append("○ STOPPED", style="bold red")

    last_ts = get_last_log_timestamp()
    interval = config.get("interval_hours", 3)
    email_hour = config.get("email_hour", 18)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Status", status_text)
    table.add_row("Last log entry", last_ts)
    table.add_row("Interval", f"{interval}h")
    table.add_row("Email hour", f"{email_hour}:00")

    console.print(Panel(table, title="[bold]🪵 Kindling Daemon[/bold]", border_style="green"))

    log_lines = read_last_log_lines(15)
    console.print("[bold]Recent logs:[/bold]")
    for line in log_lines:
        console.print(f"  [dim]{line}[/dim]")
    console.print()


# ---------------------------------------------------------------------------
# Daemon control
# ---------------------------------------------------------------------------


def start_daemon() -> None:
    subprocess.Popen(
        [sys.executable, str(DATA_DIR.parent / "daemon.py")],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(1)
    pid = read_pid()
    if pid:
        console.print(f"[green]Daemon started (PID {pid})[/green]")
    else:
        console.print("[yellow]Daemon may have failed to start — check logs[/yellow]")


def stop_daemon(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[yellow]Sent SIGTERM to PID {pid}[/yellow]")
    except OSError as exc:
        console.print(f"[red]Could not stop daemon: {exc}[/red]")


def run_now(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGUSR1)
        console.print("[green]Sent SIGUSR1 — daemon will run cycle immediately[/green]")
    except OSError as exc:
        console.print(f"[red]Could not signal daemon: {exc}[/red]")


# ---------------------------------------------------------------------------
# Config changes
# ---------------------------------------------------------------------------


def change_interval() -> None:
    answer = questionary.text(
        "New interval in hours (positive integer):",
        validate=lambda v: v.isdigit() and int(v) > 0 or "Enter a positive integer",
    ).ask()
    if answer is None:
        return
    config = load_config()
    config["interval_hours"] = int(answer)
    write_config(config)
    console.print(f"[green]Interval updated to {answer}h[/green]")


def change_email_hour() -> None:
    answer = questionary.text(
        "New email hour (0–23):",
        validate=lambda v: v.isdigit() and 0 <= int(v) <= 23 or "Enter a number between 0 and 23",
    ).ask()
    if answer is None:
        return
    config = load_config()
    config["email_hour"] = int(answer)
    write_config(config)
    console.print(f"[green]Email hour updated to {answer}:00[/green]")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    console.print("[bold green]🪵 Kindling Dashboard[/bold green]")

    while True:
        console.rule()
        render_status()

        pid = read_pid()
        daemon_running = pid is not None

        choices = []
        if daemon_running:
            choices += [
                questionary.Choice("Stop daemon", value="stop"),
                questionary.Choice("Restart daemon", value="restart"),
                questionary.Choice("Run now (immediate cycle)", value="run_now"),
            ]
        else:
            choices.append(questionary.Choice("Start daemon", value="start"))

        choices += [
            questionary.Choice("Change interval", value="change_interval"),
            questionary.Choice("Change email hour", value="change_email_hour"),
            questionary.Choice("View full logs", value="view_logs"),
            questionary.Choice("Refresh", value="refresh"),
            questionary.Choice("Exit", value="exit"),
        ]

        action = questionary.select("Action:", choices=choices).ask()

        if action is None or action == "exit":
            break
        elif action == "start":
            start_daemon()
        elif action == "stop":
            stop_daemon(pid)
        elif action == "restart":
            stop_daemon(pid)
            time.sleep(2)
            start_daemon()
        elif action == "run_now":
            run_now(pid)
        elif action == "change_interval":
            change_interval()
        elif action == "change_email_hour":
            change_email_hour()
        elif action == "view_logs":
            os.system(f'less +G "{LOG_PATH}"')
        elif action == "refresh":
            pass  # Loop re-renders status


if __name__ == "__main__":
    main()
