from flask import Blueprint

customer_bp = Blueprint('customer', __name__, template_folder='templates')

from app.blueprints.customer import routes  # noqa: E402, F401


@customer_bp.context_processor
def inject_cart_count():
    from flask_login import current_user
    from app.models import CartItem
    count = 0
    if current_user.is_authenticated and current_user.role == 'customer':
        count = CartItem.query.filter_by(customer_id=current_user.id).count()
    return {'cart_count': count}
