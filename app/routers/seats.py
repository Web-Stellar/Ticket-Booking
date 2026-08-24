from fastapi import APIRouter, HTTPException, Depends
from app.database import get_db_connection
from app.models import HoldSeatsRequest, ReleaseSeatsRequest
from app.auth import get_current_user
from app.services.hold_service import hold_seats_atomic, release_held_seats
from app.services.socket_manager import ws_manager

router = APIRouter(prefix="/api/seats", tags=["Seats"])

@router.get("/event/{event_id}")
def get_visual_seat_map(event_id: str):
    """Retrieves current visual seat map grid data for an event show."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, row_num, seat_num, seat_label, category, price, status, held_by_user_id, hold_expires_at
    FROM show_seats
    WHERE event_id = ?
    ORDER BY row_num ASC, seat_num ASC
    """, (event_id,))
    seats = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not seats:
        raise HTTPException(status_code=404, detail="Seat map not found for event.")

    return {"event_id": event_id, "seats": seats}

@router.post("/hold")
async def hold_seats(req: HoldSeatsRequest, current_user: dict = Depends(get_current_user)):
    """Places a temporary hold on selected seats with configurable TTL (10 minutes) and broadcasts update."""
    res = hold_seats_atomic(user_id=current_user["id"], event_id=req.event_id, seat_ids=req.seat_ids)
    if not res["success"]:
        raise HTTPException(status_code=409, detail=res["message"])

    # Broadcast seat map update via WebSockets to all connected clients
    await ws_manager.broadcast_seat_update(req.event_id, {
        "type": "SEAT_HELD",
        "event_id": req.event_id,
        "seat_ids": req.seat_ids,
        "held_by": current_user["id"],
        "expires_at": res["expires_at"]
    })

    return res

@router.post("/release")
async def release_seats(req: ReleaseSeatsRequest, current_user: dict = Depends(get_current_user)):
    """Releases seats currently held by the customer (e.g. checkout abandonment)."""
    res = release_held_seats(user_id=current_user["id"], event_id=req.event_id, seat_ids=req.seat_ids)
    
    await ws_manager.broadcast_seat_update(req.event_id, {
        "type": "SEAT_RELEASED",
        "event_id": req.event_id,
        "seat_ids": req.seat_ids
    })

    return res
