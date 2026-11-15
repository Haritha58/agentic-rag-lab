import html
import re
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "br", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "ul", "ol"}


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(raw: str | None) -> str:
    """Job descriptions arrive as HTML (sometimes double-escaped, e.g. Greenhouse)."""
    if not raw:
        return ""
    if "&lt;" in raw:
        raw = html.unescape(raw)
    stripper = _Stripper()
    stripper.feed(raw)
    text = "".join(stripper.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def norm(s: str) -> str:
    """Lowercase alphanumerics only; used for company keys and dedupe."""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def sentence_around(text: str, start: int, end: int, width: int = 160) -> str:
    """The snippet of `text` around a match, used as evidence in the UI."""
    lo = max(0, start - width // 2)
    hi = min(len(text), end + width // 2)
    snippet = text[lo:hi].replace("\n", " ").strip()
    return ("…" if lo > 0 else "") + snippet + ("…" if hi < len(text) else "")
