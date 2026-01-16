from fastapi import Request, Depends, HTTPException, status
from sqlmodel import select, Session
from app.database import get_session
from app.models import Store, TiendaNubeToken, User
from app.auth import get_user_from_session
from typing import Optional

def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get("session")
    user = get_user_from_session(session, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user

def get_current_store_id(request: Request) -> Optional[int]:
    # Try to get from header first (for API calls if needed later), then cookie
    store_id = request.cookies.get("andreani_active_store")
    if store_id:
        try:
            return int(store_id)
        except ValueError:
            return None
    return None

def get_current_store(
    store_id: Optional[int] = Depends(get_current_store_id),
    current_user: User = Depends(get_current_user), # Require login
    session: Session = Depends(get_session)
) -> Optional[Store]:
    """
    Returns the store ONLY if it belongs to the current user.
    """
    if not store_id:
        return None
    
    store = session.get(Store, store_id)
    
    # Enforce ownership
    if store and store.user_id != current_user.id:
        return None # Or raise 403, but returning None handles "no valid store active" gracefully
        
    return store

def get_current_active_token(
    store: Optional[Store] = Depends(get_current_store),
) -> Optional[TiendaNubeToken]:
    if not store:
        return None
    if not store.token:
        # Try to fetch if not loaded relationship (rare with SQLModel lazy defaults but safe)
        return None
    return store.token
