#!/usr/bin/env python3
"""
Update existing workspaces to have correct workspace types
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Workspace, WorkspaceType

load_dotenv()

def update_workspace_types():
    """Update workspace types for existing workspaces"""
    database_url = os.getenv("DATABASE_URL")
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Update Jman Sales to be a system workspace
        jman_sales = db.query(Workspace).filter(Workspace.name == "Jman Sales").first()
        if jman_sales:
            jman_sales.workspace_type = WorkspaceType.system
            jman_sales.is_system_workspace = True
            print(f"✅ Updated 'Jman Sales' to system workspace")
        
        db.commit()
        
        # Show all workspaces and their types
        workspaces = db.query(Workspace).all()
        print(f"\n📋 Current workspace types:")
        for ws in workspaces:
            print(f"   - {ws.name}: {ws.workspace_type.value}")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Error updating workspace types: {str(e)}")
        db.rollback()
        db.close()
        return False

if __name__ == "__main__":
    update_workspace_types()
