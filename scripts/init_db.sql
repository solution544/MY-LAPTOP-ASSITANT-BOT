-- Run once against a fresh database if you're not using Docker (which
-- already includes pgvector). Native PostgreSQL installs need the pgvector
-- extension built/installed separately before this will succeed — see
-- README.md "Database Setup" for the native-install path.
CREATE EXTENSION IF NOT EXISTS vector;
