from flask import Blueprint

tailor_bp = Blueprint('tailor', __name__, template_folder='templates')

from app.blueprints.tailor import routes  # noqa: E402, F401
