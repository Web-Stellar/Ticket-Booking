import os
from datetime import datetime, timedelta
from app.database import get_db_connection, db_lock

SEAT_HOLD_TTL_MINUTES = int(os.getenv("SEAT_HOLD_TTL_MINUTES", "10"))

def hold_seats_atomic(user_id: str, event_id: str, seat_ids: list) -> dict:
    """Atomic seat hold with concurrency protection and TTL expiration timestamp."""
    if not seat_ids:
        return {"success": False, "message": "No seats selected"}

    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=SEAT_HOLD_TTL_MINUTES)
    expires_at_str = expires_at.isoformat()
    now_str = now.isoformat()

    with db_lock:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            conn.execute("BEGIN IMMEDIATE;")  # Exclusive lock for writing

            # Check seat status first
            placeholders = ",".join(["?"] * len(seat_ids))
            query = f"""
            SELECT id, status, seat_label FROM show_seats 
            WHERE id IN ({placeholders}) AND event_id = ?
            """
            cursor.execute(query, (*seat_ids, event_id))
            seats = cursor.fetchall()

            if len(seats) != len(seat_ids):
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Invalid seat selection for this event."}

            unavailable_seats = [s["seat_label"] for s in seats if s["status"] != "AVAILABLE"]
            if unavailable_seats:
                conn.rollback()
                conn.close()
                return {
                    "success": False, 
                    "message": f"Seats {', '.join(unavailable_seats)} are no longer available (held or booked by another customer)."
                }

            # Update seats atomically
            update_query = f"""
            UPDATE show_seats 
            SET status = 'HELD', held_by_user_id = ?, hold_expires_at = ?, updated_at = ?
            WHERE id IN ({placeholders}) AND event_id = ? AND status = 'AVAILABLE'
            """
            cursor.execute(update_query, (user_id, expires_at_str, now_str, *seat_ids, event_id))
            
            if cursor.rowcount != len(seat_ids):
                conn.rollback()
                conn.close()
                return {
                    "success": False,
                    "message": "Concurrency conflict: One or more seats were claimed by another customer simultaneously."
                }

            conn.commit()
            conn.close()
            return {
                "success": True, 
                "seat_ids": seat_ids, 
                "expires_at": expires_at_str,
                "ttl_minutes": SEAT_HOLD_TTL_MINUTES
            }
        except Exception as e:
            conn.rollback()
            conn.close()
            return {"success": False, "message": f"Error holding seats: {str(e)}"}

def release_held_seats(user_id: str, event_id: str, seat_ids: list) -> dict:
    """Manually releases seats held by a user (e.g. checkout abandonment)."""
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(seat_ids))
        cursor.execute(f"""
        UPDATE show_seats 
        SET status = 'AVAILABLE', held_by_user_id = NULL, hold_expires_at = NULL, updated_at = ?
        WHERE id IN ({placeholders}) AND event_id = ? AND status = 'HELD' AND held_by_user_id = ?
        """, (datetime.utcnow().isoformat(), *seat_ids, event_id, user_id))
        released_count = cursor.rowcount
        conn.commit()
        conn.close()
        return {"success": True, "released_count": released_count}
