"""Local-only extraction and normalization of rendered HTML."""

import re
import unicodedata
from html.parser import HTMLParser

import trafilatura

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INLINE_WHITESPACE = re.compile(r"[^\S\n]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")
_VISIBLE_TEXT_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "blockquote",
        "br",
        "caption",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }
)
_IGNORED_TEXT_TAGS = frozenset(
    {
        "aside",
        "canvas",
        "footer",
        "form",
        "head",
        "header",
        "nav",
        "noscript",
        "script",
        "style",
        "svg",
        "template",
    }
)
_IGNORED_ELEMENT_HINTS = frozenset(
    {
        "advert",
        "banner",
        "consent",
        "cookie",
        "footer",
        "header",
        "menu",
        "modal",
        "nav",
        "popup",
        "sidebar",
    }
)


def extract_clean_text(
    html: str,
    *,
    url: str,
    max_characters: int,
    minimum_characters: int,
) -> str:
    """Extract article-like text from HTML and apply deterministic sanitation."""
    extracted = _extract_with_trafilatura(
        html,
        url=url,
    )
    normalized = normalize_text(extracted) if extracted else ""
    if len(normalized) < minimum_characters:
        # Finance screeners and other application-like pages often have no
        # article-shaped main content.  Use visible text only as a last resort,
        # keeping scripts, navigation, overlays, and hidden elements out.
        normalized = normalize_text(_extract_visible_text(html))
    if len(normalized) < minimum_characters:
        raise ValueError("No usable visible page content could be extracted")
    return normalized[:max_characters].rstrip()


def _extract_with_trafilatura(html: str, *, url: str) -> str | None:
    options = {
        "url": url,
        "include_comments": False,
        "include_images": False,
        "include_links": False,
        "include_tables": True,
        "output_format": "txt",
        "deduplicate": True,
    }
    extracted = trafilatura.extract(html, favor_precision=True, **options)
    if extracted:
        return extracted
    return trafilatura.extract(html, favor_recall=True, **options)


class _VisibleTextParser(HTMLParser):
    """Collect readable text from rendered HTML without treating markup as content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if self._ignored_depth:
            self._ignored_depth += 1
            return
        if tag in _IGNORED_TEXT_TAGS or _should_ignore_element(attrs):
            self._ignored_depth = 1
            return
        if tag in _VISIBLE_TEXT_BLOCK_TAGS:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self._ignored_depth and tag.casefold() == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag.casefold() in _VISIBLE_TEXT_BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def _should_ignore_element(attrs: list[tuple[str, str | None]]) -> bool:
    attributes = {name.casefold(): (value or "").casefold() for name, value in attrs}
    if "hidden" in attributes or attributes.get("aria-hidden") == "true":
        return True
    element_hint = " ".join(
        value for name, value in attributes.items() if name in {"class", "id", "role"}
    )
    return any(hint in element_hint for hint in _IGNORED_ELEMENT_HINTS)


def _extract_visible_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    return parser.text()


def normalize_text(text: str) -> str:
    """Normalize Unicode, controls, whitespace, and repeated lines."""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_CHARACTERS.sub("", text)
    text = _INLINE_WHITESPACE.sub(" ", text)

    seen_lines: set[str] = set()
    output_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if output_lines and output_lines[-1]:
                output_lines.append("")
            continue

        comparison_key = line.casefold()
        if comparison_key in seen_lines:
            continue
        seen_lines.add(comparison_key)
        output_lines.append(line)

    return _MANY_NEWLINES.sub("\n\n", "\n".join(output_lines)).strip()
