#!/usr/bin/env python3
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    """Run the workspace_type migration"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not found")
        return False
    
    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Check if column already exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='workspaces' AND column_name='workspace_type'
        """)
        
        if cur.fetchone():
            print("✓ workspace_type column already exists")
            conn.close()
            return True
        
        print("Adding workspace_type column...")
        
        # Create enum type
        cur.execute("CREATE TYPE workspacetype AS ENUM ('system', 'own', 'shared')")
        
        # Add column
        cur.execute("ALTER TABLE workspaces ADD COLUMN workspace_type workspacetype DEFAULT 'own'")
        
        # Update existing records
        cur.execute("UPDATE workspaces SET workspace_type = 'system' WHERE is_system_workspace = true")
        cur.execute("UPDATE workspaces SET workspace_type = 'shared' WHERE is_system_workspace = false AND is_private = false")
        cur.execute("UPDATE workspaces SET workspace_type = 'own' WHERE is_system_workspace = false AND is_private = true")
        
        # Make column NOT NULL
        cur.execute("ALTER TABLE workspaces ALTER COLUMN workspace_type SET NOT NULL")
        
        conn.commit()
        conn.close()
        
        print("✓ Migration completed successfully")
        return True
        
    except Exception as e:
        print(f"✗ Migration failed: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    run_migration()
