"""Kindling Research Script

Reads Notion pages flagged for research, uses LLMs to extract questions
and generate research reports, then writes results back to Notion.
"""

import os
import re
from datetime import datetime, timezone
from typing import TypedDict, Optional

from dotenv import load_dotenv
from notion_client import Client as NotionClient
from notion_client.client import ClientOptions
import anthropic
from openai import OpenAI
from langgraph.graph import StateGraph, END
import questionary
from rich.console import Console
from rich.table import Table

load_dotenv()

console = Console()

# Constants
NOTION_DB_ID = "2dfbad37f86a8084ab59f42395094f3e"
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

# Module-level clients (initialized in main or tests)
_notion: Optional[NotionClient] = None
_anthropic_client: Optional[anthropic.Anthropic] = None
_openai_client: Optional[OpenAI] = None


# ---------------------------------------------------------------------------
# Notion utilities
# ---------------------------------------------------------------------------

def get_page_title(page: dict) -> str:
    """Get the title of a Notion page from its properties."""
    properties = page.get("properties", {})
    for prop in properties.values():
        if prop.get("type") == "title":
            title_items = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in title_items)
    return "Untitled"


def get_page_url(page: dict) -> str:
    """Get the URL of a Notion page."""
    return page.get("url", "")


def blocks_to_text(blocks: list) -> str:
    """Convert a list of Notion block objects to plain text."""
    lines = []
    for block in blocks:
        block_type = block.get("type", "")
        if block_type in ("heading_1", "heading_2", "heading_3"):
            level = int(block_type[-1])
            texts = block.get(block_type, {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in texts)
            if text:
                lines.append(f"{'#' * level} {text}")
        elif block_type == "paragraph":
            texts = block.get("paragraph", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in texts)
            if text:
                lines.append(text)
        elif block_type == "bulleted_list_item":
            texts = block.get("bulleted_list_item", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in texts)
            if text:
                lines.append(f"- {text}")
        elif block_type == "numbered_list_item":
            texts = block.get("numbered_list_item", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in texts)
            if text:
                lines.append(f"1. {text}")
        elif block_type == "code":
            texts = block.get("code", {}).get("rich_text", [])
            code = "".join(t.get("plain_text", "") for t in texts)
            lang = block.get("code", {}).get("language", "")
            if code:
                lines.append(f"```{lang}\n{code}\n```")
        elif block_type == "quote":
            texts = block.get("quote", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in texts)
            if text:
                lines.append(f"> {text}")
        elif block_type == "toggle":
            texts = block.get("toggle", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in texts)
            if text:
                lines.append(text)
        elif block_type == "callout":
            texts = block.get("callout", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in texts)
            if text:
                lines.append(text)
        elif block_type == "divider":
            lines.append("---")
    return "\n".join(lines)


def has_kindling_results_block(notion: NotionClient, page_id: str) -> bool:
    """Check if a Notion page already has a 🪵 ✨Kindling Results toggle block."""
    response = notion.blocks.children.list(block_id=page_id)
    for block in response.get("results", []):
        if block.get("type") == "heading_2":
            h2 = block.get("heading_2", {})
            if h2.get("is_toggleable", False):
                texts = h2.get("rich_text", [])
                text = "".join(t.get("plain_text", "") for t in texts)
                if "🪵 ✨Kindling Results" in text:
                    return True
    return False


def fetch_page_blocks_recursive(notion: NotionClient, block_id: str, depth: int = 0) -> list:
    """Fetch all blocks from a Notion page, recursively including children."""
    if depth > 3:
        return []

    blocks = []
    cursor = None

    while True:
        kwargs: dict = {"block_id": block_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.blocks.children.list(**kwargs)
        page_blocks = response.get("results", [])

        for block in page_blocks:
            blocks.append(block)
            if block.get("has_children") and block.get("type") not in (
                "child_page",
                "child_database",
            ):
                child_blocks = fetch_page_blocks_recursive(notion, block["id"], depth + 1)
                blocks.extend(child_blocks)

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return blocks


def fetch_research_pages(notion: NotionClient) -> list:
    """Fetch all pages with the Kindling Research checkbox set in the Notion database."""
    pages = []
    cursor = None

    while True:
        body: dict = {
            "filter": {
                "property": "Kindling Research",
                "checkbox": {"equals": True},
            },
        }
        if cursor:
            body["start_cursor"] = cursor

        response = notion.request(
            path=f"databases/{NOTION_DB_ID}/query",
            method="POST",
            body=body,
        )
        pages.extend(response.get("results", []))

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return pages


# ---------------------------------------------------------------------------
# Markdown → Notion blocks converter
# ---------------------------------------------------------------------------

def _split_text_chunks(text: str) -> list:
    """Split text into 2000-char segments to respect Notion's rich_text limit."""
    if not text:
        return []
    chunks = []
    for i in range(0, len(text), 2000):
        chunk = text[i : i + 2000]
        if chunk:
            chunks.append({"type": "text", "text": {"content": chunk}})
    return chunks


def _parse_rich_text(text: str) -> list:
    """Parse markdown inline syntax into Notion rich_text segments.

    Handles: ***bold+italic***, **bold**, *italic*, `code`, [link](url).
    Order matters — longer patterns must come before shorter ones.
    """
    if not text:
        return [{"type": "text", "text": {"content": ""}}]

    rich_text = []
    pattern = re.compile(
        r"\*\*\*(.+?)\*\*\*"           # ***bold + italic***
        r"|\*\*(.+?)\*\*"              # **bold**
        r"|\*(.+?)\*"                  # *italic*
        r"|`([^`]+)`"                  # `inline code`
        r"|\[([^\]]+)\]\(([^)]+)\)",   # [link](url)
        re.DOTALL,
    )
    last_end = 0

    for m in pattern.finditer(text):
        # Plain text before this match
        if m.start() > last_end:
            rich_text.extend(_split_text_chunks(text[last_end : m.start()]))

        if m.group(1) is not None:  # ***bold + italic***
            for seg in _split_text_chunks(m.group(1)):
                seg["annotations"] = {"bold": True, "italic": True}
                rich_text.append(seg)
        elif m.group(2) is not None:  # **bold**
            for seg in _split_text_chunks(m.group(2)):
                seg["annotations"] = {"bold": True}
                rich_text.append(seg)
        elif m.group(3) is not None:  # *italic*
            for seg in _split_text_chunks(m.group(3)):
                seg["annotations"] = {"italic": True}
                rich_text.append(seg)
        elif m.group(4) is not None:  # `code`
            for seg in _split_text_chunks(m.group(4)):
                seg["annotations"] = {"code": True}
                rich_text.append(seg)
        else:  # [link](url)
            link_text = m.group(5)[:2000]
            link_url = m.group(6)
            rich_text.append(
                {"type": "text", "text": {"content": link_text, "link": {"url": link_url}}}
            )

        last_end = m.end()

    if last_end < len(text):
        rich_text.extend(_split_text_chunks(text[last_end:]))

    return rich_text or [{"type": "text", "text": {"content": text[:2000]}}]


def markdown_to_notion_blocks(markdown: str) -> list:
    """Convert a markdown string to a list of Notion block objects."""
    blocks = []
    lines = markdown.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code = "\n".join(code_lines)
            blocks.append(
                {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": code[:2000]}}],
                        "language": lang if lang else "plain text",
                    },
                }
            )

        # Heading 3
        elif line.startswith("### "):
            text = line[4:].strip()
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {"rich_text": _parse_rich_text(text)},
                }
            )

        # Heading 2
        elif line.startswith("## "):
            text = line[3:].strip()
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": _parse_rich_text(text)},
                }
            )

        # Heading 1
        elif line.startswith("# "):
            text = line[2:].strip()
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {"rich_text": _parse_rich_text(text)},
                }
            )

        # Bullet list
        elif line.startswith("- ") or line.startswith("* "):
            text = line[2:].strip()
            blocks.append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _parse_rich_text(text)},
                }
            )

        # Numbered list
        elif re.match(r"^\d+\. ", line):
            text = re.sub(r"^\d+\. ", "", line).strip()
            blocks.append(
                {
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": _parse_rich_text(text)},
                }
            )

        # Horizontal rule
        elif line.strip() in ("---", "***", "___"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        # Empty line — skip
        elif not line.strip():
            pass

        # Paragraph
        else:
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": _parse_rich_text(line)},
                }
            )

        i += 1

    return blocks


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

