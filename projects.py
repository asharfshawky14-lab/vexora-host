
import re
import shutil
from pathlib import Path

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
from sqlalchemy.exc import IntegrityError

from database import db
from models import ActivityLog, Project


projects_bp = Blueprint(
    "projects",
    __name__,
    url_prefix="/projects",
)

PROJECT_NAME_MAX_LENGTH = 80
STARTUP_FILE_PATTERN = re.compile(
    r"^[A-Za-z0-9_.\-/]{1,255}$"
)


def _projects_root() -> Path:
    configured = current_app.config.get("PROJECTS_DIR")

    if not configured:
        raise RuntimeError("PROJECTS_DIR is not configured.")

    root = Path(configured).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _project_directory(project: Project) -> Path:
    root = _projects_root()

    owner_dir = root / str(project.owner_id)
    target = (owner_dir / str(project.id)).resolve()

    if not target.is_relative_to(root):
        raise RuntimeError("Invalid project storage path.")

    return target


def _get_owned_project(project_id: int) -> Project:
    project = Project.query.filter_by(
        id=project_id,
        owner_id=current_user.id,
    ).first()

    if project is None:
        abort(404)

    return project


def _record_activity(
    action: str,
    project_id: int | None,
    details: str,
) -> ActivityLog:
    entry = ActivityLog(
        user_id=current_user.id,
        project_id=project_id,
        action=action,
        details=details[:2000],
        ip_address=request.remote_addr,
    )
    db.session.add(entry)
    return entry


def _validate_startup_file(value: str) -> bool:
    if not isinstance(value, str):
        return False

    value = value.strip()

    if not STARTUP_FILE_PATTERN.fullmatch(value):
        return False

    if value.startswith("/") or "\\" in value:
        return False

    parts = value.split("/")

    if any(part in {"", ".", ".."} for part in parts):
        return False

    if any(part.startswith(".") for part in parts):
        return False

    return True


@projects_bp.get("/")
@login_required
def index():
    projects = (
        Project.query
        .filter_by(owner_id=current_user.id)
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .all()
    )

    return render_template(
        "projects.html",
        projects=projects,
    )


@projects_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "GET":
        return render_template(
            "project_form.html",
            project=None,
        )

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    startup_file = request.form.get(
        "startup_file",
        "main.py",
    ).strip()

    if not name or len(name) > PROJECT_NAME_MAX_LENGTH:
        flash("اسم المشروع مطلوب وبحد أقصى 80 حرفًا.", "error")
        return render_template(
            "project_form.html",
            project=None,
        ), 400

    if len(description) > 500:
        flash("وصف المشروع يجب ألا يتجاوز 500 حرف.", "error")
        return render_template(
            "project_form.html",
            project=None,
        ), 400

    if not _validate_startup_file(startup_file):
        flash("مسار ملف التشغيل غير صالح.", "error")
        return render_template(
            "project_form.html",
            project=None,
        ), 400

    max_projects = int(
        current_app.config.get("MAX_PROJECTS_PER_USER", 20)
    )

    if max_projects < 1:
        raise RuntimeError("MAX_PROJECTS_PER_USER must be positive.")

    existing_count = Project.query.filter_by(
        owner_id=current_user.id
    ).count()

    if existing_count >= max_projects:
        flash("وصلت للحد الأقصى من المشاريع المسموح بها.", "error")
        return redirect(url_for("projects.index"))

    project = Project(
        owner_id=current_user.id,
        name=name,
        description=description,
        runtime="python",
        python_version="3.12",
        startup_file=startup_file,
        requirements_file="requirements.txt",
        status="stopped",
    )

    project_dir = None
    committed = False

    try:
        db.session.add(project)
        db.session.flush()

        project_dir = _project_directory(project)
        project_dir.mkdir(parents=True, exist_ok=False)

        _record_activity(
            "project_created",
            project.id,
            f"Created project: {project.name}",
        )

        db.session.commit()
        committed = True

    except IntegrityError:
        db.session.rollback()

        if project_dir is not None and project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)

        flash(
            "اسم المشروع مستخدم بالفعل أو توجد بيانات متعارضة.",
            "error",
        )
        return render_template(
            "project_form.html",
            project=None,
        ), 409

    except Exception:
        db.session.rollback()

        if project_dir is not None and project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)

        current_app.logger.exception("Project creation failed")

        flash("تعذر إنشاء المشروع.", "error")
        return render_template(
            "project_form.html",
            project=None,
        ), 500

    if committed:
        flash("تم إنشاء المشروع.", "success")

    return redirect(
        url_for("projects.detail", project_id=project.id)
    )


