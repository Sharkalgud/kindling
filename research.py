"""Kindling Research Script

Reads Notion pages flagged for research, uses LLMs to extract questions
and generate research reports, then writes results back to Notion.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from notion_client import Client as NotionClient
import anthropic
from openai import OpenAI
import questionary
from rich.console import Console
from rich.table import Table

load_dotenv()

console = Console()

# Re-exports from core/ (keep existing names for backward compatibility)
from core.config import (
    NOTION_DB_ID,
    HAIKU_MODEL,
    GPT_MODEL,
    HAIKU_COST_PER_M_INPUT,
    HAIKU_COST_PER_M_OUTPUT,
    GPT_COST_PER_M_INPUT,
    GPT_COST_PER_M_OUTPUT,
    EXTRACTION_PROMPT_TEMPLATE,
    RESEARCH_PROMPT_TEMPLATE,
)
from core.notion_utils import (
    get_page_title,
    get_page_url,
    blocks_to_text,
    has_kindling_results_block,
    fetch_page_blocks_recursive,
    fetch_research_pages,
    init_notion_client,
)
from core.markdown_utils import (
    markdown_to_notion_blocks,
    _parse_rich_text,
    _split_text_chunks,
)
from core.graph import (
    ResearchState,
    estimate_cost,
    write_results_to_notion,
    build_research_graph,
)

# Module-level clients (initialized in main or tests)
_notion: Optional[NotionClient] = None
_anthropic_client: Optional[anthropic.Anthropic] = None
_openai_client: Optional[OpenAI] = None


def init_clients() -> None:
    """Initialize API clients from environment variables."""
    global _notion, _anthropic_client, _openai_client
    _notion = init_notion_client()
    _anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def main() -> None:
    """Main entry point: fetch pages, show TUI, process selected pages."""
    init_clients()

    console.print("[bold green]🪵 Kindling Research[/bold green]")
    console.print("Fetching pages from Notion...")

    pages = fetch_research_pages(_notion)

    if not pages:
        console.print("[yellow]No pages found with the Kindling Research flag.[/yellow]")
        return

    console.print(f"Found {len(pages)} flagged page(s). Checking for already-processed pages...")

    unprocessed_pages = []
    for page in pages:
        if not has_kindling_results_block(_notion, page["id"]):
            unprocessed_pages.append(page)

    if not unprocessed_pages:
        console.print("[yellow]All flagged pages have already been processed.[/yellow]")
        return

    choices = [
        questionary.Choice(title=get_page_title(page), value=page)
        for page in unprocessed_pages
    ]

    selected_pages = questionary.checkbox(
        "Select pages to research (space to select, enter to confirm):",
        choices=choices,
    ).ask()

    if not selected_pages:
        console.print("[yellow]No pages selected. Exiting.[/yellow]")
        return

    graph = build_research_graph(_anthropic_client, _openai_client, _notion, console)
    results = []

    for page in selected_pages:
        page_id = page["id"]
        page_title = get_page_title(page)
        page_url = get_page_url(page)

        console.print(f"\n[bold]Processing:[/bold] {page_title}")

        blocks = fetch_page_blocks_recursive(_notion, page_id)
        page_content = blocks_to_text(blocks)

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

        status = "✅ Researched" if final_state.get("has_questions") else "⚠️  No questions"
        results.append(
            {
                "title": page_title,
                "status": status,
                "cost": f"${final_state.get('cost_estimate', 0.0):.4f}",
                "url": page_url,
            }
        )

    console.print()
    table = Table(title="Research Results", show_lines=True)
    table.add_column("Page", style="bold", no_wrap=False)
    table.add_column("Status")
    table.add_column("Cost", justify="right")
    table.add_column("Notion Link")

    for r in results:
        table.add_row(r["title"], r["status"], r["cost"], r["url"])

    console.print(table)


if __name__ == "__main__":
    main()
