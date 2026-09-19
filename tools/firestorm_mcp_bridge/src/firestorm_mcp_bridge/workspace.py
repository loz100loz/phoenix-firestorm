"""Validated local LSL workspace manifests and debounced save detection."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "firestorm-mcp.json"
SUPPORTED_TARGET_KINDS = {"worn_attachment", "selected_object"}
SUPPORTED_SYNC_MODES = {"manual", "on_save"}


class WorkspaceError(ValueError):
    """Raised when a workspace or manifest violates the sync contract."""


@dataclass(frozen=True)
class ScriptMapping:
    device_key: str
    script_key: str
    path: Path
    relative_path: str
    task_script_name: str
    sync_mode: str


@dataclass(frozen=True)
class DeviceMapping:
    key: str
    target_kind: str
    target_name: str
    scripts: tuple[ScriptMapping, ...]


@dataclass(frozen=True)
class WorkspaceManifest:
    root: Path
    manifest_path: Path
    debounce_ms: int
    devices: tuple[DeviceMapping, ...]

    @property
    def scripts(self) -> tuple[ScriptMapping, ...]:
        return tuple(script for device in self.devices for script in device.scripts)


@dataclass(frozen=True)
class WorkspaceChange:
    device_key: str
    script_key: str
    relative_path: str
    task_script_name: str
    sync_mode: str
    sha256: str
    bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "device_key": self.device_key,
            "script_key": self.script_key,
            "relative_path": self.relative_path,
            "task_script_name": self.task_script_name,
            "sync_mode": self.sync_mode,
            "sha256": self.sha256,
            "bytes": self.bytes,
        }


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkspaceError(f"{label} must be an object")
    return value


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceError(f"{label} must be a non-empty string")
    return value


def _resolve_script_path(root: Path, value: Any, label: str) -> tuple[Path, str]:
    relative = _require_nonempty_string(value, label).replace("\\", "/")
    supplied = Path(relative)
    if supplied.is_absolute():
        raise WorkspaceError(f"{label} must be relative to the workspace root")
    resolved = (root / supplied).resolve()
    try:
        normalized = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise WorkspaceError(f"{label} escapes the workspace root") from exc
    if resolved.suffix.lower() != ".lsl":
        raise WorkspaceError(f"{label} must reference an .lsl file")
    if not resolved.is_file():
        raise WorkspaceError(f"{label} does not exist: {normalized}")
    return resolved, normalized


def load_workspace(root: Path) -> WorkspaceManifest:
    """Load and validate one workspace without following paths outside it."""

    root = root.resolve()
    if not root.is_dir():
        raise WorkspaceError(f"Workspace root does not exist: {root}")
    manifest_path = root / MANIFEST_FILENAME
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkspaceError(f"Workspace manifest is missing: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkspaceError(f"Workspace manifest is not valid JSON: {exc}") from exc
    document = _require_mapping(document, "manifest")
    if document.get("version") != 1:
        raise WorkspaceError("manifest version must be 1")
    unknown = sorted(set(document) - {"version", "debounce_ms", "devices"})
    if unknown:
        raise WorkspaceError(f"manifest has unsupported fields: {', '.join(unknown)}")

    debounce_ms = document.get("debounce_ms", 750)
    if not isinstance(debounce_ms, int) or debounce_ms < 100 or debounce_ms > 10_000:
        raise WorkspaceError("debounce_ms must be an integer between 100 and 10000")
    devices_data = _require_mapping(document.get("devices"), "devices")
    if not devices_data:
        raise WorkspaceError("devices cannot be empty")

    devices: list[DeviceMapping] = []
    seen_paths: set[Path] = set()
    for device_key, raw_device in devices_data.items():
        _require_nonempty_string(device_key, "device key")
        device = _require_mapping(raw_device, f"device {device_key!r}")
        unknown = sorted(set(device) - {"target", "scripts"})
        if unknown:
            raise WorkspaceError(
                f"device {device_key!r} has unsupported fields: {', '.join(unknown)}"
            )
        target = _require_mapping(device.get("target"), f"device {device_key!r} target")
        if set(target) != {"kind", "name"}:
            raise WorkspaceError(
                f"device {device_key!r} target must contain only kind and name"
            )
        target_kind = _require_nonempty_string(target.get("kind"), "target kind")
        if target_kind not in SUPPORTED_TARGET_KINDS:
            raise WorkspaceError(
                f"device {device_key!r} target kind must be one of "
                f"{', '.join(sorted(SUPPORTED_TARGET_KINDS))}"
            )
        target_name = _require_nonempty_string(target.get("name"), "target name")
        scripts_data = _require_mapping(device.get("scripts"), f"device {device_key!r} scripts")
        if not scripts_data:
            raise WorkspaceError(f"device {device_key!r} scripts cannot be empty")

        scripts: list[ScriptMapping] = []
        task_names: set[str] = set()
        for script_key, raw_script in scripts_data.items():
            _require_nonempty_string(script_key, "script key")
            script = _require_mapping(
                raw_script, f"device {device_key!r} script {script_key!r}"
            )
            unknown = sorted(set(script) - {"path", "task_script_name", "sync_mode"})
            if unknown:
                raise WorkspaceError(
                    f"script {device_key!r}/{script_key!r} has unsupported fields: "
                    f"{', '.join(unknown)}"
                )
            path, relative_path = _resolve_script_path(
                root, script.get("path"), f"script {device_key!r}/{script_key!r} path"
            )
            if path in seen_paths:
                raise WorkspaceError(f"LSL path is mapped more than once: {relative_path}")
            seen_paths.add(path)
            task_name = _require_nonempty_string(
                script.get("task_script_name"), "task_script_name"
            )
            if task_name in task_names:
                raise WorkspaceError(
                    f"device {device_key!r} maps task script name {task_name!r} more than once"
                )
            task_names.add(task_name)
            sync_mode = script.get("sync_mode", "manual")
            if sync_mode not in SUPPORTED_SYNC_MODES:
                raise WorkspaceError(
                    f"script {device_key!r}/{script_key!r} sync_mode must be manual or on_save"
                )
            scripts.append(
                ScriptMapping(
                    device_key=device_key,
                    script_key=script_key,
                    path=path,
                    relative_path=relative_path,
                    task_script_name=task_name,
                    sync_mode=sync_mode,
                )
            )
        devices.append(
            DeviceMapping(
                key=device_key,
                target_kind=target_kind,
                target_name=target_name,
                scripts=tuple(scripts),
            )
        )
    return WorkspaceManifest(
        root=root,
        manifest_path=manifest_path,
        debounce_ms=debounce_ms,
        devices=tuple(devices),
    )


def _file_state(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    if b"\0" in data:
        raise WorkspaceError(f"LSL source contains a NUL byte: {path}")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError(f"LSL source is not valid UTF-8: {path}") from exc
    return hashlib.sha256(data).hexdigest(), len(data)


class WorkspaceWatcher:
    """Poll a workspace and emit a change only after its content is stable."""

    def __init__(self, manifest: WorkspaceManifest) -> None:
        self.manifest = manifest
        self._baseline = {
            script.path: _file_state(script.path)[0] for script in manifest.scripts
        }
        self._pending: dict[Path, tuple[str, int, float]] = {}

    def poll(self, *, now: float | None = None) -> list[WorkspaceChange]:
        now = time.monotonic() if now is None else now
        changes: list[WorkspaceChange] = []
        for script in self.manifest.scripts:
            digest, size = _file_state(script.path)
            if digest == self._baseline[script.path]:
                self._pending.pop(script.path, None)
                continue
            pending = self._pending.get(script.path)
            if pending is None or pending[0] != digest:
                self._pending[script.path] = (digest, size, now)
                continue
            if (now - pending[2]) * 1000 < self.manifest.debounce_ms:
                continue
            self._baseline[script.path] = digest
            self._pending.pop(script.path, None)
            changes.append(
                WorkspaceChange(
                    device_key=script.device_key,
                    script_key=script.script_key,
                    relative_path=script.relative_path,
                    task_script_name=script.task_script_name,
                    sync_mode=script.sync_mode,
                    sha256=digest,
                    bytes=size,
                )
            )
        return changes


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate and summarize a workspace")
    validate.add_argument("root", type=Path)
    watch = subparsers.add_parser("watch", help="Print debounced LSL save events as JSON")
    watch.add_argument("root", type=Path)
    watch.add_argument("--poll-seconds", type=float, default=0.25)
    args = parser.parse_args(argv)
    manifest = load_workspace(args.root)
    if args.command == "validate":
        print(
            json.dumps(
                {
                    "valid": True,
                    "root": str(manifest.root),
                    "devices": len(manifest.devices),
                    "scripts": len(manifest.scripts),
                    "on_save": sum(s.sync_mode == "on_save" for s in manifest.scripts),
                    "manual": sum(s.sync_mode == "manual" for s in manifest.scripts),
                    "debounce_ms": manifest.debounce_ms,
                },
                sort_keys=True,
            )
        )
        return
    if args.poll_seconds < 0.05 or args.poll_seconds > 10:
        parser.error("--poll-seconds must be between 0.05 and 10")
    watcher = WorkspaceWatcher(manifest)
    while True:
        for change in watcher.poll():
            print(json.dumps(change.as_dict(), sort_keys=True), flush=True)
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
