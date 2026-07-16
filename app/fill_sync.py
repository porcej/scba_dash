"""Background PSTrax sync for pending cylinder fill logs."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta

from flask import has_app_context

from app import db
from app.models import CylinderFillLog
from app.scraper import perform_pstrax_batch_air_fill

# Reclaim rows left in "syncing" if a worker died mid-sync.
STALE_SYNCING_MINUTES = 5


def _app_ref():
    from app import tasks as task_module

    return getattr(task_module, "_app", None)


def enqueue_fill_batch_sync(batch_id):
    """Schedule an immediate background sync for a fill batch."""
    if not batch_id:
        return
    app = _app_ref()
    if not app:
        print(f"Fill sync enqueue skipped (no app): batch_id={batch_id}")
        return

    from app.tasks import scheduler

    try:
        if not scheduler.running:
            _start_thread_sync(app, batch_id)
            return
        scheduler.add_job(
            func=sync_fill_batch,
            args=[batch_id],
            id=f"fill_sync_{batch_id}",
            name=f"PSTrax fill sync {batch_id}",
            replace_existing=True,
            next_run_time=datetime.utcnow(),
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
    except Exception as e:
        print(f"Failed to schedule fill sync for {batch_id}: {e}")
        _start_thread_sync(app, batch_id)


def _start_thread_sync(app, batch_id):
    import threading

    def _run():
        with app.app_context():
            sync_fill_batch(batch_id)

    threading.Thread(target=_run, name=f"fill-sync-{batch_id}", daemon=True).start()


def sync_pending_fill_batches():
    """Periodic retry for pending/failed fill batches (and cleanup synced leftovers)."""
    app = _app_ref()
    if not app:
        return
    try:
        with app.app_context():
            deleted = CylinderFillLog.query.filter_by(
                pstrax_status=CylinderFillLog.STATUS_SYNCED
            ).delete(synchronize_session=False)
            if deleted:
                db.session.commit()
                print(f"Deleted {deleted} leftover synced fill log row(s)")

            stale_before = datetime.utcnow() - timedelta(minutes=STALE_SYNCING_MINUTES)
            stale = CylinderFillLog.query.filter(
                CylinderFillLog.pstrax_status == CylinderFillLog.STATUS_SYNCING,
                CylinderFillLog.last_sync_attempt_at.isnot(None),
                CylinderFillLog.last_sync_attempt_at < stale_before,
            ).update(
                {
                    CylinderFillLog.pstrax_status: CylinderFillLog.STATUS_FAILED,
                    CylinderFillLog.last_sync_error: "Sync timed out; will retry",
                },
                synchronize_session=False,
            )
            if stale:
                db.session.commit()
                print(f"Reclaimed {stale} stale syncing fill log row(s)")

            batch_ids = [
                row[0]
                for row in (
                    db.session.query(CylinderFillLog.batch_id)
                    .filter(
                        CylinderFillLog.pstrax_status.in_(
                            [
                                CylinderFillLog.STATUS_PENDING,
                                CylinderFillLog.STATUS_FAILED,
                            ]
                        )
                    )
                    .distinct()
                    .all()
                )
            ]
            for batch_id in batch_ids:
                sync_fill_batch(batch_id)
    except Exception as e:
        print(f"Error in sync_pending_fill_batches: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass


def sync_fill_batch(batch_id):
    """Sync one fill batch to PSTrax; delete local rows on success."""
    if not batch_id:
        return

    app = _app_ref()

    def _do_sync():
        rows = (
            CylinderFillLog.query.filter_by(batch_id=batch_id)
            .order_by(CylinderFillLog.id.asc())
            .all()
        )
        if not rows:
            return

        if all(r.pstrax_status == CylinderFillLog.STATUS_SYNCED for r in rows):
            CylinderFillLog.query.filter_by(batch_id=batch_id).delete(
                synchronize_session=False
            )
            db.session.commit()
            return

        if all(r.pstrax_status == CylinderFillLog.STATUS_LOCAL_ONLY for r in rows):
            return

        fill_site_name = next(
            (r.fill_site_name for r in rows if (r.fill_site_name or "").strip()),
            None,
        )
        if not fill_site_name:
            CylinderFillLog.query.filter_by(batch_id=batch_id).update(
                {
                    CylinderFillLog.pstrax_status: CylinderFillLog.STATUS_LOCAL_ONLY,
                    CylinderFillLog.last_sync_error: None,
                },
                synchronize_session=False,
            )
            db.session.commit()
            return

        now = datetime.utcnow()
        claimed = CylinderFillLog.query.filter(
            CylinderFillLog.batch_id == batch_id,
            CylinderFillLog.pstrax_status.in_(
                [
                    CylinderFillLog.STATUS_PENDING,
                    CylinderFillLog.STATUS_FAILED,
                ]
            ),
        ).update(
            {
                CylinderFillLog.pstrax_status: CylinderFillLog.STATUS_SYNCING,
                CylinderFillLog.last_sync_attempt_at: now,
                CylinderFillLog.sync_attempts: CylinderFillLog.sync_attempts + 1,
            },
            synchronize_session=False,
        )
        if not claimed:
            stale_before = now - timedelta(minutes=STALE_SYNCING_MINUTES)
            claimed = CylinderFillLog.query.filter(
                CylinderFillLog.batch_id == batch_id,
                CylinderFillLog.pstrax_status == CylinderFillLog.STATUS_SYNCING,
                CylinderFillLog.last_sync_attempt_at.isnot(None),
                CylinderFillLog.last_sync_attempt_at < stale_before,
            ).update(
                {
                    CylinderFillLog.pstrax_status: CylinderFillLog.STATUS_SYNCING,
                    CylinderFillLog.last_sync_attempt_at: now,
                    CylinderFillLog.sync_attempts: CylinderFillLog.sync_attempts + 1,
                },
                synchronize_session=False,
            )
        db.session.commit()
        if not claimed:
            return

        rows = (
            CylinderFillLog.query.filter_by(batch_id=batch_id)
            .order_by(CylinderFillLog.id.asc())
            .all()
        )
        gear_ids = []
        seen = set()
        for row in rows:
            if row.gearid is None or row.gearid in seen:
                continue
            seen.add(row.gearid)
            gear_ids.append(row.gearid)

        badge = next((r.badge_number for r in rows if r.badge_number), None)
        notes = f"Filled by {badge}" if badge else None

        if not gear_ids:
            _mark_batch_failed(batch_id, "No gear IDs found for submitted cylinders")
            return

        try:
            result = perform_pstrax_batch_air_fill(
                gear_ids, fill_site_name, notes=notes
            )
        except Exception as e:
            _mark_batch_failed(batch_id, f"Unexpected PSTrax sync error: {e}")
            return

        if result and result.get("success"):
            CylinderFillLog.query.filter_by(batch_id=batch_id).update(
                {
                    CylinderFillLog.pstrax_status: CylinderFillLog.STATUS_SYNCED,
                    CylinderFillLog.last_sync_error: None,
                },
                synchronize_session=False,
            )
            db.session.commit()
            deleted = CylinderFillLog.query.filter_by(batch_id=batch_id).delete(
                synchronize_session=False
            )
            db.session.commit()
            print(
                f"PSTrax fill sync ok batch={batch_id} "
                f"site={fill_site_name} deleted_rows={deleted}"
            )
            return

        error = (result or {}).get("error") or "Unknown PSTrax sync failure"
        _mark_batch_failed(batch_id, error)

    try:
        if has_app_context():
            _do_sync()
        elif app:
            with app.app_context():
                _do_sync()
        else:
            print(f"Fill sync skipped (no app context): batch_id={batch_id}")
    except Exception as e:
        print(f"Error syncing fill batch {batch_id}: {e}")
        try:
            ctx = nullcontext() if has_app_context() else (app.app_context() if app else None)
            if ctx is None:
                return
            with ctx:
                db.session.rollback()
                _mark_batch_failed(batch_id, str(e))
        except Exception:
            pass


def _mark_batch_failed(batch_id, error):
    CylinderFillLog.query.filter_by(batch_id=batch_id).update(
        {
            CylinderFillLog.pstrax_status: CylinderFillLog.STATUS_FAILED,
            CylinderFillLog.last_sync_error: (error or "")[:2000],
            CylinderFillLog.last_sync_attempt_at: datetime.utcnow(),
        },
        synchronize_session=False,
    )
    db.session.commit()
    print(f"PSTrax fill sync failed batch={batch_id}: {error}")
