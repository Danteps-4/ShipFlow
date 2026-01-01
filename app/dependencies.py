from fastapi import Request, Depends, HTTPException, status
from sqlmodel import select, Session
from app.database import get_session
from app.models import Store, TiendaNubeToken
from typing import Optional

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
    session: Session = Depends(get_session)
) -> Optional[Store]:
    if not store_id:
        return None
    store = session.get(Store, store_id)
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
