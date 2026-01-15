from sqlmodel import create_engine, SQLModel, Session
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback for local development if not set, though ideally should be force set
if not DATABASE_URL:
    # Use a local sqlite for dev if nothing specified, or raise error?
    # For SaaS transition, let's prefer explicit configuration, but fallback to local sqlite for safety.
    DATABASE_URL = "sqlite:///./local_dev.db" 

# Check for "postgres://" and replace with "postgresql://" (Render common issue)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, echo=False)

def init_db():
    if os.getenv("ENV") != "production":
        SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
