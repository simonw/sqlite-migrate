# sqlite-migrate: Comprehensive API Design Review

## Executive Summary

sqlite-migrate is a compact (~240 lines of core code) migration system for SQLite built on sqlite-utils. The API surface is small: one class (`Migrations`) with five public methods, and one CLI command (`migrate`) with three options. This review identifies **14 design concerns** across safety, usability, correctness, and extensibility, ranked by severity.

---

## 1. Critical: No Transaction Safety Around Migrations

**Location:** `sqlite_migrate/__init__.py:71-87` (`apply` method)

**Problem:** Each migration function is executed and recorded individually with no transaction wrapping. If a migration function partially modifies the database and then raises an exception, the database is left in a corrupt intermediate state with no rollback and no record of the failed migration.

```python
def apply(self, db, *, stop_before=None):
    for migration in self.pending(db):
        migration.fn(db)           # <- can fail mid-way, leaving partial changes
        _table(db, ...).insert({   # <- never reached if fn() raises
            "migration_set": self.name,
            "name": name,
            ...
        })
```

**Impact:** Users have no way to recover from a failed migration without manual database surgery. There is no indication of which migration failed or what state the database is in.

**Recommendations:**
- Wrap each individual migration in a transaction (`db.conn.execute("BEGIN"); ... db.conn.execute("COMMIT")`) so that a failed migration rolls back cleanly
- Consider recording failed migrations with an error status so that `--list` can surface what went wrong
- At minimum, catch exceptions and re-raise with context about which migration failed

---

## 2. Critical: Security Risk from `exec()` of Arbitrary Python Files

**Location:** `sqlite_migrate/sqlite_utils_plugin.py:50-53`

```python
for filepath in files:
    code = filepath.read_text()
    namespace = {}
    exec(code, namespace)
```

**Problem:** The CLI discovers and executes Python files via `exec()` with no sandboxing. When called without arguments, it recursively searches the current directory for any file named `migrations.py` and executes it. This is a design choice inherent to the "migrations as Python code" approach, but the recursive discovery pattern amplifies the risk.

**Impact:** A malicious `migrations.py` placed anywhere in a directory tree will be silently executed. This is particularly dangerous in shared environments or CI pipelines.

**Recommendations:**
- Document the security implications prominently
- Consider requiring explicit opt-in for recursive directory scanning rather than making it the default
- Consider a `--dry-run` mode that lists discovered files without executing them
- The `--list` flag partially addresses this but still executes the files (via `exec`) to discover `Migrations` instances

---

## 3. High: Migration Ordering Is Fragile and Implicit

**Location:** `sqlite_migrate/__init__.py:36-38`

**Problem:** Migration order is determined solely by Python decorator execution order (i.e., the order functions appear in the source file). There are no sequence numbers, timestamps, or explicit ordering mechanisms. This creates several issues:

1. **No cross-file ordering guarantees** - When multiple `migrations.py` files are discovered, the order between files depends on filesystem iteration order of `rglob()` and Python `set()` ordering, both of which are non-deterministic
2. **No protection against reordering** - If a user accidentally reorders functions in the file, applied migrations won't re-run (correct), but future pending migrations will execute in the new order
3. **No dependency declaration** - Migrations cannot declare dependencies on other migrations or other migration sets

**Evidence:** The `files = set()` on `sqlite_utils_plugin.py:42` means files are stored in a hash-set with no guaranteed iteration order. Multiple migration sets from different files will be applied in arbitrary order.

**Recommendations:**
- Sort discovered files deterministically (e.g., by path) before execution
- Consider adding optional numeric prefixes or explicit ordering to migration names
- For cross-set dependencies, consider an `after=` or `depends_on=` parameter on the decorator

---

## 4. High: `display_list` Has a Logic Bug

**Location:** `sqlite_migrate/sqlite_utils_plugin.py:100-118`

```python
def display_list(db, migration_sets):
    applied = set()
    for migration_set in migration_sets:
        ...
        for migration in migration_set.applied(db):
            print("    {} - {}".format(migration.name, migration.applied_at))
            applied.add(migration.name)
        ...
        for migration in migration_set.pending(db):
            output = True
            if migration.name not in applied:  # <- bug: filters pending by cross-set applied names
                print("    {}".format(migration.name))
```

**Problem:** The `applied` set accumulates migration names across all migration sets. If migration set A has an applied migration named `foo`, and migration set B has a *pending* migration also named `foo`, the pending migration in set B will be silently hidden from the `--list` output. The `pending()` method correctly scopes by `migration_set`, but the display function incorrectly filters across sets.

**Recommendation:** Remove the cross-set `applied` name check entirely, or scope it per migration set. The `pending()` method already correctly excludes applied migrations for the given set.

---

