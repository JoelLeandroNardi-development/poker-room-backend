from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

def create_db(env_var: str, *, echo: bool = True):
    url = os.getenv(env_var)
    if not url:
        raise RuntimeError(f"{env_var} environment variable is not set")

    engine = create_async_engine(url, echo=echo)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    base = declarative_base()
    return engine, session_local, base

def make_get_db(SessionLocal):
    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        async with SessionLocal() as session:
            yield session

    return get_db


@asynccontextmanager
async def atomic(session: AsyncSession):
    async with session.begin_nested():
        yield session
