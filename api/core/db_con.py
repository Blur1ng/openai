from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
)

from .security import POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_USER, POSTGRES_PORT


SQLACHEMY_DATABASE_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@pg:{POSTGRES_PORT}/{POSTGRES_DB}"
)
engine = create_async_engine(SQLACHEMY_DATABASE_URL)


Base = declarative_base()

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Prompt(Base):
    __tablename__ = "prompt_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ai_model = Column(String)
    prompt_name = Column(String, index=True)
    prompt = Column(String)
    request = Column(String) 
    model = Column(String) 

class RequestData(Base):
    __tablename__ = "request_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ai_model = Column(String)
    request = Column(String)
    model = Column(String) 

class JobResult(Base):
    __tablename__ = "job_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, unique=True, nullable=False, index=True)
    ai_model = Column(String, nullable=False)
    model = Column(String, nullable=False)
    prompt_name = Column(String, nullable=False)
    request_code = Column(Text, nullable=False)
    result_text = Column(Text)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    status = Column(String, nullable=False, default='queued')
    error_message = Column(Text)
    created_at = Column(DateTime)
    completed_at = Column(DateTime)


async def get_db():
    async with async_session() as db:
        yield db
