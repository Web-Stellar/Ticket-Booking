from fastapi import APIRouter, HTTPException, Depends
from app.database import get_db_connection
from app.models import ConfirmBookingRequest, CancelBookingRequest
from app.auth import get_current_user
from app.services.booking_service import confirm_booking_atomic, cancel_booking_atomic
from app.services.waitlist_service import process_cancellation_waitlist_offers
from app.services.socket_manager import ws_manager

router = APIRouter(prefix="/api/bookings", tags=["Bookings"])

@router.post("/confirm")
async def confirm_booking(req: ConfirmBookingRequest, current_user: dict = Depends(get_current_user)):
    """Confirms booking for held seats, produces QR ticket email, and broadcasts booking to seat map."""
    res = confirm_booking_atomic(user_id=current_user["id"], event_id=req.event_id, seat_ids=req.seat_ids)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])

    # Broadcast real-time seat update to all clients
    await ws_manager.broadcast_seat_update(req.event_id, {
        "type": "SEAT_BOOKED",
        "event_id": req.event_id,
        "seat_ids": req.seat_ids
    })

    return res

@router.post("/cancel")
async def cancel_booking(req: CancelBookingRequest, current_user: dict = Depends(get_current_user)):
    """Cancels an existing booking and automatically triggers waitlist assignment flow for released seats."""
    res = cancel_booking_atomic(user_id=current_user["id"], booking_id=req.booking_id)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])

    event_id = res["event_id"]
    released_seats = res["released_seats"]

    # Process waitlist auto-assignment for the released seats!
    offered = process_cancellation_waitlist_offers(event_id, released_seats)

    # Broadcast seat map update
    released_ids = [s["id"] for s in released_seats]
    await ws_manager.broadcast_seat_update(event_id, {
        "type": "SEAT_RELEASED",
        "event_id": event_id,
        "seat_ids": released_ids,
        "waitlist_offered": offered
    })

    return {
        "success": True,
        "message": f"Booking cancelled successfully. {len(released_seats)} seat(s) released.",
        "waitlist_offers_triggered": len(offered)
    }

@router.get("/my")
def get_my_bookings(current_user: dict = Depends(get_current_user)):
    """Retrieves booking history and ticket QR codes for the logged-in customer."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT b.id, b.booking_ref, b.event_id, e.title as event_title, e.event_date, v.name as venue_name,
           b.total_amount, b.status, b.qr_code_data, b.created_at
    FROM bookings b
    JOIN events e ON b.event_id = e.id
    JOIN venues v ON e.venue_id = v.id
    WHERE b.user_id = ?
    ORDER BY b.created_at DESC
    """, (current_user["id"],))
    
    bookings = [dict(b) for b in cursor.fetchall()]

    for b in bookings:
        cursor.execute("SELECT seat_label, category, price FROM show_seats WHERE booking_id = ?", (b["id"],))
        b["seats"] = [dict(s) for s in cursor.fetchall()]

    conn.close()
    return bookings
