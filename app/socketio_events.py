from flask import session
from flask_login import current_user
from flask_socketio import emit, disconnect
from app import socketio, db
from app.models import Task, Alert, ScrapeData


@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    if not current_user.is_authenticated:
        disconnect()
        return False
    print(f'User {current_user.username} connected')
    emit('connected', {'message': 'Connected to server'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    if current_user.is_authenticated:
        print(f'User {current_user.username} disconnected')


def emit_task_update(task_id=None, action='updated'):
    """Emit task update event to all clients"""
    if task_id:
        task = Task.query.get(task_id)
        if task:
            data = task.to_dict()
            data['action'] = action
            socketio.emit('task_updated', data, namespace='/')
    else:
        socketio.emit('task_updated', {'action': 'refresh'}, namespace='/')


def emit_scrape_update(data=None):
    """Emit scrape data update event to all clients"""
    socketio.emit('scrape_update', data or {'action': 'refresh'}, namespace='/')


def emit_alert_update(alert_id=None):
    """Emit alert update event to all clients"""
    if alert_id:
        alert = Alert.query.get(alert_id)
        if alert:
            socketio.emit('alert_update', alert.to_dict(), namespace='/')
    else:
        # Send active alert if any
        active_alert = Alert.query.filter_by(is_active=True).first()
        if active_alert:
            socketio.emit('alert_update', active_alert.to_dict(), namespace='/')
        else:
            socketio.emit('alert_update', {'is_active': False}, namespace='/')

