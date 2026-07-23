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
    selected = list(runs)
    if len(selected) < 2:
        raise AppError(
            "INSUFFICIENT_ARTICLES",
            "At least two compatible article predictions are required.",
        )
    classes = [int(run["predicted_class"]) for run in selected]

    if method == "majority_vote":
        counts = Counter(classes)
        largest = max(counts.values())
        result = min(value for value, count in counts.items() if count == largest)
        return {
            "result_class": result,
            "ordinal_mean": "",
            "probabilities": None,
            "class_counts": {str(key): counts.get(key, 0) for key in range(5)},
        }

    if method == "ordinal_mean":
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
            vectors.append([float(value) for value in values])
        means = [
            sum(vector[index] for vector in vectors) / len(vectors)
            for index in range(5)
        ]
        largest = max(means)
        return {
            "result_class": means.index(largest),
            "ordinal_mean": "",
            "probabilities": means,
            "class_counts": {
                str(key): classes.count(key) for key in range(5)
            },
        }

    raise AppError("INVALID_INPUT", "Unknown aggregation method.")

