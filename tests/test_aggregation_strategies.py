"""The aggregation strategies and the dispersion statistics.

These tests pin the scientific claims the publisher view makes, not its wording: that
each strategy answers a different question, and that the dispersion numbers mean what
the interface says they mean. ``tests/test_core.py`` keeps the four original cases
that fix the long-standing return shape; this file covers everything added around them.

There is no test for a "tolerant" counting mode because there is no such mode: an
adjacent-class allowance needs a true label to be tolerant *of*, and aggregation has
none. The allowance survives only in the dispersion statistics below, which compare
articles with the verdict they produced rather than with a truth.
"""

import unittest

from publisher_reliability.aggregation import (
    DISPERSION_BANDS,
    METHODS,
    aggregate,
    dispersion_band,
)
from publisher_reliability.errors import AppError


def runs(classes, probabilities=None):
    """Prediction rows in the shape the ledger stores them, probabilities optional."""

    values = []
    for index, predicted_class in enumerate(classes):
        vector = probabilities[index] if probabilities else [None] * 5
        values.append(
            {
                "predicted_class": str(predicted_class),
                **{
                    f"prob_class_{class_id}": (
                        "" if vector[class_id] is None else str(vector[class_id])
                    )
                    for class_id in range(5)
                },
            }
        )
    return values


def one_hot(predicted_class):
    return [1.0 if index == predicted_class else 0.0 for index in range(5)]


class StrategyTest(unittest.TestCase):
    def test_median_ignores_an_extreme_minority_the_mean_cannot(self) -> None:
        # Four articles at class 1 and one at class 4. The mean is dragged to 1.6 and
        # rounds to 2; the median stays where the bulk of the evidence is.
        classes = [1, 1, 1, 1, 4]
        self.assertEqual(aggregate(runs(classes), "ordinal_mean")["result_class"], 2)
        self.assertEqual(aggregate(runs(classes), "median_class")["result_class"], 1)

    def test_expected_class_reads_the_centre_of_mass_not_the_peak(self) -> None:
        # Both articles peak at class 0, but they carry real mass at class 2. The peak
        # method reports 0; the centre of mass recognises the pull toward the middle.
        vectors = [[0.4, 0.1, 0.3, 0.1, 0.1], [0.4, 0.1, 0.3, 0.1, 0.1]]
        peak = aggregate(runs([0, 0], vectors), "mean_probabilities")
        centre = aggregate(runs([0, 0], vectors), "expected_class")
        self.assertEqual(peak["result_class"], 0)
        self.assertEqual(centre["result_class"], 1)
        self.assertAlmostEqual(centre["ordinal_mean"], 1.4)

    def test_confidence_weighting_lets_a_sure_minority_outweigh_hesitant_votes(self) -> None:
        # Two hesitant articles at class 0 against one certain article at class 3.
        classes = [0, 0, 3]
        vectors = [
            [0.30, 0.25, 0.20, 0.15, 0.10],
            [0.30, 0.25, 0.20, 0.15, 0.10],
            [0.01, 0.01, 0.01, 0.96, 0.01],
        ]
        self.assertEqual(aggregate(runs(classes), "majority_vote")["result_class"], 0)
        weighted = aggregate(runs(classes, vectors), "confidence_weighted_vote")
        self.assertEqual(weighted["result_class"], 3)
        # 0.30 + 0.30 against 0.96: the counted weights are reported, not just the
        # winner, and this is the one method whose weights differ from the raw counts.
        self.assertAlmostEqual(weighted["weighted_counts"][0], 0.60)
        self.assertAlmostEqual(weighted["weighted_counts"][3], 0.96)
        self.assertIsNone(aggregate(runs(classes), "majority_vote")["weighted_counts"])

    def test_every_declared_method_is_callable_and_reports_dispersion(self) -> None:
        # A method listed in the registry but not implemented would be a broken promise
        # to the interface, which builds its selector from that list.
        classes = [1, 2, 2, 3]
        vectors = [one_hot(value) for value in classes]
        for entry in METHODS:
            with self.subTest(method=entry["method"]):
                result = aggregate(runs(classes, vectors), entry["method"])
                self.assertIn(result["result_class"], range(5))
                self.assertIsNotNone(result["variance"])
                self.assertIsNotNone(result["dispersion_band"])

    def test_an_unknown_method_is_refused_rather_than_guessed(self) -> None:
        with self.assertRaises(AppError) as context:
            aggregate(runs([1, 2]), "mean_of_vibes")
        self.assertEqual(context.exception.code, "INVALID_INPUT")

    def test_a_single_article_is_not_an_aggregate(self) -> None:
        with self.assertRaises(AppError) as context:
            aggregate(runs([3]), "majority_vote")
        self.assertEqual(context.exception.code, "INSUFFICIENT_ARTICLES")


