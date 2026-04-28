-- =============================================================================
-- schema.sql
-- TSIS1 — Extended PhoneBook Schema
-- =============================================================================
-- Run once:
--   psql -U postgres -d phonebook_db -f schema.sql
-- =============================================================================

-- 1. Groups / categories
CREATE TABLE IF NOT EXISTS groups (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL
);

-- Seed default groups
INSERT INTO groups (name) VALUES
    ('Family'), ('Work'), ('Friend'), ('Other')
ON CONFLICT (name) DO NOTHING;

-- 2. Contacts (extends Practice 7 phonebook table)
--    We keep the original "phonebook" table and ADD new columns to it.
ALTER TABLE phonebook
    ADD COLUMN IF NOT EXISTS email    VARCHAR(100),
    ADD COLUMN IF NOT EXISTS birthday DATE,
    ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id);

-- 3. Phones (multiple numbers per contact)
CREATE TABLE IF NOT EXISTS phones (
    id         SERIAL PRIMARY KEY,
    contact_id INTEGER     NOT NULL REFERENCES phonebook(id) ON DELETE CASCADE,
    phone      VARCHAR(30) NOT NULL,
    type       VARCHAR(10) NOT NULL DEFAULT 'mobile'
                           CHECK (type IN ('home', 'work', 'mobile')),
    UNIQUE (contact_id, phone)
);
