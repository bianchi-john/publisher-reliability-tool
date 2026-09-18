"""Serving the tool to the public instead of to one local person.

The application was written for a single user on a loopback address, which makes two
assumptions that stop holding once it is published: that whoever reaches it is
entitled to run administrative operations, and that the Host header can only ever be
the loopback address. Setting a public host withdraws the first assumption and widens
the second by exactly one name. These tests pin that boundary.
"""

import tempfile
import unittest
from pathlib import Path

from publisher_reliability.api import create_app
from publisher_reliability.config import Config
from publisher_reliability.errors import AppError
from publisher_reliability.jobs import JobManager

PUBLIC_HOST = "prt.example.org"

# Everything that mutates shared state or accepts an upload. A visitor running any of
# these would be acting on every other visitor's workspace.
ADMINISTRATIVE = {
    ("POST", "/api/v1/models/scan"),
    ("POST", "/api/v1/models/upload"),
    ("POST", "/api/v1/imports/upload"),
}


class PublicInstanceTest(unittest.TestCase):
    def build(self, temporary: str, public_host: str = "") -> object:
        root = Path(temporary)
        config = Config(
            data_dir=root / "data",
            models_dirs=(),
            seed_dataset=root / "seed",
            offline=True,
            public_host=public_host,
        )
        config.validate()
        return create_app(config)

    def routes(self, app: object) -> set[tuple[str, str]]:
        return {
            (method, route.path)
            for route in app.routes
            for method in getattr(route, "methods", set())
        }

    def close(self, app: object) -> None:
        app.state.jobs.stop()
        app.state.storage.close()

    def test_a_public_instance_does_not_serve_administrative_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app = self.build(temporary, PUBLIC_HOST)
            try:
                served = self.routes(app)
                # Withheld entirely rather than answered with a refusal, so the
                # generated OpenAPI describes exactly what this deployment can do.
                self.assertEqual(ADMINISTRATIVE & served, set())
                # The demonstration itself stays: classifying an article is the point.
                self.assertIn(("POST", "/api/v1/evaluation-jobs"), served)
                self.assertIn(("GET", "/api/v1/publishers"), served)
                self.assertIn(("GET", "/api/v1/jobs"), served)
            finally:
                self.close(app)

    def test_a_local_instance_still_serves_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app = self.build(temporary)
            try:
                self.assertEqual(ADMINISTRATIVE & self.routes(app), ADMINISTRATIVE)
                self.assertFalse(app.state.config.is_public)
            finally:
                self.close(app)

    def test_status_reports_which_kind_of_instance_this_is(self) -> None:
        # The interface hides the local-only controls from this flag, so a visitor is
        # never shown a button whose route the deployment does not serve.
        for public_host, expected in ((PUBLIC_HOST, True), ("", False)):
            with self.subTest(public_host=public_host):
                with tempfile.TemporaryDirectory() as temporary:
                    app = self.build(temporary, public_host)
                    try:
                        self.assertEqual(app.state.config.is_public, expected)
                    finally:
                        self.close(app)

    def test_public_host_widens_the_host_check_by_exactly_one_name(self) -> None:
        config = Config(public_host=PUBLIC_HOST, port=8000)
        config.validate()
        self.assertTrue(config.is_public)
        # A published instance sits behind a proxy forwarding its own hostname, so
        # that one name is accepted; anything else still is not, because the check
        # exists to defeat DNS rebinding rather than to be switched off.
        self.assertEqual(config.public_host, PUBLIC_HOST)

    def test_a_malformed_public_host_is_refused_at_startup(self) -> None:
        for bad in ("http://prt.example.org", "prt.example.org/path", "a b"):
            with self.subTest(value=bad):
                with self.assertRaises(AppError) as raised:
                    Config(public_host=bad).validate()
                self.assertEqual(raised.exception.code, "INVALID_INPUT")


class NothingDeletesTest(unittest.TestCase):
    """FR-025: the capability is absent from the code, not hidden behind a flag."""

    def test_no_deployment_serves_any_delete_method(self) -> None:
        for public_host in (PUBLIC_HOST, ""):
            with self.subTest(public_host=public_host or "local"):
                with tempfile.TemporaryDirectory() as temporary:
                    app = PublicInstanceTest.build(self, temporary, public_host)
                    try:
                        deleting = {
                            path
                            for method, path in PublicInstanceTest.routes(self, app)
                            if method == "DELETE"
                        }
                        self.assertEqual(deleting, set())
                    finally:
                        PublicInstanceTest.close(self, app)

    def test_the_service_layer_has_no_deletion_routine(self) -> None:
        # Route tables can be edited back; a missing routine is harder to restore by
        # accident, which is the point of removing the capability rather than the
        # button. These names are the ones that were withdrawn.
        from publisher_reliability import jobs as jobs_module
        from publisher_reliability import prediction_dataset, services

        self.assertFalse(hasattr(services.ResearchService, "clear_user_data"))
        self.assertFalse(hasattr(services.ResearchService, "delete_content"))
        self.assertFalse(hasattr(jobs_module.JobManager, "clear"))
        self.assertFalse(hasattr(prediction_dataset, "clear_user_predictions"))

    def test_a_published_instance_will_not_retain_article_text(self) -> None:
        # Nothing can be deleted, so nothing may accumulate: consent to keep a body
        # is overridden rather than honoured and then stranded on the server.
        import json

        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temporary:
            app = PublicInstanceTest.build(self, temporary, PUBLIC_HOST)
            try:
                client = TestClient(app, base_url=f"http://{PUBLIC_HOST}")
                client.post(
                    "/api/v1/evaluation-jobs",
                    json={
                        "input": {"type": "article", "url": "https://example.org/a"},
                        "model_id": "irrelevant",
                        "prediction_action": "reuse",
                        "content_retention": "save_local",
                    },
                )
                recorded = json.loads(app.state.storage.rows["jobs"][0]["request_json"])
                self.assertEqual(recorded["content_retention"], "discard")
            finally:
                PublicInstanceTest.close(self, app)


class QueueBoundTest(unittest.TestCase):
    """A public instance refuses work rather than promising an unbounded wait."""

    def test_queued_jobs_are_capped_when_a_bound_is_set(self) -> None:
        from publisher_reliability.services import ResearchService
        from publisher_reliability.storage import Storage

        with tempfile.TemporaryDirectory() as temporary:
            storage = Storage(Path(temporary) / "data")
            try:
                service = ResearchService(storage, offline=True)
                jobs = JobManager(storage, service, max_queued_jobs=2)
                jobs.stop()  # Nothing drains the queue, so submissions accumulate.
                jobs._stop.clear()
                for _ in range(2):
                    jobs.submit("evaluation", {"input": {"type": "article"}})
                with self.assertRaises(AppError) as refused:
                    jobs.submit("evaluation", {"input": {"type": "article"}})
                self.assertEqual(refused.exception.code, "TOO_MANY_REQUESTS")
            finally:
                storage.close()

    def test_a_local_instance_has_no_bound(self) -> None:
        from publisher_reliability.services import ResearchService
        from publisher_reliability.storage import Storage

        with tempfile.TemporaryDirectory() as temporary:
            storage = Storage(Path(temporary) / "data")
            try:
                service = ResearchService(storage, offline=True)
                jobs = JobManager(storage, service)
                jobs.stop()
                jobs._stop.clear()
                for _ in range(5):
                    jobs.submit("evaluation", {"input": {"type": "article"}})
                self.assertEqual(len(storage.rows["jobs"]), 5)
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
