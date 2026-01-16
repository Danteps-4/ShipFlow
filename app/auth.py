from passlib.context import CryptContext
from sqlmodel import Session, select
from app.models import User, UserSession
import secrets
import hashlib
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_session(session: Session, user_id: int, duration_days: int = 7) -> str:
    """
    Creates a new session for the user.
    Returns the plain token (to set in cookie).
    Stores the hash in the DB.
    """
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    expires_at = datetime.utcnow() + timedelta(days=duration_days)
    
    user_session = UserSession(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    session.add(user_session)
    session.commit()
    session.refresh(user_session)
    
    return token

def get_user_from_session(session: Session, token: str) -> User | None:
    if not token:
        return None
        
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    query = select(UserSession).where(UserSession.token_hash == token_hash)
    user_session = session.exec(query).first()
    
    if not user_session:
        return None
        
    if user_session.expires_at < datetime.utcnow():
        # Clean up expired session
        session.delete(user_session)
        session.commit()
        return None
        
    return session.get(User, user_session.user_id)

def delete_session(session: Session, token: str):
    if not token:
        return
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    query = select(UserSession).where(UserSession.token_hash == token_hash)
    user_session = session.exec(query).first()
    if user_session:
        session.delete(user_session)
        session.commit()
