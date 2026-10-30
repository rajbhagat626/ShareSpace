-- ShareSpace Database Schema
-- Supports complete lifecycle, certifications, fair usage, waitlists, incidents, and audit trails

DROP TABLE IF EXISTS activity_logs;
DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS waitlists;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS user_certifications;
DROP TABLE IF EXISTS resources;
DROP TABLE IF EXISTS certifications;
DROP TABLE IF EXISTS users;

-- Users (RBAC: member, owner, admin)
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'member', -- 'member', 'owner', 'admin'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Certifications & Training Modules
CREATE TABLE certifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    code TEXT NOT NULL UNIQUE,
    description TEXT,
    category TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User Certifications (Eligibility tracking)
CREATE TABLE user_certifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    certification_id INTEGER NOT NULL,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (certification_id) REFERENCES certifications(id) ON DELETE CASCADE,
    UNIQUE(user_id, certification_id)
);

-- Resources (With required training & fair usage parameters)
CREATE TABLE resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    location TEXT,
    image_url TEXT,
    status TEXT DEFAULT 'available', -- 'available', 'reserved', 'in_use', 'maintenance'
    required_certification_id INTEGER,
    max_days INTEGER DEFAULT 5, -- Fair usage limit per booking
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (required_certification_id) REFERENCES certifications(id) ON DELETE SET NULL
);

-- Bookings (Full state lifecycle)
CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    start_date TEXT NOT NULL, -- YYYY-MM-DD
    end_date TEXT NOT NULL,   -- YYYY-MM-DD
    purpose TEXT,
    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'active', 'completed', 'cancelled'
    check_in_time TIMESTAMP,
    return_time TIMESTAMP,
    return_condition TEXT, -- 'Pristine', 'Good', 'Fair', 'Damaged'
    return_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Transparent Waiting Lists
CREATE TABLE waitlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT DEFAULT 'waiting', -- 'waiting', 'notified', 'converted', 'cancelled'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Damage & Incident Reports
CREATE TABLE incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    booking_id INTEGER,
    reported_by_user_id INTEGER NOT NULL,
    severity TEXT DEFAULT 'Medium', -- 'Low', 'Medium', 'High', 'Critical'
    description TEXT NOT NULL,
    status TEXT DEFAULT 'open', -- 'open', 'under_review', 'resolved'
    resolution_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL,
    FOREIGN KEY (reported_by_user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- In-App Notifications
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    link TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Auditable Activity History
CREATE TABLE activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER,
    resource_id INTEGER,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL, -- 'RESOURCE_CREATED', 'REQUESTED', 'APPROVED', 'REJECTED', 'CHECKED_IN', 'RETURNED', 'INCIDENT_LOGGED', 'INCIDENT_RESOLVED', 'TRAINING_COMPLETED', 'WAITLIST_JOINED', 'WAITLIST_PROMOTED'
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL,
    FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_resources_status ON resources(status);
CREATE INDEX idx_bookings_status ON bookings(status);
CREATE INDEX idx_bookings_dates ON bookings(start_date, end_date);
CREATE INDEX idx_waitlists_resource ON waitlists(resource_id, status);
CREATE INDEX idx_notifications_user ON notifications(user_id, is_read);
CREATE INDEX idx_activity_created ON activity_logs(created_at DESC);
