import os
from datetime import datetime, date
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, g
)
from werkzeug.security import generate_password_hash, check_password_hash

from database import (
    get_db, query_db, execute_db, log_activity, create_notification,
    check_eligibility, check_fair_usage, check_scheduling_conflict,
    promote_waitlist_if_any, init_db
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sharespace-solo-hackathon-2026-secret-key')

# ---------------------------------------------------------
# Request Hooks & Context Processors
# ---------------------------------------------------------
@app.before_request
def load_current_user():
    # If no session exists yet, default to user #2 (Sam Borrower) for instant hackathon exploration
    if 'user_id' not in session:
        session['user_id'] = 2

    user_id = session.get('user_id')
    g.user = None
    g.unread_notifs_count = 0
    g.active_bookings_count = 0
    g.pending_requests_count = 0
    g.open_incidents_count = 0

    if user_id:
        g.user = query_db("SELECT id, name, email, role FROM users WHERE id = ?", (user_id,), one=True)
        if g.user:
            # Unread notifications
            notif_row = query_db(
                "SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND is_read = 0",
                (user_id,),
                one=True
            )
            g.unread_notifs_count = notif_row['count'] if notif_row else 0

            # Active bookings for borrower
            active_row = query_db(
                "SELECT COUNT(*) as count FROM bookings WHERE user_id = ? AND status IN ('approved', 'active')",
                (user_id,),
                one=True
            )
            g.active_bookings_count = active_row['count'] if active_row else 0

            # Pending requests for owner / admin
            if g.user['role'] == 'admin':
                pending_row = query_db("SELECT COUNT(*) as count FROM bookings WHERE status = 'pending'", one=True)
            else:
                pending_row = query_db(
                    """
                    SELECT COUNT(*) as count FROM bookings b
                    JOIN resources r ON b.resource_id = r.id
                    WHERE r.owner_id = ? AND b.status = 'pending'
                    """,
                    (user_id,),
                    one=True
                )
            g.pending_requests_count = pending_row['count'] if pending_row else 0

            # Open incidents count
            inc_row = query_db("SELECT COUNT(*) as count FROM incidents WHERE status != 'resolved'", one=True)
            g.open_incidents_count = inc_row['count'] if inc_row else 0


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------
# Persona Switcher & Authentication Routes
# ---------------------------------------------------------
@app.route('/switch-user/<int:user_id>')
def switch_user(user_id):
    """1-Click Hackathon Persona Switcher (Alex Owner, Sam Borrower, Jordan Admin)."""
    user = query_db("SELECT id, name, role FROM users WHERE id = ?", (user_id,), one=True)
    if user:
        session['user_id'] = user['id']
        flash(f"Switched persona to {user['name']} ({user['role'].upper()}).", "info")
    else:
        flash("User persona not found.", "danger")
    
    referrer = request.referrer
    if referrer and ('login' not in referrer) and ('register' not in referrer):
        return redirect(referrer)
    return redirect(url_for('index'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = query_db("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid email or password. You can also use the 1-click persona buttons above.", "danger")

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', 'member')

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for('register'))

        existing = query_db("SELECT id FROM users WHERE email = ?", (email,), one=True)
        if existing:
            flash("An account with that email already exists.", "warning")
            return redirect(url_for('register'))

        pw_hash = generate_password_hash(password)
        new_id = execute_db(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name, email, pw_hash, role)
        )
        session['user_id'] = new_id
        log_activity(new_id, "USER_REGISTERED", f"{name} joined ShareSpace with role {role}.")
        flash("Registration successful! Welcome to ShareSpace.", "success")
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("You have been signed out.", "info")
    return redirect(url_for('index'))


# ---------------------------------------------------------
# Catalog & Resource Routes
# ---------------------------------------------------------
@app.route('/')
def index():
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    status = request.args.get('status', '').strip()

    sql = """
        SELECT r.*, u.name as owner_name, c.name as required_cert_name
        FROM resources r
        JOIN users u ON r.owner_id = u.id
        LEFT JOIN certifications c ON r.required_certification_id = c.id
        WHERE 1=1
    """
    args = []

    if query:
        sql += " AND (r.title LIKE ? OR r.description LIKE ? OR r.location LIKE ?)"
        pattern = f"%{query}%"
        args.extend([pattern, pattern, pattern])

    if category:
        sql += " AND r.category = ?"
        args.append(category)

    if status:
        sql += " AND r.status = ?"
        args.append(status)

    sql += " ORDER BY r.created_at DESC"
    raw_resources = query_db(sql, args)

    # Check certification eligibility for each item for current user
    resources = []
    user_id = g.user['id'] if g.user else None
    for r in raw_resources:
        item = dict(r)
        if user_id and item.get('required_certification_id'):
            eligible, _ = check_eligibility(user_id, item['id'])
            item['is_user_certified'] = eligible
        else:
            item['is_user_certified'] = True
        resources.append(item)

    # Aggregate stats for banner
    total_resources = query_db("SELECT COUNT(*) as count FROM resources", one=True)['count']
    available_resources = query_db("SELECT COUNT(*) as count FROM resources WHERE status = 'available'", one=True)['count']
    active_loans = query_db("SELECT COUNT(*) as count FROM bookings WHERE status = 'active'", one=True)['count']
    pending_requests = query_db("SELECT COUNT(*) as count FROM bookings WHERE status = 'pending'", one=True)['count']

    categories = [row['category'] for row in query_db("SELECT DISTINCT category FROM resources ORDER BY category")]

    return render_template(
        'index.html',
        resources=resources,
        categories=categories,
        query=query,
        selected_category=category,
        selected_status=status,
        stats={
            'total_resources': total_resources,
            'available_resources': available_resources,
            'active_loans': active_loans,
            'pending_requests': pending_requests
        }
    )


@app.route('/resource/<int:resource_id>')
def resource_detail(resource_id):
    resource = query_db(
        """
        SELECT r.*, u.name as owner_name, u.email as owner_email, c.name as required_cert_name
        FROM resources r
        JOIN users u ON r.owner_id = u.id
        LEFT JOIN certifications c ON r.required_certification_id = c.id
        WHERE r.id = ?
        """,
        (resource_id,),
        one=True
    )
    if not resource:
        flash("Resource not found.", "danger")
        return redirect(url_for('index'))

    # Check user eligibility
    user_id = g.user['id'] if g.user else None
    is_eligible = True
    if user_id:
        is_eligible, _ = check_eligibility(user_id, resource_id)

    # Fetch existing scheduled slots for calendar/timetable view
    occupied_slots = query_db(
        """
        SELECT b.start_date, b.end_date, b.status, u.name as borrower_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        WHERE b.resource_id = ? AND b.status IN ('approved', 'active')
        ORDER BY b.start_date ASC
        """,
        (resource_id,)
    )

    # Waitlist count
    waitlist_count_row = query_db(
        "SELECT COUNT(*) as count FROM waitlists WHERE resource_id = ? AND status = 'waiting'",
        (resource_id,),
        one=True
    )
    waitlist_count = waitlist_count_row['count'] if waitlist_count_row else 0

    return render_template(
        'resource_detail.html',
        resource=resource,
        is_eligible=is_eligible,
        occupied_slots=occupied_slots,
        waitlist_count=waitlist_count
    )


@app.route('/resource/add', methods=['GET', 'POST'])
@login_required
def add_resource():
    if g.user['role'] not in ['owner', 'admin']:
        flash("Only Resource Owners and Admins can list new resources.", "warning")
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()
        image_url = request.form.get('image_url', '').strip()
        required_cert_id = request.form.get('required_certification_id', '').strip()
        max_days = int(request.form.get('max_days', 3))

        if not title or not category or not location:
            flash("Title, category, and location are required.", "danger")
            return redirect(url_for('add_resource'))

        if not required_cert_id:
            required_cert_id = None
        else:
            required_cert_id = int(required_cert_id)

        new_resource_id = execute_db(
            """
            INSERT INTO resources (
                owner_id, title, description, category, location, image_url,
                status, required_certification_id, max_days
            )
            VALUES (?, ?, ?, ?, ?, ?, 'available', ?, ?)
            """,
            (g.user['id'], title, description, category, location, image_url, required_cert_id, max_days)
        )

        log_activity(
            user_id=g.user['id'],
            action="RESOURCE_CREATED",
            details=f"{g.user['name']} listed new resource '{title}' in {category}.",
            resource_id=new_resource_id
        )

        flash(f"Resource '{title}' published successfully to the catalog!", "success")
        return redirect(url_for('resource_detail', resource_id=new_resource_id))

    certifications = query_db("SELECT id, name, code FROM certifications ORDER BY name")
    return render_template('resource_form.html', certifications=certifications)


# ---------------------------------------------------------
# Core Booking Lifecycle Routes
# ---------------------------------------------------------
@app.route('/book/<int:resource_id>', methods=['POST'])
@login_required
def create_booking(resource_id):
    resource = query_db("SELECT * FROM resources WHERE id = ?", (resource_id,), one=True)
    if not resource:
        flash("Resource not found.", "danger")
        return redirect(url_for('index'))

    if resource['status'] == 'maintenance':
        flash("This resource is currently under maintenance and cannot be booked.", "danger")
        return redirect(url_for('resource_detail', resource_id=resource_id))

    start_date_str = request.form.get('start_date', '').strip()
    end_date_str = request.form.get('end_date', '').strip()
    purpose = request.form.get('purpose', '').strip()

    if not start_date_str or not end_date_str or not purpose:
        flash("Please provide start date, end date, and usage purpose.", "warning")
        return redirect(url_for('resource_detail', resource_id=resource_id))

    # Parse and validate dates
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date format. Please select valid dates.", "danger")
        return redirect(url_for('resource_detail', resource_id=resource_id))

    today = date.today()
    if start_date < today:
        flash("Start date cannot be in the past.", "warning")
        return redirect(url_for('resource_detail', resource_id=resource_id))

    if end_date < start_date:
        flash("End date cannot precede the start date.", "warning")
        return redirect(url_for('resource_detail', resource_id=resource_id))

    duration_days = (end_date - start_date).days + 1

    # 1. Eligibility & Training Check
    is_eligible, cert_name = check_eligibility(g.user['id'], resource_id)
    if not is_eligible:
        flash(f"Eligibility error: You must complete '{cert_name}' training before booking this equipment.", "danger")
        return redirect(url_for('resource_detail', resource_id=resource_id))

    # 2. Scheduling Conflict Check (Checks if the requested slot is open)
    has_conflict, conflicts = check_scheduling_conflict(resource_id, start_date_str, end_date_str)
    if has_conflict:
        conflicting_desc = ", ".join([f"{c['start_date']} to {c['end_date']} (by {c['borrower_name']})" for c in conflicts])
        flash(f"Scheduling collision! This resource is already booked for: {conflicting_desc}. Please choose different dates or join the waitlist below.", "warning")
        return redirect(url_for('resource_detail', resource_id=resource_id))

    # 3. Fair Usage Limits Check
    allowed, reason = check_fair_usage(g.user['id'], duration_days, resource_id)
    if not allowed:
        flash(reason, "danger")
        return redirect(url_for('resource_detail', resource_id=resource_id))

    # All checks passed: Create booking with 'pending' status
    booking_id = execute_db(
        """
        INSERT INTO bookings (resource_id, user_id, start_date, end_date, purpose, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
        """,
        (resource_id, g.user['id'], start_date_str, end_date_str, purpose)
    )

    # Log to audit trail
    log_activity(
        user_id=g.user['id'],
        action="REQUESTED",
        details=f"{g.user['name']} requested booking #{booking_id} for '{resource['title']}' ({start_date_str} to {end_date_str}).",
        booking_id=booking_id,
        resource_id=resource_id
    )

    # Notify resource owner
    create_notification(
        user_id=resource['owner_id'],
        title="New Booking Request",
        message=f"{g.user['name']} requested '{resource['title']}' for {duration_days} day(s). Please review and approve.",
        link="/manage-requests"
    )

    flash("Booking request submitted! The resource owner has been notified for approval.", "success")
    return redirect(url_for('my_bookings'))


@app.route('/my-bookings')
@login_required
def my_bookings():
    bookings = query_db(
        """
        SELECT b.*, r.title as resource_title, r.image_url, r.location, u.name as owner_name
        FROM bookings b
        JOIN resources r ON b.resource_id = r.id
        JOIN users u ON r.owner_id = u.id
        WHERE b.user_id = ?
        ORDER BY 
            CASE b.status
                WHEN 'active' THEN 1
                WHEN 'approved' THEN 2
                WHEN 'pending' THEN 3
                WHEN 'completed' THEN 4
                ELSE 5
            END,
            b.created_at DESC
        """,
        (g.user['id'],)
    )
    return render_template('my_bookings.html', bookings=bookings)


@app.route('/manage-requests')
@login_required
def manage_requests():
    if g.user['role'] not in ['owner', 'admin']:
        flash("Access restricted to Resource Owners and Admins.", "warning")
        return redirect(url_for('index'))

    # Pending incoming requests
    if g.user['role'] == 'admin':
        pending_requests = query_db(
            """
            SELECT b.*, r.title as resource_title, r.location, u.name as requester_name, u.email as requester_email, c.name as required_cert_name
            FROM bookings b
            JOIN resources r ON b.resource_id = r.id
            JOIN users u ON b.user_id = u.id
            LEFT JOIN certifications c ON r.required_certification_id = c.id
            WHERE b.status = 'pending'
            ORDER BY b.created_at ASC
            """
        )
        active_and_approved = query_db(
            """
            SELECT b.*, r.title as resource_title, r.location, u.name as borrower_name, u.email as borrower_email
            FROM bookings b
            JOIN resources r ON b.resource_id = r.id
            JOIN users u ON b.user_id = u.id
            WHERE b.status IN ('approved', 'active')
            ORDER BY b.start_date ASC
            """
        )
    else:
        pending_requests = query_db(
            """
            SELECT b.*, r.title as resource_title, r.location, u.name as requester_name, u.email as requester_email, c.name as required_cert_name
            FROM bookings b
            JOIN resources r ON b.resource_id = r.id
            JOIN users u ON b.user_id = u.id
            LEFT JOIN certifications c ON r.required_certification_id = c.id
            WHERE r.owner_id = ? AND b.status = 'pending'
            ORDER BY b.created_at ASC
            """,
            (g.user['id'],)
        )
        active_and_approved = query_db(
            """
            SELECT b.*, r.title as resource_title, r.location, u.name as borrower_name, u.email as borrower_email
            FROM bookings b
            JOIN resources r ON b.resource_id = r.id
            JOIN users u ON b.user_id = u.id
            WHERE r.owner_id = ? AND b.status IN ('approved', 'active')
            ORDER BY b.start_date ASC
            """,
            (g.user['id'],)
        )

    return render_template(
        'manage_requests.html',
        pending_requests=pending_requests,
        active_and_approved=active_and_approved
    )


@app.route('/booking/<int:booking_id>/approve', methods=['POST'])
@login_required
def approve_booking(booking_id):
    booking = query_db(
        """
        SELECT b.*, r.owner_id, r.title as resource_title, u.name as borrower_name
        FROM bookings b
        JOIN resources r ON b.resource_id = r.id
        JOIN users u ON b.user_id = u.id
        WHERE b.id = ?
        """,
        (booking_id,),
        one=True
    )
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for('manage_requests'))

    if g.user['role'] != 'admin' and booking['owner_id'] != g.user['id']:
        flash("Unauthorized: You can only approve bookings for your own resources.", "danger")
        return redirect(url_for('manage_requests'))

    # Update booking to 'approved'
    execute_db("UPDATE bookings SET status = 'approved' WHERE id = ?", (booking_id,))

    # Update resource status to 'reserved' if currently available
    execute_db("UPDATE resources SET status = 'reserved' WHERE id = ? AND status = 'available'", (booking['resource_id'],))

    # Notify requester
    create_notification(
        user_id=booking['user_id'],
        title="Booking Approved! 🎉",
        message=f"Your reservation for '{booking['resource_title']}' has been approved by the owner.",
        link="/my-bookings"
    )

    # Log to audit trail
    log_activity(
        user_id=g.user['id'],
        action="APPROVED",
        details=f"{g.user['name']} approved booking #{booking_id} for '{booking['resource_title']}' to {booking['borrower_name']}.",
        booking_id=booking_id,
        resource_id=booking['resource_id']
    )

    flash("Booking approved! The borrower has been notified.", "success")
    return redirect(url_for('manage_requests'))


