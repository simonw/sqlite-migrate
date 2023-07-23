from dataclasses import dataclass
import datetime
from typing import Callable, Optional


class Migrations:
    migrations_table = "_sqlite_migrations"

    @dataclass
    class _Migration:
        name: str
        fn: Callable

    def __init__(self, name: str):
        """
        :param name: The name of the migration set. This should be unique.
        """
        self.name = name
        self._migrations = []

    def __call__(self, *, name: Optional[str] = None) -> Callable:
        """
        :param name: The name to use for this migration - if not provided,
          the name of the function will be used
        """

        def inner(func: Callable) -> Callable:
            self._migrations.append(self._Migration(name or func.__name__, func))
            return func

        return inner

    def pending(self, db: "sqlite_utils.Database"):
        """
        Return a list of pending migrations.
        """
        self.ensure_migrations_table(db)
        already_applied = {r["name"] for r in db[self.migrations_table].rows}
        return [
            migration
            for migration in self._migrations
            if migration.name not in already_applied
        ]

    def apply(self, db: "sqlite_utils.Database"):
        """
        Apply any pending migrations to the database.
        """
        self.ensure_migrations_table(db)
        for migration in self.pending(db):
            migration.fn(db)
            db[self.migrations_table].insert(
                {
                    "migration_set": self.name,
                    "name": migration.name,
                    "applied_at": str(datetime.datetime.utcnow()),
                }
            )

    def ensure_migrations_table(self, db: "sqlite_utils.Database"):
        """
        Create _sqlite_migrations table if it doesn't already exist
        """
        if not db[self.migrations_table].exists():
            db[self.migrations_table].create(
                {
                    "migration_set": str,
                    "name": str,
                    "applied_at": str,
                },
                pk="name",
            )

    def __repr__(self):
        return "<Migrations '{}': [{}]>".format(
            self.name, ", ".join(m.name for m in self._migrations)
        )
