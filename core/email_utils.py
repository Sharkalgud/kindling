"""Email digest utilities."""

import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import DIGEST_RECIPIENT, SMTP_PORT, SMTP_SERVER


def extract_up_to_tldr(research_text: str) -> str:
    """Return everything before '## 4)' section; fallback to first 1000 chars."""
    match = re.search(r"^## 4\)", research_text, re.MULTILINE)
    if match:
        return research_text[: match.start()].rstrip()
    return research_text[:1000]


# ---------------------------------------------------------------------------
# Plain-text digest
# ---------------------------------------------------------------------------


def build_digest_text(queue: list) -> str:
    """Build a plain-text email digest from a list of queue records."""
    lines = ["Kindling Research Digest\n", "=" * 40, ""]

    total_cost = 0.0
    errors = []

    for record in queue:
        title = record.get("title", "Untitled")
        url = record.get("url", "")
        research_text = record.get("research_text", "")
        cost = record.get("cost", 0.0)
        any_error = record.get("any_error", "")
        processed_at = record.get("processed_at", "")

        total_cost += cost or 0.0

        lines.append(f"{title}")
        if url:
            lines.append(f"Notion: {url}")
        if processed_at:
            lines.append(f"Processed: {processed_at}")
        lines.append(f"Cost: ${cost:.4f}")
        lines.append("")

        if any_error:
            errors.append(f"  - {title}: {any_error}")
            lines.append(f"[ERROR] {any_error}")
        elif research_text:
            excerpt = extract_up_to_tldr(research_text)
            # Strip markdown syntax for plain text
            excerpt = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", excerpt)
            excerpt = re.sub(r"\*\*(.+?)\*\*", r"\1", excerpt)
            excerpt = re.sub(r"\*(.+?)\*", r"\1", excerpt)
            excerpt = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", excerpt)
            excerpt = re.sub(r"^#{1,3} ", "", excerpt, flags=re.MULTILINE)
            lines.append(excerpt)

        lines.append("")
        lines.append("-" * 40)
        lines.append("")

    lines.append(f"Total estimated cost: ${total_cost:.4f}")

    if errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(errors)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML digest
# ---------------------------------------------------------------------------


def _inline_md_to_html(text: str) -> str:
    """Convert inline markdown (bold, italic, links) to HTML."""
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text


def _markdown_to_html(markdown: str) -> str:
    """Convert a markdown string to an HTML fragment."""
    lines = markdown.split("\n")
    parts = []
    in_ul = False

    for line in lines:
        if line.startswith("### "):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            text = _inline_md_to_html(line[4:].strip())
            parts.append(f'<h3 style="font-size:15px;margin:20px 0 4px;">{text}</h3>')
        elif line.startswith("## "):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            text = _inline_md_to_html(line[3:].strip())
            parts.append(f'<h2 style="font-size:16px;margin:20px 0 4px;">{text}</h2>')
        elif line.startswith("# "):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            text = _inline_md_to_html(line[2:].strip())
            parts.append(f'<h1 style="font-size:18px;margin:20px 0 4px;">{text}</h1>')
        elif line.startswith("- ") or line.startswith("* "):
            if not in_ul:
                parts.append('<ul style="margin:8px 0;padding-left:20px;">')
                in_ul = True
            text = _inline_md_to_html(line[2:].strip())
            parts.append(f'<li style="margin-bottom:4px;">{text}</li>')
        elif line.strip() in ("---", "***", "___"):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            parts.append('<hr style="border:none;border-top:1px solid #e0e0e0;margin:16px 0;">')
        elif not line.strip():
            if in_ul:
                parts.append("</ul>")
                in_ul = False
        else:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            text = _inline_md_to_html(line.strip())
            parts.append(f'<p style="margin:6px 0;line-height:1.6;">{text}</p>')

    if in_ul:
        parts.append("</ul>")

    return "\n".join(parts)


def build_digest_html(queue: list) -> str:
    """Build an HTML email digest from a list of queue records."""
    total_cost = sum(r.get("cost", 0.0) or 0.0 for r in queue)
    errors = []
    pages_html = []

    for record in queue:
        title = record.get("title", "Untitled")
        url = record.get("url", "")
        research_text = record.get("research_text", "")
        cost = record.get("cost", 0.0) or 0.0
        any_error = record.get("any_error", "")
        processed_at = record.get("processed_at", "")

        notion_link = (
            f'<a href="{url}" style="color:#555;text-decoration:none;">Open in Notion ↗</a>'
            if url else ""
        )
        meta_parts = [p for p in [notion_link, processed_at, f"${cost:.4f}"] if p]
        meta = ' &nbsp;·&nbsp; '.join(meta_parts)

        if any_error:
            errors.append(f"{title}: {any_error}")
            content_html = (
                f'<p style="color:#c0392b;background:#fdf2f2;padding:10px 14px;'
                f'border-radius:4px;margin:12px 0;">'
                f'<strong>Error:</strong> {any_error}</p>'
            )
        elif research_text:
            excerpt = extract_up_to_tldr(research_text)
            content_html = _markdown_to_html(excerpt)
        else:
            content_html = '<p style="color:#888;">No content available.</p>'

        pages_html.append(f"""
        <div style="margin-bottom:40px;padding-bottom:40px;border-bottom:1px solid #e8e8e8;">
          <h2 style="font-size:20px;margin:0 0 6px;font-family:Georgia,serif;">{title}</h2>
          <p style="font-size:13px;color:#999;margin:0 0 18px;">{meta}</p>
          {content_html}
        </div>""")

    errors_section = ""
    if errors:
        items = "".join(f"<li>{e}</li>" for e in errors)
        errors_section = (
            f'<div style="margin-top:16px;">'
            f'<strong>Errors:</strong><ul style="margin:6px 0;">{items}</ul></div>'
        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Georgia,serif;max-width:660px;margin:0 auto;padding:28px 24px 48px;
             color:#1a1a1a;background:#ffffff;line-height:1.6;">

  <h1 style="font-size:24px;font-weight:bold;border-bottom:2px solid #1a1a1a;
              padding-bottom:12px;margin:0 0 32px;">🪵 Kindling Research Digest</h1>

  {"".join(pages_html)}

  <div style="font-size:13px;color:#999;border-top:1px solid #e0e0e0;padding-top:14px;margin-top:8px;">
    Total estimated cost: ${total_cost:.4f}
    {errors_section}
  </div>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


def send_digest(
    queue: list,
    gmail_user: str,
    gmail_app_password: str,
    recipient: str = DIGEST_RECIPIENT,
) -> None:
    """Send the nightly digest email via Gmail SMTP with STARTTLS."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Kindling Research Digest"
    msg["From"] = gmail_user
    msg["To"] = recipient

    msg.attach(MIMEText(build_digest_text(queue), "plain", "utf-8"))
    msg.attach(MIMEText(build_digest_html(queue), "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_app_password)
        smtp.sendmail(gmail_user, [recipient], msg.as_string())