@app.route('/booking/<int:booking_id>/reject', methods=['POST'])
@login_required
def reject_booking(booking_id):
    booking = query_db(
        """
        SELECT b.*, r.owner_id, r.title as resource_title
        FROM bookings b
        JOIN resources r ON b.resource_id = r.id
        WHERE b.id = ?
        """,
        (booking_id,),
        one=True
    )
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for('manage_requests'))

    if g.user['role'] != 'admin' and booking['owner_id'] != g.user['id']:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('manage_requests'))

    execute_db("UPDATE bookings SET status = 'rejected' WHERE id = ?", (booking_id,))

    # Notify requester
    create_notification(
        user_id=booking['user_id'],
        title="Booking Request Declined",
        message=f"Your reservation request for '{booking['resource_title']}' could not be accommodated at this time.",
        link="/my-bookings"
    )

    # Log to audit trail
    log_activity(
        user_id=g.user['id'],
        action="REJECTED",
        details=f"{g.user['name']} rejected booking #{booking_id} for '{booking['resource_title']}'.",
        booking_id=booking_id,
        resource_id=booking['resource_id']
    )

    flash("Booking request rejected.", "info")
    return redirect(url_for('manage_requests'))


@app.route('/booking/<int:booking_id>/check-in', methods=['POST'])
@login_required
def check_in_booking(booking_id):
    booking = query_db(
        """
        SELECT b.*, r.owner_id, r.title as resource_title, u.name as borrower_name
        FROM bookings b
        JOIN resources r ON b.resource_id = r.id
        JOIN users u ON b.user_id = u.id
        WHERE b.id = ?
        """,
        (booking_id,),
        one=True
    )
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for('my_bookings'))

    # Either the borrower, owner, or admin can perform the handover check-in
    if g.user['id'] != booking['user_id'] and g.user['id'] != booking['owner_id'] and g.user['role'] != 'admin':
        flash("Unauthorized action.", "danger")
        return redirect(url_for('my_bookings'))

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_db(
        "UPDATE bookings SET status = 'active', check_in_time = ? WHERE id = ?",
        (now_str, booking_id)
    )
    # Set resource status to 'in_use'
    execute_db("UPDATE resources SET status = 'in_use' WHERE id = ?", (booking['resource_id'],))

    # Audit log
    log_activity(
        user_id=g.user['id'],
        action="CHECKED_IN",
        details=f"Check-In verified: Resource '{booking['resource_title']}' handed over to {booking['borrower_name']}.",
        booking_id=booking_id,
        resource_id=booking['resource_id']
    )

    create_notification(
        user_id=booking['user_id'],
        title="Check-In Confirmed",
        message=f"You have checked in for '{booking['resource_title']}'. Enjoy using the equipment!",
        link="/my-bookings"
    )

    flash(f"Check-in confirmed! '{booking['resource_title']}' is now marked active and in-use.", "success")
    if g.user['id'] == booking['owner_id']:
        return redirect(url_for('manage_requests'))
    return redirect(url_for('my_bookings'))


