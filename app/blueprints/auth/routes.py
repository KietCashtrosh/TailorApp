from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.blueprints.auth import auth_bp
from app.extensions import db
from app.models import User, TailorProfile


def _redirect_by_role(user):
    if user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif user.role == 'tailor':
        return redirect(url_for('tailor.dashboard'))
    elif user.role == 'delivery':
        return redirect(url_for('delivery.dashboard'))
    else:
        return redirect(url_for('customer.home'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(next_page) if next_page else _redirect_by_role(user)

        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html', title='Sign In')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        role = request.form.get('role', 'customer')

        if role not in ('customer', 'tailor'):
            flash('Invalid role selected.', 'danger')
            return render_template('auth/register.html', title='Register')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html', title='Register')

        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'danger')
            return render_template('auth/register.html', title='Register')

        user = User(name=name, email=email, phone=phone, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        if role == 'tailor':
            shop_name = request.form.get('shop_name', '').strip()
            address = request.form.get('address', '').strip()
            profile = TailorProfile(
                user_id=user.id,
                shop_name=shop_name or f"{name}'s Tailor Shop",
                address=address or 'Address not set',
            )
            db.session.add(profile)

        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', title='Register')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
