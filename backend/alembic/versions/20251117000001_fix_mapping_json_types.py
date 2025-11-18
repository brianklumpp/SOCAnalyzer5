"""fix_mapping_json_types

Revision ID: 20251117000001
Revises: 2d834bf34316
Create Date: 2025-11-17 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251117000001'
down_revision = '2d834bf34316'
branch_labels = None
depends_on = None


def upgrade():
    """
    Ensure all framework mapping columns are stored as JSONB arrays (not strings).
    Creates backup columns for safe rollback, converts any malformed data, and adds
    CHECK constraints to enforce array-only types at the database level.
    """
    # Create backup columns for control mappings
    op.add_column('control', sa.Column('control_tsc_mappings_backup', postgresql.JSON(), nullable=True))
    op.add_column('control', sa.Column('control_coso_mappings_backup', postgresql.JSON(), nullable=True))
    
    # Create backup columns for CUEC mappings
    op.add_column('cuec', sa.Column('cuec_tsc_mappings_backup', postgresql.JSON(), nullable=True))
    op.add_column('cuec', sa.Column('cuec_coso_mappings_backup', postgresql.JSON(), nullable=True))
    
    # Copy existing data to backup columns
    op.execute("""
        UPDATE control 
        SET control_tsc_mappings_backup = control_tsc_mappings,
            control_coso_mappings_backup = control_coso_mappings
    """)
    
    op.execute("""
        UPDATE cuec 
        SET cuec_tsc_mappings_backup = cuec_tsc_mappings,
            cuec_coso_mappings_backup = cuec_coso_mappings
    """)
    
    # Convert any string-stored JSON to JSON arrays for control table
    # Note: Using json_typeof instead of jsonb_typeof since columns are JSON type
    op.execute("""
        UPDATE control
        SET control_tsc_mappings = 
            CASE 
                WHEN control_tsc_mappings IS NULL THEN '[]'::json
                WHEN json_typeof(control_tsc_mappings) = 'array' THEN control_tsc_mappings
                WHEN json_typeof(control_tsc_mappings) = 'string' THEN 
                    CASE 
                        WHEN control_tsc_mappings::text = '""' THEN '[]'::json
                        WHEN control_tsc_mappings::text ~ '^"\\[.*\\]"$' THEN 
                            (control_tsc_mappings#>>'{}')::json
                        ELSE '[]'::json
                    END
                ELSE '[]'::json
            END
        WHERE control_tsc_mappings IS NULL OR json_typeof(control_tsc_mappings) != 'array'
    """)
    
    op.execute("""
        UPDATE control
        SET control_coso_mappings = 
            CASE 
                WHEN control_coso_mappings IS NULL THEN '[]'::json
                WHEN json_typeof(control_coso_mappings) = 'array' THEN control_coso_mappings
                WHEN json_typeof(control_coso_mappings) = 'string' THEN 
                    CASE 
                        WHEN control_coso_mappings::text = '""' THEN '[]'::json
                        WHEN control_coso_mappings::text ~ '^"\\[.*\\]"$' THEN 
                            (control_coso_mappings#>>'{}')::json
                        ELSE '[]'::json
                    END
                ELSE '[]'::json
            END
        WHERE control_coso_mappings IS NULL OR json_typeof(control_coso_mappings) != 'array'
    """)
    
    # Convert any string-stored JSON to JSON arrays for CUEC table
    op.execute("""
        UPDATE cuec
        SET cuec_tsc_mappings = 
            CASE 
                WHEN cuec_tsc_mappings IS NULL THEN '[]'::json
                WHEN json_typeof(cuec_tsc_mappings) = 'array' THEN cuec_tsc_mappings
                WHEN json_typeof(cuec_tsc_mappings) = 'string' THEN 
                    CASE 
                        WHEN cuec_tsc_mappings::text = '""' THEN '[]'::json
                        WHEN cuec_tsc_mappings::text ~ '^"\\[.*\\]"$' THEN 
                            (cuec_tsc_mappings#>>'{}')::json
                        ELSE '[]'::json
                    END
                ELSE '[]'::json
            END
        WHERE cuec_tsc_mappings IS NULL OR json_typeof(cuec_tsc_mappings) != 'array'
    """)
    
    op.execute("""
        UPDATE cuec
        SET cuec_coso_mappings = 
            CASE 
                WHEN cuec_coso_mappings IS NULL THEN '[]'::json
                WHEN json_typeof(cuec_coso_mappings) = 'array' THEN cuec_coso_mappings
                WHEN json_typeof(cuec_coso_mappings) = 'string' THEN 
                    CASE 
                        WHEN cuec_coso_mappings::text = '""' THEN '[]'::json
                        WHEN cuec_coso_mappings::text ~ '^"\\[.*\\]"$' THEN 
                            (cuec_coso_mappings#>>'{}')::json
                        ELSE '[]'::json
                    END
                ELSE '[]'::json
            END
        WHERE cuec_coso_mappings IS NULL OR json_typeof(cuec_coso_mappings) != 'array'
    """)
    
    # Add CHECK constraints to ensure mappings are JSON arrays only
    op.create_check_constraint(
        'control_tsc_mappings_is_array',
        'control',
        "control_tsc_mappings IS NULL OR json_typeof(control_tsc_mappings) = 'array'"
    )
    
    op.create_check_constraint(
        'control_coso_mappings_is_array',
        'control',
        "control_coso_mappings IS NULL OR json_typeof(control_coso_mappings) = 'array'"
    )
    
    op.create_check_constraint(
        'cuec_tsc_mappings_is_array',
        'cuec',
        "cuec_tsc_mappings IS NULL OR json_typeof(cuec_tsc_mappings) = 'array'"
    )
    
    op.create_check_constraint(
        'cuec_coso_mappings_is_array',
        'cuec',
        "cuec_coso_mappings IS NULL OR json_typeof(cuec_coso_mappings) = 'array'"
    )


def downgrade():
    """
    Rollback: Remove CHECK constraints and restore original data from backup columns.
    """
    # Drop CHECK constraints
    op.drop_constraint('control_tsc_mappings_is_array', 'control', type_='check')
    op.drop_constraint('control_coso_mappings_is_array', 'control', type_='check')
    op.drop_constraint('cuec_tsc_mappings_is_array', 'cuec', type_='check')
    op.drop_constraint('cuec_coso_mappings_is_array', 'cuec', type_='check')
    
    # Restore from backup columns
    op.execute("""
        UPDATE control 
        SET control_tsc_mappings = control_tsc_mappings_backup,
            control_coso_mappings = control_coso_mappings_backup
    """)
    
    op.execute("""
        UPDATE cuec 
        SET cuec_tsc_mappings = cuec_tsc_mappings_backup,
            cuec_coso_mappings = cuec_coso_mappings_backup
    """)
    
    # Drop backup columns
    op.drop_column('control', 'control_tsc_mappings_backup')
    op.drop_column('control', 'control_coso_mappings_backup')
    op.drop_column('cuec', 'cuec_tsc_mappings_backup')
    op.drop_column('cuec', 'cuec_coso_mappings_backup')