@app.route('/booking/<int:booking_id>/return', methods=['POST'])
@login_required
def return_booking(booking_id):
    booking = query_db(
        """
        SELECT b.*, r.owner_id, r.title as resource_title, u.name as borrower_name
        FROM bookings b
        JOIN resources r ON b.resource_id = r.id
        JOIN users u ON b.user_id = u.id
        WHERE b.id = ?
        """,
        (booking_id,),
        one=True
    )
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for('my_bookings'))

    return_condition = request.form.get('return_condition', 'Good')
    return_notes = request.form.get('return_notes', '').strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Update booking to 'completed'
    execute_db(
        """
        UPDATE bookings
        SET status = 'completed', return_time = ?, return_condition = ?, return_notes = ?
        WHERE id = ?
        """,
        (now_str, return_condition, return_notes, booking_id)
    )

    resource_id = booking['resource_id']

    # Condition Handling: If Damaged, log Incident and place in Maintenance
    if return_condition == 'Damaged':
        execute_db("UPDATE resources SET status = 'maintenance' WHERE id = ?", (resource_id,))
        inc_desc = f"Equipment returned in DAMAGED condition by {booking['borrower_name']}. Inspector notes: {return_notes or 'Defect noted upon check-in inspection.'}"
        execute_db(
            """
            INSERT INTO incidents (resource_id, booking_id, reported_by_user_id, severity, description, status)
            VALUES (?, ?, ?, 'Medium', ?, 'open')
            """,
            (resource_id, booking_id, g.user['id'], inc_desc)
        )
        log_activity(
            user_id=g.user['id'],
            action="INCIDENT_LOGGED",
            details=f"Damage flagged upon return of '{booking['resource_title']}'. Placed in Maintenance.",
            booking_id=booking_id,
            resource_id=resource_id
        )
        flash("Return completed. Resource flagged with damage and placed into Maintenance.", "warning")
    else:
        # Resource freed back to 'available'
        execute_db("UPDATE resources SET status = 'available' WHERE id = ?", (resource_id,))
        # Check transparent waiting list for promotions!
        promoted = promote_waitlist_if_any(resource_id)
        if promoted:
            flash(f"Return verified! Resource is available, and {promoted['user_name']} was promoted from the waitlist.", "info")
        else:
            flash("Return verified! Resource is now available for new bookings.", "success")

    # Audit log
    log_activity(
        user_id=g.user['id'],
        action="RETURNED",
        details=f"Returned '{booking['resource_title']}' in {return_condition} condition. Inspection completed.",
        booking_id=booking_id,
        resource_id=resource_id
    )

    if g.user['id'] == booking['owner_id']:
        return redirect(url_for('manage_requests'))
    return redirect(url_for('my_bookings'))


