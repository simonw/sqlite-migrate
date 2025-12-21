from sqlite_migrate import Migrations
import sqlite_utils
import pytest


@pytest.fixture
def migrations():
    migrations = Migrations("test")

    @migrations()
    def m001(db):
        db["dogs"].insert({"name": "Cleo"})

    @migrations()
    def m002(db):
        db["cats"].create({"name": str})
        db.query("insert into dogs (name) values ('Pancakes')")

    return migrations


@pytest.fixture
def migrations_not_ordered_alphabetically():
    # Names order alphabetically in the wrong direction but this
    # should still be applied correctly
    migrations = Migrations("test")

    @migrations()
    def m002(db):
        db["dogs"].insert({"name": "Cleo"})

    @migrations()
    def m001(db):
        db["cats"].create({"name": str})
        db.query("insert into dogs (name) values ('Pancakes')")

    return migrations


@pytest.fixture
def migrations2():
    migrations = Migrations("test2")

    @migrations()
    def m001(db):
        db["dogs2"].insert({"name": "Cleo"})

    return migrations


def test_basic(migrations):
    db = sqlite_utils.Database(memory=True)
    assert db.table_names() == []
    migrations.apply(db)
    assert set(db.table_names()) == {"_sqlite_migrations", "dogs", "cats"}


def test_stop_before(migrations):
    db = sqlite_utils.Database(memory=True)
    assert db.table_names() == []
    migrations.apply(db, stop_before="m002")
    assert set(db.table_names()) == {"_sqlite_migrations", "dogs"}
    # Apply the rest
    migrations.apply(db)
    assert set(db.table_names()) == {"_sqlite_migrations", "dogs", "cats"}


def test_two_migration_sets(migrations, migrations2):
    db = sqlite_utils.Database(memory=True)
    assert db.table_names() == []
    migrations.apply(db)
    migrations2.apply(db)
    assert set(db.table_names()) == {"_sqlite_migrations", "dogs", "cats", "dogs2"}


def test_order_does_not_matter(migrations, migrations_not_ordered_alphabetically):
    db1 = sqlite_utils.Database(memory=True)
    db2 = sqlite_utils.Database(memory=True)
    migrations.apply(db1)
    migrations_not_ordered_alphabetically.apply(db2)
    assert db1.schema == db2.schema


@pytest.mark.parametrize(
    "create_table,pk",
    (
        # Original with pk name
        (
            {
                "migration_set": str,
                "name": str,
                "applied_at": str,
            },
            "name",
        ),
        # Second version pk migraiton_set, name
        (
            {
                "migration_set": str,
                "name": str,
                "applied_at": str,
            },
            ("migration_set", "name"),
        ),
    ),
)
def test_upgrades_sqlite_migrations(migrations, create_table, pk):
    db = sqlite_utils.Database(memory=True)
    table = db["_sqlite_migrations"].create(create_table, pk=pk)
    print(table.schema)
    # Applying migrations should fix that
    assert db.table_names() == ["_sqlite_migrations"]
    assert db["_sqlite_migrations"].pks == [pk] if isinstance(pk, str) else pk
    migrations.apply(db)
    assert db["_sqlite_migrations"].pks == ["id"]


def test_dry_run(migrations):
    db = sqlite_utils.Database(memory=True)
    assert db.table_names() == []

    # Dry run should return result with schema info but not modify database
    result = migrations.apply(db, dry_run=True)

    # Database should still be empty (except migrations table from ensure_migrations_table)
    assert "dogs" not in db.table_names()
    assert "cats" not in db.table_names()

    # Result should contain schema information
    assert result is not None
    assert result.before_schema is not None
    assert result.after_schema is not None
    assert "dogs" in result.after_schema
    assert "cats" in result.after_schema
    assert result.applied == ["m001", "m002"]

    # Now actually apply and verify it works
    migrations.apply(db)
    assert set(db.table_names()) == {"_sqlite_migrations", "dogs", "cats"}


def test_dry_run_with_stop_before(migrations):
    db = sqlite_utils.Database(memory=True)

    # Dry run with stop_before
    result = migrations.apply(db, dry_run=True, stop_before="m002")

    # Should only show m001 as applied
    assert result.applied == ["m001"]
    assert "dogs" in result.after_schema
    assert "cats" not in result.after_schema

    # Database should still be unchanged
    assert "dogs" not in db.table_names()


def test_dry_run_no_pending(migrations):
    db = sqlite_utils.Database(memory=True)

    # Apply migrations first
    migrations.apply(db)

    # Dry run with no pending migrations
    result = migrations.apply(db, dry_run=True)

    assert result is not None
    assert result.applied == []
    assert result.before_schema == result.after_schema


def test_dry_run_with_data():
    """Test dry_run_with_data copies data for migrations that need it."""
    migrations = Migrations("data_test")

    @migrations()
    def create_table(db):
        db["items"].create({"id": int, "name": str}, pk="id")

    @migrations()
    def count_items(db):
        # This migration needs data to work correctly
        count = list(db.execute("SELECT COUNT(*) FROM items").fetchone())[0]
        db["stats"].insert({"item_count": count})

    db = sqlite_utils.Database(memory=True)

    # Create table and insert some data
    db["items"].create({"id": int, "name": str}, pk="id")
    db["items"].insert_all([{"id": 1, "name": "one"}, {"id": 2, "name": "two"}])

    # Mark first migration as already applied
    migrations.ensure_migrations_table(db)
    db["_sqlite_migrations"].insert(
        {"migration_set": "data_test", "name": "create_table", "applied_at": "2024-01-01"}
    )

    # dry_run_with_data should copy the data
    result = migrations.apply(db, dry_run_with_data=True)

    assert result is not None
    assert result.applied == ["count_items"]
    assert "stats" in result.after_schema

    # Original database should be unchanged
    assert "stats" not in db.table_names()
    assert list(db["items"].rows) == [{"id": 1, "name": "one"}, {"id": 2, "name": "two"}]
