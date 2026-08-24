import os
import sys
import concurrent.futures
import time

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import init_db, get_db_connection
from app.main import seed_demo_data
from app.services.hold_service import hold_seats_atomic

def run_concurrency_test():
    """Simulates 10 threads concurrently attempting to hold the EXACT SAME seat."""
    print("=" * 60)
    print("STARTING CONCURRENCY RACE CONDITION TEST")
    print("=" * 60)

    init_db()
    seed_demo_data()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch first available seat from database
    cursor.execute("SELECT id, event_id, seat_label FROM show_seats WHERE status = 'AVAILABLE' LIMIT 1")
    target_seat = cursor.fetchone()

    if not target_seat:
        conn.close()
        print("ERROR: No available seats found for concurrency test.")
        return

    seat_id = target_seat["id"]
    event_id = target_seat["event_id"]
    seat_label = target_seat["seat_label"]

    cursor.execute("SELECT id FROM users LIMIT 10")
    user_rows = cursor.fetchall()
    user_ids = [u["id"] for u in user_rows]
    conn.close()

    print(f"Targeting Seat: '{seat_label}' (ID: {seat_id}) for Event ID: {event_id}")
    print("Launching 10 concurrent threads attempting to hold this seat simultaneously...\n")

    results = []

    def attempt_hold(thread_num):
        user_id = user_ids[thread_num % len(user_ids)]
        res = hold_seats_atomic(user_id=user_id, event_id=event_id, seat_ids=[seat_id])
        return (thread_num, res)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(attempt_hold, i + 1) for i in range(10)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    successes = [r for r in results if r[1]["success"]]
    failures = [r for r in results if not r[1]["success"]]

    print("--- CONCURRENCY TEST RESULTS ---")
    for r in results:
        status_text = "SUCCESS (HELD)" if r[1]["success"] else f"FAILED ({r[1]['message']})"
        print(f"Thread #{r[0]}: {status_text}")

    print("\n--- SUMMARY ---")
    print(f"Total Threads Attempted: {len(results)}")
    print(f"Successful Holds: {len(successes)}")
    print(f"Blocked Conflicts: {len(failures)}")

    assert len(successes) == 1, f"Concurrency failure! Expected exactly 1 success, got {len(successes)}"
    print("\n[PASSED] CONCURRENCY TEST PASSED! Exactly ONE thread acquired the seat hold.")

if __name__ == "__main__":
    run_concurrency_test()
