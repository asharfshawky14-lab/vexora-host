
import hmac
import os
import re
from datetime import timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy.exc import IntegrityError

from database import db
from models import User


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")


def _safe_next_url(target: str | None) -> str | None:
    """Reject external and protocol-relative redirects."""

    if not target:
        return None

    from urllib.parse import urljoin, urlsplit

    base = urlsplit(request.host_url)
    candidate = urlsplit(urljoin(request.host_url, target))

    if candidate.scheme not in {"http", "https"}:
        return None

    if candidate.netloc != base.netloc:
        return None

    if candidate.username or candidate.password:
        return None

    return candidate.path + (
        f"?{candidate.query}" if candidate.query else ""
    )


def _login_throttle_key() -> str:
    # The production deployment should also enforce rate limits
    # at the reverse proxy or a shared rate-limit service.
    return "login_failures"


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if (
            not username
            or len(username) > 254
            or not password
            or len(password) > 1024
        ):
            flash("راجع اسم المستخدم وكلمة المرور.", "error")
            return render_template("login.html"), 400

        user = User.query.filter(
            db.func.lower(User.username) == username
        ).first()

        # Use a generic message to avoid revealing whether an account exists.
        if (
            user is None
            or not user.is_active
            or not user.check_password(password)
        ):
            current_app.logger.warning(
                "Failed login attempt from %s",
                request.remote_addr or "unknown",
            )
            flash("بيانات الدخول غير صحيحة.", "error")
            return render_template("login.html"), 401

        logout_user()
        session.clear()

        login_user(user, remember=False, fresh=True)
        session.permanent = True

        next_url = _safe_next_url(request.args.get("next"))
        return redirect(next_url or url_for("dashboard.index"))

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("تم تسجيل الخروج.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/setup-owner", methods=["GET", "POST"])
def setup_owner():
    """
    One-time owner creation.

    Set OWNER_SETUP_TOKEN in the server environment, then submit
    that token with the initial username, email and password.
    This route disables itself as soon as any account exists.
    """

    setup_token = os.environ.get("OWNER_SETUP_TOKEN", "")

    if not setup_token or len(setup_token) < 32:
        return "Owner setup is not enabled.", 404

    if User.query.limit(1).first() is not None:
        return "Owner setup is already closed.", 404

    if request.method == "GET":
        return render_template("setup_owner.html")

    submitted_token = request.form.get("setup_token", "")

    if not hmac.compare_digest(submitted_token, setup_token):
        current_app.logger.warning(
            "Invalid owner setup attempt from %s",
            request.remote_addr or "unknown",
        )
        return "Forbidden", 403

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not USERNAME_PATTERN.fullmatch(username):
        flash(
            "اسم المستخدم يجب أن يكون من 3 إلى 32 حرفًا أو رقمًا "
            "أو _ أو -.",
            "error",
        )
        return render_template("setup_owner.html"), 400

    if (
        not email
        or len(email) > 254
        or "@" not in email
        or len(password) < 12
        or len(password) > 1024
    ):
        flash(
            "أدخل بريدًا إلكترونيًا صحيحًا وكلمة مرور "
            "لا تقل عن 12 حرفًا.",
            "error",
        )
        return render_template("setup_owner.html"), 400

    user = User(
        username=username,
        email=email,
        is_active_account=True,
    )
    user.set_password(password)

    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(
            "اسم المستخدم أو البريد الإلكتروني مستخدم بالفعل.",
            "error",
        )
        return render_template("setup_owner.html"), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Owner setup failed")
        return "Unable to create owner account.", 500

    # Remove the setup secret from the current process environment
    # after successful setup; also remove it from deployment settings.
    os.environ.pop("OWNER_SETUP_TOKEN", None)

    current_app.logger.info(
        "Initial owner account created: user_id=%s",
        user.id,
    )

    login_user(user, remember=False, fresh=True)
    session.permanent = True

    return redirect(url_for("dashboard.index"))


def configure_auth(app):
    app.config.setdefault(
        "PERMANENT_SESSION_LIFETIME",
        timedelta(hours=12),
    )
    app.register_blueprint(auth_bp)
