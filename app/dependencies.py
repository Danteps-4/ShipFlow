from fastapi import Request, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import select, Session
from app.database import get_session
from app.models import Store, TiendaNubeToken, User
from app.security import SECRET_KEY, ALGORITHM, jwt, JWTError
from typing import Optional

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

def get_token(request: Request, token_header: Optional[str] = Depends(oauth2_scheme)):
    if token_header:
        return token_header
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

async def get_current_user(token: str = Depends(get_token), session: Session = Depends(get_session)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    if user is None:
        raise credentials_exception
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
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
) -> Optional[Store]:
    """
    Returns the store ONLY if it belongs to the current user.
    """
    if not store_id:
        return None
    
    store = session.get(Store, store_id)
    if not store:
        return None
        
    # OWNERSHIP CHECK
    if store.user_id != current_user.id:
        # Don't leak existence, or return 403 explicitly? 
        # Requirement says "devuelve 403".
        raise HTTPException(status_code=403, detail="Access to this store is forbidden")
        
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
