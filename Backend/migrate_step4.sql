-- Run once on the production AND test databases (create_all never alters existing tables).
ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS notified_at timestamptz,
  ADD COLUMN IF NOT EXISTS notify_attempts integer NOT NULL DEFAULT 0;
