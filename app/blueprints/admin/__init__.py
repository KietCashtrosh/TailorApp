from flask import Blueprint

admin_bp = Blueprint('admin', __name__, template_folder='templates')

from app.blueprints.admin import routes  # noqa: E402, F401


@admin_bp.context_processor
def inject_pending_approvals():
    from app.models import User
    count = User.query.filter_by(approval_status='pending').count()
    return {'pending_approvals_count': count}
