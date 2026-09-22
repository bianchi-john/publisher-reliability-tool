"""Shared query and evaluation services used by the API and CLI."""

from __future__ import annotations

import csv
import io
import json
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Iterable

from .aggregation import METHODS, WARNING, aggregate
from .errors import AppError
from .page_kind import refuse_site_address
from .identity import article_id, normalize_url, normalized_hostname, publisher_id
from .inference import InferenceEngine, RetrievedArticle, fetch_article
from .prediction_dataset import sync_user_predictions
from .storage import Storage, json_field, utc_now


INFERENCE_PHASES = {
    "verifying the checkpoint digest": 40,
    "preparing the pinned tokenizer": 55,
    "loading the model weights": 65,
    "classifying the article text": 78,
}

PREDICTION_EXPORT_COLUMNS = [
    "article_id",
    "url",
    "domain",
    "publisher_id",
    "prediction_origin",
    "prediction_run_id",
    "model_id",
    "prediction_family",
    "prediction_fold_id",
    "prediction_model_name",
    "prediction_model_provenance",
    "prediction_official_manifest_entry_sha256",
    "predicted_label",
    *[f"prob_class_{index}" for index in range(5)],
    "prediction_action",
    "input_source",
    "content_retention",
    "job_id",
    "inference_started_at",
    "inference_completed_at",
    "duration_ms",
    "device",
    "software_versions_json",
    "recorded_at",
]


def _effective_time(run: dict[str, str]) -> str:
    return run["inference_completed_at"] or run["recorded_at"]


