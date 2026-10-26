
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, jsonify, redirect, url_for
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from database import db, init_extensions
from models import User, Project, ActivityLog

from auth import configure_auth
from dashboard import register_dashboard
from projects import projects_bp
from file_manager import register_file_manager


def configure_logging(app: Flask) -> None:
    """Configure console and rotating file logging."""

    log_dir = Path(app.config["LOGS_DIR"])
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "vexora.log"

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    app.logger.setLevel(logging.INFO)

    if not any(
        isinstance(handler, RotatingFileHandler)
        and getattr(handler, "baseFilename", None)
        == str(log_file.resolve())
        for handler in app.logger.handlers
    ):
        app.logger.addHandler(file_handler)


def register_security_headers(app: Flask) -> None:
    """Add baseline browser security headers."""

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault(
            "X-Content-Type-Options",
            "nosniff",
        )
        response.headers.setdefault(
            "X-Frame-Options",
            "SAMEORIGIN",
        )
        response.headers.setdefault(
            "Referrer-Policy",
            "strict-origin-when-cross-origin",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )

        if request_is_https():
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response

    def request_is_https() -> bool:
        from flask import request

        return request.is_secure


def register_error_handlers(app: Flask) -> None:
    """Return safe errors without exposing internal tracebacks."""

    @app.errorhandler(400)
    def bad_request(error):
        if _wants_json():
            return jsonify({
                "ok": False,
                "error": "Bad request",
            }), 400

        return (
            "الطلب غير صالح. راجع البيانات وحاول مرة تانية.",
            400,
        )

    @app.errorhandler(403)
    def forbidden(error):
        if _wants_json():
            return jsonify({
                "ok": False,
                "error": "Forbidden",
            }), 403

        return "مش مسموح لك بتنفيذ الطلب ده.", 403

    @app.errorhandler(404)
    def not_found(error):
        if _wants_json():
            return jsonify({
                "ok": False,
                "error": "Not found",
            }), 404

        return "الصفحة المطلوبة غير موجودة.", 404

    @app.errorhandler(413)
    def request_too_large(error):
        if _wants_json():
            return jsonify({
                "ok": False,
                "error": "Request too large",
            }), 413

        return "حجم الملف أو الطلب أكبر من المسموح.", 413

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception(
            "Unhandled application error",
            exc_info=error,
        )

        if _wants_json():
            return jsonify({
                "ok": False,
                "error": "Internal server error",
            }), 500

        return "حصل خطأ داخلي. حاول مرة تانية.", 500

    def _wants_json() -> bool:
        from flask import request

        return (
            request.path.startswith("/api/")
            or request.is_json
            or "application/json"
            in request.headers.get("Accept", "")
        )


def create_app(test_config=None) -> Flask:
    """Create and configure the VEXORA HOST web application."""

    app = Flask(
        __name__,
        instance_relative_config=True,
    )

    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    # Validate the environment configuration outside test mode.
    if not test_config:
        Config.validate()

    Path(app.instance_path).mkdir(
        parents=True,
        exist_ok=True,
    )

    configure_logging(app)
    init_extensions(app)

    # Register authentication, dashboard, project, and file routes.
    configure_auth(app)
    register_dashboard(app)
    app.register_blueprint(projects_bp)
    register_file_manager(app)

    register_security_headers(app)
    register_error_handlers(app)

    @app.get("/")
    def index():
        return redirect(url_for("dashboard.index"))

    @app.get("/health")
    def health():
        """Basic application health check."""

        return jsonify({
            "ok": True,
            "service": "vexora-host",
        })

    @app.get("/health/database")
    def database_health():
        """Check whether the configured database can answer a query."""

        try:
            db.session.execute(text("SELECT 1"))
            return jsonify({
                "ok": True,
                "database": "connected",
            })
        except Exception:
            db.session.rollback()
            app.logger.exception("Database health check failed")

            return jsonify({
                "ok": False,
                "database": "unavailable",
            }), 503

    @app.cli.command("init-db")
    def init_db_command():
        """Create missing database tables for a fresh installation."""

        # Importing models above registers the ORM tables.
        with app.app_context():
            db.create_all()

        print("VEXORA HOST database tables initialized.")

    if os.environ.get("AUTO_CREATE_DB", "false").lower() in {
        "1",
        "true",
        "yes",
    }:
        with app.app_context():
            db.create_all()
            app.logger.info(
                "Database table initialization completed."
            )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        debug=False,
        )
          
