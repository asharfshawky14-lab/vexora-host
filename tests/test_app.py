
import unittest

from app import app


class VexoraHostPageTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_all_dashboard_pages(self):
        pages = [
            "/",
            "/projects",
            "/files",
            "/editor",
            "/terminal",
            "/logs",
            "/settings",
            "/environment",
            "/dependencies",
            "/startup",
            "/monitoring",
            "/backups",
            "/deployments",
            "/github",
            "/activity",
        ]

        for path in pages:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(
                    response.status_code,
                    200,
                    f"{path} returned HTTP {response.status_code}",
                )

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_missing_page_returns_404(self):
        response = self.client.get("/this-page-does-not-exist")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
