from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Task, Alert, ScrapeData, ScrapeConfig, User
from app.forms import TaskForm, AlertForm, ScrapeConfigForm, PasswordChangeForm
from app.user_forms import UserForm
from app.admin import admin_required
from app.socketio_events import emit_task_update, emit_alert_update, emit_scrape_update
from app.tasks import update_scrape_schedule
from app.scraper import perform_scrape as run_scrape
from datetime import datetime
import json

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """Redirect to dashboard"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    else:
        return redirect(url_for('auth.login'))


@bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard view"""
    # Get recent tasks for current user
    recent_tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).limit(5).all()
    
    # Get latest scraped data
    latest_scrape = ScrapeData.query.order_by(ScrapeData.scraped_at.desc()).first()
    scraped_data = latest_scrape.get_data() if latest_scrape else {}
    
    # Get active alert
    active_alert = Alert.query.filter_by(is_active=True).first()
    
    return render_template('dashboard.html', 
                         recent_tasks=recent_tasks,
                         scraped_data=scraped_data,
                         active_alert=active_alert)


@bp.route('/tasks')
@login_required
def tasks():
    """Task list management page"""
    user_tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
    form = TaskForm()
    return render_template('tasks.html', tasks=user_tasks, form=form)


@bp.route('/tasks/create', methods=['POST'])
@login_required
def create_task():
    """Create a new task"""
    form = TaskForm()
    if form.validate_on_submit():
        task = Task(
            content=form.content.data,
            completed=form.completed.data,
            user_id=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        emit_task_update(task.id)
        flash('Task created successfully!', 'success')
        return redirect(url_for('main.tasks'))
    flash('Error creating task.', 'error')
    return redirect(url_for('main.tasks'))


@bp.route('/tasks/<int:task_id>/update', methods=['POST'])
@login_required
def update_task(task_id):
    """Update an existing task"""
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('main.tasks'))
    
    form = TaskForm()
    if form.validate_on_submit():
        task.content = form.content.data
        task.completed = form.completed.data
        task.updated_at = datetime.utcnow()
        db.session.commit()
        emit_task_update(task.id)
        flash('Task updated successfully!', 'success')
    return redirect(url_for('main.tasks'))


@bp.route('/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
def toggle_task(task_id):
    """Toggle task completion status"""
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    task.completed = not task.completed
    task.updated_at = datetime.utcnow()
    db.session.commit()
    emit_task_update(task.id)
    return jsonify({'success': True, 'completed': task.completed})


@bp.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """Delete a task"""
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('main.tasks'))
    
    db.session.delete(task)
    db.session.commit()
    emit_task_update()
    flash('Task deleted successfully!', 'success')
    return redirect(url_for('main.tasks'))


@bp.route('/alerts')
@login_required
def alerts():
    """Alert management page"""
    user_alerts = Alert.query.filter_by(created_by=current_user.id).order_by(Alert.created_at.desc()).all()
    form = AlertForm()
    return render_template('alerts.html', alerts=user_alerts, form=form)


@bp.route('/alerts/create', methods=['POST'])
@login_required
def create_alert():
    """Create a new alert"""
    form = AlertForm()
    if form.validate_on_submit():
        alert = Alert(
            message=form.message.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            is_active=False,  # Will be activated by background task
            created_by=current_user.id
        )
        # If no start_time, activate immediately
        if not alert.start_time:
            alert.start_time = datetime.utcnow()
            alert.is_active = datetime.utcnow() <= alert.end_time
        else:
            alert.is_active = (alert.start_time <= datetime.utcnow() <= alert.end_time)
        
        db.session.add(alert)
        db.session.commit()
        emit_alert_update(alert.id)
        flash('Alert created successfully!', 'success')
        return redirect(url_for('main.alerts'))
    flash('Error creating alert.', 'error')
    return redirect(url_for('main.alerts'))


