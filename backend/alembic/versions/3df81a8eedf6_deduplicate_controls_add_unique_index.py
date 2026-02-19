"""deduplicate controls and add unique partial index on (scan_id, control_id)

Revision ID: 3df81a8eedf6
Revises: 9a37bd62db73
Create Date: 2026-02-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3df81a8eedf6'
down_revision = '9a37bd62db73'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ──────────────────────────────────────────────────────────────────
    # Phase 1: Clean up duplicate controls
    #
    # For each (scan_id, control_id) group with >1 row, keep the row
    # with the highest control_confidence (tie-break: lowest id).
    # Reassign control_objective_mappings from losers to the survivor,
    # then delete the loser rows.
    # ──────────────────────────────────────────────────────────────────

    conn = op.get_bind()

    # Step 1a: Insert missing objective mappings from losers to survivors.
    # Multiple losers may map to the same objective — ON CONFLICT DO NOTHING
    # handles that safely, keeping whichever mapping the survivor already has.
    conn.execute(sa.text("""
        WITH survivor AS (
            SELECT DISTINCT ON (scan_id, control_id)
                id AS survivor_id, scan_id, control_id
            FROM control
            WHERE control_id IS NOT NULL AND control_id != ''
              AND (scan_id, control_id) IN (
                  SELECT scan_id, control_id
                  FROM control
                  WHERE control_id IS NOT NULL AND control_id != ''
                  GROUP BY scan_id, control_id
                  HAVING COUNT(*) > 1
              )
            ORDER BY scan_id, control_id,
                     COALESCE(control_confidence, 0) DESC,
                     id ASC
        ),
        loser AS (
            SELECT c.id AS loser_id, s.survivor_id
            FROM control c
            JOIN survivor s ON s.scan_id = c.scan_id AND s.control_id = c.control_id
            WHERE c.id != s.survivor_id
        ),
        best_loser_mapping AS (
            -- For each (survivor, objective) pair, pick the loser mapping
            -- with the highest confidence
            SELECT DISTINCT ON (l.survivor_id, m.objective_id)
                l.survivor_id,
                m.objective_id,
                m.mapping_confidence,
                m.page_proximity_score,
                m.line_proximity_score,
                m.gpt_alignment_score,
                m.id_alignment_score,
                m.objective_gpt_confidence_boost,
                m.mapping_justification,
                m.mapping_method,
                m.is_primary
            FROM control_objective_mappings m
            JOIN loser l ON m.control_id = l.loser_id
            ORDER BY l.survivor_id, m.objective_id,
                     COALESCE(m.mapping_confidence, 0) DESC
        )
        INSERT INTO control_objective_mappings
            (control_id, objective_id, mapping_confidence,
             page_proximity_score, line_proximity_score,
             gpt_alignment_score, id_alignment_score,
             objective_gpt_confidence_boost, mapping_justification,
             mapping_method, is_primary, created_at)
        SELECT
            survivor_id, objective_id, mapping_confidence,
            page_proximity_score, line_proximity_score,
            gpt_alignment_score, id_alignment_score,
            objective_gpt_confidence_boost, mapping_justification,
            mapping_method, is_primary, NOW()
        FROM best_loser_mapping
        ON CONFLICT (control_id, objective_id) DO NOTHING
    """))

    # Step 1b: Delete all mappings still pointing to loser controls
    conn.execute(sa.text("""
        WITH survivor AS (
            SELECT DISTINCT ON (scan_id, control_id)
                id AS survivor_id, scan_id, control_id
            FROM control
            WHERE control_id IS NOT NULL AND control_id != ''
              AND (scan_id, control_id) IN (
                  SELECT scan_id, control_id
                  FROM control
                  WHERE control_id IS NOT NULL AND control_id != ''
                  GROUP BY scan_id, control_id
                  HAVING COUNT(*) > 1
              )
            ORDER BY scan_id, control_id,
                     COALESCE(control_confidence, 0) DESC,
                     id ASC
        ),
        loser AS (
            SELECT c.id AS loser_id
            FROM control c
            JOIN survivor s ON s.scan_id = c.scan_id AND s.control_id = c.control_id
            WHERE c.id != s.survivor_id
        )
        DELETE FROM control_objective_mappings
        WHERE control_id IN (SELECT loser_id FROM loser)
    """))

    # Step 1c: Delete the duplicate control rows themselves
    conn.execute(sa.text("""
        WITH survivor AS (
            SELECT DISTINCT ON (scan_id, control_id)
                id AS survivor_id, scan_id, control_id
            FROM control
            WHERE control_id IS NOT NULL AND control_id != ''
              AND (scan_id, control_id) IN (
                  SELECT scan_id, control_id
                  FROM control
                  WHERE control_id IS NOT NULL AND control_id != ''
                  GROUP BY scan_id, control_id
                  HAVING COUNT(*) > 1
              )
            ORDER BY scan_id, control_id,
                     COALESCE(control_confidence, 0) DESC,
                     id ASC
        )
        DELETE FROM control
        WHERE id NOT IN (SELECT survivor_id FROM survivor)
          AND control_id IS NOT NULL AND control_id != ''
          AND (scan_id, control_id) IN (
              SELECT scan_id, control_id FROM survivor
          )
    """))

    # ──────────────────────────────────────────────────────────────────
    # Phase 2: Add unique partial index to prevent future duplicates
    #
    # Partial index: only applies when control_id is non-null and non-empty.
    # Controls without an ID (rare/legacy) are exempt.
    # ──────────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE UNIQUE INDEX uq_control_scan_control_id
        ON control (scan_id, control_id)
        WHERE control_id IS NOT NULL AND control_id != ''
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_control_scan_control_id"))
    # Data cleanup is not reversible — deleted duplicates cannot be restored
