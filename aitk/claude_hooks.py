"""Claude Code hook registration from hooks/hooks.json.

`bin/aitk install` writes the toolkit's hooks into `~/.claude/settings.json` by
default (`--no-hooks` opts out), and `bin/aitk uninstall` removes them.
hooks/hooks.json is the single registration source: Codex reads it through the
plugin, where `$PLUGIN_ROOT` is set; Claude Code settings get the absolute
toolkit root in its place, because an unset variable turns
`bash "$PLUGIN_ROOT/hooks/..."` into `bash "/hooks/..."`, which exits 127 and
lets the command through.

Ownership is by content, so a later uninstall finds the entries without any
ledger: a hook handler belongs to the toolkit when its command points into
`<toolkit root>/hooks/`. Install first removes every such handler (including
ones an older install-hooks.sh wrote for hooks that no longer exist), then
appends the hooks.json entries. It also adds `permissions.deny` rules for the
git bypasses; they hold even when python3 is missing, but they do not match
inside `sh -c`, so the git guard stays.

A small record in `~/.ai-toolkit/claude-hooks.json` remembers the roots
written, the deny rules this toolkit added (a rule the user already had is
left alone), the settings containers it created, and an opt-out, so uninstall
puts the file back as it found it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile


RECORD_NAME = "claude-hooks.json"
RECORD_VERSION = 1
PLUGIN_ROOT = "$PLUGIN_ROOT"
DENY_RULES = (
    "Bash(git push --force *)",
    "Bash(git push -f *)",
    "Bash(git commit --no-verify *)",
    "Bash(git commit -n *)",
)


class HookSettingsError(ValueError):
    """The settings file cannot be updated safely."""


def settings_path(home: Path) -> Path:
    return home / ".claude" / "settings.json"


def record_path(state_dir: Path) -> Path:
    return state_dir / RECORD_NAME


def _double_quoted(text: str) -> str:
    """`text` made safe inside a double-quoted bash word."""
    return re.sub(r'([\\"$`])', r"\\\1", text)


def hooks_dir(root: Path) -> str:
    return f"{root}/hooks/"


def desired_hooks(root: Path) -> dict[str, list[dict]]:
    """hooks.json's entries with the absolute toolkit root for `$PLUGIN_ROOT`."""
    source = json.loads((root / "hooks/hooks.json").read_text(encoding="utf-8"))
    hooks = source.get("hooks")
    if not isinstance(hooks, dict):
        raise HookSettingsError("hooks/hooks.json has no hooks object")
    quoted_root = _double_quoted(str(root))
    result: dict[str, list[dict]] = {}
    for event, groups in hooks.items():
        result[event] = []
        for group in groups:
            entry = json.loads(json.dumps(group))
            for handler in entry.get("hooks", []):
                command = handler.get("command", "")
                if PLUGIN_ROOT not in command:
                    raise HookSettingsError(f"hooks/hooks.json command does not use {PLUGIN_ROOT}: {command}")
                handler["command"] = command.replace(PLUGIN_ROOT, quoted_root)
            result[event].append(entry)
    return result


def _owned(handler: object, directories: list[str]) -> bool:
    if not isinstance(handler, dict):
        return False
    command = handler.get("command")
    if not isinstance(command, str):
        return False
    return any(
        directory in command or _double_quoted(directory) in command for directory in directories
    )


