-- This file predates the naming convention, which is exactly what the linter points out.
CREATE VIEW active_customers AS
    SELECT id, email
    FROM customers
    WHERE deleted_at IS NULL;
