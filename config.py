
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        result = int(value)
    except ValueError as exc:
        raise RuntimeError(
            f"Environment variable {name} must be an integer."
        ) from exc

    if result < minimum:
        raise RuntimeError(
            f"Environment variable {name} must be at least {minimum}."
        )

    return result


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'instance' / 'vexora.db').as_posix()}",
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    MAX_CONTENT_LENGTH = _get_int(
        "MAX_UPLOAD_MB", 50, minimum=1
    ) * 1024 * 1024

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _get_bool(
        "SESSION_COOKIE_SECURE", True
    )

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = _get_bool(
        "REMEMBER_COOKIE_SECURE", True
    )
    REMEMBER_COOKIE_SAMESITE = "Lax"

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    PASSWORD_HASH_ROUNDS = _get_int(
        "PASSWORD_HASH_ROUNDS", 12, minimum=4
    )

    PROJECTS_DIR = Path(
        os.getenv("PROJECTS_DIR", str(BASE_DIR / "projects"))
    ).resolve()

    BACKUPS_DIR = Path(
        os.getenv("BACKUPS_DIR", str(BASE_DIR / "backups"))
    ).resolve()

    LOGS_DIR = Path(
        os.getenv("LOGS_DIR", str(BASE_DIR / "logs"))
    ).resolve()

    MAX_PROJECTS_PER_USER = _get_int(
        "MAX_PROJECTS_PER_USER", 20
    )

    MAX_PROJECT_FILE_MB = _get_int(
        "MAX_PROJECT_FILE_MB", 10
    )

    MAX_PROJECT_FILES = _get_int(
        "MAX_PROJECT_FILES", 1000
    )

    RUNNER_URL = os.getenv("RUNNER_URL", "").rstrip("/")
    RUNNER_TOKEN = os.getenv("RUNNER_TOKEN", "")

    RUNNER_CONNECT_TIMEOUT = _get_int(
        "RUNNER_CONNECT_TIMEOUT", 5
    )
    RUNNER_READ_TIMEOUT = _get_int(
        "RUNNER_READ_TIMEOUT", 30
    )

    @classmethod
    def validate(cls) -> None:
        if not cls.SECRET_KEY or len(cls.SECRET_KEY) < 32:
            raise RuntimeError(
                "SECRET_KEY must be set to a random secret "
                "of at least 32 characters."
            )

        if cls.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///"):
            if os.getenv("DATABASE_URL") is None:
                db_path = BASE_DIR / "instance" / "vexora.db"
                db_path.parent.mkdir(
                    parents=True, exist_ok=True
                )

        for directory in (
            cls.PROJECTS_DIR,
            cls.BACKUPS_DIR,
            cls.LOGS_DIR,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def runner_is_configured(cls) -> bool:
        return bool(cls.RUNNER_URL and cls.RUNNER_TOKEN)