## 5. High: No Programmatic API for Common Operations

**Problem:** The library provides a `Migrations` class for the Python API, but several operations are only available through the CLI:

- **Migration discovery** (scanning filesystem for `migrations.py` files) is only in the CLI code
- **Schema diffing** (verbose mode) is only in the CLI code
- **Listing migrations** in a formatted way is only in the CLI code

Users who want to integrate sqlite-migrate into a larger application (e.g., a web framework, a test harness, or a CI pipeline) cannot reuse any of this logic without importing CLI internals.

**Recommendations:**
- Extract filesystem discovery into a standalone function: `discover_migrations(paths: List[Path]) -> List[Migrations]`
- Make `display_list` logic available as a data-returning method (not just `print()`)
- Consider a `migrate()` top-level convenience function that combines discovery and application

---

## 6. Medium: `Migrations` Class Uses `__call__` as a Decorator Factory

**Location:** `sqlite_migrate/__init__.py:30-40`

```python
migration = Migrations("creatures")

@migration()       # <- note the parentheses
def create_table(db):
    ...
```

**Problem:** Using `__call__` on the class instance as a decorator factory is unusual and potentially confusing:

1. `migration()` looks like a function call, not a decorator registration
2. The parentheses are required (for the `name=` parameter) but easy to forget—`@migration` without parentheses silently fails by passing the decorated function as `self` to a new `Migrations` instance
3. The naming convention (`migration = Migrations(...)` then `@migration()`) means the variable name `migration` reads as singular but represents the collection

**Recommendation:** Consider adding a dedicated method name:
```python
@migration.register()           # or
@migration.step()               # or
@migration.add()
```
This makes intent clearer and avoids the `__call__` overload confusion. Alternatively, if `__call__` is kept, add a runtime check: if `__call__` receives a callable as the first positional argument, raise a `TypeError` with a helpful message about the required parentheses.

---

## 7. Medium: No Migration Rollback / Down Migrations

**Problem:** The API only supports forward migrations. There is no mechanism to reverse a migration. While this is an intentional simplification (and many migration systems share this limitation), the complete absence means:

1. No way to test a migration in isolation and then undo it
2. Development workflows require manual database recreation
3. `--stop-before` only works for *pending* migrations—there is no way to "undo" an already-applied migration

**Recommendation:** This is noted as a known limitation. If rollback is out of scope, document it explicitly as a design decision. Consider at minimum a `mark_unapplied(db, name)` method that removes the record from `_sqlite_migrations` (without reversing schema changes), which would allow re-running a migration during development.

---

## 8. Medium: `ensure_migrations_table` Is Called Redundantly

**Location:** `sqlite_migrate/__init__.py:42-57, 59-69, 71-87, 89-110`

**Problem:** Every public method (`pending`, `applied`, `apply`) calls `ensure_migrations_table(db)`. The `apply` method calls it directly and also indirectly through `pending()`:

```python
def apply(self, db, *, stop_before=None):
    self.ensure_migrations_table(db)          # call 1
    for migration in self.pending(db):        # pending() calls it again (call 2)
        ...
```

This means the table existence check runs at least twice per `apply()` call. While cheap for SQLite, it's a code smell that suggests the initialization responsibility is unclear.

**Recommendations:**
- Make `ensure_migrations_table` idempotent and cheap (already is), but call it in a single place—either at the start of each public method OR lazily on first database access
- Consider a `_table_ensured` flag per `(db, table_name)` pair to avoid repeated checks

---

## 9. Medium: No Validation of Migration Names

**Problem:** Migration names are not validated for uniqueness or format:

1. **Duplicate names within a set:** If two `@migration()` decorated functions have the same name, both are appended to `_migrations`. The first will run and be recorded; the second will be skipped by `pending()` because the name is already in `already_applied`. This silent deduplication could mask bugs.
2. **No name format restrictions:** Names can contain any characters, including spaces, SQL-special characters, or empty strings.
3. **No migration set name validation:** The `Migrations("name")` constructor accepts any string with no restrictions.

**Recommendations:**
- Raise an error if a duplicate migration name is registered within the same set
- Validate that names are non-empty and contain only safe characters
- Warn if a migration set name conflicts with an existing set in the database

---

## 10. Medium: `applied()` Does Not Preserve Registration Order

**Location:** `sqlite_migrate/__init__.py:59-69`

```python
def applied(self, db):
    return [
        self._AppliedMigration(name=row["name"], applied_at=row["applied_at"])
        for row in db[self.migrations_table].rows_where(
            "migration_set = ?", [self.name]
        )
    ]
```

**Problem:** The `applied()` method returns rows in database insertion order (by `id`), which matches application order. However, it does not return them in the *registration* order that `pending()` uses. If migrations were somehow applied out of registration order (e.g., due to code changes between runs), the `applied` and `pending` lists would use inconsistent orderings.

