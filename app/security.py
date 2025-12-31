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

def decrypt_token(token_encrypted: str) -> str:
    if not token_encrypted: return ""
    f = Fernet(get_key())
    return f.decrypt(token_encrypted.encode()).decode()
