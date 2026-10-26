
from pathlib import Path, PurePosixPath

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from database import db
from models import ActivityLog, Project


file_manager_bp = Blueprint(
    "file_manager",
    __name__,
    url_prefix="/projects",
)

TEXT_EXTENSIONS = {
    ".py", ".txt", ".md", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".sh", ".html", ".css",
    ".js", ".xml", ".sql",
}

BLOCKED_NAMES = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
}

BLOCKED_SUFFIXES = {".pyc", ".pyo"}
DEFAULT_MAX_FILE_MB = 10
DEFAULT_MAX_FILES = 1000


def _get_project(project_id: int) -> Project:
    project = Project.query.filter_by(
        id=project_id,
        owner_id=current_user.id,
    ).first()

    if project is None:
        abort(404)

    return project


def _project_root(project: Project) -> Path:
    configured = current_app.config.get("PROJECTS_DIR")

    if not configured:
        raise RuntimeError("PROJECTS_DIR is not configured.")

    root = Path(configured).resolve()
    root.mkdir(parents=True, exist_ok=True)

    target = (
        root / str(project.owner_id) / str(project.id)
    ).resolve()

    if not target.is_relative_to(root):
        abort(400, description="Invalid project directory.")

    return target


def _safe_path(project: Project, relative_path: str) -> Path:
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or len(relative_path) > 255
        or "\x00" in relative_path
    ):
        abort(400, description="Invalid file path.")

    normalized = relative_path.replace("\\", "/")
    pure = PurePosixPath(normalized)

    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or any(part.startswith(".") for part in pure.parts)
        or any(part in BLOCKED_NAMES for part in pure.parts)
        or any(part.endswith(":") for part in pure.parts)
        or pure.suffix.lower() in BLOCKED_SUFFIXES
    ):
        abort(400, description="This path is not allowed.")

    root = _project_root(project)
    target = root.joinpath(*pure.parts).resolve()

    if not target.is_relative_to(root):
        abort(400, description="Path escapes project directory.")

    current = root

    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            abort(400, description="Symbolic links are not allowed.")

    return target


def _limits() -> tuple[int, int]:
    max_file_mb = int(
        current_app.config.get(
            "MAX_PROJECT_FILE_MB", DEFAULT_MAX_FILE_MB
        )
    )
    max_files = int(
        current_app.config.get(
            "MAX_PROJECT_FILES", DEFAULT_MAX_FILES
        )
    )

    if max_file_mb < 1 or max_files < 1:
        raise RuntimeError("File limits must be positive.")

    return max_file_mb * 1024 * 1024, max_files


def _count_files(root: Path) -> int:
    if not root.exists():
        return 0

    count = 0

    for item in root.rglob("*"):
        if item.is_symlink():
            continue
        if item.is_file():
            count += 1

    return count


def _record(project: Project, action: str, path: str) -> None:
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            project_id=project.id,
            action=action,
            details=path[:2000],
            ip_address=request.remote_addr,
        )
    )


def _require_text_file(path: Path, max_bytes: int) -> str:
    if not path.exists() or not path.is_file():
        abort(404)

    if path.stat().st_size > max_bytes:
        abort(413, description="File exceeds the editing size limit.")

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        abort(415, description="File is not UTF-8 text.")


@file_manager_bp.get("/<int:project_id>/files")
@login_required
def list_files(project_id: int):
    project = _get_project(project_id)
    root = _project_root(project)
    root.mkdir(parents=True, exist_ok=True)

    files = []

    for item in sorted(root.rglob("*")):
        if item.is_symlink() or not item.is_file():
            continue

        relative = item.relative_to(root).as_posix()
        parts = PurePosixPath(relative).parts

        if (
            any(part.startswith(".") for part in parts)
            or any(part in BLOCKED_NAMES for part in parts)
            or item.suffix.lower() in BLOCKED_SUFFIXES
        ):
            continue

        files.append({
            "path": relative,
            "size": item.stat().st_size,
            "editable": item.suffix.lower() in TEXT_EXTENSIONS,
        })

    return render_template(
        "file_manager.html",
        project=project,
        files=files,
    )