def estimate_cost(extraction_tokens: dict, research_tokens: dict) -> float:
    """Estimate the total USD cost of API calls given token usage dicts."""
    haiku_input = extraction_tokens.get("input", 0)
    haiku_output = extraction_tokens.get("output", 0)
    gpt_input = research_tokens.get("input", 0)
    gpt_output = research_tokens.get("output", 0)

    haiku_cost = (
        haiku_input * HAIKU_COST_PER_M_INPUT + haiku_output * HAIKU_COST_PER_M_OUTPUT
    ) / 1_000_000
    gpt_cost = (
        gpt_input * GPT_COST_PER_M_INPUT + gpt_output * GPT_COST_PER_M_OUTPUT
    ) / 1_000_000

    return haiku_cost + gpt_cost


# ---------------------------------------------------------------------------
# Notion write
# ---------------------------------------------------------------------------

def write_results_to_notion(notion: NotionClient, page_id: str, content_markdown: str) -> None:
    """Append a toggleable 🪵 ✨Kindling Results heading_2 block to a Notion page."""
    # Create the toggle heading
    response = notion.blocks.children.append(
        block_id=page_id,
        children=[
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "🪵 ✨Kindling Results"}}
                    ],
                    "is_toggleable": True,
                    "color": "green_background",
                },
            }
        ],
    )
    toggle_block_id = response["results"][0]["id"]

    content_blocks = markdown_to_notion_blocks(content_markdown)
    if not content_blocks:
        return

    # Append in batches of 100 (Notion API limit)
    for i in range(0, len(content_blocks), 100):
        batch = content_blocks[i : i + 100]
        notion.blocks.children.append(block_id=toggle_block_id, children=batch)


