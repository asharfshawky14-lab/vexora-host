
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app


class RunnerError(RuntimeError):
    """Raised when the external runner cannot complete a request."""


class RunnerClient:
    """Authenticated client for the separate VEXORA bot runner."""

    def __init__(
        self,
        base_url: str,
        token: str,
        connect_timeout: int = 5,
        read_timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

        if not self.base_url or not self.token:
            raise RunnerError(
                "Runner URL and authentication token are required."
            )

        if not self.base_url.startswith("https://"):
            raise RunnerError(
                "The runner must use HTTPS in production."
            )

        if self.connect_timeout < 1 or self.read_timeout < 1:
            raise RunnerError("Runner timeouts must be positive.")

    @classmethod
    def from_app_config(cls) -> "RunnerClient":
        config = current_app.config

        return cls(
            base_url=config.get("RUNNER_URL", ""),
            token=config.get("RUNNER_TOKEN", ""),
            connect_timeout=int(
                config.get("RUNNER_CONNECT_TIMEOUT", 5)
            ),
            read_timeout=int(
                config.get("RUNNER_READ_TIMEOUT", 30)
            ),
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not path.startswith("/") or path.startswith("//"):
            raise RunnerError("Invalid runner endpoint path.")

        body = None

        if payload is not None:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(body or b"").hexdigest()

        # The runner must implement the same signature format.
        signing_message = "\n".join(
            [method.upper(), path, timestamp, body_hash]
        ).encode("utf-8")

        signature = hmac.new(
            self.token.encode("utf-8"),
            signing_message,
            hashlib.sha256,
        ).hexdigest()

        request = Request(
            url=f"{self.base_url}{path}",
            data=body,
            method=method.upper(),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Vexora-Timestamp": timestamp,
                "X-Vexora-Signature": signature,
            },
        )

        try:
            # urllib uses a single timeout value for this operation.
            # Separate connect/read timeout enforcement requires a
            # transport that supports both independently.
            with urlopen(
                request,
                timeout=max(self.connect_timeout, self.read_timeout),
            ) as response:
                raw = response.read(2 * 1024 * 1024 + 1)

                if len(raw) > 2 * 1024 * 1024:
                    raise RunnerError(
                        "Runner response exceeded the size limit."
                    )

                if not raw:
                    return {}

                try:
                    result = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RunnerError(
                        "Runner returned invalid JSON."
                    ) from exc

                if not isinstance(result, dict):
                    raise RunnerError(
                        "Runner response must be a JSON object."
                    )

                return result

        except HTTPError as exc:
            # Do not expose authorization headers or tokens in errors.
            raise RunnerError(
                f"Runner returned HTTP {exc.code}."
            ) from exc

        except (URLError, TimeoutError, OSError) as exc:
            raise RunnerError(
                "Could not connect to the runner service."
            ) from exc

    @staticmethod
    def _validate_project_id(project_id: str) -> str:
        if (
            not isinstance(project_id, str)
            or not project_id
            or len(project_id) > 128
            or any(
                char not in
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for char in project_id
            )
        ):
            raise RunnerError("Invalid runner project ID.")

        return project_id

    def create_project(
        self,
        project_id: str,
        owner_id: int,
        name: str,
    ) -> dict[str, Any]:
        project_id = self._validate_project_id(project_id)

        if not isinstance(owner_id, int) or owner_id <= 0:
            raise RunnerError("Invalid owner ID.")

        if not isinstance(name, str) or not name.strip():
            raise RunnerError("Project name is required.")

        return self._request(
            "POST",
            "/v1/projects",
            {
                "project_id": project_id,
                "owner_id": owner_id,
                "name": name.strip()[:80],
            },
        )

    def start_project(self, project_id: str) -> dict[str, Any]:
        project_id = self._validate_project_id(project_id)

        return self._request(
            "POST",
            f"/v1/projects/{project_id}/start",
            {},
        )

    def stop_project(self, project_id: str) -> dict[str, Any]:
        project_id = self._validate_project_id(project_id)

        return self._request(
            "POST",
            f"/v1/projects/{project_id}/stop",
            {},
        )

    def restart_project(self, project_id: str) -> dict[str, Any]:
        project_id = self._validate_project_id(project_id)

        return self._request(
            "POST",
            f"/v1/projects/{project_id}/restart",
            {},
        )

    def get_project_status(self, project_id: str) -> dict[str, Any]:
        project_id = self._validate_project_id(project_id)

        return self._request(
            "GET",
            f"/v1/projects/{project_id}/status",
        )

    def get_project_logs(
        self,
        project_id: str,
        limit: int = 200,
    ) -> dict[str, Any]:
        project_id = self._validate_project_id(project_id)

        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise RunnerError("Log limit must be between 1 and 1000.")

        return self._request(
            "GET",
            f"/v1/projects/{project_id}/logs?limit={limit}",
        )

    def delete_project(self, project_id: str) -> dict[str, Any]:
        project_id = self._validate_project_id(project_id)

        return self._request(
            "DELETE",
            f"/v1/projects/{project_id}",
        )


def get_runner_client() -> RunnerClient:
    """Create a runner client using the active Flask configuration."""

    return RunnerClient.from_app_config()