More practically, the `applied()` method returns `_AppliedMigration` objects that lack the `fn` field, making the applied/pending return types asymmetric and harder to work with generically.

**Recommendation:** Consider adding an explicit `ORDER BY id` to the query for clarity, and unify the return types or provide a single method that returns all migrations with their status.

---

## 11. Low: CLI Mixes `print()` and `click.echo()`

**Location:** `sqlite_migrate/sqlite_utils_plugin.py`

The `migrate` function uses `click.echo()` (lines 74-97) while `display_list` uses `print()` (lines 103-117). This inconsistency means:

1. `click.echo()` respects Click's output handling (e.g., piping, encoding)
2. `print()` does not, and can fail in some environments with encoding issues

**Recommendation:** Use `click.echo()` consistently throughout.

---

## 12. Low: `_AppliedMigration.applied_at` Is a `str`, Not `datetime`

**Location:** `sqlite_migrate/__init__.py:19-21`

```python
@dataclass
class _AppliedMigration:
    name: str
    applied_at: datetime.datetime  # <- type hint says datetime
```

The type hint declares `applied_at` as `datetime.datetime`, but the value stored in and retrieved from the database is an ISO 8601 string. The `applied()` method passes the raw string from the database:

```python
self._AppliedMigration(name=row["name"], applied_at=row["applied_at"])
```

**Impact:** The type hint is misleading. Code that relies on `applied_at` being a `datetime` object (e.g., calling `.strftime()`) will fail at runtime.

**Recommendation:** Either parse the string into a `datetime` object in `applied()`, or change the type hint to `str`.

---

## 13. Low: No `__all__` Export in `__init__.py`

**Location:** `sqlite_migrate/__init__.py`

**Problem:** The module does not define `__all__`, so `from sqlite_migrate import *` will export everything in the module namespace, including the internal `_table` helper function and all imported modules (`dataclasses`, `datetime`, `cast`, etc.).

**Recommendation:** Add `__all__ = ["Migrations"]` to explicitly declare the public API.

---

## 14. Low: Dependency Version Not Pinned

**Location:** `pyproject.toml:12-14`

```toml
dependencies = [
    "sqlite-utils"
]
```

**Problem:** No minimum version of `sqlite-utils` is specified. The library uses features like `table.transform()`, `table.indexes`, and the plugin hook system, which were added in specific sqlite-utils versions. A user with an old sqlite-utils installation will get cryptic `AttributeError` failures.

**Recommendation:** Pin a minimum version, e.g., `sqlite-utils>=3.17` (or whichever version introduced the `hookimpl`/plugin system and `transform()`).

---

## API Surface Summary

| Component | Public API | Assessment |
|-----------|-----------|------------|
| `Migrations.__init__(name)` | Constructor | Clean, simple |
| `Migrations.__call__(*, name=)` | Decorator factory | Works but unconventional (see #6) |
| `Migrations.pending(db)` | Query pending | Good, clear semantics |
| `Migrations.applied(db)` | Query applied | Type hint mismatch (see #12) |
| `Migrations.apply(db, *, stop_before=)` | Execute migrations | Missing transaction safety (see #1) |
| `Migrations.ensure_migrations_table(db)` | Schema setup | Should be internal/private |
| `Migrations.migrations_table` | Class attribute | Reasonable extension point |
| CLI: `migrate` | Main command | Good ergonomics |
| CLI: `--list` | Inspection flag | Has display bug (see #4) |
| CLI: `--verbose` | Debug flag | Useful, well-implemented |
| CLI: `--stop-before` | Partial apply | Good for development |

## Prioritized Action Items

1. **Fix `display_list` cross-set filtering bug** (#4) - straightforward bug fix
2. **Add transaction wrapping around individual migrations** (#1) - critical for production safety
3. **Sort discovered files deterministically** (#3) - one-line fix with large correctness impact
4. **Fix `_AppliedMigration.applied_at` type** (#12) - type correctness
5. **Use `click.echo()` consistently** (#11) - minor consistency fix
6. **Add `__all__` export** (#13) - minor API hygiene
7. **Pin minimum sqlite-utils version** (#14) - dependency safety
8. **Validate duplicate migration names** (#9) - error prevention
9. **Extract discovery logic into public API** (#5) - usability improvement
10. **Document security implications of `exec()`** (#2) - user awareness
11. **Consider decorator API alternatives** (#6) - API ergonomics (breaking change)
12. **Remove redundant `ensure_migrations_table` calls** (#8) - code clarity
13. **Add explicit `ORDER BY`** (#10) - defensive correctness
14. **Document rollback limitations** (#7) - user expectations
