import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import init_db, get_db_connection
from app.main import seed_demo_data
from app.services.hold_service import hold_seats_atomic
from app.services.booking_service import confirm_booking_atomic, cancel_booking_atomic
from app.services.waitlist_service import join_waitlist, process_cancellation_waitlist_offers

def test_waitlist_auto_assignment():
    print("=" * 60)
    print("STARTING WAITLIST & CANCELLATION AUTO-ASSIGNMENT TEST")
    print("=" * 60)

    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ticket_booking.db")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass

    init_db()
    seed_demo_data()

    # 1. Fetch Event and Users
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM events LIMIT 1")
    event_id = cursor.fetchone()["id"]

    cursor.execute("SELECT id FROM users WHERE role = 'CUSTOMER'")
    users = cursor.fetchall()
    user1_id = users[0]["id"]
    user2_id = users[1]["id"] if len(users) > 1 else users[0]["id"]

    cursor.execute("SELECT id, seat_label FROM show_seats WHERE event_id = ? AND category = 'STANDARD' LIMIT 1", (event_id,))
    seat = cursor.fetchone()
    seat_id = seat["id"]
    seat_label = seat["seat_label"]
    conn.close()

    # 2. Hold & Confirm Seat for User 1
    print(f"Step 1: User 1 holds seat '{seat_label}'")
    hold_res = hold_seats_atomic(user1_id, event_id, [seat_id])
    assert hold_res["success"] == True

    print("Step 2: User 1 confirms booking and receives QR code ticket")
    book_res = confirm_booking_atomic(user1_id, event_id, [seat_id])
    assert book_res["success"] == True
    booking_id = book_res["booking_id"]

    # 3. Mark all remaining STANDARD seats BOOKED to simulate sold-out category
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE show_seats SET status = 'BOOKED' WHERE event_id = ? AND category = 'STANDARD'", (event_id,))
    conn.commit()
    conn.close()

    # 4. User 2 joins waitlist for STANDARD category
    print("Step 3: User 2 joins waitlist for category 'STANDARD'")
    wl_res = join_waitlist(user2_id, event_id, "STANDARD")
    print(f"Waitlist result: {wl_res['message']}")
    assert wl_res["success"] == True

    # 5. Revert target seat to BOOKED by User 1
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE show_seats SET status = 'BOOKED', booking_id = ? WHERE id = ?", (booking_id, seat_id))
    conn.commit()
    conn.close()

    # 6. User 1 cancels booking
    print("Step 4: User 1 cancels booking")
    cancel_res = cancel_booking_atomic(user1_id, booking_id)
    assert cancel_res["success"] == True

    # 7. Process cancellation waitlist offer
    print("Step 5: System processes waitlist auto-assignment flow")
    offers = process_cancellation_waitlist_offers(event_id, cancel_res["released_seats"])
    print(f"Waitlist offers generated: {offers}")

    assert len(offers) == 1, "Expected 1 waitlist offer to be generated"
    assert offers[0]["user_id"] == user2_id, "Offer should be assigned to User 2"

    print("\n[PASSED] WAITLIST AUTO-ASSIGNMENT TEST PASSED!")

if __name__ == "__main__":
    test_waitlist_auto_assignment()
