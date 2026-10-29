import json
import tempfile
import unittest
from pathlib import Path

from c_deck.models import (
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
from c_deck.storage import CommandStore, parse_commands_payload


class StorageTest(unittest.TestCase):
    def test_dates_are_formatted_for_paris_timezone(self):
        self.assertEqual(format_paris_datetime("2026-10-05T12:00:00+00:00"), "05-10-2026 14:00")
        self.assertEqual(format_paris_datetime("2026-01-05T12:00:00+00:00"), "05-01-2026 13:00")
        self.assertEqual(format_paris_datetime(None), "")

    def test_normalize_tags_deduplicates_and_trims(self):
        self.assertEqual(normalize_tags(" linux, #Moodle; linux ,, Cache "), ["linux", "Moodle", "Cache"])

    def test_variables_are_detected_and_rendered(self):
        command = "php admin/cli/scheduled_task.php --execute='{{class_task}}'"

        self.assertEqual(extract_variables(command), ["class_task"])
        self.assertEqual(extract_variables("echo $HOME && echo {{course_id}}"), ["course_id"])
        self.assertEqual(normalize_variables("$class_task, course_id"), ["class_task", "course_id"])
        self.assertEqual(
            normalize_variable_defaults(r"class_task=local_dashboard_eticeo\task\send_info", ["class_task"]),
            {"class_task": r"local_dashboard_eticeo\task\send_info"},
        )
        self.assertEqual(
            render_command_template(command, {"class_task": r"local_dashboard_eticeo\task\send_info"}),
            r"php admin/cli/scheduled_task.php --execute='local_dashboard_eticeo\task\send_info'",
        )
        self.assertEqual(render_command_template("echo $legacy", {"legacy": "ok"}), "echo ok")

    def test_legacy_dollar_variable_is_inferred_from_default_value(self):
        command = "php admin/cli/scheduled_task.php --execute='$classtaskname'"
        defaults = normalize_variable_defaults(r"classtaskname=local_dashboard_eticeo\task\send_info", [])

        variables = merge_variables_from_defaults(command, [], defaults)
        entry = CommandEntry.from_dict(
            {
                "title": "Task",
                "command": command,
                "variable_defaults": defaults,
            }
        )

        self.assertEqual(variables, ["classtaskname"])
        self.assertEqual(entry.variables, ["classtaskname"])
        self.assertEqual(
            render_command_template(command, entry.variable_defaults),
            r"php admin/cli/scheduled_task.php --execute='local_dashboard_eticeo\task\send_info'",
        )

    def test_usage_danger_and_advanced_search(self):
        command = CommandEntry.from_dict(
            {
                "title": "Danger",
                "command": "rm -rf /tmp/demo",
                "category": "Linux",
                "tags": ["cleanup"],
                "favorite": True,
                "variables": ["path"],
                "variable_defaults": {"path": "/tmp/demo"},
            }
        )

        self.assertTrue(is_dangerous_command(command.command))
        self.assertTrue(command.confirm_before_copy)
        self.assertTrue(command.matches("tag:cleanup category:lin favorite:true danger:true var:path"))
        command.mark_used()
        self.assertEqual(command.use_count, 1)
        self.assertTrue(command.matches("used:true"))

    def test_explicit_confirm_false_is_kept_for_dangerous_command(self):
        command = CommandEntry.from_dict(
            {
                "title": "Maj Moodle",
                "command": "php admin/cli/upgrade.php --non-interactive",
                "confirm_before_copy": False,
            }
        )

        self.assertFalse(command.confirm_before_copy)
        self.assertFalse(CommandEntry.from_dict(command.to_dict()).confirm_before_copy)

    def test_variable_history_keeps_recent_distinct_values(self):
        command = CommandEntry.from_dict(
            {"title": "Task", "command": "php run.php --task='{{class_task}}'"}
        )
        for value in ["a", "b", "a", "c", "d", "e", "f", "  "]:
            command.remember_variable_values({"class_task": value, "unknown": "x"}, max_values=5)

        self.assertEqual(command.variable_history, {"class_task": ["f", "e", "d", "c", "a"]})
        self.assertEqual(CommandEntry.from_dict(command.to_dict()).variable_history, command.variable_history)

    def test_dangerous_variants_are_detected(self):
        self.assertTrue(is_dangerous_command("rm -fr /tmp/demo"))
        self.assertTrue(is_dangerous_command("sudo rm --recursive --force /tmp/demo"))
        self.assertTrue(is_dangerous_command("docker compose down --volumes"))
        self.assertTrue(is_dangerous_command("docker system prune --all --force"))
        self.assertFalse(is_dangerous_command("echo 'rm -rf /tmp/demo'"))

    def test_store_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "commands.json"
            store = CommandStore(path)
            commands = store.load()

            self.assertTrue(commands)
            self.assertTrue(path.exists())

            reloaded = CommandStore(path)
            self.assertEqual(len(reloaded.load()), len(commands))

    def test_parse_accepts_list_payload(self):
        payload = [{"title": "List files", "command": "ls -la", "tags": "linux, files"}]
        commands = parse_commands_payload(payload)

        self.assertEqual(commands[0].title, "List files")
        self.assertEqual(commands[0].tags, ["linux", "files"])

    def test_import_merges_by_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "commands.json"
            import_path = Path(tmp_dir) / "import.json"
            store = CommandStore(path)
            store.load()
            existing_id = store.commands[0].id
            import_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "commands": [
                            {
                                "id": existing_id,
                                "title": "Updated",
                                "command": "echo updated",
                                "category": "Shell",
                            },
                            {
                                "title": "New",
                                "command": "echo new",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            added = store.import_file(import_path)

            self.assertEqual(added, 1)
            self.assertTrue(any(command.title == "Updated" for command in store.commands))
            self.assertTrue(any(command.title == "New" for command in store.commands))

    def test_import_skips_duplicate_title_and_command_without_same_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "commands.json"
            import_path = Path(tmp_dir) / "import.json"
            store = CommandStore(path)
            store.commands = [CommandEntry.from_dict({"title": "Same", "command": "echo same"})]
            store.save()
            import_path.write_text(
                json.dumps({"commands": [{"title": "Same", "command": "echo same"}]}),
                encoding="utf-8",
            )

            added = store.import_file(import_path)

            self.assertEqual(added, 0)
            self.assertEqual(len(store.commands), 1)

    def test_invalid_json_is_backed_up_and_recreated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "commands.json"
            path.write_text("{invalid", encoding="utf-8")
            store = CommandStore(path)

            commands = store.load()

            self.assertTrue(commands)
            self.assertTrue(path.exists())
            self.assertTrue(path.with_name("commands.json.bak").exists())
            self.assertIsNotNone(store.recovery_message)

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "commands.json"
            store = CommandStore(path)
            store.load()
            store.set_setting("theme_mode", "dark")
            store.set_setting("view_mode", "compact")

            reloaded = CommandStore(path)
            reloaded.load()

            self.assertEqual(reloaded.get_setting("theme_mode"), "dark")
            self.assertEqual(reloaded.get_setting("view_mode"), "compact")

    def test_variables_round_trip(self):
        payload = [
            {
                "title": "Moodle task",
                "command": "php admin/cli/scheduled_task.php --execute='{{class_task}}'",
                "variable_defaults": {"class_task": r"local_dashboard_eticeo\task\send_info"},
                "use_count": 2,
            }
        ]
        commands = parse_commands_payload(payload)

        self.assertEqual(commands[0].variables, ["class_task"])
        self.assertEqual(commands[0].variable_defaults["class_task"], r"local_dashboard_eticeo\task\send_info")
        self.assertEqual(commands[0].use_count, 2)


if __name__ == "__main__":
    unittest.main()
