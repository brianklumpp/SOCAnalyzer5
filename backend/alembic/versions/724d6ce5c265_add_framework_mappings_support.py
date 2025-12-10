"""add_framework_mappings_support

Revision ID: 724d6ce5c265
Revises: 65a929ef6dc1
Create Date: 2025-12-09 00:56:46.278804

Multi-Framework Mapping Support - Phase 1

Adds comprehensive framework mapping support beyond TSC/COSO:
- framework_mappings: Universal JSON column for unlimited frameworks
- primary_framework: Track which framework had highest confidence
- primary_criterion_id: Track the best matching criterion overall
- primary_confidence: Store the best match confidence score
- detected_standards: Track which standards were found in report (e.g., ["ISAE 3402", "SSAE 18"])
- active_frameworks: List of frameworks actually used for this scan (e.g., ["TSC", "COSO", "ISAE3402"])

Schema for framework_mappings JSON column:
{
    "TSC": [
        {"id": "CC7.2", "confidence": 0.95, "reasoning": "...", "deviation": "..."},
        {"id": "CC6.1", "confidence": 0.88, "reasoning": "...", "deviation": null}
    ],
    "COSO": [
        {"id": "10", "confidence": 0.92, "reasoning": "...", "deviation": null}
    ],
    "FINANCIAL_ASSERTIONS": [
        {"id": "EO1", "confidence": 0.90, "reasoning": "...", "deviation": null}
    ],
    "ISAE3402": [
        {"id": "CO-3", "confidence": 0.87, "reasoning": "...", "deviation": null}
    ]
}

This allows controls/CUECs to map to multiple frameworks simultaneously,
with each framework supporting multiple criteria matches (top_k).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = '724d6ce5c265'
down_revision = '65a929ef6dc1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add framework_mappings to Control table
    op.add_column('control', sa.Column('framework_mappings', JSON, nullable=True))
    op.add_column('control', sa.Column('primary_framework', sa.String(64), nullable=True))
    op.add_column('control', sa.Column('primary_criterion_id', sa.String(128), nullable=True))
    op.add_column('control', sa.Column('primary_confidence', sa.Float, nullable=True))
    
    # Add framework_mappings to CUEC table
    op.add_column('cuec', sa.Column('framework_mappings', JSON, nullable=True))
    op.add_column('cuec', sa.Column('primary_framework', sa.String(64), nullable=True))
    op.add_column('cuec', sa.Column('primary_criterion_id', sa.String(128), nullable=True))
    op.add_column('cuec', sa.Column('primary_confidence', sa.Float, nullable=True))
    
    # Add framework detection to Scan table
    op.add_column('scan', sa.Column('detected_standards', JSON, nullable=True))
    op.add_column('scan', sa.Column('active_frameworks', JSON, nullable=True))


def downgrade() -> None:
    # Remove columns from Control table
    op.drop_column('control', 'primary_confidence')
    op.drop_column('control', 'primary_criterion_id')
    op.drop_column('control', 'primary_framework')
    op.drop_column('control', 'framework_mappings')
    
    # Remove columns from CUEC table
    op.drop_column('cuec', 'primary_confidence')
    op.drop_column('cuec', 'primary_criterion_id')
    op.drop_column('cuec', 'primary_framework')
    op.drop_column('cuec', 'framework_mappings')
    
    # Remove columns from Scan table
    op.drop_column('scan', 'active_frameworks')
    op.drop_column('scan', 'detected_standards')

