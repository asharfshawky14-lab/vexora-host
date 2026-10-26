
import hashlib
import hmac
import json
import os
import re
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any

from flask import Flask, jsonify, request


def required_env(name: str, minimum_length: int = 1) -> str:
    value = os.environ.get(name, "")

    if len(value) < minimum_length:
        raise RuntimeError(
            f"Environment variable {name} must contain "
            f"at least {minimum_length} characters."
        )

    return value


RUNNER_TOKEN = required_env("RUNNER_TOKEN", 32)
RUNNER_HOST = os.environ.get("RUNNER_HOST", "127.0.0.1")
RUNNER_PORT = int(os.environ.get("RUNNER_PORT", "8090"))
MAX_CLOCK_SKEW_SECONDS = 60
MAX_BODY_BYTES = 64 * 1024

PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES

projects: dict[str, dict[str, Any]] = {}
request_timestamps: dict[str, float] = {}
lock = Lock()


def json_error(message: str, status: int):
    return jsonify({"ok": False, "error": message}), status


def authenticate_request():
    timestamp = request.headers.get("X-Vexora-Timestamp", "")
    signature = request.headers.get("X-Vexora-Signature", "")

    if not timestamp.isdigit() or len(timestamp) > 12:
        return False

    now = int(time.time())
    request_time = int(timestamp)

    if abs(now - request_time) > MAX_CLOCK_SKEW_SECONDS:
        return False

    raw_body = request.get_data(cache=True)
    body_hash = hashlib.sha256(raw_body).hexdigest()

    signing_message = "\n".join(
        [
            request.method.upper(),
            request.path,
            timestamp,
            body_hash,
        ]
    ).encode("utf-8")

    expected_signature = hmac.new(
        RUNNER_TOKEN.encode("utf-8"),
        signing_message,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return False

    # Basic replay protection for authenticated request signatures.
    replay_key = f"{timestamp}:{signature}"

    with lock:
        cutoff = time.time() - MAX_CLOCK_SKEW_SECONDS
        expired = [
            key
            for key, created_at in request_timestamps.items()
            if created_at < cutoff
        ]

        for key in expired:
            request_timestamps.pop(key, None)

        if replay_key in request_timestamps:
            return False

        request_timestamps[replay_key] = time.time()

    return True


@app.before_request
def verify_authentication():
    if request.path == "/health":
        return None

    if not authenticate_request():
        return json_error("Unauthorized", 401)

    return None


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "vexora-runner-control",
        "execution_enabled": False,
    })


@app.post("/v1/projects")
def create_project():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return json_error("Expected a JSON object", 400)

    project_id = data.get("project_id")
    owner_id = data.get("owner_id")
    name = data.get("name")

    if (
        not isinstance(project_id, str)
        or not PROJECT_ID_PATTERN.fullmatch(project_id)
    ):
        return json_error("Invalid project ID", 400)

    if (
        not isinstance(owner_id, int)
        or isinstance(owner_id, bool)
        or owner_id <= 0
    ):
        return json_error("Invalid owner ID", 400)

    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        return json_error("Invalid project name", 400)

    with lock:
        if project_id in projects:
            return json_error("Project already exists", 409)

        projects[project_id] = {
            "project_id": project_id,
            "owner_id": owner_id,
            "name": name.strip(),
            "status": "stopped",
            "logs": deque(maxlen=1000),
            "created_at": int(time.time()),
        }

    return jsonify({
        "ok": True,
        "project_id": project_id,
        "status": "stopped",
        "execution_enabled": False,
    }), 201


def get_project(project_id: str):
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        return None

    return projects.get(project_id)


@app.post("/v1/projects/<project_id>/start")
def start_project(project_id: str):
    with lock:
        project = get_project(project_id)

        if project is None:
            return json_error("Project not found", 404)

        # Deliberately do not execute uploaded Python code.
        project["status"] = "stopped"

    return json_error(
        "Python execution is disabled until an isolated runner is installed.",
        503,
    )


@app.post("/v1/projects/<project_id>/stop")
def stop_project(project_id: str):
    with lock:
        project = get_project(project_id)

        if project is None:
            return json_error("Project not found", 404)

    return jsonify({
        "ok": True,
        "project_id": project_id,
        "status": project["status"],
        "message": "No process is managed by this control service.",
    })


@app.post("/v1/projects/<project_id>/restart")
def restart_project(project_id: str):
    with lock:
        if get_project(project_id) is None:
            return json_error("Project not found", 404)

    return json_error(
        "Restart is unavailable because isolated execution is disabled.",
        503,
    )


@app.get("/v1/projects/<project_id>/status")
def project_status(project_id: str):
    with lock:
        project = get_project(project_id)

        if project is None:
            return json_error("Project not found", 404)

        return jsonify({
            "ok": True,
            "project_id": project_id,
            "status": project["status"],
            "execution_enabled": False,
        })


@app.get("/v1/projects/<project_id>/logs")
def project_logs(project_id: str):
    with lock:
        project = get_project(project_id)

        if project is None:
            return json_error("Project not found", 404)

        try:
            limit = int(request.args.get("limit", "200"))
        except ValueError:
            return json_error("Invalid log limit", 400)

        if not 1 <= limit <= 1000:
            return json_error("Log limit must be between 1 and 1000", 400)

        return jsonify({
            "ok": True,
            "project_id": project_id,
            "logs": list(project["logs"])[-limit:],
            "execution_enabled": False,
        })


@app.delete("/v1/projects/<project_id>")
def delete_project(project_id: str):
    with lock:
        if project_id not in projects:
            return json_error("Project not found", 404)

        projects.pop(project_id, None)

    return jsonify({
        "ok": True,
        "project_id": project_id,
        "deleted": True,
    })


if __name__ == "__main__":
    if not 1 <= RUNNER_PORT <= 65535:
        raise RuntimeError("RUNNER_PORT is invalid.")

    # Bind locally by default. Use a private network or authenticated
    # reverse proxy if the web application runs on another host.
    app.run(
        host=RUNNER_HOST,
        port=RUNNER_PORT,
        debug=False,
        use_reloader=False,
      )
      
