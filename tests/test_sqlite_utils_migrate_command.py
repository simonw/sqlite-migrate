from sqlite_migrate import Migrations
import sqlite_utils
from sqlite_utils.cli import cli
import click
import pathlib
from click.testing import CliRunner


def test_basic():
    runner = CliRunner()
    with runner.isolated_filesystem():
        path = pathlib.Path(".")
        (path / "foo").mkdir()
        migrations_py = path / "foo" / "migrations.py"
        migrations_py.write_text(
            """
from sqlite_migrate import Migrations

m = Migrations("hello")

@m()
def foo(db):
    db["foo"].insert({"hello": "world"})

@m()
def bar(db):
    db["bar"].insert({"hello": "world"})
    """,
            "utf-8",
        )
        db_path = str(path / "test.db")
        result = runner.invoke(sqlite_utils.cli.cli, ["migrate", db_path])
        assert result.exit_code == 0, result.output
        db = sqlite_utils.Database(db_path)
        assert db["foo"].exists()
        assert db["bar"].exists()
        assert db["_sqlite_migrations"].exists()
        rows = list(db["_sqlite_migrations"].rows)
        assert len(rows) == 2
        assert rows[0]["name"] == "foo"
        assert rows[1]["name"] == "bar"
