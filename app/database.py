import sqlite3
import os
import threading
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ticket_booking.db")
db_lock = threading.Lock()

def get_db_connection():
    """Returns a new SQLite connection configured for concurrent access."""
    conn = sqlite3.connect(DB_PATH, timeout=20.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    """Initializes the database schema and seeds initial admin, organiser, and default venue."""
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('ADMIN', 'ORGANISER', 'CUSTOMER')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Venues table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS venues (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            total_rows INTEGER NOT NULL,
            seats_per_row INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Venue seats template table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS venue_seats (
            id TEXT PRIMARY KEY,
            venue_id TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            seat_num INTEGER NOT NULL,
            seat_label TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('STANDARD', 'PREMIUM', 'VIP')),
            FOREIGN KEY (venue_id) REFERENCES venues(id) ON DELETE CASCADE
        );
        """)

        # Events table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL, -- Movie / Concert / Play
            venue_id TEXT NOT NULL,
            organiser_id TEXT NOT NULL,
            event_date TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (venue_id) REFERENCES venues(id),
            FOREIGN KEY (organiser_id) REFERENCES users(id)
        );
        """)

        # Event per-category pricing table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_prices (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('STANDARD', 'PREMIUM', 'VIP')),
            price REAL NOT NULL,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
            UNIQUE(event_id, category)
        );
        """)

        # Show seats table (per-event seat state)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS show_seats (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            seat_num INTEGER NOT NULL,
            seat_label TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK(status IN ('AVAILABLE', 'HELD', 'BOOKED', 'OFFERED')),
            held_by_user_id TEXT,
            hold_expires_at TIMESTAMP,
            booking_id TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
            FOREIGN KEY (held_by_user_id) REFERENCES users(id),
            FOREIGN KEY (booking_id) REFERENCES bookings(id)
        );
        """)

        # Bookings table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            booking_ref TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'CONFIRMED' CHECK(status IN ('CONFIRMED', 'CANCELLED')),
            qr_code_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (event_id) REFERENCES events(id)
        );
        """)

        # Waitlist table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('STANDARD', 'PREMIUM', 'VIP')),
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'OFFERED', 'CLAIMED', 'EXPIRED')),
            offered_at TIMESTAMP,
            offer_expires_at TIMESTAMP,
            offered_seat_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (offered_seat_id) REFERENCES show_seats(id)
        );
        """)

        # Email notifications log table (for previewing emails in UI)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            to_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            body_html TEXT NOT NULL,
            qr_code_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Indexes for fast lookup & concurrency operations
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_show_seats_event_status ON show_seats(event_id, status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_show_seats_hold_expiry ON show_seats(status, hold_expires_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_waitlist_event_category ON waitlist(event_id, category, status, created_at);")

        conn.commit()
        conn.close()
