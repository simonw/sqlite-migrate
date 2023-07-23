from sqlite_migrate import Migrations
import sqlite_utils


def test_basic():
    db = sqlite_utils.Database(memory=True)
    assert db.table_names() == []
    migrations = Migrations("test")

    @migrations()
    def m001(db):
        db["dogs"].insert({"name": "Cleo"})

    @migrations()
    def m002(db):
        db["cats"].create({"name": str})

    migrations.apply(db)
    assert set(db.table_names()) == {"_sqlite_migrations", "dogs", "cats"}
