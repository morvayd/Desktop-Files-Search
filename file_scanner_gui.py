from contextlib import redirect_stderr, redirect_stdout
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)


def get_db_path():
    """Return the SQLite database path, creating its parent directory if needed."""
    db_dir = Path(__file__).resolve().parent / "SQLite"
    db_dir.mkdir(exist_ok=True)
    return str(db_dir / "SearchDB.sqlite")


def connect_to_database(db_path):
    """Connect to SQLite using an in-memory journal for exFAT compatibility."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=MEMORY")
    return conn


def get_default_scan_folder():
    """Return the current user's Documents directory."""
    return str(Path.home() / "Documents")


def init_database(db_path):
    """Create application tables and add a default scan folder when needed."""
    logger.info("Connecting to database: %s", db_path)
    conn = connect_to_database(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS FoldersToScan (
                FoldersToScan TEXT,
                DateLastScan TEXT
            )
        """)
        cursor.execute("SELECT COUNT(*) FROM FoldersToScan")
        if cursor.fetchone()[0] == 0:
            default_path = get_default_scan_folder()
            logger.info("Inserting default path: %s", default_path)
            cursor.execute(
                "INSERT INTO FoldersToScan (FoldersToScan, DateLastScan) VALUES (?, ?)",
                (default_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ScanTime (
                ScanStart TEXT,
                ScanEnd TEXT,
                ScanDelta TEXT,
                ScanFolder TEXT
            )
        """)
        conn.commit()
        logger.info("Database initialization complete.")
    finally:
        conn.close()


