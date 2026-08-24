import os
import uuid
import qrcode
import io
import base64
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
from app.database import get_db_connection

def generate_qr_code_base64(data_string: str) -> str:
    """Generates a high-resolution QR code image and returns it as base64 string."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def dispatch_smtp_email_if_configured(to_email: str, subject: str, body_html: str, qr_code_base64: str = None):
    """Attempts to send a real email over SMTP if credentials are configured in .env."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_from = os.getenv("SMTP_FROM", "tickets@eventmaster.com")

    if not smtp_host or not smtp_user or not smtp_pass:
        # SMTP not configured - silent fallback to web UI inbox viewer
        return

    try:
        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = to_email

        msg_alternative = MIMEMultipart("alternative")
        msg.attach(msg_alternative)

        msg_html = MIMEText(body_html, "html")
        msg_alternative.attach(msg_html)

        # Attach QR Code Image if present
        if qr_code_base64:
            img_data = base64.b64decode(qr_code_base64)
            img = MIMEImage(img_data, _subtype="png")
            img.add_header("Content-ID", "<qrcode_ticket>")
            img.add_header("Content-Disposition", "inline", filename="qr_ticket.png")
            msg.attach(img)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [to_email], msg.as_string())
    except Exception as e:
        print(f"SMTP Dispatch notice (logged locally): {e}")

def send_booking_confirmation_email(user_email: str, user_name: str, booking_ref: str, event_title: str, event_date: str, venue_name: str, seats_list: list, total_amount: float, qr_code_base64: str):
    """Sends confirmed ticket email with inline embedded QR code and logs to DB for instant preview."""
    subject = f"🎟️ Confirmed Booking: {booking_ref} - {event_title}"
    seats_str = ", ".join(seats_list)
    
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; background-color: #ffffff;">
        <h2 style="color: #2563eb; margin-top: 0;">Your Ticket Booking is Confirmed!</h2>
        <p>Hi <strong>{user_name}</strong>,</p>
        <p>Thank you for your purchase. Here are your booking details:</p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding: 8px 0; color: #4a5568;">Booking Ref:</td><td style="padding: 8px 0; font-weight: bold;">{booking_ref}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding: 8px 0; color: #4a5568;">Event:</td><td style="padding: 8px 0; font-weight: bold;">{event_title}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding: 8px 0; color: #4a5568;">Venue:</td><td style="padding: 8px 0;">{venue_name}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding: 8px 0; color: #4a5568;">Date & Time:</td><td style="padding: 8px 0;">{event_date}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding: 8px 0; color: #4a5568;">Seats:</td><td style="padding: 8px 0; color: #16a34a; font-weight: bold;">{seats_str}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding: 8px 0; color: #4a5568;">Total Paid:</td><td style="padding: 8px 0; font-weight: bold;">${total_amount:.2f}</td></tr>
        </table>
        <div style="text-align: center; margin: 24px 0;">
            <p style="font-weight: bold; color: #4a5568;">Present this QR Code at the venue entrance:</p>
            <img src="data:image/png;base64,{qr_code_base64}" alt="QR Ticket" style="width: 200px; height: 200px; border: 4px solid #cbd5e1; border-radius: 8px;" />
        </div>
        <p style="color: #718096; font-size: 12px; text-align: center;">Ticket Booking Platform System • Automatically Generated</p>
    </div>
    """

    # 1. Log email to database for live web UI preview
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO emails (id, to_email, subject, body_html, qr_code_data, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), user_email, subject, body_html, qr_code_base64, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    # 2. Optionally dispatch real email over SMTP if configured in .env
    dispatch_smtp_email_if_configured(user_email, subject, body_html, qr_code_base64)

def send_waitlist_offer_email(user_email: str, user_name: str, event_title: str, category: str, seat_label: str, offer_expires_at: str, claim_url: str):
    """Sends time-limited waitlist offer notification email to the customer."""
    subject = f"⚡ Great News! A seat is available for {event_title}"
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; background-color: #ffffff;">
        <h2 style="color: #ea580c; margin-top: 0;">Waitlist Seat Available!</h2>
        <p>Hi <strong>{user_name}</strong>,</p>
        <p>A seat has just become available in your waitlisted category <strong>({category})</strong> for <strong>{event_title}</strong>!</p>
        <p>Assigned Seat: <strong style="color: #2563eb;">{seat_label}</strong></p>
        <p style="color: #dc2626; font-weight: bold;">⏰ You have until {offer_expires_at} UTC to claim this seat before it passes to the next person in line.</p>
        <div style="text-align: center; margin: 28px 0;">
            <a href="{claim_url}" style="background-color: #16a34a; color: white; text-decoration: none; padding: 14px 28px; border-radius: 6px; font-weight: bold; font-size: 16px;">Claim & Book Now</a>
        </div>
    </div>
    """

    # 1. Log email to database for live web UI preview
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO emails (id, to_email, subject, body_html, qr_code_data, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), user_email, subject, body_html, None, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    # 2. Optionally dispatch real email over SMTP if configured in .env
    dispatch_smtp_email_if_configured(user_email, subject, body_html)
