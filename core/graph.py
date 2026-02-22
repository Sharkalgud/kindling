"""LangGraph research workflow with client injection."""

from datetime import datetime, timezone
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from core.config import (
    EXTRACTION_PROMPT_TEMPLATE,
    GPT_MODEL,
    HAIKU_MODEL,
    RESEARCH_PROMPT_TEMPLATE,
    HAIKU_COST_PER_M_INPUT,
    HAIKU_COST_PER_M_OUTPUT,
    GPT_COST_PER_M_INPUT,
    GPT_COST_PER_M_OUTPUT,
)
from core.markdown_utils import markdown_to_notion_blocks


# ---------------------------------------------------------------------------
# State
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


def write_results_to_notion(notion, page_id: str, content_markdown: str) -> None:
    """Append a toggleable 🪵 ✨Kindling Results heading_2 block to a Notion page."""
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
# Graph factory
# ---------------------------------------------------------------------------


def build_research_graph(anthropic_client, openai_client, notion_client, console=None):
    """Build and compile the LangGraph research workflow with injected clients."""

    def _print(msg: str) -> None:
        if console is not None:
            console.print(msg)

    def extract_questions_node(state: ResearchState) -> dict:
        _print(f"[cyan]  Extracting questions...[/cyan]")

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            title=state["page_title"],
            content=state["page_content"],
        )

        message = anthropic_client.messages.create(
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
        _print(f"[cyan]  Researching with web search...[/cyan]")

        prompt = RESEARCH_PROMPT_TEMPLATE.format(questions=state["questions"])

        response = openai_client.responses.create(
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
        _print(f"[cyan]  Writing results to Notion...[/cyan]")

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

        write_results_to_notion(notion_client, state["page_id"], content)

        return {
            "cost_estimate": cost,
            "processed_at": processed_at,
        }

    def should_do_research(state: ResearchState) -> str:
        return "do_research" if state.get("has_questions", False) else "update_notion"

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
