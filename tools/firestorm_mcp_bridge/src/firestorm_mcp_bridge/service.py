"""Allowlisted viewer operations exposed by the MCP bridge."""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .leap import LeapConnection, LeapError

NULL_UUID = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class Snapshot:
    path: Path
    metadata: dict[str, Any]


class Stage0Service:
    """Stage 0 operations plus one guarded, reversible test-HUD script proof."""

    def __init__(
        self,
        leap: LeapConnection,
        capture_dir: Path,
        allowed_attachment_names: tuple[str, ...],
        *,
        script_backup_dir: Path | None = None,
        request_timeout: float = 15.0,
        touch_cooldown: float = 1.0,
    ) -> None:
        self.leap = leap
        self.capture_dir = capture_dir.resolve()
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.script_backup_dir = (
            script_backup_dir.resolve()
            if script_backup_dir is not None
            else (self.capture_dir.parent / "script-backups").resolve()
        )
        self.allowed_attachment_names = tuple(dict.fromkeys(allowed_attachment_names))
        self.request_timeout = request_timeout
        self.touch_cooldown = touch_cooldown
        self._apis: dict[str, Any] | None = None
        self._touch_lock = threading.Lock()
        self._script_proof_lock = threading.Lock()
        self._last_touch = 0.0

    def discover_viewer_apis(self, *, refresh: bool = False) -> dict[str, Any]:
        if refresh or self._apis is None:
            self._apis = self.leap.discover_apis(timeout=self.request_timeout)
        return {
            "count": len(self._apis),
            "apis": self._apis,
            "required_stage0": {
                name: name in self._apis
                for name in ("LLAgent", "LLViewerWindow")
            },
            "required_script_proof": {
                "LLScriptAutomation": "LLScriptAutomation" in self._apis,
            },
        }

    def viewer_status(self) -> dict[str, Any]:
        discovery = self.discover_viewer_apis()
        avatar_id = NULL_UUID
        if discovery["required_stage0"]["LLAgent"]:
            response = self.leap.request(
                "LLAgent",
                {"op": "getID"},
                timeout=self.request_timeout,
            )
            avatar_id = str(response.get("id", NULL_UUID))
        return {
            "leap_connected": self.leap.connected,
            "avatar_id": avatar_id,
            "logged_in": avatar_id != NULL_UUID,
            "leap_features": self.leap.features,
            "api_count": discovery["count"],
            "required_stage0": discovery["required_stage0"],
            "required_script_proof": discovery["required_script_proof"],
            "allowed_attachment_names": list(self.allowed_attachment_names),
        }

    def list_attachments(self) -> list[dict[str, Any]]:
        self._require_api("LLAgent")
        response = self.leap.request(
            "LLAgent",
            {"op": "getAttachedObjectsList"},
            timeout=self.request_timeout,
        )
        attachments = response.get("attachments", [])
        if not isinstance(attachments, list):
            raise LeapError("Firestorm returned an invalid attachments result")
        normalized = [dict(item) for item in attachments if isinstance(item, dict)]
        normalized.sort(key=lambda item: (str(item.get("name", "")), str(item.get("object_id", ""))))
        return normalized

    def touch_test_hud(
        self,
        attachment_name: str = "MCP POC ROOT",
        inventory_item_id: str | None = None,
        face: int = 0,
    ) -> dict[str, Any]:
        """Touch one currently worn, explicitly allowlisted attachment root."""

        if face < 0 or face > 31:
            raise LeapError("face must be between 0 and 31")
        target = self._resolve_allowed_attachment(attachment_name, inventory_item_id)
        object_id = str(target["object_id"])

        with self._touch_lock:
            now = time.monotonic()
            remaining = self.touch_cooldown - (now - self._last_touch)
            if remaining > 0:
                raise LeapError(f"Touch rate limit active; retry in {remaining:.2f} seconds")
            self.leap.notify(
                "LLAgent",
                {"op": "requestTouch", "obj_uuid": object_id, "face": face},
            )
            self._last_touch = now

        return {
            "sent": True,
            "confirmed": False,
            "object_id": object_id,
            "inventory_item_id": str(target.get("inventory_item_id", "")),
            "name": attachment_name,
            "face": face,
            "note": "Firestorm's existing requestTouch operation does not send an acknowledgement.",
        }

    def list_test_hud_scripts(
        self,
        attachment_name: str = "MCP POC ROOT",
    ) -> list[dict[str, Any]]:
        """List scripts only inside one exact allowlisted, currently worn HUD."""

        _, scripts = self._get_test_hud_scripts(attachment_name)
        return [
            {
                "name": str(item.get("name", "")),
                "description": str(item.get("description", "")),
                "can_copy": bool(item.get("can_copy")),
                "can_modify": bool(item.get("can_modify")),
            }
            for item in scripts
        ]

    def prove_test_hud_script_round_trip(
        self,
        attachment_name: str = "MCP POC ROOT",
    ) -> dict[str, Any]:
        """Append a harmless marker to the sole test script, verify, and restore it."""

        with self._script_proof_lock:
            target, scripts = self._get_test_hud_scripts(attachment_name)
            if len(scripts) != 1:
                raise LeapError(
                    "The reversible proof requires exactly one LSL script in the allowlisted test HUD"
                )
            script = scripts[0]
            if not script.get("can_copy") or not script.get("can_modify"):
                raise LeapError("The sole test-HUD script is not both copyable and modifiable")

            object_id = str(target["object_id"])
            item_id = self._validated_uuid(script.get("item_id"), "script item")
            script_name = str(script.get("name", ""))
            original = self._get_script_source(object_id, item_id)
            backup_path = self._write_script_backup(original)

            marker = f"// Firestorm MCP reversible proof {uuid.uuid4().hex}"
            candidate = original
            if candidate and not candidate.endswith(("\n", "\r")):
                candidate += "\n"
            candidate += marker + "\n"

            primary_error: Exception | None = None
            initial_result: dict[str, Any] | None = None
            restore_result: dict[str, Any] | None = None
            try:
                initial_result = self._update_script_source(
                    object_id,
                    item_id,
                    candidate,
                )
                if not initial_result.get("compiled"):
                    raise LeapError("Firestorm reported that the marked script did not compile")
                self._wait_for_script_source(object_id, item_id, candidate)
            except Exception as exc:
                primary_error = exc

            try:
                restore_result = self._update_script_source(
                    object_id,
                    item_id,
                    original,
                )
                if not restore_result.get("compiled"):
                    raise LeapError("Firestorm reported that the original script did not recompile")
                self._wait_for_script_source(object_id, item_id, original)
            except Exception as restore_error:
                message = (
                    "The test-HUD script could not be fully restored. "
                    f"The exact local backup is at {backup_path}. "
                    f"Restore error: {restore_error}"
                )
                if primary_error is not None:
                    message += f". Initial proof error: {primary_error}"
                raise LeapError(message) from restore_error

            if primary_error is not None:
                raise LeapError(
                    "The write proof failed, but the exact original source was restored and recompiled. "
                    f"Backup: {backup_path}. Error: {primary_error}"
                ) from primary_error

            return {
                "proved": True,
                "attachment_name": attachment_name,
                "script_name": script_name,
                "backup_path": str(backup_path),
                "original_bytes": len(original.encode("utf-8")),
                "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "marker_compiled": bool(initial_result and initial_result.get("compiled")),
                "marker_verified": True,
                "original_restored": True,
                "original_recompiled": bool(restore_result and restore_result.get("compiled")),
                "runtime_state_preserved": True,
            }

    def capture_viewer(
        self,
        *,
        width: int = 1600,
        height: int = 900,
        show_ui: bool = False,
        show_hud: bool = True,
    ) -> Snapshot:
        self._require_api("LLViewerWindow")
        if width < 320 or width > 3840:
            raise LeapError("width must be between 320 and 3840")
        if height < 200 or height > 2160:
            raise LeapError("height must be between 200 and 2160")

        filename = self.capture_dir / f"firestorm-stage0-{uuid.uuid4().hex}.png"
        response = self.leap.request(
            "LLViewerWindow",
            {
                "op": "saveSnapshot",
                "filename": str(filename),
                "width": width,
                "height": height,
                "showui": show_ui,
                "showhud": show_hud,
                "rebuild": False,
                "type": "COLOR",
            },
            timeout=max(self.request_timeout, 30.0),
        )
        if not response.get("ok"):
            raise LeapError("Firestorm reported that the snapshot could not be saved")
        if not filename.is_file() or filename.stat().st_size == 0:
            raise LeapError("Firestorm reported success but no snapshot file was created")

        return Snapshot(
            path=filename,
            metadata={
                "filename": str(filename),
                "width": width,
                "height": height,
                "show_ui": show_ui,
                "show_hud": show_hud,
                "bytes": filename.stat().st_size,
            },
        )

    def _require_api(self, name: str) -> None:
        discovery = self.discover_viewer_apis()
        if name not in discovery["apis"]:
            raise LeapError(f"The running Firestorm viewer does not expose {name}")

    @staticmethod
    def _validated_uuid(value: Any, label: str) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise LeapError(f"Firestorm returned an invalid {label} UUID") from exc

    def _resolve_allowed_attachment(
        self,
        attachment_name: str,
        inventory_item_id: str | None = None,
    ) -> dict[str, Any]:
        if attachment_name not in self.allowed_attachment_names:
            raise LeapError(
                f"Attachment {attachment_name!r} is not allowlisted for this bridge session"
            )
        if inventory_item_id is not None:
            inventory_item_id = self._validated_uuid(inventory_item_id, "inventory item")

        matches = [
            item
            for item in self.list_attachments()
            if item.get("name") == attachment_name
            and (
                inventory_item_id is None
                or str(item.get("inventory_item_id")) == inventory_item_id
            )
        ]
        if not matches:
            raise LeapError(
                "The allowlisted attachment is not currently worn, or its inventory item ID did not match"
            )
        if len(matches) > 1 and inventory_item_id is None:
            raise LeapError(
                "More than one worn attachment has that name; provide its inventory_item_id"
            )

        target = matches[0]
        target["object_id"] = self._validated_uuid(target.get("object_id"), "attachment object")
        return target

    def _get_test_hud_scripts(
        self,
        attachment_name: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        self._require_api("LLScriptAutomation")
        target = self._resolve_allowed_attachment(attachment_name)
        response = self.leap.request(
            "LLScriptAutomation",
            {"op": "getTaskInventory", "object_id": target["object_id"]},
            timeout=max(self.request_timeout, 45.0),
        )
        items = response.get("items")
        if not isinstance(items, list):
            raise LeapError("Firestorm returned an invalid task inventory result")
        scripts = [dict(item) for item in items if isinstance(item, dict) and item.get("is_script")]
        scripts.sort(key=lambda item: str(item.get("name", "")))
        return target, scripts

    def _get_script_source(self, object_id: str, item_id: str) -> str:
        response = self.leap.request(
            "LLScriptAutomation",
            {"op": "getScriptSource", "object_id": object_id, "item_id": item_id},
            timeout=max(self.request_timeout, 75.0),
        )
        source = response.get("source")
        if not isinstance(source, str):
            raise LeapError("Firestorm returned an invalid script source result")
        return source

    def _update_script_source(
        self,
        object_id: str,
        item_id: str,
        source: str,
    ) -> dict[str, Any]:
        return self.leap.request(
            "LLScriptAutomation",
            {
                "op": "updateScriptSource",
                "object_id": object_id,
                "item_id": item_id,
                "source": source,
            },
            timeout=max(self.request_timeout, 150.0),
        )

    def _wait_for_script_source(
        self,
        object_id: str,
        item_id: str,
        expected: str,
    ) -> None:
        deadline = time.monotonic() + 20.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                if self._get_script_source(object_id, item_id) == expected:
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(0.5)
        detail = f": {last_error}" if last_error else ""
        raise LeapError(f"Timed out waiting for exact script source read-back{detail}")

    def _write_script_backup(self, source: str) -> Path:
        for parent in (self.script_backup_dir, *self.script_backup_dir.parents):
            if (parent / ".git").exists():
                raise LeapError("Script backups must be stored outside a Git working tree")
        self.script_backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        path = self.script_backup_dir / f"hud-script-{stamp}-{uuid.uuid4().hex[:8]}.lsl"
        with path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(source)
            stream.flush()
        with path.open("r", encoding="utf-8", newline="") as stream:
            if stream.read() != source:
                raise LeapError("The local script backup did not verify byte-for-byte")
        return path
