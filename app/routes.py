from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db, socketio
from app.models import Task, Alert, ScrapeData, ScrapeConfig, User, Equipment, CylinderFillLog, FillSite, FillBoard
from app.forms import TaskForm, AlertForm, ScrapeConfigForm, PasswordChangeForm, FillSiteForm, FillBoardForm
from app.user_forms import UserForm
from app.admin import admin_required
from app.socketio_events import emit_task_update, emit_alert_update, emit_scrape_update
from app.tasks import update_scrape_schedule, update_equipment_scrape_schedule
from app.scraper import perform_scrape as run_scrape
from app.scraper import perform_equipment_scrape as run_equipment_scrape
from app.scraper import perform_pstrax_batch_air_fill
from app.timezone_utils import local_now, normalize_timezone_name
from datetime import datetime, date
import json
import uuid
from sqlalchemy import func

bp = Blueprint('main', __name__)


def _parse_mdy_date(value):
    """Parse mm/dd/yyyy (or m/d/yyyy) into a date, or None."""
    if not value:
        return None
    text = str(value).strip()
    parts = text.split('/')
    if len(parts) != 3:
        return None
    try:
        month = int(parts[0])
        day = int(parts[1])
        year = int(parts[2])
        return date(year, month, day)
    except (TypeError, ValueError):
        return None


def _is_hydro_overdue(next_hydro):
    hydro_date = _parse_mdy_date(next_hydro)
    if hydro_date is None:
        return False
    return hydro_date < date.today()


@bp.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Check database connectivity by performing a simple query
        User.query.first()
        db_status = 'healthy'
        db_error = None
    except Exception as e:
        db_status = 'unhealthy'
        db_error = str(e)
    
    # Get basic application stats
    try:
        user_count = User.query.count()
        task_count = Task.query.count()
        alert_count = Alert.query.count()
        scrape_config_exists = ScrapeConfig.query.first() is not None
        latest_scrape = ScrapeData.query.order_by(ScrapeData.scraped_at.desc()).first()
        
        stats = {
            'users': user_count,
            'tasks': task_count,
            'alerts': alert_count,
            'scrape_config_configured': scrape_config_exists,
            'latest_scrape': latest_scrape.scraped_at.isoformat() if latest_scrape else None
        }
    except Exception as e:
        stats = {'error': str(e)}
    
    # Determine overall health status
    overall_status = 'healthy' if db_status == 'healthy' else 'unhealthy'
    
    response = {
        'status': overall_status,
        'timestamp': datetime.utcnow().isoformat(),
        'database': {
            'status': db_status,
            'error': db_error
        },
        'stats': stats
    }
    
    status_code = 200 if overall_status == 'healthy' else 503
    return jsonify(response), status_code


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
    # Get recent incomplete tasks (all users, since only admins can create tasks)
    recent_tasks = Task.query.filter_by(completed=False).order_by(Task.priority.asc(), Task.created_at.desc()).limit(5).all()
    
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
    # Show all tasks to all users (since only admins can create tasks)
    all_tasks = Task.query.order_by(Task.priority.asc(), Task.created_at.desc()).all()
    form = TaskForm()
    return render_template('tasks.html', tasks=all_tasks, form=form)