@bp.route('/alerts/<int:alert_id>/delete', methods=['POST'])
@login_required
def delete_alert(alert_id):
    """Delete an alert"""
    alert = Alert.query.get_or_404(alert_id)
    if alert.created_by != current_user.id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('main.alerts'))
    
    db.session.delete(alert)
    db.session.commit()
    emit_alert_update()
    flash('Alert deleted successfully!', 'success')
    return redirect(url_for('main.alerts'))


@bp.route('/settings')
@login_required
def settings():
    """Settings page for pstrax credentials"""
    config = ScrapeConfig.query.first()
    if not config:
        config = ScrapeConfig()
        db.session.add(config)
        db.session.commit()
    
    # Ensure base_url is set (for existing records that might not have it)
    if not config.pstrax_base_url:
        config.pstrax_base_url = 'https://pstrax.com'
        db.session.commit()
    
    form = ScrapeConfigForm()
    form.pstrax_base_url.data = config.pstrax_base_url
    form.pstrax_username.data = config.pstrax_username
    form.scrape_interval.data = str(config.scrape_interval)
    
    return render_template('settings.html', form=form, config=config)


@bp.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    """Update pstrax credentials"""
    config = ScrapeConfig.query.first()
    if not config:
        config = ScrapeConfig()
        db.session.add(config)
    
    # Ensure base_url is set (for existing records that might not have it)
    if not config.pstrax_base_url:
        config.pstrax_base_url = 'https://pstrax.com'
    
    form = ScrapeConfigForm()
    if form.validate_on_submit():
        if form.pstrax_base_url.data:
            # Ensure URL has protocol
            base_url = form.pstrax_base_url.data.strip()
            if base_url and not base_url.startswith(('http://', 'https://')):
                base_url = 'https://' + base_url
            config.pstrax_base_url = base_url or 'https://pstrax.com'
        config.pstrax_username = form.pstrax_username.data
        if form.pstrax_password.data:
            config.set_password(form.pstrax_password.data)
        if form.scrape_interval.data:
            try:
                config.scrape_interval = int(form.scrape_interval.data)
            except ValueError:
                flash('Invalid scrape interval.', 'error')
                return redirect(url_for('main.settings'))
        
        db.session.commit()
        
        # Update scraping schedule if interval changed
        update_scrape_schedule()
        
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('main.settings'))
    
    flash('Error updating settings.', 'error')
    return redirect(url_for('main.settings'))


@bp.route('/change-password')
@login_required
def change_password():
    """Page for users to change their password"""
    form = PasswordChangeForm()
    return render_template('change_password.html', form=form)


@bp.route('/change-password', methods=['POST'])
@login_required
def update_password():
    """Handle password change"""
    form = PasswordChangeForm()
    
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'error')
        return render_template('change_password.html', form=form)
    
    # Verify current password
    if not current_user.check_password(form.current_password.data):
        flash('Current password is incorrect.', 'error')
        return render_template('change_password.html', form=form)
    
    # Check that new password and confirm password match
    if form.new_password.data != form.confirm_password.data:
        flash('New password and confirmation do not match.', 'error')
        return render_template('change_password.html', form=form)
    
    # Update password
    current_user.set_password(form.new_password.data)
    db.session.commit()
    
    flash('Password changed successfully!', 'success')
    return redirect(url_for('main.change_password'))


# API Routes
@bp.route('/api/alerts/active')
@login_required
def get_active_alert():
    """API endpoint to get active alert"""
    active_alert = Alert.query.filter_by(is_active=True).first()
    if active_alert:
        return jsonify({'alert': active_alert.to_dict()})
    return jsonify({'alert': None})


@bp.route('/api/tasks')
@login_required
def api_tasks():
    """API endpoint to get user tasks"""
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
    return jsonify({'tasks': [task.to_dict() for task in tasks]})


@bp.route('/api/scrape-data')
@login_required
def api_scrape_data():
    """API endpoint to get latest scraped data"""
    latest_scrape = ScrapeData.query.order_by(ScrapeData.scraped_at.desc()).first()
    if latest_scrape:
        return jsonify({'data': latest_scrape.get_data(), 'scraped_at': latest_scrape.scraped_at.isoformat()})
    return jsonify({'data': {}, 'scraped_at': None})


