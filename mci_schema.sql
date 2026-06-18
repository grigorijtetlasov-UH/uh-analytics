-- IRIS · MCI schema (запускати від postgres:  psql -v appuser=<user> -f mci_schema.sql)
CREATE SCHEMA IF NOT EXISTS mci AUTHORIZATION :appuser;
SET ROLE :appuser;

CREATE TABLE IF NOT EXISTS mci.snapshots (
    snapshot_date DATE         PRIMARY KEY,
    ts            TIMESTAMPTZ  NOT NULL,
    score         NUMERIC(5,1) NOT NULL,
    label         TEXT         NOT NULL,
    advice        TEXT,
    sub_indexes   JSONB        NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mci_snapshots_ts ON mci.snapshots (ts);

CREATE TABLE IF NOT EXISTS mci.sub_scores (
    snapshot_date DATE         NOT NULL,
    name          TEXT         NOT NULL,
    score         NUMERIC(5,1) NOT NULL,
    weight        NUMERIC(4,3) NOT NULL,
    weighted      NUMERIC(6,2) NOT NULL,
    signals       JSONB,
    PRIMARY KEY (snapshot_date, name)
);

RESET ROLE;

