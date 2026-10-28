BEGIN;

ALTER TABLE audit_log DROP COLUMN payload;
ALTER TABLE audit_log ADD CONSTRAINT audit_created_at_not_null CHECK (created_at IS NOT NULL);

COMMIT;
