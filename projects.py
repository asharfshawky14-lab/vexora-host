
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
    """Return the project directory without allowing path traversal."""

    root = _projects_root()
    target = (
        root
        / str(project.owner_id)
        / str(project.id)
    ).resolve()

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
    project: Project | None = None,
    details: str = "",
) -> None:
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            project_id=project.id if project else None,
            action=action,
            details=details[:2000],
            ip_address=request.remote_addr,
        )
    )


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
        return render_template("project_form.html", project=None)

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    startup_file = request.form.get("startup_file", "main.py").strip()

    if not name or len(name) > PROJECT_NAME_MAX_LENGTH:
        flash("اسم المشروع مطلوب وبحد أقصى 80 حرفًا.", "error")
        return render_template("project_form.html", project=None), 400

    if len(description) > 500:
        flash("وصف المشروع يجب ألا يتجاوز 500 حرف.", "error")
        return render_template("project_form.html", project=None), 400

    if (
        not STARTUP_FILE_PATTERN.fullmatch(startup_file)
        or startup_file.startswith("/")
        or "\\" in startup_file
        or any(part in {"", ".", ".."} for part in startup_file.split("/"))
    ):
        flash("مسار ملف التشغيل غير صالح.", "error")
        return render_template("project_form.html", project=None), 400

    max_projects = current_app.config.get(
        "MAX_PROJECTS_PER_USER", 20
    )

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

    try:
        db.session.add(project)
        db.session.flush()

        project_dir = _project_directory(project)
        project_dir.mkdir(parents=True, exist_ok=False)

        _record_activity(
            "project_created",
            project,
            f"Created project: {project.name}",
        )

        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        if "project_dir" in locals() and project_dir.exists():
            shutil.rmtree(project_dir)
        flash("اسم المشروع مستخدم بالفعل.", "error")
        return render_template("project_form.html", project=None), 409

    except Exception:
        db.session.rollback()

        if "project_dir" in locals() and project_dir.exists():
            shutil.rmtree(project_dir)

        current_app.logger.exception("Project creation failed")
        flash("تعذر إنشاء المشروع. راجع سجل الأخطاء.", "error")
        return render_template("project_form.html", project=None), 500

    flash("تم إنشاء المشروع.", "success")
    return redirect(url_for("projects.detail", project_id=project.id))


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
        flash("الوصف طويل جدًا.", "error")
        return redirect(
            url_for("projects.detail", project_id=project.id)
        )

    if (
        not STARTUP_FILE_PATTERN.fullmatch(startup_file)
        or startup_file.startswith("/")
        or "\\" in startup_file
        or any(part in {"", ".", ".."} for part in startup_file.split("/"))
    ):
        flash("مسار ملف التشغيل غير صالح.", "error")
        return redirect(
            url_for("projects.detail", project_id=project.id)
        )

    old_name = project.name

    project.name = name
    project.description = description
    project.startup_file = startup_file

    try:
        _record_activity(
            "project_updated",
            project,
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

    # Never delete files while a runner may still be using them.
    if project.status in {"running", "starting", "stopping"}:
        flash(
            "أوقف المشروع من مشغّل البوتات قبل حذفه.",
            "error",
        )
        return redirect(url_for("projects.index"))

    project_dir = _project_directory(project)

    try:
        _record_activity(
            "project_deleted",
            project,
            f"Deleted project: {project.name}",
        )

        db.session.delete(project)
        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Project deletion failed")
        flash("تعذر حذف المشروع من قاعدة البيانات.", "error")
        return redirect(url_for("projects.index"))

    # Delete only the verified directory belonging to this project.
    if project_dir.exists():
        try:
            shutil.rmtree(project_dir)
        except OSError:
            current_app.logger.exception(
                "Project record deleted but its files could not be removed: %s",
                project.id,
            )
            flash(
                "تم حذف سجل المشروع، لكن تعذر حذف ملفاته. "
                "تحتاج إلى مراجعة التخزين.",
                "warning",
            )
            return redirect(url_for("projects.index"))

    flash("تم حذف المشروع.", "success")
    return redirect(url_for("projects.index"))


def register_projects(app):
    """Register project-management routes."""

    if "projects" in app.blueprints:
        raise RuntimeError(
            "The projects blueprint is already registered."
        )

    app.register_blueprint(projects_bp)
