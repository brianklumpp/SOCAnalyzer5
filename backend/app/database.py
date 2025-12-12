# SQLAlchemy async engine and session setup

from .config import DATABASE_URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(DATABASE_URL, echo=True, future=True)

AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session