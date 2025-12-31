from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    stores: List["Store"] = Relationship(back_populates="user")

class Store(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    tiendanube_user_id: int = Field(unique=True, index=True) # The ID returned by Tienda Nube
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    user: Optional[User] = Relationship(back_populates="stores")
    token: Optional["TiendaNubeToken"] = Relationship(back_populates="store")

class TiendaNubeToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    access_token_encrypted: str # New encrypted field
    token_type: str
    scope: str
    user_id: int = Field(unique=True) # Tienda Nube user_id (redundant but kept for easy lookup if Store not linked yet)
    store_id: Optional[int] = Field(default=None, foreign_key="store.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    store: Optional[Store] = Relationship(back_populates="token")
