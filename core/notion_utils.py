"""Notion API utilities."""

import os

from notion_client import Client as NotionClient
from notion_client.client import ClientOptions

from core.config import NOTION_DB_ID


def init_notion_client() -> NotionClient:
    """Create and return a Notion client from environment variables."""
    return NotionClient(
        options=ClientOptions(
            auth=os.environ["NOTION_API_KEY"],
            notion_version="2022-06-28",
        )
    )


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
