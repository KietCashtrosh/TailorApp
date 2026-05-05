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
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Contact support.', 'danger')
                return render_template('auth/login.html', title='Sign In')
            if user.approval_status == 'pending':
                flash('Your account is awaiting admin approval. You will be notified once approved.', 'warning')
                return render_template('auth/login.html', title='Sign In')
            if user.approval_status == 'rejected':
                flash('Your registration was not approved. Contact support for assistance.', 'danger')
                return render_template('auth/login.html', title='Sign In')
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

        if role not in ('customer', 'tailor', 'delivery'):
            flash('Invalid role selected.', 'danger')
            return render_template('auth/register.html', title='Register')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html', title='Register')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('auth/register.html', title='Register')

        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'danger')
            return render_template('auth/register.html', title='Register')

        # Tailors and delivery agents start in 'pending' — admin must approve
        approval_status = 'pending' if role in ('tailor', 'delivery') else 'approved'

        user = User(name=name, email=email, phone=phone, role=role,
                    approval_status=approval_status)
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

        if role in ('tailor', 'delivery'):
            flash('Account created! Your application is under review — an admin will approve it shortly.', 'info')
        else:
            flash('Account created! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', title='Register')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
