# Kindling Research

A Python tool that reads Notion pages flagged for research, uses LLMs to extract questions and generate research reports, then writes the results back into Notion. Optionally, you can run it as a background process that give a daily digest of what has been researched at the end of the day.

## How it works

1. Queries a Notion database for pages with **Kindling Research** checkbox = true
2. Filters out pages that already have a `🪵 ✨Kindling Results` toggle block
3. For each unresearched page:
   - Reads the page title and body content
   - Uses **Claude Haiku** to extract research questions from the content
   - If questions are found, uses **GPT** (with web search) to produce a structured research report
   - Appends a green toggleable `🪵 ✨Kindling Results` heading to the Notion page containing the report

## Prerequisites

- Python 3.10+
- API keys for Notion, Anthropic, and OpenAI

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

See `.env.example` for the full list of required environment variables.

### Setting up your Notion database

1. Create a Notion integration at [notion.so/my-integrations](https://www.notion.so/my-integrations). Give it **Read content** and **Update content** capabilities.
2. Open your database in Notion and share it with your integration (click **...** → **Add connections** → select your integration).
3. Add a checkbox property named **Kindling Research** to your database. Pages with this checked will be picked up for research.
4. Find your database ID: open the database as a full page in your browser. The URL will look like `https://www.notion.so/yourworkspace/<database-id>?v=...`. The database ID is the 32-character hex string before the `?`. Copy it into `NOTION_DB_ID` in your `.env`.

## Modes of use

### On-demand (`research.py`)

Run the research pipeline interactively whenever you want:

```bash
python research.py
```

The script presents a terminal multi-select UI — use **Space** to select pages and **Enter** to confirm and start processing. A summary table with page names, status, cost, and Notion links is shown when done.

### Always-running background daemon (`daemon.py`)

Run the research pipeline automatically on a schedule and receive nightly email digests:

```bash
python daemon.py
```

The daemon:
- Polls Notion every N hours (default: 3) for unresearched pages
- Processes them oldest-first and appends results to `data/queue.json`
- Sends a digest email at a configured hour (default: 18:00) then clears the queue
- Writes rotating logs to `data/daemon.log` (10 MB × 3 backups)
- Responds to `SIGTERM` (graceful shutdown) and `SIGUSR1` (run cycle immediately)

#### Dashboard

The TUI dashboard lets you monitor and control the daemon interactively:

```bash
python dashboard.py
```

Actions available: start/stop/restart daemon, trigger an immediate cycle, change interval or email hour, view full logs.

#### Auto-start on login (macOS)

Run once after install to register a launchd agent that starts the daemon on login or restart of your computer:

```bash
bash setup_autostart.sh
```

Verify:
```bash
launchctl list | grep kindling
```

> **Note:** `setup_autostart.sh` uses `pyenv which python3` to get the absolute Python binary path, since launchd doesn't source `~/.zshrc`.

## Running tests

Unit tests (no API calls):

```bash
pytest tests/
```

Integration tests (require valid API keys in `.env`):

```bash
pytest tests/ -m integration
```
