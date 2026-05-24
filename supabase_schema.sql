-- Run this in your Supabase dashboard: SQL Editor → New query → Run

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    apify_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- If the users table already exists, run these to add the new columns:
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS apify_enabled BOOLEAN DEFAULT TRUE;

-- Seed the admin account (run once; replace the hash with bcrypt of NishitRathod@Build&GenerateRevenue):
-- UPDATE users SET is_admin = TRUE, email = 'codewithnishit@gmail.com' WHERE username = 'sales@restrucai';

CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    search_query TEXT NOT NULL,
    location TEXT,
    max_results INTEGER DEFAULT 50,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Migration (run if campaigns table already exists without user_id):
-- ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE CASCADE,
    name TEXT,
    address TEXT,
    phone TEXT,
    email TEXT,
    website TEXT,
    rating REAL,
    reviews INTEGER,
    category TEXT,
    latitude REAL,
    longitude REAL,
    google_url TEXT,
    raw_json TEXT,
    call_status TEXT DEFAULT 'Need to Call',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- If you already created the leads table earlier, run these to add the new columns:
-- ALTER TABLE leads ADD COLUMN IF NOT EXISTS call_status TEXT DEFAULT 'Need to Call';
-- ALTER TABLE leads ADD COLUMN IF NOT EXISTS notes TEXT;
