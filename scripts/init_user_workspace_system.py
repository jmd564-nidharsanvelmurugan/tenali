#!/usr/bin/env python3
"""
Initialization script for the new user workspace system.
This script sets up the Azure Search index and updates existing workspaces.
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base, Workspace, WorkspaceType
from Jlens.lib.azure_search_service import AzureSearchService

load_dotenv()

def init_database():
    """Initialize database connection"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not found in environment variables")
        return None
    
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

def create_user_workspace_index():
    """Create the user workspace search index"""
    print("Creating user workspace search index...")
    
    search_service = AzureSearchService()
    
    if search_service.index_exists():
        print("✓ User workspace index already exists")
        return True
    
    success = search_service.create_user_workspace_index()
    if success:
        print("✓ User workspace index created successfully")
        return True
    else:
        print("✗ Failed to create user workspace index")
        return False

def update_existing_workspaces(db):
    """Update existing workspaces with workspace_type"""
    print("Updating existing workspaces...")
    
    try:
        # Get all workspaces without workspace_type set
        workspaces = db.query(Workspace).filter(Workspace.workspace_type == None).all()
        
        updated_count = 0
        for workspace in workspaces:
            if workspace.is_system_workspace:
                workspace.workspace_type = WorkspaceType.system
            elif workspace.is_private:
                workspace.workspace_type = WorkspaceType.own
            else:
                workspace.workspace_type = WorkspaceType.shared
            
            updated_count += 1
        
        db.commit()
        print(f"✓ Updated {updated_count} workspaces with workspace_type")
        return True
        
    except Exception as e:
        print(f"✗ Error updating workspaces: {str(e)}")
        db.rollback()
        return False

def verify_setup():
    """Verify the setup is working correctly"""
    print("Verifying setup...")
    
    # Check Azure Search service
    search_service = AzureSearchService()
    if not search_service.index_exists():
        print("✗ User workspace index not found")
        return False
    
    print("✓ User workspace index is accessible")
    
    # Check database connection
    db = init_database()
    if not db:
        print("✗ Database connection failed")
        return False
    
    try:
        # Check if workspace_type column exists
        workspace_count = db.query(Workspace).count()
        print(f"✓ Database connection working ({workspace_count} workspaces found)")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Database verification failed: {str(e)}")
        return False

def main():
    """Main initialization function"""
    print("🚀 Initializing User Workspace System")
    print("=" * 50)
    
    # Step 1: Create search index
    if not create_user_workspace_index():
        print("❌ Failed to create search index. Exiting.")
        sys.exit(1)
    
    # Step 2: Update database
    db = init_database()
    if not db:
        print("❌ Failed to connect to database. Exiting.")
        sys.exit(1)
    
    if not update_existing_workspaces(db):
        print("❌ Failed to update existing workspaces. Exiting.")
        db.close()
        sys.exit(1)
    
    db.close()
    
    # Step 3: Verify setup
    if not verify_setup():
        print("❌ Setup verification failed. Please check the configuration.")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("✅ User Workspace System initialized successfully!")
    print("\nNext steps:")
    print("1. Run database migration: alembic upgrade head")
    print("2. Restart the application")
    print("3. Test file upload in own/shared workspaces")

if __name__ == "__main__":
    main()
