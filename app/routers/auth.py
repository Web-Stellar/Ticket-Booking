import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status
from app.database import get_db_connection
from app.models import UserRegisterRequest, UserLoginRequest, TokenResponse
from app.auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.post("/register", response_model=TokenResponse)
def register_user(req: UserRegisterRequest):
    role = req.role.upper()
    if role not in ("ADMIN", "ORGANISER", "CUSTOMER"):
        raise HTTPException(status_code=400, detail="Invalid role. Choose ADMIN, ORGANISER, or CUSTOMER.")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email = ?", (req.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered.")

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(req.password)

    cursor.execute("""
    INSERT INTO users (id, email, password_hash, name, role, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, req.email, pw_hash, req.name, role, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    token = create_access_token({"sub": user_id, "role": role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user_id,
        "email": req.email,
        "name": req.name,
        "role": role
    }

@router.post("/login", response_model=TokenResponse)
def login_user(req: UserLoginRequest):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, email, password_hash, name, role FROM users WHERE email = ?", (req.email,))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token({"sub": user["id"], "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"]
    }

@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
