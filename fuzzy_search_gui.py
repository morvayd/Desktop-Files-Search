import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sqlite3
import os
from pathlib import Path
from rapidfuzz import fuzz, process

def get_db_path():
    """
    Determines the path for the SQLite database.
    Matches the directory structure used by the File Scanner.
    """
    current_dir = Path(__file__).resolve().parent
    db_path = current_dir / "SQLite" / "SearchDB.sqlite"
    return str(db_path)


def get_database_setup_error(db_path):
    """Return a startup error when the scanner database is not ready."""
    db_file = Path(db_path)
    if not db_file.parent.is_dir():
        return f"Database folder not found: {db_file.parent}"
    if not db_file.is_file():
        return f"Database file not found: {db_file}"

    try:
        connection = sqlite3.connect(
            f"{db_file.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("ScanFolders",),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as error:
        return f"Could not verify the database: {error}"

    if table is None:
        return "The ScanFolders table was not found in the database."
    return None


def get_scan_folder_count(db_path):
    """Return the total number of records in the validated scan table."""
    db_file = Path(db_path)
    connection = sqlite3.connect(
        f"{db_file.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    try:
        return connection.execute("SELECT COUNT(*) FROM ScanFolders").fetchone()[0]
    finally:
        connection.close()


def show_database_setup_error(root, detail):
    """Show a modal error dialog that closes only through its button."""
    dialog = root
    dialog.title("Required Database Not Found")
    dialog.resizable(False, False)
    dialog.protocol("WM_DELETE_WINDOW", lambda: None)
    if detail.startswith("Database folder not found:"):
        detail = detail.replace(":", ":\n", 1)
        extra_height = 30
    else:
        extra_height = 0

    message_frame = ttk.Frame(dialog, padding=15)
    message_frame.pack(fill=tk.X)
    tk.Label(message_frame, bitmap="warning").pack(
        side=tk.LEFT, padx=(0, 12), anchor=tk.N
    )
    ttk.Label(
        message_frame,
        text=(
            "The required hard drive scan has not yet completed.  "
            "Please run file_scanner_gui.py first."
        ),
        justify=tk.LEFT,
        wraplength=450,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(dialog, text=detail, padding=(15, 0), justify=tk.LEFT).pack(
        fill=tk.X
    )
    ttk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=(0, 12))

    dialog.update_idletasks()
    screen_width = dialog.winfo_screenwidth()
    screen_height = dialog.winfo_screenheight()
    dialog_width = dialog.winfo_width()
    dialog_height = dialog.winfo_height() + extra_height
    x = max(0, (screen_width - dialog_width) // 2)
    y = max(0, (screen_height - dialog_height) // 2)
    dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

    dialog.deiconify()
    dialog.lift()
    dialog.grab_set()
    dialog.wait_window()


def perform_fuzzy_search(
    query, db_path, score_cutoff=60, limit=None, exclude_query=""
):
    """
    Executes the fuzzy search logic against the SQLite database.
    Returns matching scores and file paths, plus a status message.
    """
    if not os.path.exists(db_path):
        return [], f"Error: Database not found at {db_path}"

    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT CompleteFile, corpus FROM ScanFolders WHERE corpus IS NOT NULL"
        ).fetchall()
        conn.close()

        if not rows:
            return [], "The database contains no indexed file data to search."

        choices = [row[1] for row in rows]
        file_map = [row[0] for row in rows]

        matches = process.extract(
            query,
            choices,
            scorer=fuzz.WRatio,
            score_cutoff=score_cutoff,
            limit=limit,
        )

        if not matches:
            return [], f"No matches found for '{query}' (Threshold: {score_cutoff}%)"

        excluded_terms = [term.casefold() for term in exclude_query.split()]
        results = [
            (f"{score:.0f}%", file_map[row_index])
            for matched_corpus, score, row_index in matches
            if not any(
                term in str(file_map[row_index]).casefold()
                for term in excluded_terms
            )
        ]
        if not results:
            return [], f"No matches found for '{query}' after exclusions."
        return results, f"Results for '{query}':"

    except sqlite3.Error as e:
        return [], f"Database error: {e}"
    except Exception as e:
        return [], f"An unexpected error occurred: {e}"

class FuzzySearchGUI:
    def __init__(self, root, record_count):
        self.root = root
        self.title_str = "Fuzzy Search Research Tool GUI"
        self.root.title(self.title_str)
        self.root.geometry("700x720")

        self.db_path = get_db_path()
        self.record_count = record_count
        self.page_size = 20
        self.current_page = 0
        self.search_results = []

        self._setup_ui()
        self._setup_events()

    def _setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Input Section ---
        input_frame = ttk.LabelFrame(main_frame, text="Search Controls", padding="10")
        input_frame.pack(fill=tk.X, pady=(0, 10))

        # Query entry
        query_row = ttk.Frame(input_frame)
        query_row.pack(fill=tk.X, pady=5)

        ttk.Label(query_row, text="Search Query:").pack(side=tk.LEFT, padx=(0, 5))
        self.query_entry = ttk.Entry(query_row)
        self.query_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.query_entry.bind("<Return>", lambda e: self._start_search())

        exclude_row = ttk.Frame(input_frame)
        exclude_row.pack(fill=tk.X, pady=5)
        ttk.Label(exclude_row, text="Exclude terms:").pack(
            side=tk.LEFT, padx=(0, 5)
        )
        self.exclude_entry = ttk.Entry(exclude_row)
        self.exclude_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.exclude_entry.bind("<Return>", lambda e: self._start_search())

        self.search_btn = ttk.Button(query_row, text="🔍 Search", command=self._start_search)
        self.search_btn.pack(side=tk.LEFT, padx=5)

        record_info_row = ttk.Frame(input_frame)
        record_info_row.pack(fill=tk.X, pady=(4, 0))
        self.reset_btn = ttk.Button(
            record_info_row, text="Reset", command=self._reset_search
        )
        self.reset_btn.pack(side=tk.LEFT)
        ttk.Label(
            record_info_row,
            text=f"Indexed records in ScanFolders: {self.record_count:,}",
        ).pack(side=tk.RIGHT)

        # --- Search Results Section ---
        result_frame = ttk.LabelFrame(main_frame, text="Search Results", padding="5")
        result_frame.pack(fill=tk.BOTH, expand=True)

        self.result_status = tk.StringVar()
        ttk.Label(result_frame, textvariable=self.result_status).pack(
            anchor=tk.W, fill=tk.X, pady=(0, 5)
        )

        results_frame = ttk.Frame(result_frame)
        results_frame.pack(fill=tk.BOTH, expand=True)

        self.results_tree = ttk.Treeview(
            results_frame,
            columns=("score", "path"),
            show="headings",
            selectmode="extended",
            height=self.page_size,
        )
        self.results_tree.heading("score", text="Match")
        self.results_tree.heading("path", text="Path")
        self.results_tree.column("score", width=80, stretch=False)
        self.results_tree.column("path", width=550)
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vertical_scrollbar = ttk.Scrollbar(
            results_frame, orient=tk.VERTICAL, command=self.results_tree.yview
        )
        vertical_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal_scrollbar = ttk.Scrollbar(
            result_frame, orient=tk.HORIZONTAL, command=self.results_tree.xview
        )
        horizontal_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.results_tree.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )

        footer = ttk.Frame(main_frame)
        footer.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(footer, text="About", command=self._show_about).pack(
            side=tk.RIGHT
        )

        pagination_frame = ttk.Frame(result_frame)
        pagination_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        self.first_btn = ttk.Button(
            pagination_frame,
            text="First",
            command=self._show_first_page,
            state=tk.DISABLED,
        )
        self.first_btn.pack(side=tk.LEFT)
        self.previous_btn = ttk.Button(
            pagination_frame,
            text="Previous",
            command=self._show_previous_page,
            state=tk.DISABLED,
        )
        self.previous_btn.pack(side=tk.LEFT)
        self.page_label = tk.StringVar(value="No results")
        ttk.Label(pagination_frame, textvariable=self.page_label).pack(
            side=tk.LEFT, expand=True
        )
        self.last_btn = ttk.Button(
            pagination_frame,
            text="Last",
            command=self._show_last_page,
            state=tk.DISABLED,
        )
        self.last_btn.pack(side=tk.RIGHT, padx=(0, 5))
        self.next_btn = ttk.Button(
            pagination_frame,
            text="Next",
            command=self._show_next_page,
            state=tk.DISABLED,
        )
        self.next_btn.pack(side=tk.RIGHT)

    def _setup_events(self):
        pass

    def _show_about(self):
        messagebox.showinfo(
            "About",
            "Created By:  Daniel Morvay,\nGitHub Account:  https://github.com/morvayd/",
            parent=self.root,
        )

    def _reset_search(self):
        self.query_entry.delete(0, tk.END)
        self.exclude_entry.delete(0, tk.END)
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.search_results = []
        self.current_page = 0
        self.result_status.set("")
        self._update_pagination_controls()

    def _start_search(self):
        query = self.query_entry.get().strip()
        exclude_query = self.exclude_entry.get().strip()
        if not query:
            messagebox.showwarning("Warning", "Please enter a search query.")
            return

        # Disable button while searching
        self.search_btn.config(state=tk.DISABLED)
        self.reset_btn.config(state=tk.DISABLED)
        self.query_entry.config(state=tk.DISABLED)
        self.exclude_entry.config(state=tk.DISABLED)
        
        # Clear previous results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.search_results = []
        self.current_page = 0
        self._update_pagination_controls()
        self.result_status.set("Searching ...")

        # Start search in a background thread
        search_thread = threading.Thread(
            target=self._search_worker,
            args=(query, exclude_query),
            daemon=True,
        )
        search_thread.start()

    def _search_worker(self, query, exclude_query):
        # Perform the heavy lifting in the background
        result = perform_fuzzy_search(
            query, self.db_path, exclude_query=exclude_query
        )
        
        # Update the UI from the main thread
        self.root.after(0, self._on_search_complete, result)

    def _on_search_complete(self, result):
        self.search_btn.config(state=tk.NORMAL)
        self.reset_btn.config(state=tk.NORMAL)
        self.query_entry.config(state=tk.NORMAL)
        self.exclude_entry.config(state=tk.NORMAL)

        matches, status = result
        self.search_results = matches
        self.current_page = 0
        if matches:
            self.result_status.set("")
        elif status.startswith("No matches found for "):
            self.result_status.set("No Search Matches Found ...")
        else:
            self.result_status.set(status)
        self._render_results_page()

    def _render_results_page(self):
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        start = self.current_page * self.page_size
        end = min(start + self.page_size, len(self.search_results))
        for score, path in self.search_results[start:end]:
            self.results_tree.insert("", tk.END, values=(score, path))
        self._update_pagination_controls()

    def _update_pagination_controls(self):
        total = len(self.search_results)
        if total:
            start = self.current_page * self.page_size + 1
            end = min((self.current_page + 1) * self.page_size, total)
            self.page_label.set(f"Showing {start}-{end} of {total}")
        else:
            self.page_label.set("No results")

        self.previous_btn.config(
            state=tk.NORMAL if self.current_page > 0 else tk.DISABLED
        )
        self.first_btn.config(
            state=tk.NORMAL if self.current_page > 0 else tk.DISABLED
        )
        has_next_page = (self.current_page + 1) * self.page_size < total
        self.next_btn.config(state=tk.NORMAL if has_next_page else tk.DISABLED)
        self.last_btn.config(state=tk.NORMAL if has_next_page else tk.DISABLED)

    def _show_first_page(self):
        if self.current_page > 0:
            self.current_page = 0
            self._render_results_page()

    def _show_previous_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render_results_page()

    def _show_next_page(self):
        if (self.current_page + 1) * self.page_size < len(self.search_results):
            self.current_page += 1
            self._render_results_page()

    def _show_last_page(self):
        last_page = (len(self.search_results) - 1) // self.page_size
        if self.current_page < last_page:
            self.current_page = last_page
            self._render_results_page()

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    database_error = get_database_setup_error(get_db_path())
    if database_error:
        show_database_setup_error(root, database_error)
    else:
        try:
            record_count = get_scan_folder_count(get_db_path())
        except sqlite3.Error as error:
            show_database_setup_error(
                root,
                f"Could not count records in ScanFolders: {error}",
            )
        else:
            root.deiconify()
            app = FuzzySearchGUI(root, record_count)
            root.mainloop()
