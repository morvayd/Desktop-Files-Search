
***

# 🔍 Python Local Search

**Python Local Search** is a lightweight, dual-interface desktop tool designed to transform your local files into a searchable database. Through a simple two-step process—**Scan, then Search**—you can perform high-speed, fuzzy-matched queries across your entire hard drive.

**Supported platforms:** Windows, macOS, and Linux. The interface sizing, path handling, and folder-opening behavior adapt to the operating system.

## 🚀 Overview

Standard OS search often struggles with typos or partial filenames. This tool solves that by building a local index of your file metadata using SQLite. Once indexed, you can perform "fuzzy" searches, allowing for typos (e.g., searching for "budjet" to find "budget") using advanced string-matching algorithms.

### Key Capabilities
*   **Intelligent Indexing:** Recursively scans folders and builds a comprehensive metadata database.
*   **Fuzzy Search:** Uses `rapidfuzz` (WRatio) to find files even when your search terms are imperfect.
*   **Robust Data Management:** Uses a "staging" architecture to ensure your search index is not replaced by an incomplete scan.
*   **Dual-Interface:** Includes a user-friendly **Scanner GUI** for managing folders and a high-performance **Search GUI** for exploring results.
*   **Path Filtering and Navigation:** Exclude terms from search results, page through matches, and open the selected directory or a file's containing folder using the host operating system's native folder opener.
*   **Cross-Platform Paths:** Scanner paths follow the running OS conventions, and indexed search text normalizes native and alternate path separators for Windows, macOS, and Linux.
*   **Image-Based About Dialogs:** Both applications display the author and a clickable GitHub link alongside a circular profile image.

---

## 🛠 Getting Started

### Prerequisites
- **Python 3.x**
- **External Libraries**:
  ```bash
  python -m pip install -r requirements.txt
  ```
  On Debian or Ubuntu, install Tkinter and Pillow's Tk support if they are missing:
  ```bash
  sudo apt update
  sudo apt install python3-tk python3-pil.imagetk
  ```

### Step 1: Indexing (The Scan)
Run the **Scanner GUI** to build your search database:
```bash
python file_scanner_gui.py
```
1.  **Configure:** Add the folders you want to search (e.g., your `Documents` or `Work` folders). If no folders are configured on first launch, the scanner defaults to the current user's `Documents` directory (`~/Documents`). The Browse button uses your OS folder picker; on Windows, selected paths are normalized to Windows format (for example, `C:\` for a drive root).
2.  **Save:** Click **Save Changes to DB** to persist your configuration.
3.  **Scan:** Click **Run Scan**. The app will recursively index your files.
    *   *Note: Scanning large drives (like `C:\` or `/`) can take time and significant disk space.*
4.  **Quit or About:** Use **Quit** to close the scanner, or **About** to view the author and GitHub link.
5.  **Monitor:** Scan messages and errors appear in the **Console Output** area.

### Step 2: Searching
Once the scan is complete, run the **Search GUI**:
```bash
python fuzzy_search_gui.py
```
1.  **Query:** Type your search term and press **Enter**.
2.  **Refine:** Use the **Exclude terms** box to omit specific file types (e.g., exclude `png` to hide all images).
3.  **Navigate:** Use the pagination controls to browse through matches.
4.  **Open Folder:** Select a result and click **Open Folder** to open its containing folder (or the selected path itself when it is a directory). The app uses Windows' native folder opener, `open` on macOS, and `xdg-open` on Linux. Missing paths or launch failures are reported in an error dialog.
5.  **View Full Path:** Select a result to show its full path in a popup next to the row.
6.  **Quit or About:** Use **Quit** to close the search app, or **About** to view the author and GitHub link.

The Search GUI opens at 700-by-730 pixels on Windows and macOS, and 700-by-800 pixels on Linux.

### About Dialog
Both GUIs use the same custom About dialog: a dark 360-by-150-pixel window with the author line, clickable soft-blue **GitHub Account** link, and **Close** button. A 72-by-72 circular crop of `Picture/14187194.png` appears at the left. The image is loaded relative to the application script; if it is missing or unreadable, the app reports the failure in an error dialog. The crop and display are provided by Pillow.

---

## 📊 Technical Details

### Database Architecture
The application maintains a local SQLite database at `SQLite/SearchDB.sqlite`. 

| Table | Description |
| :--- | :--- |
| `FoldersToScan` | Your configured paths and last scan timestamp. |
| `ScanFolders` | The main index of files and non-empty directories. |
| `EmptyFolders` | Directories containing no files. |
| `UnableToScan` | Log of directories that were inaccessible during the last scan. |
| `ScanTime` | Metadata tracking the duration and timing of scan runs. |

**Data Integrity:** To prevent data loss during interruptions, the scanner uses a "staging" method. It writes results to temporary tables and only replaces the live index if the entire scan completes successfully.

**Note on Compatibility:** SQLite connections use `journal_mode=MEMORY` for high performance on exFAT filesystems (common on external drives), though this offers slightly weaker crash recovery than durable disk-based journaling.

### Fuzzy Matching Logic
The search engine uses the **WRatio** scorer from `rapidfuzz`. This allows for a degree of error in the query. By default, the threshold is set to **60%**, meaning a result must be at least 60% similar to your query to be displayed.

---

## 📂 Project Structure
```text
.
├── README.md
├── adr/
│   ├── 0001-file-scanner-architecture.md
│   └── 0002-fuzzy-search-architecture.md
├── file_scanner_gui.py   # Main Scanner interface & engine
├── fuzzy_search_gui.py   # Main Search interface
├── Picture/
│   └── 14187194.png      # Source photo cropped for both About dialogs
└── SQLite/
    └── SearchDB.sqlite   # Local runtime database
```

## 📜 License
*Created by [Daniel Morvay](https://github.com/morvayd/)*. Use for research and personal productivity.
