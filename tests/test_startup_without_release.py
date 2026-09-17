"""Starting a workspace that has no bundled release, before and after a local run.

`--seed-dataset` may legitimately point somewhere no release was ever installed; the
product specification calls a missing seed a valid empty mode. That directory is also
where the private prediction mirror is written, and the mirror writer creates it when
it is absent. So the first local evaluation brings the directory into existence with
nothing in it but `user-predictions.csv`.

If the presence of a release were decided by the directory rather than by its
manifest, that first evaluation would make the application refuse to start ever
after, and the only way out would be deleting the very history the mirror exists to
protect. These tests pin the manifest as the deciding artifact, while keeping a real
release that is damaged a loud failure.
"""

import tempfile
import unittest
from pathlib import Path

from publisher_reliability.api import create_app
from publisher_reliability.config import Config
from publisher_reliability.errors import AppError
from publisher_reliability.identity import (
    article_id,
    normalized_hostname,
    publisher_id,
)
from publisher_reliability.prediction_dataset import (
    USER_PREDICTIONS_FILENAME,
    sync_user_predictions,
)
from publisher_reliability.storage import HEADERS, Storage, json_field, utc_now

URL = "https://outlet.example/a"


class StartupWithoutBundledReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.seed = self.root / "seed"
        self.data = self.root / "data"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _start(self) -> None:
        app = create_app(
            Config(
                port=8000,
                data_dir=self.data,
                models_dirs=(self.root / "models",),
                seed_dataset=self.seed,
                offline=True,
            )
        )
        app.state.jobs.stop()
        app.state.storage.close()

    def _record_local_run(self) -> None:
        """Do what one completed evaluation does: append a run, then mirror it."""

        with Storage(self.data) as storage:
            model = {column: "" for column in HEADERS["models"]}
            model.update(
                model_id="model-1",
                family="bert",
                fold_id=2,
                display_name="BERT fold 2 (local checkpoint)",
                artifact_kind="pytorch_state_dict",
                class_order_json="[0,1,2,3,4]",
                runtime_scientific_json="{}",
                status="compatible",
                artifact_available=True,
                runnable=True,
                registered_at=utc_now(),
                last_validated_at=utc_now(),
            )
            storage.upsert("models", "model_id", model)
            run = {column: "" for column in HEADERS["prediction_runs"]}
            run.update(
                prediction_run_id="run-1",
                article_id=article_id(URL),
                canonical_url=URL,
                publisher_id=publisher_id(normalized_hostname(URL)),
                normalized_hostname=normalized_hostname(URL),
                model_id="model-1",
                predicted_class=3,
                origin="local_inference",
                action="missing_run_inference",
                input_source=URL,
                content_retention="discard",
                job_id="job-1",
                inference_started_at=utc_now(),
                inference_completed_at=utc_now(),
                duration_ms=10,
                device="cpu",
                software_versions_json=json_field({}),
                recorded_at=utc_now(),
            )
            for index in range(5):
                run[f"prob_class_{index}"] = "0.6" if index == 3 else "0.1"
            storage.append("prediction_runs", run)
            sync_user_predictions(
                self.seed,
                storage.rows["prediction_runs"],
                {row["model_id"]: row for row in storage.rows["models"]},
            )

    def test_starts_with_no_seed_directory_at_all(self) -> None:
        self.assertFalse(self.seed.exists())
        self._start()

    def test_still_starts_after_the_mirror_creates_the_seed_directory(self) -> None:
        self._start()
        self._record_local_run()

        # The evaluation brought the directory into existence, holding only the mirror.
        self.assertTrue(self.seed.is_dir())
        self.assertEqual(
            sorted(path.name for path in self.seed.iterdir()),
            [USER_PREDICTIONS_FILENAME],
        )

        self._start()

    def test_the_mirrored_run_survives_that_restart(self) -> None:
        self._start()
        self._record_local_run()
        self.data.rename(self.root / "thrown-away")

        self._start()

        with Storage(self.data) as storage:
            runs = storage.rows["prediction_runs"]
            self.assertEqual([row["prediction_run_id"] for row in runs], ["run-1"])
            self.assertEqual(runs[0]["origin"], "local_inference")

    def test_a_release_whose_manifest_is_damaged_still_fails_loudly(self) -> None:
        # Fail-closed has to survive the fix: a manifest that is present but unusable
        # means a real release is broken, which is not something to start around.
        self.seed.mkdir()
        (self.seed / "manifest.json").write_text("{not json", encoding="utf-8")

        with self.assertRaises(AppError) as raised:
            self._start()
        self.assertEqual(raised.exception.code, "IMPORT_INVALID")


if __name__ == "__main__":
    unittest.main()
