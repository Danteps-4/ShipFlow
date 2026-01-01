from cryptography.fernet import Fernet
import os
import base64

# Generate a key if not present (dev only)
# In production, ENCRYPTION_KEY must be set (32 url-safe base64-encoded bytes)
def get_key():
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        # Fallback for dev ONLY. In prod this should fail ideally.
        if os.getenv("ENV") == "production":
             raise RuntimeError("Missing ENCRYPTION_KEY in production")
        return Fernet.generate_key()
    try:
        return key.encode() if isinstance(key, str) else key
    except:
        return key

def encrypt_token(token: str) -> str:
    if not token: return ""
    f = Fernet(get_key())
    return f.encrypt(token.encode()).decode()

    return f.decrypt(token_encrypted.encode()).decode()

# Authentication Logic
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional

# Auth Config
SECRET_KEY = os.getenv("APP_SECRET", "supersecretkey_change_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 day for convenience

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