class DispersionTest(unittest.TestCase):
    def test_bands_follow_the_measured_thresholds(self) -> None:
        # The cut points are not cosmetic: they come from publisher-level error rates
        # measured on the study corpus, so they are pinned rather than left to drift.
        self.assertEqual([entry[0] for entry in DISPERSION_BANDS], [0.25, 1.00, None])
        self.assertEqual(dispersion_band(0.0), "stable")
        self.assertEqual(dispersion_band(0.2499), "stable")
        self.assertEqual(dispersion_band(0.25), "elevated")
        self.assertEqual(dispersion_band(0.999), "elevated")
        self.assertEqual(dispersion_band(1.0), "high")
        self.assertEqual(dispersion_band(9.9), "high")

    def test_identical_articles_report_no_spread_and_full_agreement(self) -> None:
        result = aggregate(runs([3, 3, 3, 3]), "majority_vote")
        self.assertEqual(result["variance"], 0)
        self.assertEqual(result["tolerant_variance"], 0)
        self.assertEqual(result["agreement"], 1)
        self.assertEqual(result["tolerant_agreement"], 1)
        self.assertEqual(result["dispersion_band"], "stable")

    def test_agreement_counts_articles_against_the_verdict_they_produced(self) -> None:
        # Classes 1, 1, 2, 4 with a majority verdict of 1: half the articles match it
        # exactly, three of four are within one class of it.
        result = aggregate(runs([1, 1, 2, 4]), "majority_vote")
        self.assertEqual(result["result_class"], 1)
        self.assertEqual(result["agreement"], 0.5)
        self.assertEqual(result["tolerant_agreement"], 0.75)

    def test_tolerant_variance_forgives_only_the_neighbouring_class(self) -> None:
        # Verdict 1. The article at class 2 is adjacent and costs nothing; the one at
        # class 4 is two classes beyond the allowance, so it contributes (3 - 1)^2 = 4.
        result = aggregate(runs([1, 1, 2, 4]), "majority_vote")
        self.assertEqual(result["tolerant_variance"], 4 / 4)
        self.assertGreater(result["variance"], 0)

    def test_the_mean_probability_profile_is_reported_whatever_the_method(self) -> None:
        # The averaged vector describes the data, not the counting rule. The charts show
        # it beside every verdict, so a hard-class method must not withhold it.
        vectors = [[0.1, 0.5, 0.2, 0.1, 0.1], [0.3, 0.3, 0.2, 0.1, 0.1]]
        result = aggregate(runs([1, 0], vectors), "majority_vote")
        self.assertAlmostEqual(result["mean_probabilities"][1], 0.4)
        # The legacy ``probabilities`` key stays specific to the method that earned it.
        self.assertIsNone(result["probabilities"])

    def test_a_hard_class_method_still_works_without_stored_probabilities(self) -> None:
        # Most imported dataset rows carry a vector, but not all do, and a missing one
        # must not break a method that never needed it.
        result = aggregate(runs([2, 2, 3]), "majority_vote")
        self.assertEqual(result["result_class"], 2)
        self.assertIsNone(result["mean_probabilities"])


if __name__ == "__main__":
    unittest.main()
