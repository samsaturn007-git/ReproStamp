"""Persist receipt-backed route reviews and exact screenshot approvals."""

from alembic import op


revision = "0004_route_reviews"
down_revision = "0003_case_replays"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE runs ADD COLUMN reviews jsonb NOT NULL DEFAULT '[]',
                         ADD COLUMN review_approval_snapshot jsonb;
        CREATE TABLE visual_approvals (
            repo_id text NOT NULL,
            binding_sha text NOT NULL,
            binding jsonb NOT NULL,
            run_id uuid NOT NULL REFERENCES runs(id),
            receipt_sha text NOT NULL,
            accepted_by text NOT NULL CHECK (accepted_by = 'owner'),
            accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (repo_id, binding_sha)
        );
        CREATE INDEX visual_approvals_commit ON visual_approvals (repo_id, (binding->>'commit'));
        CREATE INDEX visual_approvals_profile ON visual_approvals (repo_id, (binding->>'profile_sha256'), accepted_at);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE visual_approvals;
        ALTER TABLE runs DROP COLUMN reviews, DROP COLUMN review_approval_snapshot;
    """)
