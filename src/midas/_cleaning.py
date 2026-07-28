"""Local-only extraction and normalization of rendered HTML."""

import re
import unicodedata

import trafilatura

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INLINE_WHITESPACE = re.compile(r"[^\S\n]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")


def extract_clean_text(
    html: str,
    *,
    url: str,
    max_characters: int,
    minimum_characters: int,
) -> str:
    """Extract article-like text from HTML and apply deterministic sanitation."""
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_images=False,
        include_links=False,
        include_tables=True,
        output_format="txt",
        deduplicate=True,
        favor_precision=True,
    )
    if not extracted:
        raise ValueError("No main-page content could be extracted")

    normalized = normalize_text(extracted)
    if len(normalized) < minimum_characters:
        raise ValueError("Extracted page content is too short")
    return normalized[:max_characters].rstrip()


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
