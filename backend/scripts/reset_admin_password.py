"""Reset admin user password."""
import asyncio
import sys
from backend.app.database import async_session_maker
from backend.app.models import User
from backend.app.auth.security import get_password_hash
from sqlalchemy import select


async def main():
    """Reset admin password to Admin1234!"""
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.username == 'admin'))
        admin = result.scalars().first()
        
        if not admin:
            print("❌ Admin user not found!")
            return 1
        
        admin.hashed_password = get_password_hash('Admin1234!')
        await db.commit()
        
        print('✅ Admin password reset successfully!')
        print('   Username: admin')
        print('   Password: Admin1234!')
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
