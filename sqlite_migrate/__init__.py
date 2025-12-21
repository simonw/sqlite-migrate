from dataclasses import dataclass
import datetime
from typing import cast, Callable, List, Optional
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlite_utils.db import Database, Table


@dataclass
class DryRunResult:
    """Result of a dry-run migration."""

    before_schema: str
    after_schema: str
    applied: List[str]


class Migrations:
    migrations_table = "_sqlite_migrations"

    @dataclass
    class _Migration:
        name: str
        fn: Callable

    @dataclass
    class _AppliedMigration:
        name: str
        applied_at: datetime.datetime

    def __init__(self, name: str):
        """
        :param name: The name of the migration set. This should be unique.
        """
        self.name = name
        self._migrations: List[Migrations._Migration] = []

    def __call__(self, *, name: Optional[str] = None) -> Callable:
        """
        :param name: The name to use for this migration - if not provided,
          the name of the function will be used
        """

        def inner(func: Callable) -> Callable:
            self._migrations.append(self._Migration(name or func.__name__, func))
            return func

        return inner

    def pending(self, db: "Database") -> List["Migrations._Migration"]:
        """
        Return a list of pending migrations.
        """
        self.ensure_migrations_table(db)
        already_applied = {
            r["name"]
            for r in db[self.migrations_table].rows_where(
                "migration_set = ?", [self.name]
            )
        }
        return [
            migration
            for migration in self._migrations
            if migration.name not in already_applied
        ]

    def applied(self, db: "Database") -> List["Migrations._AppliedMigration"]:
        """
        Return a list of applied migrations.
        """
        self.ensure_migrations_table(db)
        return [
            self._AppliedMigration(name=row["name"], applied_at=row["applied_at"])
            for row in db[self.migrations_table].rows_where(
                "migration_set = ?", [self.name]
            )
        ]

    def apply(
        self,
        db: "Database",
        *,
        stop_before: Optional[str] = None,
        dry_run: bool = False,
    ) -> Optional[DryRunResult]:
        """
        Apply any pending migrations to the database.

        :param db: The sqlite-utils Database instance
        :param stop_before: Stop before applying this migration
        :param dry_run: If True, run migrations in a transaction then rollback,
            returning a DryRunResult with schema before/after and list of
            migrations that would be applied
        :return: DryRunResult if dry_run=True, otherwise None
        """
        self.ensure_migrations_table(db)
        pending = self.pending(db)

        if dry_run:
            before_schema = db.schema
            applied_names: List[str] = []

            if not pending:
                return DryRunResult(
                    before_schema=before_schema,
                    after_schema=before_schema,
                    applied=[],
                )

            # Create a temporary in-memory copy of the database to run migrations
            # This avoids issues with sqlite-utils auto-committing transactions
            import sqlite3

            temp_conn = sqlite3.connect(":memory:")

            # Copy schema and data from original database
            db.conn.backup(temp_conn)

            # Import Database here to avoid circular import issues
            from sqlite_utils import Database as SqliteDatabase

            temp_db = SqliteDatabase(temp_conn)

            # Run migrations on the temporary copy
            for migration in pending:
                name = migration.name
                if name == stop_before:
                    break
                migration.fn(temp_db)
                applied_names.append(name)

            after_schema = temp_db.schema
            temp_conn.close()

            return DryRunResult(
                before_schema=before_schema,
                after_schema=after_schema,
                applied=applied_names,
            )

        # Normal apply
        for migration in pending:
            name = migration.name
            if name == stop_before:
                return None
            migration.fn(db)
            _table(db, self.migrations_table).insert(
                {
                    "migration_set": self.name,
                    "name": name,
                    "applied_at": str(datetime.datetime.now(datetime.timezone.utc)),
                }
            )
        return None

    def ensure_migrations_table(self, db: "Database"):
        """
        Ensure _sqlite_migrations table exists and has the correct schema
        """
        table = _table(db, self.migrations_table)
        if not table.exists():
            table.create(
                {
                    "id": int,
                    "migration_set": str,
                    "name": str,
                    "applied_at": str,
                },
                pk="id",
            )
            table.create_index(["migration_set", "name"], unique=True)
        elif table.pks != ["id"]:
            # This has an older primary key scheme, upgrade it
            table.transform(pk="id")
            unique_indexes = {tuple(index.columns) for index in table.indexes}
            if ("migration_set", "name") not in unique_indexes:
                table.create_index(["migration_set", "name"], unique=True)

    def __repr__(self):
        return "<Migrations '{}': [{}]>".format(
            self.name, ", ".join(m.name for m in self._migrations)
        )


def _table(db: "Database", name: str) -> "Table":
    # mypy workaround
    return cast("Table", db[name])