@bp.route('/tasks/create', methods=['POST'])
@login_required
@admin_required
def create_task():
    """Create a new task"""
    form = TaskForm()
    if form.validate_on_submit():
        task = Task(
            content=form.content.data,
            completed=form.completed.data,
            priority=form.priority.data,
            user_id=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        emit_task_update(task.id, action='added')
        flash('Task created successfully!', 'success')
        return redirect(url_for('main.tasks'))
    flash('Error creating task.', 'error')
    return redirect(url_for('main.tasks'))


@bp.route('/tasks/<int:task_id>/update', methods=['POST'])
@login_required
@admin_required
def update_task(task_id):
    """Update an existing task - admin only"""
    task = Task.query.get_or_404(task_id)
    
    # Handle JSON requests (AJAX)
    if request.is_json or request.headers.get('Content-Type') == 'application/json':
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'errors': {'content': ['No data provided']}}), 400
        
        content = data.get('content', '').strip()
        if not content:
            return jsonify({'success': False, 'errors': {'content': ['Task content cannot be empty']}}), 400
        
        if len(content) > 1000:
            return jsonify({'success': False, 'errors': {'content': ['Task content cannot exceed 1000 characters']}}), 400
        
        task.content = content
        task.completed = data.get('completed', task.completed)
        task.priority = data.get('priority', task.priority)
        task.updated_at = datetime.utcnow()
        db.session.commit()
        emit_task_update(task.id, action='updated')
        
        return jsonify({'success': True, 'task': task.to_dict()})
    
    # Handle form submissions
    form = TaskForm()
    if form.validate_on_submit():
        task.content = form.content.data
        task.completed = form.completed.data
        task.priority = form.priority.data
        task.updated_at = datetime.utcnow()
        db.session.commit()
        emit_task_update(task.id, action='updated')
        flash('Task updated successfully!', 'success')
        return redirect(url_for('main.tasks'))
    
    # Form validation errors
    errors = {field: [error for error in field_errors] for field, field_errors in form.errors.items()}
    if errors:
        flash('Error updating task. Please check the form.', 'error')
    return redirect(url_for('main.tasks'))