@app.route('/booking/<int:booking_id>/cancel', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    booking = query_db(
        """
        SELECT b.*, r.title as resource_title
        FROM bookings b
        JOIN resources r ON b.resource_id = r.id
        WHERE b.id = ?
        """,
        (booking_id,),
        one=True
    )
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for('my_bookings'))

    if g.user['id'] != booking['user_id'] and g.user['role'] not in ['owner', 'admin']:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('my_bookings'))

    execute_db("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))

    # If the resource was reserved or in use, check if it can be reset to available
    other_active = query_db(
        "SELECT id FROM bookings WHERE resource_id = ? AND status IN ('approved', 'active') AND id != ?",
        (booking['resource_id'], booking_id)
    )
    if not other_active:
        execute_db("UPDATE resources SET status = 'available' WHERE id = ? AND status != 'maintenance'", (booking['resource_id'],))
        promote_waitlist_if_any(booking['resource_id'])

    log_activity(
        user_id=g.user['id'],
        action="CANCELLED",
        details=f"Booking #{booking_id} for '{booking['resource_title']}' was cancelled.",
        booking_id=booking_id,
        resource_id=booking['resource_id']
    )

    flash("Reservation cancelled.", "info")
    return redirect(url_for('my_bookings'))


# ---------------------------------------------------------
# Transparent Waiting Lists
# ---------------------------------------------------------
@app.route('/join-waitlist/<int:resource_id>', methods=['POST'])
@login_required
def join_waitlist(resource_id):
    resource = query_db("SELECT * FROM resources WHERE id = ?", (resource_id,), one=True)
    if not resource:
        flash("Resource not found.", "danger")
        return redirect(url_for('index'))

    today_str = date.today().strftime("%Y-%m-%d")
    execute_db(
        "INSERT INTO waitlists (resource_id, user_id, start_date, end_date, status) VALUES (?, ?, ?, ?, 'waiting')",
        (resource_id, g.user['id'], today_str, today_str)
    )

    # Count queue position
    pos_row = query_db(
        "SELECT COUNT(*) as count FROM waitlists WHERE resource_id = ? AND status = 'waiting'",
        (resource_id,),
        one=True
    )
    pos = pos_row['count'] if pos_row else 1

    log_activity(
        user_id=g.user['id'],
        action="WAITLIST_JOINED",
        details=f"{g.user['name']} joined waitlist as #{pos} for '{resource['title']}'.",
        resource_id=resource_id
    )

    create_notification(
        user_id=g.user['id'],
        title="Waitlist Position Confirmed",
        message=f"You joined the waitlist for '{resource['title']}' at position #{pos}.",
        link="/waitlists"
    )

    flash(f"You have joined the transparent waiting list as #{pos}! You will be notified the moment a spot opens.", "success")
    return redirect(url_for('waitlists'))


@app.route('/waitlists')
@login_required
def waitlists():
    # My waitlists with dynamic position calculation
    raw_my_waitlists = query_db(
        """
        SELECT w.*, r.title as resource_title, u.name as owner_name
        FROM waitlists w
        JOIN resources r ON w.resource_id = r.id
        JOIN users u ON r.owner_id = u.id
        WHERE w.user_id = ?
        ORDER BY w.created_at DESC
        """,
        (g.user['id'],)
    )
    my_waitlists = []
    for item in raw_my_waitlists:
        w_dict = dict(item)
        pos_row = query_db(
            "SELECT COUNT(*) as count FROM waitlists WHERE resource_id = ? AND status = 'waiting' AND created_at <= ?",
            (w_dict['resource_id'], w_dict['created_at']),
            one=True
        )
        w_dict['position'] = pos_row['count'] if pos_row else 1
        my_waitlists.append(w_dict)

    # Public transparency queue across all resources
    raw_public = query_db(
        """
        SELECT w.*, r.title as resource_title, u.name as user_name
        FROM waitlists w
        JOIN resources r ON w.resource_id = r.id
        JOIN users u ON w.user_id = u.id
        WHERE w.status = 'waiting'
        ORDER BY w.resource_id, w.created_at ASC
        """
    )
    public_queues = []
    counter = {}
    for q in raw_public:
        q_dict = dict(q)
        r_id = q_dict['resource_id']
        counter[r_id] = counter.get(r_id, 0) + 1
        q_dict['position'] = counter[r_id]
        public_queues.append(q_dict)

    return render_template('waitlists.html', my_waitlists=my_waitlists, public_queues=public_queues)


@app.route('/waitlist/<int:waitlist_id>/cancel', methods=['POST'])
@login_required
def cancel_waitlist(waitlist_id):
    execute_db("DELETE FROM waitlists WHERE id = ? AND user_id = ?", (waitlist_id, g.user['id']))
    flash("You have been removed from the waiting list.", "info")
    return redirect(url_for('waitlists'))


# ---------------------------------------------------------
# Damage & Incident Management Routes
# ---------------------------------------------------------
@app.route('/incidents')
@login_required
def incidents():
    incidents_list = query_db(
        """
        SELECT i.*, r.title as resource_title, r.status as resource_status, u.name as reporter_name, u.role as reporter_role
        FROM incidents i
        JOIN resources r ON i.resource_id = r.id
        JOIN users u ON i.reported_by_user_id = u.id
        ORDER BY 
            CASE i.status WHEN 'open' THEN 1 WHEN 'under_review' THEN 2 ELSE 3 END,
            i.created_at DESC
        """
    )
    return render_template('incidents.html', incidents=incidents_list)


@app.route('/incident/report', methods=['POST'])
@login_required
def report_incident():
    resource_id_str = request.form.get('resource_id', '').strip()
    severity = request.form.get('severity', 'Medium')
    description = request.form.get('description', '').strip()

    if not description:
        flash("Incident description is required.", "warning")
        return redirect(url_for('incidents'))

    # If resource_id was left blank in generic modal, find first matching
    if not resource_id_str:
        res = query_db("SELECT id, title FROM resources LIMIT 1", one=True)
        resource_id = res['id']
    else:
        resource_id = int(resource_id_str)

    res = query_db("SELECT title, owner_id FROM resources WHERE id = ?", (resource_id,), one=True)

    inc_id = execute_db(
        """
        INSERT INTO incidents (resource_id, reported_by_user_id, severity, description, status)
        VALUES (?, ?, ?, ?, 'open')
        """,
        (resource_id, g.user['id'], severity, description)
    )

    # Set resource status to 'maintenance'
    execute_db("UPDATE resources SET status = 'maintenance' WHERE id = ?", (resource_id,))

    log_activity(
        user_id=g.user['id'],
        action="INCIDENT_LOGGED",
        details=f"Incident #{inc_id} filed for '{res['title']}': {description} (Severity: {severity}). Placed into Maintenance.",
        resource_id=resource_id
    )

    create_notification(
        user_id=res['owner_id'],
        title="⚠️ Damage Incident Reported",
        message=f"An incident ({severity}) was reported for '{res['title']}'. The item is currently in Maintenance.",
        link="/incidents"
    )

    flash("Incident reported. Resource placed into Maintenance mode until resolved.", "danger")
    return redirect(url_for('incidents'))


@app.route('/incident/<int:incident_id>/resolve', methods=['POST'])
@login_required
def resolve_incident(incident_id):
    if g.user['role'] not in ['owner', 'admin']:
        flash("Only Owners and Admins can resolve equipment incidents.", "warning")
        return redirect(url_for('incidents'))

    notes = request.form.get('resolution_notes', 'Repaired and verified.').strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    incident = query_db("SELECT * FROM incidents WHERE id = ?", (incident_id,), one=True)
    if not incident:
        flash("Incident not found.", "danger")
        return redirect(url_for('incidents'))

    execute_db(
        "UPDATE incidents SET status = 'resolved', resolution_notes = ?, resolved_at = ? WHERE id = ?",
        (notes, now_str, incident_id)
    )

    # Check if there are other open incidents on this resource
    open_left = query_db("SELECT id FROM incidents WHERE resource_id = ? AND status != 'resolved'", (incident['resource_id'],))
    if not open_left:
        # Restore resource to available (or reserved if pending approved bookings)
        has_future_booking = query_db("SELECT id FROM bookings WHERE resource_id = ? AND status = 'approved'", (incident['resource_id'],))
        new_status = 'reserved' if has_future_booking else 'available'
        execute_db("UPDATE resources SET status = ? WHERE id = ?", (new_status, incident['resource_id']))

    log_activity(
        user_id=g.user['id'],
        action="INCIDENT_RESOLVED",
        details=f"Incident #{incident_id} marked resolved by {g.user['name']}. Notes: {notes}",
        resource_id=incident['resource_id']
    )

    flash("Incident successfully marked as resolved! Resource returned to active service.", "success")
    return redirect(url_for('incidents'))


# ---------------------------------------------------------
# Training & Certifications
# ---------------------------------------------------------
@app.route('/training')
@login_required
def training_catalog():
    certs = query_db("SELECT * FROM certifications ORDER BY name")
    user_cert_ids = [
        row['certification_id']
        for row in query_db("SELECT certification_id FROM user_certifications WHERE user_id = ?", (g.user['id'],))
    ]

    cert_list = []
    for c in certs:
        c_dict = dict(c)
        c_dict['user_has_cert'] = c['id'] in user_cert_ids
        # Count resources requiring this cert
        res_count = query_db("SELECT COUNT(*) as count FROM resources WHERE required_certification_id = ?", (c['id'],), one=True)
        c_dict['resources_count'] = res_count['count'] if res_count else 0
        cert_list.append(c_dict)

    return render_template('training.html', certifications=cert_list)


@app.route('/training/complete/<int:cert_id>', methods=['POST'])
@login_required
def complete_training(cert_id):
    cert = query_db("SELECT name FROM certifications WHERE id = ?", (cert_id,), one=True)
    if not cert:
        flash("Certification module not found.", "danger")
        return redirect(url_for('training_catalog'))

    # Grant certification
    execute_db(
        "INSERT OR IGNORE INTO user_certifications (user_id, certification_id, notes) VALUES (?, ?, 'Completed Online Interactive Simulation')",
        (g.user['id'], cert_id)
    )

    log_activity(
        user_id=g.user['id'],
        action="TRAINING_COMPLETED",
        details=f"{g.user['name']} completed training and earned '{cert['name']}' certification."
    )

    create_notification(
        user_id=g.user['id'],
        title="Training Clearance Granted! 🎓",
        message=f"You earned the '{cert['name']}' credential. You are now cleared to book certified equipment.",
        link="/training"
    )

    flash(f"Congratulations! You completed the training simulation and earned your '{cert['name']}' clearance.", "success")

    redirect_to = request.form.get('redirect_to')
    if redirect_to:
        return redirect(redirect_to)
    return redirect(url_for('training_catalog'))


# ---------------------------------------------------------
# Activity History & Notifications
# ---------------------------------------------------------
@app.route('/activity-history')
@login_required
def activity_history():
    action = request.args.get('action', '').strip()
    sql = """
        SELECT a.*, u.name as actor_name, u.role as actor_role
        FROM activity_logs a
        JOIN users u ON a.user_id = u.id
        WHERE 1=1
    """
    args = []
    if action:
        sql += " AND a.action = ?"
        args.append(action)

    sql += " ORDER BY a.created_at DESC LIMIT 100"
    logs = query_db(sql, args)
    return render_template('activity_history.html', logs=logs, selected_action=action)


@app.route('/notifications')
@login_required
def notifications():
    notifs = query_db(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
        (g.user['id'],)
    )
    return render_template('notifications.html', notifications=notifs)


@app.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_notifications_read():
    execute_db("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (g.user['id'],))
    flash("All notifications marked as read.", "info")
    return redirect(url_for('notifications'))


# ---------------------------------------------------------
# App Entry Point
# ---------------------------------------------------------
if __name__ == '__main__':
    # Initialize DB schema if not present
    if not os.path.exists('sharespace.db'):
        print("Database not found. Initializing and seeding...")
        from seed import seed_database
        seed_database()

    print(">> ShareSpace starting on http://127.0.0.1:5000 ...")
    app.run(debug=True, port=5000)
