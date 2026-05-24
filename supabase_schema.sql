-- Run this in your Supabase dashboard: SQL Editor → New query → Run

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    search_query TEXT NOT NULL,
    location TEXT,
    max_results INTEGER DEFAULT 50,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
