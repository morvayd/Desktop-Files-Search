# Python Local Search

A local desktop application for scanning configured folders, storing file metadata in SQLite, and searching indexed paths with fuzzy matching.

## Features

### File scanner GUI

- Manage folders for recursive scanning in a selectable, whole-row table.
- Browse for a folder or enter a path; adding requires an existing path. Edit and apply changes to a selected row, or remove the selected row.
- Save the displayed folder list to SQLite. Clearing all folders requires confirmation.
- Run scans in a background thread while viewing live console output. Folder controls are disabled during a scan, then restored when it completes.
- Reload the configured folders after a scan and show a success or failure dialog.
- Record files and non-empty directories in `ScanFolders`, empty directories in `EmptyFolders`, inaccessible directories in `UnableToScan`, and per-folder scan durations in `ScanTime`.
- Stage scan results and replace the previous completed index only after every configured folder has been scanned recursively and successfully.
- Open **About** to view the creator name and GitHub account.

### Fuzzy search GUI

- Display the total number of records in `ScanFolders`.
- Search indexed paths with RapidFuzz's `WRatio` scorer and a default 60% score cutoff.
- Exclude one or more case-insensitive terms from matching paths. Enter terms separated by spaces; a path containing any excluded term is removed.
- Display results in descending match-score order, 20 at a time, in a selectable table.
- Navigate result pages with **First**, **Previous**, **Next**, and **Last** controls.
- Reset the query, exclusions, results, status, and current page with **Reset**.
- Press Enter in either search field to start a search. Empty queries show a warning.
- Run searches in a background thread; the query/exclusion fields and **Search**/**Reset** buttons are disabled until results return. Show searching, no-match, and error status messages.
- Check at startup that the SQLite folder, database, and `ScanFolders` table are present. If not, show an on-screen warning with the specific issue; click **OK** to dismiss it.
- Open **About** to view the creator name and GitHub account.

Both About dialogs display:

```text
Created By:  Daniel Morvay,
GitHub Account:  https://github.com/morvayd/
```

## Requirements

- Python 3
- Tkinter (included with many Python distributions; some Linux distributions package it separately)
- pandas
- rapidfuzz

Install the external packages in the Python environment used to run the applications:

```bash
python -m pip install pandas rapidfuzz
```

## Getting started

Run the scanner GUI:

```bash
python file_scanner_gui.py
```

The scanner creates and initializes `SQLite/SearchDB.sqlite` on startup. If no folders are configured for scanning, it adds the current user's `Documents` folder. Browse for or enter a folder path, use **Add Entry**, and edit or remove rows as needed. Select **Save Changes to DB** to persist the displayed folder list, then select **Run Scan** to scan each configured folder and its subfolders recursively. Scanning a large folder tree—including scanning `/` on macOS/Linux or `C:\` on Windows—can take a long time and consume substantial disk space. A configured folder that does not exist causes the run to fail; inaccessible subfolders are recorded in `UnableToScan` while the rest of the scan continues.

After a successful scan, run the fuzzy-search GUI:

```bash
python fuzzy_search_gui.py
```

Enter a search query. To omit paths containing particular text, enter one or more space-separated terms in **Exclude terms**. For example, search for `Dan` and exclude `png` to omit paths containing `png`, including `.png` filenames. Exclusions are case-insensitive and checked against the full path. The search compares the query with the indexed `corpus` text, uses `WRatio` with a 60% cutoff, and returns all qualifying matches in descending score order. Results are shown 20 per page with the visible range and total count. Use the page controls to move through results, and **Reset** to clear the query, exclusions, results, status, and current page. If the database is valid but `ScanFolders` has no rows, the window displays a count of zero and search reports that no indexed file data is available.

This is fuzzy string matching on indexed paths, not semantic search over file contents. The search GUI requires a readable `ScanFolders` table at startup; it does not create the scanner database or table.

## Database

The database is stored at `SQLite/SearchDB.sqlite` relative to the application files.

| Table | Purpose |
| --- | --- |
| `FoldersToScan` | Configured folder paths for recursive scans and their date field. |
| `ScanFolders` | Files and non-empty directories from the last completed scan. This is the table searched and counted by the fuzzy-search GUI. |
| `EmptyFolders` | Empty directories from the last completed scan. |
| `UnableToScan` | Directories that could not be traversed or whose metadata could not be read during the last completed scan. |
| `ScanTime` | Start time, end time, elapsed duration, and folder path for each recursive folder scan. |

The scan-result tables contain `FilePath`, `FileName`, `CompleteFile`, `corpus`, `IsDirectory`, `Extension`, `Size`, and `LastModified` fields. Fuzzy search compares the query against `corpus`, displays matching `CompleteFile` paths, and applies exclusions to the full path.

SQLite connections in the scanner use an in-memory journal for compatibility with exFAT. This provides weaker recovery protection if the process or machine stops during a write. For stronger crash recovery, use a filesystem and journal mode supported by SQLite's locking and durable journaling.

The database can contain private folder paths and filenames. Do not publish it if it contains personal information.

## Project layout

```text
.
├── README.md
├── adr/
│   ├── 0001-file-scanner-architecture.md
│   └── 0002-fuzzy-search-architecture.md
├── file_scanner_gui.py   # Scanner engine and Tkinter interface
├── fuzzy_search_gui.py   # Fuzzy path-search interface
└── SQLite/
    └── SearchDB.sqlite   # Local runtime database
```
