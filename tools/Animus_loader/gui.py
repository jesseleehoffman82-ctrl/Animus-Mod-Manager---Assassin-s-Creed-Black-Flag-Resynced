"""Animus Mod & Outfit Manager - legacy desktop GUI for Assassin's Creed Black Flag Resynced.

AC Black Flag themed UI with:
  * Game folder detection
  * Mod management (install/uninstall)
  * Activity logging
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import DEFAULT_GAME_DIR, Loader, LoaderError
from .outfits import OutfitError
from .packs import PackError, PackManager
from .nexus import NexusClient, NexusError


class LoaderApp:
    #: Category labels for the OUTFITS / WEAPONS tabs.
    CATEGORY_LABELS = {
        "outfit": ("OUTFIT", "outfit", "IMPORTED OUTFITS"),
        "weapon": ("WEAPON", "weapon", "IMPORTED WEAPON SKINS"),
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Animus Mod & Outfit Manager")
        self.root.geometry("900x650")
        self.root.minsize(780, 550)
        
        # Theme colors
        self.COLOR_BG = "#0a0a0a"
        self.COLOR_PANEL = "#141414"
        self.COLOR_BORDER = "#c9a55c"
        self.COLOR_TEXT = "#e8e8e8"
        self.COLOR_TEXT_DIM = "#888888"
        self.COLOR_GREEN = "#4caf50"
        self.COLOR_RED = "#f44336"
        self.COLOR_GOLD = "#c9a55c"
        self.COLOR_HOVER = "#1a1a1a"
        
        # Style configuration
        self._configure_styles()
        
        self.loader = Loader(game_dir=DEFAULT_GAME_DIR)

        self._build_widgets()
        self.refresh_game_status()
        self.refresh_packages()
        self.refresh_texture_tabs()
    
    def _configure_styles(self) -> None:
        """Configure custom Tkinter styles for AC Black Flag theme."""
        style = ttk.Style()
        
        # Configure main window
        self.root.configure(bg=self.COLOR_BG)

        # Create custom styles
        style.theme_use('clam')

        # Base dark theme: every ttk widget defaults to the dark palette so
        # nothing shows as the light clam default (the "white boxes" bug).
        style.configure('.', background=self.COLOR_BG,
                        foreground=self.COLOR_TEXT)
        style.configure('TFrame', background=self.COLOR_BG)
        style.configure('TLabel', background=self.COLOR_BG,
                        foreground=self.COLOR_TEXT)
        style.configure('TLabelframe', background=self.COLOR_BG,
                        foreground=self.COLOR_GOLD)
        style.configure('TLabelframe.Label', background=self.COLOR_BG,
                        foreground=self.COLOR_GOLD)
        style.configure('TNotebook', background=self.COLOR_BG,
                        borderwidth=0)
        style.configure('TNotebook.Tab', background=self.COLOR_PANEL,
                        foreground=self.COLOR_TEXT, padding=(10, 5))
        style.map('TNotebook.Tab',
                  background=[('selected', self.COLOR_GOLD)],
                  foreground=[('selected', self.COLOR_BG)])
        style.configure('Treeview', background=self.COLOR_PANEL,
                        fieldbackground=self.COLOR_PANEL,
                        foreground=self.COLOR_TEXT,
                        rowheight=30,
                        font=('Segoe UI', 10))
        style.configure('Treeview.Heading', background='#1a1a1a',
                        foreground=self.COLOR_GOLD,
                        font=('Segoe UI', 9, 'bold'))
        style.map('Treeview', background=[('selected', '#1a2530')])
        style.configure('TButton', background='#2a2a2a',
                        foreground=self.COLOR_TEXT, padding=(8, 4))
        style.map('TButton',
                  background=[('active', '#3a3a3a')],
                  foreground=[('active', self.COLOR_TEXT)])
        style.configure('TEntry', background=self.COLOR_PANEL,
                        fieldbackground=self.COLOR_PANEL,
                        foreground=self.COLOR_TEXT)
        style.configure('Vertical.TScrollbar', background=self.COLOR_PANEL,
                        troughcolor=self.COLOR_BG)

        # Small variant for the compact CHECK UPDATES button.
        style.configure('SmallDark.TButton', background='#2a2a2a',
                        foreground=self.COLOR_TEXT, padding=(3, 1),
                        font=('Segoe UI', 8))
        style.map('SmallDark.TButton',
                  background=[('active', '#3a3a3a')],
                  foreground=[('active', self.COLOR_TEXT)])

        # Frame styles
        style.configure('TitleFrame.TFrame', background=self.COLOR_BG)
        style.configure('Panel.TFrame', background=self.COLOR_PANEL)
        style.configure('Panel.TLabelFrame', background=self.COLOR_PANEL)
        style.layout('Panel.TLabelFrame', style.layout('TLabelframe'))
        
        # Button styles
        style.configure('GoldButton.TButton', 
                       background=self.COLOR_GOLD,
                       foreground=self.COLOR_BG,
                       font=('Segoe UI', 9))
        style.configure('DarkButton.TButton',
                       background='#2a2a2a',
                       foreground=self.COLOR_TEXT,
                       font=('Segoe UI', 9))
        style.map('GoldButton.TButton',
                 background=[('active', '#d4b870')],
                 foreground=[('active', self.COLOR_BG)])
        style.map('DarkButton.TButton',
                 background=[('active', '#3a3a3a')],
                 foreground=[('active', self.COLOR_TEXT)])
        
        # Entry styles
        style.configure('GameEntry.TEntry', background=self.COLOR_PANEL,
                        foreground=self.COLOR_TEXT,
                        fieldbackground=self.COLOR_PANEL,
                        font=('Consolas', 10))
        
        # Treeview styles
        style.configure('ModTree.Treeview',
                        background=self.COLOR_PANEL,
                        foreground=self.COLOR_TEXT,
                        rowheight=32,
                        font=('Segoe UI', 10))
        style.configure('ModTree.Treeview.heading',
                        background='#1a1a1a',
                        foreground=self.COLOR_GOLD,
                        font=('Segoe UI', 9, 'bold'))
        style.map('ModTree.Treeview',
                 background=[('selected', '#1a2530')])
        
        # Label styles
        style.configure('SectionLabel.TLabel',
                        background=self.COLOR_PANEL,
                        foreground=self.COLOR_GOLD,
                        font=('Segoe UI', 10, 'bold'))
        style.configure('StatusLabel.TLabel',
                        background=self.COLOR_BG,
                        foreground=self.COLOR_TEXT_DIM,
                        font=('Segoe UI', 9))
        style.configure('GreenStatus.TLabel',
                        background=self.COLOR_BG,
                        foreground=self.COLOR_GREEN,
                        font=('Segoe UI', 9))
        
        # Text log styles
        style.configure('LogText.TText',
                       background=self.COLOR_PANEL,
                       foreground=self.COLOR_TEXT,
                       font=('Consolas', 9))

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_widgets(self) -> None:
        # Header section
        header_frame = ttk.Frame(self.root, padding=(15, 15, 15, 10))
        header_frame.pack(fill="x")

        # Title labels
        title_label = ttk.Label(header_frame,
                               text="ASSASSIN'S CREED BLACK FLAG RESYNCED",
                               font=('Segoe UI', 18, 'bold'),
                               foreground=self.COLOR_TEXT)
        title_label.pack(side="left")

        subtitle_label = ttk.Label(header_frame,
                                   text="ANIMUS MOD & OUTFIT MANAGER\nFOR ASSASSIN'S CREED BLACK FLAG RESYNCED",
                                   font=('Segoe UI', 10),
                                   foreground=self.COLOR_GOLD)
        subtitle_label.pack(side="left", padx=(15, 0), pady=(5, 0))

        # Game folder panel
        game_panel = ttk.LabelFrame(self.root, text="GAME FOLDER", padding=10, style='Panel.TLabelFrame')
        game_panel.pack(fill="x", padx=15, pady=(10, 10))

        game_inner = ttk.Frame(game_panel)
        game_inner.pack(fill="x")

        self.game_dir_var = tk.StringVar(value=str(self.loader.game_dir))
        self.game_dir_entry = ttk.Entry(game_inner,
                                       textvariable=self.game_dir_var,
                                       width=70,
                                       style='GameEntry.TEntry')
        self.game_dir_entry.pack(side="left", padx=(0, 10), fill="x", expand=True)

        browse_btn = ttk.Button(game_inner, text="BROWSE", style='DarkButton.TButton',
                               command=self.browse_game_dir)
        browse_btn.pack(side="left", padx=5)

        detect_btn = ttk.Button(game_inner, text="DETECT", style='DarkButton.TButton',
                               command=self.detect_game_dir)
        detect_btn.pack(side="left", padx=5)

        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(game_inner, textvariable=self.status_var,
                                      style='StatusLabel.TLabel')
        self.status_label.pack(side="left", padx=15)

        # Row: Notebook with the CHECK UPDATES button inline with the tab labels
        top_row = ttk.Frame(self.root, padding=(15, 0, 15, 8))
        top_row.pack(fill="x")
        top_row.columnconfigure(0, weight=1)

        # Notebook: MODS / OUTFITS / WEAPONS (fixed-height pane, not the whole app)
        nb_parent = ttk.Frame(top_row)
        nb_parent.grid(row=0, column=0, sticky="nsew")
        self.nb = ttk.Notebook(nb_parent, height=280)
        self.nb.pack(fill="both", expand=True)

        # Top controls — locked in place, inline with the tab labels (never moves)
        self.top_controls = ttk.Frame(nb_parent)
        self.top_controls.place(relx=0.5, rely=0.042, anchor="center")

        self.check_updates_btn = ttk.Button(self.top_controls,
                                            text="CHECK UPDATES",
                                            style='SmallDark.TButton',
                                            command=self.check_updates)
        self.check_updates_btn.pack(side="left", padx=(0, 10))

        ttk.Label(self.top_controls, text="Public Nexus metadata",
                  background=self.COLOR_BG, foreground=self.COLOR_TEXT,
                  font=('Segoe UI', 8)).pack(side="left")

        # ---- MODS tab ----
        mods_tab = ttk.Frame(self.nb)
        self.nb.add(mods_tab, text="MODS")
        self._build_mods_tab(mods_tab)

        # ---- OUTFITS / WEAPONS tabs (inline, no separate window) ----
        self.trees = {}
        self.tree_meta = {}
        self.apply_labels = {}
        self.tab_frames = {}
        self.manager = PackManager(game_dir=self.loader.game_dir,
                                   mods_root=self.loader.mods_root)
        for cat in ("outfit", "weapon"):
            frame = ttk.Frame(self.nb)
            self.nb.add(frame, text=f"{self.CATEGORY_LABELS[cat][0]}S")
            self.tab_frames[cat] = frame
            self._build_tab_frame(cat)

        # Activity log (shared) — expands at the bottom
        log_panel = ttk.LabelFrame(self.root, text="MOD ACTIVITY", padding=10, style='Panel.TLabelFrame')
        log_panel.pack(fill="both", expand=True, padx=15, pady=(10, 15))

        log_toolbar = ttk.Frame(log_panel)
        log_toolbar.pack(fill="x", pady=(0, 4))
        ttk.Label(log_toolbar, text="Install, apply, revert and update actions show here.",
                  background=self.COLOR_PANEL, foreground=self.COLOR_TEXT_DIM).pack(side="left")
        ttk.Button(log_toolbar, text="CLEAR", style='DarkButton.TButton',
                   command=self.clear_log).pack(side="right")

        self.log_text = tk.Text(log_panel, height=14, state="disabled",
                               bg=self.COLOR_PANEL, fg=self.COLOR_TEXT,
                               font=('Consolas', 9), relief="flat",
                               wrap="none",
                               highlightthickness=1, highlightbackground="#1a1a1a")
        self.log_text.pack(fill="both", expand=True, padx=0, pady=(0, 4))

        # scrollbar
        scroll = ttk.Scrollbar(log_panel, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)

        # Footer
        footer = ttk.Frame(self.root, padding=(15, 5, 15, 5))
        footer.pack(fill="x")

        footer_label = ttk.Label(footer, text="ANIMUS MOD & OUTFIT MANAGER v1.0.0",
                                font=('Segoe UI', 8), foreground=self.COLOR_TEXT_DIM)
        footer_label.pack(side="left")

    def _build_mods_tab(self, parent: ttk.Frame) -> None:
        """Build the main .jmod mod list inside the MODS tab."""
        btns = ttk.Frame(parent, padding=(10, 8, 10, 8))
        btns.pack(fill="x")
        self.install_mod_btn = ttk.Button(btns, text="INSTALL MOD",
                                          style='GoldButton.TButton',
                                          command=self.install_mod)
        self.install_mod_btn.pack(side="left", padx=(0, 10))
        ttk.Button(btns, text="REFRESH", style='DarkButton.TButton',
                   command=self.refresh_packages).pack(side="right")

        cols = ("enabled", "mod", "version", "author", "targets", "actions")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings",
                                 selectmode="browse", style='ModTree.Treeview')
        self.tree.heading("enabled", text="ENABLED")
        self.tree.heading("mod", text="MOD")
        self.tree.heading("version", text="VERSION")
        self.tree.heading("author", text="AUTHOR")
        self.tree.heading("targets", text="TARGETS")
        self.tree.heading("actions", text="")
        self.tree.column("enabled", width=60, anchor="center")
        self.tree.column("mod", width=320)
        self.tree.column("version", width=80, anchor="center")
        self.tree.column("author", width=200)
        self.tree.column("targets", width=60, anchor="center")
        self.tree.column("actions", width=50, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tree.bind("<Double-1>", self._on_tree_doubleclick)
        self.tree.bind("<ButtonRelease-1>", self._on_main_tree_click)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def log(self, message: str, tag: str = "info") -> None:
        """Append a line to the MOD ACTIVITY log.

        tag: "info" (normal), "ok" (green), "warn" (gold), "err" (red).
        """
        colors = {
            "info": self.COLOR_TEXT,
            "ok": self.COLOR_GREEN,
            "warn": self.COLOR_GOLD,
            "err": self.COLOR_RED,
        }
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] ")
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.configure(state="disabled")
        self.log_text.tag_configure(tag, foreground=colors.get(tag, self.COLOR_TEXT))
        self.log_text.see("end")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for widget in (self.install_mod_btn,):
            widget.configure(state=state)

    def _run_threaded(self, fn, *args, **kwargs):
        self.set_busy(True)

        def target():
            try:
                result = fn(*args, **kwargs)
                self.root.after(0, lambda: self._finish_ok(result))
            except (LoaderError, OSError) as exc:
                self.root.after(0, lambda: self._finish_err(str(exc)))
            except Exception as exc:  # pragma: no cover
                self.root.after(0, lambda: self._finish_err(f"Unexpected error: {exc}"))

        threading.Thread(target=target, daemon=True).start()

    def _finish_err(self, message: str) -> None:
        self.set_busy(False)
        self.log(f"ERROR: {message}", "err")
        messagebox.showerror("Animus Mod & Outfit Manager", message)

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def browse_game_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(self.loader.game_dir))
        if chosen:
            self.loader.game_dir = Path(chosen)
            self.game_dir_var.set(chosen)
            self.refresh_game_status()

    def detect_game_dir(self) -> None:
        self.loader = Loader(game_dir=DEFAULT_GAME_DIR)
        self.game_dir_var.set(str(self.loader.game_dir))
        self.refresh_game_status()
        self.log(f"Detected game folder: {self.loader.game_dir}")

    def refresh_game_status(self) -> None:
        game_dir = self.loader.game_dir
        exe = game_dir / "ACBlackFlag.exe"
        if exe.is_file():
            self.status_var.set("Game found")
            self.status_label.configure(style='GreenStatus.TLabel')
            self.root.title(f"Animus Mod & Outfit Manager - {game_dir}")
        else:
            self.status_var.set("Game NOT found - choose folder")
            self.status_label.configure(style='StatusLabel.TLabel')

    def _finish_ok(self, result) -> None:
        self.set_busy(False)
        self.log(f"{result if result is not None else 'done'}", "ok")
        self.refresh_game_status()
        self.refresh_packages()
    
    def refresh_packages(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        installed = {r.name: r for r in self.loader.list_installed()}
        
        for path in self.loader.discover_packages():
            try:
                pkg = self.loader.read_package(path)
            except LoaderError as exc:
                self.tree.insert("", "end", values=("", "INVALID", str(exc), "-", 0, ""))
                continue
            
            record = installed.get(pkg.name)
            enabled = bool(record and record.enabled)
            on = "Y" if enabled else ""
            self.tree.insert(
                "",
                "end",
                values=(on, pkg.name, pkg.version, pkg.author, len(pkg.targets), ""),
                tags=(str(enabled).lower(),)
            )

    def _selected_item(self) -> tuple | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Animus Mod & Outfit Manager", "Select a mod first.")
            return None
        return self.tree.item(selection[0])
    
    def _selected_name(self) -> str | None:
        item = self._selected_item()
        if not item or not item['values']:
            return None
        return item['values'][1]
    
    def _selected_path(self) -> Path | None:
        name = self._selected_name()
        if not name:
            return None
        for path in self.loader.discover_packages():
            try:
                pkg = self.loader.read_package(path)
            except LoaderError:
                continue
            if pkg.name == name:
                return path
        return None
    
    def toggle_enabled(self, item_id: str) -> None:
        tags = self.tree.item(item_id, 'tags')
        enabled = tags[0] == 'true' if tags else False
        
        if enabled:
            self.disable_selected()
        else:
            self.enable_selected()
    
    def enable_selected(self) -> None:
        path = self._selected_path()
        if path:
            self._run_threaded(self._do_enable, path)
    
    def _do_enable(self, path: Path):
        pkg = self.loader.read_package(path)
        backups = self.loader.apply(path, priority=0)
        targets = ", ".join(f"{t.forge}@{t.resource_id:#X}" for t in pkg.targets[:3])
        detail = f"; {targets}" if targets else ""
        return f"Enabled '{pkg.name} v{pkg.version}' — {len(backups)} target(s) patched{detail}"
    
    def disable_selected(self) -> None:
        name = self._selected_name()
        if name:
            self._run_threaded(self._do_disable, name)
    
    def _do_disable(self, name: str):
        restored = self.loader.remove(name)
        return f"Disabled {name}; restored {len(restored)} file(s)"
    
    def install_mod(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Install Mod",
            filetypes=[("Jackdaw Mod Package", "*.jmod"), ("All Files", "*.*")]
        )
        if chosen:
            self._run_threaded(self._do_install, Path(chosen))
    
    def _do_install(self, path: Path):
        pkg = self.loader.read_package(path)
        backups = self.loader.apply(path, priority=0)
        return f"Installed '{pkg.name} v{pkg.version}' — {len(backups)} target(s) patched"
    
    def uninstall_mod(self) -> None:
        name = self._selected_name()
        if name:
            self._run_threaded(self._do_uninstall, name)
    
    def _do_uninstall(self, name: str):
        restored = self.loader.remove(name)
        return f"Uninstalled {name}; restored {len(restored)} file(s)"
    
    def _on_tree_doubleclick(self, event) -> None:
        """Handle double-click on tree item to toggle enabled state."""
        item = self.tree.identify_row(event.y)
        if item:
            self.toggle_enabled(item)
    
    def _on_action_click(self, item_id: str) -> None:
        """Handle click on the '...' column to uninstall."""
        name = self._selected_name()
        if name and messagebox.askyesno("Uninstall Mod", f"Uninstall {name}?"):
            self._run_threaded(self._do_uninstall, name)

    def _on_main_tree_click(self, event) -> None:
        """Click on ENABLED column toggles a mod; click on '...' column uninstalls."""
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col == "#1":
            item = self.tree.identify_row(event.y)
            if item:
                self.toggle_enabled(item)
        elif col == "#6":
            item = self.tree.identify_row(event.y)
            if item:
                self._on_action_click(item)

    def select_tab(self, cat: str) -> None:
        """Switch the notebook to a named tab (outfit | weapon | mods)."""
        if cat == "mods":
            tab = self.nb.tabs()[0]
        else:
            tab = self.tab_frames.get(cat)
        if tab:
            self.nb.select(tab)

    def check_updates(self) -> None:
        """Check all mods/packs that have a Nexus id (threaded)."""
        self.log("Checking public Nexus metadata for updates...")
        import threading
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _check_updates_worker(self) -> None:
        try:
            client = NexusClient()
            mod_results = self.loader.check_updates(client=client)
            pack_results = self.manager.check_updates(client=client)
        except Exception as exc:  # pragma: no cover
            self.root.after(0, lambda: self.log(f"Update check failed: {exc}"))
            return
        self.root.after(0, lambda: self._render_updates(mod_results, pack_results))

    def _render_updates(self, mod_results: list, pack_results: list) -> None:
        for r in mod_results:
            if r.get("error"):
                self.log(f"[mod] {r['name']}: {r['error']}", "err")
            elif r.get("mod_id") is None:
                pass
            elif r.get("has_update"):
                self.log(f"UPDATE [mod] {r['name']}: {r.get('current') or '?'} -> {r['latest']}  (nexus {r['mod_id']})", "warn")
            else:
                self.log(f"     [mod] {r['name']}: latest {r.get('latest')}")
        for r in pack_results:
            if r.get("error"):
                self.log(f"[{r.get('category')}] {r['name']}: {r['error']}", "err")
            elif r.get("mod_id") is None:
                pass
            elif r.get("has_update"):
                self.log(f"UPDATE [{r.get('category')}] {r['name']}: {r.get('current') or '?'} -> {r['latest']}  (nexus {r['mod_id']})", "warn")
            else:
                self.log(f"     [{r.get('category')}] {r['name']}: latest {r.get('latest')}")
        self.log("Update check finished.", "ok")

    # ------------------------------------------------------------------ #
    # OUTFITS / WEAPONS tabs (inline in main window)
    # ------------------------------------------------------------------ #
    def _build_tab_frame(self, cat: str) -> None:
        frame = self.tab_frames[cat]
        label, item, panel_text = self.CATEGORY_LABELS[cat]
        btns = ttk.Frame(frame, padding=(10, 8, 10, 8))
        btns.pack(fill="x")
        ttk.Button(btns, text=f"INSTALL {label} PACK", style='GoldButton.TButton',
                   command=lambda c=cat: self.install_pack(c)).pack(side="left", padx=(0, 10))
        ttk.Button(btns, text="APPLY CHANGES", style='GoldButton.TButton',
                   command=lambda c=cat: self.apply_changes(c)).pack(side="left", padx=(0, 10))
        ttk.Button(btns, text="RESTORE TO VANILLA", style='DarkButton.TButton',
                   command=self.revert_textures).pack(side="left", padx=(0, 10))
        ttk.Button(btns, text="REVERT SELECTED", style='DarkButton.TButton',
                   command=lambda c=cat: self.revert_pack(c)).pack(side="left", padx=(0, 10))
        self.apply_labels[cat] = tb = ttk.Label(btns, text="")
        tb.pack(side="left", padx=(10, 0))

        panel = ttk.LabelFrame(frame, text=panel_text, padding=10)
        panel.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        cols = ("enabled", "name", "slots", "order")
        tree = ttk.Treeview(panel, columns=cols, show="headings", selectmode="browse")
        tree.heading("enabled", text="ON")
        tree.heading("name", text="NAME")
        tree.heading("slots", text="SLOTS")
        tree.heading("order", text="PRIORITY (bottom wins)")
        tree.column("enabled", width=46, anchor="center")
        tree.column("name", width=320)
        tree.column("slots", width=60, anchor="center")
        tree.column("order", width=60, anchor="center")
        tree.pack(fill="both", expand=True)
        tree.bind("<ButtonRelease-1>", lambda e, c=cat: self._on_pack_tree_click(e, c))

        reord = ttk.Frame(frame, padding=(10, 0, 10, 8))
        reord.pack(fill="x")
        ttk.Button(reord, text="MOVE UP (lower priority)", style='DarkButton.TButton',
                   command=lambda c=cat: self.move_pack(c, up=False)).pack(side="left", padx=(0, 10))
        ttk.Button(reord, text="MOVE DOWN (higher priority)", style='DarkButton.TButton',
                   command=lambda c=cat: self.move_pack(c, up=True)).pack(side="left")
        self.trees[cat] = tree
        self.tree_meta[cat] = {}

    def _refresh_tree_meta(self, cat: str) -> None:
        tree = self.trees[cat]
        self.tree_meta[cat] = {}
        for item_id in tree.get_children():
            self.tree_meta[cat][item_id] = tree.item(item_id, "values")

    def _cat_label(self, cat: str, upper: bool = True) -> str:
        label, item, _ = self.CATEGORY_LABELS[cat]
        return label if upper else item

    def _update_apply_label(self, cat: str) -> None:
        if cat not in self.apply_labels:
            return
        staged = len(self.manager._staged(cat))
        self.apply_labels[cat].configure(
            text=f"  {staged} enabled  |  bottom-most wins on overlap",
            foreground=self.COLOR_TEXT)

    def refresh_texture_tabs(self) -> None:
        for cat, tree in self.trees.items():
            for item_id in tree.get_children():
                tree.delete(item_id)
            staged = set(self.manager._staged(cat))
            order = [p.id for p in self.manager.list_packs(category=cat)]
            for pack in self.manager.list_packs(category=cat):
                pos = order.index(pack.id) + 1
                on = "Y" if pack.id in staged else ""
                tree.insert("", "end", values=(on, pack.name, len(pack.slots), pos))
            self._refresh_tree_meta(cat)
            self._update_apply_label(cat)

    def _selected_pack_name(self, cat: str):
        sel = self.trees[cat].selection()
        if not sel:
            return None
        return self.trees[cat].item(sel[0], "values")[1]

    def _selected_pack_id(self, cat: str):
        name = self._selected_pack_name(cat)
        if not name:
            messagebox.showinfo("Animus Mod & Outfit Manager",
                                f"Select a pack in the {self._cat_label(cat)} tab first.")
            return None
        for pack in self.manager.list_packs(category=cat):
            if pack.name == name:
                return pack.id
        return None

    def install_pack(self, cat: str) -> None:
        chosen = filedialog.askopenfilename(
            title=f"Select {self._cat_label(cat, False)} pack (zip/folder of textures)",
            filetypes=[
                ("Pack archive", "*.zip *.7z *.tar *.tgz"),
                ("Texture", "*.dds *.png"),
                ("All Files", "*.*"),
            ])
        if not chosen:
            return
        try:
            pack = self.manager.install(Path(chosen), category=cat)
        except PackError as exc:
            messagebox.showerror("Animus Mod & Outfit Manager", str(exc))
            return
        self.log(f"INSTALLED '{pack['pack'].name}' ({len(pack['pack'].slots)} slot(s)). "
                 f"Enabled + applied.", "ok")
        self.refresh_texture_tabs()

    def toggle_pack(self, cat: str, pack_id: str) -> None:
        staged = set(self.manager._staged(cat))
        self.manager.set_enabled(pack_id, pack_id not in staged)
        self.refresh_texture_tabs()

    def _on_pack_tree_click(self, event, cat: str) -> None:
        tree = self.trees[cat]
        region = tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        item = tree.identify_row(event.y)
        if not item:
            return
        if tree.identify_column(event.x) != "#1":
            return
        name = tree.item(item, "values")[1]
        for pack in self.manager.list_packs(category=cat):
            if pack.name == name:
                self.toggle_pack(cat, pack.id)
                return

    def move_pack(self, cat: str, up: bool) -> None:
        name = self._selected_pack_name(cat)
        if not name:
            return
        ordered = [p.id for p in self.manager.list_packs(category=cat)]
        ids = [p.id for p in self.manager.list_packs(category=cat)]
        idx = [i for i, p in enumerate(self.manager.list_packs(category=cat)) if p.name == name]
        if not idx:
            return
        i = idx[0]
        j = i + 1 if up else i - 1
        if not (0 <= j < len(ordered)):
            return
        ordered[i], ordered[j] = ordered[j], ordered[i]
        self.manager.set_order(cat, ordered)
        self.refresh_texture_tabs()

    def apply_changes(self, cat: str) -> None:
        try:
            result = self.manager.apply_staged(cat)
        except PackError as exc:
            messagebox.showerror("Animus Mod & Outfit Manager", str(exc))
            return
        if result.get("packs"):
            n = len(result["packs"])
            self.log(f"APPLIED {n} enabled {self._cat_label(cat, False)} pack(s) "
                     f"({result['external_mips']} mips, {result['materials']} materials).", "ok")
            for c in result.get("conflicts", []):
                self.log(f"  CONFLICT slot {c['slot']}: '{c['loser']}' overridden by "
                         f"'{c['winner']}' (lower in list).", "warn")
        else:
            self.log(f"No enabled {self._cat_label(cat, False)} packs to apply.")
        self.refresh_texture_tabs()

    def revert_textures(self) -> None:
        if not messagebox.askyesno("Animus Mod & Outfit Manager",
                                   "Revert the active texture pack back to vanilla?"):
            return
        try:
            result = self.manager.revert_all()
        except (PackError, OSError) as exc:
            messagebox.showerror("Animus Mod & Outfit Manager", str(exc))
            return
        self.log(f"Reverted {result['reverted']} write(s) to vanilla.", "ok")
        self.refresh_texture_tabs()

    def revert_pack(self, cat: str) -> None:
        """Revert the selected pack of a tab back to vanilla."""
        pack_id = self._selected_pack_id(cat)
        if not pack_id:
            return
        pack = self.manager.get_pack(pack_id)
        if not messagebox.askyesno("Animus Mod & Outfit Manager",
                                   f"Revert '{pack.name}' back to vanilla?"):
            return
        try:
            result = self.manager.revert_pack(pack_id)
        except (PackError, OSError) as exc:
            messagebox.showerror("Animus Mod & Outfit Manager", str(exc))
            return
        self.log(f"Reverted '{pack.name}' ({result['reverted']} write(s)).", "ok")
        for issue in result.get("issues", []):
            if issue and issue != "no journal":
                self.log(f"  NOTE: {issue}", "warn")
        self.refresh_texture_tabs()



def main(argv: list[str] | None = None) -> int:
    root = tk.Tk()
    LoaderApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
