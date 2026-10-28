-- Speeds up the login lookup.
CREATE INDEX idx_customers_email ON customers (email);
