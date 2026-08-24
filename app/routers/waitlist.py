from fastapi import APIRouter, HTTPException, Depends
from app.database import get_db_connection
from app.models import JoinWaitlistRequest, ClaimWaitlistOfferRequest
from app.auth import get_current_user
from app.services.waitlist_service import join_waitlist
from app.services.booking_service import confirm_booking_atomic
from app.services.socket_manager import ws_manager

router = APIRouter(prefix="/api/waitlist", tags=["Waitlist"])

@router.post("/join")
def join_category_waitlist(req: JoinWaitlistRequest, current_user: dict = Depends(get_current_user)):
    """Customer joins waitlist for a specific seat category when an event is sold out."""
    res = join_waitlist(user_id=current_user["id"], event_id=req.event_id, category=req.category.upper())
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@router.post("/claim")
async def claim_waitlist_offer(req: ClaimWaitlistOfferRequest, current_user: dict = Depends(get_current_user)):
    """Claim a time-limited waitlist offer before it expires and confirm the booking."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT w.id, w.event_id, w.user_id, w.category, w.status, w.offer_expires_at, w.offered_seat_id
    FROM waitlist w
    WHERE w.id = ?
    """, (req.waitlist_id,))
    waitlist_entry = cursor.fetchone()

    if not waitlist_entry:
        conn.close()
        raise HTTPException(status_code=404, detail="Waitlist offer entry not found.")

    if waitlist_entry["user_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="This waitlist offer belongs to another user.")

    if waitlist_entry["status"] != "OFFERED":
        conn.close()
        raise HTTPException(status_code=400, detail=f"Offer is not active. Current status: {waitlist_entry['status']}")

    seat_id = waitlist_entry["offered_seat_id"]
    event_id = waitlist_entry["event_id"]

    # Mark waitlist claimed
    cursor.execute("UPDATE waitlist SET status = 'CLAIMED' WHERE id = ?", (req.waitlist_id,))
    conn.commit()
    conn.close()

    # Confirm booking for offered seat
    booking_res = confirm_booking_atomic(user_id=current_user["id"], event_id=event_id, seat_ids=[seat_id])

    if not booking_res["success"]:
        raise HTTPException(status_code=400, detail=booking_res["message"])

    await ws_manager.broadcast_seat_update(event_id, {
        "type": "SEAT_BOOKED",
        "event_id": event_id,
        "seat_ids": [seat_id]
    })

    return {
        "success": True,
        "message": "Waitlist offer claimed and booking confirmed!",
        "booking": booking_res
    }

@router.get("/my")
def get_my_waitlist_entries(current_user: dict = Depends(get_current_user)):
    """Retrieves all active and historical waitlist entries for the logged-in user."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT w.id, w.event_id, e.title as event_title, w.category, w.status, 
           w.offered_at, w.offer_expires_at, w.created_at, s.seat_label
    FROM waitlist w
    JOIN events e ON w.event_id = e.id
    LEFT JOIN show_seats s ON w.offered_seat_id = s.id
    WHERE w.user_id = ?
    ORDER BY w.created_at DESC
    """, (current_user["id"],))

    entries = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return entries
