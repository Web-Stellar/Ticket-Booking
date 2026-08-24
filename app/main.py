import os
import asyncio
import uuid
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from app.database import init_db, get_db_connection
from app.auth import hash_password
from app.services.socket_manager import ws_manager
from app.jobs.sweeper import run_sweeper_loop

from app.routers import auth, venues, events, seats, bookings, waitlist, organiser, emails

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup lifecycle: initializes database, seeds demo data, and runs TTL sweeper background loop."""
    init_db()
    seed_demo_data()
    sweeper_task = asyncio.create_task(run_sweeper_loop())
    yield
    sweeper_task.cancel()

app = FastAPI(
    title="Ticket Booking System API",
    description="Full-stack Ticket Booking System with real-time visual seat map, seat hold TTL, waitlist auto-assignment, and QR code tickets.",
    version="1.0.0",
    lifespan=lifespan
)

# Mount Routers
app.include_router(auth.router)
app.include_router(venues.router)
app.include_router(events.router)
app.include_router(seats.router)
app.include_router(bookings.router)
app.include_router(waitlist.router)
app.include_router(organiser.router)
app.include_router(emails.router)

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.websocket("/ws/seats/{event_id}")
async def websocket_seat_updates(websocket: WebSocket, event_id: str):
    """WebSocket endpoint for broadcasting real-time seat map changes to clients."""
    await ws_manager.connect(websocket, event_id)
    try:
        while True:
            # Keep connection open and receive heartbeats
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, event_id)

@app.get("/", response_class=HTMLResponse)
def serve_index():
    """Serves main web application dashboard."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Ticket Booking System Backend API Running</h1>"

def seed_demo_data():
    """Seeds initial users, venue, and demo event listings if database is empty."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM users")
    if cursor.fetchone()["count"] > 0:
        conn.close()
        return  # Already seeded

    now_str = datetime.utcnow().isoformat()

    # Create Default Users
    admin_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    cust1_id = str(uuid.uuid4())
    cust2_id = str(uuid.uuid4())

    cursor.execute("""
    INSERT INTO users (id, email, password_hash, name, role, created_at)
    VALUES 
    (?, 'admin@tickets.com', ?, 'System Admin', 'ADMIN', ?),
    (?, 'organiser@cinema.com', ?, 'Starlight Events', 'ORGANISER', ?),
    (?, 'john@example.com', ?, 'John Doe', 'CUSTOMER', ?),
    (?, 'alice@example.com', ?, 'Alice Smith', 'CUSTOMER', ?)
    """, (
        admin_id, hash_password("admin123"), now_str,
        org_id, hash_password("org123"), now_str,
        cust1_id, hash_password("cust123"), now_str,
        cust2_id, hash_password("cust123"), now_str
    ))

    # Create Venue 1: Grand Cinema Hall
    v1_id = str(uuid.uuid4())
    cursor.execute("""
    INSERT INTO venues (id, name, location, total_rows, seats_per_row, created_at)
    VALUES (?, 'Grand Cinema Hall', 'Downtown Plaza, NY', 6, 8, ?)
    """, (v1_id, now_str))

    # Generate venue seats layout (Rows A..F x 8 seats = 48 seats)
    row_letters = "ABCDEF"
    venue_seats = []
    for r_idx in range(6):
        r_num = r_idx + 1
        r_letter = row_letters[r_idx]
        cat = "VIP" if r_idx < 2 else ("PREMIUM" if r_idx < 4 else "STANDARD")
        for s_num in range(1, 9):
            seat_label = f"{r_letter}{s_num}"
            venue_seats.append((str(uuid.uuid4()), v1_id, r_num, s_num, seat_label, cat))

    cursor.executemany("""
    INSERT INTO venue_seats (id, venue_id, row_num, seat_num, seat_label, category)
    VALUES (?, ?, ?, ?, ?, ?)
    """, venue_seats)

    # Create Event 1: Cyberpunk Odyssey 2099 Movie
    e1_id = str(uuid.uuid4())
    event_date = (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%dT19:30:00")
    cursor.execute("""
    INSERT INTO events (id, title, description, category, venue_id, organiser_id, event_date, created_at)
    VALUES (?, 'Cyberpunk Odyssey 2099', 'Blockbuster sci-fi action thriller in 4K IMAX Laser.', 'Movie', ?, ?, ?, ?)
    """, (e1_id, v1_id, org_id, event_date, now_str))

    # Per-Category Prices for Event 1
    prices = [("VIP", 30.0), ("PREMIUM", 20.0), ("STANDARD", 12.0)]
    for cat, pr in prices:
        cursor.execute("INSERT INTO event_prices (id, event_id, category, price) VALUES (?, ?, ?, ?)",
                       (str(uuid.uuid4()), e1_id, cat, pr))

    # Generate show_seats for Event 1
    price_dict = dict(prices)
    show_seats = []
    for vs in venue_seats:
        s_id, _, r_num, s_num, s_label, cat = vs
        pr = price_dict[cat]
        show_seats.append((str(uuid.uuid4()), e1_id, r_num, s_num, s_label, cat, pr, 'AVAILABLE', now_str))

    cursor.executemany("""
    INSERT INTO show_seats (id, event_id, row_num, seat_num, seat_label, category, price, status, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, show_seats)

    conn.commit()
    conn.close()
    print("Demo dataset seeded successfully! Default login credentials created.")
