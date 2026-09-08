"""remove orphaned conversation history

Revision ID: 20260908_0003
Revises: 20260908_0002
"""

from alembic import op


revision = "20260908_0003"
down_revision = "20260908_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Earlier versions intentionally preserved Run history after deleting a
    # workspace conversation. Remove those existing orphaned records once;
    # repository deletion now keeps future records in sync transactionally.
    op.execute("""
        DELETE FROM orchestration_tasks
        WHERE run_id IN (
            SELECT r.id FROM orchestration_runs r
            LEFT JOIN conversations c ON c.id = r.conversation_id
            WHERE c.id IS NULL
        )
    """)
    op.execute("""
        DELETE FROM artifacts
        WHERE run_id IN (
            SELECT r.id FROM orchestration_runs r
            LEFT JOIN conversations c ON c.id = r.conversation_id
            WHERE c.id IS NULL
        )
    """)
    op.execute("DELETE FROM events WHERE conversation_id NOT IN (SELECT id FROM conversations)")
    op.execute("DELETE FROM messages WHERE conversation_id NOT IN (SELECT id FROM conversations)")
    op.execute("DELETE FROM orchestration_runs WHERE conversation_id NOT IN (SELECT id FROM conversations)")

def downgrade() -> None:
    # Deleted orphaned history cannot be reconstructed.
    pass
