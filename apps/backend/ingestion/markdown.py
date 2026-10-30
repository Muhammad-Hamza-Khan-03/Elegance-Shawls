"""Turn untrusted product-description HTML into a small, safe Markdown subset.

Only headings (``##``/``###``), paragraphs, ``- `` bullets, ``**bold**`` and ``*italic*`` survive.
Links lose their target, images, scripts, styles and every attribute are dropped, so the output is
plain text with light structure that a reviewer UI renders without ever touching raw HTML.
"""
import re
import unicodedata

from bs4 import BeautifulSoup, NavigableString, Tag

HEADINGS = {"h1": "## ", "h2": "## ", "h3": "### ", "h4": "### ", "h5": "### ", "h6": "### "}
SKIP = {"script", "style", "noscript", "iframe", "svg", "img", "picture", "video", "form", "button", "template"}
BLOCKS = {"p", "div", "section", "article", "blockquote", "table", "tr", "ul", "ol", "li", "br", *HEADINGS}


def _inline(node, out: list[str]) -> None:
    for child in node.children:
        if isinstance(child, NavigableString):
            out.append(str(child))
        elif isinstance(child, Tag) and child.name not in SKIP:
            if child.name == "br":
                out.append("\n")
            elif child.name in ("strong", "b"):
                inner: list[str] = []
                _inline(child, inner)
                text = "".join(inner).strip()
                out.append(f"**{text}**" if text else "")
            elif child.name in ("em", "i"):
                inner = []
                _inline(child, inner)
                text = "".join(inner).strip()
                out.append(f"*{text}*" if text else "")
            else:
                _inline(child, out)


def _blocks(node, out: list[str]) -> None:
    pending: list[str] = []

    def flush():
        text = _collapse("".join(pending))
        if text:
            out.append(text)
        pending.clear()

    for child in node.children:
        if isinstance(child, NavigableString):
            pending.append(str(child))
        elif isinstance(child, Tag) and child.name not in SKIP:
            if child.name in HEADINGS:
                flush()
                text = _collapse("".join(_collect(child)))
                if text:
                    out.append(HEADINGS[child.name] + text.replace("\n", " "))
            elif child.name in ("ul", "ol"):
                flush()
                items = [_collapse("".join(_collect(li))).replace("\n", " ") for li in child.find_all("li", recursive=False)]
                lines = [f"- {item}" for item in items if item]
                if lines:
                    out.append("\n".join(lines))
            elif child.name in ("p", "div", "section", "article", "blockquote", "table", "tr", "li"):
                flush()
                if any(isinstance(c, Tag) and c.name in BLOCKS for c in child.children):
                    _blocks(child, out)
                else:
                    text = _collapse("".join(_collect(child)))
                    if text:
                        out.append(text)
            else:
                pending.extend(_collect(child) if child.name != "br" else ["\n"])
    flush()


def _collect(node) -> list[str]:
    out: list[str] = []
    _inline(node, out)
    return out


def _collapse(text: str) -> str:
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n\t")
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def html_to_markdown(html: str | Tag, limit: int | None = None) -> str:
    """Blocks are separated by a blank line. ``limit`` cuts at a block boundary where possible."""
    root = html if isinstance(html, Tag) else BeautifulSoup(str(html), "html.parser")
    blocks: list[str] = []
    _blocks(root, blocks)
    text = "\n\n".join(blocks)
    if limit and len(text) > limit:
        cut = text[:limit]
        boundary = cut.rfind("\n\n")
        text = (cut[:boundary] if boundary > limit // 2 else cut).rstrip()
    return text


def plain(text: str) -> str:
    """Letters and digits only, for comparing two renderings of the same text."""
    return re.sub(r"[\W_]+", "", text).lower()
