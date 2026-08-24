from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

# --- Auth Models ---
class UserRegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str = Field(default="CUSTOMER", description="ADMIN, ORGANISER, or CUSTOMER")

class UserLoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    name: str
    role: str

# --- Venue Models ---
class VenueCreateRequest(BaseModel):
    name: str
    location: str
    total_rows: int = Field(gt=0, le=26, description="Rows A-Z")
    seats_per_row: int = Field(gt=0, le=50)

# --- Event Models ---
class EventCategoryPrice(BaseModel):
    category: str  # STANDARD, PREMIUM, VIP
    price: float = Field(gt=0)

class EventCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    category: str  # Movie, Concert, Play
    venue_id: str
    event_date: str  # ISO string: "2026-09-01T19:00:00"
    prices: List[EventCategoryPrice]

# --- Seat Hold / Booking Requests ---
class HoldSeatsRequest(BaseModel):
    event_id: str
    seat_ids: List[str]

class ReleaseSeatsRequest(BaseModel):
    event_id: str
    seat_ids: List[str]

class ConfirmBookingRequest(BaseModel):
    event_id: str
    seat_ids: List[str]

class CancelBookingRequest(BaseModel):
    booking_id: str

# --- Waitlist Models ---
class JoinWaitlistRequest(BaseModel):
    event_id: str
    category: str  # STANDARD, PREMIUM, VIP

class ClaimWaitlistOfferRequest(BaseModel):
    waitlist_id: str
