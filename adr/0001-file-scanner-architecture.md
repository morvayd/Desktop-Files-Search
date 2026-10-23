# ADR 0001: File Scanner Architecture

## Status
Accepted; reflects the current scanner, GUI, and SQLite schema.

## Context
The application scans configured folders recursively and stores file and directory metadata in a local SQLite database. It is intended for local file indexing on Windows, macOS, and Linux, without requiring a separate database server. The current scanner implementation and Tkinter interface are both in `file_scanner_gui.py`.

The design has evolved to support scans of multiple configured roots, distinguish empty directories, and avoid replacing the last completed index until a new scan finishes successfully.

## Decisions

### 1. Storage engine: SQLite
- SQLite is a serverless, file-based database suitable for a local scanner.
- The database is stored at `SQLite/SearchDB.sqlite`, relative to `file_scanner_gui.py`.
- Database access uses Python's standard-library `sqlite3` module.
- Connections select `PRAGMA journal_mode=MEMORY` to support writes on the project's exFAT volume. This reduces rollback protection if the process or machine stops during a write; a filesystem and journal mode with SQLite-supported locking and durable journaling are preferable when stronger crash recovery is required.

### 2. Data access: pandas
- `pandas` is used to read configured scan roots and append batches of scan metadata to SQLite.
- `FoldersToScan` is read with `pandas.read_sql_query`; scan batches are appended with `DataFrame.to_sql`.

### 3. Recursive traversal: `os.walk`
- `os.walk` recursively visits the configured root and its descendant directories.
- Files are recorded with their parent path, name, complete path, extension, size, and last-modified timestamp.
- Descendant directories are recorded as well. The selected root is recorded only when it is itself empty.
- Empty directories are identified when the current `os.walk` result has no child directories and no files. Their records go to `EmptyFolders`; files and non-empty directory records go to `ScanFolders`.
- The scanner raises on missing roots. `os.walk` directory traversal errors and directory stat failures are collected in `TemporaryUnableToScan`; inaccessible files are silently skipped. The app reports each configured root and its scan start time without printing inaccessible-path warnings.
- Symbolic-link directories are not followed because `os.walk` uses its default `followlinks=False`.

### 4. Scan staging and replacement
- At the start of a scan run, `TemporaryScanFolders`, `TemporaryEmptyFolders`, and `TemporaryUnableToScan` are dropped and recreated with the current result schemas.
- Results and inaccessible-directory records from every configured root are appended to these temporary tables.
- Once all configured roots finish and staged writes succeed, the application replaces `ScanFolders`, `EmptyFolders`, and `UnableToScan` with the temporary tables inside a SQLite transaction.
- The obsolete `Empty` table is dropped as part of that replacement if it exists.
- If a missing root, database operation, or other unhandled error stops scanning or saving before replacement, the previous live result tables remain in place. Inaccessible directories are logged and do not stop the scan; inaccessible file stat failures are silently skipped. Partial temporary tables may remain until the next run, when they are recreated.
- `ScanTime` stores per-root start time, end time, elapsed duration, and root path. Timing rows are written during scanning and are separate from the staged index tables.

### 5. Result schema
Both scan-result tables use the following columns:

| Column | Meaning |
| --- | --- |
| `FilePath` | Parent directory path. |
| `FileName` | File or directory name. |
| `CompleteFile` | Complete file or directory path. |
| `corpus` | Search text derived from `CompleteFile` by replacing `/`, hyphens, and periods with spaces. File rows also replace underscores with spaces. |
| `IsDirectory` | `0` for file rows; `1` for directory rows. |
| `Extension` | Lowercase file extension; empty for directories. |
| `Size` | File size or directory metadata size in bytes. |
| `LastModified` | Local timestamp formatted as `%Y-%m-%d %H:%M:%S`. |

`ScanFolders` contains file rows and non-empty directory rows. `EmptyFolders` contains empty-directory rows, with `IsDirectory = 1`.

`UnableToScan` contains `ScanRoot`, `DirectoryPath`, `Error`, and `ScanTime` columns for directories that could not be traversed or stat'ed.

### 6. Path and default-root handling
- `pathlib.Path` is used to locate the script directory, create the database directory, and resolve the user's home directory.
- On first initialization, if `FoldersToScan` is empty, the scanner adds `Path.home() / "Documents"` as the default root on Windows, macOS, and Linux.
- Users can add additional roots in `FoldersToScan`; all configured roots are scanned in one run before the live index tables are replaced.
- File `CompleteFile` values are assembled by joining the walked root and filename. Directory paths come from `os.walk`.

### 7. Other tables
- `FoldersToScan` stores configured root paths and a `DateLastScan` field.
- `ScanTime` stores timing information for each configured root.
- `UnableToScan` stores inaccessible-directory details from the last completed run and is replaced from its staging table after scanning.
- The unused `CompletePath` column was removed from the schema and existing database. `CompleteFile` is the supported complete-path field.

### 8. Project documentation
- Architecture Decision Records are stored in the `adr/` directory.
- The README documents setup, GUI usage, and the local database. Update this ADR when the storage, traversal, schema, replacement policy, or GUI integration changes.

### 9. GUI application
- `file_scanner_gui.py` contains the scan logic and provides a Tkinter interface for viewing and editing configured scan roots, saving them to the database, starting scans, and viewing output.
- On startup, the GUI creates the SQLite directory as needed, initializes the folder configuration and timing tables, and adds the user's `Documents` folder if no roots are configured.
- The selectable Treeview presents each configured root as a whole row. The user can browse for a folder, enter a path, add an existing path, edit and apply changes to a selected root, remove a selected root, and save the displayed list to the database. Clearing all roots requires confirmation.
- Scans run on a background thread. The GUI disables folder-management and scan controls during the scan, then re-enables them and reloads the displayed roots when the worker completes.
- The GUI routes Python logging records and scan `stdout`/`stderr` to its Console Output widget through a thread-safe queue.
- Scan completion is reported with a success or failure dialog based on whether the scan call raises an exception. Missing roots fail the scan; inaccessible directories are recorded while the rest of the scan proceeds.
- An **About** button opens a dialog showing `Created By:  Daniel Morvay,` and `GitHub Account:  https://github.com/morvayd/`.

## Consequences

### Positive
- No database server is required, and the index remains in one local SQLite database.
- Multiple configured roots contribute to one complete scan result.
- Empty directories are retained separately from the main file/non-empty-directory index.
- Staging prevents an incomplete scan from replacing the previous completed index.
- Recursive traversal uses Python's standard library and works across supported operating systems.

### Negative / risks
- Scanning large roots can take substantial time and produce a large database.
- `pandas` remains an external runtime dependency.
- `journal_mode=MEMORY` has weaker recovery guarantees for interrupted writes than a durable disk-backed journal.
- SQLite remains a single-writer database; concurrent scanner processes are not supported by this workflow.
- Symbolic-link directories are not followed by the current traversal and are not recorded as directory rows.
- `corpus` normalization currently differs slightly between file and directory records: file paths also replace underscores, while directory paths do not.