def newest_runs(runs: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    result = sorted(runs, key=lambda row: row["prediction_run_id"])
    result.sort(key=_effective_time, reverse=True)
    return result


def paginate(items: list[dict[str, object]], limit: int, offset: int) -> dict[str, object]:
    if limit not in {25, 50, 100} or not 0 <= offset <= 1_000_000:
        raise AppError(
            "INVALID_INPUT",
            "limit must be 25, 50, or 100 and offset must be between 0 and 1,000,000.",
        )
    page_items = items[offset : offset + limit]
    next_offset = offset + limit if offset + limit < len(items) else None
    return {
        "items": page_items,
        "page": {"limit": limit, "offset": offset, "next_offset": next_offset},
    }


class ResearchService:
    def __init__(
        self,
        storage: Storage,
        *,
        offline: bool = False,
        model_roots: tuple[Path, ...] = (),
        device: str = "auto",
        inference_engine: InferenceEngine | None = None,
        prediction_dataset_dir: Path | None = None,
    ):
        self.storage = storage
        self.offline = offline
        self.prediction_dataset_dir = prediction_dataset_dir
        self.inference = inference_engine or InferenceEngine(
            storage,
            model_roots=model_roots,
            offline=offline,
            device=device,
        )

    @property
    def models_by_id(self) -> dict[str, dict[str, str]]:
        return {row["model_id"]: row for row in self.storage.rows["models"]}

    @property
    def runs_by_id(self) -> dict[str, dict[str, str]]:
        return {
            row["prediction_run_id"]: row
            for row in self.storage.rows["prediction_runs"]
        }

    @staticmethod
    def model_provenance(model: dict[str, str]) -> str:
        if model.get("artifact_kind") == "historical_virtual":
            try:
                source = json.loads(model.get("runtime_scientific_json") or "{}").get(
                    "source_model_provenance"
                )
            except json.JSONDecodeError:
                source = None
            if source in {"paper_official", "user_custom", "local_checkpoint"}:
                return source
            return "paper_dataset"
        if model.get("official_manifest_entry_sha256"):
            return "paper_official"
        if model.get("artifact_kind", "").startswith("custom_"):
            return "user_custom"
        return "local_checkpoint"

    def _imported_fold_registry(self) -> dict[str, set[int]]:
        """Map each imported article to the cross-validation fold that held it out.

        The fold is recorded per article rather than per model family because every
        family in the study was split the same way: one publisher-disjoint
        ``StratifiedKFold(n_splits=5, shuffle=True, random_state=42)`` over the same
        publisher list. An article held out in fold 3 is therefore held out in fold 3
        for every family trained on it, and was in the training set of the other four
        folds.

        Keying the registry by article rather than by family is therefore both simpler
        and safer: the guard depends only on where an article sat in the split, so it
        cannot be defeated by a checkpoint whose own family happens to have no stored
        predictions to derive a fold from.
        """

        registry: dict[str, set[int]] = defaultdict(set)
        models = self.models_by_id
        for run in self.storage.rows["prediction_runs"]:
            if run["origin"] not in {"bundled_import", "user_import"}:
                continue
            model = models.get(run["model_id"])
            if model is not None:
                registry[run["article_id"]].add(int(model["fold_id"]))
        return registry

    @staticmethod
    def _fold_is_safe(
        model: dict[str, str],
        article_identifier: str,
        registry: dict[str, set[int]],
    ) -> bool:
        """Whether this checkpoint may evaluate this article without leakage.

        Safe means one of: the article is unknown to the imported dataset, or it was
        held out in exactly the fold this checkpoint was validated on. An article
        recorded against several folds is never safe, because no single held-out fold
        can be established for it.
        """

        assigned = registry.get(article_identifier, set())
        return not assigned or (
            len(assigned) == 1 and int(model["fold_id"]) in assigned
        )

    def article_summaries(
        self,
        *,
        q: str | None = None,
        publisher: str | None = None,
        model_id: str | None = None,
        predicted_class: int | None = None,
        origin: str | None = None,
        article_source: str | None = None,
        sort: str = "updated_desc",
    ) -> list[dict[str, object]]:
        """Derive the article list from prediction runs; there is no article table.

        An article exists because something predicted on it, so the runs are the source
        of truth and the summary is recomputed rather than cached. Note that the source
        type is decided from every run of the article, not from the filtered subset: a
        dataset article stays a dataset article even when the current filter only shows
        its user evaluation.
        """

        if article_source not in {None, "dataset", "user_evaluation"}:
            raise AppError("INVALID_INPUT", "Unknown article source filter.")
        origin_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for run in self.storage.rows["prediction_runs"]:
            origin_counts[run["article_id"]][run["origin"]] += 1
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for run in self.storage.rows["prediction_runs"]:
            if model_id and run["model_id"] != model_id:
                continue
            if predicted_class is not None and run["predicted_class"] != str(predicted_class):
                continue
            if origin and run["origin"] != origin:
                continue
            if publisher and run["normalized_hostname"] != publisher:
                continue
            if q and q.lower() not in run["canonical_url"].lower():
                continue
            grouped[run["article_id"]].append(run)

        content_ids = {row["article_id"] for row in self.storage.rows["local_content"]}
        summaries: list[dict[str, object]] = []
        for art_id, runs in grouped.items():
            counts = origin_counts[art_id]
            dataset_run_count = counts["bundled_import"] + counts["user_import"]
            local_run_count = counts["local_inference"]
            source_type = "dataset" if dataset_run_count else "user_evaluation"
            if article_source and source_type != article_source:
                continue
            ordered = newest_runs(runs)
            latest = ordered[0]
            summaries.append(
                {
                    "article_id": art_id,
                    "canonical_url": latest["canonical_url"],
                    "publisher_id": latest["publisher_id"],
                    "normalized_hostname": latest["normalized_hostname"],
                    "model_count": len({run["model_id"] for run in runs}),
                    "run_count": len(runs),
                    "latest_prediction_run_id": latest["prediction_run_id"],
                    "latest_model_id": latest["model_id"],
                    "latest_predicted_class": int(latest["predicted_class"]),
                    "source_type": source_type,
                    "dataset_run_count": dataset_run_count,
                    "local_run_count": local_run_count,
                    "has_user_evaluation": bool(local_run_count),
                    "content_saved": art_id in content_ids,
                    "first_seen_at": min(run["recorded_at"] for run in runs),
                    "updated_at": max(_effective_time(run) for run in runs),
                }
            )
        if sort == "url_asc":
            summaries.sort(key=lambda row: str(row["canonical_url"]))
        elif sort == "updated_desc":
            summaries.sort(key=lambda row: str(row["canonical_url"]))
            summaries.sort(key=lambda row: str(row["updated_at"]), reverse=True)
        else:
            raise AppError("INVALID_INPUT", "Unknown article sort.")
        return summaries

    def article(self, identifier: str) -> dict[str, object]:
        summary = next(
            (
                item
                for item in self.article_summaries()
                if item["article_id"] == identifier
            ),
            None,
        )
        if summary is None:
            raise AppError("NOT_FOUND", "Article was not found.")
        runs = newest_runs(
            row
            for row in self.storage.rows["prediction_runs"]
            if row["article_id"] == identifier
        )
        return {
            **summary,
            "runs": [self.run_summary(run) for run in runs],
            "warning": WARNING,
        }

    def run_summary(self, run: dict[str, str]) -> dict[str, object]:
        model = self.models_by_id.get(run["model_id"], {})
        probabilities = [
            float(run[f"prob_class_{index}"])
            if run[f"prob_class_{index}"] != ""
            else None
            for index in range(5)
        ]
        return {
            **run,
            "predicted_class": int(run["predicted_class"]),
            "probabilities": probabilities if all(v is not None for v in probabilities) else None,
            "family": model.get("family"),
            "fold_id": int(model["fold_id"]) if model.get("fold_id") else None,
            "model_display_name": model.get("display_name"),
            "model_provenance": self.model_provenance(model) if model else None,
        }

    def prediction_runs(self, **filters: str | None) -> list[dict[str, object]]:
        result = []
        models = self.models_by_id
        for run in self.storage.rows["prediction_runs"]:
            if any(
                value and run[key] != value
                for key, value in filters.items()
                if key in run
            ):
                continue
            family = filters.get("family")
            if family and models.get(run["model_id"], {}).get("family") != family:
                continue
            result.append(self.run_summary(run))
        result = sorted(result, key=lambda row: str(row["prediction_run_id"]))
        result.sort(
            key=lambda row: str(row["inference_completed_at"] or row["recorded_at"]),
            reverse=True,
        )
        return result

    def prediction_run(self, identifier: str) -> dict[str, object]:
        row = self.runs_by_id.get(identifier)
        if row is None:
            raise AppError("NOT_FOUND", "Prediction run was not found.")
        return {
            **self.run_summary(row),
            "article": {
                "article_id": row["article_id"],
                "canonical_url": row["canonical_url"],
                "publisher_id": row["publisher_id"],
                "normalized_hostname": row["normalized_hostname"],
            },
            "model": self.models_by_id.get(row["model_id"]),
            "warning": WARNING,
        }

    def publisher_summaries(
        self, *, q: str | None = None, model_id: str | None = None
    ) -> list[dict[str, object]]:
        """Derive publishers from the hostnames present in prediction runs.

        A publisher-level class is not counted here because none is stored: it is
        derived on demand from these runs by ``publisher_aggregation``.
        """

        runs: dict[str, list[dict[str, str]]] = defaultdict(list)
        for run in self.storage.rows["prediction_runs"]:
            if q and q.lower() not in run["normalized_hostname"].lower():
                continue
            if model_id and run["model_id"] != model_id:
                continue
            runs[run["publisher_id"]].append(run)
        result = []
        for pub_id, rows in runs.items():
            result.append(
                {
                    "publisher_id": pub_id,
                    "normalized_hostname": rows[0]["normalized_hostname"],
                    "article_count": len({row["article_id"] for row in rows}),
                    "run_count": len(rows),
                    "model_count": len({row["model_id"] for row in rows}),
                    "probability_run_count": sum(
                        bool(row["prob_class_0"]) for row in rows
                    ),
                }
            )
        result.sort(key=lambda row: str(row["normalized_hostname"]))
        return result

    def publisher(self, identifier: str) -> dict[str, object]:
        summary = next(
            (
                item
                for item in self.publisher_summaries()
                if item["publisher_id"] == identifier
            ),
            None,
        )
        if summary is None:
            raise AppError("NOT_FOUND", "Publisher was not found.")
        rows = [
            row
            for row in self.storage.rows["prediction_runs"]
            if row["publisher_id"] == identifier
        ]
        class_counts: dict[str, Counter[int]] = defaultdict(Counter)
        for row in rows:
            class_counts[row["model_id"]][int(row["predicted_class"])] += 1
        articles = [
            item
            for item in self.article_summaries()
            if item["publisher_id"] == identifier
        ][:20]
        return {
            **summary,
            "counts_by_model_class": {
                model: {str(index): counts.get(index, 0) for index in range(5)}
                for model, counts in class_counts.items()
            },
            "articles": articles,
            "warning": WARNING,
        }

    UNAVAILABLE = (
        "At least two leakage-safe articles are required for an aggregate."
    )

    @staticmethod
    def _empty_aggregate(reason: str) -> dict[str, object]:
        """The shape every group reports when it cannot produce a class.

        The keys are the same ones a successful aggregate carries, so the interface
        never has to branch on presence: it branches on ``result_class`` being null.
        """

        return {
            "result_class": None,
            "ordinal_mean": None,
            "probabilities": None,
            "mean_probabilities": None,
            "weighted_counts": None,
            "class_counts": {str(index): 0 for index in range(5)},
            "mean_class": None,
            "variance": None,
            "tolerant_variance": None,
            "agreement": None,
            "tolerant_agreement": None,
            "dispersion_band": None,
            "dispersion_note": None,
            "unavailable_reason": reason,
        }

    def _aggregate_or_reason(
        self, runs: list[dict[str, str]], method: str
    ) -> dict[str, object]:
        """Aggregate a group, turning a refusal into a displayable reason.

        A model that cannot be aggregated is not an error for the whole page: the
        other models still have something to say, so the refusal is reported in place
        of that one verdict rather than raised.
        """

        if len(runs) < 2:
            return self._empty_aggregate(self.UNAVAILABLE)
        try:
            calculation = aggregate(runs, method)
        except AppError as exc:
            return self._empty_aggregate(exc.message)
        # aggregate() reports "" for a method that computes no ordinal mean, and a
        # float for one that does. Only the empty string means "not applicable":
        # testing truthiness instead would turn a real mean of 0.0 into a null, which
        # is exactly what a publisher whose articles all sit in the lowest class has.
        ordinal_mean = calculation["ordinal_mean"]
        return {
            **calculation,
            "ordinal_mean": None if ordinal_mean == "" else ordinal_mean,
            "unavailable_reason": None,
        }

    def publisher_aggregation(
        self,
        identifier: str,
        *,
        method: str = "majority_vote",
        excluded_article_ids: Iterable[str] = (),
    ) -> dict[str, object]:
        """Derive publisher-level classes from the stored article predictions.

        A publisher's reliability class is not a separate record a user creates; it is
        a reading of the article predictions already held, and it changes with the
        counting rule and with which articles are considered. So it is recomputed on
        every request from the current runs instead of being frozen into a ledger row.

        One measurement is one exact checkpoint. Predictions are never pooled across
        models, not even across folds of one family: the study split publishers
        between folds, so each checkpoint saw a different part of the corpus, and
        merging their verdicts would report a number no model produced while hiding
        any publisher whose articles unexpectedly straddle a fold boundary. Those
        cases are worth seeing, not smoothing over.

        Nothing is written: this is a read of the ledger, not a record in it.
        """

        if method not in {row["method"] for row in METHODS}:
            raise AppError("INVALID_INPUT", "Unknown aggregation method.")
        summary = next(
            (
                item
                for item in self.publisher_summaries()
                if item["publisher_id"] == identifier
            ),
            None,
        )
        if summary is None:
            raise AppError("NOT_FOUND", "Publisher was not found.")

        excluded = {str(value) for value in excluded_article_ids}
        fold_registry = self._imported_fold_registry()
        models = self.models_by_id
        by_group: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
        # The exact article set the caller may exclude from, URLs included, so the
        # interface never has to guess it from a paginated run listing.
        considered: dict[str, str] = {}
        for run in self.storage.rows["prediction_runs"]:
            if run["publisher_id"] != identifier:
                continue
            model = models.get(run["model_id"])
            if model is None or not self._fold_is_safe(
                model, run["article_id"], fold_registry
            ):
                continue
            # One run per article per model: a page re-evaluated many times must not
            # count more than a page evaluated once.
            current = by_group[run["model_id"]].get(run["article_id"])
            if current is None or newest_runs([current, run])[0] is run:
                by_group[run["model_id"]][run["article_id"]] = run
            considered[run["article_id"]] = run["canonical_url"]

        results: list[dict[str, object]] = []
        for model_identifier, runs_by_article in by_group.items():
            model = models[model_identifier]
            eligible = newest_runs(
                [run for article, run in runs_by_article.items() if article not in excluded]
            )
            entry: dict[str, object] = {
                "model_id": model_identifier,
                "family": model["family"],
                "fold_id": int(model["fold_id"]),
                "display_name": model["display_name"],
                "provenance": self.model_provenance(model),
                "available_count": len(runs_by_article),
                "used_count": len(eligible),
                "excluded_count": len(runs_by_article) - len(eligible),
            }
            entry.update(self._aggregate_or_reason(eligible, method))
            # Per-article detail for the charts: the strip of individual verdicts is
            # the only honest way to show why a variance is what it is.
            entry["articles"] = sorted(
                (
                    {
                        "article_id": article,
                        "predicted_class": int(run["predicted_class"]),
                        "confidence": self._run_confidence(run),
                        "excluded": article in excluded,
                    }
                    for article, run in runs_by_article.items()
                ),
                key=lambda item: str(item["article_id"]),
            )
            entry["article_ids"] = sorted(runs_by_article)
            results.append(entry)

        results.sort(key=lambda row: (str(row["family"]), int(row["fold_id"])))
        return {
            "publisher_id": identifier,
            "normalized_hostname": summary["normalized_hostname"],
            "method": method,
            "excluded_article_ids": sorted(excluded),
            "articles": [
                {
                    "article_id": article,
                    "canonical_url": url,
                    "excluded": article in excluded,
                }
                for article, url in sorted(considered.items(), key=lambda kv: kv[1])
            ],
            "models": results,
            "warning": WARNING,
        }

    @staticmethod
    def _run_confidence(run: dict[str, str]) -> float | None:
        """How sure the model was, or nothing when the vector was not stored."""

        values = [run[f"prob_class_{index}"] for index in range(5)]
        if any(value == "" for value in values):
            return None
        return max(float(value) for value in values)

    def models(self, *, family: str | None = None, status: str | None = None):
        rows = [
            {
                **row,
                "fold_id": int(row["fold_id"]),
                "artifact_available": row["artifact_available"] == "true",
                "runnable": row["runnable"] == "true",
                "identity_kind": (
                    "historical"
                    if row["artifact_kind"] == "historical_virtual"
                    else "local"
                ),
                "support_level": (
                    "core"
                    if row["family"] in {"bert", "roberta"}
                    else "paper_llm"
                    if row["official_manifest_entry_sha256"]
                    else "custom"
                    if row["artifact_kind"].startswith("custom_")
                    else "optional"
                ),
                "provenance": self.model_provenance(row),
            }
            for row in self.storage.rows["models"]
            if (not family or row["family"] == family)
            and (not status or row["status"] == status)
        ]
        rows.sort(key=lambda row: (str(row["family"]), int(row["fold_id"])))
        return rows

    def available_models(self, *, url: str) -> dict[str, object]:
        """Explain which local checkpoints may classify one article URL, and why not.

        The interface never offers a checkpoint it cannot honour, so this answers two
        questions at once: which options are genuinely selectable, and why the rest are
        not. The explanation carries as much weight as the list, because "nothing is
        available" has several unrelated causes: no checkpoint installed, no installed
        family and fold matching the stored predictions, or a leakage guard that
        rejects every installed fold.

        One article is the only input. A publisher class is read from the articles
        already classified, by ``publisher_aggregation``, so there is no availability
        question to ask about a publisher before evaluating it.
        """

        canonical = normalize_url(url)
        # Refused here as well as during retrieval, so the interface can say that
        # a homepage is a homepage while the reader is still typing, instead of
        # letting them start a job that is certain to fail.
        refuse_site_address(canonical)
        identifier = article_id(canonical)
        stored_runs = [
            row
            for row in self.storage.rows["prediction_runs"]
            if row["article_id"] == identifier
        ]
        local_models = [
            model
            for model in self.storage.rows["models"]
            if model["artifact_kind"] != "historical_virtual"
            and model["artifact_available"] == "true"
        ]
        fold_registry = self._imported_fold_registry()

        options = self._stored_prediction_options(
            stored_runs, local_models, fold_registry
        )
        new_options, blocked = self._new_inference_options(
            local_models,
            fold_registry,
            identifier,
            {str(row["model_id"]) for row in options},
        )
        options.extend(new_options)

        # Stored reuse before new inference, then a stable family/fold order so the
        # selector does not reshuffle between refreshes.
        options.sort(
            key=lambda row: (
                not bool(row["eligible"]),
                str(row["mode"]),
                str(row["family"]),
                int(row["fold_id"]),
            )
        )
        code, message = self._availability_verdict(
            options=options,
            local_model_count=len(local_models),
            input_known=bool(stored_runs),
            blocked=blocked,
        )
        return {
            "items": options,
            "availability": {
                "code": code,
                "message": message,
                "input_known": bool(stored_runs),
                "local_checkpoint_count": len(local_models),
                "eligible_model_count": sum(bool(row["eligible"]) for row in options),
                "blocked_training_models": blocked,
            },
        }

    def _stored_prediction_options(
        self,
        stored_runs: list[dict[str, str]],
        local_models: list[dict[str, str]],
        fold_registry: dict[str, set[int]],
    ) -> list[dict[str, object]]:
        """Options that reuse a prediction already stored for this article.

        A stored run is offered only when the same family and fold is installed here,
        so the workspace never promises a reproduction it cannot perform, and only when
        the leakage guard accepts it. Anything that survives both conditions can be
        honoured, which is why every option returned here is eligible.
        """

        local_by_family_fold: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
        for model in local_models:
            local_by_family_fold[(model["family"], int(model["fold_id"]))].append(model)

        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for run in stored_runs:
            grouped[run["model_id"]].append(run)

        models = self.models_by_id
        options: list[dict[str, object]] = []
        for model_identifier, runs in grouped.items():
            model = models.get(model_identifier)
            if model is None:
                continue
            local_matches = local_by_family_fold.get(
                (model["family"], int(model["fold_id"])), []
            )
            if not local_matches:
                continue
            safe_runs = [
                run
                for run in runs
                if self._fold_is_safe(model, run["article_id"], fold_registry)
            ]
            if not safe_runs:
                continue
            # Prefer a compatible checkpoint; the ID breaks ties so the choice is stable.
            local_model = sorted(
                local_matches,
                key=lambda row: (row["status"] != "compatible", row["model_id"]),
            )[0]
            article_count = len({run["article_id"] for run in safe_runs})
            options.append(
                {
                    "model_id": model_identifier,
                    "local_model_id": local_model["model_id"],
                    "family": model["family"],
                    "fold_id": int(model["fold_id"]),
                    "display_name": model["display_name"],
                    "provenance": self.model_provenance(local_model),
                    "local_status": local_model["status"],
                    "local_runnable": local_model["runnable"] == "true",
                    "article_count": article_count,
                    "run_count": len(safe_runs),
                    "probability_count": sum(
                        bool(run["prob_class_0"]) for run in safe_runs
                    ),
                    "eligible": True,
                    "mode": "stored_prediction",
                }
            )
        return options

    def _new_inference_options(
        self,
        local_models: list[dict[str, str]],
        fold_registry: dict[str, set[int]],
        article_identifier: str,
        already_offered: set[str],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """Checkpoints that may classify this article now, and those the guard blocks.

        Only single articles reach this path, because a publisher result aggregates
        stored predictions and never retrieves a page. A checkpoint is blocked when the
        imported folds show it was trained on this article, or when the article belongs
        to several folds at once and no choice can be defended as held out.
        """

        options: list[dict[str, object]] = []
        blocked: list[dict[str, object]] = []
        for local_model in local_models:
            family = local_model["family"]
            fold_id = int(local_model["fold_id"])
            assigned_folds = fold_registry.get(article_identifier, set())
            if len(assigned_folds) > 1:
                blocked.append(
                    {
                        "family": family,
                        "fold_id": fold_id,
                        "reason": (
                            "The canonical article appears in multiple imported "
                            "folds, so no checkpoint is leakage-safe."
                        ),
                    }
                )
                continue
            if assigned_folds and fold_id not in assigned_folds:
                blocked.append(
                    {
                        "family": family,
                        "fold_id": fold_id,
                        "reason": (
                            "The article belongs to another held-out fold, so "
                            "this checkpoint was trained on it."
                        ),
                    }
                )
                continue
            # Skip a checkpoint already offered as stored reuse, one whose held-out
            # fold makes the stored run the honest answer, and one that cannot run here.
            if (
                local_model["model_id"] in already_offered
                or (assigned_folds and fold_id in assigned_folds)
                or local_model["runnable"] != "true"
            ):
                continue
            options.append(
                {
                    "model_id": local_model["model_id"],
                    "local_model_id": local_model["model_id"],
                    "family": family,
                    "fold_id": fold_id,
                    "display_name": local_model["display_name"],
                    "provenance": self.model_provenance(local_model),
                    "local_status": local_model["status"],
                    "local_runnable": True,
                    "article_count": 0,
                    "run_count": 0,
                    "probability_count": 0,
                    "eligible": True,
                    "mode": "new_inference",
                }
            )
        return options, blocked

    @staticmethod
    def _availability_verdict(
        *,
        options: list[dict[str, object]],
        local_model_count: int,
        input_known: bool,
        blocked: list[dict[str, object]],
    ) -> tuple[str, str]:
        """Name the one reason that explains this outcome, most specific cause first."""

        eligible_count = sum(bool(row["eligible"]) for row in options)
        if not local_model_count:
            return (
                "NO_LOCAL_CHECKPOINTS",
                "No validated local checkpoint is available. Add a supported model "
                "under Models and scan the configured directories.",
            )
        if eligible_count:
            if any(
                row["eligible"] and row["mode"] == "new_inference" for row in options
            ):
                return (
                    "AVAILABLE",
                    f"{eligible_count} model option(s) are available. Options marked "
                    "'new inference' will retrieve and classify this page locally.",
                )
            return (
                "AVAILABLE",
                f"{eligible_count} local checkpoint(s) have enough leakage-safe "
                "stored predictions for this request.",
            )
        if not input_known:
            return (
                "NEW_ARTICLE_REQUIRES_INFERENCE",
                "This URL is not present in the imported prediction dataset. It requires "
                "a new inference run, but no runnable local model is available.",
            )
        if blocked:
            if any("multiple imported folds" in str(row["reason"]) for row in blocked):
                return (
                    "TRAINING_DATA_LEAKAGE",
                    "This canonical article appears in multiple imported folds, so no "
                    "checkpoint can be considered leakage-safe.",
                )
            return (
                "TRAINING_DATA_LEAKAGE",
                "The available local checkpoint fold was trained on this dataset "
                "article. Evaluation is blocked to prevent training-data leakage.",
            )
        return (
            "NO_MATCHING_LOCAL_MODEL",
            "Stored predictions exist, but none matches a family and fold currently "
            "available as a local checkpoint under Models.",
        )

    def assert_not_training_article(
        self,
        model: dict[str, str],
        article_identifier: str,
        fold_registry: dict[str, set[int]] | None = None,
    ) -> None:
        """Reject known training exposure or ambiguous imported fold membership.

        Applies to every family, because fold membership is a property of the article
        under the study's single publisher-disjoint split, not of the model asking.
        """

        family = model["family"]
        registry = (
            fold_registry
            if fold_registry is not None
            else self._imported_fold_registry()
        )
        assigned_folds = registry.get(article_identifier, set())
        if len(assigned_folds) > 1:
            raise AppError(
                "TRAINING_DATA_LEAKAGE",
                "The article has ambiguous membership in multiple imported folds.",
                {
                    "model_family": family,
                    "model_fold": int(model["fold_id"]),
                    "article_test_folds": sorted(assigned_folds),
                },
            )
        if assigned_folds and int(model["fold_id"]) not in assigned_folds:
            raise AppError(
                "TRAINING_DATA_LEAKAGE",
                "The selected checkpoint was trained on this dataset article.",
                {
                    "model_family": family,
                    "model_fold": int(model["fold_id"]),
                    "article_test_folds": sorted(assigned_folds),
                },
            )

    def imports(self) -> list[dict[str, object]]:
        rows = sorted(
            self.storage.rows["imports"],
            key=lambda row: row["completed_at"],
            reverse=True,
        )
        return [
            {
                **row,
                **{
                    key: int(row[key])
                    for key in (
                        "source_rows", "accepted_rows", "rejected_rows", "duplicate_rows"
                    )
                },
                "protected_columns": json.loads(row["protected_columns_json"]),
                "warnings": json.loads(row["warnings_json"]),
            }
            for row in rows
        ]

    def content(self, identifier: str) -> dict[str, str]:
        row = next(
            (
                row
                for row in self.storage.rows["local_content"]
                if row["article_id"] == identifier
            ),
            None,
        )
        if row is None:
            raise AppError("NOT_FOUND", "Saved article content was not found.")
        return row

    def export_predictions(
        self,
        *,
        q: str | None = None,
        publisher: str | None = None,
        model_id: str | None = None,
        predicted_class: int | None = None,
        origin: str | None = None,
        article_source: str | None = None,
        sort: str = "updated_desc",
    ) -> str:
        """Export one row per stored prediction run, keeping one article's runs adjacent."""

        if article_source not in {None, "dataset", "user_evaluation"}:
            raise AppError("INVALID_INPUT", "Unknown article source filter.")
        if sort not in {"url_asc", "updated_desc"}:
            raise AppError("INVALID_INPUT", "Unknown article sort.")

        source_types: dict[str, str] = {}
        for run in self.storage.rows["prediction_runs"]:
            if run["origin"] in {"bundled_import", "user_import"}:
                source_types[run["article_id"]] = "dataset"
            elif run["article_id"] not in source_types:
                source_types[run["article_id"]] = "user_evaluation"

        models = self.models_by_id
        selected: list[dict[str, str]] = []
        for run in self.storage.rows["prediction_runs"]:
            if model_id and run["model_id"] != model_id:
                continue
            if predicted_class is not None and run["predicted_class"] != str(predicted_class):
                continue
            if origin and run["origin"] != origin:
                continue
            if publisher and run["normalized_hostname"] != publisher:
                continue
            if q and q.lower() not in run["canonical_url"].lower():
                continue
            if article_source and source_types[run["article_id"]] != article_source:
                continue
            selected.append(run)

        def model_order(run: dict[str, str]) -> tuple[str, int, str]:
            model = models.get(run["model_id"], {})
            fold = str(model.get("fold_id", ""))
            return (
                str(model.get("family", "")),
                int(fold) if fold.isdigit() else 0,
                run["prediction_run_id"],
            )

        selected.sort(key=lambda run: (run["canonical_url"], *model_order(run)))
        if sort == "updated_desc":
            updated_at: dict[str, str] = {}
            for run in selected:
                article = run["article_id"]
                updated_at[article] = max(updated_at.get(article, ""), _effective_time(run))
            selected.sort(key=lambda run: updated_at[run["article_id"]], reverse=True)

        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output, fieldnames=PREDICTION_EXPORT_COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        for run in selected:
            model = models.get(run["model_id"], {})
            writer.writerow(
                {
                    "article_id": run["article_id"],
                    "url": run["canonical_url"],
                    "domain": run["normalized_hostname"],
                    "publisher_id": run["publisher_id"],
                    "prediction_origin": run["origin"],
                    "prediction_run_id": run["prediction_run_id"],
                    "model_id": run["model_id"],
                    "prediction_family": model.get("family", ""),
                    "prediction_fold_id": model.get("fold_id", ""),
                    "prediction_model_name": model.get("display_name", ""),
                    "prediction_model_provenance": (
                        self.model_provenance(model) if model else ""
                    ),
                    "prediction_official_manifest_entry_sha256": model.get(
                        "official_manifest_entry_sha256", ""
                    ),
                    "predicted_label": run["predicted_class"],
                    **{
                        f"prob_class_{index}": run[f"prob_class_{index}"]
                        for index in range(5)
                    },
                    "prediction_action": run["action"],
                    "input_source": run["input_source"],
                    "content_retention": run["content_retention"],
                    "job_id": run["job_id"],
                    "inference_started_at": run["inference_started_at"],
                    "inference_completed_at": run["inference_completed_at"],
                    "duration_ms": run["duration_ms"],
                    "device": run["device"],
                    "software_versions_json": run["software_versions_json"],
                    "recorded_at": run["recorded_at"],
                }
            )
        return output.getvalue()

    def evaluate(
        self,
        request: dict[str, object],
        job_id: str,
        *,
        on_progress: Callable[[str, int], None] | None = None,
    ) -> dict[str, object]:
        """Classify one article, reporting named phases so a caller can show progress.

        One article is the only thing a user evaluates. A publisher-level class is not
        produced here: it is a reading over the articles already classified, derived on
        demand by ``publisher_aggregation`` and never stored.

        ``on_progress`` receives a human-readable phase and a 0-100 percentage at each
        step that can take noticeable time (retrieval, checkpoint loading, inference,
        persistence), because a job that reports only its start and end leaves the
        interface frozen for several seconds.
        """

        def report(phase: str, progress: int) -> None:
            if on_progress is not None:
                on_progress(phase, progress)

        report("checking the selected model", 8)
        model_identifier = str(request["model_id"])
        model = self.models_by_id.get(model_identifier)
        if model is None:
            raise AppError("MODEL_NOT_AVAILABLE", "Selected model was not found.")
        action = str(request.get("prediction_action", "reuse"))
        retention = str(request.get("content_retention", "discard"))
        if action not in {"reuse", "recompute"} or retention not in {
            "discard", "save_local"
        }:
            raise AppError("INVALID_INPUT", "Unsupported evaluation option.")
        input_value = request.get("input")
        if not isinstance(input_value, dict):
            raise AppError("INVALID_INPUT", "Evaluation input is required.")
        if input_value.get("type") != "article":
            raise AppError("INVALID_INPUT", "Unknown evaluation input type.")

        return self._evaluate_article(
            input_value,
            model,
            model_identifier,
            self._imported_fold_registry(),
            job_id=job_id,
            action=action,
            retention=retention,
            report=report,
        )

    def _evaluate_article(
        self,
        input_value: dict[str, object],
        model: dict[str, str],
        model_identifier: str,
        fold_registry: dict[str, set[int]],
        *,
        job_id: str,
        action: str,
        retention: str,
        report: Callable[[str, int], None],
    ) -> dict[str, object]:
        """Reuse the stored prediction for one article, or create a new one.

        Reuse is the default because an immutable run already answers the question and
        costs no retrieval; ``recompute`` is the explicit way to ask for a fresh run,
        which is then stored alongside the earlier one rather than replacing it.
        """

        canonical = normalize_url(str(input_value.get("url", "")))
        self.assert_not_training_article(model, article_id(canonical), fold_registry)
        run = (
            self._latest_run(article_id(canonical), model_identifier)
            if action == "reuse"
            else None
        )
        if run is None:
            run = self._create_inference_run(
                model,
                canonical,
                job_id=job_id,
                action=action,
                retention=retention,
                report=report,
            )
            reused = False
        else:
            report("reusing the stored prediction", 60)
            if retention == "save_local":
                # Saving the body still requires retrieval, and the page may have moved
                # since the stored run: refuse rather than attach a different article.
                report("retrieving the article page", 70)
                retrieved = fetch_article(canonical, offline=self.offline)
                if article_id(retrieved.canonical_url) != run["article_id"]:
                    raise AppError(
                        "INVALID_URL",
                        "Retrieved canonical URL differs from the stored prediction.",
                    )
                self._save_content(retrieved)
            reused = True
        report("saving the result", 92)
        return {
            "article_id": run["article_id"],
            "canonical_url": run["canonical_url"],
            "prediction_run_id": run["prediction_run_id"],
            "predicted_class": int(run["predicted_class"]),
            "probabilities": [
                float(run[f"prob_class_{index}"]) for index in range(5)
            ],
            "model_id": model_identifier,
            "family": model["family"],
            "fold_id": int(model["fold_id"]),
            "model_display_name": model["display_name"],
            "model_provenance": self.model_provenance(model),
            "origin": run["origin"],
            "reused": reused,
        }

    def _latest_run(
        self, article_identifier: str, model_identifier: str
    ) -> dict[str, str] | None:
        matching = [
            row
            for row in self.storage.rows["prediction_runs"]
            if row["article_id"] == article_identifier
            and row["model_id"] == model_identifier
        ]
        return newest_runs(matching)[0] if matching else None

    def _save_content(self, article: RetrievedArticle) -> None:
        self.storage.upsert(
            "local_content",
            "article_id",
            {
                "article_id": article_id(article.canonical_url),
                "canonical_url": article.canonical_url,
                "title": article.title,
                "text": article.text,
                "content_saved_at": utc_now(),
            },
        )

    def _create_inference_run(
        self,
        model: dict[str, str],
        canonical_url: str,
        *,
        job_id: str,
        action: str,
        retention: str,
        report: Callable[[str, int], None] | None = None,
    ) -> dict[str, str]:
        """Retrieve, classify and persist one new prediction.

        The leakage guard is checked twice on purpose: once against the URL the user
        supplied and again against the canonical URL that retrieval actually resolved
        to, because a redirect can land on a dataset article the checkpoint was trained
        on. The run is written to the ledger first and mirrored into the prediction
        dataset afterwards, so the authoritative record exists even if the mirror fails.
        """

        def progress(phase: str, value: int) -> None:
            if report is not None:
                report(phase, value)

        if (
            model["artifact_kind"] == "historical_virtual"
            or model["artifact_available"] != "true"
            or model["runnable"] != "true"
        ):
            raise AppError(
                "MODEL_NOT_RUNNABLE",
                "The selected model cannot create a new prediction.",
            )
        started = utc_now()
        started_clock = time.monotonic()
        progress("retrieving and extracting the article page", 20)
        retrieved = fetch_article(canonical_url, offline=self.offline)
        identifier = article_id(retrieved.canonical_url)
        self.assert_not_training_article(model, identifier)
        prediction = self.inference.predict(
            model,
            retrieved.text,
            on_progress=lambda phase: progress(phase, INFERENCE_PHASES.get(phase, 60)),
        )
        progress("saving the prediction", 90)
        completed = utc_now()
        run: dict[str, object] = {
            "prediction_run_id": str(uuid.uuid4()),
            "article_id": identifier,
            "canonical_url": retrieved.canonical_url,
            "publisher_id": publisher_id(
                normalized_hostname(retrieved.canonical_url)
            ),
            "normalized_hostname": normalized_hostname(retrieved.canonical_url),
            "model_id": model["model_id"],
            "predicted_class": prediction.predicted_class,
            **{
                f"prob_class_{index}": prediction.probabilities[index]
                for index in range(5)
            },
            "origin": "local_inference",
            "action": "recompute" if action == "recompute" else "missing_run_inference",
            "input_source": canonical_url,
            "content_retention": retention,
            "source_import_id": "",
            "job_id": job_id,
            "inference_started_at": started,
            "inference_completed_at": completed,
            "duration_ms": round((time.monotonic() - started_clock) * 1000),
            "device": prediction.device,
            "software_versions_json": json_field(prediction.software_versions),
            "recorded_at": completed,
        }
        self.storage.append("prediction_runs", run)
        sync_user_predictions(
            self.prediction_dataset_dir,
            self.storage.rows["prediction_runs"],
            self.models_by_id,
        )
        if retention == "save_local":
            self._save_content(retrieved)
        return {key: str(value) for key, value in run.items()}
