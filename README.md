# 🎟️ Ticket Booking System Platform

A production-grade full-stack ticket booking platform built with **Python (FastAPI)**, **SQLite/PostgreSQL**, **WebSockets**, **Tailwind CSS**, and **QR Code Ticket Generation**.

Features an interactive visual seat map, configurable seat hold TTL auto-release, atomic concurrency race condition protection, category-based waitlists with automated time-limited cascading offers on cancellation, and email delivery with inline QR tickets.

---

## 📸 Key Capabilities

1. **Role-Based Access Control (RBAC)**:
   - **Customer**: Browse events, view live visual seat map, hold seats, confirm bookings, receive QR code tickets via email, view booking history, cancel bookings, join waitlists.
   - **Organiser**: Create movie/concert listings, assign venue layouts, set per-category pricing (VIP, PREMIUM, STANDARD), view sales summaries and revenue per event.
   - **Admin**: Create venues with customizable row counts and seats per row with auto-generated category grids.

2. **Interactive Visual Seat Map & Real-time WebSockets**:
   - Live color-coded seat status: `AVAILABLE` (Green), `HELD` (Yellow), `BOOKED` (Red), `OFFERED` (Blue).
   - Real-time seat map synchronization via WebSockets (`/ws/seats/{event_id}`).

3. **Seat Hold & TTL Auto-Release**:
   - Places 10-minute configurable TTL hold on seats during checkout.
   - Background sweeper auto-releases abandoned seat holds every 5 seconds and updates all live seat maps.

4. **Concurrency Protection**:
   - Atomic conditional updates (`UPDATE ... WHERE status = 'AVAILABLE'`) and row-level database locks ensure simultaneous booking attempts for the same seat **never conflict or double-book**.

5. **Waitlist Management & Time-Limited Auto-Assignment**:
   - FIFO waitlists per seat category (`STANDARD`, `PREMIUM`, `VIP`) when an event is sold out.
   - On booking cancellation, released seats are automatically offered to the next waitlisted customer with a 5-minute time-limited claim link.
   - If unclaimed before expiry, the offer cascades automatically to the next customer in line.

6. **Dynamic QR Code Ticket Generation**:
   - Generates unique base64 PNG QR code ticket containing verification payload.
   - Delivers HTML confirmation email with inline QR ticket image (previewable in built-in email inbox UI tab).

---

## 🚀 Quick Start Guide

### Prerequisites
* Python 3.9+
* Pip package manager

### 1. Installation
Clone or navigate to the repository directory:
```bash
cd E:\ticket-booking-system
```

Install dependencies:
```bash
python -m pip install fastapi uvicorn qrcode pydantic pyjwt bcrypt websockets jinja2
```

### 2. Environment Setup
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Default `.env` contents:
```ini
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:///./ticket_booking.db
JWT_SECRET=super_secret_jwt_key_ticket_booking_2026
SEAT_HOLD_TTL_MINUTES=10
WAITLIST_OFFER_TTL_MINUTES=5
SWEEPER_INTERVAL_SECONDS=5
```

### 3. Running the Server
Launch using Python runner:
```bash
python run.py
```
Or directly with Uvicorn:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at: **`http://localhost:8000`**

---

## 👥 Preset Demo Accounts

The system automatically seeds demo data on first launch:

| Role | Email | Password | Access Rights |
| :--- | :--- | :--- | :--- |
| **Customer** | `john@example.com` | `cust123` | Book seats, view QR tickets, join waitlists |
| **Customer** | `alice@example.com` | `cust123` | Secondary customer for concurrency testing |
| **Organiser** | `organiser@cinema.com` | `org123` | Create listings, set pricing, view revenue |
| **Admin** | `admin@tickets.com` | `admin123` | Create venues, configure seat layouts |

*Quick login buttons are built directly into the top navigation header!*

---

## 🛠️ REST API Documentation

### Authentication (`/api/auth`)
* `POST /api/auth/register`: Register new user (`ADMIN`, `ORGANISER`, `CUSTOMER`).
* `POST /api/auth/login`: Authenticate and receive JWT access token.
* `GET /api/auth/me`: Get current authenticated user profile.

### Venues (`/api/venues`)
* `POST /api/venues`: Admin creates venue with row count and seats per row.
* `GET /api/venues`: List all venues.

### Events (`/api/events`)
* `POST /api/events`: Organiser publishes event listing with per-category pricing.
* `GET /api/events`: List active events with available seat counts.
* `GET /api/events/{event_id}`: Retrieve detailed event information and category stats.

### Seats & Holds (`/api/seats`)
* `GET /api/seats/event/{event_id}`: Get visual seat map grid status.
* `POST /api/seats/hold`: Hold seats atomically (`seat_ids: ["id1", "id2"]`).
* `POST /api/seats/release`: Abandon held seats manually.

### Bookings & Tickets (`/api/bookings`)
* `POST /api/bookings/confirm`: Confirm booking for held seats, generate QR code, and send email.
* `POST /api/bookings/cancel`: Cancel booking and trigger waitlist auto-assignment.
* `GET /api/bookings/my`: View booking history and QR code tickets.

### Waitlist (`/api/waitlist`)
* `POST /api/waitlist/join`: Join sold-out category waitlist queue.
* `POST /api/waitlist/claim`: Claim active time-limited waitlist offer.
* `GET /api/waitlist/my`: View active waitlist entries and countdown timers.

### Organiser Dashboard (`/api/organiser`)
* `GET /api/organiser/summary`: View revenue breakdown and ticket sales metrics.

### Email Inbox Log (`/api/emails`)
* `GET /api/emails/inbox`: Preview sent emails with embedded QR code tickets.

---

## 🧪 Running Concurrency & Unit Tests

Run the multi-threaded race condition test (simulates 10 threads fighting for 1 seat):
```bash
python tests/test_concurrency.py
```

Run waitlist auto-assignment and cancellation tests:
```bash
python tests/test_ttl_and_waitlist.py
```

---

## 📐 System Design Write-Up

A comprehensive 800-word system design write-up covering seat hold TTL, concurrency prevention algorithms, waitlist state machine, and data models is located at:
**[`docs/system_design.md`](file:///E:/ticket-booking-system/docs/system_design.md)**

---

## 🌐 Hosted Application Deployment Guide

### Option 1: Render / Railway (Recommended for Full-Stack)
1. Push repository to GitHub.
2. Create a new Web Service on Render or Railway.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Set environment variables from `.env.example`.

### Option 2: Vercel (Serverless Backend + Static Frontend)
1. Deploy frontend static files (`app/templates`, `app/static`) to Vercel.
2. Deploy FastAPI backend using Vercel Serverless Functions (`api/index.py`).
