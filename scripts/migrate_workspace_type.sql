-- Create workspace type enum
CREATE TYPE workspacetype AS ENUM ('system', 'own', 'shared');

-- Add workspace_type column with default value
ALTER TABLE workspaces ADD COLUMN workspace_type workspacetype DEFAULT 'own';

-- Update existing workspaces based on current flags
UPDATE workspaces SET workspace_type = 'system' WHERE is_system_workspace = true;
UPDATE workspaces SET workspace_type = 'shared' WHERE is_system_workspace = false AND is_private = false;
UPDATE workspaces SET workspace_type = 'own' WHERE is_system_workspace = false AND is_private = true;

-- Make the column NOT NULL after setting values
ALTER TABLE workspaces ALTER COLUMN workspace_type SET NOT NULL;