@bp.route('/api/gear-list')
@login_required
def api_gear_list():
    """API endpoint to get gear list data"""
    try:
        from app.scraper import PstraxScraper
        
        config = ScrapeConfig.query.first()
        if not config or not config.pstrax_username or not config.pstrax_password_encrypted:
            return jsonify({'error': 'No credentials configured', 'data': None}), 400
        
        password = config.get_password()
        if not password:
            return jsonify({'error': 'Could not decrypt password', 'data': None}), 400
        
        base_url = config.pstrax_base_url or 'https://app1.pstrax.com'
        scraper = PstraxScraper()
        
        # Login first
        login_success, login_result = scraper.login(config.pstrax_username, password, base_url=base_url)
        if not login_success:
            return jsonify({'error': 'Login failed', 'data': None}), 401
        
        # Get gear list
        gear_list_response = scraper.getGearList(base_url=base_url)
        
        if gear_list_response.status_code == 200:
            try:
                gear_data = gear_list_response.json()
                return jsonify({'data': gear_data, 'status': 'success'})
            except (ValueError, json.JSONDecodeError):
                # Try parsing as text/html (server returns wrong Content-Type)
                try:
                    gear_data = json.loads(gear_list_response.text)
                    return jsonify({'data': gear_data, 'status': 'success'})
                except (ValueError, json.JSONDecodeError):
                    return jsonify({'error': 'Failed to parse JSON response', 'data': None}), 500
        else:
            return jsonify({
                'error': f'Failed to fetch gear list. Status: {gear_list_response.status_code}',
                'status_code': gear_list_response.status_code,
                'data': None
            }), gear_list_response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e), 'data': None}), 500


@bp.route('/api/scrape/trigger', methods=['POST'])
@login_required
def trigger_scrape():
    """Manually trigger a scrape"""
    try:
        run_scrape()
        flash('Scrape triggered successfully!', 'success')
        return jsonify({'success': True, 'message': 'Scrape triggered'})
    except Exception as e:
        flash(f'Error triggering scrape: {str(e)}', 'error')
        return jsonify({'success': False, 'error': str(e)}), 500


# Admin Routes
@bp.route('/admin/users')
@login_required
@admin_required
def admin_users():
    """Admin page to manage users"""
    users = User.query.order_by(User.created_at.desc()).all()
    form = UserForm()
    return render_template('admin/users.html', users=users, form=form)


@bp.route('/admin/users/create', methods=['POST'])
@login_required
@admin_required
def admin_create_user():
    """Create a new user (admin only)"""
    form = UserForm()
    if form.validate_on_submit():
        # Check if username already exists
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash(f'Username "{form.username.data}" already exists.', 'error')
            return redirect(url_for('main.admin_users'))
        
        new_user = User(
            username=form.username.data,
            is_admin=form.is_admin.data
        )
        
        if form.password.data:
            new_user.set_password(form.password.data)
        else:
            flash('Password is required.', 'error')
            return redirect(url_for('main.admin_users'))
        
        db.session.add(new_user)
        db.session.commit()
        flash(f'User "{new_user.username}" created successfully!', 'success')
    else:
        flash('Error creating user. Please check the form.', 'error')
    
    return redirect(url_for('main.admin_users'))


@bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    """Delete a user (admin only)"""
    user = User.query.get_or_404(user_id)
    
    # Don't allow deleting yourself
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('main.admin_users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{username}" deleted successfully!', 'success')
    return redirect(url_for('main.admin_users'))


@bp.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
def admin_toggle_admin(user_id):
    """Toggle admin status (admin only)"""
    user = User.query.get_or_404(user_id)
    
    # Don't allow removing your own admin status
    if user.id == current_user.id:
        return jsonify({'error': 'You cannot remove your own admin status'}), 400
    
    user.is_admin = not user.is_admin
    db.session.commit()
    
    status = 'granted' if user.is_admin else 'revoked'
    flash(f'Admin status {status} for user "{user.username}".', 'success')
    return jsonify({'success': True, 'is_admin': user.is_admin})

