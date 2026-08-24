import os
import asyncio
import logging
from datetime import datetime
from app.database import get_db_connection, db_lock
from app.services.socket_manager import ws_manager
from app.services.waitlist_service import process_cancellation_waitlist_offers

SWEEPER_INTERVAL_SECONDS = int(os.getenv("SWEEPER_INTERVAL_SECONDS", "5"))
logger = logging.getLogger("sweeper")

async def run_sweeper_loop():
    """Background task loop enforcing seat hold TTL auto-release and waitlist offer expiration."""
    logger.info("Starting Background TTL Sweeper Loop...")
    while True:
        try:
            now_str = datetime.utcnow().isoformat()
            
            # --- 1. Expire Held Seats ---
            released_seats_by_event = {}
            with db_lock:
                conn = get_db_connection()
                cursor = conn.cursor()

                # Find expired held seats
                cursor.execute("""
                SELECT id, event_id, seat_label FROM show_seats 
                WHERE status = 'HELD' AND hold_expires_at <= ?
                """, (now_str,))
                expired_holds = cursor.fetchall()

                if expired_holds:
                    expired_ids = [row["id"] for row in expired_holds]
                    placeholders = ",".join(["?"] * len(expired_ids))
                    cursor.execute(f"""
                    UPDATE show_seats 
                    SET status = 'AVAILABLE', held_by_user_id = NULL, hold_expires_at = NULL, updated_at = ?
                    WHERE id IN ({placeholders})
                    """, (now_str, *expired_ids))
                    conn.commit()

                    for row in expired_holds:
                        evt_id = row["event_id"]
                        if evt_id not in released_seats_by_event:
                            released_seats_by_event[evt_id] = []
                        released_seats_by_event[evt_id].append(row["id"])

                # --- 2. Expire Waitlist Offers ---
                cursor.execute("""
                SELECT w.id as waitlist_id, w.event_id, w.category, w.offered_seat_id, s.seat_label
                FROM waitlist w
                LEFT JOIN show_seats s ON w.offered_seat_id = s.id
                WHERE w.status = 'OFFERED' AND w.offer_expires_at <= ?
                """, (now_str,))
                expired_offers = cursor.fetchall()

                expired_offer_seats = []
                for offer in expired_offers:
                    w_id = offer["waitlist_id"]
                    e_id = offer["event_id"]
                    s_id = offer["offered_seat_id"]
                    s_label = offer["seat_label"] or "Seat"

                    # Mark waitlist entry expired
                    cursor.execute("UPDATE waitlist SET status = 'EXPIRED' WHERE id = ?", (w_id,))
                    
                    # Reset seat status to AVAILABLE
                    if s_id:
                        cursor.execute("""
                        UPDATE show_seats 
                        SET status = 'AVAILABLE', held_by_user_id = NULL, hold_expires_at = NULL, updated_at = ?
                        WHERE id = ? AND status = 'OFFERED'
                        """, (now_str, s_id))
                        expired_offer_seats.append({"id": s_id, "category": offer["category"], "label": s_label, "event_id": e_id})

                conn.commit()
                conn.close()

            # --- 3. Process Waitlist Cascades for Expired Offers ---
            for offer_seat in expired_offer_seats:
                e_id = offer_seat["event_id"]
                process_cancellation_waitlist_offers(e_id, [offer_seat])
                if e_id not in released_seats_by_event:
                    released_seats_by_event[e_id] = []
                released_seats_by_event[e_id].append(offer_seat["id"])

            # --- 4. Broadcast Real-Time WebSocket Seat Map Updates ---
            for event_id, seat_ids in released_seats_by_event.items():
                await ws_manager.broadcast_seat_update(event_id, {
                    "type": "SEAT_RELEASED",
                    "event_id": event_id,
                    "seat_ids": seat_ids,
                    "timestamp": now_str
                })

        except Exception as e:
            logger.error(f"Error in background sweeper loop: {e}")

        await asyncio.sleep(SWEEPER_INTERVAL_SECONDS)