def _strip_handlers(settings: dict, directories: list[str], drop_emptied: bool = False) -> None:
    """Remove every hook handler pointing into `directories`; drop emptied groups.

    With `drop_emptied`, an event list (and then the hooks object) that held
    only toolkit handlers is removed too, as the older hook installer did.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        return
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(handlers, list):
                kept_groups.append(group)
                continue
            kept = [handler for handler in handlers if not _owned(handler, directories)]
            if len(kept) != len(handlers):
                if not kept:
                    continue
                group = {**group, "hooks": kept}
            kept_groups.append(group)
        if drop_emptied and groups and not kept_groups:
            del hooks[event]
        else:
            hooks[event] = kept_groups
    if drop_emptied and not hooks:
        del settings["hooks"]


def _prune(settings: dict, created: list[str]) -> None:
    """Remove containers this toolkit created once they are empty again."""
    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            if hooks[event] == [] and f"hooks.{event}" in created:
                del hooks[event]
        if hooks == {} and "hooks" in created:
            del settings["hooks"]
    permissions = settings.get("permissions")
    if isinstance(permissions, dict):
        if permissions.get("deny") == [] and "permissions.deny" in created:
            del permissions["deny"]
        if permissions == {} and "permissions" in created:
            del settings["permissions"]


def _indent(text: str) -> int | str:
    match = re.search(r"\n([ \t]+)\S", text)
    if not match:
        return 2
    whitespace = match.group(1)
    return whitespace if "\t" in whitespace else len(whitespace)


def _render(settings: dict, original: str | None) -> str:
    indent = _indent(original) if original else 2
    text = json.dumps(settings, indent=indent, ensure_ascii=False)
    if original is None or original.endswith("\n"):
        text += "\n"
    return text


def _write(path: Path, text: str) -> None:
    # Follow a symlinked settings file (a dotfiles checkout) instead of
    # replacing the link with a regular file.
    target = Path(os.path.realpath(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = (target.stat().st_mode & 0o777) if target.exists() else 0o644
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _read_settings(path: Path) -> tuple[dict, str | None]:
    if not path.exists():
        return {}, None
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}, text
    try:
        settings = json.loads(text)
    except json.JSONDecodeError as error:
        raise HookSettingsError(f"{path} is not valid JSON ({error}); fix it first") from error
    if not isinstance(settings, dict):
        raise HookSettingsError(f"{path} does not hold a JSON object; fix it first")
    return settings, text


def check_settings(home: Path) -> None:
    """Refuse before any install step when the settings file cannot be edited."""
    _read_settings(settings_path(home))


def load_record(state_dir: Path) -> dict:
    path = record_path(state_dir)
    if path.is_symlink():
        raise HookSettingsError(f"hook record cannot be a symlink: {path}")
    if not path.is_file():
        return {}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return record if isinstance(record, dict) and record.get("version") == RECORD_VERSION else {}


def _save_record(state_dir: Path, record: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = record_path(state_dir)
    descriptor, temporary = tempfile.mkstemp(prefix=".claude-hooks.", dir=state_dir)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"version": RECORD_VERSION, **record}, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def register(root: Path, home: Path, state_dir: Path) -> list[str]:
    """Write the hooks.json entries and deny rules; return the paths changed."""
    path = settings_path(home)
    settings, original = _read_settings(path)
    record = load_record(state_dir)
    directories = list(dict.fromkeys([hooks_dir(root), *_strings(record.get("hook_dirs"))]))
    created = _strings(record.get("created"))
    _strip_handlers(settings, directories)

    hooks = settings.get("hooks")
    if hooks is None:
        hooks = settings["hooks"] = {}
        created.append("hooks")
    if not isinstance(hooks, dict):
        raise HookSettingsError(f"{path}: `hooks` is not an object; fix it first")
    for event, groups in desired_hooks(root).items():
        if event not in hooks:
            hooks[event] = []
            created.append(f"hooks.{event}")
        if not isinstance(hooks[event], list):
            raise HookSettingsError(f"{path}: `hooks.{event}` is not a list; fix it first")
        hooks[event].extend(groups)

    permissions = settings.get("permissions")
    if permissions is None:
        permissions = settings["permissions"] = {}
        created.append("permissions")
    if not isinstance(permissions, dict):
        raise HookSettingsError(f"{path}: `permissions` is not an object; fix it first")
    deny = permissions.get("deny")
    if deny is None:
        deny = permissions["deny"] = []
        created.append("permissions.deny")
    if not isinstance(deny, list):
        raise HookSettingsError(f"{path}: `permissions.deny` is not a list; fix it first")
    added = _strings(record.get("deny_added"))
    for rule in DENY_RULES:
        if rule not in deny:
            deny.append(rule)
            added.append(rule)

    text = _render(settings, original)
    changed = []
    if text != original:
        _write(path, text)
        changed.append(str(path))
    _save_record(
        state_dir,
        {
            "settings": str(path),
            "hook_dirs": [hooks_dir(root)],
            "deny_added": list(dict.fromkeys(added)),
            "created": list(dict.fromkeys(created)),
            "created_file": bool(record.get("created_file")) or original is None,
            "opted_out": False,
        },
    )
    return changed


def unregister(root: Path, home: Path, state_dir: Path, opted_out: bool = False) -> list[str]:
    """Remove the toolkit's hook handlers and the deny rules it added."""
    path = settings_path(home)
    record = load_record(state_dir)
    changed: list[str] = []
    if path.exists():
        settings, original = _read_settings(path)
        directories = list(dict.fromkeys([hooks_dir(root), *_strings(record.get("hook_dirs"))]))
        _strip_handlers(settings, directories, drop_emptied=True)
        # Without the record, the toolkit's rules are recognized by content.
        added = _strings(record["deny_added"]) if "deny_added" in record else list(DENY_RULES)
        permissions = settings.get("permissions")
        if isinstance(permissions, dict) and isinstance(permissions.get("deny"), list):
            permissions["deny"] = [rule for rule in permissions["deny"] if rule not in added]
        created = _strings(record.get("created")) if record else [
            "hooks", *(f"hooks.{event}" for event in desired_hooks(root)), "permissions", "permissions.deny",
        ]
        _prune(settings, created)
        if settings == {} and record.get("created_file"):
            path.unlink()
            changed.append(str(path))
        else:
            text = _render(settings, original)
            if text != original:
                _write(path, text)
                changed.append(str(path))
    if record or opted_out:
        _save_record(
            state_dir,
            {
                "settings": str(path),
                "hook_dirs": [],
                "deny_added": [],
                "created": [],
                "created_file": False,
                "opted_out": opted_out or bool(record.get("opted_out")),
            },
        )
    return changed


def opted_out(state_dir: Path) -> bool:
    return bool(load_record(state_dir).get("opted_out"))
