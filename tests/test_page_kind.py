"""Refusing a page that is not one article.

Newspaper3k will extract text from a publisher's front page and hand back a long
string of headlines, which clears every length check the application had. The
result would be a class computed over a list of links, presented exactly like a
class computed over an article. These tests pin both halves of the refusal: the
URL that addresses a site, and the page whose text is not prose.
"""

import unittest

from publisher_reliability.errors import AppError
from publisher_reliability.page_kind import (
    addresses_a_site,
    declared_page_type,
    prose_measure,
    refuse_non_article_text,
    refuse_site_address,
)

PARAGRAPH = (
    "The committee met for three hours on Tuesday and published its findings the "
    "following morning, setting out the sequence of events in unusual detail and "
    "naming the officials who had signed each authorisation."
)
HEADLINE = "Minister resigns after inquiry"


class SiteAddressTest(unittest.TestCase):
    def test_a_front_page_addresses_a_site(self) -> None:
        for url in ("https://example.org/", "https://news.example.org/"):
            with self.subTest(url=url):
                self.assertTrue(addresses_a_site(url))

    def test_a_section_index_addresses_a_site(self) -> None:
        for url in ("https://example.org/news", "https://example.org/world/politics"):
            with self.subTest(url=url):
                self.assertTrue(addresses_a_site(url))

    def test_an_article_address_does_not(self) -> None:
        # A slug, a date path, a numeric id, and a deep path are each enough.
        for url in (
            "https://example.org/2026/09/21/minister-resigns-after-inquiry",
            "https://example.org/news/minister-resigns-after-inquiry",
            "https://example.org/story/481920",
            "https://example.org/a/b/c",
        ):
            with self.subTest(url=url):
                self.assertFalse(addresses_a_site(url))

    def test_a_query_string_can_carry_the_article_so_the_check_abstains(self) -> None:
        # `?id=1234` is the article's identity; refusing it on the strength of an
        # empty path would reject a real page.
        self.assertFalse(addresses_a_site("https://example.org/?id=1234"))

    def test_the_refusal_names_the_homepage_case(self) -> None:
        with self.assertRaises(AppError) as raised:
            refuse_site_address("https://example.org/")
        self.assertEqual(raised.exception.code, "NOT_AN_ARTICLE")
        self.assertIn("site or a section", raised.exception.details["reason"])


class ProseTest(unittest.TestCase):
    def test_headlines_are_not_prose_however_many_there_are(self) -> None:
        front_page = "\n\n".join([HEADLINE] * 40)
        self.assertGreater(len(front_page), 200)  # It would clear the length floor.
        prose, share = prose_measure(front_page)
        self.assertEqual((prose, share), (0, 0.0))

    def test_an_article_of_one_paragraph_is_prose(self) -> None:
        # The test is a share, not a paragraph count, because plenty of articles
        # are a single block of text.
        prose, share = prose_measure(PARAGRAPH)
        self.assertGreaterEqual(prose, 200)
        self.assertEqual(share, 1.0)

    def test_a_few_long_teasers_among_headlines_are_still_not_an_article(self) -> None:
        # The teasers alone would clear any length floor; what gives the page
        # away is that they are a small share of what is on it.
        mixed = "\n\n".join([PARAGRAPH] * 2 + [HEADLINE] * 40)
        prose, share = prose_measure(mixed)
        self.assertGreater(prose, 200)
        self.assertLess(share, 0.5)

    def test_the_declared_type_is_read_from_the_head(self) -> None:
        html = b'<html><head><meta property="og:type" content="Article"></head></html>'
        self.assertEqual(declared_page_type(html), "article")
        self.assertEqual(declared_page_type(b"<html><head></head></html>"), "")


class RefusalTest(unittest.TestCase):
    def test_a_wall_of_headlines_is_refused(self) -> None:
        with self.assertRaises(AppError) as raised:
            refuse_non_article_text(
                "https://example.org/",
                b"<html><head><meta property='og:type' content='website'></head></html>",
                "\n\n".join([HEADLINE] * 40),
            )
        self.assertEqual(raised.exception.code, "NOT_AN_ARTICLE")

    def test_a_page_that_is_simply_not_an_article(self) -> None:
        # A deep URL, no website declaration, and no prose: a video page, a form,
        # a product listing. The reader is told what is wrong, not where they are.
        with self.assertRaises(AppError) as raised:
            refuse_non_article_text(
                "https://example.org/watch/v/8891",
                b"<html><head></head><body></body></html>",
                "Play  Share  Subscribe",
            )
        self.assertEqual(raised.exception.code, "NOT_AN_ARTICLE")

    def test_a_page_that_says_it_is_an_article_but_extracted_badly(self) -> None:
        # Not the wrong kind of page: the same extraction failure as before.
        with self.assertRaises(AppError) as raised:
            refuse_non_article_text(
                "https://example.org/news/minister-resigns-after-inquiry",
                b"<html><head><meta property='og:type' content='article'></head></html>",
                "",
            )
        self.assertEqual(raised.exception.code, "EXTRACTION_FAILED")

    def test_a_prose_page_that_calls_itself_a_website_is_refused(self) -> None:
        # Measured on real pages: a software download page, a repository page and
        # a Wikipedia entry are all full of prose and all declare "website" or
        # "object", while every real article measured declared "article". The
        # declaration is therefore taken at its word.
        with self.assertRaises(AppError) as raised:
            refuse_non_article_text(
                "https://example.org/downloads/release-notes",
                b"<html><head><meta property='og:type' content='website'></head></html>",
                f"{PARAGRAPH}\n\n{PARAGRAPH}\n\n{PARAGRAPH}",
            )
        self.assertEqual(raised.exception.code, "NOT_AN_ARTICLE")
        self.assertIn("website", raised.exception.details["reason"])

    def test_an_article_passes(self) -> None:
        refuse_non_article_text(
            "https://example.org/news/minister-resigns-after-inquiry",
            b"<html><head><meta property='og:type' content='article'></head></html>",
            f"{PARAGRAPH}\n\n{PARAGRAPH}",
        )


class OneMessageTest(unittest.TestCase):
    """Every refusal reads the same, whatever decided it.

    The reader's next step is identical in all of them -- find the article and
    paste its link -- so the distinction lives in the details, for a bug report,
    and not in a second error code the interface would have to explain.
    """

    def messages(self) -> set[str]:
        seen = set()
        cases = [
            lambda: refuse_site_address("https://example.org/"),
            lambda: refuse_non_article_text(
                "https://example.org/watch/v/8891", b"<html></html>", "Play  Share"),
            lambda: refuse_non_article_text(
                "https://example.org/downloads/notes",
                b"<html><head><meta property='og:type' content='website'></head></html>",
                f"{PARAGRAPH}\n\n{PARAGRAPH}"),
        ]
        for case in cases:
            with self.assertRaises(AppError) as raised:
                case()
            self.assertEqual(raised.exception.code, "NOT_AN_ARTICLE")
            seen.add(raised.exception.message)
        return seen

    def test_the_wording_never_changes(self) -> None:
        self.assertEqual(len(self.messages()), 1)

    def test_but_the_reason_does(self) -> None:
        reasons = set()
        for url, html, text in [
            ("https://example.org/", b"", ""),
            ("https://example.org/watch/v/8891", b"<html></html>", "Play  Share"),
        ]:
            with self.assertRaises(AppError) as raised:
                (refuse_site_address(url) if url.endswith("/")
                 else refuse_non_article_text(url, html, text))
            reasons.add(raised.exception.details["reason"])
        self.assertEqual(len(reasons), 2)


if __name__ == "__main__":
    unittest.main()
