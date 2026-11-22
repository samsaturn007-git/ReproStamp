"""Store local owner sessions, queued runs, attempts, events, and artifacts."""

from alembic import op


revision = "0001_durable_runs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE owner_sessions (
            token_hash text PRIMARY KEY,
            csrf_token text NOT NULL,
            expires_at timestamptz NOT NULL
        );
        CREATE TABLE runs (
            id uuid PRIMARY KEY,
            submission_key uuid NOT NULL UNIQUE,
            request jsonb NOT NULL,
            base_sha text NOT NULL,
            head_sha text NOT NULL,
            plan jsonb NOT NULL,
            state text NOT NULL CHECK (state IN
                ('queued', 'running', 'cancelling', 'cancelled', 'completed', 'incomplete', 'blocked')),
            fence bigint NOT NULL DEFAULT 0,
            lease_until timestamptz,
            event_seq bigint NOT NULL DEFAULT 0,
            verdict text CHECK (verdict IN ('VERIFIED', 'FAILED', 'INCONCLUSIVE', 'POLICY_BLOCKED')),
            reason text,
            detail text,
            engine_verdicts jsonb NOT NULL DEFAULT '{}',
            receipt_sha text,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            finished_at timestamptz,
            expires_at timestamptz,
            purged_at timestamptz
        );
        CREATE INDEX runs_claimable ON runs (state, created_at)
            WHERE state IN ('queued', 'running', 'cancelling');
        CREATE INDEX runs_expirable ON runs (expires_at) WHERE purged_at IS NULL;
        CREATE TABLE run_events (
            run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            seq bigint NOT NULL,
            kind text NOT NULL,
            data jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (run_id, seq)
        );
        CREATE TABLE attempts (
            run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            fence bigint NOT NULL,
            engine text NOT NULL,
            side text NOT NULL CHECK (side IN ('base', 'head')),
            number smallint NOT NULL CHECK (number IN (1, 2)),
            state text NOT NULL CHECK (state IN ('running', 'completed', 'incomplete', 'interrupted')),
            result jsonb,
            PRIMARY KEY (run_id, fence, engine, side, number)
        );
        CREATE TABLE artifacts (
            id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            kind text NOT NULL CHECK (kind IN ('receipt', 'trace', 'screenshot', 'log', 'summary')),
            path text NOT NULL,
            size bigint NOT NULL CHECK (size >= 0),
            sha256 text,
            UNIQUE (run_id, path)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE artifacts, attempts, run_events, runs, owner_sessions")
