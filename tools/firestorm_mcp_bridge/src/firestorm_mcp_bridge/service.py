"""Allowlisted viewer operations exposed by the MCP bridge."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import unified_diff
from pathlib import Path
from typing import Any

from .leap import LeapConnection, LeapError
from .workspace import WorkspaceError, load_workspace

NULL_UUID = "00000000-0000-0000-0000-000000000000"
MAX_SCRIPT_SOURCE_BYTES = 64 * 1024
MAX_PATCH_FRAGMENT_BYTES = 16 * 1024
EDIT_PLAN_TTL = timedelta(minutes=30)
EDIT_CONFIRMATION = "APPLY MCP POC ROOT"
TARGET_HANDLE_TTL_SECONDS = 10 * 60.0


@dataclass(frozen=True)
class Snapshot:
    path: Path
    metadata: dict[str, Any]


class Stage0Service:
    """Guarded viewer operations plus read-only selected-target identity."""

    def __init__(
        self,
        leap: LeapConnection,
        capture_dir: Path,
        allowed_attachment_names: tuple[str, ...],
        *,
        script_backup_dir: Path | None = None,
        request_timeout: float = 15.0,
        touch_cooldown: float = 1.0,
        target_handle_ttl: float = TARGET_HANDLE_TTL_SECONDS,
        monotonic_clock: Callable[[], float] = time.monotonic,
        workspace_roots: dict[str, Path] | None = None,
    ) -> None:
        if target_handle_ttl <= 0:
            raise ValueError("target_handle_ttl must be positive")
        self.leap = leap
        self.capture_dir = capture_dir.resolve()
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.script_backup_dir = (
            script_backup_dir.resolve()
            if script_backup_dir is not None
            else (self.capture_dir.parent / "script-backups").resolve()
        )
        self.script_edit_plan_dir = (self.script_backup_dir.parent / "script-edit-plans").resolve()
        self.allowed_attachment_names = tuple(dict.fromkeys(allowed_attachment_names))
        self.request_timeout = request_timeout
        self.touch_cooldown = touch_cooldown
        self.target_handle_ttl = target_handle_ttl
        self._monotonic_clock = monotonic_clock
        self.workspace_roots: dict[str, Path] = {}
        for key, root in (workspace_roots or {}).items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key):
                raise ValueError(
                    "workspace keys must be 1-64 lowercase letters, digits, hyphens, or underscores"
                )
            resolved = root.resolve()
            if not resolved.is_dir():
                raise ValueError(f"workspace root does not exist: {resolved}")
            self.workspace_roots[key] = resolved
        self.session_fingerprint = uuid.uuid4().hex
        self._apis: dict[str, Any] | None = None
        self._touch_lock = threading.Lock()
        self._script_proof_lock = threading.Lock()
        self._target_handle_lock = threading.Lock()
        self._target_handles: dict[str, dict[str, Any]] = {}
        self._workspace_baseline_lock = threading.Lock()
        self._workspace_baselines: dict[tuple[str, str, str, str], str] = {}
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
            "workspace_keys": sorted(self.workspace_roots),
            "session_fingerprint": self.session_fingerprint,
        }

    def viewer_context(self) -> dict[str, Any]:
        """Return the non-secret identity of this viewer/avatar bridge session."""

        self._require_api("LLScriptAutomation")
        response = self.leap.request(
            "LLScriptAutomation",
            {"op": "getViewerContext"},
            timeout=self.request_timeout,
        )
        avatar_id = self._validated_uuid(response.get("avatar_id"), "avatar")
        region_id = self._validated_uuid(response.get("region_id"), "region")
        logged_in = bool(response.get("logged_in"))
        if logged_in and (avatar_id == NULL_UUID or region_id == NULL_UUID):
            raise LeapError("Firestorm returned an incomplete logged-in viewer context")
        return {
            "session_fingerprint": self.session_fingerprint,
            "leap_connected": self.leap.connected,
            "logged_in": logged_in,
            "avatar_id": avatar_id,
            "avatar_name": str(response.get("avatar_name", "")),
            "grid_id": str(response.get("grid_id", "")),
            "grid_label": str(response.get("grid_label", "")),
            "region_id": region_id,
            "region_name": str(response.get("region_name", "")),
            "agent_position_region": response.get("agent_position_region"),
            "agent_position_global": response.get("agent_position_global"),
        }

    def inspect_selected_target(self) -> dict[str, Any]:
        """Inspect one selected linkset and issue a handle only for a safe target."""

        raw, scripts, identity, identity_sha256 = self._read_selected_target()
        eligible, blocked_reason = self._target_eligibility(raw)
        result = self._public_target_summary(raw, scripts, identity_sha256)
        result["eligible_for_future_mutation"] = eligible
        result["blocked_reason"] = blocked_reason
        result["target_handle"] = None
        result["expires_at"] = None

        if not eligible:
            return result

        now = self._monotonic_clock()
        target_handle = uuid.uuid4().hex
        expires_at = datetime.now(UTC) + timedelta(seconds=self.target_handle_ttl)
        with self._target_handle_lock:
            self._cleanup_expired_target_handles(now)
            self._target_handles[target_handle] = {
                "identity": identity,
                "identity_sha256": identity_sha256,
                "expires_monotonic": now + self.target_handle_ttl,
                "expires_at": expires_at.isoformat(),
            }
        result["target_handle"] = target_handle
        result["expires_at"] = expires_at.isoformat()
        return result

    def revalidate_selected_target(self, target_handle: str) -> dict[str, Any]:
        """Re-resolve a selected target and reject expired or changed identity."""

        raw, scripts, identity_sha256, entry = self._revalidate_target_handle(
            target_handle
        )

        result = self._public_target_summary(raw, scripts, identity_sha256)
        result.update(
            {
                "valid": True,
                "target_handle": target_handle,
                "expires_at": str(entry["expires_at"]),
            }
        )
        return result

    def workspace_status(
        self,
        workspace_key: str,
        device_key: str,
        script_key: str,
        target_handle: str,
    ) -> dict[str, Any]:
        """Compare one allowlisted local mapping with permitted selected-object source."""

        root = self.workspace_roots.get(workspace_key)
        if root is None:
            raise LeapError("The workspace key is not allowlisted for this bridge session")
        try:
            manifest = load_workspace(root)
        except WorkspaceError as exc:
            raise LeapError(f"The allowlisted workspace is invalid: {exc}") from exc

        device = next((item for item in manifest.devices if item.key == device_key), None)
        if device is None:
            raise LeapError("The device key is not present in the allowlisted workspace")
        script = next((item for item in device.scripts if item.script_key == script_key), None)
        if script is None:
            raise LeapError("The script key is not present in the selected workspace device")

        raw, scripts, identity_sha256, _ = self._revalidate_target_handle(target_handle)
        common = {
            "workspace_key": workspace_key,
            "device_key": device.key,
            "script_key": script.script_key,
            "relative_path": script.relative_path,
            "target_kind": device.target_kind,
            "expected_target_name": device.target_name,
            "task_script_name": script.task_script_name,
            "sync_mode": script.sync_mode,
            "target_identity_sha256": identity_sha256,
            "source_returned": False,
            "writes_performed": False,
            "baseline_known": False,
            "baseline_sha256": None,
            "local": None,
            "remote": None,
        }

        selected_name = str(raw.get("root_name") or raw.get("object_name") or "")
        expected_attachment = device.target_kind == "worn_attachment"
        if bool(raw.get("is_attachment")) != expected_attachment:
            return {
                **common,
                "status": "blocked",
                "reason": "The selected target kind does not match the workspace mapping",
                "selected_target_name": selected_name,
            }
        if selected_name != device.target_name:
            return {
                **common,
                "status": "blocked",
                "reason": "The selected target name does not match the workspace mapping",
                "selected_target_name": selected_name,
            }

        matches = [item for item in scripts if str(item.get("name", "")) == script.task_script_name]
        if not matches:
            local_source = self._read_workspace_source(script.path, root)
            return {
                **common,
                "status": "missing",
                "reason": "The mapped task script is missing from the selected prim",
                "selected_target_name": selected_name,
                "local": self._source_summary(local_source),
            }
        if len(matches) != 1:
            return {
                **common,
                "status": "blocked",
                "reason": "More than one task script has the mapped exact name",
                "selected_target_name": selected_name,
            }

        item = matches[0]
        if not bool(item.get("can_copy")) or not bool(item.get("can_modify")):
            return {
                **common,
                "status": "blocked",
                "reason": "The mapped task script is not both copyable and modifiable",
                "selected_target_name": selected_name,
            }

        local_source = self._read_workspace_source(script.path, root)
        remote_source = self._get_script_source(raw["object_id"], item["item_id"])
        _, _, verified_identity_sha256, _ = self._revalidate_target_handle(target_handle)
        if verified_identity_sha256 != identity_sha256:
            raise LeapError("The selected target changed during workspace comparison")
        local = self._source_summary(local_source)
        remote = self._source_summary(remote_source)
        baseline_key = (workspace_key, device.key, script.script_key, identity_sha256)
        with self._workspace_baseline_lock:
            baseline = self._workspace_baselines.get(baseline_key)
            if local["sha256"] == remote["sha256"]:
                status = "unchanged"
                reason = "Local and in-world source hashes match"
                self._workspace_baselines[baseline_key] = local["sha256"]
                baseline = local["sha256"]
            elif baseline is None:
                status = "conflict"
                reason = "Local and in-world source differ without a verified sync baseline"
            elif local["sha256"] != baseline and remote["sha256"] == baseline:
                status = "local_ahead"
                reason = "Only the local source changed from the verified baseline"
            elif local["sha256"] == baseline and remote["sha256"] != baseline:
                status = "remote_ahead"
                reason = "Only the in-world source changed from the verified baseline"
            else:
                status = "conflict"
                reason = "Both local and in-world source changed from the verified baseline"

        return {
            **common,
            "status": status,
            "reason": reason,
            "selected_target_name": selected_name,
            "baseline_known": baseline is not None,
            "baseline_sha256": baseline,
            "local": local,
            "remote": remote,
        }

    def _revalidate_target_handle(
        self, target_handle: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str, dict[str, Any]]:
        """Return internal live target data only after exact handle revalidation."""

        if not re.fullmatch(r"[0-9a-f]{32}", target_handle):
            raise LeapError("target_handle must be a 32-character lowercase hexadecimal value")
        now = self._monotonic_clock()
        with self._target_handle_lock:
            entry = self._target_handles.get(target_handle)
            if entry is None:
                raise LeapError("The target handle is unknown to this viewer session")
            if now >= float(entry["expires_monotonic"]):
                self._target_handles.pop(target_handle, None)
                raise LeapError("The target handle has expired")

        try:
            raw, scripts, identity, identity_sha256 = self._read_selected_target()
        except Exception:
            with self._target_handle_lock:
                self._target_handles.pop(target_handle, None)
            raise
        eligible, blocked_reason = self._target_eligibility(raw)
        if not eligible:
            with self._target_handle_lock:
                self._target_handles.pop(target_handle, None)
            raise LeapError(f"The selected target is no longer eligible: {blocked_reason}")
        if identity != entry["identity"] or identity_sha256 != entry["identity_sha256"]:
            with self._target_handle_lock:
                self._target_handles.pop(target_handle, None)
            raise LeapError("The selected target changed; the stale handle was invalidated")

        finish_now = self._monotonic_clock()
        with self._target_handle_lock:
            if self._target_handles.get(target_handle) is not entry:
                raise LeapError("The target handle was invalidated during revalidation")
            if finish_now >= float(entry["expires_monotonic"]):
                self._target_handles.pop(target_handle, None)
                raise LeapError("The target handle expired during revalidation")

        return raw, scripts, identity_sha256, entry

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

    def add_third_touch_color(
        self,
        attachment_name: str = "MCP POC ROOT",
    ) -> dict[str, Any]:
        """Persistently extend the exact red/green test script with blue."""

        with self._script_proof_lock:
            target, scripts = self._get_test_hud_scripts(attachment_name)
            if len(scripts) != 1:
                raise LeapError(
                    "The three-color edit requires exactly one LSL script in the allowlisted test HUD"
                )
            script = scripts[0]
            if not script.get("can_copy") or not script.get("can_modify"):
                raise LeapError("The sole test-HUD script is not both copyable and modifiable")

            object_id = str(target["object_id"])
            item_id = self._validated_uuid(script.get("item_id"), "script item")
            script_name = str(script.get("name", ""))
            original = self._get_script_source(object_id, item_id)
            candidate = self._build_three_color_touch_source(original)
            backup_path = self._write_script_backup(original)

            primary_error: Exception | None = None
            update_result: dict[str, Any] | None = None
            try:
                update_result = self._update_script_source(object_id, item_id, candidate)
                if not update_result.get("compiled"):
                    raise LeapError("Firestorm reported that the three-color script did not compile")
                self._wait_for_script_source(object_id, item_id, candidate)
            except Exception as exc:
                primary_error = exc

            if primary_error is not None:
                try:
                    restore_result = self._update_script_source(object_id, item_id, original)
                    if not restore_result.get("compiled"):
                        raise LeapError("Firestorm reported that the original script did not recompile")
                    self._wait_for_script_source(object_id, item_id, original)
                except Exception as restore_error:
                    raise LeapError(
                        "The three-color edit failed and the original could not be fully restored. "
                        f"The exact local backup is at {backup_path}. "
                        f"Restore error: {restore_error}. Edit error: {primary_error}"
                    ) from restore_error
                raise LeapError(
                    "The three-color edit failed, but the exact original source was restored and recompiled. "
                    f"Backup: {backup_path}. Error: {primary_error}"
                ) from primary_error

            return {
                "updated": True,
                "attachment_name": attachment_name,
                "script_name": script_name,
                "backup_path": str(backup_path),
                "original_bytes": len(original.encode("utf-8")),
                "updated_bytes": len(candidate.encode("utf-8")),
                "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "updated_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
                "third_color": {"name": "blue", "rgb": [0.0, 0.0, 1.0]},
                "compiled": bool(update_result and update_result.get("compiled")),
                "source_verified": True,
                "runtime_state_preserved": True,
            }

    def preview_test_hud_script_edit(
        self,
        operation: str,
        find_text: str,
        replacement_text: str,
        expected_occurrences: int = 1,
    ) -> dict[str, Any]:
        """Create a short-lived, outside-Git edit plan without uploading."""

        if operation not in {"replace", "append"}:
            raise LeapError("operation must be 'replace' or 'append'")
        if "\0" in find_text or "\0" in replacement_text:
            raise LeapError("Patch fragments cannot contain a NUL byte")
        if len(find_text.encode("utf-8")) > MAX_PATCH_FRAGMENT_BYTES:
            raise LeapError("find_text exceeds the 16 KiB safety limit")
        if len(replacement_text.encode("utf-8")) > MAX_PATCH_FRAGMENT_BYTES:
            raise LeapError("replacement_text exceeds the 16 KiB safety limit")
        if expected_occurrences < 1 or expected_occurrences > 100:
            raise LeapError("expected_occurrences must be between 1 and 100")

        with self._script_proof_lock:
            self._cleanup_expired_script_edit_plans()
            target, scripts = self._get_test_hud_scripts("MCP POC ROOT")
            if len(scripts) != 1:
                raise LeapError(
                    "Script editing requires exactly one LSL script in MCP POC ROOT"
                )
            script = scripts[0]
            if not script.get("can_copy") or not script.get("can_modify"):
                raise LeapError("The sole test-HUD script is not both copyable and modifiable")

            object_id = str(target["object_id"])
            item_id = self._validated_uuid(script.get("item_id"), "script item")
            script_name = str(script.get("name", ""))
            original = self._get_script_source(object_id, item_id)

            if operation == "replace":
                if not find_text:
                    raise LeapError("find_text cannot be empty for a replace operation")
                occurrences = original.count(find_text)
                if occurrences != expected_occurrences:
                    raise LeapError(
                        "The exact find_text occurrence count did not match; no edit plan was created"
                    )
                candidate = original.replace(find_text, replacement_text)
                separator_added = False
            else:
                if find_text:
                    raise LeapError("find_text must be empty for an append operation")
                occurrences = 0
                if original and not original.endswith(("\n", "\r")):
                    original_suffix = "\n"
                else:
                    original_suffix = ""
                separator_added = bool(original_suffix)
                candidate = original + original_suffix + replacement_text

            if candidate == original:
                raise LeapError("The proposed edit does not change the script")
            if len(candidate.encode("utf-8")) > MAX_SCRIPT_SOURCE_BYTES:
                raise LeapError("The proposed script exceeds the 64 KiB safety limit")

            created = datetime.now(UTC)
            expires = created + EDIT_PLAN_TTL
            plan_id = uuid.uuid4().hex
            plan = {
                "version": 1,
                "plan_id": plan_id,
                "created_at": created.isoformat(),
                "expires_at": expires.isoformat(),
                "attachment_name": "MCP POC ROOT",
                "script_name": script_name,
                "operation": operation,
                "occurrences": occurrences,
                "original": original,
                "candidate": candidate,
                "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "candidate_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
            }
            _, diff_path = self._write_script_edit_plan(plan)
            return {
                "planned": True,
                "plan_id": plan_id,
                "attachment_name": "MCP POC ROOT",
                "script_name": script_name,
                "operation": operation,
                "occurrences": occurrences,
                "separator_added": separator_added,
                "original_bytes": len(original.encode("utf-8")),
                "candidate_bytes": len(candidate.encode("utf-8")),
                "original_sha256": plan["original_sha256"],
                "candidate_sha256": plan["candidate_sha256"],
                "diff_path": str(diff_path),
                "expires_at": expires.isoformat(),
                "confirmation_required": EDIT_CONFIRMATION,
                "source_returned": False,
            }

    def apply_test_hud_script_edit(
        self,
        plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        """Apply one exact previewed plan, verify it, and restore on failure."""

        if confirmation != EDIT_CONFIRMATION:
            raise LeapError(f"confirmation must exactly equal {EDIT_CONFIRMATION!r}")
        if not re.fullmatch(r"[0-9a-f]{32}", plan_id):
            raise LeapError("plan_id is invalid")

        with self._script_proof_lock:
            plan_path = self.script_edit_plan_dir / f"{plan_id}.json"
            if not plan_path.is_file():
                raise LeapError("The edit plan does not exist or has already been consumed")
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise LeapError("The edit plan could not be read safely") from exc
            if not isinstance(plan, dict) or plan.get("plan_id") != plan_id:
                raise LeapError("The edit plan is invalid")
            try:
                expires = datetime.fromisoformat(str(plan["expires_at"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise LeapError("The edit plan expiry is invalid") from exc
            if datetime.now(UTC) >= expires:
                self._remove_script_edit_plan(plan_id)
                raise LeapError("The edit plan has expired; create a fresh preview")

            original = plan.get("original")
            candidate = plan.get("candidate")
            if not isinstance(original, str) or not isinstance(candidate, str):
                raise LeapError("The edit plan source payload is invalid")
            if hashlib.sha256(original.encode("utf-8")).hexdigest() != plan.get(
                "original_sha256"
            ) or hashlib.sha256(candidate.encode("utf-8")).hexdigest() != plan.get(
                "candidate_sha256"
            ):
                raise LeapError("The edit plan failed its integrity check")

            target, scripts = self._get_test_hud_scripts("MCP POC ROOT")
            if len(scripts) != 1:
                raise LeapError(
                    "Script editing requires exactly one LSL script in MCP POC ROOT"
                )
            script = scripts[0]
            if not script.get("can_copy") or not script.get("can_modify"):
                raise LeapError("The sole test-HUD script is not both copyable and modifiable")
            object_id = str(target["object_id"])
            item_id = self._validated_uuid(script.get("item_id"), "script item")
            current = self._get_script_source(object_id, item_id)
            if current != original:
                self._remove_script_edit_plan(plan_id)
                raise LeapError(
                    "The live script changed after preview; the stale plan was not applied"
                )

            backup_path = self._write_script_backup(original)
            primary_error: Exception | None = None
            update_result: dict[str, Any] | None = None
            try:
                update_result = self._update_script_source(object_id, item_id, candidate)
                if not update_result.get("compiled"):
                    raise LeapError("Firestorm reported that the edited script did not compile")
                self._wait_for_script_source(object_id, item_id, candidate)
            except Exception as exc:
                primary_error = exc

            if primary_error is not None:
                try:
                    restore_result = self._update_script_source(object_id, item_id, original)
                    if not restore_result.get("compiled"):
                        raise LeapError("Firestorm reported that the original script did not recompile")
                    self._wait_for_script_source(object_id, item_id, original)
                except Exception as restore_error:
                    raise LeapError(
                        "The planned edit failed and the original could not be fully restored. "
                        f"The exact local backup is at {backup_path}. "
                        f"Restore error: {restore_error}. Edit error: {primary_error}"
                    ) from restore_error
                self._remove_script_edit_plan(plan_id)
                raise LeapError(
                    "The planned edit failed, but the exact original source was restored and recompiled. "
                    f"Backup: {backup_path}. Error: {primary_error}"
                ) from primary_error

            self._remove_script_edit_plan(plan_id)
            return {
                "applied": True,
                "plan_id": plan_id,
                "attachment_name": "MCP POC ROOT",
                "script_name": str(script.get("name", "")),
                "backup_path": str(backup_path),
                "original_bytes": len(original.encode("utf-8")),
                "updated_bytes": len(candidate.encode("utf-8")),
                "original_sha256": plan["original_sha256"],
                "updated_sha256": plan["candidate_sha256"],
                "compiled": bool(update_result and update_result.get("compiled")),
                "source_verified": True,
                "runtime_state_preserved": True,
                "plan_consumed": True,
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

    def _read_selected_target(
        self,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], str]:
        self._require_api("LLScriptAutomation")
        response = self.leap.request(
            "LLScriptAutomation",
            {"op": "inspectSelection"},
            timeout=self.request_timeout,
        )
        raw = dict(response)

        for field, label in (
            ("avatar_id", "avatar"),
            ("region_id", "region"),
            ("root_id", "selected root"),
            ("object_id", "selected object"),
            ("owner_id", "selected owner"),
            ("creator_id", "selected creator"),
            ("group_id", "selected group"),
            ("attachment_item_id", "attachment item"),
        ):
            raw[field] = self._validated_uuid(raw.get(field), label)
        for field in ("avatar_id", "region_id", "root_id", "object_id"):
            if raw[field] == NULL_UUID:
                raise LeapError(f"Firestorm returned a null {field.replace('_', ' ')}")
        if bool(raw.get("group_owned")):
            if raw["group_id"] == NULL_UUID:
                raise LeapError("Firestorm returned a group-owned target without a group id")
        elif raw["owner_id"] == NULL_UUID:
            raise LeapError("Firestorm returned a null owner id")

        link_ids = raw.get("link_ids")
        if not isinstance(link_ids, list) or not link_ids:
            raise LeapError("Firestorm returned an invalid selected linkset identity")
        raw["link_ids"] = [
            self._validated_uuid(value, "linkset object") for value in link_ids
        ]
        if any(value == NULL_UUID for value in raw["link_ids"]):
            raise LeapError("Firestorm returned a null linkset object UUID")

        try:
            raw["selection_object_count"] = int(raw.get("selection_object_count"))
            raw["selection_root_count"] = int(raw.get("selection_root_count"))
            raw["link_number"] = int(raw.get("link_number"))
            raw["link_count"] = int(raw.get("link_count"))
            raw["face_count"] = int(raw.get("face_count"))
        except (TypeError, ValueError) as exc:
            raise LeapError("Firestorm returned invalid selected-object counts") from exc
        if raw["link_count"] != len(raw["link_ids"]):
            raise LeapError("The selected linkset changed while Firestorm described it")
        if not 1 <= raw["selection_object_count"] <= raw["link_count"]:
            raise LeapError("Firestorm returned an invalid selected-object count")
        if (
            raw["selection_root_count"] != 1
            and raw["selection_object_count"] != 1
        ):
            raise LeapError("Select exactly one linkset or one linked prim in Firestorm")
        if raw["selection_root_count"] not in (0, 1):
            raise LeapError("Firestorm returned an ambiguous selected-linkset count")
        if len(set(raw["link_ids"])) != len(raw["link_ids"]):
            raise LeapError("Firestorm returned duplicate linkset object UUIDs")
        if raw["link_ids"][0] != raw["root_id"]:
            raise LeapError("Firestorm returned an inconsistent selected root identity")
        if raw["object_id"] not in raw["link_ids"]:
            raise LeapError("Firestorm returned a selected object outside its linkset")
        expected_is_root = raw["object_id"] == raw["root_id"]
        if bool(raw.get("is_root")) != expected_is_root:
            raise LeapError("Firestorm returned an inconsistent selected-object role")
        expected_link_number = (
            0
            if expected_is_root and raw["link_count"] == 1
            else raw["link_ids"].index(raw["object_id"]) + 1
        )
        if raw["link_number"] != expected_link_number:
            raise LeapError("Firestorm returned an invalid selected link number")
        if not raw.get("logged_in") or not raw.get("properties_complete"):
            raise LeapError("Firestorm returned an incomplete selected-object context")

        expected_self_owned = (
            not bool(raw.get("group_owned")) and raw["owner_id"] == raw["avatar_id"]
        )
        if bool(raw.get("owner_is_logged_in_avatar")) != expected_self_owned:
            raise LeapError("Firestorm returned inconsistent selected-object ownership")

        eligible, _ = self._target_eligibility(raw)
        scripts: list[dict[str, Any]] = []
        if eligible:
            inventory_response = self.leap.request(
                "LLScriptAutomation",
                {"op": "getTaskInventory", "object_id": raw["object_id"]},
                timeout=max(self.request_timeout, 45.0),
            )
            items = inventory_response.get("items")
            if not isinstance(items, list):
                raise LeapError("Firestorm returned an invalid selected-object inventory")
            for item in items:
                if not isinstance(item, dict) or not item.get("is_script"):
                    continue
                script = dict(item)
                script["item_id"] = self._validated_uuid(
                    script.get("item_id"), "selected script item"
                )
                if script["item_id"] == NULL_UUID:
                    raise LeapError("Firestorm returned a null selected script item UUID")
                scripts.append(script)
            if len({item["item_id"] for item in scripts}) != len(scripts):
                raise LeapError("Firestorm returned duplicate selected script item UUIDs")
            scripts.sort(key=lambda item: (str(item.get("name", "")), item["item_id"]))

        identity = {
            "session_fingerprint": self.session_fingerprint,
            "avatar_id": raw["avatar_id"],
            "grid_id": str(raw.get("grid_id", "")),
            "region_id": raw["region_id"],
            "root_id": raw["root_id"],
            "object_id": raw["object_id"],
            "owner_id": raw["owner_id"],
            "creator_id": raw["creator_id"],
            "group_id": raw["group_id"],
            "attachment_item_id": raw["attachment_item_id"],
            "link_ids": raw["link_ids"],
            "object_name": str(raw.get("object_name", "")),
            "object_description": str(raw.get("object_description", "")),
            "root_name": str(raw.get("root_name", "")),
            "root_description": str(raw.get("root_description", "")),
            "selection_object_count": raw["selection_object_count"],
            "selection_root_count": raw["selection_root_count"],
            "link_number": raw["link_number"],
            "link_count": raw["link_count"],
            "face_count": raw["face_count"],
            "is_root": bool(raw.get("is_root")),
            "is_attachment": bool(raw.get("is_attachment")),
            "position_region": raw.get("position_region"),
            "root_position_region": raw.get("root_position_region"),
            "group_owned": bool(raw.get("group_owned")),
            "can_modify": bool(raw.get("can_modify")),
            "can_copy": bool(raw.get("can_copy")),
            "can_move": bool(raw.get("can_move")),
            "can_transfer": bool(raw.get("can_transfer")),
            "scripts": [
                {
                    "item_id": item["item_id"],
                    "name": str(item.get("name", "")),
                    "description": str(item.get("description", "")),
                    "can_copy": bool(item.get("can_copy")),
                    "can_modify": bool(item.get("can_modify")),
                    "can_transfer": bool(item.get("can_transfer")),
                }
                for item in scripts
            ],
        }
        serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        identity_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return raw, scripts, identity, identity_sha256

    @staticmethod
    def _target_eligibility(raw: dict[str, Any]) -> tuple[bool, str | None]:
        if bool(raw.get("group_owned")):
            return False, "Group-owned targets are disabled by the strict self-owner policy"
        if not bool(raw.get("owner_is_logged_in_avatar")):
            return False, "The selected object is not owned by the logged-in avatar"
        if not bool(raw.get("can_modify")):
            return False, "The logged-in avatar cannot modify the selected object"
        return True, None

    def _public_target_summary(
        self,
        raw: dict[str, Any],
        scripts: list[dict[str, Any]],
        identity_sha256: str,
    ) -> dict[str, Any]:
        owner_relation = "self"
        if raw.get("group_owned"):
            owner_relation = "group"
        elif not raw.get("owner_is_logged_in_avatar"):
            owner_relation = "other"
        return {
            "viewer": {
                "session_fingerprint": self.session_fingerprint,
                "avatar_id": raw["avatar_id"],
                "avatar_name": str(raw.get("avatar_name", "")),
                "grid_id": str(raw.get("grid_id", "")),
                "grid_label": str(raw.get("grid_label", "")),
                "region_id": raw["region_id"],
                "region_name": str(raw.get("region_name", "")),
            },
            "target": {
                "identity_sha256": identity_sha256,
                "object_name": str(raw.get("object_name", "")),
                "object_description": str(raw.get("object_description", "")),
                "root_name": str(raw.get("root_name", "")),
                "root_description": str(raw.get("root_description", "")),
                "selection_object_count": raw["selection_object_count"],
                "selection_root_count": raw["selection_root_count"],
                "link_number": raw["link_number"],
                "link_count": raw["link_count"],
                "face_count": raw["face_count"],
                "is_root": bool(raw.get("is_root")),
                "is_attachment": bool(raw.get("is_attachment")),
                "position_region": raw.get("position_region"),
                "root_position_region": raw.get("root_position_region"),
                "owner_relation": owner_relation,
                "owner_is_logged_in_avatar": bool(
                    raw.get("owner_is_logged_in_avatar")
                ),
                "group_owned": bool(raw.get("group_owned")),
                "can_modify": bool(raw.get("can_modify")),
                "can_copy": bool(raw.get("can_copy")),
                "can_move": bool(raw.get("can_move")),
                "can_transfer": bool(raw.get("can_transfer")),
                "properties_complete": bool(raw.get("properties_complete")),
            },
            "script_inventory": {
                "count": len(scripts),
                "source_returned": False,
                "scripts": [
                    {
                        "name": str(item.get("name", "")),
                        "description": str(item.get("description", "")),
                        "can_copy": bool(item.get("can_copy")),
                        "can_modify": bool(item.get("can_modify")),
                        "can_transfer": bool(item.get("can_transfer")),
                    }
                    for item in scripts
                ],
            },
        }

    def _cleanup_expired_target_handles(self, now: float) -> None:
        expired = [
            handle
            for handle, entry in self._target_handles.items()
            if now >= float(entry["expires_monotonic"])
        ]
        for handle in expired:
            self._target_handles.pop(handle, None)

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
        if len(source.encode("utf-8")) > MAX_SCRIPT_SOURCE_BYTES:
            raise LeapError("Firestorm returned script source larger than the allowed limit")
        return source

    @staticmethod
    def _read_workspace_source(path: Path, workspace_root: Path) -> str:
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(workspace_root)
        except (OSError, ValueError) as exc:
            raise LeapError("The mapped local LSL file escaped its allowlisted workspace") from exc
        try:
            data = resolved.read_bytes()
        except OSError as exc:
            raise LeapError("The mapped local LSL file could not be read") from exc
        if len(data) > MAX_SCRIPT_SOURCE_BYTES:
            raise LeapError("The mapped local LSL file is larger than the allowed limit")
        if b"\0" in data:
            raise LeapError("The mapped local LSL file contains a NUL byte")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LeapError("The mapped local LSL file is not valid UTF-8") from exc

    @staticmethod
    def _source_summary(source: str) -> dict[str, Any]:
        data = source.encode("utf-8")
        canonical = source.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        return {
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "bytes": len(data),
            "hash_normalization": "utf8-lf",
        }

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

    @staticmethod
    def _build_three_color_touch_source(source: str) -> str:
        """Transform only the known two-color touch toggle into red/green/blue."""

        declarations = list(
            re.finditer(
                r"(?m)^[ \t]*integer[ \t]+(?P<name>[A-Za-z_]\w*)[ \t]*;[ \t]*$",
                source,
            )
        )
        if len(declarations) != 1:
            raise LeapError("The test script no longer has the expected single state variable")
        variable = declarations[0].group("name")
        escaped = re.escape(variable)

        toggle_pattern = re.compile(
            rf"(?m)^(?P<indent>[ \t]*){escaped}[ \t]*=[ \t]*!{escaped}[ \t]*;[ \t]*$"
        )
        toggle_matches = list(toggle_pattern.finditer(source))
        if len(toggle_matches) != 1:
            raise LeapError("The test script no longer has the expected two-state touch toggle")

        zero = r"0(?:\.0+)?"
        one = r"1(?:\.0+)?"
        red = rf"<[ \t]*{one}[ \t]*,[ \t]*{zero}[ \t]*,[ \t]*{zero}[ \t]*>"
        green = rf"<[ \t]*{zero}[ \t]*,[ \t]*{one}[ \t]*,[ \t]*{zero}[ \t]*>"
        color_block = re.compile(
            rf"(?m)^(?P<indent>[ \t]*)if[ \t]*\([ \t]*{escaped}[ \t]*\)[ \t]*\r?\n"
            rf"(?P<redline>(?P<callindent>[ \t]*)llSetColor[ \t]*\([ \t]*{red}[ \t]*,[ \t]*ALL_SIDES[ \t]*\)[ \t]*;[ \t]*)\r?\n"
            rf"(?P=indent)else[ \t]*\r?\n"
            rf"(?P<greenline>(?P=callindent)llSetColor[ \t]*\([ \t]*{green}[ \t]*,[ \t]*ALL_SIDES[ \t]*\)[ \t]*;[ \t]*)$"
        )
        color_matches = list(color_block.finditer(source))
        if len(color_matches) != 1 or len(re.findall(r"\bllSetColor[ \t]*\(", source)) != 2:
            raise LeapError("The test script no longer has the expected red/green touch-color block")

        newline = "\r\n" if "\r\n" in color_matches[0].group(0) else "\n"
        match = color_matches[0]
        replacement = (
            f"{match.group('indent')}if ({variable} == 1){newline}"
            f"{match.group('redline')}{newline}"
            f"{match.group('indent')}else if ({variable} == 2){newline}"
            f"{match.group('greenline')}{newline}"
            f"{match.group('indent')}else{newline}"
            f"{match.group('callindent')}llSetColor(<0.0, 0.0, 1.0>, ALL_SIDES);"
        )
        candidate = source[: match.start()] + replacement + source[match.end() :]
        # The color-block replacement can change offsets after the toggle, so
        # replace the independently validated toggle by content and count.
        candidate, count = toggle_pattern.subn(
            rf"\g<indent>{variable} = ({variable} + 1) % 3;",
            candidate,
        )
        if count != 1:
            raise LeapError("The touch state update could not be transformed safely")
        if len(re.findall(r"\bllSetColor[ \t]*\(", candidate)) != 3:
            raise LeapError("The generated script did not contain exactly three color operations")
        return candidate

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

    def _write_script_edit_plan(self, plan: dict[str, Any]) -> tuple[Path, Path]:
        for parent in (self.script_edit_plan_dir, *self.script_edit_plan_dir.parents):
            if (parent / ".git").exists():
                raise LeapError("Script edit plans must be stored outside a Git working tree")
        self.script_edit_plan_dir.mkdir(parents=True, exist_ok=True)
        plan_id = str(plan["plan_id"])
        plan_path = self.script_edit_plan_dir / f"{plan_id}.json"
        diff_path = self.script_edit_plan_dir / f"{plan_id}.diff"
        serialized = json.dumps(plan, ensure_ascii=False, sort_keys=True)
        with plan_path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(serialized)
            stream.flush()
        if plan_path.read_text(encoding="utf-8") != serialized:
            plan_path.unlink(missing_ok=True)
            raise LeapError("The local script edit plan did not verify byte-for-byte")

        diff = "".join(
            unified_diff(
                str(plan["original"]).splitlines(keepends=True),
                str(plan["candidate"]).splitlines(keepends=True),
                fromfile="current.lsl",
                tofile="proposed.lsl",
            )
        )
        try:
            with diff_path.open("x", encoding="utf-8", newline="") as stream:
                stream.write(diff)
                stream.flush()
            if diff_path.read_text(encoding="utf-8") != diff:
                raise LeapError("The local script diff did not verify byte-for-byte")
        except Exception:
            plan_path.unlink(missing_ok=True)
            diff_path.unlink(missing_ok=True)
            raise
        return plan_path, diff_path

    def _remove_script_edit_plan(self, plan_id: str) -> None:
        (self.script_edit_plan_dir / f"{plan_id}.json").unlink(missing_ok=True)
        (self.script_edit_plan_dir / f"{plan_id}.diff").unlink(missing_ok=True)

    def _cleanup_expired_script_edit_plans(self) -> None:
        if not self.script_edit_plan_dir.is_dir():
            return
        now = datetime.now(UTC)
        for plan_path in self.script_edit_plan_dir.glob("*.json"):
            if not re.fullmatch(r"[0-9a-f]{32}\.json", plan_path.name):
                continue
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                expires = datetime.fromisoformat(str(plan["expires_at"]))
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if now >= expires:
                self._remove_script_edit_plan(plan_path.stem)
