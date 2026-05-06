from flask import Flask
from config import Config
from app.extensions import db, login_manager, csrf


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    from app.blueprints.auth import auth_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.tailor import tailor_bp
    from app.blueprints.delivery import delivery_bp
    from app.blueprints.customer import customer_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(tailor_bp, url_prefix='/tailor')
    app.register_blueprint(delivery_bp, url_prefix='/delivery')
    app.register_blueprint(customer_bp, url_prefix='/')

    from app.models import User, Notification, CartItem, FamilyProfile

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_globals():
        from flask import session
        from flask_login import current_user
        unread_notif_count = 0
        cart_count = 0
        active_family_profile = None
        if current_user.is_authenticated:
            unread_notif_count = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).count()
            if current_user.role == 'customer':
                cart_count = CartItem.query.filter_by(
                    customer_id=current_user.id
                ).count()
                profile_id = session.get('active_profile_id')
                if profile_id:
                    active_family_profile = FamilyProfile.query.filter_by(
                        id=profile_id, user_id=current_user.id
                    ).first()
        return {
            'unread_notif_count': unread_notif_count,
            'cart_count': cart_count,
            'active_family_profile': active_family_profile,
        }

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template as rt
        return rt('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template as rt
        return rt('errors/500.html'), 500

    return app
