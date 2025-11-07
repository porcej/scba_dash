from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from app import db
from app.models import Alert, ScrapeConfig
from app.scraper import perform_scrape
from app.socketio_events import emit_alert_update
import atexit

# Global scheduler
scheduler = BackgroundScheduler()

# Global app reference for background tasks
_app = None


def check_alerts():
    """Background task to check and update alert status"""
    global _app
    if not _app:
        return
    try:
        with _app.app_context():
            now = datetime.now()
            
            # Get all alerts
            alerts = Alert.query.all()
            
            for alert in alerts:
                was_active = alert.is_active
                
                # Determine if alert should be active
                start_time = alert.start_time or alert.created_at
                end_time = alert.end_time
                
                if start_time <= now <= end_time:
                    alert.is_active = True
                else:
                    alert.is_active = False
                
                # Emit update if status changed
                if was_active != alert.is_active:
                    db.session.commit()
                    emit_alert_update(alert.id)
                    print(f"Alert {alert.id} status changed: {'active' if alert.is_active else 'inactive'}")
    except Exception as e:
        print(f"Error checking alerts: {e}")


def scheduled_scrape():
    """Background task for scheduled scraping"""
    global _app
    if not _app:
        return
    try:
        with _app.app_context():
            perform_scrape()
    except Exception as e:
        print(f"Error in scheduled scrape: {e}")


def start_background_tasks(app):
    """Start all background tasks"""
    global _app
    _app = app
    
    with app.app_context():
        # Schedule alert checking every minute
        scheduler.add_job(
            func=check_alerts,
            trigger=IntervalTrigger(minutes=1),
            id='check_alerts',
            name='Check alert status',
            replace_existing=True
        )
        
        # Schedule scraping based on configured interval
        config = ScrapeConfig.query.first()
        interval_minutes = config.scrape_interval if config else 15
        
        scheduler.add_job(
            func=scheduled_scrape,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id='scheduled_scrape',
            name='Scheduled scraping',
            replace_existing=True
        )
        
        scheduler.start()
        print("Background tasks started")
        
        # Shut down scheduler on app exit
        atexit.register(lambda: scheduler.shutdown())


def update_scrape_schedule():
    """Update scraping schedule when interval changes"""
    global _app
    if not _app:
        return
    try:
        with _app.app_context():
            config = ScrapeConfig.query.first()
            if not config:
                return
            
            # Remove existing job
            try:
                scheduler.remove_job('scheduled_scrape')
            except:
                pass
            
            # Add new job with updated interval
            scheduler.add_job(
                func=scheduled_scrape,
                trigger=IntervalTrigger(minutes=config.scrape_interval),
                id='scheduled_scrape',
                name='Scheduled scraping',
                replace_existing=True
            )
    except Exception as e:
        print(f"Error updating scrape schedule: {e}")

