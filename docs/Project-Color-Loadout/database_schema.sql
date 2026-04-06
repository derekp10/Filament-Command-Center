-- ==========================================
-- 🗂️ TABLE 1: Projects (The Core Library)
-- ==========================================
-- This table holds the fast-search data and the JSON payload.

CREATE TABLE Projects (
    project_id TEXT PRIMARY KEY,                 -- Auto-generated UUID
    project_name TEXT NOT NULL,                  -- e.g., "Minecraft Enzo"
    target_printer TEXT,                         -- e.g., "Prusa XL 5T"
    
    -- File Tracking (Sniff Mode)
    base_directory_alias TEXT,                   -- e.g., "truenas_projects"
    relative_path TEXT,                          -- e.g., "/Toys/Enzo/Minecraft Enzo.3mf"
    lock_status TEXT,                            -- "Slot-Locked" or "Swappable"
    
    -- UI & Meta
    thumbnail_base64 TEXT,                       -- Extracted G-code preview image
    last_printed DATETIME,
    notes TEXT,                                  -- Success/Failure notes
    
    -- 🌟 THE HYBRID MAGIC COLUMN 🌟
    -- This stores the entire JSON array of your toolhead slots!
    -- Using SQLite's JSON1 extension, we can still query inside this text block if needed.
    loadout_data TEXT 
);

-- ==========================================
-- 🔍 TABLE 2: Filament_Index (Reverse Lookup)
-- ==========================================
-- This solves the "Where is this used?" problem. 
-- It is updated automatically whenever a project is saved.

CREATE TABLE Filament_Index (
    index_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,                             -- Links back to Projects table
    filament_id INTEGER,                         -- The generic FCC/Spoolman material ID
    preferred_hex TEXT,                          -- The exact color requested
    
    FOREIGN KEY(project_id) REFERENCES Projects(project_id) ON DELETE CASCADE
);

-- ==========================================
-- 🚦 TABLE 3: Print_Queue (The Lazy Swap Optimizer)
-- ==========================================
-- This manages the Spooler and optimization algorithm.

CREATE TABLE Print_Queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,                             -- Which project is queued
    queue_order INTEGER,                         -- Position in line (1, 2, 3...)
    strict_colors BOOLEAN DEFAULT 1,             -- 1 = Exact match, 0 = Allow Aesthetic Compromise
    status TEXT DEFAULT 'Queued',                -- 'Queued', 'Optimizing', 'Spooled', 'Printed'
    
    FOREIGN KEY(project_id) REFERENCES Projects(project_id) ON DELETE CASCADE
);