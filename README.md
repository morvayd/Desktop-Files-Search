
***

# 🔍 Python Local Search

**Python Local Search** is a lightweight, dual-interface desktop tool designed to transform your local files into a searchable database. Through a simple two-step process—**Scan, then Search**—you can perform high-speed, fuzzy-matched queries across your entire hard drive.

## 🚀 Overview

Standard OS search often struggles with typos or partial filenames. This tool solves that by building a local index of your file metadata using SQLite. Once indexed, you can perform "fuzzy" searches, allowing for typos (e.g., searching for "budjet" to find "budget") using advanced string-matching algorithms.

### Key Capabilities
*   **Intelligent Indexing:** Recursively scans folders and builds a comprehensive metadata database.
*   **Fuzzy Search:** Uses `rapidfuzz` (WRatio) to find files even when your search terms are imperfect.
4.  **Robust Data Management:** Uses a "staging" architecture to ensure your search index is never corrupted by an interrupted scan.
5.  **Dual-Interface:** Includes a user-friendly **Scanner GUI** for managing folders and a high-performance **Search GUI** for exploring results.

---

## 🛠 Getting Started

### Prerequisites
- **Python 3.x**
- **External Libraries**: 
  ```bash
  python -m pip install pandas rapidfuzz
  ```
  *(Note: On some Linux distributions, you may need to install `python3-tk` separately.)*

### Step 1: Indexing (The Scan)
Run the **Scanner GUI** to build your search database:
```bash
python file_scanner_gui.py
```
1.  **Configure:** Add the folders you want to search (e.g., your `Documents` or `Work` folders).
2.  **Save:** Click **Save Changes to DB** to persist your configuration.
3.  **Scan:** Click **Run Scan**. The app will recursively index your files.
    *   *Note: Scanning large drives (like `C:\` or `/`) can take time and significant disk space.*

### Step 2: Searching
Once the scan is complete, run the **Search GUI**:
```bash
python fuzzy_search_gui.py
```
1.  **Query:** Type your search term and press **Enter**.
2.  **Refine:** Use the **Exclude terms** box to omit specific file types (e.g., exclude `png` to hide all images).
3.  **Navigate:** Use the pagination controls to browse through matches.

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
└── SQLite/
    └── SearchDB.sqlite   # Local runtime database
```

## 📜 License
*Created by [Daniel Morvay](https://github.com/morvayd/)*. Use for research and personal productivity.
