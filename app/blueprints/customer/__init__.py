from flask import Blueprint

customer_bp = Blueprint('customer', __name__, template_folder='templates')

from app.blueprints.customer import routes  # noqa: E402, F401
