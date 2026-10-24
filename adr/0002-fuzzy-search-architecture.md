# ADR 0002: Fuzzy Search Research Tool Architecture

## Status
Accepted; reflects the current fuzzy-search GUI.

## Context
The fuzzy-search tool ranks paths from the index produced by the file-scanner GUI. It uses RapidFuzz for approximate matching and provides a Tkinter interface for searching, reviewing, filtering, and navigating results. Both GUIs use the same local SQLite database; the fuzzy-search GUI does not import or invoke the scanner GUI.

## Decisions

### 1. Search engine and data
- Search `corpus` values in `ScanFolders`, excluding rows whose `corpus` is `NULL`.
- Use RapidFuzz's `WRatio` scorer with a 60% score cutoff.
- Retrieve every match at or above the cutoff and preserve RapidFuzz's descending match-score order.
- Display each match's score and corresponding `CompleteFile` path.
- Apply excluded terms to the full `CompleteFile` path after fuzzy matching. Terms are whitespace-separated and compared case-insensitively as substrings; a result is removed if its path contains any excluded term.

### 2. GUI and results navigation
- Build the interface with Tkinter and ttk.
- Provide a search query field, an **Exclude terms** field, a **Search** button, and a **Reset** button.
- Show the total `ScanFolders` row count in the search controls.
- Display results in a selectable, two-column Treeview, 20 records per page.
- Allow one result to be selected at a time and provide an **Open Folder** button that opens the selected path when it is a directory, or its containing folder when it is a file.
- Selecting a result displays a path popup next to its row. The popup is positioned about 66 pixels from the Treeview's left edge and is moved left if needed to stay on-screen; it is hidden when the selection is cleared or the results page changes.
- Provide **First**, **Previous**, **Next**, and **Last** navigation. The range indicator reports the visible one-based range and total, including a shorter final page.
- **Reset** clears both input fields, displayed results, status text, and pagination state.
- Pressing Enter in either input field starts a search; an empty query produces a warning.
- Disable the query/exclusion fields and **Search**/**Reset** buttons while a search is running; page controls are updated for the cleared result list.
- Show searching and no-match status text; surface database or other search errors in the status area. A valid empty `ScanFolders` table has a record count of zero and produces a no-indexed-data status.
- Use a 700-by-730 initial window size and request enough Treeview height for 20 result rows.
- Provide **Quit** and **About** buttons in the footer. **Quit** closes the root window.
- **About** opens a custom 360-by-150-pixel dark dialog with the author name, soft-blue clickable GitHub Account link, and **Close** button. A 72-by-72 circular crop of `Picture/14187194.png` appears on the left. Pillow is used to crop and render the image; a load failure is reported in an error dialog.

### 3. Startup database validation
- Before displaying the search interface, verify that the `SQLite` directory and `SearchDB.sqlite` file exist and that the database contains a `ScanFolders` table.
- Open the database read-only for validation and record counting; do not silently create a missing search database.
- If a check fails, display a modal warning dialog with an icon and explanatory text, keep it on-screen, and require the user to acknowledge it with **OK** before exiting.
- Once validation succeeds, count all rows in `ScanFolders` and display the count in the GUI.

### 4. Responsiveness and thread safety
- Run fuzzy matching in a background `threading.Thread` so the GUI remains responsive during a search.
- Disable search inputs and Search/Reset while the search is running.
- Schedule result updates on Tkinter's event loop with `root.after()`; update widgets only from the GUI thread.

### 5. Application boundaries
- `fuzzy_search_gui.py` owns the search query, matching, exclusions, and presentation logic.
- `file_scanner_gui.py` owns scan-root management, scanning, and index creation.
- The applications are decoupled at runtime and exchange data through `SQLite/SearchDB.sqlite`.
- The search tool performs fuzzy matching over path-derived text, not semantic or full-content search.

## Data flow
1. On startup, validate the database path and `ScanFolders` table, then count its rows.
2. The user enters a query and optional space-separated exclusion terms.
3. The worker loads non-null `corpus` values and their corresponding `CompleteFile` paths from SQLite.
4. RapidFuzz scores the corpus values against the query using `WRatio` and the 60% cutoff.
5. Matching paths containing any excluded term are removed, without reordering the remaining matches.
6. The GUI displays the remaining results in ranked pages of 20, allowing row selection and first/previous/next/last navigation.

## Consequences

### Positive
- The GUI remains responsive during fuzzy matching.
- All qualifying matches can be navigated rather than limiting the user to a single page.
- Exclusions allow users to narrow path results without altering fuzzy-score ranking.
- The database is only read by this GUI, and startup checks guide users to run the scanner when the index is unavailable.
- Scanner and search responsibilities remain separate while sharing one local database.
- The selection popup makes long paths available without widening the results table, and the About dialog is consistent with the scanner's.

### Negative / risks
- Loading the `corpus` values and paths into memory can become a bottleneck for very large indexes.
- Exclusions use substring checks against full paths, so a term can match a directory name or filename extension as well as a basename.
- SQLite remains subject to its normal locking behavior if a scan and search access the database concurrently.
- Fuzzy matching compares normalized path text, not file contents or semantic meaning.
- Pillow is an external runtime dependency used to render the circular About image.
