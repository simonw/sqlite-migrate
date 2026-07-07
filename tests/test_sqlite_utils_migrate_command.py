import pathlib

from click.testing import CliRunner
import sqlite_utils
import sqlite_utils.cli


def test_sqlite_utils_migrate_command_with_sqlite_migrate_import(tmpdir):
    path = pathlib.Path(tmpdir)
    migrations_py = path / "migrations.py"
    migrations_py.write_text(
        """
from sqlite_migrate import Migrations

migrations = Migrations("hello")

@migrations()
def foo(db):
    db["foo"].insert({"hello": "world"})
""",
        "utf-8",
    )
    db_path = str(path / "test.db")

    result = CliRunner().invoke(
        sqlite_utils.cli.cli, ["migrate", db_path, str(migrations_py)]
    )

    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(db_path)
    assert db["foo"].exists()
