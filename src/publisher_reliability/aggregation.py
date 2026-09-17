"""Publisher-level scientific aggregation formulas and dispersion statistics.

Two ideas run through this module.

**The five classes are ordered, not merely distinct.** They are NewsGuard reliability
bands over a 0--100 score, so predicting class 3 for a class 4 publisher is a near
miss while predicting class 0 is a different judgement entirely. Methods that exploit
that ordering (ordinal mean, median, expected class) are kept alongside the ones that
do not (majority vote), because they answer different questions and a reader should be
able to see them disagree.

**Dispersion is reported, never hidden.** A publisher whose articles are classified all
over the range is telling you the model does not have a stable opinion about it. The
bands in ``DISPERSION_BANDS`` come from measured error rates, not taste: see the
comment there.

There is deliberately no "tolerant" counting mode here, although the underlying study
reports a tolerant accuracy that counts a prediction correct when it lands in an
adjacent band. That metric compares a prediction against a *true* label. Aggregation
has no true label to compare against -- it compares articles with the verdict they
themselves produced -- so spreading each vote onto its neighbours would not measure
tolerance to error; it would merely smooth the histogram, using a weight nobody
measured. A reader who wants the ordering respected already has three methods that
respect it openly. Adjacency survives only where it needs no ground truth: in the
dispersion statistics below, which describe how far the articles sit from each other.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable

from .errors import AppError


WARNING = (
    "Predictions are estimates, not fact checks. A publisher result depends on "
    "the selected articles, exact checkpoint/fold, and aggregation method."
)

# Variance of the predicted classes across a publisher's articles, banded by the
# publisher-level error rates measured on the study corpus (10 articles per outlet):
#
#   variance    majority error   tolerant error
#   0.00-0.25            ~4 %            ~1 %
#   0.25-0.50           ~43 %           ~12 %
#   0.50-1.00           ~55 %           ~18 %
#   1.00-1.50           ~64 %           ~22 %
#   1.50-2.00           ~82 %           ~43 %
#
# The cliff is at 0.25: below it the aggregate is usually right, immediately above it
# the error rate multiplies tenfold. 1.00 is the second step, where even the tolerant
# reading fails more than a fifth of the time.
DISPERSION_BANDS = (
    (
        0.25,
        "stable",
        "The articles agree. On the study corpus this band carried roughly a 4% "
        "publisher-level error rate, 1% when adjacent classes are allowed.",
    ),
    (
        1.00,
        "elevated",
        "The articles disagree noticeably. On the study corpus this band carried a "
        "43-55% publisher-level error rate, 12-18% when adjacent classes are allowed: "
        "read this verdict as indicative only.",
    ),
    (
        None,
        "high",
        "The articles disagree severely, so no single class represents this publisher "
        "well. On the study corpus this band carried a 64-82% publisher-level error "
        "rate, 22-43% when adjacent classes are allowed.",
    ),
)

METHODS = [
    {
        "method": "majority_vote",
        "label": "Majority vote",
        "version": "2",
        "formula": "Most frequent hard class.",
        "description": (
            "Counts how many articles landed in each class and takes the largest "
            "count. Ignores how close the classes are to each other."
        ),
        "minimum_count": 2,
        "probabilities_required": False,
        "tie_rule": "Smallest class wins.",
        "warning": WARNING,
    },
    {
        "method": "ordinal_mean",
        "label": "Ordinal mean",
        "version": "2",
        "formula": "Arithmetic mean of hard classes; floor(mean + 0.5).",
        "description": (
            "Averages the class indices, so a publisher split between classes 1 and 3 "
            "reads as 2 rather than arbitrarily picking one side."
        ),
        "minimum_count": 2,
        "probabilities_required": False,
        "tie_rule": "Half values round upward.",
        "warning": WARNING,
    },
    {
        "method": "median_class",
        "label": "Median class",
        "version": "1",
        "formula": "Lower median of the hard classes.",
        "description": (
            "The middle article once they are sorted by class. Unlike the mean, a "
            "handful of extreme articles cannot drag the verdict."
        ),
        "minimum_count": 2,
        "probabilities_required": False,
        "tie_rule": "Lower of the two middle classes wins.",
        "warning": WARNING,
    },
    {
        "method": "mean_probabilities",
        "label": "Mean probabilities",
        "version": "2",
        "formula": "Component-wise mean of five probability vectors; arg max.",
        "description": (
            "Averages the full probability vectors and takes the peak, so an article "
            "that was barely confident counts for less than one that was certain."
        ),
        "minimum_count": 2,
        "probabilities_required": True,
        "tie_rule": "Smallest maximum index wins.",
        "warning": WARNING,
    },
    {
        "method": "expected_class",
        "label": "Expected class",
        "version": "1",
        "formula": "sum(k * mean P(k)) over k; floor(value + 0.5).",
        "description": (
            "The centre of mass of the averaged probability vector rather than its "
            "peak. Closest to treating reliability as the 0-100 grade underneath the "
            "five bands."
        ),
        "minimum_count": 2,
        "probabilities_required": True,
        "tie_rule": "Half values round upward.",
        "warning": WARNING,
    },
    {
        "method": "confidence_weighted_vote",
        "label": "Confidence-weighted vote",
        "version": "1",
        "formula": "Vote per article weighted by its own maximum probability.",
        "description": (
            "A majority vote in which a hesitant article carries less weight than a "
            "confident one, without discarding it."
        ),
        "minimum_count": 2,
        "probabilities_required": True,
        "tie_rule": "Smallest class wins.",
        "warning": WARNING,
    },
]

METHOD_NAMES = tuple(entry["method"] for entry in METHODS)


def dispersion_band(variance: float) -> str:
    """Name the risk band a class variance falls into."""

    for upper, name, _description in DISPERSION_BANDS:
        if upper is None or variance < upper:
            return name
    return DISPERSION_BANDS[-1][1]


def band_description(name: str) -> str:
    return next(
        description for _upper, band, description in DISPERSION_BANDS if band == name
    )


def _classes(runs: list[dict[str, str]]) -> list[int]:
    classes = [int(run["predicted_class"]) for run in runs]
    if any(value not in range(5) for value in classes):
        # Out-of-range means the stored ledger is corrupt, not that the caller erred.
        raise AppError("STORAGE_ERROR", "A prediction contains an invalid class.")
    return classes


def _vectors(runs: list[dict[str, str]]) -> list[list[float]]:
    """Read the five probabilities of every run, refusing to guess a missing one."""

    vectors: list[list[float]] = []
    for run in runs:
        values = [run[f"prob_class_{index}"] for index in range(5)]
        if any(value == "" for value in values):
            raise AppError(
                "PROBABILITIES_REQUIRED",
                "This aggregation method requires complete probabilities.",
            )
        vector = [float(value) for value in values]
        if (
            any(
                not math.isfinite(value) or value < 0 or value > 1 for value in vector
            )
            or abs(sum(vector) - 1) > 1e-5
        ):
            raise AppError(
                "STORAGE_ERROR", "A prediction contains an invalid probability vector."
            )
        vectors.append(vector)
    return vectors


def _arg_max(values: list[float]) -> int:
    """Index of the largest value; ties resolve to the smallest class."""

    largest = max(values)
    return next(index for index, value in enumerate(values) if value == largest)


def _dispersion(classes: list[int], result: int) -> dict[str, object]:
    """Describe how far the articles sit from each other and from the verdict.

    ``variance`` is the ordinary population variance of the class indices, the same
    statistic the study's error-rate bands were measured against.

    ``tolerant_variance`` and ``tolerant_agreement`` charge nothing for landing in a
    class adjacent to the verdict, isolating the disagreement the ordinal scale cannot
    excuse. Unlike a tolerant *accuracy*, these need no true label: they measure how far
    the articles sit from the verdict they themselves produced, not from the truth.
    Both are relative to ``result``, so they move when the counting rule does.
    """

    mean = sum(classes) / len(classes)
    variance = sum((value - mean) ** 2 for value in classes) / len(classes)
    tolerant_variance = sum(
        max(0.0, abs(value - result) - 1) ** 2 for value in classes
    ) / len(classes)
    exact = sum(1 for value in classes if value == result)
    adjacent = sum(1 for value in classes if abs(value - result) <= 1)
    band = dispersion_band(variance)
    return {
        "mean_class": mean,
        "variance": variance,
        "tolerant_variance": tolerant_variance,
        "agreement": exact / len(classes),
        "tolerant_agreement": adjacent / len(classes),
        "dispersion_band": band,
        "dispersion_note": band_description(band),
    }


def aggregate(runs: Iterable[dict[str, str]], method: str) -> dict[str, object]:
    """Combine several article predictions into one publisher-level class.

    Every method reports the same dispersion statistics alongside its verdict, so a
    confident-looking class and the disagreement behind it are never separated. Two
    articles is the floor: a single prediction is not an aggregate, and reporting it as
    one would overstate what the publisher-level number means.
    """

    if method not in METHOD_NAMES:
        raise AppError("INVALID_INPUT", "Unknown aggregation method.")

    selected = list(runs)
    if len(selected) < 2:
        raise AppError(
            "INSUFFICIENT_ARTICLES",
            "At least two compatible article predictions are required.",
        )
    classes = _classes(selected)
    counts = Counter(classes)
    class_counts = {str(key): counts.get(key, 0) for key in range(5)}

    needs_probabilities = next(
        entry["probabilities_required"] for entry in METHODS if entry["method"] == method
    )
    # The averaged probability vector describes the data, not the counting rule, so it
    # is reported whenever the stored runs carry one. Only a method that cannot work
    # without it turns a missing vector into a refusal.
    try:
        vectors = _vectors(selected)
    except AppError as exc:
        if needs_probabilities or exc.code != "PROBABILITIES_REQUIRED":
            raise
        vectors = None
    mean_vector = (
        [sum(vector[index] for vector in vectors) / len(vectors) for index in range(5)]
        if vectors
        else None
    )

    weighted_counts: list[float] | None = None
    ordinal_mean: float | str = ""

    if method == "majority_vote":
        result = _arg_max([float(counts.get(key, 0)) for key in range(5)])

    elif method == "ordinal_mean":
        mean = sum(classes) / len(classes)
        ordinal_mean = mean
        # floor(mean + 0.5) rounds halves upward, unlike Python's banker's rounding.
        result = math.floor(mean + 0.5)

    elif method == "median_class":
        ordered = sorted(classes)
        # Lower median: with an even count the more cautious of the two middles.
        result = ordered[(len(ordered) - 1) // 2]

    elif method == "mean_probabilities":
        assert mean_vector is not None
        result = _arg_max(mean_vector)

    elif method == "expected_class":
        assert mean_vector is not None
        expectation = sum(index * value for index, value in enumerate(mean_vector))
        ordinal_mean = expectation
        result = math.floor(expectation + 0.5)

    else:  # confidence_weighted_vote
        assert vectors is not None
        weights = [0.0] * 5
        for predicted, vector in zip(classes, vectors, strict=True):
            weights[predicted] += max(vector)
        weighted_counts = weights
        result = _arg_max(weights)

    return {
        "result_class": result,
        "ordinal_mean": ordinal_mean,
        "probabilities": mean_vector if method == "mean_probabilities" else None,
        "mean_probabilities": mean_vector,
        "class_counts": class_counts,
        "weighted_counts": weighted_counts,
        **_dispersion(classes, result),
    }
