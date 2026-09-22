"""Tell an article apart from a front page, and both from a page that is neither.

Newspaper3k extracts text from anything that has paragraphs in it. Give it a
publisher's front page and it returns a wall of headlines and teasers, which is
long enough to clear the minimum length and would then be classified as though it
were one article. The class that came back would be meaningless, and nothing in
the interface would say so.

Two checks stand in the way, and they are deliberately separate because the
advice a reader needs is different in each case:

  * a URL that addresses a site rather than a page is refused before anything is
    downloaded, since no amount of parsing would change the answer;
  * a page whose extracted text is not continuous prose is refused after parsing,
    because only the text can tell a long article from a list of links to
    articles.

Both are heuristics, so both are tuned to be quiet: the point is to catch the
obvious mistakes -- pasting a homepage, pasting a video page, pasting a search
result -- not to adjudicate borderline cases. A page that fails a check is never
classified; a page that passes may still be something odd, and the reader is
trusted with that.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .errors import AppError

# Newspaper3k joins the paragraphs it kept with a blank line, so the body arrives
# already divided. A block this long is continuous prose rather than a headline.
MIN_PROSE_BLOCK_CHARS = 140
# What separates an article from an index is not how much text there is -- a busy
# front page easily has more -- but how much of it is prose. An article is almost
# entirely body; a front page is almost entirely link labels.
MIN_PROSE_SHARE = 0.5
# The same floor the length check uses, so this test never refuses a page that
# would have been accepted for its length alone.
MIN_PROSE_CHARS = 200

# Path segments that name a section of a site rather than one piece of writing.
# The list is short on purpose: a wrong entry here refuses a real article.
SECTION_SEGMENTS = frozenset({
    "news", "world", "politics", "business", "opinion", "sport", "sports",
    "culture", "tech", "technology", "science", "health", "latest", "topics",
    "category", "categories", "section", "sections", "tag", "tags", "archive",
    "archives", "author", "authors", "search", "index",
})

# An article's own segment usually reads as a slug -- three or more words joined
# by hyphens -- or carries a numeric identifier. Either is enough to believe the
# URL addresses one page.
_SLUG = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+){2,}")
_HAS_DIGITS = re.compile(r"\d")

# What a page calls itself in `og:type`. Measured on real pages: NPR, Al Jazeera
# and CBS all declare "article" on their articles, while a section hub, a
# software download page, a repository page and a Wikipedia entry declare
# "website" or "object". A declaration that is not article-like is therefore
# taken at its word, even when the page is full of prose -- which is how a page
# that reads perfectly well but is not journalism gets refused.
ARTICLE_TYPES = frozenset({"article", "news", "newsarticle", "blog", "text"})

# Only read from the first part of the document: og:type sits in <head>, and this
# avoids scanning megabytes of body for a tag that cannot be there.
_HEAD_BYTES = 200_000
_OG_TYPE = re.compile(
    rb"""<meta[^>]+?(?:property|name)\s*=\s*["']og:type["'][^>]*?"""
    rb"""content\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)


def addresses_a_site(url: str) -> bool:
    """True when the URL names a site or a section of one, not a single page.

    This is the cheap check, made before the page is fetched. It only says yes
    when there is nothing page-like in the URL at all, so an article that lives
    at an unusual address is let through to the text check rather than refused
    here on the strength of its spelling.
    """

    parts = urlsplit(url)
    if parts.query or parts.fragment:
        # A query string can carry the article's identity (`?id=1234`), so the
        # URL is no longer just a site address and this check has no opinion.
        return False
    segments = [segment for segment in parts.path.split("/") if segment]
    if not segments:
        return True  # The front page itself.
    if len(segments) > 2:
        return False  # Deep enough to be a page, whatever the segments say.
    last = segments[-1]
    if _SLUG.search(last) or _HAS_DIGITS.search(last):
        return False
    return all(segment.lower() in SECTION_SEGMENTS for segment in segments)


def declared_page_type(html: bytes) -> str:
    """The page's own `og:type`, lowercased, or "" when it does not declare one."""

    match = _OG_TYPE.search(html[:_HEAD_BYTES])
    return match.group(1).decode("utf-8", errors="replace").strip().lower() if match else ""


def prose_measure(text: str) -> tuple[int, float]:
    """How much of the extracted text is prose, absolutely and as a share.

    Returns the number of characters that sit in long blocks, and their share of
    the whole. Both matter: the count keeps a page of two short sentences out,
    and the share is what tells a front page from an article, since a front page
    can carry far more text than an article and still be nothing but link labels.

    An article of one long paragraph scores a share of 1.0, which is why the test
    is not "at least two paragraphs": plenty of articles are one.
    """

    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    total = sum(len(block) for block in blocks)
    prose = sum(len(block) for block in blocks if len(block) >= MIN_PROSE_BLOCK_CHARS)
    return prose, (prose / total if total else 0.0)


def refuse_site_address(url: str) -> None:
    """Refuse a URL that addresses a site rather than an article."""

    if addresses_a_site(url):
        raise AppError(
            "PUBLISHER_HOMEPAGE",
            "This address is a publisher's home or section page, not an article. "
            "Open the article you want and paste the link to that page.",
            {"url": url},
        )


def _refuse(url: str, reason: str, details: dict[str, object]) -> None:
    """Raise the refusal that the evidence supports.

    The homepage code is reserved for the case the URL itself settles, because
    that is the only evidence strong enough to name where the reader ended up.
    Everything else says what is wrong with the page and leaves the reader to
    recognise it.
    """

    if addresses_a_site(url):
        raise AppError(
            "PUBLISHER_HOMEPAGE",
            f"This address is a publisher's home or section page, not an article "
            f"({reason}). Open the article you want and paste the link to that page.",
            {"url": url, **details},
        )
    raise AppError(
        "NOT_AN_ARTICLE",
        f"This page does not read as a news article ({reason}). Paste the link to "
        f"a single article.",
        {"url": url, **details},
    )


def refuse_non_article_text(url: str, html: bytes, text: str) -> None:
    """Refuse a page that is not one news article, after it has been parsed.

    Two questions, in order. What does the page say it is? And, when it says
    nothing, does its text read like an article's?
    """

    page_type = declared_page_type(html)
    prose, share = prose_measure(text)
    measured: dict[str, object] = {
        "prose_chars": prose,
        "prose_share": round(share, 2),
        "declared_type": page_type,
    }
    reads_as_prose = prose >= MIN_PROSE_CHARS and share >= MIN_PROSE_SHARE

    if page_type in ARTICLE_TYPES:
        if reads_as_prose:
            return
        # It says it is an article and it is not lying about being a page; the
        # extraction simply failed, which is the error that already existed.
        raise AppError(
            "EXTRACTION_FAILED",
            "The page declares itself an article, but no continuous text could be "
            "extracted from it.",
            {"url": url, **measured},
        )
    if page_type:
        _refuse(url, f'the page declares itself "{page_type}"', measured)
    if not reads_as_prose:
        _refuse(url, "it has no continuous body text", measured)
