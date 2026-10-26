
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect


db = SQLAlchemy(
    session_options={
        "expire_on_commit": False,
    }
)

login_manager = LoginManager()
csrf = CSRFProtect()


def init_extensions(app: Flask) -> None:
    """Initialize shared Flask extensions for the application."""

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY must be configured before initializing extensions."
        )

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError(
            "SQLALCHEMY_DATABASE_URI must be configured."
        )

    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "info"

    csrf.init_app(app)


@login_manager.user_loader
def load_user(user_id: str):
    """Load an authenticated user from the database."""

    from models import User

    try:
        parsed_id = int(user_id)
    except (TypeError, ValueError):
        return None

    if parsed_id <= 0:
        return None

    return db.session.get(User, parsed_id)
