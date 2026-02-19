"""Unit tests for research.py"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is on the path so `import research` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import research


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_page():
    """A minimal Notion page object with a title and URL."""
    return {
        "id": "test-page-id",
        "url": "https://www.notion.so/test-page-id",
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": "Test Page Title"}],
            }
        },
    }


@pytest.fixture
def mock_notion():
    """A MagicMock standing in for the Notion client."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Notion utility tests
# ---------------------------------------------------------------------------


def test_get_page_title(mock_page):
    assert research.get_page_title(mock_page) == "Test Page Title"


def test_get_page_title_untitled():
    page = {"id": "x", "url": "", "properties": {}}
    assert research.get_page_title(page) == "Untitled"


def test_get_page_title_empty_title():
    page = {
        "id": "x",
        "url": "",
        "properties": {"Name": {"type": "title", "title": []}},
    }
    assert research.get_page_title(page) == ""


def test_get_page_url(mock_page):
    assert research.get_page_url(mock_page) == "https://www.notion.so/test-page-id"


def test_get_page_url_missing():
    assert research.get_page_url({}) == ""


# ---------------------------------------------------------------------------
# blocks_to_text tests
# ---------------------------------------------------------------------------


def test_blocks_to_text_all_types():
    blocks = [
        {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "H1"}]}},
        {"type": "heading_2", "heading_2": {"rich_text": [{"plain_text": "H2"}]}},
        {"type": "heading_3", "heading_3": {"rich_text": [{"plain_text": "H3"}]}},
        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Para"}]}},
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"plain_text": "Bullet"}]},
        },
        {
            "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": [{"plain_text": "Number"}]},
        },
        {"type": "divider", "divider": {}},
    ]
    result = research.blocks_to_text(blocks)
    assert "# H1" in result
    assert "## H2" in result
    assert "### H3" in result
    assert "Para" in result
    assert "- Bullet" in result
    assert "1. Number" in result
    assert "---" in result


def test_blocks_to_text_skips_empty_rich_text():
    blocks = [
        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": ""}]}},
    ]
    result = research.blocks_to_text(blocks)
    assert result == ""


def test_blocks_to_text_unknown_type_ignored():
    blocks = [{"type": "unsupported_block", "unsupported_block": {}}]
    result = research.blocks_to_text(blocks)
    assert result == ""


# ---------------------------------------------------------------------------
# has_kindling_results_block tests
# ---------------------------------------------------------------------------


def test_has_kindling_results_block_found(mock_notion):
    mock_notion.blocks.children.list.return_value = {
        "results": [
            {
                "type": "heading_2",
                "heading_2": {
                    "is_toggleable": True,
                    "rich_text": [{"plain_text": "🪵 ✨Kindling Results"}],
                },
            }
        ]
    }
    assert research.has_kindling_results_block(mock_notion, "page-id") is True


def test_has_kindling_results_block_not_found(mock_notion):
    mock_notion.blocks.children.list.return_value = {
        "results": [
            {
                "type": "paragraph",
                "paragraph": {"rich_text": [{"plain_text": "Some text"}]},
            }
        ]
    }
    assert research.has_kindling_results_block(mock_notion, "page-id") is False


def test_has_kindling_results_block_non_toggle_heading(mock_notion):
    """heading_2 without is_toggleable should not match."""
    mock_notion.blocks.children.list.return_value = {
        "results": [
            {
                "type": "heading_2",
                "heading_2": {
                    "is_toggleable": False,
                    "rich_text": [{"plain_text": "🪵 ✨Kindling Results"}],
                },
            }
        ]
    }
    assert research.has_kindling_results_block(mock_notion, "page-id") is False


def test_has_kindling_results_block_empty_page(mock_notion):
    mock_notion.blocks.children.list.return_value = {"results": []}
    assert research.has_kindling_results_block(mock_notion, "page-id") is False


# ---------------------------------------------------------------------------
# markdown_to_notion_blocks tests
# ---------------------------------------------------------------------------


def test_markdown_to_notion_blocks_headings():
    md = "# Heading 1\n## Heading 2\n### Heading 3"
    blocks = research.markdown_to_notion_blocks(md)
    types = [b["type"] for b in blocks]
    assert "heading_1" in types
    assert "heading_2" in types
    assert "heading_3" in types


def test_markdown_to_notion_blocks_lists():
    md = "- Bullet one\n* Bullet two\n1. Numbered item"
    blocks = research.markdown_to_notion_blocks(md)
    types = [b["type"] for b in blocks]
    assert types.count("bulleted_list_item") == 2
    assert types.count("numbered_list_item") == 1


