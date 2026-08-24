# Ticket Booking System - System Design Architecture

## 1. High-Level Architecture Overview
The Ticket Booking System is designed to handle high-demand movie and concert ticketing where race conditions, inventory contention, and checkout abandonment are critical challenges. The architecture consists of a stateless API application server, a transactional relational store (SQLite/PostgreSQL with WAL mode), a background event sweeper engine, WebSockets for instant seat map synchronization, and an email delivery pipeline with embedded dynamic QR codes.

---

## 2. Seat Hold TTL & Auto-Release Mechanism
When a customer selects seats, the system places a temporary **hold** with a configurable Time-To-Live (TTL) of 10 minutes. 

* **Hold Creation**: The backend updates the seat record, setting `status = 'HELD'`, `held_by_user_id = <user_id>`, and `hold_expires_at = NOW() + 10 MINS`.
* **Checkout Abandonment**: If a customer navigates away or fails to confirm payment before `hold_expires_at`, the seat is abandoned.
* **Auto-Release Sweeper**: A lightweight background sweeper job executes every 5 seconds. It queries for expired holds (`status = 'HELD' AND hold_expires_at <= NOW()`), resets their state to `'AVAILABLE'`, and clears the user binding.
* **Real-Time Push**: Immediately upon auto-release, a WebSocket event (`SEAT_RELEASED`) broadcasts the updated state to all clients currently viewing that show's visual seat map.

---

## 3. Concurrency Protection & Race Condition Prevention
To prevent two customers from holding or booking the exact same seat simultaneously, the system employs **Atomic Conditional Updates** backed by database row-level transaction isolation (`BEGIN IMMEDIATE`).

* **Atomic State Mutation**: The hold operation executes within a strict transaction:
  ```sql
  UPDATE show_seats 
  SET status = 'HELD', held_by_user_id = ?, hold_expires_at = ?
  WHERE id IN (...) AND event_id = ? AND status = 'AVAILABLE';
  ```
* **Conflict Detection**: The database evaluates the condition atomically. If two users submit simultaneous hold requests for seat `A1`, exactly **one** update statement succeeds (`affected_rows == len(seats)`). The losing transaction sees `affected_rows < len(seats)`, triggers an immediate rollback, and returns a `409 Conflict` response: *"Seat A1 is no longer available"*.
* **No Double Booking**: Booking confirmation follows the same atomic pattern, ensuring seats transition from `HELD` to `BOOKED` safely.

---

## 4. Waitlist Auto-Assignment & Time-Limited Offer Flow
When an event category (e.g., VIP, Premium, Standard) sells out, customers can join a category-specific FIFO waitlist.

```
[Booking Cancelled] ──> [Seat Released] ──> [Fetch FIFO Waitlist] ──> [Set OFFERED & 5m TTL] ──> [Email Claim Link]
                                                                                                            │
                                                                   ┌────────────────────────────────────────┴──────────────────┐
                                                                   ▼                                                           ▼
                                                        [User Claims in < 5m]                                      [Offer Expires > 5m]
                                                                   │                                                           │
                                                      [Seat Status: BOOKED]                                       [Offer Marked EXPIRED]
                                                                                                                               │
                                                                                                                  [Cascade to Next User in FIFO]
```

1. **Trigger on Cancellation**: When a customer cancels a booking, the associated seats transition to `AVAILABLE`.
2. **Auto-Assignment Engine**: The system queries the waitlist table for `status = 'PENDING'` filtered by `event_id` and `category`, sorted by `created_at ASC` (FIFO).
3. **Time-Limited Offer**: The first waitlisted customer is selected. The seat status changes to `OFFERED`, bound to the customer's ID with `offer_expires_at = NOW() + 5 MINS`. An automated email is dispatched containing a unique claim link.
4. **Cascading Offer Expiry**: If the customer claims the offer within 5 minutes, the seat is booked. If the offer expires, the sweeper marks the waitlist record `EXPIRED`, resets the seat to `AVAILABLE`, and automatically triggers the assignment flow for the **next customer in line**.

---

## 5. Seat Map Data Model & Real-Time Updates
The relational model separates venue physical layout from per-event show instances:
* `venues` & `venue_seats`: Defines static physical seat grids and categories (`STANDARD`, `PREMIUM`, `VIP`).
* `events` & `show_seats`: Clones venue layouts for each event show time, maintaining live status (`AVAILABLE`, `HELD`, `BOOKED`, `OFFERED`), per-category prices, and expiration timestamps.
* **WebSocket Synchronization**: Clients subscribe to `/ws/seats/{event_id}`. Any status mutation (`HELD`, `RELEASED`, `BOOKED`) broadcasts a JSON payload, prompting visual grid updates without full page reloads.

---

## 6. QR Code Generation & Email Delivery
Upon booking confirmation:
1. Server constructs a cryptographically unique payload: `REF:<booking_ref>|EVT:<title>|SEATS:<labels>|USER:<email>`.
2. The `qrcode` generator produces a 300 DPI PNG image, encoded to base64.
3. An inline HTML email is dispatched via SMTP/Nodemailer containing ticket metadata and the embedded QR code image for scanning at the venue.
