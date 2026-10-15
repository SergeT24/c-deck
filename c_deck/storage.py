from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import CommandEntry

APP_DIR = ".c-deck"
LEGACY_APP_DIRS = (".jutsudeck", ".command_vault")
DATA_FILE = "commands.json"
DEFAULT_SETTINGS = {
    "theme_mode": "light",
    "view_mode": "detailed",
}


SAMPLE_COMMANDS = [
    {
        "title": "Moodle - vider les caches",
        "command": "php admin/cli/purge_caches.php",
        "category": "Moodle",
        "tags": ["moodle", "cache", "maintenance"],
        "notes": "Depuis la racine de l'installation Moodle.",
    },
    {
        "title": "Docker - voir les conteneurs",
        "command": "docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\"",
        "category": "Docker",
        "tags": ["docker", "debug"],
        "notes": "",
    },
    {
        "title": "Linux - espace disque lisible",
        "command": "df -h",
        "category": "Linux",
        "tags": ["linux", "disk"],
        "notes": "",
    },
]


class CommandStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_data_path()
        self.commands: list[CommandEntry] = []
        self.settings: dict[str, str] = DEFAULT_SETTINGS.copy()
        self.recovery_message: str | None = None

    def load(self) -> list[CommandEntry]:
        self.migrate_legacy_data()
        if not self.path.exists():
            self.commands = [CommandEntry.from_dict(item) for item in SAMPLE_COMMANDS]
            self.save()
            return self.commands

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.settings = parse_settings_payload(data)
            self.commands = parse_commands_payload(data)
        except (json.JSONDecodeError, ValueError):
            backup_path = self.backup_invalid_data_file()
            self.settings = DEFAULT_SETTINGS.copy()
            self.commands = [CommandEntry.from_dict(item) for item in SAMPLE_COMMANDS]
            self.save()
            self.recovery_message = f"JSON invalide sauvegardé dans {backup_path}. Nouveau fichier créé."
        return self.commands

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "settings": self.settings,
            "commands": [command.to_dict() for command in self.commands],
        }
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)

    def upsert(self, command: CommandEntry) -> None:
        for index, existing in enumerate(self.commands):
            if existing.id == command.id:
                command.touch()
                self.commands[index] = command
                self.save()
                return
        command.touch()
        self.commands.append(command)
        self.save()

    def delete(self, command_id: str) -> None:
        self.commands = [command for command in self.commands if command.id != command_id]
        self.save()

    def get(self, command_id: str | None) -> CommandEntry | None:
        return next((command for command in self.commands if command.id == command_id), None)

    def import_file(self, path: Path, replace: bool = False) -> int:
        imported = parse_commands_payload(json.loads(path.read_text(encoding="utf-8")))
        if replace:
            self.commands = imported
            self.save()
            return len(imported)

        by_id = {command.id: command for command in self.commands}
        fingerprints = {command_fingerprint(command) for command in self.commands}
        added = 0
        for command in imported:
            fingerprint = command_fingerprint(command)
            existing = by_id.get(command.id)
            if existing is None and fingerprint in fingerprints:
                continue
            if existing is None:
                added += 1
            else:
                fingerprints.discard(command_fingerprint(existing))
            by_id[command.id] = command
            fingerprints.add(fingerprint)
        self.commands = sorted(by_id.values(), key=lambda item: item.title.lower())
        self.save()
        return added

    def export_file(self, path: Path) -> None:
        payload = {
            "version": 1,
            "settings": self.settings,
            "commands": [command.to_dict() for command in self.commands],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_setting(self, key: str, default: str = "") -> str:
        return str(self.settings.get(key, default))

    def set_setting(self, key: str, value: str) -> None:
        self.settings[key] = value
        self.save()

    def migrate_legacy_data(self) -> None:
        if self.path.exists():
            return
        for legacy_dir in LEGACY_APP_DIRS:
            legacy_path = Path.home() / legacy_dir / DATA_FILE
            if not legacy_path.exists():
                continue
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
            return

    def backup_invalid_data_file(self) -> Path:
        backup_path = next_backup_path(self.path)
        os.replace(self.path, backup_path)
        return backup_path


def default_data_path() -> Path:
    return Path.home() / APP_DIR / DATA_FILE


def next_backup_path(path: Path) -> Path:
    backup_path = path.with_name(f"{path.name}.bak")
    if not backup_path.exists():
        return backup_path
    index = 1
    while True:
        candidate = path.with_name(f"{path.name}.bak.{index}")
        if not candidate.exists():
            return candidate
        index += 1


def command_fingerprint(command: CommandEntry) -> tuple[str, str]:
    return (command.title.strip().casefold(), command.command.strip())


def parse_commands_payload(data: Any) -> list[CommandEntry]:
    if isinstance(data, dict):
        raw_commands = data.get("commands", [])
    elif isinstance(data, list):
        raw_commands = data
    else:
        raise ValueError("Le fichier JSON doit contenir une liste ou un objet avec une clé 'commands'.")

    if not isinstance(raw_commands, list):
        raise ValueError("La clé 'commands' doit contenir une liste.")

    commands = []
    for item in raw_commands:
        if not isinstance(item, dict):
            continue
        command = CommandEntry.from_dict(item)
        if command.command:
            commands.append(command)
    return commands


def parse_settings_payload(data: Any) -> dict[str, str]:
    settings = DEFAULT_SETTINGS.copy()
    if isinstance(data, dict) and isinstance(data.get("settings"), dict):
        for key, value in data["settings"].items():
            settings[str(key)] = str(value)
    if settings.get("theme_mode") not in {"light", "dark"}:
        settings["theme_mode"] = DEFAULT_SETTINGS["theme_mode"]
    if settings.get("view_mode") not in {"compact", "detailed"}:
        settings["view_mode"] = DEFAULT_SETTINGS["view_mode"]
    return settings
