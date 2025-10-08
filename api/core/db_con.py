from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import (
    Column,
    Integer,
    String,
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
    ai_model = Column(String, primary_key=True)
    prompt_name = Column(String, index=True)
    prompt = Column(String, index=True)
    request = Column(String, index=True) 
    model = Column(String) 


async def get_db():
    async with async_session() as db:
        yield db
