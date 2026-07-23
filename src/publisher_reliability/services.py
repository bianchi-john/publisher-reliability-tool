"""Shared query and evaluation services used by the API and CLI."""

from __future__ import annotations

import csv
import io
import json
import uuid
from collections import Counter, defaultdict
from typing import Iterable

from .aggregation import WARNING, aggregate
from .errors import AppError
from .identity import article_id, normalize_url, normalized_hostname, publisher_id
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
    def __init__(self, storage: Storage, *, offline: bool = False):
        self.storage = storage
        self.offline = offline

    @property
    def models_by_id(self) -> dict[str, dict[str, str]]:
        return {row["model_id"]: row for row in self.storage.rows["models"]}

    @property
    def runs_by_id(self) -> dict[str, dict[str, str]]:
        return {
            row["prediction_run_id"]: row
            for row in self.storage.rows["prediction_runs"]
        }

    def article_summaries(
        self,
        *,
        q: str | None = None,
        publisher: str | None = None,
        model_id: str | None = None,
        predicted_class: int | None = None,
        origin: str | None = None,
        sort: str = "updated_desc",
    ) -> list[dict[str, object]]:
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
        )[:20]
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
                "support_level": (
                    "core" if row["family"] in {"bert", "roberta"} else "optional"
                ),
            }
            for row in self.storage.rows["models"]
            if (not family or row["family"] == family)
            and (not status or row["status"] == status)
        ]
        rows.sort(key=lambda row: (str(row["family"]), int(row["fold_id"])))
        return rows

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
            "latest_model_id", "latest_predicted_class", "content_saved",
            "first_seen_at", "updated_at",
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
        if action == "recompute":
            raise AppError(
                "MODEL_NOT_RUNNABLE",
                "The selected historical model cannot recompute predictions.",
            )
        if retention == "save_local":
            raise AppError(
                "NETWORK_REQUIRED" if self.offline else "MODEL_NOT_RUNNABLE",
                "Content retrieval is unavailable until a runnable model is installed.",
            )

        input_value = request.get("input")
        if not isinstance(input_value, dict):
            raise AppError("INVALID_INPUT", "Evaluation input is required.")
        input_type = input_value.get("type")
        if input_type == "article":
            canonical = normalize_url(str(input_value.get("url", "")))
            run = self._latest_run(article_id(canonical), model_identifier)
            if run is None:
                raise AppError(
                    "MODEL_NOT_RUNNABLE",
                    "No stored run exists and the selected model cannot infer.",
                )
            return {
                "article_id": run["article_id"],
                "prediction_run_id": run["prediction_run_id"],
                "reused": True,
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
                run = self._latest_run(article_id(canonical), model_identifier)
                if run is None:
                    raise AppError(
                        "MODEL_NOT_RUNNABLE",
                        "A listed article has no stored run for the selected model.",
                    )
                selected.append(run)
            requested = len(selected)
            partial = False
            input_mode = "article_list"
            hostname = hostnames.pop()
        elif input_type == "publisher":
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

