# sqlite-migrate

[![PyPI](https://img.shields.io/pypi/v/sqlite-migrate.svg)](https://pypi.org/project/sqlite-migrate/)
[![Changelog](https://img.shields.io/github/v/release/simonw/sqlite-migrate?include_prereleases&label=changelog)](https://sqlite-migrate.datasette.io/en/stable/changelog.html)
[![Tests](https://github.com/simonw/sqlite-migrate/workflows/Test/badge.svg)](https://github.com/simonw/sqlite-migrate/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/sqlite-migrate/blob/main/LICENSE)

A simple database migration system for SQLite, based on sqlite-utils

**This project is an early alpha. Expect breaking changes.**

## Installation

This tool works as a plugin for [sqlite-utils](https://sqlite-utils.datasette.io/). First install that:

```bash
pip install sqlite-utils
```
Then install this plugin like so:
```bash
sqlite-utils install sqlite-migrate
```
## Migration files

This tool works against migration files. A migration file looks like this:

```python
from sqlite_migrate import Migrations

# Pick a unique name here - it must not clash with other migration sets that
# the user might run against the same database.

migration = Migrations("creatures")

# Use this decorator against functions that implement migrations
@migration()
def m001_create_table(db):
    # db is a sqlite-utils Database instance
    db["creatures"].create(
        {"id": int, "name": str, "species": str},
        pk="id"
    )

@migration()
def m002_add_weight(db):
    # db is a sqlite-utils Database instance
    db["creatures"].add_column("weight", float)
```
Here is [documentation on the Database instance](https://sqlite-utils.datasette.io/en/stable/python-api.html) passed to each migration function.

## Running migrations

Running this command will execute those migrations in sequence against the specified database file.

Call `migrate` with a path to your database and a path to the migrations file you want to apply:
```bash
sqlite-utils migrate creatures.db path/to/migrations.py
```
Running this multiple times will have no additional affect, unless you add more migration functions to the file.

If you call it without arguments it will search for and apply any `migrations.py` files in the current directory or any of its subdirectories.

You can also pass the path to a directory, in which case all `migrations.py` files in that directory and its subdirectories will be applied:

```bash
sqlite-utils migrate creatures.db path/to/parent/
```

## Listing migrations

Add `--list` to list migrations without running them, for example:

```bash
sqlite-utils migrate creatures.db --list
```
The output will look something like this:
```
Migrations for: creatures

  Applied:
    m001_create_table - 2023-07-23 04:09:40.324002
    m002_add_weight - 2023-07-23 04:09:40.324649
    m003_add_age - 2023-07-23 04:09:44.441616
    m003_cleanup - 2023-07-23 04:09:44.443394
    m004_cleanup - 2023-07-23 04:09:44.444184
    m005_cleanup - 2023-07-23 04:09:44.445389
    m006_cleanup - 2023-07-23 04:09:44.446742
    m007_cleanup - 2023-07-23 04:16:02.529983

  Pending:
    m008_cleanup
```

## Verbose mode

Add `-v` or `--verbose` for verbose output, which will show the schema before and after the migrations were applied along with a diff:

```bash
sqlite-utils migrate creatures.db --verbose
```
Example output:
```
Migrating creatures.db

Schema before:

  CREATE TABLE [_sqlite_migrations] (
     [migration_set] TEXT,
     [name] TEXT PRIMARY KEY,
     [applied_at] TEXT
  );
  CREATE TABLE [creatures] (
     [id] INTEGER PRIMARY KEY,
     [name] TEXT,
     [species] TEXT
  , [weight] FLOAT);

Schema after:

  CREATE TABLE [_sqlite_migrations] (
     [migration_set] TEXT,
     [name] TEXT PRIMARY KEY,
     [applied_at] TEXT
  );
  CREATE TABLE "creatures" (
     [id] INTEGER PRIMARY KEY,
     [name] TEXT,
     [species] TEXT,
     [weight] FLOAT,
     [age] INTEGER,
     [shoe_size] INTEGER
  );

Schema diff:

    [name] TEXT PRIMARY KEY,
    [applied_at] TEXT
 );
-CREATE TABLE [creatures] (
+CREATE TABLE "creatures" (
    [id] INTEGER PRIMARY KEY,
    [name] TEXT,
-   [species] TEXT
-, [weight] FLOAT);
+   [species] TEXT,
+   [weight] FLOAT,
+   [age] INTEGER,
+   [shoe_size] INTEGER
+);
```