@projects_bp.get("/<int:project_id>")
@login_required
def detail(project_id: int):
    project = _get_owned_project(project_id)

    return render_template(
        "project_detail.html",
        project=project,
    )


@projects_bp.post("/<int:project_id>/update")
@login_required
def update(project_id: int):
    project = _get_owned_project(project_id)

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    startup_file = request.form.get(
        "startup_file",
        project.startup_file,
    ).strip()

    if not name or len(name) > PROJECT_NAME_MAX_LENGTH:
        flash("اسم المشروع مطلوب وبحد أقصى 80 حرفًا.", "error")
        return redirect(
            url_for("projects.detail", project_id=project.id)
        )

    if len(description) > 500:
        flash("الوصف يجب ألا يتجاوز 500 حرف.", "error")
        return redirect(
            url_for("projects.detail", project_id=project.id)
        )

    if not _validate_startup_file(startup_file):
        flash("مسار ملف التشغيل غير صالح.", "error")
        return redirect(
            url_for("projects.detail", project_id=project.id)
        )

    old_name = project.name

    try:
        project.name = name
        project.description = description
        project.startup_file = startup_file

        _record_activity(
            "project_updated",
            project.id,
            f"Updated project: {old_name} -> {name}",
        )

        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        flash("اسم المشروع مستخدم بالفعل.", "error")
        return redirect(
            url_for("projects.detail", project_id=project.id)
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Project update failed")
        flash("تعذر حفظ التعديلات.", "error")
        return redirect(
            url_for("projects.detail", project_id=project.id)
        )

    flash("تم حفظ بيانات المشروع.", "success")
    return redirect(
        url_for("projects.detail", project_id=project.id)
    )


@projects_bp.post("/<int:project_id>/delete")
@login_required
def delete(project_id: int):
    project = _get_owned_project(project_id)

    if project.status in {"running", "starting", "stopping"}:
        flash(
            "لا يمكن حذف المشروع قبل إيقافه من مشغّل البوتات.",
            "error",
        )
        return redirect(url_for("projects.index"))

    project_id_value = project.id
    project_name = project.name
    project_dir = _project_directory(project)

    # Preserve the deletion record independently of the project row.
    # project_id is NULL so the foreign key does not erase this audit entry.
    try:
        _record_activity(
            "project_deleted",
            None,
            f"Deleted project id={project_id_value}, "
            f"name={project_name}",
        )

        db.session.delete(project)
        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Project deletion failed")
        flash("تعذر حذف المشروع من قاعدة البيانات.", "error")
        return redirect(url_for("projects.index"))

    # Remove files only after the database transaction succeeds.
    if project_dir.exists():
        try:
            root = _projects_root()

            if (
                not project_dir.is_relative_to(root)
                or project_dir.is_symlink()
            ):
                raise RuntimeError(
                    "Refusing to remove an unsafe project directory."
                )

            shutil.rmtree(project_dir)

        except OSError:
            current_app.logger.exception(
                "Project files could not be removed for project id=%s",
                project_id_value,
            )
            flash(
                "تم حذف سجل المشروع، لكن تعذر حذف ملفاته من التخزين.",
                "warning",
            )
            return redirect(url_for("projects.index"))

        except RuntimeError:
            current_app.logger.exception(
                "Unsafe project directory; refusing deletion."
            )
            flash(
                "تم حذف سجل المشروع، لكن يلزم فحص مجلد التخزين يدويًا.",
                "warning",
            )
            return redirect(url_for("projects.index"))

    flash("تم حذف المشروع.", "success")
    return redirect(url_for("projects.index"))


def register_projects(app):
    if "projects" in app.blueprints:
        raise RuntimeError(
            "The projects blueprint is already registered."
        )

    app.register_blueprint(projects_bp)
