import uuid
from datetime import datetime
from app.database import get_db_connection, db_lock
from app.services.email_service import generate_qr_code_base64, send_booking_confirmation_email

def confirm_booking_atomic(user_id: str, event_id: str, seat_ids: list) -> dict:
    """Confirms booking for currently held seats, generates QR ticket, and emails receipt."""
    if not seat_ids:
        return {"success": False, "message": "No seats selected for booking."}

    now_str = datetime.utcnow().isoformat()
    booking_ref = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    booking_id = str(uuid.uuid4())

    with db_lock:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            conn.execute("BEGIN IMMEDIATE;")

            # Retrieve seats held by user
            placeholders = ",".join(["?"] * len(seat_ids))
            cursor.execute(f"""
            SELECT s.id, s.seat_label, s.price, s.category, s.status, s.held_by_user_id, s.hold_expires_at,
                   e.title as event_title, e.event_date, v.name as venue_name, u.email, u.name as user_name
            FROM show_seats s
            JOIN events e ON s.event_id = e.id
            JOIN venues v ON e.venue_id = v.id
            JOIN users u ON u.id = ?
            WHERE s.id IN ({placeholders}) AND s.event_id = ?
            """, (user_id, *seat_ids, event_id))
            
            rows = cursor.fetchall()
            if len(rows) != len(seat_ids):
                conn.rollback()
                conn.close()
                return {"success": False, "message": "One or more seats not found."}

            first_row = rows[0]
            event_title = first_row["event_title"]
            event_date = first_row["event_date"]
            venue_name = first_row["venue_name"]
            user_email = first_row["email"]
            user_name = first_row["user_name"]

            # Verify seats are HELD by this user and not expired
            invalid_seats = []
            total_amount = 0.0
            seat_labels = []

            for row in rows:
                seat_labels.append(row["seat_label"])
                total_amount += row["price"]
                # Must be held by user or offered to waitlisted user
                if row["status"] not in ("HELD", "OFFERED") or row["held_by_user_id"] != user_id:
                    invalid_seats.append(row["seat_label"])

            if invalid_seats:
                conn.rollback()
                conn.close()
                return {
                    "success": False,
                    "message": f"Seats {', '.join(invalid_seats)} are not currently held by your session or hold has expired."
                }

            # Encode payload into QR code
            qr_payload = f"REF:{booking_ref}|EVT:{event_title}|SEATS:{','.join(seat_labels)}|USER:{user_email}"
            qr_code_base64 = generate_qr_code_base64(qr_payload)

            # Create Booking Record
            cursor.execute("""
            INSERT INTO bookings (id, booking_ref, user_id, event_id, total_amount, status, qr_code_data, created_at)
            VALUES (?, ?, ?, ?, ?, 'CONFIRMED', ?, ?)
            """, (booking_id, booking_ref, user_id, event_id, total_amount, qr_code_base64, now_str))

            # Update Seat status to BOOKED
            cursor.execute(f"""
            UPDATE show_seats
            SET status = 'BOOKED', booking_id = ?, held_by_user_id = NULL, hold_expires_at = NULL, updated_at = ?
            WHERE id IN ({placeholders}) AND event_id = ?
            """, (booking_id, now_str, *seat_ids, event_id))

            conn.commit()
            conn.close()

            # Send Email in background thread/task
            send_booking_confirmation_email(
                user_email=user_email,
                user_name=user_name,
                booking_ref=booking_ref,
                event_title=event_title,
                event_date=event_date,
                venue_name=venue_name,
                seats_list=seat_labels,
                total_amount=total_amount,
                qr_code_base64=qr_code_base64
            )

            return {
                "success": True,
                "booking_id": booking_id,
                "booking_ref": booking_ref,
                "total_amount": total_amount,
                "seat_labels": seat_labels,
                "qr_code_base64": qr_code_base64
            }

        except Exception as e:
            conn.rollback()
            conn.close()
            return {"success": False, "message": f"Booking confirmation error: {str(e)}"}

def cancel_booking_atomic(user_id: str, booking_id: str) -> dict:
    """Cancels a booking, releases seats to AVAILABLE, and returns released seat information for waitlist assignment."""
    now_str = datetime.utcnow().isoformat()

    with db_lock:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            conn.execute("BEGIN IMMEDIATE;")

            # Retrieve booking
            cursor.execute("""
            SELECT id, booking_ref, user_id, event_id, status FROM bookings WHERE id = ?
            """, (booking_id,))
            booking = cursor.fetchone()

            if not booking:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Booking not found."}

            if booking["user_id"] != user_id:
                # Check if user is admin/organiser
                cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
                usr = cursor.fetchone()
                if not usr or usr["role"] not in ("ADMIN", "ORGANISER"):
                    conn.rollback()
                    conn.close()
                    return {"success": False, "message": "Unauthorized to cancel this booking."}

            if booking["status"] == "CANCELLED":
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Booking is already cancelled."}

            event_id = booking["event_id"]

            # Update booking status
            cursor.execute("UPDATE bookings SET status = 'CANCELLED' WHERE id = ?", (booking_id,))

            # Find seats associated with this booking
            cursor.execute("""
            SELECT id, category, seat_label FROM show_seats WHERE booking_id = ?
            """, (booking_id,))
            seats = cursor.fetchall()

            released_seats_info = [{"id": s["id"], "category": s["category"], "label": s["seat_label"]} for s in seats]

            # Revert seat statuses to AVAILABLE
            cursor.execute("""
            UPDATE show_seats 
            SET status = 'AVAILABLE', booking_id = NULL, held_by_user_id = NULL, hold_expires_at = NULL, updated_at = ?
            WHERE booking_id = ?
            """, (now_str, booking_id))

            conn.commit()
            conn.close()

            return {
                "success": True,
                "booking_id": booking_id,
                "event_id": event_id,
                "released_seats": released_seats_info
            }
        except Exception as e:
            conn.rollback()
            conn.close()
            return {"success": False, "message": f"Cancellation error: {str(e)}"}
