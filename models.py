
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from database import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(32),
        nullable=False,
        unique=True,
        index=True,
    )

    email = db.Column(
        db.String(254),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash = db.Column(db.String(512), nullable=False)

    is_active_account = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    projects = db.relationship(
        "Project",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    activity_logs = db.relationship(
        "ActivityLog",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "length(username) >= 3",
            name="ck_users_username_min_length",
        ),
        CheckConstraint(
            "length(email) >= 5",
            name="ck_users_email_min_length",
        ),
    )

    @property
    def is_active(self) -> bool:
        return self.is_active_account

    @validates("username")
    def validate_username(self, key, value):
        if not isinstance(value, str):
            raise ValueError("Username must be text.")

        value = value.strip().lower()

        if not 3 <= len(value) <= 32:
            raise ValueError(
                "Username must be between 3 and 32 characters."
            )

        if not all(
            character.isascii()
            and (character.isalnum() or character in "_-")
            for character in value
        ):
            raise ValueError(
                "Username may contain letters, numbers, _ and - only."
            )

        return value

    @validates("email")
    def validate_email(self, key, value):
        if not isinstance(value, str):
            raise ValueError("Email must be text.")

        value = value.strip().lower()

        if len(value) > 254 or "@" not in value:
            raise ValueError("A valid email address is required.")

        local_part, separator, domain = value.rpartition("@")

        if (
            not separator
            or not local_part
            or not domain
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
        ):
            raise ValueError("A valid email address is required.")

        return value

    def set_password(self, password: str) -> None:
        if not isinstance(password, str) or len(password) < 12:
            raise ValueError(
                "Password must contain at least 12 characters."
            )

        if len(password) > 1024:
            raise ValueError("Password is too long.")

        self.password_hash = generate_password_hash(
            password,
            method="scrypt",
        )

    def check_password(self, password: str) -> bool:
        if not isinstance(password, str):
            return False

        try:
            return check_password_hash(
                self.password_hash,
                password,
            )
        except (ValueError, TypeError):
            return False


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)

    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(80), nullable=False)

    description = db.Column(
        db.String(500),
        nullable=False,
        default="",
    )

    runtime = db.Column(
        db.String(20),
        nullable=False,
        default="python",
    )

    python_version = db.Column(
        db.String(20),
        nullable=False,
        default="3.12",
    )

    startup_file = db.Column(
        db.String(255),
        nullable=False,
        default="main.py",
    )

    requirements_file = db.Column(
        db.String(255),
        nullable=False,
        default="requirements.txt",
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="stopped",
        index=True,
    )

    runner_project_id = db.Column(
        db.String(128),
        nullable=True,
        unique=True,
    )

    last_started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    owner = db.relationship(
        "User",
        back_populates="projects",
    )

    activity_logs = db.relationship(
        "ActivityLog",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "name",
            name="uq_projects_owner_name",
        ),
        CheckConstraint(
            "length(name) BETWEEN 1 AND 80",
            name="ck_projects_name_length",
        ),
        CheckConstraint(
            "runtime = 'python'",
            name="ck_projects_supported_runtime",
        ),
        CheckConstraint(
            "status IN ('stopped', 'starting', 'running', "
            "'stopping', 'error')",
            name="ck_projects_status",
        ),
        Index(
            "ix_projects_owner_status",
            "owner_id",
            "status",
        ),
    )

    @validates("name")
    def validate_name(self, key, value):
        if not isinstance(value, str):
            raise ValueError("Project name must be text.")

        value = value.strip()

        if not value or len(value) > 80:
            raise ValueError(
                "Project name must be between 1 and 80 characters."
            )

        return value

    @validates("runtime")
    def validate_runtime(self, key, value):
        if value != "python":
            raise ValueError("Only Python projects are supported.")

        return value

    @validates("status")
    def validate_status(self, key, value):
        allowed = {
            "stopped",
            "starting",
            "running",
            "stopping",
            "error",
        }

        if value not in allowed:
            raise ValueError("Unsupported project status.")

        return value


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    action = db.Column(db.String(80), nullable=False)

    details = db.Column(
        db.Text,
        nullable=False,
        default="",
    )

    ip_address = db.Column(db.String(45), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    user = db.relationship(
        "User",
        back_populates="activity_logs",
    )

    project = db.relationship(
        "Project",
        back_populates="activity_logs",
    )

    __table_args__ = (
        Index(
            "ix_activity_logs_user_created",
            "user_id",
            "created_at",
        ),
    )