def test_markdown_to_notion_blocks_code():
    md = "```python\nprint('hello')\n```"
    blocks = research.markdown_to_notion_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "code"
    assert blocks[0]["code"]["language"] == "python"
    assert "print('hello')" in blocks[0]["code"]["rich_text"][0]["text"]["content"]


def test_markdown_to_notion_blocks_code_no_lang():
    md = "```\nsome code\n```"
    blocks = research.markdown_to_notion_blocks(md)
    assert blocks[0]["code"]["language"] == "plain text"


def test_markdown_to_notion_blocks_paragraph():
    md = "Just a plain paragraph."
    blocks = research.markdown_to_notion_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "paragraph"
    assert blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == "Just a plain paragraph."


def test_markdown_to_notion_blocks_links():
    md = "Visit [OpenAI](https://openai.com) for details."
    blocks = research.markdown_to_notion_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "paragraph"

    rich_text = blocks[0]["paragraph"]["rich_text"]
    link_items = [r for r in rich_text if r.get("text", {}).get("link")]
    assert len(link_items) == 1
    assert link_items[0]["text"]["content"] == "OpenAI"
    assert link_items[0]["text"]["link"]["url"] == "https://openai.com"


def test_markdown_to_notion_blocks_bold():
    md = "This is **bold** text."
    blocks = research.markdown_to_notion_blocks(md)
    rich_text = blocks[0]["paragraph"]["rich_text"]
    bold_items = [r for r in rich_text if r.get("annotations", {}).get("bold")]
    assert len(bold_items) == 1
    assert bold_items[0]["text"]["content"] == "bold"


def test_markdown_to_notion_blocks_italic():
    md = "This is *italic* text."
    blocks = research.markdown_to_notion_blocks(md)
    rich_text = blocks[0]["paragraph"]["rich_text"]
    italic_items = [r for r in rich_text if r.get("annotations", {}).get("italic")]
    assert len(italic_items) == 1
    assert italic_items[0]["text"]["content"] == "italic"


def test_markdown_to_notion_blocks_bold_italic():
    md = "This is ***bold and italic*** text."
    blocks = research.markdown_to_notion_blocks(md)
    rich_text = blocks[0]["paragraph"]["rich_text"]
    both = [
        r for r in rich_text
        if r.get("annotations", {}).get("bold") and r.get("annotations", {}).get("italic")
    ]
    assert len(both) == 1
    assert both[0]["text"]["content"] == "bold and italic"


def test_markdown_to_notion_blocks_inline_code():
    md = "Use `foo()` to call it."
    blocks = research.markdown_to_notion_blocks(md)
    rich_text = blocks[0]["paragraph"]["rich_text"]
    code_items = [r for r in rich_text if r.get("annotations", {}).get("code")]
    assert len(code_items) == 1
    assert code_items[0]["text"]["content"] == "foo()"


def test_markdown_to_notion_blocks_divider():
    md = "Before\n---\nAfter"
    blocks = research.markdown_to_notion_blocks(md)
    types = [b["type"] for b in blocks]
    assert "divider" in types


def test_markdown_to_notion_blocks_empty_lines_skipped():
    md = "Line 1\n\n\nLine 2"
    blocks = research.markdown_to_notion_blocks(md)
    # Only two paragraph blocks; empty lines are skipped
    assert len(blocks) == 2


def test_markdown_to_notion_blocks_empty_string():
    blocks = research.markdown_to_notion_blocks("")
    assert blocks == []


# ---------------------------------------------------------------------------
# estimate_cost tests
# ---------------------------------------------------------------------------


def test_estimate_cost_known_values():
    extraction = {"input": 1000, "output": 500}
    research_toks = {"input": 2000, "output": 800}

    cost = research.estimate_cost(extraction, research_toks)

    expected_haiku = (1000 * 0.80 + 500 * 4.00) / 1_000_000
    expected_gpt = (2000 * 5.00 + 800 * 15.00) / 1_000_000
    assert abs(cost - (expected_haiku + expected_gpt)) < 1e-10


def test_estimate_cost_zeros():
    assert research.estimate_cost({}, {}) == 0.0


def test_estimate_cost_only_extraction():
    cost = research.estimate_cost({"input": 1_000_000, "output": 0}, {})
    assert abs(cost - 0.80) < 1e-6


def test_estimate_cost_only_research():
    cost = research.estimate_cost({}, {"input": 1_000_000, "output": 0})
    assert abs(cost - 5.00) < 1e-6


