
from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required
from sqlalchemy import desc, func

from database import db
from models import ActivityLog, Project


dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/dashboard",
)


@dashboard_bp.get("/")
@login_required
def index():
    """Display dashboard data belonging to the signed-in user."""

    owner_id = current_user.id

    # Every project query is scoped to the authenticated owner.
    project_count = (
        db.session.query(func.count(Project.id))
        .filter(Project.owner_id == owner_id)
        .scalar()
        or 0
    )

    status_counts = dict(
        db.session.query(
            Project.status,
            func.count(Project.id),
        )
        .filter(Project.owner_id == owner_id)
        .group_by(Project.status)
        .all()
    )

    running_count = status_counts.get("running", 0)
    starting_count = status_counts.get("starting", 0)
    stopped_count = status_counts.get("stopped", 0)
    stopping_count = status_counts.get("stopping", 0)
    error_count = status_counts.get("error", 0)

    recent_projects = (
        Project.query
        .filter(Project.owner_id == owner_id)
        .order_by(desc(Project.updated_at), desc(Project.id))
        .limit(8)
        .all()
    )

    recent_activity = (
        ActivityLog.query
        .filter(ActivityLog.user_id == owner_id)
        .order_by(
            desc(ActivityLog.created_at),
            desc(ActivityLog.id),
        )
        .limit(10)
        .all()
    )

    return render_template(
        "dashboard.html",
        project_count=project_count,
        running_count=running_count,
        starting_count=starting_count,
        stopped_count=stopped_count,
        stopping_count=stopping_count,
        error_count=error_count,
        recent_projects=recent_projects,
        recent_activity=recent_activity,
    )


def register_dashboard(app):
    """Register dashboard routes with the Flask application."""

    if "dashboard" in app.blueprints:
        raise RuntimeError(
            "The dashboard blueprint is already registered."
        )

    app.register_blueprint(dashboard_bp)