def prepare_temporary_scan_tables(db_path):
    """Create empty staging tables for a scan run."""
    conn = connect_to_database(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS TemporaryScanFolders")
        cursor.execute("DROP TABLE IF EXISTS TemporaryEmptyFolders")
        cursor.execute("DROP TABLE IF EXISTS TemporaryUnableToScan")
        cursor.execute("""
            CREATE TABLE TemporaryScanFolders (
                FilePath TEXT,
                FileName TEXT,
                CompleteFile TEXT,
                corpus TEXT,
                IsDirectory INTEGER NOT NULL DEFAULT 0,
                Extension TEXT,
                Size INTEGER,
                LastModified TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE TemporaryEmptyFolders (
                FilePath TEXT,
                FileName TEXT,
                CompleteFile TEXT,
                corpus TEXT,
                IsDirectory INTEGER NOT NULL DEFAULT 1,
                Extension TEXT,
                Size INTEGER,
                LastModified TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE TemporaryUnableToScan (
                ScanRoot TEXT,
                DirectoryPath TEXT,
                Error TEXT,
                ScanTime TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def replace_scan_tables(db_path):
    """Atomically replace live scan tables with completed staging tables."""
    conn = connect_to_database(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP TABLE IF EXISTS ScanFolders")
        conn.execute("DROP TABLE IF EXISTS EmptyFolders")
        conn.execute("DROP TABLE IF EXISTS UnableToScan")
        conn.execute("DROP TABLE IF EXISTS Empty")
        conn.execute("ALTER TABLE TemporaryScanFolders RENAME TO ScanFolders")
        conn.execute("ALTER TABLE TemporaryEmptyFolders RENAME TO EmptyFolders")
        conn.execute("ALTER TABLE TemporaryUnableToScan RENAME TO UnableToScan")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_folders_to_scan(db_path):
    """Load configured scan roots from SQLite."""
    conn = connect_to_database(db_path)
    try:
        return pd.read_sql_query(
            "SELECT FoldersToScan FROM FoldersToScan",
            conn,
        )
    finally:
        conn.close()


def perform_scan(folder_path, inaccessible_directories=None):
    """Recursively scan a folder and return file and directory metadata."""
    scan_results = []
    folder_path = str(folder_path).strip()

    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Scan path does not exist: {folder_path}")

    if inaccessible_directories is None:
        inaccessible_directories = []

    def record_walk_error(error):
        error_path = error.filename or folder_path
        inaccessible_directories.append({
            "ScanRoot": folder_path,
            "DirectoryPath": os.fsdecode(error_path),
            "Error": str(error),
            "ScanTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    for root, directories, files in os.walk(folder_path, onerror=record_walk_error):
        is_empty_folder = not directories and not files
        if root != folder_path or is_empty_folder:
            try:
                stat = os.stat(root)
            except OSError as error:
                inaccessible_directories.append({
                    "ScanRoot": folder_path,
                    "DirectoryPath": root,
                    "Error": str(error),
                    "ScanTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                continue

            scan_results.append({
                "FilePath": os.path.dirname(root),
                "FileName": os.path.basename(root),
                "CompleteFile": root,
                "corpus": root.replace("/", " ").replace("-", " ").replace(".", " "),
                "IsDirectory": 1,
                "Extension": "",
                "Size": stat.st_size,
                "_empty_folder": is_empty_folder,
                "LastModified": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            })

        for file_name in files:
            complete_file = os.path.join(root, file_name)
            try:
                stat = os.stat(complete_file)
            except OSError:
                continue

            scan_results.append({
                "FilePath": root,
                "FileName": file_name,
                "CompleteFile": complete_file,
                "corpus": complete_file.replace("/", " ").replace("-", " ").replace(".", " ").replace("_", " "),
                "IsDirectory": 0,
                "Extension": os.path.splitext(file_name)[1].lower(),
                "Size": stat.st_size,
                "_empty_folder": False,
                "LastModified": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            })

    return scan_results


def save_unable_to_scan(db_path, inaccessible_directories):
    """Append inaccessible directory details to the staging table."""
    if not inaccessible_directories:
        return

    conn = connect_to_database(db_path)
    try:
        pd.DataFrame(inaccessible_directories).to_sql(
            "TemporaryUnableToScan",
            conn,
            if_exists="append",
            index=False,
        )
    finally:
        conn.close()


def save_scan_results(db_path, results):
    """Append scan results to their appropriate staging tables."""
    if not results:
        return

    empty_folders = [
        {key: value for key, value in row.items() if key != "_empty_folder"}
        for row in results
        if row.get("_empty_folder", False)
    ]
    scan_folders = [
        {key: value for key, value in row.items() if key != "_empty_folder"}
        for row in results
        if not row.get("_empty_folder", False)
    ]
    conn = connect_to_database(db_path)
    try:
        if scan_folders:
            pd.DataFrame(scan_folders).to_sql(
                "TemporaryScanFolders",
                conn,
                if_exists="append",
                index=False,
            )
        if empty_folders:
            pd.DataFrame(empty_folders).to_sql(
                "TemporaryEmptyFolders",
                conn,
                if_exists="append",
                index=False,
            )
    finally:
        conn.close()

    logger.info(
        "Staged %s records and %s empty folders.",
        len(scan_folders),
        len(empty_folders),
    )


def save_scan_time(db_path, folder, start_time, end_time, delta):
    """Store timing information for a completed root scan."""
    conn = connect_to_database(db_path)
    try:
        conn.execute("""
            INSERT INTO ScanTime (ScanStart, ScanEnd, ScanDelta, ScanFolder)
            VALUES (?, ?, ?, ?)
        """, (
            start_time.strftime("%Y-%m-%d %H:%M:%S"),
            end_time.strftime("%Y-%m-%d %H:%M:%S"),
            str(delta),
            folder,
        ))
        conn.commit()
    finally:
        conn.close()
    logger.info("Saved scan time for: %s", folder)


def run_scan_sequence(db_path):
    """Scan every configured root and replace live tables on success."""
    try:
        prepare_temporary_scan_tables(db_path)
        folders_to_process = load_folders_to_scan(db_path)["FoldersToScan"].tolist()

        for folder in folders_to_process:
            scan_start = datetime.now()
            logger.info(
                "Scanning folder: %s | Start time: %s",
                folder,
                scan_start.strftime("%Y-%m-%d %H:%M:%S"),
            )
            inaccessible_directories = []
            results = perform_scan(folder, inaccessible_directories)
            scan_end = datetime.now()
            save_scan_results(db_path, results)
            save_unable_to_scan(db_path, inaccessible_directories)
            save_scan_time(db_path, folder, scan_start, scan_end, scan_end - scan_start)

        replace_scan_tables(db_path)
        logger.info("Successfully replaced scan tables with completed scan results.")
    except Exception:
        logger.exception("An error occurred during the scan.")
        raise

# Custom logging handler to send log messages to a queue
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put(msg)


class QueueStream:
    def __init__(self, log_queue):
        self.log_queue = log_queue
        self.buffer = ""

    def write(self, text):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.log_queue.put(line.rstrip("\r"))
        return len(text)

    def flush(self):
        if self.buffer:
            self.log_queue.put(self.buffer)
            self.buffer = ""


class FileScannerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Python File Scanner GUI")
        self.root.geometry("800x650")

        self.db_path = get_db_path()
        self.log_queue = queue.Queue()

        # Route application logging to the GUI instead of the terminal.
        self.root_logger = logging.getLogger()
        self.previous_root_handlers = self.root_logger.handlers[:]
        self.previous_root_level = self.root_logger.level
        for handler in self.previous_root_handlers:
            self.root_logger.removeHandler(handler)
        self.queue_handler = QueueHandler(self.log_queue)
        self.queue_handler.setFormatter(logging.Formatter("%(message)s"))
        self.root_logger.addHandler(self.queue_handler)
        self.root_logger.setLevel(logging.INFO)

        self.logger = logging.getLogger("GUI")

        self._setup_ui()
        init_database(self.db_path)
        self._load_data()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start queue monitoring thread
        self.root.after(100, self._process_logs)

    def _setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Tree Section (List of Paths) ---
        tree_frame = ttk.LabelFrame(main_frame, text="Configured Folders (FoldersToScan)", padding="5")
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.tree = ttk.Treeview(tree_frame, columns=("path", "last_scan"), show="headings")
        self.tree.heading("path", text="Folder Path")
        self.tree.heading("last_scan", text="Last Scan Date")
        self.tree.column("path", width=450)
        self.tree.column("last_scan", width=150)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscroll=scrollbar.set)

        # --- Input Section ---
        input_frame = ttk.LabelFrame(main_frame, text="Path Input & Actions", padding="5")
        input_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Path selection and basic entry
        path_row = ttk.Frame(input_frame)
        path_row.pack(fill=tk.X, pady=2)
        
        ttk.Label(path_row, text="Path:").pack(side=tk.LEFT)
        self.path_entry = ttk.Entry(path_row)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.browse_btn = ttk.Button(path_row, text="Browse", command=self._browse_folder)
        self.browse_btn.pack(side=tk.LEFT, padx=2)

        # Row 2: Management buttons
        mgmt_row = ttk.Frame(input_frame)
        mgmt_row.pack(fill=tk.X, pady=5)

        self.add_btn = ttk.Button(mgmt_row, text="Add Entry", command=self._add_folder)
        self.add_btn.pack(side=tk.LEFT, padx=2)

        self.edit_btn = ttk.Button(mgmt_row, text="Edit Selection", command=self._edit_selection)
        self.edit_btn.pack(side=tk.LEFT, padx=2)

        self.apply_btn = ttk.Button(mgmt_row, text="Apply Change", command=self._apply_edit)
        self.apply_btn.pack(side=tk.LEFT, padx=2)

        self.del_btn = ttk.Button(mgmt_row, text="Remove from List", command=self._delete_folder)
        self.del_btn.pack(side=tk.LEFT, padx=2)

        self.save_btn = ttk.Button(mgmt_row, text="💾 Save Changes to DB", command=self._save_to_db)
        self.save_btn.pack(side=tk.RIGHT, padx=2)

        # --- Scan Section ---
        scan_frame = ttk.LabelFrame(main_frame, text="Scan Control", padding="5")
        scan_frame.pack(fill=tk.X, pady=(0, 5))

        self.run_btn = ttk.Button(scan_frame, text="🚀 Run Scan", command=self._start_scan)
        self.run_btn.pack(pady=5)

        # --- Log Section ---
        log_frame = ttk.LabelFrame(main_frame, text="Console Output", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_frame,
            height=10,
            state='disabled',
            background="#f0f0f0",
            foreground="black",
            font=("Consolas", 9),
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscroll=log_scroll.set)

        footer = ttk.Frame(main_frame)
        footer.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(footer, text="About", command=self._show_about).pack(
            side=tk.RIGHT
        )

    def _show_about(self):
        messagebox.showinfo(
            "About",
            "Created By:  Daniel Morvay,\nGitHub Account:  https://github.com/morvayd/",
            parent=self.root,
        )

    def _browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, folder)

    def _load_data(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        try:
            conn = sqlite3.connect(self.db_path)
            df = pd.read_sql_query("SELECT FoldersToScan, DateLastScan FROM FoldersToScan", conn)
            conn.close()
            for _, row in df.iterrows():
                self.tree.insert("", tk.END, values=(row['FoldersToScan'], row['DateLastScan']))
        except Exception as e:
            self.logger.error(f"Error loading data: {e}")

    def _add_folder(self):
        path = self.path_entry.get().strip()
        if not path:
            messagebox.showwarning("Warning", "Please enter a path.")
            return
        
        if not os.path.exists(path):
            messagebox.showerror("Error", "Path does not exist.")
            return

        self.tree.insert("", tk.END, values=(path, "N/A"))
        self.path_entry.delete(0, tk.END)

    def _edit_selection(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Warning", "Please select an entry from the list to edit.")
            return
        
        current_path = self.tree.item(selected_item[0])['values'][0]
        self.path_entry.delete(0, tk.END)
        self.path_entry.insert(0, current_path)

    def _apply_edit(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Warning", "Please select an entry from the list to apply changes to.")
            return
        
        new_path = self.path_entry.get().strip()
        if not new_path:
            messagebox.showerror("Error", "Path cannot be empty.")
            return

        self.tree.set(selected_item[0], column='path', value=new_path)
        self.logger.info(f"Updated entry to: {new_path}")

    def _delete_folder(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Warning", "Please select an item from the list to remove.")
            return
        self.tree.delete(selected_item[0])
        self.logger.info("Removed item from visual list (not yet saved to DB).")

    def _save_to_db(self):
        new_data = []
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            new_data.append((values[0], values[1]))

        if not new_data:
            if messagebox.askyesno("Warning", "The list is empty. Do you really want to clear all scan folders?"):
                self._perform_actual_save(True)
            return

        self._perform_actual_save(False)

    def _perform_actual_save(self, clear_all):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if clear_all:
                cursor.execute("DELETE FROM FoldersToScan")
            else:
                new_data = []
                for item in self.tree.get_children():
                    values = self.tree.item(item)['values']
                    new_data.append((values[0], values[1]))
                
                cursor.execute("DELETE FROM FoldersToScan")
                cursor.executemany("INSERT INTO FoldersToScan (FoldersToScan, DateLastScan) VALUES (?, ?)", new_data)
            
            conn.commit()
            conn.close()
            self.logger.info("Successfully saved changes to database.")
            messagebox.showinfo("Success", "Changes saved to database.")
        except Exception as e:
            self.logger.error(f"Error saving to database: {e}")
            messagebox.showerror("Error", f"Could not save to database: {e}")

    def _start_scan(self):
        self.run_btn.config(state=tk.DISABLED)
        self.browse_btn.config(state=tk.DISABLED)
        self.add_btn.config(state=tk.DISABLED)
        self.edit_btn.config(state=tk.DISABLED)
        self.apply_btn.config(state=tk.DISABLED)
        self.del_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)

        scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
        scan_thread.start()

    def _scan_worker(self):
        stdout_stream = QueueStream(self.log_queue)
        stderr_stream = QueueStream(self.log_queue)
        scan_succeeded = False
        try:
            with redirect_stdout(stdout_stream), redirect_stderr(stderr_stream):
                run_scan_sequence(self.db_path)
            scan_succeeded = True
        except Exception as e:
            self.logger.error(f"Scan thread error: {e}")
        finally:
            stdout_stream.flush()
            stderr_stream.flush()
            self.root.after(0, lambda: self._on_scan_complete(scan_succeeded))

    def _on_close(self):
        self.root_logger.removeHandler(self.queue_handler)
        for handler in self.previous_root_handlers:
            self.root_logger.addHandler(handler)
        self.root_logger.setLevel(self.previous_root_level)
        self.root.destroy()

    def _on_scan_complete(self, scan_succeeded):
        self.run_btn.config(state=tk.NORMAL)
        self.browse_btn.config(state=tk.NORMAL)
        self.add_btn.config(state=tk.NORMAL)
        self.edit_btn.config(state=tk.NORMAL)
        self.apply_btn.config(state=tk.NORMAL)
        self.del_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.NORMAL)
        self._load_data()
        if scan_succeeded:
            messagebox.showinfo("Scan Finished", "The scan process has completed.")
        else:
            messagebox.showerror(
                "Scan Failed",
                "The scan process failed. See Console Output for details.",
            )

    def _process_logs(self):
        while True:
            try:
                msg = self.log_queue.get_nowait()
                self._append_to_log(msg)
            except queue.Empty:
                break
        self.root.after(100, self._process_logs)

    def _append_to_log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

if __name__ == "__main__":
    root = tk.Tk()
    app = FileScannerGUI(root)
    root.mainloop()
