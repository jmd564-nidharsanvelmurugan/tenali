import os
import traceback
from sqlalchemy import text
from sqlalchemy.orm import Session
from core.database import SessionLocal


def execute_sql_file(db: Session, filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        sql = f.read()

    for statement in sql.split(";"):
        stmt = statement.strip()
        if stmt:
            db.execute(text(stmt))   # wrap in text() for SQLAlchemy 2.x


def seed():
    db: Session = SessionLocal()
    base_dir = os.path.dirname(__file__)

    try:
        # Execute proposal_questions and proposal_metadata SQL files
        execute_sql_file(db, os.path.join(base_dir, "AiProposal/seed/insert_proposal_questions.sql"))
        execute_sql_file(db, os.path.join(base_dir, "AiProposal/seed/insert_proposal_metadata.sql"))

        db.commit()

    except Exception:
        db.rollback()
        
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
