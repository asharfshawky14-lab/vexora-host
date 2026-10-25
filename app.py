
import os
import logging

from flask import Flask, render_template, jsonify, request
from werkzeug.exceptions import HTTPException
from database import init_db, get_db

# ==================================================
# VEXORA HOST - Main Application
# ==================================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vexora-host")

# Initialize the persistent application database.
init_db()

# All dashboard sections and their template names.
SECTIONS = {
    "dashboard": {
        "title": "Dashboard",
        "active": "dashboard",
        "template": "pages/dashboard.html",
    },
    "projects": {
        "title": "Projects / Servers",
        "active": "projects",
        "template": "pages/projects.html",
    },
    "files_page": {
        "title": "Files",
        "active": "files",
        "template": "pages/files.html",
    },
    "editor": {
        "title": "Code Editor",
        "active": "editor",
        "template": "pages/editor.html",
    },
    "terminal": {
        "title": "Terminal",
        "active": "terminal",
        "template": "pages/terminal.html",
    },
    "logs": {
        "title": "Logs",
        "active": "logs",
        "template": "pages/logs.html",
    },
    "settings": {
        "title": "Settings",
        "active": "settings",
        "template": "pages/settings.html",
    },
    "environment": {
        "title": "Environment Variables",
        "active": "environment",
        "template": "pages/environment.html",
    },
    "dependencies": {
        "title": "Dependencies",
        "active": "dependencies",
        "template": "pages/dependencies.html",
    },
    "startup": {
        "title": "Startup",
        "active": "startup",
        "template": "pages/startup.html",
    },
    "monitoring": {
        "title": "Monitoring",
        "active": "monitoring",
        "template": "pages/monitoring.html",
    },
    "backups": {
        "title": "Backups",
        "active": "backups",
        "template": "pages/backups.html",
    },
    "deployments": {
        "title": "Deployments",
        "active": "deployments",
        "template": "pages/deployments.html",
    },
    "github_page": {
        "title": "GitHub",
        "active": "github",
        "template": "pages/github.html",
    },
    "activity": {
        "title": "Activity / Events",
        "active": "activity",
        "template": "pages/activity.html",
    },
}


def render_section(section_key):
    """Render one of the independently maintained dashboard pages."""
    section = SECTIONS[section_key]

    return render_template(
        section["template"],
        page_title=section["title"],
        active_page=section["active"],
        app_name="VEXORA HOST",
    )


# ==================================================
# Main dashboard
# ==================================================

@app.route("/")
def dashboard():
    return render_section("dashboard")


# ==================================================
# Projects and server management
# ==================================================

@app.route("/projects")
def projects():
    return render_section("projects")


# ==================================================
# Files
# ==================================================

@app.route("/files")
def files_page():
    return render_section("files_page")


# ==================================================
# Code editor
# ==================================================

@app.route("/editor")
def editor():
    return render_section("editor")


# ==================================================
# Terminal
# ==================================================

@app.route("/terminal")
def terminal():
    return render_section("terminal")


# ==================================================
# Logs
# ==================================================

@app.route("/logs")
def logs():
    return render_section("logs")


# ==================================================
# Settings
# ==================================================

@app.route("/settings")
def settings():
    return render_section("settings")


# ==================================================
# Environment variables
# ==================================================

@app.route("/environment")
def environment():
    return render_section("environment")


# ==================================================
# Dependencies
# ==================================================

@app.route("/dependencies")
def dependencies():
    return render_section("dependencies")


# ==================================================
# Startup configuration
# ==================================================

@app.route("/startup")
def startup():
    return render_section("startup")


# ==================================================
# Resource monitoring
# ==================================================

@app.route("/monitoring")
def monitoring():
    return render_section("monitoring")


# ==================================================
# Backups
# ==================================================

@app.route("/backups")
def backups():
    return render_section("backups")


# ==================================================
# Deployments
# ==================================================

@app.route("/deployments")
def deployments():
    return render_section("deployments")


# ==================================================
# GitHub integration page
# ==================================================

@app.route("/github")
def github_page():
    return render_section("github_page")


# ==================================================
# Activity and events
# ==================================================

@app.route("/activity")
def activity():
    return render_section("activity")


# ==================================================
# Health check for the hosting platform
# ==================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "application": "VEXORA HOST",
    }), 200


# ==================================================
# Error handlers
# ==================================================

@app.errorhandler(404)
def page_not_found(error):
    if request_wants_json():
        return jsonify({"error": "Not found"}), 404

    return (
        render_template(
            "errors/404.html",
            app_name="VEXORA HOST",
        ),
        404,
    )


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return error

    logger.exception("Unexpected application error")

    if request_wants_json():
        return jsonify({"error": "Internal server error"}), 500

    return (
        render_template(
            "errors/500.html",
            app_name="VEXORA HOST",
        ),
        500,
    )


def request_wants_json():
    from flask import request

    return (
        request.path.startswith("/api/")
        or request.is_json
        or "application/json" in request.headers.get("Accept", "")
    )


# ==================================================
# Local development entry point
# ==================================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