# ---------------------------------------------------------------------------
# Graph integration tests (mocked)
# ---------------------------------------------------------------------------


def test_graph_no_questions():
    """When extraction finds no questions, research node must not be called."""
    with (
        patch.object(research, "_anthropic_client") as mock_ant,
        patch.object(research, "_openai_client") as mock_oai,
        patch.object(research, "_notion"),
        patch("research.write_results_to_notion") as mock_write,
    ):
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(text="I don't see any questions in this text.")
        ]
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 20
        mock_ant.messages.create.return_value = mock_message

        graph = research.build_research_graph()

        initial_state: research.ResearchState = {
            "page_id": "test-id",
            "page_title": "Test Page",
            "page_content": "This is just a note with no questions.",
            "questions": None,
            "research_result": None,
            "has_questions": False,
            "extraction_tokens": {},
            "research_tokens": {},
            "cost_estimate": 0.0,
            "processed_at": "",
        }

        final_state = graph.invoke(initial_state)

        mock_oai.responses.create.assert_not_called()
        mock_write.assert_called_once()
        assert not final_state.get("has_questions")


def test_graph_with_questions():
    """When extraction finds questions, both research and write nodes must run."""
    with (
        patch.object(research, "_anthropic_client") as mock_ant,
        patch.object(research, "_openai_client") as mock_oai,
        patch.object(research, "_notion"),
        patch("research.write_results_to_notion") as mock_write,
    ):
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(
                text=(
                    "I want to know why physical therapy practices don't follow the "
                    "stretch lab model. Specifically, I am curious about the business "
                    "model differences and patient outcomes."
                )
            )
        ]
        mock_message.usage.input_tokens = 150
        mock_message.usage.output_tokens = 50
        mock_ant.messages.create.return_value = mock_message

        mock_response = MagicMock()
        mock_response.output_text = "# Research Report\n\nHere are the findings..."
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 300
        mock_oai.responses.create.return_value = mock_response

        graph = research.build_research_graph()

        initial_state: research.ResearchState = {
            "page_id": "test-id",
            "page_title": "PT practices question",
            "page_content": "Why don't PT practices follow the stretch lab model?",
            "questions": None,
            "research_result": None,
            "has_questions": False,
            "extraction_tokens": {},
            "research_tokens": {},
            "cost_estimate": 0.0,
            "processed_at": "",
        }

        final_state = graph.invoke(initial_state)

        mock_oai.responses.create.assert_called_once()
        mock_write.assert_called_once()
        assert final_state.get("has_questions")
        assert final_state.get("research_result") is not None
        assert final_state.get("cost_estimate") > 0


# ---------------------------------------------------------------------------
# Integration tests (require real API keys)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_notion_api_access():
    """Verify real Notion API read access to the test pages."""
    from dotenv import load_dotenv
    from notion_client import Client as NotionClient

    load_dotenv()

    notion = NotionClient(auth=os.environ["NOTION_API_KEY"])

    test_page_ids = [
        "30bbad37f86a804a9e31ec40c5549aae",
        "30abad37f86a80b099e5d39db193e08b",
    ]

    for page_id in test_page_ids:
        page = notion.pages.retrieve(page_id=page_id)
        assert page.get("id") is not None, f"Could not retrieve page {page_id}"

        blocks = notion.blocks.children.list(block_id=page_id)
        assert "results" in blocks, f"Could not list blocks for page {page_id}"


@pytest.mark.integration
def test_kindling_research_checkbox_is_true():
    """Verify the Kindling Research checkbox is True on each test page."""
    from dotenv import load_dotenv
    from notion_client import Client as NotionClient

    load_dotenv()

    notion = NotionClient(auth=os.environ["NOTION_API_KEY"])

    test_page_ids = [
        "30bbad37f86a804a9e31ec40c5549aae",
        "30abad37f86a80b099e5d39db193e08b",
    ]

    for page_id in test_page_ids:
        page = notion.pages.retrieve(page_id=page_id)
        props = page.get("properties", {})

        assert "Kindling Research" in props, (
            f"Page {page_id} has no 'Kindling Research' property. "
            f"Available properties: {list(props.keys())}"
        )

        prop = props["Kindling Research"]
        assert prop.get("type") == "checkbox", (
            f"Page {page_id}: 'Kindling Research' is type '{prop.get('type')}', expected 'checkbox'"
        )
        assert prop.get("checkbox") is True, (
            f"Page {page_id}: 'Kindling Research' checkbox is not True"
        )
