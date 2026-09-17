"""The shipped release, measured under the application's own URL identity.

`scripts/prepare_public_dataset.py` decides two rows are duplicates by comparing the
raw `url` strings, and the shipped manifest accordingly claims `duplicate_url_rows: 0`.
The application does not use raw strings: an article's identity is its *canonical*
URL, which `normalize_url` derives by lowercasing the host, applying IDNA and dropping
`utm_*` and other tracking parameters that never change which page is addressed.

Under that stricter rule the release is not duplicate-free. A handful of rows collapse
onto an article another row already occupies, and most of those pairs were scored by
*different* folds — so the article ends up recorded against two held-out folds at once,
which the leakage guard can only answer by refusing every checkpoint for it.

These are known properties of the current release, pinned here so the count cannot grow
unnoticed, and so that a change to `normalize_url` that quietly collapses far more
articles fails loudly instead of shrinking the usable corpus.
"""

import csv
import re
import unittest
from collections import defaultdict
from pathlib import Path

from publisher_reliability.identity import article_id, normalize_url

RELEASE = Path(__file__).resolve().parents[1] / "dataset" / "predictions" / "predictions.csv"

# import_bundled_release passes legacy_bare_percent=True, so the same repair is applied
# here; otherwise this would measure a different string than the application imports.
BARE_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")

EXPECTED_SOURCE_ROWS = 17283
EXPECTED_CANONICAL_ARTICLES = 17269
EXPECTED_AMBIGUOUS_FOLD_ARTICLES = 13
EXPECTED_SAME_FOLD_DUPLICATE_ARTICLES = 1


def _canonical_groups() -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    with RELEASE.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if (row.get("prediction_origin") or "dataset_original") != "dataset_original":
                continue
            raw = BARE_PERCENT.sub("%25", row["url"].strip())
            groups[article_id(normalize_url(raw))].append(row)
    return groups


@unittest.skipUnless(RELEASE.is_file(), "the bundled release is not present")
class ReleasedDatasetIdentityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.groups = _canonical_groups()
        cls.collided = {
            article: rows for article, rows in cls.groups.items() if len(rows) > 1
        }

    def test_the_release_has_the_expected_size_under_canonical_identity(self) -> None:
        self.assertEqual(
            sum(len(rows) for rows in self.groups.values()), EXPECTED_SOURCE_ROWS
        )
        self.assertEqual(len(self.groups), EXPECTED_CANONICAL_ARTICLES)

    def test_canonical_url_collisions_have_not_grown(self) -> None:
        """Every collision is one the raw-string duplicate check could not see."""

        self.assertEqual(
            len(self.collided),
            EXPECTED_SOURCE_ROWS - EXPECTED_CANONICAL_ARTICLES,
            "the number of rows sharing a canonical article changed",
        )
        for rows in self.collided.values():
            spellings = {row["url"].strip() for row in rows}
            self.assertGreater(
                len(spellings),
                1,
                "a collision with one spelling would be a plain duplicate the "
                "release preparation should already have rejected",
            )

    def test_the_ambiguous_fold_articles_are_a_known_short_list(self) -> None:
        """Rows scored by different folds leave their article unusable, not wrong.

        The leakage guard refuses every checkpoint for such an article rather than
        picking one fold, so these are silently absent from aggregation. That is the
        safe outcome; the point of pinning it is that the list must not grow.
        """

        ambiguous = 0
        same_fold = 0
        for rows in self.collided.values():
            folds = {row["bert_fold_id"] for row in rows}
            if len(folds) > 1:
                ambiguous += 1
            else:
                same_fold += 1
        self.assertEqual(ambiguous, EXPECTED_AMBIGUOUS_FOLD_ARTICLES)
        self.assertEqual(same_fold, EXPECTED_SAME_FOLD_DUPLICATE_ARTICLES)
        # Still a rounding error against the corpus: worth knowing, not alarming.
        self.assertLess(ambiguous / len(self.groups), 0.001)

    def test_both_families_agree_on_which_fold_held_an_article_out(self) -> None:
        """One split was used for every family, so the two fold columns must match.

        If they ever diverged, the article-level fold registry the leakage guard is
        built on would be reading a fold that only applies to one family.
        """

        for rows in self.groups.values():
            for row in rows:
                self.assertEqual(
                    row["bert_fold_id"],
                    row["roberta_fold_id"],
                    f"fold columns disagree for {row['url']}",
                )


if __name__ == "__main__":
    unittest.main()