@file_manager_bp.route(
    "/<int:project_id>/files/new",
    methods=["GET", "POST"],
)
@login_required
def create_file(project_id: int):
    project = _get_project(project_id)
    root = _project_root(project)
    max_bytes, max_files = _limits()

    if request.method == "GET":
        return render_template(
            "file_editor.html",
            project=project,
            file_path="",
            content="",
            is_new=True,
        )

    relative = request.form.get("path", "").strip()
    content = request.form.get("content", "")

    target = _safe_path(project, relative)

    if target.suffix.lower() not in TEXT_EXTENSIONS:
        abort(415, description="Unsupported text file type.")

    if not isinstance(content, str):
        abort(400, description="Invalid file content.")

    encoded = content.encode("utf-8")

    if len(encoded) > max_bytes:
        abort(413, description="File exceeds the size limit.")

    if _count_files(root) >= max_files:
        flash("وصلت للحد الأقصى لعدد الملفات.", "error")
        return redirect(
            url_for("file_manager.list_files", project_id=project.id)
        )

    if target.exists():
        flash("الملف موجود بالفعل.", "error")
        return redirect(
            url_for("file_manager.list_files", project_id=project.id)
        )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)

        # Re-check the final path after creating parent directories.
        target = _safe_path(project, relative)

        with target.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)

        _record(project, "file_created", relative)
        db.session.commit()

    except FileExistsError:
        db.session.rollback()
        flash("الملف موجود بالفعل.", "error")
        return redirect(
            url_for("file_manager.list_files", project_id=project.id)
        )

    except Exception:
        db.session.rollback()

        if target.exists() and target.is_file():
            target.unlink(missing_ok=True)

        current_app.logger.exception("File creation failed")
        flash("تعذر إنشاء الملف.", "error")
        return redirect(
            url_for("file_manager.list_files", project_id=project.id)
        )

    flash("تم إنشاء الملف.", "success")
    return redirect(
        url_for(
            "file_manager.edit_file",
            project_id=project.id,
            file_path=relative,
        )
    )


@file_manager_bp.route(
    "/<int:project_id>/files/edit",
    methods=["GET", "POST"],
)
@login_required
def edit_file(project_id: int):
    project = _get_project(project_id)
    max_bytes, _ = _limits()

    relative = request.args.get("file_path", "")

    if request.method == "POST":
        relative = request.form.get("file_path", "")

    target = _safe_path(project, relative)

    if target.suffix.lower() not in TEXT_EXTENSIONS:
        abort(415, description="Unsupported text file type.")

    if request.method == "GET":
        content = _require_text_file(target, max_bytes)

        return render_template(
            "file_editor.html",
            project=project,
            file_path=relative,
            content=content,
            is_new=False,
        )

    content = request.form.get("content", "")

    if not isinstance(content, str):
        abort(400, description="Invalid file content.")

    encoded = content.encode("utf-8")

    if len(encoded) > max_bytes:
        abort(413, description="File exceeds the size limit.")

    if not target.exists() or not target.is_file():
        abort(404)

    # Refuse editing a file if it has become a symbolic link.
    if target.is_symlink():
        abort(400, description="Symbolic links are not allowed.")

    try:
        # Write atomically to avoid leaving a partially-written file.
        temporary = target.with_name(target.name + ".vexora-tmp")

        if temporary.exists() or temporary.is_symlink():
            abort(409, description="A temporary file already exists.")

        with temporary.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()

        temporary.replace(target)

        _record(project, "file_updated", relative)
        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception("File update failed")
        flash("تعذر حفظ الملف.", "error")
        return redirect(
            url_for(
                "file_manager.edit_file",
                project_id=project.id,
                file_path=relative,
            )
        )

    flash("تم حفظ الملف.", "success")
    return redirect(
        url_for(
            "file_manager.edit_file",
            project_id=project.id,
            file_path=relative,
        )
    )


@file_manager_bp.post(
    "/<int:project_id>/files/delete",
)
@login_required
def delete_file(project_id: int):
    project = _get_project(project_id)
    relative = request.form.get("file_path", "")
    target = _safe_path(project, relative)

    if not target.exists() or not target.is_file():
        abort(404)

    if target.is_symlink():
        abort(400, description="Symbolic links are not allowed.")

    try:
        target.unlink()

        _record(project, "file_deleted", relative)
        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception("File deletion failed")
        flash("تعذر حذف الملف.", "error")
        return redirect(
            url_for("file_manager.list_files", project_id=project.id)
        )

    # Remove empty parent directories, but never remove project root.
    root = _project_root(project)
    parent = target.parent

    while parent != root and parent.is_relative_to(root):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent

    flash("تم حذف الملف.", "success")
    return redirect(
        url_for("file_manager.list_files", project_id=project.id)
    )


def register_file_manager(app):
    if "file_manager" in app.blueprints:
        raise RuntimeError(
            "The file manager blueprint is already registered."
        )

    app.register_blueprint(file_manager_bp)
