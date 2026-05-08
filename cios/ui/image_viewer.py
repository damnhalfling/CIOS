"""CIOS — Image Viewer.

Full-size image overlay with keyboard navigation, slideshow mode,
EXIF info panel, and basic editing controls (rotate, flip, brightness).
"""

import os
import tkinter as tk

from PIL import Image

try:
    from PIL import ImageTk
except ImportError:
    ImageTk = None  # type: ignore[assignment,misc]

from cios.ui.theme import (
    ACCENT_LT,
    BG,
    BG_CARD,
    BG_HOVER,
    FG_SEC,
    SP_COMPACT,
    SP_MICRO,
    SP_TIGHT,
    WARNING,
)


class ImageViewer:
    """Full-size image overlay with keyboard navigation and slideshow."""

    def __init__(
        self,
        parent: tk.Frame,
        files: list[dict],
        start_index: int,
        root: tk.Tk,
        fonts: dict,
        on_close: callable | None = None,
    ):
        """
        Args:
            parent: Frame to overlay (feed_area).
            files: List of image file dicts (each with "path", "name", "media_type").
            start_index: Index of clicked image.
            root: Tk root for bindings.
            fonts: Font dict.
            on_close: Optional callback invoked when the viewer closes.
        """
        self._parent = parent
        self._files = files
        self._current_index = start_index
        self._root = root
        self._fonts = fonts
        self._on_close = on_close

        # Keep PhotoImage reference alive to prevent GC
        self._current_photo: ImageTk.PhotoImage | None = None

        # Key binding IDs for cleanup
        self._bind_ids: list[str] = []

        # Slideshow state (Requirement 4.1, 4.2)
        self._slideshow_active: bool = False
        self._slideshow_paused: bool = False
        self._slideshow_interval: int = 5000  # ms (Requirement 4.2)
        self._slideshow_after_id: str | None = None

        # Build overlay
        self._overlay = tk.Frame(parent, bg=BG)
        self._overlay.place(relwidth=1, relheight=1)

        # Image display label (centered)
        self._image_label = tk.Label(self._overlay, bg=BG, bd=0)
        self._image_label.pack(expand=True, fill="both")

        # Filename label at the bottom
        self._filename_label = tk.Label(
            self._overlay,
            text="",
            font=self._fonts.get("sub", None),
            fg=FG_SEC,
            bg=BG,
            anchor="center",
            pady=SP_COMPACT,
        )
        self._filename_label.pack(side="bottom", fill="x")

        # Favorite button (★/☆) at bottom-right
        self._fav_btn = tk.Label(
            self._overlay,
            text="☆",
            font=self._fonts.get("sub", None),
            fg=FG_SEC,
            bg=BG,
            cursor="hand2",
            padx=SP_COMPACT,
            pady=SP_COMPACT,
        )
        self._fav_btn.place(relx=1.0, rely=1.0, anchor="se", x=-SP_COMPACT, y=-SP_COMPACT)
        self._fav_btn.bind("<Button-1>", lambda _: self._toggle_favorite())

        # Info panel (hidden by default, toggled with 'i' key)
        self._info_visible: bool = False
        self._info_frame: tk.Frame | None = None

        # Edit toolbar at the top
        self._toolbar = tk.Frame(self._overlay, bg=BG_CARD)
        self._toolbar.place(relx=0.5, y=SP_COMPACT, anchor="n")

        toolbar_items = [
            ("↻ 90°", self._rotate_cw),
            ("↺ 90°", self._rotate_ccw),
            ("↔ Flip", self._flip_h),
            ("↕ Flip", self._flip_v),
            ("☀ +", self._brightness_up),
            ("☀ −", self._brightness_down),
            ("ℹ Info", self._toggle_info),
            ("↗ Enviar", self._share),
        ]

        for text, cmd in toolbar_items:
            btn = tk.Label(
                self._toolbar,
                text=text,
                font=self._fonts.get("small", None),
                fg=ACCENT_LT,
                bg=BG_CARD,
                padx=SP_TIGHT,
                pady=SP_MICRO,
                cursor="hand2",
            )
            btn.pack(side="left", padx=2)
            btn.bind("<Button-1>", lambda _, c=cmd: c())
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=BG_HOVER))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=BG_CARD))

        # Bind Escape key — stops slideshow if active, otherwise closes viewer
        # (Requirement 3.3, 4.4)
        bind_id = self._root.bind("<Escape>", lambda e: self._handle_escape())
        self._bind_ids.append(("<Escape>", bind_id))

        # Bind Right arrow key to navigate forward (Requirement 3.5)
        bind_id = self._root.bind("<Right>", lambda e: self.navigate(+1))
        self._bind_ids.append(("<Right>", bind_id))

        # Bind Left arrow key to navigate backward (Requirement 3.6)
        bind_id = self._root.bind("<Left>", lambda e: self.navigate(-1))
        self._bind_ids.append(("<Left>", bind_id))

        # Bind Space to toggle slideshow pause (Requirement 4.5)
        bind_id = self._root.bind("<space>", lambda e: self._toggle_slideshow_pause())
        self._bind_ids.append(("<space>", bind_id))

        # Show the initial image
        self._show_image(self._current_index)

    def _handle_escape(self) -> None:
        """Handle Escape key press.

        If slideshow is active, stop it (Requirement 4.4).
        Otherwise, close the viewer (Requirement 3.3).
        """
        if self._slideshow_active:
            self.stop_slideshow()
        else:
            self.close()

    def _toggle_slideshow_pause(self) -> None:
        """Toggle slideshow pause state (Requirement 4.5)."""
        if self._slideshow_active:
            self._slideshow_paused = not self._slideshow_paused

    def start_slideshow(self) -> None:
        """Enter slideshow mode (Requirement 4.1)."""
        self._slideshow_active = True
        self._slideshow_paused = False
        self._slideshow_tick()

    def _slideshow_tick(self) -> None:
        """Advance to next image and schedule next tick (Requirement 4.1, 4.3)."""
        if not self._slideshow_active:
            return
        if not self._slideshow_paused:
            self.navigate(+1)
        self._slideshow_after_id = self._root.after(self._slideshow_interval, self._slideshow_tick)

    def stop_slideshow(self) -> None:
        """Exit slideshow mode (Requirement 4.4)."""
        self._slideshow_active = False
        self._slideshow_paused = False
        if self._slideshow_after_id:
            self._root.after_cancel(self._slideshow_after_id)
            self._slideshow_after_id = None
        # Close viewer and return to grid
        self.close()

    def close(self) -> None:
        """Destroy overlay and unbind keys."""
        # Stop any active slideshow scheduling
        if self._slideshow_after_id:
            self._root.after_cancel(self._slideshow_after_id)
            self._slideshow_after_id = None
        self._slideshow_active = False

        # Unbind all registered key bindings
        for sequence, bind_id in self._bind_ids:
            self._root.unbind(sequence, bind_id)
        self._bind_ids.clear()

        # Destroy the overlay frame
        if self._overlay and self._overlay.winfo_exists():
            self._overlay.destroy()

        # Release photo reference
        self._current_photo = None

        # Invoke close callback if provided
        if self._on_close:
            self._on_close()

    def _show_image(self, index: int) -> None:
        """Load and display image at index, scaled to fit."""
        self._current_index = index
        file_info = self._files[index]
        file_path = file_info.get("path", "")
        file_name = file_info.get("name", os.path.basename(file_path))

        # Update filename label (Requirement 3.4)
        self._filename_label.configure(text=file_name)

        # Update favorite button state
        self._update_fav_button(file_path)

        # Update filename label (Requirement 3.4)
        self._filename_label.configure(text=file_name)

        try:
            # Load image with Pillow
            img = Image.open(file_path)
            img_w, img_h = img.size

            # Get available display area
            # Update geometry to get current dimensions
            self._overlay.update_idletasks()
            max_w = self._overlay.winfo_width()
            max_h = self._overlay.winfo_height() - self._filename_label.winfo_reqheight()

            # Ensure minimum dimensions
            if max_w < 1:
                max_w = 800
            if max_h < 1:
                max_h = 600

            # Scale to fit
            new_w, new_h = self._scale_to_fit(img_w, img_h, max_w, max_h)

            # Resize image
            img = img.resize((new_w, new_h), Image.LANCZOS)

            # Convert to PhotoImage for Tkinter display
            self._current_photo = ImageTk.PhotoImage(img)
            self._image_label.configure(image=self._current_photo)

        except OSError:
            # Handle corrupt or unreadable images
            self._current_photo = None
            self._image_label.configure(image="", text="⚠ Cannot load image", fg=FG_SEC)

    def _scale_to_fit(
        self, img_width: int, img_height: int, max_width: int, max_height: int
    ) -> tuple[int, int]:
        """Compute scaled dimensions preserving aspect ratio.

        Returns (new_width, new_height) such that:
        - new_width <= max_width
        - new_height <= max_height
        - aspect ratio is preserved (new_width/new_height == img_width/img_height)
        """
        if img_width <= 0 or img_height <= 0:
            return (1, 1)

        # Calculate scale factor to fit within bounds
        scale_w = max_width / img_width
        scale_h = max_height / img_height
        scale = min(scale_w, scale_h)

        new_width = max(1, int(img_width * scale))
        new_height = max(1, int(img_height * scale))

        return (new_width, new_height)

    def _toggle_favorite(self) -> None:
        """Toggle favorite status for the current image."""
        from cios.skills.gallery_store import get_store

        file_info = self._files[self._current_index]
        file_path = file_info.get("path", "")
        if not file_path:
            return

        store = get_store()
        is_fav = store.toggle_favorite(file_path)
        self._fav_btn.configure(
            text="★" if is_fav else "☆",
            fg=WARNING if is_fav else FG_SEC,
        )

    def _update_fav_button(self, file_path: str) -> None:
        """Update the favorite button to reflect current file's state."""
        from cios.skills.gallery_store import get_store

        if not file_path:
            self._fav_btn.configure(text="☆", fg=FG_SEC)
            return

        store = get_store()
        is_fav = store.is_favorite(file_path)
        self._fav_btn.configure(
            text="★" if is_fav else "☆",
            fg=WARNING if is_fav else FG_SEC,
        )

    def _rotate_cw(self) -> None:
        """Rotate current image 90° clockwise."""
        from cios.skills.image_edit import rotate_image

        path = self._current_file_path()
        if path and rotate_image(path, degrees=90):
            self._show_image(self._current_index)

    def _rotate_ccw(self) -> None:
        """Rotate current image 90° counter-clockwise."""
        from cios.skills.image_edit import rotate_image

        path = self._current_file_path()
        if path and rotate_image(path, degrees=-90):
            self._show_image(self._current_index)

    def _flip_h(self) -> None:
        """Flip current image horizontally."""
        from cios.skills.image_edit import flip_image

        path = self._current_file_path()
        if path and flip_image(path, direction="horizontal"):
            self._show_image(self._current_index)

    def _flip_v(self) -> None:
        """Flip current image vertically."""
        from cios.skills.image_edit import flip_image

        path = self._current_file_path()
        if path and flip_image(path, direction="vertical"):
            self._show_image(self._current_index)

    def _brightness_up(self) -> None:
        """Increase brightness by 10%."""
        from cios.skills.image_edit import adjust_image

        path = self._current_file_path()
        if path:
            adjust_image(path, brightness=1.1)
            self._show_image(self._current_index)

    def _brightness_down(self) -> None:
        """Decrease brightness by 10%."""
        from cios.skills.image_edit import adjust_image

        path = self._current_file_path()
        if path:
            adjust_image(path, brightness=0.9)
            self._show_image(self._current_index)

    def _share(self) -> None:
        """Share current image via xdg-open."""
        from cios.skills.image_edit import share_file

        path = self._current_file_path()
        if path:
            share_file(path)

    def _toggle_info(self) -> None:
        """Toggle EXIF info panel visibility."""
        self._info_visible = not self._info_visible

        if self._info_visible:
            self._show_info_panel()
        else:
            self._hide_info_panel()

    def _show_info_panel(self) -> None:
        """Show EXIF metadata panel on the right side."""
        from cios.skills.image_edit import format_metadata, get_metadata

        if self._info_frame and self._info_frame.winfo_exists():
            self._info_frame.destroy()

        path = self._current_file_path()
        if not path:
            return

        meta = get_metadata(path)
        if not meta:
            return

        self._info_frame = tk.Frame(self._overlay, bg=BG_CARD, padx=SP_COMPACT, pady=SP_COMPACT)
        self._info_frame.place(relx=1.0, rely=0.5, anchor="e", x=-SP_COMPACT)

        info_text = format_metadata(meta)
        info_label = tk.Label(
            self._info_frame,
            text=info_text,
            font=self._fonts.get("small", None),
            fg=FG_SEC,
            bg=BG_CARD,
            justify="left",
            anchor="nw",
        )
        info_label.pack()

    def _hide_info_panel(self) -> None:
        """Hide the info panel."""
        if self._info_frame and self._info_frame.winfo_exists():
            self._info_frame.destroy()
        self._info_frame = None

    def _current_file_path(self) -> str | None:
        """Get the file path of the currently displayed image."""
        if not self._files or self._current_index >= len(self._files):
            return None
        return self._files[self._current_index].get("path", "")

    def navigate(self, delta: int) -> None:
        """Move to next (+1) or previous (-1) image with wrapping."""
        if not self._files:
            return
        n = len(self._files)
        self._current_index = (self._current_index + delta) % n
        # Hide info panel on navigation (will show stale data otherwise)
        if self._info_visible:
            self._show_info_panel()
        self._show_image(self._current_index)
