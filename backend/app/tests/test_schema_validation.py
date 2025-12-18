"""
Automated Schema Validation Test

Purpose: Validate that database schema, SQLAlchemy models, and INSERT mappings
are all aligned. This test catches mismatches that could cause runtime errors.

Run this test after:
- Creating new Alembic migrations
- Modifying models.py
- Updating config.py TABLE_FIELD_MAP
- Before deploying to production

Usage:
    pytest backend/app/tests/test_schema_validation.py -v
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.models import Control, CUEC, SubserviceOrg, Company, Product
from backend.app.config import TABLE_FIELD_MAP


# Map of model classes to their table names
MODEL_MAP = {
    'control': Control,
    'cuec': CUEC,
    'subservice_org': SubserviceOrg,
    'company': Company,
    'product': Product
}


@pytest.fixture
async def db_engine():
    """Create async database engine for testing"""
    database_url = os.getenv(
        'DATABASE_URL',
        'postgresql+asyncpg://soc2_analyzer:puntitforthewin@localhost:5432/soc2analyzer'
    )
    engine = create_async_engine(database_url, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Create async database session"""
    async_session = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_session() as session:
        yield session


async def get_database_columns(session: AsyncSession, table_name: str) -> set:
    """
    Get actual column names from PostgreSQL database for a table.
    
    Returns:
        Set of column names (excluding 'id' primary key)
    """
    query = text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = :table_name 
        AND table_schema = 'public'
    """)
    result = await session.execute(query, {"table_name": table_name})
    columns = {row[0] for row in result}
    # Exclude 'id' as it's auto-generated primary key
    columns.discard('id')
    return columns


def get_model_columns(model_class) -> set:
    """
    Get column names from SQLAlchemy model definition.
    
    Returns:
        Set of column names (excluding 'id' primary key)
    """
    inspector = inspect(model_class)
    columns = {col.name for col in inspector.columns}
    # Exclude 'id' as it's auto-generated primary key
    columns.discard('id')
    return columns


def get_insert_fields(table_name: str) -> set:
    """
    Get field names from TABLE_FIELD_MAP configuration.
    
    Returns:
        Set of field names configured for INSERT operations
    """
    return set(TABLE_FIELD_MAP.get(table_name, []))


# Fields that are intentionally NOT in INSERT mapping (manual operations only)
MANUAL_OPERATION_FIELDS = {
    'control': {
        'annotation', 'analyst_notes', 'edit_log',  # Manual user edits
        'deviation_summary',  # Manual deviation summary
        'merge_history',  # Auto/manual merge tracking
        'is_duplicate_instance', 'duplicate_group_id', 'instance_differentiator',  # Duplicate management
        'updated_at', 'updated_by_user_id'  # Audit fields set by system
    },
    'cuec': set(),  # All CUEC fields should be in INSERT
    'subservice_org': set(),  # All subservice_org fields should be in INSERT
    'company': set(),  # All company fields should be in INSERT
    'product': set()  # All product fields should be in INSERT
}


@pytest.mark.asyncio
async def test_control_schema_alignment(db_session):
    """Validate Control table schema alignment"""
    table_name = 'control'
    
    # Get columns from all three sources
    db_columns = await get_database_columns(db_session, table_name)
    model_columns = get_model_columns(MODEL_MAP[table_name])
    insert_fields = get_insert_fields(table_name)
    manual_fields = MANUAL_OPERATION_FIELDS[table_name]
    
    # Expected INSERT fields = model columns - manual operation fields
    expected_insert_fields = model_columns - manual_fields
    
    # Validation 1: Database should have all model columns
    missing_in_db = model_columns - db_columns
    assert not missing_in_db, (
        f"Control model defines columns not in database: {missing_in_db}\n"
        f"Create Alembic migration to add these columns."
    )
    
    # Validation 2: Model should have all database columns
    missing_in_model = db_columns - model_columns
    assert not missing_in_model, (
        f"Control database has columns not in model: {missing_in_model}\n"
        f"Add these columns to Control model in models.py."
    )
    
    # Validation 3: INSERT mapping should have all extractor output fields
    missing_in_insert = expected_insert_fields - insert_fields
    assert not missing_in_insert, (
        f"Control extractor outputs not in TABLE_FIELD_MAP: {missing_in_insert}\n"
        f"Add these to config.py TABLE_FIELD_MAP['control']."
    )
    
    # Validation 4: INSERT mapping should not have manual operation fields
    unexpected_in_insert = insert_fields & manual_fields
    assert not unexpected_in_insert, (
        f"Manual operation fields incorrectly in TABLE_FIELD_MAP: {unexpected_in_insert}\n"
        f"Remove these from config.py TABLE_FIELD_MAP['control']."
    )
    
    # Validation 5: No invalid fields in INSERT mapping
    invalid_fields = insert_fields - model_columns
    assert not invalid_fields, (
        f"TABLE_FIELD_MAP has invalid fields not in model: {invalid_fields}\n"
        f"Remove these from config.py TABLE_FIELD_MAP['control']."
    )
    
    print(f"✅ Control schema validation passed:")
    print(f"   - Database columns: {len(db_columns)}")
    print(f"   - Model columns: {len(model_columns)}")
    print(f"   - INSERT fields: {len(insert_fields)}")
    print(f"   - Manual fields (excluded): {len(manual_fields)}")


@pytest.mark.asyncio
async def test_cuec_schema_alignment(db_session):
    """Validate CUEC table schema alignment"""
    table_name = 'cuec'
    
    db_columns = await get_database_columns(db_session, table_name)
    model_columns = get_model_columns(MODEL_MAP[table_name])
    insert_fields = get_insert_fields(table_name)
    
    # For CUEC, all model columns should be in INSERT (no manual-only fields)
    
    missing_in_db = model_columns - db_columns
    assert not missing_in_db, (
        f"CUEC model defines columns not in database: {missing_in_db}"
    )
    
    missing_in_model = db_columns - model_columns
    assert not missing_in_model, (
        f"CUEC database has columns not in model: {missing_in_model}"
    )
    
    missing_in_insert = model_columns - insert_fields
    assert not missing_in_insert, (
        f"CUEC fields not in TABLE_FIELD_MAP: {missing_in_insert}"
    )
    
    invalid_fields = insert_fields - model_columns
    assert not invalid_fields, (
        f"TABLE_FIELD_MAP has invalid CUEC fields: {invalid_fields}"
    )
    
    print(f"✅ CUEC schema validation passed: {len(model_columns)} fields aligned")


@pytest.mark.asyncio
async def test_subservice_org_schema_alignment(db_session):
    """Validate SubserviceOrg table schema alignment"""
    table_name = 'subservice_org'
    
    db_columns = await get_database_columns(db_session, table_name)
    model_columns = get_model_columns(MODEL_MAP[table_name])
    insert_fields = get_insert_fields(table_name)
    
    # For subservice_org, all model columns should be in INSERT
    
    missing_in_db = model_columns - db_columns
    assert not missing_in_db, (
        f"SubserviceOrg model defines columns not in database: {missing_in_db}"
    )
    
    missing_in_model = db_columns - model_columns
    assert not missing_in_model, (
        f"SubserviceOrg database has columns not in model: {missing_in_model}"
    )
    
    missing_in_insert = model_columns - insert_fields
    assert not missing_in_insert, (
        f"SubserviceOrg fields not in TABLE_FIELD_MAP: {missing_in_insert}\n"
        f"This will cause data loss from extractor!"
    )
    
    invalid_fields = insert_fields - model_columns
    assert not invalid_fields, (
        f"TABLE_FIELD_MAP has invalid SubserviceOrg fields: {invalid_fields}"
    )
    
    print(f"✅ SubserviceOrg schema validation passed: {len(model_columns)} fields aligned")


@pytest.mark.asyncio
async def test_company_schema_alignment(db_session):
    """Validate Company table schema alignment"""
    table_name = 'company'
    
    db_columns = await get_database_columns(db_session, table_name)
    model_columns = get_model_columns(MODEL_MAP[table_name])
    insert_fields = get_insert_fields(table_name)
    
    missing_in_db = model_columns - db_columns
    assert not missing_in_db, f"Company model/DB mismatch: {missing_in_db}"
    
    missing_in_model = db_columns - model_columns
    assert not missing_in_model, f"Company DB/model mismatch: {missing_in_model}"
    
    missing_in_insert = model_columns - insert_fields
    assert not missing_in_insert, f"Company INSERT missing: {missing_in_insert}"
    
    invalid_fields = insert_fields - model_columns
    assert not invalid_fields, f"Company INSERT invalid: {invalid_fields}"
    
    print(f"✅ Company schema validation passed: {len(model_columns)} fields aligned")


@pytest.mark.asyncio
async def test_product_schema_alignment(db_session):
    """Validate Product table schema alignment"""
    table_name = 'product'
    
    db_columns = await get_database_columns(db_session, table_name)
    model_columns = get_model_columns(MODEL_MAP[table_name])
    insert_fields = get_insert_fields(table_name)
    
    missing_in_db = model_columns - db_columns
    assert not missing_in_db, f"Product model/DB mismatch: {missing_in_db}"
    
    missing_in_model = db_columns - model_columns
    assert not missing_in_model, f"Product DB/model mismatch: {missing_in_model}"
    
    missing_in_insert = model_columns - insert_fields
    assert not missing_in_insert, f"Product INSERT missing: {missing_in_insert}"
    
    invalid_fields = insert_fields - model_columns
    assert not invalid_fields, f"Product INSERT invalid: {invalid_fields}"
    
    print(f"✅ Product schema validation passed: {len(model_columns)} fields aligned")


@pytest.mark.asyncio
async def test_no_orphaned_insert_fields(db_session):
    """
    Validate that TABLE_FIELD_MAP doesn't contain fields that don't exist in models.
    This catches typos and obsolete field references.
    """
    all_issues = []
    
    for table_name, model_class in MODEL_MAP.items():
        model_columns = get_model_columns(model_class)
        insert_fields = get_insert_fields(table_name)
        
        orphaned = insert_fields - model_columns
        if orphaned:
            all_issues.append(f"{table_name}: {orphaned}")
    
    assert not all_issues, (
        f"TABLE_FIELD_MAP contains fields not in models:\n" +
        "\n".join(all_issues)
    )
    
    print("✅ No orphaned fields in TABLE_FIELD_MAP")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