@bp.route('/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
def toggle_task(task_id):
    """Toggle task completion status - any user can toggle any task"""
    task = Task.query.get_or_404(task_id)
    
    task.completed = not task.completed
    task.updated_at = datetime.utcnow()
    db.session.commit()
    action = 'completed' if task.completed else 'uncompleted'
    emit_task_update(task.id, action=action)
    return jsonify({'success': True, 'completed': task.completed})


@bp.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_task(task_id):
    """Delete a task - admin only"""
    task = Task.query.get_or_404(task_id)
    
    deleted_task_id = task.id
    db.session.delete(task)
    db.session.commit()
    socketio.emit('task_updated', {'id': deleted_task_id, 'action': 'deleted'}, namespace='/')
    
    # Return JSON for AJAX requests, redirect for form submissions
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({'success': True, 'id': deleted_task_id})
    
    flash('Task deleted successfully!', 'success')
    return redirect(url_for('main.tasks'))


@bp.route('/alerts')
@login_required
def alerts():
    """Alert management page"""
    alerts = Alert.query.order_by(Alert.created_at.desc()).all()
    form = AlertForm()
    config = ScrapeConfig.query.first()
    default_color = config.get_default_alert_color() if config else 'danger'
    # Always apply configured default for new alert form, so admins see the current default pre-selected
    form.color_theme.data = default_color
    return render_template('alerts.html', alerts=alerts, form=form)


@bp.route('/alerts/create', methods=['POST'])
@login_required
@admin_required
def create_alert():
    """Create a new alert"""
    form = AlertForm()
    config = ScrapeConfig.query.first()
    default_color = config.get_default_alert_color() if config else 'danger'
    if form.validate_on_submit():
        alert = Alert(
            message=form.message.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            is_active=False,  # Will be activated by background task
            created_by=current_user.id,
            color_theme=(form.color_theme.data or default_color).lower()
        )
        # Normalize activation against configured app timezone wall-clock
        now = local_now().replace(tzinfo=None)

        # If no start_time, activate immediately
        if not alert.start_time:
            alert.start_time = now
            alert.is_active = now <= alert.end_time
        else:
            alert.is_active = (alert.start_time <= now <= alert.end_time)
        
        db.session.add(alert)
        db.session.commit()
        emit_alert_update(alert.id)
        flash('Alert created successfully!', 'success')
        return redirect(url_for('main.alerts'))
    flash('Error creating alert.', 'error')
    return redirect(url_for('main.alerts'))


@bp.route('/alerts/<int:alert_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_alert(alert_id):
    """Edit an existing alert"""
    alert = Alert.query.get_or_404(alert_id)
    
    form = AlertForm(obj=alert)
    config = ScrapeConfig.query.first()
    default_color = config.get_default_alert_color() if config else 'danger'
    if request.method == 'GET' and not form.color_theme.data:
        form.color_theme.data = alert.color_theme or default_color
    
    if form.validate_on_submit():
        alert.message = form.message.data
        alert.start_time = form.start_time.data
        alert.end_time = form.end_time.data
        alert.color_theme = (form.color_theme.data or default_color).lower()
        
        now = local_now().replace(tzinfo=None)

        # Recalculate is_active status
        if not alert.start_time:
            alert.start_time = now
            alert.is_active = now <= alert.end_time
        else:
            alert.is_active = (alert.start_time <= now <= alert.end_time)
        
        db.session.commit()
        emit_alert_update(alert.id)
        flash('Alert updated successfully!', 'success')
        return redirect(url_for('main.alerts'))
    
    return render_template('edit_alert.html', alert=alert, form=form)


@bp.route('/alerts/<int:alert_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_alert(alert_id):
    """Delete an alert"""
    alert = Alert.query.get_or_404(alert_id)
    
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
    form.equipment_scrape_interval_hours.data = str(
        getattr(config, 'equipment_scrape_interval_hours', None) or 24
    )
    form.default_alert_color.data = config.get_default_alert_color()
    form.alerts_font_size.data = config.get_alert_font_size()
    form.app_timezone.data = config.get_app_timezone()
    form.gear_list_type_ids.data = config.gear_list_type_ids or '11'
    form.gear_list_statuses.data = config.gear_list_statuses or 'Active'
    form.allow_out_of_hydro_fills.data = config.get_allow_out_of_hydro_fills()

    selected_type_ids = set(config.get_gear_list_type_ids())
    gear_type_rows = (
        db.session.query(Equipment.geartypeid, func.max(Equipment.geartype))
        .filter(Equipment.geartypeid.isnot(None))
        .group_by(Equipment.geartypeid)
        .order_by(Equipment.geartypeid.asc())
        .all()
    )

    gear_types = []
    seen_ids = set()
    for geartypeid, geartype in gear_type_rows:
        if geartypeid is None:
            continue
        seen_ids.add(int(geartypeid))
        gear_types.append({
            'id': int(geartypeid),
            'name': (geartype or 'Unknown Type').strip() or 'Unknown Type',
            'selected': int(geartypeid) in selected_type_ids,
        })

    # Keep any configured IDs visible even if equipment table does not currently include them.
    missing_selected_ids = sorted(selected_type_ids - seen_ids)
    for type_id in missing_selected_ids:
        gear_types.append({
            'id': int(type_id),
            'name': 'Unknown Type (not in equipment table)',
            'selected': True,
        })

    selected_statuses = config.get_gear_list_statuses()
    selected_statuses_lower = {s.lower() for s in selected_statuses}
    status_rows = (
        db.session.query(func.trim(Equipment.status))
        .filter(Equipment.status.isnot(None))
        .filter(func.trim(Equipment.status) != '')
        .group_by(func.trim(Equipment.status))
        .order_by(func.trim(Equipment.status).asc())
        .all()
    )
    gear_statuses = []
    seen_statuses_lower = set()
    for (status_value,) in status_rows:
        label = (status_value or '').strip()
        if not label:
            continue
        key = label.lower()
        seen_statuses_lower.add(key)
        gear_statuses.append({
            'label': label,
            'selected': key in selected_statuses_lower,
        })

    missing_selected_statuses = [
        s for s in selected_statuses if s.lower() not in seen_statuses_lower
    ]
    for status in missing_selected_statuses:
        gear_statuses.append({
            'label': status,
            'selected': True,
            'missing': True,
        })

    return render_template(
        'settings.html',
        form=form,
        config=config,
        gear_types=gear_types,
        gear_statuses=gear_statuses,
        fill_sites=FillSite.query.order_by(FillSite.name.asc()).all(),
        fill_boards=FillBoard.query.order_by(FillBoard.name.asc()).all(),
        fill_site_form=FillSiteForm(),
        fill_board_form=_fill_board_form(),
        active_settings_tab=request.args.get('tab', 'pstrax'),
    )


def _fill_board_form(obj=None):
    form = FillBoardForm(obj=obj)
    sites = FillSite.query.order_by(FillSite.name.asc()).all()
    form.fill_site_id.choices = [(s.id, s.name) for s in sites]
    return form


@bp.route('/settings/fill-sites/create', methods=['POST'])
@login_required
@admin_required
def create_fill_site():
    form = FillSiteForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        if FillSite.query.filter(func.lower(FillSite.name) == name.lower()).first():
            flash(f'Fill site "{name}" already exists.', 'error')
            return redirect(url_for('main.settings', tab='fills'))
        db.session.add(FillSite(name=name))
        db.session.commit()
        flash(f'Fill site "{name}" created.', 'success')
    else:
        flash('Error creating fill site.', 'error')
    return redirect(url_for('main.settings', tab='fills'))


@bp.route('/settings/fill-sites/<int:site_id>/update', methods=['POST'])
@login_required
@admin_required
def update_fill_site(site_id):
    site = FillSite.query.get_or_404(site_id)
    form = FillSiteForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        conflict = (
            FillSite.query
            .filter(func.lower(FillSite.name) == name.lower(), FillSite.id != site.id)
            .first()
        )
        if conflict:
            flash(f'Fill site "{name}" already exists.', 'error')
            return redirect(url_for('main.settings', tab='fills'))
        site.name = name
        db.session.commit()
        flash(f'Fill site updated to "{name}".', 'success')
    else:
        flash('Error updating fill site.', 'error')
    return redirect(url_for('main.settings', tab='fills'))


@bp.route('/settings/fill-sites/<int:site_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_fill_site(site_id):
    site = FillSite.query.get_or_404(site_id)
    if site.boards.count() > 0:
        flash(
            f'Cannot delete fill site "{site.name}" while fill boards still use it.',
            'error',
        )
        return redirect(url_for('main.settings', tab='fills'))
    name = site.name
    db.session.delete(site)
    db.session.commit()
    flash(f'Fill site "{name}" deleted.', 'success')
    return redirect(url_for('main.settings', tab='fills'))


@bp.route('/settings/fill-boards/create', methods=['POST'])
@login_required
@admin_required
def create_fill_board():
    form = _fill_board_form()
    if not form.fill_site_id.choices:
        flash('Create a fill site before adding a fill board.', 'error')
        return redirect(url_for('main.settings', tab='fills'))
    if form.validate_on_submit():
        board = FillBoard(
            name=form.name.data.strip(),
            fill_site_id=form.fill_site_id.data,
            key=FillBoard.generate_key(),
        )
        db.session.add(board)
        db.session.commit()
        flash(f'Fill board "{board.name}" created.', 'success')
    else:
        flash('Error creating fill board.', 'error')
    return redirect(url_for('main.settings', tab='fills'))


@bp.route('/settings/fill-boards/<int:board_id>/update', methods=['POST'])
@login_required
@admin_required
def update_fill_board(board_id):
    board = FillBoard.query.get_or_404(board_id)
    form = _fill_board_form()
    if form.validate_on_submit():
        board.name = form.name.data.strip()
        board.fill_site_id = form.fill_site_id.data
        db.session.commit()
        flash(f'Fill board "{board.name}" updated.', 'success')
    else:
        flash('Error updating fill board.', 'error')
    return redirect(url_for('main.settings', tab='fills'))


@bp.route('/settings/fill-boards/<int:board_id>/regenerate-key', methods=['POST'])
@login_required
@admin_required
def regenerate_fill_board_key(board_id):
    board = FillBoard.query.get_or_404(board_id)
    board.regenerate_key()
    db.session.commit()
    flash(f'Key regenerated for fill board "{board.name}".', 'success')
    return redirect(url_for('main.settings', tab='fills'))


@bp.route('/settings/fill-boards/<int:board_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_fill_board(board_id):
    board = FillBoard.query.get_or_404(board_id)
    name = board.name
    CylinderFillLog.query.filter_by(fill_board_id=board.id).update(
        {CylinderFillLog.fill_board_id: None},
        synchronize_session=False,
    )
    db.session.delete(board)
    db.session.commit()
    flash(f'Fill board "{name}" deleted.', 'success')
    return redirect(url_for('main.settings', tab='fills'))


@bp.route('/settings/update', methods=['POST'])
@login_required
@admin_required
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
        if form.equipment_scrape_interval_hours.data:
            try:
                h = int(form.equipment_scrape_interval_hours.data)
                if h < 1:
                    raise ValueError('min 1')
                config.equipment_scrape_interval_hours = h
            except ValueError:
                flash('Invalid equipment sync interval (use whole hours, minimum 1).', 'error')
                return redirect(url_for('main.settings'))
        config.default_alert_color = (form.default_alert_color.data or 'danger').lower()
        if form.alerts_font_size.data:
            config.alerts_font_size = int(form.alerts_font_size.data)
        else:
            config.alerts_font_size = 16
        config.app_timezone = normalize_timezone_name(
            form.app_timezone.data or 'America/New_York'
        )
        config.set_gear_list_type_ids(form.gear_list_type_ids.data)
        config.set_gear_list_statuses(form.gear_list_statuses.data)
        config.allow_out_of_hydro_fills = bool(form.allow_out_of_hydro_fills.data)
        
        db.session.commit()
        
        update_scrape_schedule()
        update_equipment_scrape_schedule()
        
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('main.settings'))
    
    flash('Error updating settings.', 'error')
    return redirect(url_for('main.settings'))


@bp.app_context_processor
def inject_alert_settings():
    config = ScrapeConfig.query.first()
    default_color = 'danger'
    font_size = 16
    timezone_name = 'America/New_York'
    if config:
        default_color = config.get_default_alert_color()
        font_size = config.get_alert_font_size()
        timezone_name = config.get_app_timezone()
    return {
        'default_alert_color': default_color,
        'alerts_font_size_px': font_size,
        'app_timezone': timezone_name,
    }


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


@bp.route('/fills')
@bp.route('/fills/<string:board_key>')
def public_fills(board_key=None):
    """Public iPad-friendly page to log SCBA cylinder fills."""
    fill_board = None
    fill_site_name = None
    if board_key:
        fill_board = FillBoard.query.filter_by(key=board_key).first_or_404()
        fill_site_name = fill_board.fill_site.name if fill_board.fill_site else None

    cylinders = (
        Equipment.query.filter(Equipment.geartypeid == 11)
        .order_by(Equipment.internalid.asc())
        .all()
    )
    # Keep payload small (table is ~hundreds of rows). Send only what UI needs.
    data = [
        {
            "gearid": c.gearid,
            "internalid": (c.internalid or "").strip(),
            "serial": c.serial or "",
            "status": c.status or "",
            "description": c.description or "",
            "next_hydro": c.next_hydro or "",
        }
        for c in cylinders
        if c.internalid
    ]
    page_title = (
        f"SCBA Cylinder Fill Log for {fill_site_name}"
        if fill_site_name
        else "SCBA Cylinder Fill Log"
    )
    config = ScrapeConfig.query.first()
    allow_out_of_hydro_fills = (
        config.get_allow_out_of_hydro_fills() if config else False
    )
    return render_template(
        'fills_public.html',
        cylinders_json=json.dumps(data),
        page_title=page_title,
        fill_site_name=fill_site_name,
        board_key=fill_board.key if fill_board else None,
        allow_out_of_hydro_fills=allow_out_of_hydro_fills,
    )


@bp.route('/api/fills/log', methods=['POST'])
def public_log_fills():
    """Public endpoint: create fill log rows for selected cylinders."""
    payload = request.get_json(silent=True) or {}
    internalids = payload.get("internalids") or []
    if not isinstance(internalids, list):
        return jsonify({"success": False, "error": "internalids must be a list"}), 400

    internalids = [str(x).strip() for x in internalids if str(x).strip()]
    if not internalids:
        return jsonify({"success": False, "error": "No cylinders provided"}), 400

    board_key = (payload.get("board_key") or "").strip() or None
    fill_board = None
    fill_site = None
    fill_site_name = None
    if board_key:
        fill_board = FillBoard.query.filter_by(key=board_key).first()
        if not fill_board:
            return jsonify({"success": False, "error": "Invalid fill board key"}), 400
        fill_site = fill_board.fill_site
        fill_site_name = fill_site.name if fill_site else None

    badge_raw = str(payload.get("badge_number") or "").strip()
    badge_digits = "".join(ch for ch in badge_raw if ch.isdigit())[:4]
    if len(badge_digits) != 4:
        return jsonify({
            "success": False,
            "error": "Badge number is required and must be exactly 4 digits",
        }), 400
    badge_number = badge_digits.zfill(4)
    fill_notes = f"Filled by {badge_number}"

    batch_id = str(uuid.uuid4())
    now = datetime.utcnow()

    # Resolve internalid -> equipment
    equipment_rows = (
        Equipment.query.filter(Equipment.internalid.in_(internalids)).all()
    )
    by_internal = {str(e.internalid).strip(): e for e in equipment_rows if e.internalid}

    config = ScrapeConfig.query.first()
    allow_out_of_hydro = (
        config.get_allow_out_of_hydro_fills() if config else False
    )
    if not allow_out_of_hydro:
        overdue_ids = [
            iid
            for iid in internalids
            if _is_hydro_overdue((by_internal.get(iid).next_hydro if by_internal.get(iid) else None))
        ]
        if overdue_ids:
            return jsonify({
                "success": False,
                "error": (
                    "Filling cylinders that are out of hydro is disabled. "
                    f"Overdue: {', '.join(overdue_ids)}"
                ),
            }), 400

    created = 0
    gear_ids = []
    for iid in internalids:
        eq = by_internal.get(iid)
        if eq and eq.gearid is not None:
            gear_ids.append(eq.gearid)
        db.session.add(
            CylinderFillLog(
                batch_id=batch_id,
                gearid=eq.gearid if eq else None,
                internalid=iid,
                fill_site_id=fill_site.id if fill_site else None,
                fill_board_id=fill_board.id if fill_board else None,
                fill_site_name=fill_site_name,
                filled_at=now,
                created_at=now,
            )
        )
        created += 1

    db.session.commit()

    pstrax_result = None
    if board_key and fill_site_name:
        unique_gear_ids = []
        seen = set()
        for gid in gear_ids:
            if gid in seen:
                continue
            seen.add(gid)
            unique_gear_ids.append(gid)
        if not unique_gear_ids:
            pstrax_result = {
                'success': False,
                'error': 'No gear IDs found for submitted cylinders',
            }
        else:
            try:
                pstrax_result = perform_pstrax_batch_air_fill(
                    unique_gear_ids, fill_site_name, notes=fill_notes
                )
            except Exception as e:
                pstrax_result = {
                    'success': False,
                    'error': f'Unexpected PSTrax sync error: {e}',
                }

    return jsonify({
        "success": True,
        "batch_id": batch_id,
        "created": created,
        "filled_at": now.isoformat(),
        "fill_site": fill_site_name,
        "badge_number": badge_number,
        "pstrax": pstrax_result,
    })


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
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.priority.asc(), Task.created_at.desc()).all()
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
    """Gear list from DB (refreshed by equipment scraper on its own schedule)."""
    try:
        config = ScrapeConfig.query.first()
        type_ids = config.get_gear_list_type_ids() if config else [11]
        statuses = config.get_gear_list_statuses() if config else ['Active']
        status_keys = [s.lower() for s in statuses if str(s).strip()]
        rows = (
            Equipment.query
            .filter(Equipment.geartypeid.in_(type_ids))
            .filter(func.lower(func.trim(Equipment.status)).in_(status_keys))
            .order_by(Equipment.gearid)
            .all()
        )
        data = [r.to_api_row() for r in rows]
        return jsonify({
            'data': {'data': data, 'not_found': []},
            'status': 'success',
            'count': len(data),
            'gear_type_ids': type_ids,
            'gear_statuses': statuses,
        })
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


@bp.route('/api/scrape/equipment-trigger', methods=['POST'])
@login_required
@admin_required
def trigger_equipment_scrape():
    """Manually run PSTrax equipment sync (replaces equipment table)."""
    try:
        run_equipment_scrape()
        return jsonify({'success': True, 'message': 'Equipment sync completed'})
    except Exception as e:
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

