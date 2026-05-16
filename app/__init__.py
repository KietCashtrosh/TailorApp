import os
from flask import Flask, jsonify
from config import config_map, DevelopmentConfig


def create_app(config_class=None):
    """
    Application factory.

    config_class can be:
      - a Config class (for tests: TestingConfig)
      - None  → reads FLASK_ENV env var, falls back to DevelopmentConfig
    """
    if config_class is None:
        env = os.environ.get('FLASK_ENV', 'development').lower()
        config_class = config_map.get(env, DevelopmentConfig)

    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Fix url_for() to generate https:// links on Railway/Render ───────────
    # Railway terminates TLS at its proxy and forwards X-Forwarded-Proto.
    # Without this, url_for(_external=True) produces http:// links in emails.
    if os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER'):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    from app.extensions import db, login_manager, csrf, mail
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    # Ensure upload sub-directories exist
    for sub in ('catalogue', 'shop_photos', 'work_images'):
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], sub), exist_ok=True)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    # ── Blueprints ────────────────────────────────────────────────────────────
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
    from flask_login import user_loaded_from_cookie

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @user_loaded_from_cookie.connect_via(app)
    def on_loaded_from_cookie(sender, user):
        """Remember-me cookie just restored this customer into a fresh session.
        Clear the profile selection so home() will redirect to the selector."""
        from flask import session
        if hasattr(user, 'role') and user.role == 'customer':
            session.pop('active_profile_id', None)

    # ── Context processor ─────────────────────────────────────────────────────
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

    # ── Health check endpoint (used by Railway load balancer) ─────────────────
    @app.route('/healthz')
    def healthz():
        """Lightweight liveness probe — no auth, no DB query needed."""
        return jsonify(status='ok'), 200

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template as rt
        return rt('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template as rt
        return rt('errors/500.html'), 500

    return app
