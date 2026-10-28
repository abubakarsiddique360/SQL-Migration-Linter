BEGIN;

UPDATE customers SET country_code = 'US';

DELETE FROM audit_log;

COMMIT;
