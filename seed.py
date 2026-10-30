import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from database import init_db, get_db

def seed_database():
    print("Re-initializing ShareSpace database with complete schema...")
    init_db()

    conn = get_db()
    cur = conn.cursor()
    default_pw = generate_password_hash("password123")

    # 1. Seed Demo Users with RBAC roles
    users = [
        ("Alex Chen (Owner)", "alex@sharespace.local", default_pw, "owner"),
        ("Sam Rivera (Borrower)", "sam@sharespace.local", default_pw, "member"),
        ("Jordan Taylor (Admin)", "jordan@sharespace.local", default_pw, "admin")
    ]
    cur.executemany(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        users
    )
    conn.commit()

    alex_id = 1
    sam_id = 2
    jordan_id = 3

    # 2. Seed Certifications / Training Modules
    certs = [
        ("3D Printing & Additive Safety", "CERT-3DPRINT", "Essential filament loading, slicing safety, hotbed hazard prevention, and post-print cleaning.", "Lab & Prototyping"),
        ("Heavy Workshop & Power Tools Safety", "CERT-TOOLS", "Safety goggles, battery maintenance, torque clutch settings, and workshop emergency protocols.", "Workshop"),
        ("Broadcast Studio & Pro Audio Clearance", "CERT-AUDIO", "Proper XLR routing, 48V phantom power management, and acoustic dampening handling.", "Media & Audio")
    ]
    cur.executemany(
        "INSERT INTO certifications (name, code, description, category) VALUES (?, ?, ?, ?)",
        certs
    )
    conn.commit()

    # 3. Seed User Certifications (Eligibility)
    # Alex: Has all
    # Sam: Has Audio only (Sam is NOT certified for 3D Printing yet, which demonstrates training eligibility blocking!)
    # Jordan: Has all
    user_certs = [
        (alex_id, 1, "Verified by Makerspace Staff"),
        (alex_id, 2, "Verified by Workshop Lead"),
        (alex_id, 3, "Verified by Studio Manager"),
        (sam_id, 3, "Completed Online Audio Orientation"), # Sam only has Audio clearance
        (jordan_id, 1, "Administrator Exemption"),
        (jordan_id, 2, "Administrator Exemption"),
        (jordan_id, 3, "Administrator Exemption")
    ]
    cur.executemany(
        "INSERT INTO user_certifications (user_id, certification_id, notes) VALUES (?, ?, ?)",
        user_certs
    )
    conn.commit()

    # 4. Seed Resources with Fair Usage Limits & Training Requirements
    resources = [
        (
            alex_id,
            "Sony Alpha A7 IV Mirrorless Camera Kit",
            "Includes 24-70mm f/2.8 GM lens, 2x NP-FZ100 batteries, charger, and 128GB V90 SD card. Perfect for media projects and event recording.",
            "Media & Cameras",
            "Media Lab - Station 4",
            "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=800&q=80",
            "available",
            None, # Open to all members
            4     # Max 4 days per reservation
        ),
        (
            alex_id,
            "Meta Quest 3 VR Headset (512GB)",
            "Dual RGB passthrough cameras, Touch Plus controllers, elite strap. Pre-installed with development tools and WebXR environments.",
            "Electronics",
            "Innovation Hub - Locker B2",
            "https://images.unsplash.com/photo-1622979135240-caa6648190b6?auto=format&fit=crop&w=800&q=80",
            "in_use", # Currently in use by Sam
            None,
            3
        ),
        (
            jordan_id,
            "Bambu Lab X1-Carbon 3D Printer",
            "High-speed multi-color printing capable of carbon fiber filament. Bed size 256x256x256mm. Enclosed chamber with active carbon filter.",
            "Lab Equipment",
            "Makerspace - Bay 1",
            "https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=800&q=80",
            "available",
            1, # Requires CERT-3DPRINT!
            2  # Fair usage: Max 2 days
        ),
        (
            alex_id,
            "Shure SM7B Studio Podcast Mic + Stand",
            "Broadcast-grade dynamic microphone with Cloudlifter CL-1 preamp, heavy-duty boom arm, and Mogami XLR cable.",
            "Media & Cameras",
            "Audio Studio - Room A",
            "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?auto=format&fit=crop&w=800&q=80",
            "reserved", # Reserved starting tomorrow
            3, # Requires CERT-AUDIO
            3
        ),
        (
            jordan_id,
            "Private Focus & Meeting Pod 2B",
            "Soundproof acoustic booth for up to 4 people. Equipped with 4K display, HDMI/USB-C hub, and writeable glass whiteboards.",
            "Workspaces",
            "Level 2 - East Wing",
            "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=800&q=80",
            "available",
            None,
            1  # Max 1 day
        ),
        (
            alex_id,
            "DeWalt 20V Max Cordless Drill & Impact Driver Set",
            "Complete kit with 2x 4Ah batteries, rapid charger, bit set, and rugged carry case.",
            "Tools",
            "Workshop - Cabinet 3",
            "https://images.unsplash.com/photo-1504148455328-c376907d081c?auto=format&fit=crop&w=800&q=80",
            "maintenance", # Currently under maintenance due to incident!
            2, # Requires CERT-TOOLS
            3
        )
    ]

    cur.executemany(
        """
        INSERT INTO resources (
            owner_id, title, description, category, location, image_url, status, required_certification_id, max_days
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        resources
    )
    conn.commit()

    # 5. Seed Bookings Across All Lifecycle States
    today = datetime.now()
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    two_days_ago = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    in_three_days = (today + timedelta(days=3)).strftime("%Y-%m-%d")
    in_five_days = (today + timedelta(days=5)).strftime("%Y-%m-%d")

    bookings = [
        # 1: COMPLETED booking (Sony Camera returned yesterday in Pristine condition)
        (
            1, # Sony Camera
            sam_id, # Sam
            two_days_ago,
            yesterday,
            "Filming promotional interviews for the hackathon showcase.",
            "completed",
            f"{two_days_ago} 10:00:00",
            f"{yesterday} 17:30:00",
            "Pristine",
            "Returned thoroughly cleaned, all lens caps and batteries accounted for."
        ),
        # 2: ACTIVE booking (Meta Quest 3 in use by Sam right now)
        (
            2, # Meta Quest 3
            sam_id, # Sam
            yesterday,
            tomorrow,
            "Testing WebXR prototype interaction with VR controllers.",
            "active",
            f"{yesterday} 14:15:00",
            None,
            None,
            None
        ),
        # 3: APPROVED booking (Shure SM7B reserved for tomorrow)
        (
            4, # Shure Mic
            sam_id, # Sam
            tomorrow,
            in_three_days,
            "Recording voiceover narration for product demo video.",
            "approved",
            None,
            None,
            None,
            None
        ),
        # 4: PENDING booking (Meeting Pod 2B requested by Sam - Alex can approve/reject)
        (
            5, # Meeting Pod
            sam_id, # Sam
            in_three_days,
            in_three_days,
            "Team sync and sprint review presentation rehearsal.",
            "pending",
            None,
            None,
            None,
            None
        )
    ]

    cur.executemany(
        """
        INSERT INTO bookings (
            resource_id, user_id, start_date, end_date, purpose, status,
            check_in_time, return_time, return_condition, return_notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        bookings
    )
    conn.commit()

    # 6. Seed Transparent Waiting List
    # Jordan is on the waitlist for Meta Quest 3 (which is currently in_use by Sam)
    cur.execute(
        """
        INSERT INTO waitlists (resource_id, user_id, start_date, end_date, status)
        VALUES (?, ?, ?, ?, 'waiting')
        """,
        (2, jordan_id, tomorrow, in_three_days)
    )
    conn.commit()

    # 7. Seed Damage & Incident Management
    # DeWalt Drill was flagged with a damaged chuck upon return
    cur.execute(
        """
        INSERT INTO incidents (resource_id, booking_id, reported_by_user_id, severity, description, status, resolution_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            6, # DeWalt Drill Set
            None,
            alex_id,
            "Medium",
            "Keyless chuck collar slips and fails to lock 1/4 inch drill bits securely. Requires replacement jaw spring.",
            "open",
            None
        )
    )
    conn.commit()

    # 8. Seed In-App Notifications
    notifications = [
        (sam_id, "Booking Approved!", "Alex approved your reservation for 'Shure SM7B Studio Podcast Mic + Stand'.", "/my-bookings", 0),
        (sam_id, "Check-in Confirmed", "You successfully checked in for 'Meta Quest 3 VR Headset (512GB)'.", "/my-bookings", 1),
        (alex_id, "New Booking Request", "Sam requested 'Private Focus & Meeting Pod 2B'. Please review and approve.", "/manage-requests", 0),
        (jordan_id, "Waitlist Confirmed", "You are #1 on the waiting list for 'Meta Quest 3 VR Headset (512GB)'.", "/waitlists", 0)
    ]
    cur.executemany(
        "INSERT INTO notifications (user_id, title, message, link, is_read) VALUES (?, ?, ?, ?, ?)",
        notifications
    )
    conn.commit()

    # 9. Seed Comprehensive Auditable Activity History
    logs = [
        (None, 1, alex_id, "RESOURCE_CREATED", "Alex listed 'Sony Alpha A7 IV Mirrorless Camera Kit' in Media & Cameras."),
        (None, 3, jordan_id, "RESOURCE_CREATED", "Jordan listed 'Bambu Lab X1-Carbon 3D Printer' (Requires 3D Printing Safety)."),
        (None, 6, alex_id, "RESOURCE_CREATED", "Alex listed 'DeWalt 20V Max Cordless Drill & Impact Driver Set'."),
        (1, 1, sam_id, "REQUESTED", "Sam requested booking #1 for Sony Camera."),
        (1, 1, alex_id, "APPROVED", "Alex approved booking #1."),
        (1, 1, alex_id, "CHECKED_IN", "Handover completed. Resource status updated to 'In Use'."),
        (1, 1, alex_id, "RETURNED", "Returned in Pristine condition (5/5). All lens caps & accessories verified. Booking completed."),
        (2, 2, sam_id, "REQUESTED", "Sam requested booking #2 for Meta Quest 3."),
        (2, 2, alex_id, "APPROVED", "Alex approved booking #2."),
        (2, 2, alex_id, "CHECKED_IN", "Check-in confirmed by Alex. Item currently active."),
        (None, 2, jordan_id, "WAITLIST_JOINED", "Jordan joined the waiting list as position #1 for Meta Quest 3."),
        (3, 4, sam_id, "REQUESTED", "Sam requested booking #3 for Shure SM7B Podcast Mic."),
        (3, 4, alex_id, "APPROVED", "Alex approved booking #3. Awaiting check-in tomorrow."),
        (4, 5, sam_id, "REQUESTED", "Sam requested booking #4 for Meeting Pod 2B."),
        (None, 6, alex_id, "INCIDENT_LOGGED", "Incident #1 logged: DeWalt Drill chuck slipping. Resource placed into Maintenance.")
    ]
    cur.executemany(
        "INSERT INTO activity_logs (booking_id, resource_id, user_id, action, details) VALUES (?, ?, ?, ?, ?)",
        logs
    )
    conn.commit()
    conn.close()

    print("ShareSpace database seeded successfully with all hackathon requirements!")

if __name__ == '__main__':
    seed_database()
