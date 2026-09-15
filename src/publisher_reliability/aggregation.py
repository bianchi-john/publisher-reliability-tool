"""Publisher-level scientific aggregation formulas."""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable

from .errors import AppError


WARNING = (
    "Predictions are estimates, not fact checks. A publisher result depends on "
    "the selected articles, exact checkpoint/fold, and aggregation method."
)

METHODS = [
    {
        "method": "majority_vote",
        "version": "1",
        "formula": "Most frequent hard class.",
        "minimum_count": 2,
        "probabilities_required": False,
        "tie_rule": "Smallest class wins.",
        "warning": WARNING,
    },
    {
        "method": "ordinal_mean",
        "version": "1",
        "formula": "Arithmetic mean of hard classes; floor(mean + 0.5).",
        "minimum_count": 2,
        "probabilities_required": False,
        "tie_rule": "Half values round upward.",
        "warning": WARNING,
    },
    {
        "method": "mean_probabilities",
        "version": "1",
        "formula": "Component-wise mean of five probability vectors.",
        "minimum_count": 2,
        "probabilities_required": True,
        "tie_rule": "Smallest maximum index wins.",
        "warning": WARNING,
    },
]


def aggregate(runs: Iterable[dict[str, str]], method: str) -> dict[str, object]:
    """Combine several article predictions into one publisher-level class.

    The three methods answer subtly different questions and are kept separate rather
    than blended: majority vote counts outlets' most common verdict, ordinal mean
    exploits the fact that the five reliability classes are ordered rather than merely
    distinct, and mean probabilities uses the full confidence vector and therefore
    refuses runs that lack one.

    Tie rules are fixed and documented in ``METHODS`` so that a repeated aggregation of
    the same runs always returns the same class. Two articles is the floor: a single
    prediction is not an aggregate, and reporting it as one would overstate what the
    publisher-level number means.
    """

    selected = list(runs)
    if len(selected) < 2:
        raise AppError(
            "INSUFFICIENT_ARTICLES",
            "At least two compatible article predictions are required.",
        )
    classes = [int(run["predicted_class"]) for run in selected]
    if any(value not in range(5) for value in classes):
        # Out-of-range means the stored ledger is corrupt, not that the caller erred.
        raise AppError("STORAGE_ERROR", "A prediction contains an invalid class.")

    if method == "majority_vote":
        counts = Counter(classes)
        largest = max(counts.values())
        # A tie resolves to the smallest class: the more cautious reading of the
        # evidence, and a deterministic one.
        result = min(value for value, count in counts.items() if count == largest)
        return {
            "result_class": result,
            "ordinal_mean": "",
            "probabilities": None,
            "class_counts": {str(key): counts.get(key, 0) for key in range(5)},
        }

    if method == "ordinal_mean":
        # Averaging class indices is only meaningful because the bands are ordered.
        # floor(mean + 0.5) rounds halves upward, unlike Python's banker's rounding.
        mean = sum(classes) / len(classes)
        return {
            "result_class": math.floor(mean + 0.5),
            "ordinal_mean": mean,
            "probabilities": None,
            "class_counts": {
                str(key): classes.count(key) for key in range(5)
            },
        }

    if method == "mean_probabilities":
        vectors: list[list[float]] = []
        for run in selected:
            values = [run[f"prob_class_{index}"] for index in range(5)]
            if any(value == "" for value in values):
                raise AppError(
                    "PROBABILITIES_REQUIRED",
                    "This aggregation method requires complete probabilities.",
                )
            vector = [float(value) for value in values]
            if (
                any(
                    not math.isfinite(value) or value < 0 or value > 1
                    for value in vector
                )
                or abs(sum(vector) - 1) > 1e-5
            ):
                raise AppError(
                    "STORAGE_ERROR",
                    "A prediction contains an invalid probability vector.",
                )
            vectors.append(vector)
        means = [
            sum(vector[index] for vector in vectors) / len(vectors)
            for index in range(5)
        ]
        largest = max(means)
        # index() returns the first maximum, so a tie resolves to the smallest class.
        return {
            "result_class": means.index(largest),
            "ordinal_mean": "",
            "probabilities": means,
            "class_counts": {
                str(key): classes.count(key) for key in range(5)
            },
        }

    raise AppError("INVALID_INPUT", "Unknown aggregation method.")
