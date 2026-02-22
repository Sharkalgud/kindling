# Kindling Research

A Python CLI that reads Notion pages flagged for research, uses LLMs to extract questions and generate research reports, then writes the results back into Notion as a toggle section.

## How it works

1. Queries the Notion Archives database for pages with **Kindling Research** checkbox = true
2. Filters out pages that already have a `🪵 ✨Kindling Results` toggle block
3. Presents a terminal multi-select UI to choose which pages to process
4. For each selected page:
   - Reads the page title and body content
   - Uses **Claude Haiku** to extract research questions from the content
   - If questions are found, uses **GPT-5.2** (with web search) to produce a structured research report
   - Appends a green toggleable `🪵 ✨Kindling Results` heading to the Notion page containing the report
5. Displays a summary table with page names, status, estimated cost, and Notion links

## Prerequisites

- Python 3.10+
- API keys for Notion, Anthropic, and OpenAI

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project directory:

```env
NOTION_API_KEY=ntn_your_notion_integration_token
ANTHROPIC_API_KEY=sk-ant-your_anthropic_key
OPENAI_API_KEY=sk-proj-your_openai_key
```

The Notion integration must have **read** and **write** access to the Archives database (`2dfbad37f86a8084ab59f42395094f3e`).

## Usage

```bash
python research.py
```

Use **Space** to select pages in the TUI, **Enter** to confirm and start processing.

## Background Daemon

The daemon runs the research pipeline automatically on a schedule and sends a nightly email digest.

```bash
python daemon.py
```

The daemon:
- Polls Notion every N hours (default: 3) for unresearched pages
- Processes them oldest-first and appends results to `data/queue.json`
- Sends a digest email at a configured hour (default: 18:00) then clears the queue
- Writes rotating logs to `data/daemon.log` (10 MB × 3 backups)
- Responds to `SIGTERM` (graceful shutdown) and `SIGUSR1` (run cycle immediately)

Add these to your `.env` for digest emails:
```env
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=your-google-app-password
```

## Dashboard

The TUI dashboard lets you monitor and control the daemon interactively:

```bash
python dashboard.py
```

Actions available: start/stop/restart daemon, trigger an immediate cycle, change interval or email hour, view full logs.

## Auto-start on login (macOS)

Run once after install to register a launchd agent that starts the daemon on login:

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

## Architecture

The processing pipeline is built with **LangGraph**:

```
extract_questions → (has questions?) → do_research → update_notion
                  ↘ (no questions)  ↗                      ↑
                                    → update_notion ────────┘
```

| Node | Model | Purpose |
|---|---|---|
| `extract_questions` | Claude Haiku (`claude-haiku-4-5-20251001`) | Extract research questions from page content |
| `do_research` | GPT-5.2 + web search | Produce a structured research report |
| `update_notion` | — | Write results back to Notion |

## Cost estimation

| Model | Input | Output |
|---|---|---|
| Claude Haiku | $0.80 / 1M tokens | $4.00 / 1M tokens |
| GPT-5.2 | $5.00 / 1M tokens (est.) | $15.00 / 1M tokens (est.) |

Actual cost is displayed in the results table after processing.
