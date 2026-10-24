# Created by Daniel Morvay
# GitHub URL: https://github.com/morvayd/
# This application provides a graphical user interface for performing fuzzy searches on files stored in a SQLite database.

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sqlite3
import os
import subprocess
import sys
from pathlib import Path
import webbrowser
from PIL import Image, ImageDraw, ImageOps, ImageTk

try:
    from rapidfuzz import fuzz, process
except ImportError as exc:
    raise RuntimeError(
        "Missing dependency: rapidfuzz. Install it with 'python -m pip install rapidfuzz'."
    ) from exc

def validate_database(db_path):
    """Return a startup error and record count for the scanner database."""
    db_file = Path(db_path)
    if not db_file.parent.is_dir():
        return f"Database folder not found: {db_file.parent}", None
    if not db_file.is_file():
        return f"Database file not found: {db_file}", None

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
            if table is None:
                return "The ScanFolders table was not found in the database.", None
            try:
                record_count = connection.execute(
                    "SELECT COUNT(*) FROM ScanFolders"
                ).fetchone()[0]
            except sqlite3.Error as error:
                return f"Could not count records in ScanFolders: {error}", None
        finally:
            connection.close()
    except sqlite3.Error as error:
        return f"Could not verify the database: {error}", None
    return None, record_count


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

        matches = process.extract(
            query,
            (row[1] for row in rows),
            scorer=fuzz.WRatio,
            score_cutoff=score_cutoff,
            limit=limit,
        )

        if not matches:
            return [], f"No matches found for '{query}' (Threshold: {score_cutoff}%)"

        excluded_terms = [term.casefold() for term in exclude_query.split()]
        results = [
            (f"{score:.0f}%", rows[row_index][0])
            for _, score, row_index in matches
            if not any(
                term in str(rows[row_index][0]).casefold()
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
    def __init__(self, root, db_path, record_count):
        self.root = root
        self.title_str = "Fuzzy Search Research Tool GUI"
        self.root.title(self.title_str)
        #  .geometry("<width>x<height>")
        self.root.geometry("700x730")

        self.db_path = db_path
        self.record_count = record_count
        self.page_size = 20
        self.current_page = 0
        self.search_results = []
        self.path_tooltip: tk.Toplevel | None = None
        self.path_tooltip_label: tk.Label | None = None
        self.hovered_result = None
        self.path_tooltip_size: tuple[int, int] | None = None
        self.about_images: dict[tk.Toplevel, ImageTk.PhotoImage] = {}

        self._setup_ui()

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
        results_toolbar = ttk.Frame(result_frame)
        results_toolbar.pack(fill=tk.X, pady=(0, 5))
        self.open_folder_btn = ttk.Button(
            results_toolbar,
            text="Open Folder",
            command=self._open_selected_folder,
            state=tk.DISABLED,
        )
        self.open_folder_btn.pack(side=tk.LEFT)
        ttk.Label(results_toolbar, textvariable=self.result_status).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0)
        )

        results_frame = ttk.Frame(result_frame)
        results_frame.pack(fill=tk.BOTH, expand=True)

        self.results_tree = ttk.Treeview(
            results_frame,
            columns=("score", "path"),
            show="headings",
            selectmode="browse",
            height=self.page_size,
        )
        self.results_tree.bind(
            "<<TreeviewSelect>>", self._on_result_selection_changed
        )
        self.results_tree.bind("<MouseWheel>", self._on_results_mousewheel)
        self.results_tree.bind("<Button-4>", self._on_results_mousewheel)
        self.results_tree.bind("<Button-5>", self._on_results_mousewheel)
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
        ttk.Button(footer, text="Quit", command=self.root.destroy).pack(
            side=tk.LEFT
        )
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

    def _on_results_mousewheel(self, event):
        if getattr(event, "num", None) == 4:
            self._show_previous_page()
        elif getattr(event, "num", None) == 5:
            self._show_next_page()
        elif getattr(event, "delta", 0) > 0:
            self._show_previous_page()
        elif getattr(event, "delta", 0) < 0:
            self._show_next_page()
        return "break"

    def _hide_path_tooltip(self, _event=None):
        tooltip = self.path_tooltip
        self.hovered_result = None
        if tooltip is not None:
            tooltip.withdraw()

    def _on_result_selection_changed(self, event):
        selected = event.widget.selection()
        self.open_folder_btn.config(state=tk.NORMAL if selected else tk.DISABLED)
        if not selected:
            self._hide_path_tooltip()
            return

        item = selected[0]
        values = event.widget.item(item, "values")
        if len(values) < 2 or not str(values[1]).strip():
            self._hide_path_tooltip()
            return

        path = str(values[1])
        if self.path_tooltip is None or self.path_tooltip_label is None:
            tooltip = tk.Toplevel(self.root)
            tooltip.overrideredirect(True)
            tooltip.configure(background="#4A90D9")
            tooltip_label = tk.Label(
                tooltip,
                text=path,
                padx=6,
                pady=6,
                relief=tk.SOLID,
                borderwidth=1,
                background="#4A90D9",
                foreground="#FFFFFF",
                wraplength=max(
                    200,
                    min(450, self.root.winfo_screenwidth() - 40),
                ),
            )
            tooltip_label.pack()
            self.path_tooltip = tooltip
            self.path_tooltip_label = tooltip_label

        tooltip = self.path_tooltip
        tooltip_label = self.path_tooltip_label
        tooltip_label.config(text=path)
        self.hovered_result = (item, path)
        tooltip.update_idletasks()
        self.path_tooltip_size = (
            tooltip.winfo_reqwidth(),
            tooltip.winfo_reqheight(),
        )

        row_bounds = event.widget.bbox(item)
        if not row_bounds:
            self._hide_path_tooltip()
            return

        _, row_y, _, _ = row_bounds
        tooltip_width, tooltip_height = self.path_tooltip_size
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = event.widget.winfo_rootx() + 66
        y = event.widget.winfo_rooty() + row_y
        if x + tooltip_width > screen_width:
            x = event.widget.winfo_rootx() - tooltip_width - 12
        if y + tooltip_height > screen_height:
            y = screen_height - tooltip_height
        tooltip.geometry(f"+{max(0, x)}+{max(0, y)}")
        tooltip.deiconify()
        tooltip.lift()

    def _open_selected_folder(self):
        selected = self.results_tree.selection()
        if not selected:
            messagebox.showwarning(
                "No Result Selected",
                "Select a search result before opening its folder.",
                parent=self.root,
            )
            return

        values = self.results_tree.item(selected[0], "values")
        if len(values) < 2 or not values[1]:
            messagebox.showerror(
                "Invalid File Path",
                "The selected result does not contain a File Path.",
                parent=self.root,
            )
            return

        result_path = Path(values[1]).expanduser()
        if not result_path.exists():
            messagebox.showerror(
                "Path Not Found",
                f"The indexed path no longer exists:\n{result_path}",
                parent=self.root,
            )
            return

        folder_path = result_path if result_path.is_dir() else result_path.parent
        if sys.platform == "darwin":
            command = ["open", str(folder_path)]
        elif os.name == "nt":
            command = ["explorer", str(folder_path)]
        else:
            command = ["xdg-open", str(folder_path)]

        try:
            subprocess.Popen(command)
        except OSError as error:
            messagebox.showerror(
                "Could Not Open Folder",
                f"Could not open {folder_path}:\n{error}",
                parent=self.root,
            )

    def _show_about(self):
        image_path = Path(__file__).resolve().parent / "Picture" / "14187194.png"
        try:
            with Image.open(image_path) as source:
                about_image = ImageOps.fit(
                    source.convert("RGBA"),
                    (288, 288),
                    method=Image.Resampling.LANCZOS,
                )
            circular_mask = Image.new("L", (288, 288), 0)
            ImageDraw.Draw(circular_mask).ellipse((0, 0, 287, 287), fill=255)
            about_image.putalpha(circular_mask)
            about_image = about_image.resize((72, 72), Image.Resampling.LANCZOS)
        except OSError as error:
            messagebox.showerror(
                "About Image Error",
                f"Could not load the About image at {image_path}:\n{error}",
                parent=self.root,
            )
            return

        # Create a custom popup window
        about_window = tk.Toplevel(self.root)
        self.about_images[about_window] = ImageTk.PhotoImage(
            about_image, master=about_window
        )
        about_window.bind(
            "<Destroy>",
            lambda event: self.about_images.pop(about_window, None)
            if event.widget is about_window
            else None,
            add="+",
        )
        about_window.title("About")
        about_window.geometry("360x150")
        about_window.resizable(False, False)
        about_window.configure(bg="#2f3136")

        content_frame = tk.Frame(about_window, bg="#2f3136", padx=20, pady=15)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Circular profile photo on the left, centered vertically
        image_label = tk.Label(
            content_frame,
            image=self.about_images[about_window],
            bg="#2f3136",
            borderwidth=0,
        )
        image_label.pack(side=tk.LEFT, padx=(0, 18), pady=(8, 28))

        text_frame = tk.Frame(content_frame, bg="#2f3136")
        text_frame.pack(side=tk.LEFT, expand=True, fill=tk.Y)

        # Main text
        label = tk.Label(
            text_frame,
            text="Created By: Daniel Morvay",
            justify=tk.LEFT,
            anchor="w",
            bg="#2f3136",
            fg="white",
            pady=10,
            font=("TkDefaultFont", 12),
        )
        label.pack(fill=tk.X)

        # Hyperlink text
        url = "https://github.com/morvayd/"
        link_label = tk.Label(
            text_frame,
            text="GitHub Account",
            fg="#6ea9ff",
            bg="#2f3136",
            cursor="hand2",
            font=("TkDefaultFont", 12, "underline"),
            activeforeground="#9dc1ff",
            justify=tk.LEFT,
            anchor="w",
        )
        link_label.pack(fill=tk.X)

        # Bind the click event to open the URL
        link_label.bind("<Button-1>", lambda e: webbrowser.open(url))

        # Close button
        ttk.Button(
            text_frame,
            text="Close",
            command=about_window.destroy,
        ).pack(anchor=tk.W, pady=(16, 0))


    def _reset_search(self):
        self._hide_path_tooltip()
        self.query_entry.delete(0, tk.END)
        self.exclude_entry.delete(0, tk.END)
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.open_folder_btn.config(state=tk.DISABLED)
        self.search_results = []
        self.current_page = 0
        self.result_status.set("")
        self._update_pagination_controls()

    def _start_search(self):
        self._hide_path_tooltip()
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
        self.open_folder_btn.config(state=tk.DISABLED)
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
        self._hide_path_tooltip()
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.open_folder_btn.config(state=tk.DISABLED)

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
    db_path = str(Path(__file__).resolve().parent / "SQLite" / "SearchDB.sqlite")
    database_error, record_count = validate_database(db_path)
    if database_error:
        show_database_setup_error(root, database_error)
    else:
        root.deiconify()
        app = FuzzySearchGUI(root, db_path, record_count)
        root.mainloop()
