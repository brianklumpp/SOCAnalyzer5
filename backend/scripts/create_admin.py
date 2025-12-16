#!/usr/bin/env python3
"""
Script to create the first admin user for SOCAnalyzer.
Run this script before the first deployment to set up initial admin access.

Usage:
    python -m backend.scripts.create_admin
    
Or with environment variables:
    ADMIN_USERNAME=admin ADMIN_EMAIL=admin@company.com ADMIN_PASSWORD=secure123 python -m backend.scripts.create_admin
"""
import sys
import os
import asyncio
import getpass
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select
from backend.app.database import AsyncSessionLocal
from backend.app.models import User
from backend.app.auth.security import get_password_hash


async def create_admin_user(username: str, email: str, password: str, full_name: str = None):
    """Create an admin user in the database."""
    async with AsyncSessionLocal() as db:
        # Check if user already exists
        result = await db.execute(select(User).where(User.username == username))
        existing_user = result.scalars().first()
        
        if existing_user:
            print(f"❌ User '{username}' already exists!")
            return False
        
        # Check if email already exists
        result = await db.execute(select(User).where(User.email == email))
        existing_email = result.scalars().first()
        
        if existing_email:
            print(f"❌ Email '{email}' is already registered!")
            return False
        
        # Create admin user
        admin_user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            is_admin=True,
            is_active=True
        )
        
        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)
        
        print(f"\n✅ Admin user created successfully!")
        print(f"   Username: {admin_user.username}")
        print(f"   Email: {admin_user.email}")
        print(f"   ID: {admin_user.id}")
        print(f"   Admin: {admin_user.is_admin}")
        print(f"\n🔐 You can now log in with these credentials.")
        
        return True


def get_input_with_env(prompt: str, env_var: str, secret: bool = False) -> str:
    """Get input from environment variable or prompt user."""
    value = os.getenv(env_var)
    if value:
        if not secret:
            print(f"{prompt} (from {env_var}): {value}")
        else:
            print(f"{prompt} (from {env_var}): {'*' * 8}")
        return value
    
    if secret:
        return getpass.getpass(prompt)
    else:
        return input(prompt)


async def main():
    """Main function to create admin user."""
    print("=" * 60)
    print("SOCAnalyzer Admin User Creation")
    print("=" * 60)
    print()
    
    # Check if running non-interactively (all env vars set)
    non_interactive = all([
        os.getenv('ADMIN_USERNAME'),
        os.getenv('ADMIN_EMAIL'),
        os.getenv('ADMIN_PASSWORD')
    ])
    
    if non_interactive:
        print("📝 Running in non-interactive mode (using environment variables)")
        print()
    else:
        print("📝 Please provide admin user details:")
        print()
    
    # Get user input
    username = get_input_with_env("Username: ", "ADMIN_USERNAME")
    email = get_input_with_env("Email: ", "ADMIN_EMAIL")
    password = get_input_with_env("Password: ", "ADMIN_PASSWORD", secret=True)
    
    if not non_interactive:
        password_confirm = getpass.getpass("Confirm Password: ")
        
        if password != password_confirm:
            print("❌ Passwords do not match!")
            return 1
    
    full_name = get_input_with_env("Full Name (optional): ", "ADMIN_FULL_NAME")
    if not full_name:
        full_name = None
    
    print()
    print("Creating admin user...")
    
    try:
        success = await create_admin_user(username, email, password, full_name)
        return 0 if success else 1
    except Exception as e:
        print(f"\n❌ Error creating admin user: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
