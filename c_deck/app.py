from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path

import flet as ft

from .models import (
    CommandEntry,
    extract_variables,
    format_paris_datetime,
    is_dangerous_command,
    merge_variables_from_defaults,
    normalize_tags,
    normalize_variable_defaults,
    normalize_variables,
    render_command_template,
)
from . import __author__, __version__
from .storage import CommandStore, default_data_path

APP_TITLE = "C-Deck"
ALL_CATEGORIES = "Toutes"
ALL_TAGS = "Tous"
MAX_VARIABLES = 5
MAX_RECENT_VALUES = 5
SHORTCUTS = (
    ("Ctrl+F", "Aller dans la recherche"),
    ("↑ / ↓", "Commande précédente / suivante"),
    ("Ctrl+C", "Copier la commande sélectionnée"),
    ("Ctrl+N", "Nouvelle commande"),
    ("Ctrl+S", "Enregistrer"),
    ("Échap", "Annuler les modifications / fermer la fenêtre"),
    ("F1", "Afficher les raccourcis"),
)
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
APP_ICON_ICO_PATH = ASSETS_DIR / "c-deck-icon.ico"
APP_ICON_PNG_PATH = ASSETS_DIR / "c-deck-icon.png"


class CDeckApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.store = CommandStore()
        self.commands = self.store.load()
        self.startup_message = self.store.recovery_message
        self.selected_id: str | None = self.commands[0].id if self.commands else None
        self.category_filter = ALL_CATEGORIES
        self.tag_filter = ALL_TAGS
        self.query = ""
        self.scope_filter = "all"
        self.theme_mode_value = self.store.get_setting("theme_mode", "light")
        self.view_mode_value = self.store.get_setting("view_mode", "detailed")
        self.active_dialog: ft.AlertDialog | None = None
        self.editor_snapshot: dict[str, object] = {}
        self.focused_control: ft.Control | None = None

        self.import_picker = ft.FilePicker(on_result=self.on_import_result)
        self.export_picker = ft.FilePicker(on_result=self.on_export_result)
        self.clipboard = ft.Clipboard() if hasattr(ft, "Clipboard") else None
        self.register_service(self.import_picker)
        self.register_service(self.export_picker)
        if self.clipboard is not None:
            self.register_service(self.clipboard)

        self.search_field = ft.TextField(
            hint_text="Rechercher une commande, un tag, une catégorie... (Ctrl+F)",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            filled=True,
            border_radius=8,
            autofocus=True,
            expand=True,
            on_change=self.on_search_change,
        )
        self.category_dropdown = ft.Dropdown(
            label="Catégorie",
            dense=True,
            border_radius=8,
            on_select=self.on_category_change,
        )
        self.tag_dropdown = ft.Dropdown(
            label="Tag",
            dense=True,
            border_radius=8,
            on_select=self.on_tag_change,
        )
        self.list_view = ft.ListView(expand=True, spacing=8, padding=0)
        self.category_list = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
        self.status_text = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.stats_text = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.theme_button = ft.IconButton(
            tooltip="Mode sombre",
            on_click=self.toggle_theme,
        )
        self.view_button = ft.IconButton(
            tooltip="Vue compacte",
            on_click=self.toggle_view_mode,
        )
        self.scope_buttons = ft.Row(spacing=6, wrap=True)

        self.title_field = ft.TextField(label="Titre", dense=True, border_radius=8)
        self.command_field = ft.TextField(
            label="Commande",
            multiline=True,
            min_lines=5,
            max_lines=10,
            border_radius=8,
        )
        self.editor_category_field = ft.Dropdown(
            label="Catégorie",
            dense=True,
            border_radius=8,
            editable=True,
            enable_filter=True,
            enable_search=True,
        )
        self.tags_field = ft.TextField(
            label="Tags",
            hint_text="linux, moodle, maintenance",
            dense=True,
            border_radius=8,
        )
        self.variables_field = ft.TextField(
            label=f"Variables max {MAX_VARIABLES}",
            hint_text="class_task, course_id",
            dense=True,
            border_radius=8,
        )
        self.variable_defaults_field = ft.TextField(
            label="Valeurs par défaut",
            hint_text=r"class_task=local_dashboard_eticeo\task\send_info",
            dense=True,
            border_radius=8,
        )
        self.notes_field = ft.TextField(
            label="Notes",
            multiline=True,
            min_lines=3,
            max_lines=6,
            border_radius=8,
        )
        self.favorite_checkbox = ft.Checkbox(label="Favori", value=False)
        self.confirm_before_copy_checkbox = ft.Checkbox(label="Confirmation avant copie", value=False)

        self.editor_title = ft.Text("Commande", size=20, weight=ft.FontWeight.BOLD)
        self.copy_button = ft.IconButton(
            icon=ft.Icons.CONTENT_COPY,
            tooltip="Copier (Ctrl+C)",
            on_click=self.copy_selected_command,
        )
        self.duplicate_button = ft.IconButton(
            icon=ft.Icons.FILE_COPY_OUTLINED,
            tooltip="Dupliquer",
            on_click=self.duplicate_selected_command,
        )
        self.delete_button = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            tooltip="Supprimer",
            icon_color=ft.Colors.ERROR,
            on_click=self.confirm_delete,
        )

        # Track text focus so list shortcuts (Ctrl+C, arrows) don't hijack editing.
        for control in (
            self.search_field,
            self.title_field,
            self.command_field,
            self.tags_field,
            self.variables_field,
            self.variable_defaults_field,
            self.notes_field,
            self.editor_category_field,
        ):
            control.on_focus = self.on_field_focus
            control.on_blur = self.on_field_blur
        self.page.on_keyboard_event = self.on_keyboard

        self.build_page()
        self.refresh_all()
        if self.startup_message:
            self.show_message(self.startup_message)

    def build_page(self) -> None:
        self.page.title = APP_TITLE
        if hasattr(self.page, "window"):
            self.page.window.width = 1180
            self.page.window.height = 760
            self.page.window.min_width = 940
            self.page.window.min_height = 620
            if APP_ICON_ICO_PATH.exists():
                self.page.window.icon = str(APP_ICON_ICO_PATH)
            elif APP_ICON_PNG_PATH.exists():
                self.page.window.icon = str(APP_ICON_PNG_PATH)
        else:
            self.page.window_width = 1180
            self.page.window_height = 760
        self.apply_theme()
        self.apply_view_mode()
        self.page.theme = ft.Theme(
            color_scheme_seed="#2563eb",
            visual_density=ft.VisualDensity.COMPACT,
        )
        self.page.dark_theme = ft.Theme(
            color_scheme_seed="#38bdf8",
            visual_density=ft.VisualDensity.COMPACT,
        )
        self.page.padding = 0

        sidebar = ft.Container(
            width=196,
            padding=ft.Padding(left=14, top=16, right=14, bottom=12),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=34,
                                height=34,
                                border_radius=8,
                                bgcolor=ft.Colors.PRIMARY_CONTAINER,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.TERMINAL, size=20, color=ft.Colors.ON_PRIMARY_CONTAINER),
                            ),
                            ft.Column(
                                [
                                    ft.Text(APP_TITLE, size=19, weight=ft.FontWeight.BOLD),
                                    ft.Text(f"v{__version__}", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                                ],
                                spacing=0,
                                tight=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.FilledButton(
                        "Nouvelle",
                        icon=ft.Icons.ADD,
                        tooltip="Nouvelle commande (Ctrl+N)",
                        expand=False,
                        on_click=self.new_command,
                    ),
                    ft.Row(
                        [
                            ft.IconButton(icon=ft.Icons.UPLOAD_FILE, tooltip="Importer JSON", on_click=self.pick_import_file),
                            ft.IconButton(icon=ft.Icons.DOWNLOAD, tooltip="Exporter JSON", on_click=self.pick_export_file),
                            ft.IconButton(
                                icon=ft.Icons.FOLDER_OPEN,
                                tooltip=str(default_data_path()),
                                on_click=lambda _: self.show_message(str(default_data_path())),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=10),
                    ft.Text("Catégories", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE_VARIANT),
                    self.category_list,
                    ft.Divider(height=10),
                    ft.Row(
                        [
                            self.theme_button,
                            self.view_button,
                            ft.IconButton(icon=ft.Icons.KEYBOARD, tooltip="Raccourcis (F1)", on_click=self.open_shortcuts_dialog),
                            ft.IconButton(icon=ft.Icons.INFO_OUTLINE, tooltip="À propos", on_click=self.open_about_dialog),
                            ft.Container(expand=True),
                        ],
                        spacing=2,
                    ),
                    self.status_text,
                ],
                spacing=10,
                expand=True,
            ),
        )

        self.category_dropdown.width = 210
        self.tag_dropdown.width = 170
        self.editor_category_field.expand = True
        self.tags_field.expand = True

        middle = ft.Container(
            expand=True,
            padding=ft.Padding(left=18, top=16, right=18, bottom=16),
            bgcolor=ft.Colors.SURFACE,
            content=ft.Column(
                [
                    ft.Row([self.search_field], spacing=10),
                    ft.Row(
                        [
                            self.scope_buttons,
                            ft.Container(expand=True),
                            self.category_dropdown,
                            self.tag_dropdown,
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.stats_text,
                    self.list_view,
                ],
                spacing=10,
            ),
        )

        editor = ft.Container(
            width=392,
            padding=ft.Padding(left=16, top=16, right=16, bottom=16),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.EDIT_NOTE, size=22, color=ft.Colors.PRIMARY),
                            self.editor_title,
                            ft.Container(expand=True),
                            self.copy_button,
                            self.duplicate_button,
                            self.delete_button,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        spacing=8,
                    ),
                    ft.Divider(height=10),
                    self.title_field,
                    self.command_field,
                    ft.Row([self.editor_category_field, self.tags_field], spacing=10),
                    self.variables_field,
                    self.variable_defaults_field,
                    self.notes_field,
                    ft.Row([self.favorite_checkbox, self.confirm_before_copy_checkbox], wrap=True, spacing=10),
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Annuler", icon=ft.Icons.CLOSE, tooltip="Annuler (Échap)", on_click=self.cancel_edit
                            ),
                            ft.FilledButton(
                                "Enregistrer", icon=ft.Icons.SAVE, tooltip="Enregistrer (Ctrl+S)", on_click=self.save_command
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

        self.page.add(ft.Row([sidebar, middle, editor], expand=True, spacing=0))

    def refresh_all(self, refill_editor: bool = True) -> None:
        self.refresh_filters()
        self.refresh_scope_controls()
        self.refresh_sidebar()
        self.refresh_stats()
        self.refresh_list()
        if refill_editor:
            self.fill_editor(self.store.get(self.selected_id))
        self.status_text.value = f"{len(self.commands)} commandes"
        self.status_text.tooltip = str(default_data_path())
        self.page.update()

    def refresh_scope_controls(self) -> None:
        options = [
            ("all", "Toutes"),
            ("favorites", "Favoris"),
            ("recent", "Récentes"),
            ("top", "Top"),
        ]
        controls = []
        for value, label in options:
            button_class = ft.FilledButton if self.scope_filter == value else ft.OutlinedButton
            controls.append(button_class(label, data=value, on_click=self.on_scope_change))
        self.scope_buttons.controls = controls

    def refresh_stats(self) -> None:
        favorites = sum(1 for command in self.commands if command.favorite)
        dangerous = sum(1 for command in self.commands if command.confirm_before_copy)
        used = sum(1 for command in self.commands if command.use_count > 0)
        total_uses = sum(command.use_count for command in self.commands)
        top = max(self.commands, key=lambda command: command.use_count, default=None)
        top_label = f" • Top: {top.title} ({top.use_count})" if top and top.use_count else ""
        self.stats_text.value = (
            f"{len(self.commands)} commandes • {favorites} favoris • {dangerous} sensibles • "
            f"{used} déjà utilisées • {total_uses} copies"
            f"{top_label}"
        )

    def refresh_filters(self) -> None:
        command_categories = sorted({command.category for command in self.commands} | {"General"}, key=str.lower)
        categories = [ALL_CATEGORIES] + command_categories
        tags = [ALL_TAGS] + sorted({tag for command in self.commands for tag in command.tags}, key=str.lower)

        if self.category_filter not in categories:
            self.category_filter = ALL_CATEGORIES
        if self.tag_filter not in tags:
            self.tag_filter = ALL_TAGS

        self.category_dropdown.options = [ft.dropdown.Option(category) for category in categories]
        self.category_dropdown.value = self.category_filter
        self.editor_category_field.options = [ft.dropdown.Option(category) for category in command_categories]
        self.tag_dropdown.options = [ft.dropdown.Option(tag) for tag in tags]
        self.tag_dropdown.value = self.tag_filter

    def refresh_sidebar(self) -> None:
        counts: dict[str, int] = {ALL_CATEGORIES: len(self.commands)}
        for command in self.commands:
            counts[command.category] = counts.get(command.category, 0) + 1

        controls = []
        for category, count in sorted(counts.items(), key=lambda item: (item[0] != ALL_CATEGORIES, item[0].lower())):
            selected = category == self.category_filter
            controls.append(
                ft.Container(
                    border_radius=8,
                    padding=ft.Padding(left=10, top=8, right=10, bottom=8),
                    bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else None,
                    ink=True,
                    on_click=lambda _, value=category: self.set_category_filter(value),
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.FOLDER, size=16),
                            ft.Text(category, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(str(count), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=8,
                    ),
                )
            )
        self.category_list.controls = controls

    def refresh_list(self) -> None:
        visible = self.filtered_commands()
        self.list_view.controls = self.build_list_controls(visible)
        if not visible:
            self.list_view.controls = [
                ft.Container(
                    padding=22,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text("Aucune commande trouvée.", color=ft.Colors.ON_SURFACE_VARIANT),
                )
            ]

    def build_list_controls(self, commands: list[CommandEntry]) -> list[ft.Control]:
        if self.scope_filter != "all" or self.query or self.category_filter != ALL_CATEGORIES or self.tag_filter != ALL_TAGS:
            return [self.command_tile(command) for command in commands]

        favorites = [command for command in commands if command.favorite]
        others = [command for command in commands if not command.favorite]
        controls: list[ft.Control] = []
        if favorites:
            controls.append(self.section_header("Favoris"))
            controls.extend(self.command_tile(command) for command in favorites)
        if others:
            controls.append(self.section_header("Commandes"))
            controls.extend(self.command_tile(command) for command in others)
        return controls

    def section_header(self, title: str) -> ft.Control:
        return ft.Container(
            padding=ft.Padding(left=4, top=8, right=4, bottom=4),
            content=ft.Text(title, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE_VARIANT),
        )

    def metadata_pill(self, text: str, icon: str | None = None, danger: bool = False) -> ft.Control:
        controls: list[ft.Control] = []
        if icon:
            controls.append(ft.Icon(icon, size=13, color=ft.Colors.ERROR if danger else ft.Colors.ON_SURFACE_VARIANT))
        controls.append(
            ft.Text(
                text,
                size=11,
                color=ft.Colors.ERROR if danger else ft.Colors.ON_SURFACE_VARIANT,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
        return ft.Container(
            border_radius=999,
            padding=ft.Padding(left=8, top=4, right=8, bottom=4),
            bgcolor=ft.Colors.ERROR_CONTAINER if danger else ft.Colors.SURFACE_CONTAINER_LOW,
            content=ft.Row(controls, spacing=4, tight=True),
        )

    def filtered_commands(self) -> list[CommandEntry]:
        commands = [
            command
            for command in self.commands
            if command.matches(
                self.query,
                None if self.category_filter == ALL_CATEGORIES else self.category_filter,
                None if self.tag_filter == ALL_TAGS else self.tag_filter,
            )
        ]
        if self.scope_filter == "favorites":
            commands = [command for command in commands if command.favorite]
        elif self.scope_filter == "recent":
            commands = [command for command in commands if command.last_used_at]
        elif self.scope_filter == "top":
            commands = [command for command in commands if command.use_count > 0]

        if self.scope_filter == "recent":
            return sorted(commands, key=lambda item: item.last_used_at or "", reverse=True)
        if self.scope_filter == "top":
            return sorted(commands, key=lambda item: (item.use_count, item.last_used_at or ""), reverse=True)
        return sorted(
            commands,
            key=lambda item: (not item.favorite, -item.use_count, item.category.lower(), item.title.lower()),
        )

    def command_tile(self, command: CommandEntry) -> ft.Control:
        selected = command.id == self.selected_id
        compact = self.view_mode_value == "compact"
        tag_controls = [self.metadata_pill(tag, ft.Icons.TAG) for tag in command.tags[:4]]
        meta_controls = [
            self.metadata_pill(command.category, ft.Icons.FOLDER),
            self.metadata_pill(f"{command.use_count} copie(s)", ft.Icons.CONTENT_COPY),
        ]
        if command.last_used_at:
            meta_controls.append(
                self.metadata_pill(format_paris_datetime(command.last_used_at), ft.Icons.SCHEDULE)
            )
        if command.variables:
            meta_controls.append(self.metadata_pill(f"{len(command.variables)} variable(s)", ft.Icons.DATA_OBJECT))
        if command.confirm_before_copy:
            meta_controls.append(self.metadata_pill("sensible", ft.Icons.WARNING, danger=True))
        leading_icon = ft.Icons.TERMINAL
        favorite_icon = ft.Icons.STAR if command.favorite else ft.Icons.STAR_BORDER
        favorite_tooltip = "Retirer des favoris" if command.favorite else "Mettre en favori"
        favorite_color = ft.Colors.AMBER if command.favorite else ft.Colors.ON_SURFACE_VARIANT
        command_preview = ft.Text(
            command.command.replace("\n", " "),
            size=12,
            font_family="Consolas",
            color=ft.Colors.ON_SURFACE_VARIANT,
            max_lines=1 if compact else 2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        return ft.Container(
            key=ft.ScrollKey(command.id),
            border_radius=8,
            bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else ft.Colors.SURFACE,
            border=ft.Border(
                left=ft.BorderSide(1, ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT),
                top=ft.BorderSide(1, ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT),
                right=ft.BorderSide(1, ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT),
                bottom=ft.BorderSide(1, ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT),
            ),
            padding=8 if compact else 12,
            ink=True,
            data=command.id,
            on_click=self.on_tile_click,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(leading_icon, size=17, color=ft.Colors.PRIMARY),
                            ft.Text(command.title, weight=ft.FontWeight.BOLD, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.IconButton(
                                icon=favorite_icon,
                                tooltip=favorite_tooltip,
                                icon_size=18,
                                icon_color=favorite_color,
                                data=command.id,
                                on_click=self.toggle_favorite_from_tile,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CONTENT_COPY,
                                tooltip="Copier",
                                icon_size=18,
                                data=command.id,
                                on_click=self.copy_command_from_tile,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Container(
                        border_radius=6,
                        padding=ft.Padding(left=8, top=7, right=8, bottom=7),
                        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                        content=command_preview,
                    ),
                    ft.Row(meta_controls, spacing=10, wrap=True) if not compact else ft.Container(height=0),
                    ft.Row(tag_controls, spacing=6, wrap=True) if tag_controls and not compact else ft.Container(height=0),
                ],
                spacing=5 if compact else 8,
            ),
        )

    def fill_editor(self, command: CommandEntry | None) -> None:
        self.editor_title.value = "Nouvelle commande" if command is None else "Commande"
        self.copy_button.disabled = command is None
        self.duplicate_button.disabled = command is None
        self.delete_button.disabled = command is None
        self.title_field.value = command.title if command else ""
        self.command_field.value = command.command if command else ""
        editor_category = command.category if command else "General"
        self.editor_category_field.value = editor_category
        self.editor_category_field.text = editor_category
        self.tags_field.value = ", ".join(command.tags) if command else ""
        self.variables_field.value = ", ".join(command.variables) if command else ""
        self.variable_defaults_field.value = self.format_variable_defaults(command.variable_defaults) if command else ""
        self.notes_field.value = command.notes if command else ""
        self.favorite_checkbox.value = command.favorite if command else False
        self.confirm_before_copy_checkbox.value = command.confirm_before_copy if command else False
        self.editor_snapshot = self.editor_state()

    def editor_state(self) -> dict[str, object]:
        return {
            "title": self.title_field.value or "",
            "command": self.command_field.value or "",
            "category": self.editor_category_field.value or self.editor_category_field.text or "",
            "tags": self.tags_field.value or "",
            "variables": self.variables_field.value or "",
            "variable_defaults": self.variable_defaults_field.value or "",
            "notes": self.notes_field.value or "",
            "favorite": bool(self.favorite_checkbox.value),
            "confirm_before_copy": bool(self.confirm_before_copy_checkbox.value),
        }

    def has_unsaved_changes(self) -> bool:
        return self.editor_state() != self.editor_snapshot

    async def run_guarded(self, action: Callable[[], Awaitable[None] | None]) -> None:
        """Run action, asking first what to do with unsaved editor changes."""

        async def run_action() -> None:
            result = action()
            if inspect.isawaitable(result):
                await result

        if not self.has_unsaved_changes():
            await run_action()
            return

        def stay(_: ft.ControlEvent) -> None:
            self.close_dialog()

        async def discard(_: ft.ControlEvent) -> None:
            self.close_dialog()
            self.editor_snapshot = self.editor_state()
            await run_action()

        async def save_then_continue(_: ft.ControlEvent) -> None:
            self.close_dialog()
            if self.save_command(None):
                await run_action()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Modifications non enregistrées"),
            content=ft.Text("La commande en cours d'édition a été modifiée. Que veux-tu faire ?"),
            actions=[
                ft.TextButton("Rester", on_click=stay),
                ft.OutlinedButton("Ignorer", icon=ft.Icons.CLOSE, on_click=discard),
                ft.FilledButton("Enregistrer", icon=ft.Icons.SAVE, on_click=save_then_continue),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.open_dialog(dialog)

    async def on_tile_click(self, event: ft.ControlEvent) -> None:
        command_id = str(event.control.data)
        if command_id == self.selected_id:
            return
        await self.run_guarded(lambda: self.select_command(command_id))

    def select_command(self, command_id: str) -> None:
        self.selected_id = command_id
        self.refresh_list()
        self.fill_editor(self.store.get(command_id))
        self.page.update()

    def set_category_filter(self, category: str) -> None:
        self.category_filter = category
        self.refresh_all(refill_editor=False)

    def on_search_change(self, event: ft.ControlEvent) -> None:
        self.query = event.control.value.strip()
        self.refresh_list()
        self.page.update()

    def on_category_change(self, event: ft.ControlEvent) -> None:
        self.category_filter = event.control.value or ALL_CATEGORIES
        self.refresh_all(refill_editor=False)

    def on_tag_change(self, event: ft.ControlEvent) -> None:
        self.tag_filter = event.control.value or ALL_TAGS
        self.refresh_all(refill_editor=False)

    def on_scope_change(self, event: ft.ControlEvent) -> None:
        self.scope_filter = str(event.control.data or "all")
        self.refresh_all(refill_editor=False)

    async def new_command(self, _: ft.ControlEvent | None = None) -> None:
        await self.run_guarded(self.open_new_command)

    async def open_new_command(self) -> None:
        self.selected_id = None
        self.fill_editor(None)
        self.refresh_list()
        self.page.update()
        await self.title_field.focus()

    def cancel_edit(self, _: ft.ControlEvent | None = None) -> None:
        self.fill_editor(self.store.get(self.selected_id))
        self.page.update()

    def on_field_focus(self, event: ft.ControlEvent) -> None:
        self.focused_control = event.control

    def on_field_blur(self, event: ft.ControlEvent) -> None:
        if self.focused_control is event.control:
            self.focused_control = None

    def editing_text(self) -> bool:
        """True when the cursor is in an editor field (not the search field)."""
        return self.focused_control is not None and self.focused_control is not self.search_field

    async def on_keyboard(self, event: ft.KeyboardEvent) -> None:
        key = event.key
        if self.active_dialog is not None:
            if key == "Escape":
                self.close_dialog()
            return
        ctrl = event.ctrl or event.meta
        if ctrl and key == "F":
            await self.search_field.focus()
        elif ctrl and key == "N":
            await self.new_command()
        elif ctrl and key == "S":
            self.save_command(None)
            self.page.update()
        elif ctrl and key == "C" and not self.editing_text() and self.selected_id:
            await self.copy_command(self.selected_id)
            self.page.update()
        elif key == "F1":
            self.open_shortcuts_dialog()
        elif key == "Escape":
            self.cancel_edit()
        elif key in {"Arrow Down", "Arrow Up"} and not self.editing_text():
            await self.move_selection(1 if key == "Arrow Down" else -1)

    async def move_selection(self, step: int) -> None:
        visible = self.filtered_commands()
        if not visible:
            return
        ids = [command.id for command in visible]
        if self.selected_id in ids:
            index = max(0, min(len(ids) - 1, ids.index(self.selected_id) + step))
        else:
            index = 0 if step > 0 else len(ids) - 1
        target_id = ids[index]
        if target_id == self.selected_id:
            return

        async def select_and_scroll() -> None:
            self.select_command(target_id)
            await self.list_view.scroll_to(scroll_key=target_id, duration=150)

        await self.run_guarded(select_and_scroll)

    async def duplicate_selected_command(self, _: ft.ControlEvent | None = None) -> None:
        await self.run_guarded(self.duplicate_command)

    async def duplicate_command(self) -> None:
        source = self.store.get(self.selected_id)
        if not source:
            return
        copy = CommandEntry(
            title=f"{source.title} (copie)",
            command=source.command,
            category=source.category,
            tags=list(source.tags),
            variables=list(source.variables),
            variable_defaults=dict(source.variable_defaults),
            notes=source.notes,
            favorite=source.favorite,
            confirm_before_copy=source.confirm_before_copy,
        )
        self.store.upsert(copy)
        self.commands = self.store.commands
        self.selected_id = copy.id
        self.refresh_all()
        self.show_message("Commande dupliquée.")
        await self.title_field.focus()

    def save_command(self, _: ft.ControlEvent | None) -> bool:
        title = (self.title_field.value or "").strip()
        command_text = (self.command_field.value or "").strip()
        category = ((self.editor_category_field.value or self.editor_category_field.text or "General").strip() or "General")
        variables = self.resolve_command_variables(command_text)
        if not title or not command_text:
            self.show_message("Titre et commande sont obligatoires.")
            return False
        if variables is None:
            return False
        variable_defaults = self.resolve_variable_defaults(variables)
        variables = merge_variables_from_defaults(command_text, variables, variable_defaults, MAX_VARIABLES)
        variable_defaults = normalize_variable_defaults(self.variable_defaults_field.value or "", variables)
        existing = self.store.get(self.selected_id)
        # Auto-detection only for new or edited command text, so an explicit uncheck is kept.
        command_changed = existing is None or existing.command != command_text
        confirm_before_copy = bool(self.confirm_before_copy_checkbox.value) or (
            command_changed and is_dangerous_command(command_text)
        )
        if existing:
            command = CommandEntry(
                id=existing.id,
                title=title,
                command=command_text,
                category=category,
                tags=normalize_tags(self.tags_field.value),
                variables=variables,
                variable_defaults=variable_defaults,
                notes=(self.notes_field.value or "").strip(),
                favorite=bool(self.favorite_checkbox.value),
                confirm_before_copy=confirm_before_copy,
                use_count=existing.use_count,
                variable_history=existing.variable_history,
                created_at=existing.created_at,
                updated_at=existing.updated_at,
                last_used_at=existing.last_used_at,
            )
        else:
            command = CommandEntry(
                title=title,
                command=command_text,
                category=category,
                tags=normalize_tags(self.tags_field.value),
                variables=variables,
                variable_defaults=variable_defaults,
                notes=(self.notes_field.value or "").strip(),
                favorite=bool(self.favorite_checkbox.value),
                confirm_before_copy=confirm_before_copy,
            )

        self.store.upsert(command)
        self.commands = self.store.commands
        self.selected_id = command.id
        self.refresh_all()
        self.show_message("Commande enregistrée.")
        return True

    def format_variable_defaults(self, defaults: dict[str, str]) -> str:
        return "; ".join(f"{key}={value}" for key, value in defaults.items())

    def resolve_command_variables(self, command_text: str) -> list[str] | None:
        raw_variables = (self.variables_field.value or "").strip()
        if raw_variables:
            raw_parts = [part for part in raw_variables.replace(";", ",").split(",") if part.strip()]
            if len(raw_parts) > MAX_VARIABLES:
                self.show_message(f"Maximum {MAX_VARIABLES} variables par commande.")
                return None
            variables = normalize_variables(raw_variables, max_items=MAX_VARIABLES)
            if len(variables) != len(raw_parts):
                self.show_message("Variables invalides ignorées. Utilise lettres, chiffres et underscore.")
            return variables
        detected_variables = extract_variables(command_text, max_items=MAX_VARIABLES + 1)
        if len(detected_variables) > MAX_VARIABLES:
            self.show_message(f"Maximum {MAX_VARIABLES} variables par commande.")
            return None
        return detected_variables

    def resolve_variable_defaults(self, variables: list[str]) -> dict[str, str]:
        return normalize_variable_defaults(self.variable_defaults_field.value or "", variables)

    async def copy_selected_command(self, _: ft.ControlEvent) -> None:
        await self.copy_command(self.selected_id)

    async def copy_command_from_tile(self, event: ft.ControlEvent) -> None:
        await self.copy_command(str(event.control.data))

    def toggle_favorite_from_tile(self, event: ft.ControlEvent) -> None:
        command = self.store.get(str(event.control.data))
        if not command:
            return
        command.favorite = not command.favorite
        command.touch()
        self.store.save()
        self.commands = self.store.commands
        if command.id == self.selected_id:
            self.favorite_checkbox.value = command.favorite
            self.editor_snapshot["favorite"] = command.favorite
        self.refresh_filters()
        self.refresh_sidebar()
        self.refresh_stats()
        self.refresh_list()
        self.page.update()

    async def copy_command(self, command_id: str | None) -> None:
        command = self.store.get(command_id)
        if not command:
            return
        if command.variables:
            self.open_variable_dialog(command)
            return
        await self.copy_rendered_command(command, command.command)

    async def copy_rendered_command(
        self,
        command: CommandEntry,
        rendered_command: str,
        confirmed: bool = False,
        values: dict[str, str] | None = None,
    ) -> None:
        if command.confirm_before_copy and not confirmed:
            self.open_danger_dialog(command, rendered_command, values)
            return
        if self.clipboard is not None:
            await self.clipboard.set(rendered_command)
        elif hasattr(self.page, "set_clipboard"):
            self.page.set_clipboard(rendered_command)
        command.mark_used()
        if values:
            command.remember_variable_values(values, MAX_RECENT_VALUES)
        self.store.save()
        self.refresh_stats()
        self.refresh_list()
        self.show_message("Commande copiée.")

    def open_variable_dialog(self, command: CommandEntry) -> None:
        fields = [
            ft.TextField(
                label=f"${variable}",
                dense=True,
                border_radius=8,
                autofocus=index == 0,
                data=variable,
                value=command.variable_defaults.get(variable, ""),
            )
            for index, variable in enumerate(command.variables[:MAX_VARIABLES])
        ]

        def recent_values_row(field: ft.TextField) -> ft.Control:
            recent = command.variable_history.get(str(field.data), [])
            if not recent:
                return ft.Container(height=0)

            def use_value(event: ft.ControlEvent) -> None:
                field.value = str(event.control.data)
                field.update()

            return ft.Row(
                [ft.Text("Récentes :", size=11, color=ft.Colors.ON_SURFACE_VARIANT)]
                + [
                    ft.Chip(
                        label=ft.Text(value, size=11, font_family="Consolas"),
                        tooltip=value,
                        data=value,
                        on_click=use_value,
                    )
                    for value in recent
                ],
                spacing=6,
                wrap=True,
            )

        field_controls: list[ft.Control] = []
        for field in fields:
            field_controls.append(field)
            field_controls.append(recent_values_row(field))

        def close_dialog(_: ft.ControlEvent) -> None:
            self.close_dialog()

        async def copy_with_values(_: ft.ControlEvent) -> None:
            values = {str(field.data): field.value or "" for field in fields}
            rendered_command = render_command_template(command.command, values)
            self.close_dialog()
            await self.copy_rendered_command(command, rendered_command, values=values)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Renseigner les variables"),
            content=ft.Column(
                [
                    ft.Text(command.title, weight=ft.FontWeight.BOLD),
                    ft.Text(command.command, size=12, font_family="Consolas", selectable=True),
                    *field_controls,
                ],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton("Annuler", on_click=close_dialog),
                ft.FilledButton("Copier", icon=ft.Icons.CONTENT_COPY, on_click=copy_with_values),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.open_dialog(dialog)

    def open_danger_dialog(
        self, command: CommandEntry, rendered_command: str, values: dict[str, str] | None = None
    ) -> None:
        def close_dialog(_: ft.ControlEvent) -> None:
            self.close_dialog()

        async def copy_confirmed(_: ft.ControlEvent) -> None:
            self.close_dialog()
            await self.copy_rendered_command(command, rendered_command, confirmed=True, values=values)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Commande sensible"),
            content=ft.Column(
                [
                    ft.Text(command.title, weight=ft.FontWeight.BOLD),
                    ft.Text(rendered_command, size=12, font_family="Consolas", selectable=True),
                ],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton("Annuler", on_click=close_dialog),
                ft.FilledButton("Copier quand même", icon=ft.Icons.WARNING, on_click=copy_confirmed),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.open_dialog(dialog)

    def open_shortcuts_dialog(self, _: ft.ControlEvent | None = None) -> None:
        rows = [
            ft.Row(
                [
                    ft.Container(
                        width=90,
                        content=ft.Text(keys, font_family="Consolas", weight=ft.FontWeight.BOLD),
                    ),
                    ft.Text(description, expand=True),
                ],
                spacing=12,
            )
            for keys, description in SHORTCUTS
        ]
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Raccourcis clavier"),
            content=ft.Column(
                [
                    *rows,
                    ft.Divider(height=10),
                    ft.Text(
                        "Dans les champs d'édition, Ctrl+C et les flèches gardent leur comportement habituel.",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                tight=True,
                spacing=8,
                width=420,
            ),
            actions=[ft.FilledButton("Fermer", on_click=lambda _: self.close_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.open_dialog(dialog)

    def open_about_dialog(self, _: ft.ControlEvent | None = None) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.TERMINAL, color=ft.Colors.PRIMARY),
                    ft.Text(APP_TITLE, weight=ft.FontWeight.BOLD),
                ],
                spacing=10,
            ),
            content=ft.Column(
                [
                    ft.Text("Carnet de commandes : stocker, retrouver et copier tes commandes fréquentes."),
                    ft.Text(f"Version {__version__}"),
                    ft.Text(f"Auteur : {__author__}"),
                    ft.Text(
                        f"Données : {default_data_path()}",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        selectable=True,
                    ),
                ],
                tight=True,
                spacing=8,
                width=420,
            ),
            actions=[ft.FilledButton("Fermer", on_click=lambda _: self.close_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.open_dialog(dialog)

    def apply_theme(self) -> None:
        self.page.theme_mode = ft.ThemeMode.DARK if self.theme_mode_value == "dark" else ft.ThemeMode.LIGHT
        if hasattr(self, "theme_button"):
            is_dark = self.theme_mode_value == "dark"
            self.theme_button.icon = ft.Icons.LIGHT_MODE if is_dark else ft.Icons.DARK_MODE
            self.theme_button.tooltip = "Mode clair" if is_dark else "Mode sombre"

    def toggle_theme(self, _: ft.ControlEvent) -> None:
        self.theme_mode_value = "light" if self.theme_mode_value == "dark" else "dark"
        self.store.set_setting("theme_mode", self.theme_mode_value)
        self.apply_theme()
        self.page.update()

    def apply_view_mode(self) -> None:
        if hasattr(self, "view_button"):
            compact = self.view_mode_value == "compact"
            self.view_button.icon = ft.Icons.VIEW_AGENDA if compact else ft.Icons.DENSITY_SMALL
            self.view_button.tooltip = "Vue détaillée" if compact else "Vue compacte"

    def toggle_view_mode(self, _: ft.ControlEvent) -> None:
        self.view_mode_value = "detailed" if self.view_mode_value == "compact" else "compact"
        self.store.set_setting("view_mode", self.view_mode_value)
        self.apply_view_mode()
        self.refresh_list()
        self.page.update()

    def confirm_delete(self, _: ft.ControlEvent) -> None:
        command = self.store.get(self.selected_id)
        if not command:
            return

        def close_dialog(event: ft.ControlEvent) -> None:
            self.close_dialog()

        def delete_command(event: ft.ControlEvent) -> None:
            self.store.delete(command.id)
            self.commands = self.store.commands
            self.selected_id = self.commands[0].id if self.commands else None
            self.close_dialog()
            self.refresh_all()
            self.show_message("Commande supprimée.")

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Supprimer la commande ?"),
            content=ft.Text(command.title),
            actions=[
                ft.TextButton("Annuler", on_click=close_dialog),
                ft.FilledButton("Supprimer", icon=ft.Icons.DELETE_OUTLINE, on_click=delete_command),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.open_dialog(dialog)

    async def pick_import_file(self, _: ft.ControlEvent) -> None:
        result = self.import_picker.pick_files(
            dialog_title="Importer des commandes",
            allowed_extensions=["json"],
            file_type=ft.FilePickerFileType.CUSTOM,
            allow_multiple=False,
        )
        if inspect.isawaitable(result):
            await result

    async def pick_export_file(self, _: ft.ControlEvent) -> None:
        result = self.export_picker.save_file(
            dialog_title="Exporter les commandes",
            file_name="c-deck-export.json",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
        )
        if inspect.isawaitable(result):
            path = await result
            if path:
                self.export_to_path(Path(path))

    def on_import_result(self, event: ft.FilePickerResultEvent) -> None:
        if not event.files:
            return
        try:
            added = self.store.import_file(Path(event.files[0].path))
            self.commands = self.store.commands
            self.selected_id = self.commands[0].id if self.commands else None
            self.refresh_all()
            self.show_message(f"Import terminé: {added} nouvelle(s) commande(s).")
        except Exception as exc:
            self.show_message(f"Import impossible: {exc}")

    def on_export_result(self, event: ft.FilePickerResultEvent) -> None:
        if not event.path:
            return
        try:
            self.export_to_path(Path(event.path))
            self.show_message("Export terminé.")
        except Exception as exc:
            self.show_message(f"Export impossible: {exc}")

    def export_to_path(self, path: Path) -> None:
        self.store.export_file(path)

    def show_message(self, message: str) -> None:
        snack_bar = ft.SnackBar(ft.Text(message))
        if hasattr(self.page, "show_dialog"):
            self.page.show_dialog(snack_bar)
            return
        self.page.snack_bar = snack_bar
        self.page.snack_bar.open = True
        self.page.update()

    def register_service(self, control: ft.Control) -> None:
        if hasattr(self.page, "services"):
            self.page.services.append(control)
            return
        self.page.overlay.append(control)

    def open_dialog(self, dialog: ft.AlertDialog) -> None:
        self.active_dialog = dialog

        def on_dismiss(_: ft.ControlEvent) -> None:
            if self.active_dialog is dialog:
                self.active_dialog = None

        dialog.on_dismiss = on_dismiss
        if hasattr(self.page, "show_dialog"):
            self.page.show_dialog(dialog)
            return
        if hasattr(self.page, "open"):
            self.page.open(dialog)
            return
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

    def close_dialog(self) -> None:
        if self.active_dialog is None:
            return
        if hasattr(self.page, "show_dialog"):
            # Close this dialog explicitly: pop_dialog() could close a snackbar shown on top of it.
            self.active_dialog.open = False
            self.active_dialog.update()
            self.active_dialog = None
            return
        if hasattr(self.page, "close") and self.active_dialog is not None:
            self.page.close(self.active_dialog)
            self.active_dialog = None
            return
        if getattr(self.page, "dialog", None) is not None:
            self.page.dialog.open = False
            self.active_dialog = None
            self.page.update()


def main(page: ft.Page | None = None) -> None:
    if page is None:
        if hasattr(ft, "run"):
            ft.run(main)
        else:
            ft.app(target=main)
        return
    CDeckApp(page)
