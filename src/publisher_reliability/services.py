"""Shared query and evaluation services used by the API and CLI."""

from __future__ import annotations

import csv
import io
import json
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from .aggregation import WARNING, aggregate
from .errors import AppError
from .identity import article_id, normalize_url, normalized_hostname, publisher_id
from .inference import InferenceEngine, RetrievedArticle, fetch_article
from .prediction_dataset import sync_user_predictions
from .storage import Storage, json_field, utc_now


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

    def _imported_fold_registry(self) -> dict[tuple[str, str], set[int]]:
        registry: dict[tuple[str, str], set[int]] = defaultdict(set)
        models = self.models_by_id
        for run in self.storage.rows["prediction_runs"]:
            if run["origin"] not in {"bundled_import", "user_import"}:
                continue
            model = models.get(run["model_id"])
            if model is not None:
                registry[(run["article_id"], model["family"])].add(
                    int(model["fold_id"])
                )
        return registry

    @staticmethod
    def _fold_is_safe(
        model: dict[str, str],
        article_identifier: str,
        registry: dict[tuple[str, str], set[int]],
    ) -> bool:
        assigned = registry.get((article_identifier, model["family"]), set())
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
        runs: dict[str, list[dict[str, str]]] = defaultdict(list)
        for run in self.storage.rows["prediction_runs"]:
            if q and q.lower() not in run["normalized_hostname"].lower():
                continue
            if model_id and run["model_id"] != model_id:
                continue
            runs[run["publisher_id"]].append(run)
        evaluations: dict[str, list[dict[str, str]]] = defaultdict(list)
        for evaluation in self.storage.rows["evaluations"]:
            evaluations[evaluation["publisher_id"]].append(evaluation)

        result = []
        for pub_id, rows in runs.items():
            latest_evaluation = max(
                (row["created_at"] for row in evaluations.get(pub_id, [])), default=""
            )
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
                    "evaluation_count": len(evaluations.get(pub_id, [])),
                    "latest_evaluation_at": latest_evaluation or None,
                }
            )
        result.sort(key=lambda row: str(row["normalized_hostname"]))
        result.sort(key=lambda row: str(row["latest_evaluation_at"] or ""), reverse=True)
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
        evaluations = [
            self.evaluation_summary(row)
            for row in sorted(
                (
                    row
                    for row in self.storage.rows["evaluations"]
                    if row["publisher_id"] == identifier
                ),
                key=lambda row: row["created_at"],
                reverse=True,
            )[:20]
        ]
        return {
            **summary,
            "counts_by_model_class": {
                model: {str(index): counts.get(index, 0) for index in range(5)}
                for model, counts in class_counts.items()
            },
            "articles": articles,
            "evaluations": evaluations,
            "warning": WARNING,
        }

    @staticmethod
    def evaluation_summary(row: dict[str, str]) -> dict[str, object]:
        return {
            **row,
            "requested_count": int(row["requested_count"]),
            "used_count": int(row["used_count"]),
            "partial": row["partial"] == "true",
            "result_class": int(row["result_class"]),
            "ordinal_mean": float(row["ordinal_mean"]) if row["ordinal_mean"] else None,
        }

    def evaluations(self, **filters: str | None) -> list[dict[str, object]]:
        rows = [
            row
            for row in self.storage.rows["evaluations"]
            if not any(value and row[key] != value for key, value in filters.items())
        ]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return [self.evaluation_summary(row) for row in rows]

    def evaluation(self, identifier: str) -> dict[str, object]:
        row = next(
            (
                row
                for row in self.storage.rows["evaluations"]
                if row["evaluation_id"] == identifier
            ),
            None,
        )
        if row is None:
            raise AppError("NOT_FOUND", "Evaluation was not found.")
        run_ids = json.loads(row["prediction_run_ids_json"])
        runs = [self.run_summary(self.runs_by_id[run_id]) for run_id in run_ids]
        counts = Counter(int(run["predicted_class"]) for run in runs)
        probabilities = [
            float(row[f"prob_class_{index}"])
            if row[f"prob_class_{index}"]
            else None
            for index in range(5)
        ]
        return {
            **self.evaluation_summary(row),
            "article_ids": json.loads(row["article_ids_json"]),
            "runs": runs,
            "class_counts": {str(index): counts.get(index, 0) for index in range(5)},
            "mean_probabilities": (
                probabilities if all(value is not None for value in probabilities) else None
            ),
            "warnings": json.loads(row["warnings_json"]),
        }

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
                    else "custom"
                    if row["family"].startswith("custom_")
                    else "optional"
                ),
            }
            for row in self.storage.rows["models"]
            if (not family or row["family"] == family)
            and (not status or row["status"] == status)
        ]
        rows.sort(key=lambda row: (str(row["family"]), int(row["fold_id"])))
        return rows

    def available_models(
        self,
        *,
        input_type: str,
        url: str,
        requested_count: int = 2,
        allow_partial: bool = False,
    ) -> dict[str, object]:
        """Explain availability and return locally present, leakage-safe stored models."""

        canonical = normalize_url(url)
        if input_type == "article":
            matching = [
                row
                for row in self.storage.rows["prediction_runs"]
                if row["article_id"] == article_id(canonical)
            ]
            required = 1
        elif input_type == "publisher":
            hostname = normalized_hostname(canonical)
            matching = [
                row
                for row in self.storage.rows["prediction_runs"]
                if row["normalized_hostname"] == hostname
            ]
            required = 2 if allow_partial else max(2, requested_count)
        else:
            raise AppError("INVALID_INPUT", "Unknown evaluation input type.")

        local_models = [
            model
            for model in self.storage.rows["models"]
            if model["artifact_kind"] != "historical_virtual"
            and model["artifact_available"] == "true"
        ]
        local_by_family_fold: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
        for model in local_models:
            local_by_family_fold[(model["family"], int(model["fold_id"]))].append(model)

        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for run in matching:
            grouped[run["model_id"]].append(run)
        models = self.models_by_id
        fold_registry = self._imported_fold_registry()
        result: list[dict[str, object]] = []
        article_identifier = article_id(canonical) if input_type == "article" else ""
        had_matching_local_identity = False
        for model_identifier, runs in grouped.items():
            model = models.get(model_identifier)
            if model is None:
                continue
            family_fold = (model["family"], int(model["fold_id"]))
            local_matches = local_by_family_fold.get(family_fold, [])
            if not local_matches:
                continue
            had_matching_local_identity = True
            safe_runs = [
                run
                for run in runs
                if self._fold_is_safe(model, run["article_id"], fold_registry)
            ]
            if not safe_runs:
                continue
            article_count = len({run["article_id"] for run in safe_runs})
            probability_count = sum(bool(run["prob_class_0"]) for run in safe_runs)
            local_model = sorted(
                local_matches,
                key=lambda row: (row["status"] != "compatible", row["model_id"]),
            )[0]
            result.append(
                {
                    "model_id": model_identifier,
                    "local_model_id": local_model["model_id"],
                    "family": model["family"],
                    "fold_id": int(model["fold_id"]),
                    "display_name": model["display_name"],
                    "local_status": local_model["status"],
                    "local_runnable": local_model["runnable"] == "true",
                    "article_count": article_count,
                    "run_count": len(safe_runs),
                    "probability_count": probability_count,
                    "eligible": article_count >= required,
                    "mode": "stored_prediction",
                }
            )

        blocked = []
        if input_type == "article":
            existing_model_ids = {str(row["model_id"]) for row in result}
            for local_model in local_models:
                family = local_model["family"]
                fold_id = int(local_model["fold_id"])
                assigned_folds = fold_registry.get((article_identifier, family), set())
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
                if (
                    local_model["model_id"] in existing_model_ids
                    or (assigned_folds and fold_id in assigned_folds)
                    or local_model["runnable"] != "true"
                ):
                    continue
                result.append(
                    {
                        "model_id": local_model["model_id"],
                        "local_model_id": local_model["model_id"],
                        "family": family,
                        "fold_id": fold_id,
                        "display_name": local_model["display_name"],
                        "local_status": local_model["status"],
                        "local_runnable": True,
                        "article_count": 0,
                        "run_count": 0,
                        "probability_count": 0,
                        "eligible": True,
                        "mode": "new_inference",
                    }
                )
        result.sort(
            key=lambda row: (
                not bool(row["eligible"]),
                str(row["mode"]),
                str(row["family"]),
                int(row["fold_id"]),
            )
        )

        eligible_count = sum(bool(row["eligible"]) for row in result)
        if not local_models:
            code = "NO_LOCAL_CHECKPOINTS"
            message = (
                "No validated local checkpoint is available. Add a supported model "
                "under Models and scan the configured directories."
            )
        elif result and eligible_count:
            code = "AVAILABLE"
            if input_type == "article" and any(
                row["eligible"] and row["mode"] == "new_inference" for row in result
            ):
                message = (
                    f"{eligible_count} model option(s) are available. Options marked "
                    "'new inference' will retrieve and classify this page locally."
                )
            else:
                message = (
                    f"{eligible_count} local checkpoint(s) have enough leakage-safe "
                    "stored predictions for this request."
                )
        elif result or (input_type == "publisher" and had_matching_local_identity):
            code = "INSUFFICIENT_SAFE_ARTICLES"
            message = (
                "Matching local checkpoints exist, but the publisher has fewer safe "
                "held-out predictions than the requested article count."
            )
        elif input_type == "article" and not matching:
            code = "NEW_ARTICLE_REQUIRES_INFERENCE"
            message = (
                "This URL is not present in the imported prediction dataset. It requires "
                "a new inference run, but no runnable local model is available."
            )
        elif blocked:
            code = "TRAINING_DATA_LEAKAGE"
            if any("multiple imported folds" in row["reason"] for row in blocked):
                message = (
                    "This canonical article appears in multiple imported folds, so no "
                    "checkpoint can be considered leakage-safe."
                )
            else:
                message = (
                    "The available local checkpoint fold was trained on this dataset "
                    "article. Evaluation is blocked to prevent training-data leakage."
                )
        else:
            code = "NO_MATCHING_LOCAL_MODEL"
            message = (
                "Stored predictions exist, but none matches a family and fold currently "
                "available as a local checkpoint under Models."
            )
        return {
            "items": result,
            "availability": {
                "code": code,
                "message": message,
                "input_known": bool(matching),
                "local_checkpoint_count": len(local_models),
                "eligible_model_count": eligible_count,
                "blocked_training_models": blocked,
            },
        }

    def assert_not_training_article(
        self,
        model: dict[str, str],
        article_identifier: str,
        fold_registry: dict[tuple[str, str], set[int]] | None = None,
    ) -> None:
        """Reject known training exposure or ambiguous imported fold membership."""

        family = model["family"]
        registry = (
            fold_registry
            if fold_registry is not None
            else self._imported_fold_registry()
        )
        assigned_folds = registry.get((article_identifier, family), set())
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

    def delete_content(self, identifier: str, confirmation: str) -> dict[str, object]:
        if any(
            row["job_type"] == "evaluation" and row["status"] == "running"
            for row in self.storage.rows["jobs"]
        ):
            raise AppError(
                "INVALID_INPUT", "Content cannot be deleted during an evaluation."
            )
        row = self.content(identifier)
        if row["canonical_url"] != confirmation:
            raise AppError("INVALID_INPUT", "Canonical URL confirmation does not match.")
        self.storage.delete("local_content", "article_id", identifier)
        return {
            "deleted": True,
            "backup_notice": "User backups and external copies are unchanged.",
        }

    def export_articles(self, **filters: object) -> str:
        columns = [
            "article_id", "canonical_url", "publisher_id", "normalized_hostname",
            "model_count", "run_count", "latest_prediction_run_id",
            "latest_model_id", "latest_predicted_class", "source_type",
            "dataset_run_count", "local_run_count", "has_user_evaluation",
            "content_saved", "first_seen_at", "updated_at",
        ]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.article_summaries(**filters))
        return output.getvalue()

    def evaluate(self, request: dict[str, object], job_id: str) -> dict[str, object]:
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
        input_type = input_value.get("type")
        fold_registry = self._imported_fold_registry()
        if input_type == "article":
            canonical = normalize_url(str(input_value.get("url", "")))
            self.assert_not_training_article(
                model, article_id(canonical), fold_registry
            )
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
                )
                reused = False
            else:
                if retention == "save_local":
                    retrieved = fetch_article(canonical, offline=self.offline)
                    if article_id(retrieved.canonical_url) != run["article_id"]:
                        raise AppError(
                            "INVALID_URL",
                            "Retrieved canonical URL differs from the stored prediction.",
                        )
                    self._save_content(retrieved)
                reused = True
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
                "origin": run["origin"],
                "reused": reused,
            }

        method = str(request.get("aggregation_method", ""))
        if method not in {"majority_vote", "ordinal_mean", "mean_probabilities"}:
            raise AppError("INVALID_INPUT", "Aggregation method is required.")

        if input_type == "article_list":
            raw_urls = input_value.get("urls")
            if not isinstance(raw_urls, list) or not 2 <= len(raw_urls) <= 50:
                raise AppError("INVALID_INPUT", "Article list must contain 2 to 50 URLs.")
            canonical_urls = [normalize_url(str(url)) for url in raw_urls]
            if len(set(canonical_urls)) != len(canonical_urls):
                raise AppError("INVALID_INPUT", "Article URLs must be distinct.")
            hostnames = {normalized_hostname(url) for url in canonical_urls}
            if len(hostnames) != 1:
                raise AppError("INVALID_INPUT", "All articles must share one publisher.")
            selected = []
            for canonical in canonical_urls:
                self.assert_not_training_article(
                    model, article_id(canonical), fold_registry
                )
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
                    )
                selected.append(run)
            requested = len(selected)
            partial = False
            input_mode = "article_list"
            hostname = hostnames.pop()
        elif input_type == "publisher":
            if action == "recompute":
                raise AppError(
                    "INVALID_INPUT",
                    "Publisher recompute requires an explicit article list.",
                )
            canonical = normalize_url(str(input_value.get("url", "")))
            hostname = normalized_hostname(canonical)
            try:
                requested = int(input_value.get("requested_article_count", 0))
            except (TypeError, ValueError) as exc:
                raise AppError("INVALID_INPUT", "Requested count must be an integer.") from exc
            if not 2 <= requested <= 50:
                raise AppError("INVALID_INPUT", "Requested count must be between 2 and 50.")
            allow_partial = bool(input_value.get("allow_partial", False))
            candidates: dict[str, dict[str, str]] = {}
            for run in self.storage.rows["prediction_runs"]:
                if (
                    run["normalized_hostname"] == hostname
                    and run["model_id"] == model_identifier
                ):
                    if not self._fold_is_safe(
                        model, run["article_id"], fold_registry
                    ):
                        continue
                    current = candidates.get(run["article_id"])
                    if current is None or newest_runs([current, run])[0] is run:
                        candidates[run["article_id"]] = run
            selected = newest_runs(candidates.values())[:requested]
            if len(selected) < 2 or (len(selected) < requested and not allow_partial):
                raise AppError(
                    "INSUFFICIENT_ARTICLES",
                    "The publisher does not have enough compatible stored predictions.",
                )
            partial = len(selected) < requested
            input_mode = "publisher"
        else:
            raise AppError("INVALID_INPUT", "Unknown evaluation input type.")

        calculation = aggregate(selected, method)
        evaluation_id = str(uuid.uuid4())
        probabilities = calculation["probabilities"] or ("", "", "", "", "")
        row: dict[str, object] = {
            "evaluation_id": evaluation_id,
            "publisher_id": publisher_id(hostname),
            "normalized_hostname": hostname,
            "model_id": model_identifier,
            "method": method,
            "method_version": "1",
            "input_mode": input_mode,
            "requested_count": requested,
            "used_count": len(selected),
            "partial": partial,
            "result_class": calculation["result_class"],
            "ordinal_mean": calculation["ordinal_mean"],
            **{
                f"prob_class_{index}": probabilities[index] for index in range(5)
            },
            "article_ids_json": json_field([run["article_id"] for run in selected]),
            "prediction_run_ids_json": json_field(
                [run["prediction_run_id"] for run in selected]
            ),
            "job_id": job_id,
            "created_at": utc_now(),
            "warnings_json": json_field([WARNING]),
        }
        self.storage.append("evaluations", row)
        return {
            "evaluation_id": evaluation_id,
            "publisher_id": row["publisher_id"],
            "result_class": calculation["result_class"],
            "used_count": len(selected),
            "partial": partial,
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
    ) -> dict[str, str]:
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
        retrieved = fetch_article(canonical_url, offline=self.offline)
        identifier = article_id(retrieved.canonical_url)
        self.assert_not_training_article(model, identifier)
        prediction = self.inference.predict(model, retrieved.text)
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
