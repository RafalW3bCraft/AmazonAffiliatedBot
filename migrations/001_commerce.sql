-- 001_commerce.sql — DealPilot commerce schema (PostgreSQL)
-- Idempotent: safe to run repeatedly. Applied by CommerceStorage on init.

CREATE TABLE IF NOT EXISTS merchant_products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(64) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL,
    currency CHAR(3) NOT NULL,
    stock INT NOT NULL,
    version INT NOT NULL,
    source VARCHAR(16) DEFAULT 'MERCHANT',
    rights_evidence TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS cart_quotes (
    id SERIAL PRIMARY KEY,
    quote_id UUID UNIQUE NOT NULL,
    actor_id VARCHAR(64) NOT NULL,
    currency CHAR(3) NOT NULL,
    items_json JSONB NOT NULL,
    total NUMERIC(12,2) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'OPEN',
    expires_at TIMESTAMP NOT NULL,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS checkout_attempts (
    id SERIAL PRIMARY KEY,
    cart_quote_id INT NOT NULL REFERENCES cart_quotes(id),
    buyer_id VARCHAR(64) NOT NULL,
    request_id VARCHAR(64) UNIQUE NOT NULL,
    paypal_order_id VARCHAR(64) UNIQUE,
    capture_request_id VARCHAR(64),
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP DEFAULT now() NOT NULL,
    updated_at TIMESTAMP DEFAULT now() NOT NULL
);

ALTER TABLE checkout_attempts
    ADD COLUMN IF NOT EXISTS capture_request_id VARCHAR(64);

CREATE TABLE IF NOT EXISTS payment_captures (
    id SERIAL PRIMARY KEY,
    checkout_attempt_id INT NOT NULL REFERENCES checkout_attempts(id),
    paypal_capture_id VARCHAR(64) UNIQUE NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(24) NOT NULL,
    verified_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payment_events (
    id SERIAL PRIMARY KEY,
    provider_event_id VARCHAR(128) UNIQUE NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    verification_result VARCHAR(24) NOT NULL,
    processing_state VARCHAR(24) NOT NULL,
    received_at TIMESTAMP DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id SERIAL PRIMARY KEY,
    actor_id VARCHAR(64) NOT NULL,
    model VARCHAR(64) NOT NULL,
    input_hash CHAR(64) NOT NULL,
    output_redacted TEXT NOT NULL DEFAULT '',
    approved_quote_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_actions (
    id SERIAL PRIMARY KEY,
    actor_id VARCHAR(64) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    subject_id VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    correlation_id VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checkout_attempts_quote ON checkout_attempts(cart_quote_id);
CREATE INDEX IF NOT EXISTS idx_payment_captures_attempt ON payment_captures(checkout_attempt_id);
CREATE INDEX IF NOT EXISTS idx_cart_quotes_quote_id ON cart_quotes(quote_id);
