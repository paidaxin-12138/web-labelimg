#!/usr/bin/env python3
"""Seed default admin user for development."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, init_db
from app.core.security import hash_password
from app.models import User, UserRole


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "admin@example.com"))
        if result.scalar_one_or_none():
            print("Admin already exists")
            return
        user = User(
            email="admin@example.com",
            password_hash=hash_password("admin123"),
            display_name="Admin",
            role=UserRole.admin,
        )
        db.add(user)
        await db.commit()
        print("Created admin@example.com / admin123")


if __name__ == "__main__":
    asyncio.run(main())
