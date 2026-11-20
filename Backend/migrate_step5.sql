-- Run once on the production AND test databases (create_all never alters existing tables).
ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS kind varchar(20) NOT NULL DEFAULT 'sales',
  ADD COLUMN IF NOT EXISTS context text;
CREATE INDEX IF NOT EXISTS ix_leads_kind ON leads (kind);
