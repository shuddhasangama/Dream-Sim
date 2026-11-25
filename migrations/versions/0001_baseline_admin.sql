CREATE TABLE IF NOT EXISTS "AdminIdentity" (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, role TEXT NOT NULL,
 password_hash TEXT NOT NULL, protected_totp TEXT NOT NULL,
 last_totp_counter BIGINT NOT NULL DEFAULT -1, enabled INTEGER NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS "AdminSession" (
 id TEXT PRIMARY KEY, admin_id TEXT NOT NULL REFERENCES "AdminIdentity"(id),
 csrf_hash TEXT NOT NULL, created_at BIGINT NOT NULL, last_seen_at BIGINT NOT NULL,
 expires_at BIGINT NOT NULL, revoked_at BIGINT
);
CREATE TABLE IF NOT EXISTS "AdminThrottle" (
 id TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS "AdminAudit" (
 id TEXT PRIMARY KEY, admin_id TEXT, action TEXT NOT NULL, section TEXT,
 created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS admin_audit_created ON "AdminAudit"(created_at);
