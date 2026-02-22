"""Markdown to Notion blocks converter."""

import re


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
