"""Persist linked case replays and attempt observation times."""

from alembic import op


revision = "0003_case_replays"
down_revision = "0002_github_pilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE runs ADD COLUMN source_run_id uuid REFERENCES runs(id),
                         ADD COLUMN replay jsonb,
                         ADD CHECK ((source_run_id IS NULL) = (replay IS NULL)),
                         ADD CHECK (source_run_id IS NULL OR (verdict IS NULL AND receipt_sha IS NULL));
        CREATE INDEX runs_source_replays ON runs (source_run_id, created_at) WHERE source_run_id IS NOT NULL;
        CREATE INDEX runs_failure_repository ON runs ((request->>'repo_id'))
            WHERE receipt_sha IS NOT NULL AND source_run_id IS NULL;
        ALTER TABLE attempts DROP CONSTRAINT attempts_number_check,
                             ADD CHECK (number BETWEEN 1 AND 5),
                             ADD COLUMN observed_at timestamptz;
        UPDATE attempts a SET observed_at = e.created_at FROM run_events e
        WHERE e.run_id = a.run_id AND e.kind = 'attempt_finished'
          AND e.data->>'generation' = a.fence::text AND e.data->>'engine' = a.engine
          AND e.data->>'side' = a.side AND e.data->>'number' = a.number::text;
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM runs WHERE source_run_id IS NOT NULL;
        ALTER TABLE attempts DROP COLUMN observed_at, DROP CONSTRAINT attempts_number_check,
                             ADD CHECK (number IN (1, 2));
        DROP INDEX runs_failure_repository, runs_source_replays;
        ALTER TABLE runs DROP COLUMN replay, DROP COLUMN source_run_id;
    """)
