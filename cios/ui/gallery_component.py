"""CIOS — Gallery Component.

Renders a scrollable thumbnail grid inside the center panel.
Displays a path header, responsive grid of placeholder cells (gray square + filename),
and a slideshow button. Thumbnails are loaded asynchronously in a background thread.
"""

import logging
import queue
import threading
import tkinter as tk
from dataclasses import dataclass

from PIL import Image, ImageDraw

try:
    from PIL import ImageTk
except ImportError:
    ImageTk = None  # type: ignore[assignment,misc]

from cios.ui.theme import (
    ACCENT,
    ACCENT_LT,
    BG,
    BG_CARD,
    BG_HOVER,
    ERROR,
    FG,
    FG_DIM,
    FG_SEC,
    SP_COMPACT,
    SP_MICRO,
    SP_TIGHT,
    WARNING,
)

logger = logging.getLogger(__name__)


@dataclass
class ThumbnailTask:
    """A pending thumbnail generation task."""

    index: int
    file_path: str
    media_type: str  # determines if play overlay is needed


def _apply_play_overlay(thumb: Image.Image) -> Image.Image:
    """Composite a play triangle onto a video thumbnail.

    Draws a semi-transparent circle with a white triangle play icon
    centered on the thumbnail image.

    Args:
        thumb: The source thumbnail image.

    Returns:
        A new RGBA image with the play overlay composited on top.
    """
    overlay = Image.new("RGBA", thumb.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Draw semi-transparent circle + triangle
    cx, cy = thumb.size[0] // 2, thumb.size[1] // 2
    r = min(cx, cy) // 3
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 128))
    # Triangle play icon
    tri_points = [(cx - r // 3, cy - r // 2), (cx - r // 3, cy + r // 2), (cx + r // 2, cy)]
    draw.polygon(tri_points, fill=(255, 255, 255, 200))
    return Image.alpha_composite(thumb.convert("RGBA"), overlay)


class GalleryComponent:
    """Renders a scrollable thumbnail grid inside the center panel."""

    THUMB_SIZE = (140, 140)
    CELL_PAD = 8
    CELL_WIDTH = THUMB_SIZE[0] + CELL_PAD * 2  # 156
    # Row height: thumbnail height + vertical padding (top + bottom) + filename label (~20px)
    ROW_HEIGHT = THUMB_SIZE[1] + CELL_PAD * 2 + 20  # 176

    def __init__(self, parent: tk.Frame, gallery_data: dict, root: tk.Tk, fonts: dict):
        """
        Args:
            parent: The feed_area frame to render into.
            gallery_data: The "gallery" dict from Gallery_Signal.
            root: Tk root for after() scheduling.
            fonts: Font dict from CIOSApp.
        """
        self._parent = parent
        self._gallery_data = gallery_data
        self._root = root
        self._fonts = fonts

        self._source_path: str = gallery_data.get("source_path", "")
        self._media_type: str = gallery_data.get("media_type", "image")
        self._files: list[dict] = gallery_data.get("files", [])
        self._total_count: int = gallery_data.get("total_count", len(self._files))

        # Widget references
        self._outer_frame: tk.Frame | None = None
        self._header_frame: tk.Frame | None = None
        self._scroll_frame = None  # ScrollFrame instance
        self._grid_frame: tk.Frame | None = None
        self._cells: list[dict] = []  # list of cell state dicts
        self._photos: list = []  # keep PhotoImage references alive

        # Track current column count for resize detection
        self._current_cols: int = 0

        # Reference to active ImageViewer (prevent GC)
        self._viewer: object | None = None

        # Async thumbnail loading state
        self._cancelled: bool = False
        self._thumb_queue: queue.Queue = queue.Queue()
        self._loaded_indices: set = set()  # Track enqueued/loaded indices

        # Selection mode state
        self._selection_mode: bool = False
        self._selected_indices: set = set()
        self._selection_toolbar: tk.Frame | None = None

        self._build()

    def _build(self) -> None:
        """Build the full gallery component."""
        self._outer_frame = tk.Frame(self._parent, bg=BG)
        self._outer_frame.pack(fill="both", expand=True)

        self._build_header()
        self._build_grid()

        # Bind resize event on the outer frame
        self._outer_frame.bind("<Configure>", self._on_resize)

    def destroy(self) -> None:
        """Clean up all widgets and cancel pending thumbnail loads."""
        self._cancelled = True
        if self._outer_frame and self._outer_frame.winfo_exists():
            self._outer_frame.destroy()
        self._cells.clear()
        self._photos.clear()

    def _build_header(self) -> None:
        """Render path header and slideshow button."""
        self._header_frame = tk.Frame(self._outer_frame, bg=BG)
        self._header_frame.pack(fill="x", pady=(0, SP_COMPACT))

        # Path header label
        path_label = tk.Label(
            self._header_frame,
            text=self._source_path,
            font=self._fonts.get("sec", None),
            fg=FG_SEC,
            bg=BG,
            anchor="w",
        )
        path_label.pack(side="left", fill="x", expand=True)

        # Slideshow button (Requirement 4.6)
        slideshow_btn = tk.Label(
            self._header_frame,
            text="▶ Slideshow",
            font=self._fonts.get("btn", None),
            fg=ACCENT_LT,
            bg=BG_CARD,
            padx=SP_COMPACT,
            pady=SP_MICRO,
            cursor="hand2",
        )
        slideshow_btn.pack(side="right", padx=(SP_TIGHT, 0))
        slideshow_btn.bind("<Button-1>", lambda _: self._start_slideshow())
        slideshow_btn.bind("<Enter>", lambda _: slideshow_btn.configure(bg=BG_HOVER))
        slideshow_btn.bind("<Leave>", lambda _: slideshow_btn.configure(bg=BG_CARD))

        # Select mode button
        self._select_btn = tk.Label(
            self._header_frame,
            text="☐ Selecionar",
            font=self._fonts.get("btn", None),
            fg=ACCENT_LT,
            bg=BG_CARD,
            padx=SP_COMPACT,
            pady=SP_MICRO,
            cursor="hand2",
        )
        self._select_btn.pack(side="right", padx=(SP_TIGHT, 0))
        self._select_btn.bind("<Button-1>", lambda _: self._toggle_selection_mode())
        self._select_btn.bind("<Enter>", lambda _: self._select_btn.configure(bg=BG_HOVER))
        self._select_btn.bind("<Leave>", lambda _: self._select_btn.configure(bg=BG_CARD))

    def _build_grid(self) -> None:
        """Create the ScrollFrame container and grid Frame."""
        from cios.ui.gui import ScrollFrame

        self._scroll_frame = ScrollFrame(self._outer_frame, bg=BG)
        self._scroll_frame.pack(fill="both", expand=True)

        self._grid_frame = tk.Frame(self._scroll_frame.inner, bg=BG)
        self._grid_frame.pack(fill="both", expand=True)

        # Initialize column count based on parent width before creating cells
        try:
            self._parent.update_idletasks()
            parent_width = self._parent.winfo_width()
            if parent_width > 1:
                self._current_cols = self._compute_columns(parent_width)
        except Exception:
            pass
        if self._current_cols < 1:
            self._current_cols = 3  # sensible default

        # Create placeholder cells for each file
        self._create_cells()

        # Start loading thumbnails in background
        self._load_thumbnails_async()

    def _compute_columns(self, width: int) -> int:
        """Calculate column count based on available width."""
        return max(1, width // self.CELL_WIDTH)

    def _on_resize(self, event) -> None:
        """Reflow grid when panel width changes."""
        new_cols = self._compute_columns(event.width)
        if new_cols != self._current_cols:
            self._current_cols = new_cols
            self._reflow_grid()

    def _create_cells(self) -> None:
        """Create placeholder cells (gray square + filename label) for each file."""
        self._cells.clear()

        for i, file_info in enumerate(self._files):
            cell = self._create_cell(i, file_info)
            self._cells.append(cell)

        # Initial layout
        self._reflow_grid()

    def _create_cell(self, index: int, file_info: dict) -> dict:
        """Create a single cell with placeholder thumbnail and filename label."""
        from cios.skills.gallery_store import get_store

        cell_frame = tk.Frame(
            self._grid_frame,
            bg=BG,
            padx=self.CELL_PAD,
            pady=self.CELL_PAD,
        )

        # Placeholder thumbnail (gray square)
        thumb_label = tk.Label(
            cell_frame,
            width=self.THUMB_SIZE[0],
            height=self.THUMB_SIZE[1],
            bg=BG_CARD,
            relief="flat",
            bd=0,
        )
        # Use pixel-sized frame trick for exact dimensions
        thumb_label.configure(
            image="",
            width=self.THUMB_SIZE[0],
            height=self.THUMB_SIZE[1],
        )
        thumb_label.pack(pady=(0, SP_MICRO))

        # Action bar (favorite ★ + delete ✕)
        action_bar = tk.Frame(cell_frame, bg=BG)
        action_bar.pack(fill="x", pady=(0, SP_MICRO))

        file_path = file_info.get("path", "")
        store = get_store()
        is_fav = store.is_favorite(file_path) if file_path else False

        fav_label = tk.Label(
            action_bar,
            text="★" if is_fav else "☆",
            font=self._fonts.get("small", None),
            fg=WARNING if is_fav else FG_DIM,
            bg=BG,
            cursor="hand2",
        )
        fav_label.pack(side="left", padx=(0, SP_TIGHT))
        fav_label.bind("<Button-1>", lambda _, idx=index: self._on_favorite_click(idx))

        del_label = tk.Label(
            action_bar,
            text="✕",
            font=self._fonts.get("small", None),
            fg=FG_DIM,
            bg=BG,
            cursor="hand2",
        )
        del_label.pack(side="right", padx=(SP_TIGHT, 0))
        del_label.bind("<Button-1>", lambda _, idx=index: self._on_delete_click(idx))
        del_label.bind("<Enter>", lambda _, lbl=del_label: lbl.configure(fg=ERROR))
        del_label.bind("<Leave>", lambda _, lbl=del_label: lbl.configure(fg=FG_DIM))

        # Filename label
        filename = file_info.get("name", "")
        # Truncate long filenames for display
        display_name = filename if len(filename) <= 18 else filename[:15] + "…"
        name_label = tk.Label(
            cell_frame,
            text=display_name,
            font=self._fonts.get("small", None),
            fg=FG_DIM,
            bg=BG,
            anchor="center",
            wraplength=self.THUMB_SIZE[0],
        )
        name_label.pack()

        # Bind click events
        thumb_label.bind("<Button-1>", lambda _, idx=index: self._on_thumbnail_click(idx))
        cell_frame.bind("<Button-1>", lambda _, idx=index: self._on_thumbnail_click(idx))
        thumb_label.configure(cursor="hand2")
        cell_frame.configure(cursor="hand2")

        return {
            "index": index,
            "file_info": file_info,
            "frame": cell_frame,
            "thumb_label": thumb_label,
            "name_label": name_label,
            "fav_label": fav_label,
            "del_label": del_label,
            "photo": None,
            "loaded": False,
        }

    def _reflow_grid(self) -> None:
        """Reposition all cells in the grid based on current column count."""
        if not self._cells:
            return

        cols = self._current_cols if self._current_cols > 0 else 1

        # Remove all cells from grid first
        for cell in self._cells:
            cell["frame"].grid_forget()

        # Re-grid all cells
        for i, cell in enumerate(self._cells):
            row = i // cols
            col = i % cols
            cell["frame"].grid(row=row, column=col, sticky="n")

    def _on_thumbnail_click(self, index: int) -> None:
        """Handle click — in selection mode toggles selection, otherwise opens viewer."""
        # In selection mode, toggle selection instead of opening
        if self._selection_mode:
            self._toggle_cell_selection(index)
            return

        file_info = self._files[index]
        media_type = file_info.get("media_type", "image")

        if media_type == "image":
            # Filter to image files only for the viewer
            image_files = [f for f in self._files if f.get("media_type") == "image"]
            # Find the index of this file within image_files
            image_index = 0
            for i, f in enumerate(image_files):
                if f.get("path") == file_info.get("path"):
                    image_index = i
                    break
            self._open_image_viewer(image_files, image_index)
        elif media_type == "video":
            file_path = file_info.get("path", "")
            self._play_video(file_path, index)

    def _open_image_viewer(
        self, files: list[dict], start_index: int, slideshow: bool = False
    ) -> None:
        """Open ImageViewer overlay, optionally in slideshow mode."""
        from cios.ui.image_viewer import ImageViewer

        self._viewer = ImageViewer(
            parent=self._parent,
            files=files,
            start_index=start_index,
            root=self._root,
            fonts=self._fonts,
        )
        if slideshow:
            self._viewer.start_slideshow()

    def _play_video(self, file_path: str, index: int) -> None:
        """Play a video file and display error if playback fails (Requirement 5.3, 5.4)."""
        from cios.skills.media_player import play_media

        success, message = play_media(file_path)
        if not success:
            self._show_error_message(message, index)

    def _show_error_message(self, message: str, index: int) -> None:
        """Display a temporary error label below the video thumbnail cell.

        The error auto-dismisses after 5 seconds (Requirement 5.4).
        """
        if index < 0 or index >= len(self._cells):
            return

        cell = self._cells[index]
        cell_frame = cell["frame"]

        error_label = tk.Label(
            cell_frame,
            text=message,
            font=self._fonts.get("small", None),
            fg="#ff4444",
            bg=BG,
            anchor="center",
            wraplength=self.THUMB_SIZE[0],
        )
        error_label.pack(pady=(SP_MICRO, 0))

        # Auto-dismiss after 5 seconds
        def _dismiss():
            if error_label.winfo_exists():
                error_label.destroy()

        self._root.after(5000, _dismiss)

    def _toggle_selection_mode(self) -> None:
        """Enter or exit selection mode."""
        self._selection_mode = not self._selection_mode

        if self._selection_mode:
            self._selected_indices.clear()
            self._select_btn.configure(text="✓ Selecionando", fg=ACCENT)
            self._show_selection_toolbar()
            self._update_cells_selection_ui()
        else:
            self._selected_indices.clear()
            self._select_btn.configure(text="☐ Selecionar", fg=ACCENT_LT)
            self._hide_selection_toolbar()
            self._update_cells_selection_ui()

    def _show_selection_toolbar(self) -> None:
        """Show the selection action toolbar below the header."""
        if self._selection_toolbar and self._selection_toolbar.winfo_exists():
            return

        self._selection_toolbar = tk.Frame(self._outer_frame, bg=BG_CARD, pady=SP_MICRO)
        # Insert after header, before scroll frame
        self._selection_toolbar.pack(fill="x", pady=(0, SP_COMPACT), before=self._scroll_frame)

        self._sel_count_label = tk.Label(
            self._selection_toolbar,
            text="0 selecionados",
            font=self._fonts.get("small", None),
            fg=FG_SEC,
            bg=BG_CARD,
            padx=SP_COMPACT,
        )
        self._sel_count_label.pack(side="left")

        # Delete selected button
        del_btn = tk.Label(
            self._selection_toolbar,
            text="🗑 Deletar",
            font=self._fonts.get("btn", None),
            fg=ERROR,
            bg=BG_HOVER,
            padx=SP_COMPACT,
            pady=SP_MICRO,
            cursor="hand2",
        )
        del_btn.pack(side="right", padx=(SP_TIGHT, SP_COMPACT))
        del_btn.bind("<Button-1>", lambda _: self._delete_selected())

        # Favorite selected button
        fav_btn = tk.Label(
            self._selection_toolbar,
            text="★ Favoritar",
            font=self._fonts.get("btn", None),
            fg=WARNING,
            bg=BG_HOVER,
            padx=SP_COMPACT,
            pady=SP_MICRO,
            cursor="hand2",
        )
        fav_btn.pack(side="right", padx=(SP_TIGHT, 0))
        fav_btn.bind("<Button-1>", lambda _: self._favorite_selected())

        # Select all button
        all_btn = tk.Label(
            self._selection_toolbar,
            text="Todos",
            font=self._fonts.get("btn", None),
            fg=ACCENT_LT,
            bg=BG_HOVER,
            padx=SP_COMPACT,
            pady=SP_MICRO,
            cursor="hand2",
        )
        all_btn.pack(side="right", padx=(SP_TIGHT, 0))
        all_btn.bind("<Button-1>", lambda _: self._select_all())

    def _hide_selection_toolbar(self) -> None:
        """Hide the selection toolbar."""
        if self._selection_toolbar and self._selection_toolbar.winfo_exists():
            self._selection_toolbar.destroy()
        self._selection_toolbar = None

    def _update_selection_count(self) -> None:
        """Update the selection count label."""
        if hasattr(self, "_sel_count_label") and self._sel_count_label.winfo_exists():
            count = len(self._selected_indices)
            self._sel_count_label.configure(text=f"{count} selecionado{'s' if count != 1 else ''}")

    def _update_cells_selection_ui(self) -> None:
        """Update all cells to show/hide selection checkboxes."""
        for cell in self._cells:
            idx = cell["index"]
            check_label = cell.get("check_label")

            if self._selection_mode:
                # Show checkbox
                if not check_label:
                    check_label = tk.Label(
                        cell["frame"],
                        text="☐",
                        font=self._fonts.get("small", None),
                        fg=FG_DIM,
                        bg=BG,
                    )
                    check_label.place(x=2, y=2)
                    cell["check_label"] = check_label
                else:
                    check_label.place(x=2, y=2)

                is_selected = idx in self._selected_indices
                check_label.configure(
                    text="☑" if is_selected else "☐",
                    fg=ACCENT if is_selected else FG_DIM,
                )
            else:
                # Hide checkbox
                if check_label:
                    check_label.place_forget()

    def _toggle_cell_selection(self, index: int) -> None:
        """Toggle selection state of a cell."""
        if index in self._selected_indices:
            self._selected_indices.discard(index)
        else:
            self._selected_indices.add(index)

        # Update this cell's checkbox
        if index < len(self._cells):
            cell = self._cells[index]
            check_label = cell.get("check_label")
            if check_label and check_label.winfo_exists():
                is_selected = index in self._selected_indices
                check_label.configure(
                    text="☑" if is_selected else "☐",
                    fg=ACCENT if is_selected else FG_DIM,
                )

        self._update_selection_count()

    def _select_all(self) -> None:
        """Select all files."""
        if len(self._selected_indices) == len(self._files):
            # Deselect all
            self._selected_indices.clear()
        else:
            self._selected_indices = set(range(len(self._files)))
        self._update_cells_selection_ui()
        self._update_selection_count()

    def _delete_selected(self) -> None:
        """Delete all selected files (move to trash)."""
        from cios.skills.gallery_store import get_store

        if not self._selected_indices:
            return

        count = len(self._selected_indices)
        paths = [
            self._files[i].get("path", "")
            for i in sorted(self._selected_indices)
            if i < len(self._files)
        ]
        paths = [p for p in paths if p]

        if not paths:
            return

        store = get_store()
        entries = store.trash_files(paths)

        if entries:
            # Remove cells in reverse order to maintain indices
            for idx in sorted(self._selected_indices, reverse=True):
                if idx < len(self._cells):
                    self._cells[idx]["frame"].destroy()
                    self._cells.pop(idx)
                    self._files.pop(idx)

            # Re-index
            for i, c in enumerate(self._cells):
                c["index"] = i

            self._selected_indices.clear()
            self._update_selection_count()
            self._reflow_grid()
            self._update_cells_selection_ui()

    def _favorite_selected(self) -> None:
        """Add all selected files to favorites."""
        from cios.skills.gallery_store import get_store

        if not self._selected_indices:
            return

        store = get_store()
        for idx in self._selected_indices:
            if idx < len(self._files):
                path = self._files[idx].get("path", "")
                if path:
                    store.add_favorite(path)

        # Update star icons
        for idx in self._selected_indices:
            if idx < len(self._cells):
                cell = self._cells[idx]
                fav_label = cell.get("fav_label")
                if fav_label and fav_label.winfo_exists():
                    fav_label.configure(text="★", fg=WARNING)

        self._update_selection_count()

    def _on_favorite_click(self, index: int) -> None:
        """Toggle favorite status for a file."""
        from cios.skills.gallery_store import get_store

        if index < 0 or index >= len(self._files):
            return

        file_info = self._files[index]
        file_path = file_info.get("path", "")
        if not file_path:
            return

        store = get_store()
        is_fav = store.toggle_favorite(file_path)

        # Update the star visual
        cell = self._cells[index]
        fav_label = cell.get("fav_label")
        if fav_label and fav_label.winfo_exists():
            fav_label.configure(
                text="★" if is_fav else "☆",
                fg=WARNING if is_fav else FG_DIM,
            )

    def _on_delete_click(self, index: int) -> None:
        """Delete a file (move to trash) with confirmation."""
        from cios.skills.gallery_store import get_store

        if index < 0 or index >= len(self._files):
            return

        file_info = self._files[index]
        file_path = file_info.get("path", "")
        if not file_path:
            return

        # Show inline confirmation
        cell = self._cells[index]
        cell_frame = cell["frame"]

        # Create confirmation overlay
        confirm_frame = tk.Frame(cell_frame, bg=BG_CARD)
        confirm_frame.place(relwidth=1, relheight=1)

        confirm_label = tk.Label(
            confirm_frame,
            text="Deletar?",
            font=self._fonts.get("small", None),
            fg=FG,
            bg=BG_CARD,
        )
        confirm_label.pack(expand=True, pady=(20, 4))

        btn_frame = tk.Frame(confirm_frame, bg=BG_CARD)
        btn_frame.pack(pady=(0, 20))

        yes_btn = tk.Label(
            btn_frame,
            text="Sim",
            font=self._fonts.get("small", None),
            fg=ERROR,
            bg=BG_HOVER,
            padx=8,
            pady=2,
            cursor="hand2",
        )
        yes_btn.pack(side="left", padx=4)

        no_btn = tk.Label(
            btn_frame,
            text="Não",
            font=self._fonts.get("small", None),
            fg=FG_SEC,
            bg=BG_HOVER,
            padx=8,
            pady=2,
            cursor="hand2",
        )
        no_btn.pack(side="left", padx=4)

        def _confirm_delete(_=None):
            confirm_frame.destroy()
            store = get_store()
            entry = store.trash_file(file_path)
            if entry:
                self._remove_cell(index)

        def _cancel_delete(_=None):
            confirm_frame.destroy()

        yes_btn.bind("<Button-1>", _confirm_delete)
        no_btn.bind("<Button-1>", _cancel_delete)

        # Auto-dismiss after 5 seconds
        self._root.after(5000, lambda: _cancel_delete() if confirm_frame.winfo_exists() else None)

    def _remove_cell(self, index: int) -> None:
        """Remove a cell from the grid after deletion."""
        if index < 0 or index >= len(self._cells):
            return

        cell = self._cells[index]
        cell["frame"].destroy()
        self._cells.pop(index)
        self._files.pop(index)

        # Re-index remaining cells
        for i, c in enumerate(self._cells):
            c["index"] = i

        self._reflow_grid()

    def _start_slideshow(self) -> None:
        """Start slideshow mode — open ImageViewer at index 0 in slideshow (Requirement 4.6)."""
        # Filter to image files only
        image_files = [f for f in self._files if f.get("media_type") == "image"]
        if not image_files:
            return
        self._open_image_viewer(image_files, start_index=0, slideshow=True)

    def _load_thumbnails_async(self) -> None:
        """Start background thread for thumbnail generation.

        Enqueues ALL files for thumbnail loading. The worker thread processes
        them sequentially, posting results to the main thread as they complete.
        Scroll-based lazy loading triggers additional loads if the worker
        has already exited.
        """
        # Bind mousewheel scroll event for lazy loading of additional thumbnails
        if self._scroll_frame is not None:
            self._scroll_frame._canvas.bind("<Configure>", self._on_canvas_scroll, add="+")

        # Enqueue ALL files for thumbnail loading
        for i in range(len(self._files)):
            self._enqueue_thumbnail(i)

        # Start daemon worker thread
        worker = threading.Thread(
            target=self._thumbnail_worker,
            daemon=True,
            name="GalleryThumbnailWorker",
        )
        worker.start()

    def _on_canvas_scroll(self, event=None) -> None:
        """Handle canvas configure/scroll events for lazy loading."""
        self._on_scroll()

    def _get_visible_range(self, scroll_pos: float, viewport_height: int) -> tuple:
        """Calculate which thumbnail indices are currently visible.

        Args:
            scroll_pos: Current scroll position (pixels from top).
            viewport_height: Height of the visible viewport in pixels.

        Returns:
            (start_index, end_index) tuple where start >= 0 and end <= total_count.
        """
        cols = self._current_cols if self._current_cols > 0 else 1
        row_height = self.ROW_HEIGHT
        total_count = len(self._files)

        if total_count == 0 or row_height <= 0:
            return (0, 0)

        # Calculate visible rows (with 1-row buffer above and below)
        start_row = max(0, int(scroll_pos // row_height) - 1)
        end_row = (
            int((scroll_pos + viewport_height) // row_height) + 2
        )  # +1 for partial row, +1 for buffer

        # Convert rows to indices
        start_index = max(0, start_row * cols)
        end_index = min(end_row * cols, total_count)

        # Clamp start to not exceed total_count
        if start_index >= total_count:
            return (total_count, total_count)

        return (start_index, end_index)

    def _on_scroll(self) -> None:
        """Trigger lazy loading for newly visible thumbnails.

        Gets the current scroll position from the ScrollFrame canvas,
        computes the visible range, and enqueues thumbnail tasks for
        any indices not yet loaded (Requirement 7.4).
        """
        if self._cancelled or self._scroll_frame is None:
            return

        canvas = self._scroll_frame._canvas

        try:
            # Get current scroll position in pixels
            # yview() returns (first_fraction, last_fraction)
            first_frac = canvas.yview()[0]
            # Get the total scrollable height from the scroll region
            bbox = canvas.bbox("all")
            if bbox is None:
                return
            total_height = bbox[3] - bbox[1]
            scroll_pos = first_frac * total_height

            # Get viewport height
            viewport_height = canvas.winfo_height()
            if viewport_height <= 1:
                return
        except Exception:
            return

        start_idx, end_idx = self._get_visible_range(scroll_pos, viewport_height)

        # Enqueue any new indices that haven't been loaded yet
        enqueued_new = False
        for i in range(start_idx, end_idx):
            if i < len(self._files) and i not in self._loaded_indices:
                self._enqueue_thumbnail(i)
                enqueued_new = True

        # If we enqueued new tasks, ensure a worker is running
        if enqueued_new:
            self._ensure_worker_running()

    def _enqueue_thumbnail(self, index: int) -> None:
        """Enqueue a single thumbnail task if not already enqueued."""
        if index in self._loaded_indices:
            return
        self._loaded_indices.add(index)
        file_info = self._files[index]
        task = ThumbnailTask(
            index=index,
            file_path=file_info.get("path", ""),
            media_type=file_info.get("media_type", "image"),
        )
        self._thumb_queue.put(task)

    def _ensure_worker_running(self) -> None:
        """Start a new worker thread if the queue has items and no worker is active."""
        # Start a new daemon worker thread to process newly enqueued tasks
        worker = threading.Thread(
            target=self._thumbnail_worker,
            daemon=True,
            name="GalleryThumbnailWorker",
        )
        worker.start()

    def _thumbnail_worker(self) -> None:
        """Worker thread that processes thumbnail tasks from the queue.

        Calls get_thumbnail() for each file, applies play overlay for videos,
        and posts PIL Image results to the main thread via root.after().
        """
        from cios.skills.media_player import get_thumbnail

        while not self._cancelled:
            try:
                task = self._thumb_queue.get(timeout=0.5)
            except queue.Empty:
                # Queue is empty, worker is done
                break

            if self._cancelled:
                break

            try:
                # Get thumbnail path (uses cache when available)
                thumb_path = get_thumbnail(task.file_path, size=self.THUMB_SIZE)

                if thumb_path is None:
                    # Thumbnail generation failed — post placeholder signal
                    logger.warning("Thumbnail generation failed for: %s", task.file_path)
                    self._post_to_main_thread(task.index, None)
                    continue

                # Load the thumbnail as a PIL Image
                pil_image = Image.open(thumb_path)
                pil_image = pil_image.copy()  # Ensure file handle is released

                # Apply play overlay for video thumbnails
                if task.media_type == "video":
                    pil_image = _apply_play_overlay(pil_image)

                # Post PIL Image to main thread for PhotoImage conversion
                self._post_to_main_thread(task.index, pil_image)

            except Exception as e:
                logger.warning("Error loading thumbnail for %s: %s", task.file_path, e)
                self._post_to_main_thread(task.index, None)

    def _post_to_main_thread(self, index: int, pil_image: Image.Image | None) -> None:
        """Schedule _on_thumbnail_ready callback on the main thread."""
        if self._cancelled:
            return
        try:
            self._root.after(0, self._on_thumbnail_ready, index, pil_image)
        except Exception:
            # Root may have been destroyed
            pass

    def _on_thumbnail_ready(self, index: int, pil_image: Image.Image | None) -> None:
        """Callback from background thread — update cell on main thread.

        Converts PIL Image to ImageTk.PhotoImage (must be done on main thread)
        and updates the cell's thumbnail label.
        """
        if self._cancelled:
            return
        if index < 0 or index >= len(self._cells):
            return

        cell = self._cells[index]

        if pil_image is None:
            # Show placeholder for failed thumbnails
            cell["loaded"] = True
            return

        if ImageTk is None:
            # ImageTk not available — cannot display thumbnails
            cell["loaded"] = True
            return

        try:
            # Convert PIL Image to PhotoImage on the main thread
            photo = ImageTk.PhotoImage(pil_image)
            cell["photo"] = photo
            cell["loaded"] = True
            cell["thumb_label"].configure(image=photo)
            self._photos.append(photo)  # prevent GC
        except Exception as e:
            logger.warning("Failed to display thumbnail at index %d: %s", index, e)
            cell["loaded"] = True
