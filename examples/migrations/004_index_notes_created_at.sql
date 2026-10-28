-- Deliberately the same version as 004 to show how a duplicate is reported.
CREATE INDEX CONCURRENTLY idx_notes_created_at ON notes (created_at);
