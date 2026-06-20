#!/usr/bin/env python3

import os
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext
from db.models import User

# Load environment variables
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

hashed_password_admin = pwd_context.hash("admin@123")
hashed_password_user = pwd_context.hash("user@123")


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not found")
    exit(1)

# Create DB connection
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

db = SessionLocal()


def seed_users():
    users = [
        {
            "email": "admin@jlens.ai",
            "name": "Admin User",
            "designation": "Administrator",
            "client_name": "JLens",
            "role": "admin",
            "microsoft_id": None,
            "password_hash": hashed_password_admin
        },
        {
            "email": "user@jlens.ai",
            "name": "Test User",
            "designation": "AI Engineer",
            "client_name": "JLens",
            "role": "user",
            "microsoft_id": None,
            "password_hash": hashed_password_user      }
    ]

    for user_data in users:

        existing_user = (
            db.query(User)
            .filter(User.email == user_data["email"])
            .first()
        )

        if existing_user:
            print(f"ℹ User already exists: {user_data['email']}")
            continue

        new_user = User(
            id=uuid4(),
            email=user_data["email"],
            name=user_data["name"],
            designation=user_data["designation"],
            client_name=user_data["client_name"],
            role=user_data["role"],
            microsoft_id=user_data["microsoft_id"],
            password_hash=user_data["password_hash"],
            has_given_feedback=False
        )

        db.add(new_user)

        print(f"✓ Added user: {user_data['email']}")

    db.commit()


def main():
    try:
        print("🌱 Starting user seed process...")

        seed_users()

        print("✅ User seed completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"❌ Seed failed: {e}")

    finally:
        db.close()


if __name__ == "__main__":
    main()