# ---------------------------------------------------------------------------
# LangGraph state machine
# ---------------------------------------------------------------------------

class ResearchState(TypedDict):
    page_id: str
    page_title: str
    page_content: str
    questions: Optional[str]
    research_result: Optional[str]
    has_questions: bool
    extraction_tokens: dict
    research_tokens: dict
    cost_estimate: float
    processed_at: str


_NO_QUESTION_PHRASES = [
    "no question",
    "no questions",
    "does not contain any question",
    "doesn't contain any question",
    "no specific question",
    "i don't see any question",
    "i cannot find",
    "no researchable",
    "cannot identify any question",
]


def extract_questions_node(state: ResearchState) -> dict:
    """Extract research questions from page content using Claude Haiku."""
    console.print(f"[cyan]  Extracting questions...[/cyan]")

    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        title=state["page_title"],
        content=state["page_content"],
    )

    message = _anthropic_client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    questions = message.content[0].text.strip()
    extraction_tokens = {
        "input": message.usage.input_tokens,
        "output": message.usage.output_tokens,
    }

    has_questions = len(questions) > 30 and not any(
        phrase in questions.lower() for phrase in _NO_QUESTION_PHRASES
    )

    return {
        "questions": questions if has_questions else None,
        "has_questions": has_questions,
        "extraction_tokens": extraction_tokens,
    }


def do_research_node(state: ResearchState) -> dict:
    """Research questions using GPT via the OpenAI Responses API with web search."""
    console.print(f"[cyan]  Researching with web search...[/cyan]")

    prompt = RESEARCH_PROMPT_TEMPLATE.format(questions=state["questions"])

    response = _openai_client.responses.create(
        model=GPT_MODEL,
        tools=[{"type": "web_search_preview"}],
        reasoning={"effort": "high"},
        input=prompt,
    )

    research_text = response.output_text
    research_tokens = {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    }

    return {
        "research_result": research_text,
        "research_tokens": research_tokens,
    }


def update_notion_node(state: ResearchState) -> dict:
    """Write research results back to the Notion page."""
    console.print(f"[cyan]  Writing results to Notion...[/cyan]")

    processed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cost = estimate_cost(
        state.get("extraction_tokens", {}),
        state.get("research_tokens", {}),
    )

    if state.get("has_questions") and state.get("research_result"):
        content = (
            state["research_result"]
            + f"\n\n---\n\n*Processed: {processed_at} | Estimated cost: ${cost:.4f}*"
        )
    else:
        content = (
            f"No researchable questions were found in this page.\n\n"
            f"*Processed: {processed_at} | Estimated cost: ${cost:.4f}*"
        )

    write_results_to_notion(_notion, state["page_id"], content)

    return {
        "cost_estimate": cost,
        "processed_at": processed_at,
    }


def should_do_research(state: ResearchState) -> str:
    """Route: go to research if questions were found, otherwise write directly."""
    return "do_research" if state.get("has_questions", False) else "update_notion"


def build_research_graph():
    """Build and compile the LangGraph research workflow."""
    workflow = StateGraph(ResearchState)

    workflow.add_node("extract_questions", extract_questions_node)
    workflow.add_node("do_research", do_research_node)
    workflow.add_node("update_notion", update_notion_node)

    workflow.set_entry_point("extract_questions")
    workflow.add_conditional_edges(
        "extract_questions",
        should_do_research,
        {
            "do_research": "do_research",
            "update_notion": "update_notion",
        },
    )
    workflow.add_edge("do_research", "update_notion")
    workflow.add_edge("update_notion", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def init_clients() -> None:
    """Initialize API clients from environment variables."""
    global _notion, _anthropic_client, _openai_client
    _notion = NotionClient(
        options=ClientOptions(
            auth=os.environ["NOTION_API_KEY"],
            notion_version="2022-06-28",
        )
    )
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

    graph = build_research_graph()
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
