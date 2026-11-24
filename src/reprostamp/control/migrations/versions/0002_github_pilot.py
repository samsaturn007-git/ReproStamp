"""Persist webhook deliveries, check identities, and superseded evidence."""

from alembic import op


revision = "0002_github_pilot"
down_revision = "0001_durable_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE runs ADD COLUMN superseded_at timestamptz;
        CREATE TABLE github_deliveries (
            id uuid PRIMARY KEY,
            installation_id bigint NOT NULL,
            repository_id bigint NOT NULL,
            profile_id text NOT NULL,
            pr_number bigint NOT NULL,
            base_sha text NOT NULL,
            head_sha text NOT NULL,
            received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            retry_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            failures integer NOT NULL DEFAULT 0,
            state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'queued', 'superseded')),
            run_id uuid REFERENCES runs(id)
        );
        CREATE INDEX github_deliveries_pending ON github_deliveries
            (installation_id, repository_id, profile_id, retry_at) WHERE state = 'pending';
        CREATE TABLE github_checks (
            installation_id bigint NOT NULL,
            repository_id bigint NOT NULL,
            profile_id text NOT NULL,
            head_sha text NOT NULL,
            external_id uuid UNIQUE NOT NULL,
            pr_number bigint NOT NULL,
            base_sha text NOT NULL,
            run_id uuid NOT NULL REFERENCES runs(id),
            superseded boolean NOT NULL DEFAULT false,
            remote_id bigint,
            published_run_id uuid REFERENCES runs(id),
            published_phase text,
            retry_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            publish_failures integer NOT NULL DEFAULT 0,
            PRIMARY KEY (installation_id, repository_id, profile_id, head_sha)
        );
        CREATE INDEX github_checks_pr ON github_checks (installation_id, repository_id, profile_id, pr_number);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE github_checks, github_deliveries")
    op.execute("ALTER TABLE runs DROP COLUMN superseded_at")
