from fastapi import APIRouter
from app.database import get_db_connection

router = APIRouter(prefix="/api/emails", tags=["Emails"])

@router.get("/inbox")
def get_email_inbox():
    """Returns list of all sent emails with QR tickets for instant previewing in web UI."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, to_email, subject, body_html, qr_code_data, created_at 
    FROM emails 
    ORDER BY created_at DESC
    """)
    emails = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return emails
