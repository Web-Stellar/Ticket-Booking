import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from app.database import get_db_connection
from app.models import VenueCreateRequest
from app.auth import require_role

router = APIRouter(prefix="/api/venues", tags=["Venues"])

@router.post("")
def create_venue(req: VenueCreateRequest, current_user: dict = Depends(require_role(["ADMIN"]))):
    """Admin creates a new venue with seat grid and assigns seat categories (VIP, PREMIUM, STANDARD)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    venue_id = str(uuid.uuid4())
    cursor.execute("""
    INSERT INTO venues (id, name, location, total_rows, seats_per_row, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (venue_id, req.name, req.location, req.total_rows, req.seats_per_row, datetime.utcnow().isoformat()))

    # Generate venue seats layout
    # Row A..B = VIP, Row C..D = PREMIUM, Rest = STANDARD
    row_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    seats_to_insert = []

    for row_idx in range(req.total_rows):
        row_num = row_idx + 1
        row_letter = row_letters[row_idx] if row_idx < len(row_letters) else f"R{row_num}"

        if row_idx < 2:
            cat = "VIP"
        elif row_idx < 4:
            cat = "PREMIUM"
        else:
            cat = "STANDARD"

        for seat_num in range(1, req.seats_per_row + 1):
            seat_id = str(uuid.uuid4())
            seat_label = f"{row_letter}{seat_num}"
            seats_to_insert.append((seat_id, venue_id, row_num, seat_num, seat_label, cat))

    cursor.executemany("""
    INSERT INTO venue_seats (id, venue_id, row_num, seat_num, seat_label, category)
    VALUES (?, ?, ?, ?, ?, ?)
    """, seats_to_insert)

    conn.commit()
    conn.close()

    return {
        "success": True,
        "venue_id": venue_id,
        "name": req.name,
        "total_seats": len(seats_to_insert),
        "message": f"Venue '{req.name}' created with {len(seats_to_insert)} seats across {req.total_rows} rows."
    }

@router.get("")
def list_venues():
    """Lists all registered venues."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, location, total_rows, seats_per_row, created_at FROM venues ORDER BY name ASC")
    venues = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return venues
