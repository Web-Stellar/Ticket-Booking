from fastapi import APIRouter, Depends
from app.database import get_db_connection
from app.auth import require_role

router = APIRouter(prefix="/api/organiser", tags=["Organiser Dashboard"])

@router.get("/summary")
def get_organiser_summary(current_user: dict = Depends(require_role(["ORGANISER", "ADMIN"]))):
    """Organiser dashboard: lists booking summary and total revenue per event listing."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT e.id as event_id, e.title as event_title, e.category, e.event_date, v.name as venue_name,
           COUNT(s.id) as total_seats,
           SUM(CASE WHEN s.status = 'BOOKED' THEN 1 ELSE 0 END) as booked_seats,
           SUM(CASE WHEN s.status = 'HELD' THEN 1 ELSE 0 END) as held_seats,
           SUM(CASE WHEN s.status = 'AVAILABLE' THEN 1 ELSE 0 END) as available_seats,
           COALESCE(SUM(CASE WHEN s.status = 'BOOKED' THEN s.price ELSE 0 END), 0.0) as total_revenue
    FROM events e
    JOIN venues v ON e.venue_id = v.id
    LEFT JOIN show_seats s ON e.id = s.event_id
    """
    params = []

    # If organiser (not admin), filter by organiser_id
    if current_user["role"] == "ORGANISER":
        query += " WHERE e.organiser_id = ?"
        params.append(current_user["id"])

    query += " GROUP BY e.id ORDER BY e.event_date DESC"
    cursor.execute(query, params)
    events_summary = [dict(r) for r in cursor.fetchall()]

    # Global summary stats
    total_events = len(events_summary)
    grand_revenue = sum(e["total_revenue"] for e in events_summary)
    total_tickets_sold = sum(e["booked_seats"] for e in events_summary)

    conn.close()

    return {
        "grand_revenue": grand_revenue,
        "total_events": total_events,
        "total_tickets_sold": total_tickets_sold,
        "events": events_summary
    }
