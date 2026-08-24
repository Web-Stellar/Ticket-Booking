import os
import uuid
from datetime import datetime, timedelta
from app.database import get_db_connection, db_lock
from app.services.email_service import send_waitlist_offer_email

WAITLIST_OFFER_TTL_MINUTES = int(os.getenv("WAITLIST_OFFER_TTL_MINUTES", "5"))

def join_waitlist(user_id: str, event_id: str, category: str) -> dict:
    """Adds a customer to the waitlist queue for a specific seat category of an event."""
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if seats are currently available in this category
        cursor.execute("""
        SELECT COUNT(*) as available_count FROM show_seats 
        WHERE event_id = ? AND category = ? AND status = 'AVAILABLE'
        """, (event_id, category))
        row = cursor.fetchone()
        if row and row["available_count"] > 0:
            conn.close()
            return {"success": False, "message": f"Seats in {category} are currently available! You can select and book directly."}

        # Check if user is already on pending waitlist for this category
        cursor.execute("""
        SELECT id FROM waitlist 
        WHERE event_id = ? AND user_id = ? AND category = ? AND status IN ('PENDING', 'OFFERED')
        """, (event_id, user_id, category))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return {"success": False, "message": "You are already on the waitlist for this category."}

        waitlist_id = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO waitlist (id, event_id, user_id, category, status, created_at)
        VALUES (?, ?, ?, ?, 'PENDING', ?)
        """, (waitlist_id, event_id, user_id, category, datetime.utcnow().isoformat()))
        conn.commit()

        # Get queue position
        cursor.execute("""
        SELECT COUNT(*) as position FROM waitlist 
        WHERE event_id = ? AND category = ? AND status = 'PENDING' AND created_at <= (
            SELECT created_at FROM waitlist WHERE id = ?
        )
        """, (event_id, category, waitlist_id))
        pos_row = cursor.fetchone()
        position = pos_row["position"] if pos_row else 1

        conn.close()
        return {
            "success": True, 
            "waitlist_id": waitlist_id, 
            "category": category, 
            "queue_position": position,
            "message": f"Added to waitlist for {category}. Queue position: #{position}"
        }

def process_cancellation_waitlist_offers(event_id: str, released_seats: list) -> list:
    """Triggered on seat release/cancellation: checks waitlist and assigns seats to next in queue."""
    offered_results = []
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=WAITLIST_OFFER_TTL_MINUTES)
    now_str = now.isoformat()
    expires_at_str = expires_at.isoformat()

    emails_to_send = []

    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()

        for seat in released_seats:
            seat_id = seat["id"]
            category = seat["category"]
            seat_label = seat["label"]

            # Find next pending waitlist user for this event and category (FIFO)
            cursor.execute("""
            SELECT w.id as waitlist_id, w.user_id, u.email, u.name, e.title as event_title
            FROM waitlist w
            JOIN users u ON w.user_id = u.id
            JOIN events e ON w.event_id = e.id
            WHERE w.event_id = ? AND w.category = ? AND w.status = 'PENDING'
            ORDER BY w.created_at ASC
            LIMIT 1
            """, (event_id, category))

            next_waitlist = cursor.fetchone()

            if next_waitlist:
                waitlist_id = next_waitlist["waitlist_id"]
                user_id = next_waitlist["user_id"]
                user_email = next_waitlist["email"]
                user_name = next_waitlist["name"]
                event_title = next_waitlist["event_title"]

                # Reserve seat as OFFERED for this waitlisted user
                cursor.execute("""
                UPDATE show_seats 
                SET status = 'OFFERED', held_by_user_id = ?, hold_expires_at = ?, updated_at = ?
                WHERE id = ? AND status = 'AVAILABLE'
                """, (user_id, expires_at_str, now_str, seat_id))

                if cursor.rowcount > 0:
                    # Update waitlist entry to OFFERED
                    cursor.execute("""
                    UPDATE waitlist 
                    SET status = 'OFFERED', offered_at = ?, offer_expires_at = ?, offered_seat_id = ?
                    WHERE id = ?
                    """, (now_str, expires_at_str, seat_id, waitlist_id))

                    claim_url = f"http://localhost:8000/?action=claim_waitlist&waitlist_id={waitlist_id}"
                    
                    emails_to_send.append({
                        "user_email": user_email,
                        "user_name": user_name,
                        "event_title": event_title,
                        "category": category,
                        "seat_label": seat_label,
                        "offer_expires_at": expires_at_str[:19].replace("T", " "),
                        "claim_url": claim_url
                    })

                    offered_results.append({
                        "seat_id": seat_id,
                        "seat_label": seat_label,
                        "user_id": user_id,
                        "user_email": user_email,
                        "waitlist_id": waitlist_id,
                        "expires_at": expires_at_str
                    })

        conn.commit()
        conn.close()

    # Dispatch emails after releasing database transaction
    for email_data in emails_to_send:
        send_waitlist_offer_email(**email_data)

    return offered_results
