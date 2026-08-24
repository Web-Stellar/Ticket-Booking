import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from app.database import get_db_connection
from app.models import EventCreateRequest
from app.auth import require_role

router = APIRouter(prefix="/api/events", tags=["Events"])

@router.post("")
def create_event(req: EventCreateRequest, current_user: dict = Depends(require_role(["ORGANISER", "ADMIN"]))):
    """Organiser creates movie or event listing and initializes per-show seat layout with pricing."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check venue
    cursor.execute("SELECT id, name FROM venues WHERE id = ?", (req.venue_id,))
    venue = cursor.fetchone()
    if not venue:
        conn.close()
        raise HTTPException(status_code=404, detail="Venue not found.")

    event_id = str(uuid.uuid4())
    now_str = datetime.utcnow().isoformat()

    # Insert Event
    cursor.execute("""
    INSERT INTO events (id, title, description, category, venue_id, organiser_id, event_date, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (event_id, req.title, req.description, req.category, req.venue_id, current_user["id"], req.event_date, now_str))

    # Insert Per-Category Prices
    price_map = {}
    for p in req.prices:
        cat = p.category.upper()
        if cat not in ("STANDARD", "PREMIUM", "VIP"):
            conn.close()
            raise HTTPException(status_code=400, detail=f"Invalid category '{cat}'")
        price_map[cat] = p.price
        cursor.execute("""
        INSERT INTO event_prices (id, event_id, category, price)
        VALUES (?, ?, ?, ?)
        """, (str(uuid.uuid4()), event_id, cat, p.price))

    # Fetch Venue seat templates and clone to show_seats
    cursor.execute("""
    SELECT row_num, seat_num, seat_label, category FROM venue_seats WHERE venue_id = ?
    """, (req.venue_id,))
    venue_seats = cursor.fetchall()

    show_seats_to_insert = []
    for vs in venue_seats:
        cat = vs["category"]
        price = price_map.get(cat, 50.0)  # Default fallback price if omitted
        show_seat_id = str(uuid.uuid4())
        show_seats_to_insert.append((
            show_seat_id, event_id, vs["row_num"], vs["seat_num"], vs["seat_label"], cat, price, 'AVAILABLE', now_str
        ))

    cursor.executemany("""
    INSERT INTO show_seats (id, event_id, row_num, seat_num, seat_label, category, price, status, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, show_seats_to_insert)

    conn.commit()
    conn.close()

    return {
        "success": True,
        "event_id": event_id,
        "title": req.title,
        "venue_name": venue["name"],
        "total_seats_generated": len(show_seats_to_insert),
        "message": f"Event '{req.title}' created with {len(show_seats_to_insert)} seat instances."
    }

@router.get("")
def list_events(category: str = None):
    """Lists events with available seat counts and per-category pricing."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT e.id, e.title, e.description, e.category, e.event_date, v.name as venue_name, v.location,
           u.name as organiser_name,
           COUNT(s.id) as total_seats,
           SUM(CASE WHEN s.status = 'AVAILABLE' THEN 1 ELSE 0 END) as available_seats
    FROM events e
    JOIN venues v ON e.venue_id = v.id
    JOIN users u ON e.organiser_id = u.id
    LEFT JOIN show_seats s ON e.id = s.event_id
    """
    params = []
    if category:
        query += " WHERE e.category = ?"
        params.append(category)
    
    query += " GROUP BY e.id ORDER BY e.event_date ASC"
    cursor.execute(query, params)
    events = [dict(r) for r in cursor.fetchall()]

    # Attach pricing
    for evt in events:
        cursor.execute("SELECT category, price FROM event_prices WHERE event_id = ?", (evt["id"],))
        evt["prices"] = [dict(p) for p in cursor.fetchall()]

    conn.close()
    return events

@router.get("/{event_id}")
def get_event_details(event_id: str):
    """Retrieves event details and category availability."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT e.id, e.title, e.description, e.category, e.event_date, v.name as venue_name, v.location,
           v.total_rows, v.seats_per_row, u.name as organiser_name
    FROM events e
    JOIN venues v ON e.venue_id = v.id
    JOIN users u ON e.organiser_id = u.id
    WHERE e.id = ?
    """, (event_id,))
    event = cursor.fetchone()

    if not event:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")

    evt_dict = dict(event)

    cursor.execute("SELECT category, price FROM event_prices WHERE event_id = ?", (event_id,))
    evt_dict["prices"] = [dict(p) for p in cursor.fetchall()]

    # Category availability counts
    cursor.execute("""
    SELECT category, 
           COUNT(*) as total, 
           SUM(CASE WHEN status = 'AVAILABLE' THEN 1 ELSE 0 END) as available,
           SUM(CASE WHEN status = 'HELD' THEN 1 ELSE 0 END) as held,
           SUM(CASE WHEN status = 'BOOKED' THEN 1 ELSE 0 END) as booked
    FROM show_seats
    WHERE event_id = ?
    GROUP BY category
    """, (event_id,))
    evt_dict["category_stats"] = [dict(s) for s in cursor.fetchall()]

    conn.close()
    return evt_dict
