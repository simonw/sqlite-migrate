import sqlite_utils.cli
import pathlib
from click.testing import CliRunner
import pytest

TWO_MIGRATIONS = """
from sqlite_migrate import Migrations

m = Migrations("hello")

@m()
def foo(db):
    db["foo"].insert({"hello": "world"})

@m()
def bar(db):
    db["bar"].insert({"hello": "world"})
"""


@pytest.fixture
def two_migrations(tmpdir):
    path = pathlib.Path(tmpdir)
    (path / "foo").mkdir()
    migrations_py = path / "foo" / "migrations.py"
    migrations_py.write_text(TWO_MIGRATIONS, "utf-8")
    return path, migrations_py


@pytest.mark.parametrize("arg", ("TMPDIR", "TMPDIR/foo/migrations.py", "TMPDIR/foo/"))
def test_basic(two_migrations, arg):
    path, _ = two_migrations
    db_path = str(path / "test.db")

    runner = CliRunner()

    def _list():
        list_result = runner.invoke(
            sqlite_utils.cli.cli,
            ["migrate", db_path, "--list", arg.replace("TMPDIR", str(path))],
        )
        assert list_result.exit_code == 0
        return list_result.output

    assert _list() == (
        "Migrations for: hello\n\n"
        "  Applied:\n\n"
        "  Pending:\n"
        "    foo\n"
        "    bar\n\n"
    )

    result = runner.invoke(
        sqlite_utils.cli.cli, ["migrate", db_path, arg.replace("TMPDIR", str(path))]
    )
    assert result.exit_code == 0, result.output

    list_output = _list()
    assert "Migrations for: hello\n\n  Applied:\n    " in list_output
    prior_to_pending = list_output.split(" Pending")[0]
    assert "  foo" in prior_to_pending
    assert "  bar" in prior_to_pending
    assert " Pending:\n    (none)" in list_output

    db = sqlite_utils.Database(db_path)
    assert db["foo"].exists()
    assert db["bar"].exists()
    assert db["_sqlite_migrations"].exists()
    rows = list(db["_sqlite_migrations"].rows)
    assert len(rows) == 2
    assert rows[0]["name"] == "foo"
    assert rows[1]["name"] == "bar"


def test_verbose(tmpdir):
    path = pathlib.Path(tmpdir)
    (path / "foo").mkdir()
    migrations_py = path / "foo" / "migrations.py"
    migrations_py.write_text(
        """
from sqlite_migrate import Migrations

m = Migrations("hello")

@m()
def foo(db):
    db["dogs"].insert({"id": 1, "name": "Cleo"})
    """,
        "utf-8",
    )
    db_path = str(path / "test.db")
    runner = CliRunner()
    result = runner.invoke(
        sqlite_utils.cli.cli, ["migrate", db_path, str(migrations_py)]
    )
    assert result.exit_code == 0
    # Now run again with --verbose, should be no changes
    result = runner.invoke(
        sqlite_utils.cli.cli, ["migrate", db_path, str(migrations_py), "--verbose"]
    )
    assert result.exit_code == 0
    expected = """
Schema before:

  CREATE TABLE [_sqlite_migrations] (
     [migration_set] TEXT,
     [name] TEXT,
     [applied_at] TEXT,
     PRIMARY KEY ([migration_set], [name])
  );
  CREATE TABLE [dogs] (
     [id] INTEGER,
     [name] TEXT
  );

Schema after:

  (unchanged)
""".strip()
    assert expected in result.output
    # Now append to the migration and run it
    new_migration = """
@m()
def bar(db):
    db["dogs"].add_column("age", int)
    db["dogs"].add_column("weight", float)
    db["dogs"].transform()
"""
    # Append that to migrations.py
    migrations_py.write_text(migrations_py.read_text("utf-8") + new_migration)

    # And run it
    result = runner.invoke(
        sqlite_utils.cli.cli, ["migrate", db_path, str(migrations_py), "--verbose"]
    )
    assert result.exit_code == 0
    expected_diff = """
Schema diff:

    [applied_at] TEXT,
    PRIMARY KEY ([migration_set], [name])
 );
-CREATE TABLE [dogs] (
+CREATE TABLE "dogs" (
    [id] INTEGER,
-   [name] TEXT
+   [name] TEXT,
+   [age] INTEGER,
+   [weight] FLOAT
 );
""".strip()
    assert expected_diff in result.output


def test_stop_before(two_migrations):
    path, _ = two_migrations
    db_path = str(path / "test.db")
    runner = CliRunner()
    result = runner.invoke(
        sqlite_utils.cli.cli,
        [
            "migrate",
            db_path,
            str(path / "foo" / "migrations.py"),
            "--stop-before",
            "bar",
        ],
    )
    assert result.exit_code == 0
    db = sqlite_utils.Database(db_path)
    assert db["foo"].exists()
    assert not db["bar"].exists()


def test_stop_before_error(two_migrations):
    path, _ = two_migrations
    db_path = str(path / "test.db")
    (path / "foo" / "migrations2.py").write_text(
        """
from sqlite_migrate import Migrations

m = Migrations("hello2")

@m()
def foo(db):
    db["foo"].insert({"hello": "world"})
    """,
        "utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        sqlite_utils.cli.cli,
        [
            "migrate",
            db_path,
            str(path / "foo" / "migrations.py"),
            str(path / "foo" / "migrations2.py"),
            "--stop-before",
            "foo",
        ],
    )
    assert result.exit_code == 1
    assert (
        "--stop-before can only be used with a single migrations.py file"
        in result.output
    )
