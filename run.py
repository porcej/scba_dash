from app import create_app, db, socketio

app = create_app()

# Initialize database and start background tasks
with app.app_context():
    db.create_all()
    from app.tasks import start_background_tasks
    start_background_tasks(app)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8000)

