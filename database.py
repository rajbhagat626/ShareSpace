import sqlite3
import os
from datetime import datetime

DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sharespace.db')

def get_db():
    """Establish and return an SQLite connection with Row mapping and foreign keys enabled."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Read and execute schema.sql to initialize all database tables."""
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_sql = f.read()
    
    with get_db() as conn:
        conn.executescript(schema_sql)
        conn.commit()
    print("Database initialized successfully with complete schema.")

def query_db(query, args=(), one=False):
    """Convenience helper to run SELECT queries and return dictionaries."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(query, args)
        rows = cur.fetchall()
        cur.close()
        return (rows[0] if rows else None) if one else rows
    finally:
        conn.close()

def execute_db(query, args=()):
    """Convenience helper to run INSERT, UPDATE, or DELETE queries and return the last row ID."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(query, args)
        conn.commit()
        last_id = cur.lastrowid
        cur.close()
        return last_id
    finally:
        conn.close()

def log_activity(user_id, action, details, booking_id=None, resource_id=None):
    """
    Central audit log recorder. Records every state transition across the application.
    Actions: 'RESOURCE_CREATED', 'REQUESTED', 'APPROVED', 'REJECTED', 'CHECKED_IN',
             'RETURNED', 'INCIDENT_LOGGED', 'INCIDENT_RESOLVED', 'TRAINING_COMPLETED',
             'WAITLIST_JOINED', 'WAITLIST_PROMOTED', 'CANCELLED'
    """
    execute_db(
        """
        INSERT INTO activity_logs (booking_id, resource_id, user_id, action, details)
        VALUES (?, ?, ?, ?, ?)
        """,
        (booking_id, resource_id, user_id, action, details)
    )

def create_notification(user_id, title, message, link=None):
    """Add an in-app notification for a user."""
    execute_db(
        """
        INSERT INTO notifications (user_id, title, message, link, is_read)
        VALUES (?, ?, ?, ?, 0)
        """,
        (user_id, title, message, link)
    )

def check_eligibility(user_id, resource_id):
    """
    Check if a user is certified/trained for a resource.
    Returns (is_eligible: bool, cert_name: str or None)
    """
    resource = query_db(
        """
        SELECT r.id, r.required_certification_id, c.name as cert_name
        FROM resources r
        LEFT JOIN certifications c ON r.required_certification_id = c.id
        WHERE r.id = ?
        """,
        (resource_id,),
        one=True
    )
    if not resource or not resource['required_certification_id']:
        return True, None

    # Check if user holds this certification
    user_cert = query_db(
        """
        SELECT id FROM user_certifications
        WHERE user_id = ? AND certification_id = ?
        """,
        (user_id, resource['required_certification_id']),
        one=True
    )
    return (user_cert is not None), resource['cert_name']

def check_fair_usage(user_id, requested_days, resource_id):
    """
    Enforce fair usage limits:
    1. Maximum consecutive duration per booking for this resource (e.g. max_days, default 5).
    2. Maximum concurrent active/pending bookings per user (default max 3).
    Returns (is_allowed: bool, reason: str or None)
    """
    resource = query_db("SELECT max_days, title FROM resources WHERE id = ?", (resource_id,), one=True)
    max_days = resource['max_days'] if resource and resource['max_days'] else 5

    if requested_days > max_days:
        return False, f"Fair usage limit exceeded: Maximum allowed duration for '{resource['title']}' is {max_days} day(s) per booking."

    # Count user's current pending + approved + active bookings
    active_count_row = query_db(
        """
        SELECT COUNT(*) as count FROM bookings
        WHERE user_id = ? AND status IN ('pending', 'approved', 'active')
        """,
        (user_id,),
        one=True
    )
    active_count = active_count_row['count'] if active_count_row else 0
    MAX_CONCURRENT_BOOKINGS = 3
    if active_count >= MAX_CONCURRENT_BOOKINGS:
        return False, f"Fair usage limit exceeded: You currently have {active_count} active/pending reservations. The maximum allowed is {MAX_CONCURRENT_BOOKINGS} at any one time."

    return True, None

def check_scheduling_conflict(resource_id, start_date, end_date, exclude_booking_id=None):
    """
    Check for date collisions with existing 'approved' or 'active' bookings.
    Collision condition: NOT (new_end < existing_start OR new_start > existing_end)
    which simplifies to: existing_start <= new_end AND existing_end >= new_start
    """
    query = """
        SELECT b.id, b.start_date, b.end_date, b.status, u.name as borrower_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        WHERE b.resource_id = ?
          AND b.status IN ('approved', 'active')
          AND b.start_date <= ?
          AND b.end_date >= ?
    """
    args = [resource_id, end_date, start_date]
    if exclude_booking_id:
        query += " AND b.id != ?"
        args.append(exclude_booking_id)

    conflicts = query_db(query, args)
    return (len(conflicts) > 0), conflicts

def promote_waitlist_if_any(resource_id):
    """
    Checks the waiting list for this resource.
    If someone is waiting, notify the next person in line.
    """
    next_waiter = query_db(
        """
        SELECT w.id, w.user_id, w.start_date, w.end_date, r.title as resource_title, u.name as user_name
        FROM waitlists w
        JOIN resources r ON w.resource_id = r.id
        JOIN users u ON w.user_id = u.id
        WHERE w.resource_id = ? AND w.status = 'waiting'
        ORDER BY w.created_at ASC
        LIMIT 1
        """,
        (resource_id,),
        one=True
    )
    if next_waiter:
        # Update waitlist status to 'notified'
        execute_db("UPDATE waitlists SET status = 'notified' WHERE id = ?", (next_waiter['id'],))
        
        # Send in-app notification
        create_notification(
            user_id=next_waiter['user_id'],
            title="Waitlist Spot Available!",
            message=f"A spot has opened up for '{next_waiter['resource_title']}'. Visit your reservations or the resource page to finalize your booking.",
            link=f"/resource/{resource_id}"
        )
        
        # Log to activity audit trail
        log_activity(
            user_id=next_waiter['user_id'],
            action="WAITLIST_PROMOTED",
            details=f"{next_waiter['user_name']} was promoted from the waitlist for '{next_waiter['resource_title']}'.",
            resource_id=resource_id
        )
        return next_waiter
    return None

def ensure_database_initialized():
    """
    Ensure the SQLite database exists, schema is initialized, and demo data is seeded.
    Vital for Render free instances with ephemeral filesystems: whenever an instance
    boots or wakes from idle, this guarantees the app and sample data are ready.
    """
    db_path = DATABASE_PATH
    need_seed = False
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        need_seed = True
    else:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM users")
            row = cur.fetchone()
            cur.close()
            conn.close()
            if not row or row['count'] == 0:
                need_seed = True
        except Exception:
            need_seed = True

    if need_seed:
        print("[*] Initializing database and seeding demo data for Render/production environment...")
        from seed import seed_database
        seed_database()

if __name__ == '__main__':
    init_db()
