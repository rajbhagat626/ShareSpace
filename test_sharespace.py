import unittest
import os
import sqlite3
from datetime import datetime, date, timedelta
from app import app
from database import get_db, init_db, execute_db, query_db, log_activity, promote_waitlist_if_any
from seed import seed_database

class ShareSpaceTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()

        # Seed database before each test for repeatable assertions
        seed_database()

    def test_01_catalog_and_homepage(self):
        """Test homepage and catalog rendering with statistics."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'ShareSpace', response.data)
        self.assertIn(b'Shared Resource Catalog', response.data)
        self.assertIn(b'Sony Alpha A7 IV', response.data)

    def test_02_persona_switcher(self):
        """Test 1-click persona switching (Alex Owner -> Sam Borrower -> Jordan Admin)."""
        # Switch to Alex (Owner, id=1)
        resp1 = self.client.get('/switch-user/1', follow_redirects=True)
        self.assertEqual(resp1.status_code, 200)
        self.assertIn(b'Alex Chen (Owner)', resp1.data)

        # Switch to Sam (Borrower, id=2)
        resp2 = self.client.get('/switch-user/2', follow_redirects=True)
        self.assertEqual(resp2.status_code, 200)
        self.assertIn(b'Sam Rivera (Borrower)', resp2.data)

        # Switch to Jordan (Admin, id=3)
        resp3 = self.client.get('/switch-user/3', follow_redirects=True)
        self.assertEqual(resp3.status_code, 200)
        self.assertIn(b'Jordan Taylor (Admin)', resp3.data)

    def test_03_eligibility_and_training_verification(self):
        """Test that uncertified users are blocked from booking certified equipment until training is completed."""
        # Sam (Borrower, id=2) is NOT certified for 3D Printing (Resource id=3: Bambu Lab X1-Carbon)
        self.client.get('/switch-user/2')

        today_str = (date.today() + timedelta(days=20)).strftime("%Y-%m-%d")
        tomorrow_str = (date.today() + timedelta(days=21)).strftime("%Y-%m-%d")

        # Attempt to book without training
        resp = self.client.post('/book/3', data={
            'start_date': today_str,
            'end_date': tomorrow_str,
            'purpose': 'Testing uncertified booking block'
        }, follow_redirects=True)

        self.assertIn(b'Eligibility error: You must complete', resp.data)

        # Now complete the training simulation
        train_resp = self.client.post('/training/complete/1', follow_redirects=True)
        self.assertIn(b'Congratulations! You completed the training simulation', train_resp.data)

        # Cancel one of Sam's seed pending bookings so fair usage is within limit
        execute_db("DELETE FROM bookings WHERE user_id = 2 AND status = 'pending'")

        # Now booking should pass eligibility check
        book_resp = self.client.post('/book/3', data={
            'start_date': today_str,
            'end_date': tomorrow_str,
            'purpose': 'Now certified to 3D print!'
        }, follow_redirects=True)
        self.assertIn(b'Booking request submitted', book_resp.data)

    def test_04_fair_usage_duration_limit(self):
        """Test that requesting a booking longer than max_days is rejected."""
        self.client.get('/switch-user/2')
        # Resource id=1 (Sony Camera) has max_days=4
        today = date.today()
        start_str = (today + timedelta(days=10)).strftime("%Y-%m-%d")
        # Request 10 days (exceeds 4 days limit)
        end_str = (today + timedelta(days=20)).strftime("%Y-%m-%d")

        resp = self.client.post('/book/1', data={
            'start_date': start_str,
            'end_date': end_str,
            'purpose': 'Attempting excessive duration'
        }, follow_redirects=True)

        self.assertIn(b'Fair usage limit exceeded', resp.data)

    def test_05_scheduling_conflict_handling(self):
        """Test that overlapping reservations are prevented and conflict message is shown."""
        self.client.get('/switch-user/2')
        # Resource id=4 (Shure SM7B) already has an approved booking for tomorrow -> +3 days in seed data
        today = date.today()
        overlap_start = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        overlap_end = (today + timedelta(days=2)).strftime("%Y-%m-%d")

        resp = self.client.post('/book/4', data={
            'start_date': overlap_start,
            'end_date': overlap_end,
            'purpose': 'Conflicting reservation attempt'
        }, follow_redirects=True)

        self.assertIn(b'Scheduling collision!', resp.data)

    def test_06_complete_booking_lifecycle(self):
        """
        Verify end-to-end lifecycle:
        1. Jordan (id=3) requests booking for Sony Camera (id=1, owned by Alex) -> Pending
        2. Alex (Owner, id=1) approves -> Approved
        3. Check-in handover -> Active (In Use)
        4. Return inspection -> Completed (Available)
        """
        # Step 1: Jordan requests booking for Sony Camera (Resource id=1, owned by Alex)
        self.client.get('/switch-user/3')
        today = date.today()
        start_str = (today + timedelta(days=14)).strftime("%Y-%m-%d")
        end_str = (today + timedelta(days=15)).strftime("%Y-%m-%d")

        resp_req = self.client.post('/book/1', data={
            'start_date': start_str,
            'end_date': end_str,
            'purpose': 'Solo hackathon presentation prep'
        }, follow_redirects=True)
        self.assertIn(b'Booking request submitted', resp_req.data)

        # Retrieve new booking id
        booking = query_db(
            "SELECT id FROM bookings WHERE resource_id = 1 AND user_id = 3 ORDER BY id DESC LIMIT 1",
            one=True
        )
        booking_id = booking['id']

        # Step 2: Alex approves booking for his own resource
        self.client.get('/switch-user/1')
        resp_app = self.client.post(f'/booking/{booking_id}/approve', follow_redirects=True)
        self.assertIn(b'Booking approved', resp_app.data)

        b_approved = query_db("SELECT status FROM bookings WHERE id = ?", (booking_id,), one=True)
        self.assertEqual(b_approved['status'], 'approved')

        # Step 3: Check-in handover
        resp_checkin = self.client.post(f'/booking/{booking_id}/check-in', follow_redirects=True)
        self.assertIn(b'Check-in confirmed', resp_checkin.data)

        b_active = query_db("SELECT status FROM bookings WHERE id = ?", (booking_id,), one=True)
        self.assertEqual(b_active['status'], 'active')

        res_in_use = query_db("SELECT status FROM resources WHERE id = 1", one=True)
        self.assertEqual(res_in_use['status'], 'in_use')

        # Step 4: Return inspection (Pristine condition)
        resp_return = self.client.post(f'/booking/{booking_id}/return', data={
            'return_condition': 'Pristine',
            'return_notes': 'Sony Camera left spotless with all caps.'
        }, follow_redirects=True)
        self.assertIn(b'Return verified', resp_return.data)

        b_completed = query_db("SELECT status, return_condition FROM bookings WHERE id = ?", (booking_id,), one=True)
        self.assertEqual(b_completed['status'], 'completed')
        self.assertEqual(b_completed['return_condition'], 'Pristine')

        res_available = query_db("SELECT status FROM resources WHERE id = 1", one=True)
        self.assertEqual(res_available['status'], 'available')

    def test_07_damage_incident_reporting_and_resolution(self):
        """Test returning an item as 'Damaged' places it in maintenance and generates an incident report."""
        # Create an active booking for Sony Camera (id=1)
        execute_db(
            """
            INSERT INTO bookings (resource_id, user_id, start_date, end_date, purpose, status)
            VALUES (1, 2, '2026-11-01', '2026-11-02', 'Video Shoot', 'active')
            """
        )
        booking = query_db("SELECT id FROM bookings WHERE resource_id = 1 AND status = 'active' ORDER BY id DESC LIMIT 1", one=True)
        booking_id = booking['id']

        self.client.get('/switch-user/1') # Alex inspects return
        resp = self.client.post(f'/booking/{booking_id}/return', data={
            'return_condition': 'Damaged',
            'return_notes': 'Cracked front lens element from accidental drop.'
        }, follow_redirects=True)

        self.assertIn(b'Resource flagged with damage and placed into Maintenance', resp.data)

        # Verify resource is in maintenance
        res = query_db("SELECT status FROM resources WHERE id = 1", one=True)
        self.assertEqual(res['status'], 'maintenance')

        # Verify incident was created
        inc = query_db("SELECT id, status, severity FROM incidents WHERE resource_id = 1 ORDER BY id DESC LIMIT 1", one=True)
        self.assertIsNotNone(inc)
        self.assertEqual(inc['status'], 'open')

        # Now resolve the incident
        resp_res = self.client.post(f'/incident/{inc["id"]}/resolve', data={
            'resolution_notes': 'Front optical filter replaced and sensor recalibrated.'
        }, follow_redirects=True)
        self.assertIn(b'Incident successfully marked as resolved', resp_res.data)

        res_after = query_db("SELECT status FROM resources WHERE id = 1", one=True)
        self.assertEqual(res_after['status'], 'available')

    def test_08_transparent_waitlist(self):
        """Test joining a waiting list and tracking queue positions."""
        self.client.get('/switch-user/2') # Sam joins waitlist for Meta Quest (Resource id=2)
        resp = self.client.post('/join-waitlist/2', follow_redirects=True)
        self.assertIn(b'joined the transparent waiting list', resp.data)

        # Check waitlists page
        resp_list = self.client.get('/waitlists')
        self.assertEqual(resp_list.status_code, 200)
        self.assertIn(b'My Waiting List Positions', resp_list.data)
        self.assertIn(b'Position #', resp_list.data)

    def test_09_auditable_activity_history(self):
        """Test that activity logs are captured and displayed on the audit log timeline."""
        self.client.get('/switch-user/1')
        resp = self.client.get('/activity-history')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Auditable System Activity Log', resp.data)
        self.assertIn(b'APPROVED', resp.data)
        self.assertIn(b'CHECKED_IN', resp.data)
        self.assertIn(b'RETURNED', resp.data)

if __name__ == '__main__':
    unittest.main()
