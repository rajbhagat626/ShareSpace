# ShareSpace ⇄
### Resource-Sharing Web Application for 48-Hour Solo Hackathon

ShareSpace is a collaborative resource-sharing web application built with **Python (Flask)**, **SQLite**, **HTML5**, **Modern CSS**, and **Vanilla JavaScript**. It enables communities, maker labs, and campuses to share equipment, spaces, and devices safely and transparently.

---

## ⚡ Quick Start (Under 10 Seconds)

### Option 1: Double-Click Runner
Double-click `run_app.bat` in the project folder.

### Option 2: PowerShell / Terminal
```powershell
.\venv\Scripts\python.exe app.py
```
Open your browser and navigate to: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🎭 1-Click Demo Personas (Hackathon Judge Showcase)

A floating **Demo Persona Bar** appears at the top of every screen. Click any button to instantly switch users without typing passwords:

| Persona | Role | Capabilities / What to Demo |
| :--- | :--- | :--- |
| **Alex Chen** | **Owner** | Lists resources, reviews incoming requests, approves/rejects bookings, conducts check-in/return inspections, reports incidents. |
| **Sam Rivera** | **Borrower** | Explores catalog, checks eligibility, books gear, joins waiting lists, completes safety training simulations. |
| **Jordan Taylor** | **Admin** | System-wide authority: oversees all resources, reviews incidents, tracks full auditable history. |

---

## 🚀 Hackathon Features Walkthrough

### 1. Complete Booking Lifecycle
- **Listing:** Resources displayed with live status pills (🟢 *Available*, 🔵 *In Use*, 🟣 *Reserved*, 🚨 *Maintenance*).
- **Requesting:** Borrowers submit date windows and purpose.
- **Approval:** Owners approve or decline with 1-click in `Manage Requests`.
- **Check-In Handover:** Owner or borrower marks handover; status updates to *In Use*.
- **Return & Inspection:** Return modal captures condition grade (*Pristine 5/5*, *Good 4/5*, *Fair 3/5*, *Damaged*), checklist verification, and inspector notes.
- **Release:** Completed returns reset equipment status to *Available* and promote the waiting list automatically.

### 2. Eligibility & Training Verification
- High-risk equipment (e.g. *Bambu Lab X1-Carbon 3D Printer*) requires certified safety training before reservation.
- Uncertified users are blocked from submitting requests.
- A **1-Click "Complete Training Simulation"** action is provided on both the resource page and the **Training** tab for instant hackathon demonstration.

### 3. Fair Usage Limits
- **Max Duration Cap:** Enforces resource-specific caps (e.g. max 2 to 5 consecutive days).
- **Concurrent Booking Cap:** Restricts members to a maximum of 3 concurrent active/pending bookings to prevent equipment hoarding.

### 4. Scheduling Conflict Handling
- Real-time overlap detection prevents double-booking (`NOT (new_end < start OR new_start > end)`).
- Booked date slots are visually listed in the timetable on the resource detail page.
- Friendly conflict warnings prompt users to adjust dates or join the waitlist.

### 5. Transparent Waiting Lists
- When an item is occupied or in maintenance, users can click **"Join Waiting List"**.
- Transparently displays queue position (*"You are #1 in line"*).
- When a resource is returned or cancelled, the next waitlisted user is automatically notified and promoted.

### 6. Damage & Incident Management
- Marking an item **Damaged** during return automatically:
  1. Creates an **Incident Report** with severity (*Low*, *Medium*, *High*, *Critical*).
  2. Transitions resource status to **Maintenance**, blocking new bookings.
  3. Notifies the owner and admin.
- Owners/Admins can record repair notes and click **"Mark Resolved & Restore Resource"** in the **Incidents** tab to return it to active service.

### 7. In-App Notifications
- Notification bell in header with unread badge counter.
- Delivers real-time alerts for booking approvals, check-in reminders, waitlist promotions, and damage reports.

### 8. Auditable System History
- Complete chronological audit log in the **Audit Log** tab.
- Filterable by event type: `REQUESTED`, `APPROVED`, `CHECKED_IN`, `RETURNED`, `INCIDENT_LOGGED`, `INCIDENT_RESOLVED`, `TRAINING_COMPLETED`, `WAITLIST_JOINED`.

---

## 🧪 Automated Test Suite

Run the 9-point comprehensive automated test suite:
```powershell
.\venv\Scripts\python.exe -m unittest test_sharespace.py -v
```

All 9 test suites pass:
- `test_01_catalog_and_homepage`: Catalog search and status filters
- `test_02_persona_switcher`: 1-click RBAC switching
- `test_03_eligibility_and_training_verification`: Certification blocking and clearance simulation
- `test_04_fair_usage_duration_limit`: Max duration enforcement
- `test_05_scheduling_conflict_handling`: Double-booking prevention
- `test_06_complete_booking_lifecycle`: Request -> Approve -> Check-in -> Return
- `test_07_damage_incident_reporting_and_resolution`: Damage flagging, maintenance mode, and repair restoration
- `test_08_transparent_waitlist`: Queue positioning and tracking
- `test_09_auditable_activity_history`: Audit trail verification
