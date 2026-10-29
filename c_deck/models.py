from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

MAX_COMMAND_VARIABLES = 5
PARIS_TZ = ZoneInfo("Europe/Paris")
VARIABLE_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
COMMAND_SEPARATORS = {"&&", "||", ";", "|"}
DANGEROUS_PATTERNS = (
    r"\bdocker\s+(compose\s+)?down\b[^\n]*(\s-v\b|\s--volumes\b)",
    r"\bdocker\s+system\s+prune\b[^\n]*(-a\b|--all\b|-f\b|--force\b)?",
    r"\b(drop|truncate)\s+(database|table)\b",
    r"\bchmod\s+-R\s+777\b",
    r"\bmkfs\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bphp\s+admin/cli/upgrade\.php\b",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def format_paris_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(PARIS_TZ).strftime("%d-%m-%Y %H:%M")


def normalize_tags(value: str | list[str] | None) -> list[str]:
    if isinstance(value, str):
        raw_tags = value.replace(";", ",").split(",")
    elif isinstance(value, list):
        raw_tags = [str(tag) for tag in value]
    else:
        raw_tags = []

    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        tag = raw_tag.strip().lstrip("#")
        tag_key = tag.lower()
        if tag and tag_key not in seen:
            seen.add(tag_key)
            tags.append(tag)
    return tags


def normalize_variables(value: str | list[str] | None, max_items: int = MAX_COMMAND_VARIABLES) -> list[str]:
    if isinstance(value, str):
        raw_variables = value.replace(";", ",").split(",")
    elif isinstance(value, list):
        raw_variables = [str(variable) for variable in value]
    else:
        raw_variables = []

    variables: list[str] = []
    seen: set[str] = set()
    for raw_variable in raw_variables:
        variable = raw_variable.strip().lstrip("$")
        if not variable or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable):
            continue
        variable_key = variable.lower()
        if variable_key not in seen:
            seen.add(variable_key)
            variables.append(variable)
        if len(variables) >= max_items:
            break
    return variables


def normalize_variable_defaults(value: str | dict[str, Any] | None, variables: list[str] | None = None) -> dict[str, str]:
    allowed = {variable.lower(): variable for variable in (variables or [])}
    defaults: dict[str, str] = {}
    if isinstance(value, dict):
        items = [(str(key), str(raw_value)) for key, raw_value in value.items()]
    elif isinstance(value, str):
        items = []
        for part in value.replace("\n", ";").split(";"):
            if "=" not in part:
                continue
            key, raw_value = part.split("=", 1)
            items.append((key, raw_value))
    else:
        items = []

    for raw_key, raw_value in items:
        key = raw_key.strip().lstrip("$")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        output_key = allowed.get(key.lower(), key)
        if variables and output_key.lower() not in allowed:
            continue
        defaults[output_key] = raw_value.strip()
    return defaults


def extract_variables(command: str, max_items: int = MAX_COMMAND_VARIABLES) -> list[str]:
    return normalize_variables(VARIABLE_RE.findall(command or ""), max_items=max_items)


def render_command_template(command: str, values: dict[str, str]) -> str:
    rendered = command
    for variable, value in values.items():
        rendered = re.sub(rf"\{{\{{\s*{re.escape(variable)}\s*\}}\}}", lambda _: value, rendered)
        rendered = re.sub(rf"\${re.escape(variable)}\b", lambda _: value, rendered)
    return rendered


def command_uses_variable(command: str, variable: str) -> bool:
    return bool(
        re.search(rf"\{{\{{\s*{re.escape(variable)}\s*\}}\}}", command)
        or re.search(rf"\${re.escape(variable)}\b", command)
    )


def merge_variables_from_defaults(
    command: str,
    variables: list[str],
    variable_defaults: dict[str, str],
    max_items: int = MAX_COMMAND_VARIABLES,
) -> list[str]:
    merged = list(variables)
    seen = {variable.lower() for variable in merged}
    for variable in variable_defaults:
        if len(merged) >= max_items:
            break
        if variable.lower() in seen or not command_uses_variable(command, variable):
            continue
        merged.append(variable)
        seen.add(variable.lower())
    return merged


