from flask import Blueprint

delivery_bp = Blueprint('delivery', __name__, template_folder='templates')

from app.blueprints.delivery import routes  # noqa: E402, F401
