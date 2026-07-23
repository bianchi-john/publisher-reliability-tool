import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from publisher_reliability.api import create_app
from publisher_reliability.config import Config


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.config = Config(
            port=8765,
            data_dir=Path(self.temporary.name) / "data",
            models_dirs=(),
            seed_dataset=Path(self.temporary.name) / "missing-seed",
            offline=True,
        )
        self.app = create_app(self.config)
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://127.0.0.1:8765",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.state.jobs.stop()
        self.app.state.storage.close()
        self.temporary.cleanup()

    async def test_health_openapi_host_and_error_envelope(self) -> None:
        self.assertEqual(
            (await self.client.get("/health/live")).json(), {"status": "alive"}
        )
        self.assertEqual(
            (await self.client.get("/health/ready")).json(), {"status": "ready"}
        )

        openapi = await self.client.get("/api/openapi.json")
        self.assertEqual(openapi.status_code, 200)
        self.assertIn("/api/v1/articles", openapi.json()["paths"])
        self.assertIn("/api/v1/evaluation-jobs", openapi.json()["paths"])

        missing = await self.client.get(
            "/api/v1/articles/00000000-0000-0000-0000-000000000000"
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"]["code"], "NOT_FOUND")
        self.assertIn("request_id", missing.json()["error"])

        invalid_host = await self.client.get(
            "/health/live", headers={"Host": "127.0.0.1.evil:8765"}
        )
        self.assertEqual(invalid_host.status_code, 421)
        self.assertEqual(invalid_host.json()["error"]["code"], "INVALID_HOST")

    async def test_pagination_validation_uses_stable_error(self) -> None:
        response = await self.client.get("/api/v1/articles?limit=10")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()