def has_recursive_force_rm(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    for index, token in enumerate(tokens):
        if token != "rm" and not token.endswith("/rm"):
            continue

        recursive = False
        force = False
        for option in tokens[index + 1 :]:
            if option in COMMAND_SEPARATORS:
                break
            if option == "--":
                break
            if option in {"--recursive", "--dir"}:
                recursive = True
            elif option == "--force":
                force = True
            elif option.startswith("-") and not option.startswith("--"):
                flags = option[1:]
                recursive = recursive or "r" in flags or "R" in flags
                force = force or "f" in flags
        if recursive and force:
            return True
    return False


def is_dangerous_command(command: str) -> bool:
    normalized = command.lower()
    return has_recursive_force_rm(command) or any(
        re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in DANGEROUS_PATTERNS
    )


def normalize_variable_history(value: Any, variables: list[str], max_values: int = 5) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    allowed = {variable.lower(): variable for variable in variables}
    history: dict[str, list[str]] = {}
    for raw_key, raw_values in value.items():
        key = allowed.get(str(raw_key).lower())
        if key is None or not isinstance(raw_values, list):
            continue
        values = [str(item) for item in raw_values if str(item).strip()][:max_values]
        if values:
            history[key] = values
    return history


def split_search_query(query: str) -> list[str]:
    try:
        return shlex.split(query)
    except ValueError:
        return query.split()


@dataclass(slots=True)
class CommandEntry:
    title: str
    command: str
    category: str = "General"
    tags: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    variable_defaults: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    favorite: bool = False
    confirm_before_copy: bool = False
    use_count: int = 0
    variable_history: dict[str, list[str]] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    last_used_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommandEntry":
        now = utc_now()
        title = str(data.get("title") or data.get("name") or "Commande sans titre").strip()
        command = str(data.get("command") or "").strip()
        category = str(data.get("category") or "General").strip() or "General"
        variables = normalize_variables(data.get("variables")) or extract_variables(command)
        variable_defaults = normalize_variable_defaults(data.get("variable_defaults"), variables)
        variables = merge_variables_from_defaults(command, variables, variable_defaults)
        variable_defaults = normalize_variable_defaults(data.get("variable_defaults"), variables)
        try:
            use_count = max(0, int(data.get("use_count") or 0))
        except (TypeError, ValueError):
            use_count = 0

        return cls(
            id=str(data.get("id") or uuid4()),
            title=title,
            command=command,
            category=category,
            tags=normalize_tags(data.get("tags")),
            variables=variables,
            variable_defaults=variable_defaults,
            notes=str(data.get("notes") or ""),
            favorite=bool(data.get("favorite", False)),
            confirm_before_copy=(
                bool(data["confirm_before_copy"])
                if "confirm_before_copy" in data
                else is_dangerous_command(command)
            ),
            use_count=use_count,
            variable_history=normalize_variable_history(data.get("variable_history"), variables),
            created_at=str(data.get("created_at") or now),
            updated_at=str(data.get("updated_at") or now),
            last_used_at=data.get("last_used_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "command": self.command,
            "category": self.category,
            "tags": self.tags,
            "variables": self.variables,
            "variable_defaults": self.variable_defaults,
            "notes": self.notes,
            "favorite": self.favorite,
            "confirm_before_copy": self.confirm_before_copy,
            "use_count": self.use_count,
            "variable_history": self.variable_history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
        }

    def touch(self) -> None:
        self.updated_at = utc_now()

    def mark_used(self) -> None:
        now = utc_now()
        self.use_count += 1
        self.last_used_at = now
        self.updated_at = now

    def remember_variable_values(self, values: dict[str, str], max_values: int = 5) -> None:
        """Keep the most recent distinct values used for each variable, newest first."""
        for variable, value in values.items():
            if not value.strip() or variable not in self.variables:
                continue
            previous = [item for item in self.variable_history.get(variable, []) if item != value]
            self.variable_history[variable] = [value, *previous][:max_values]

    def matches(self, query: str, category: str | None = None, tag: str | None = None) -> bool:
        if category and category != "Toutes" and self.category.lower() != category.lower():
            return False
        if tag and tag != "Tous" and tag.lower() not in {item.lower() for item in self.tags}:
            return False
        if not query:
            return True

        haystack = " ".join(
            [
                self.title,
                self.command,
                self.category,
                " ".join(self.tags),
                " ".join(self.variables),
                " ".join(self.variable_defaults.values()),
                self.notes,
            ]
        ).lower()
        for part in split_search_query(query):
            if ":" in part:
                key, value = part.split(":", 1)
                key = key.lower().strip()
                value = value.lower().strip()
                if key in {"tag", "tags"} and value not in {item.lower() for item in self.tags}:
                    return False
                if key in {"cat", "category", "categorie"} and value not in self.category.lower():
                    return False
                if key in {"fav", "favorite", "favori"} and self.favorite != (value in {"1", "true", "yes", "oui", "on"}):
                    return False
                if key in {"danger", "confirm"} and self.confirm_before_copy != (value in {"1", "true", "yes", "oui", "on"}):
                    return False
                if key in {"var", "variable"} and value not in {item.lower() for item in self.variables}:
                    return False
                if key == "used" and value in {"1", "true", "yes", "oui", "on"} and self.use_count == 0:
                    return False
                if key == "used" and value in {"0", "false", "no", "non", "off"} and self.use_count > 0:
                    return False
                if key not in {
                    "tag",
                    "tags",
                    "cat",
                    "category",
                    "categorie",
                    "fav",
                    "favorite",
                    "favori",
                    "danger",
                    "confirm",
                    "var",
                    "variable",
                    "used",
                } and part.lower() not in haystack:
                    return False
                continue
            if part.lower() not in haystack:
                return False
        return True
