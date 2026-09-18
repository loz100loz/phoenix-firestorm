"""Allowlisted Stage 0 operations exposed by the MCP bridge."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .leap import LeapConnection, LeapError

NULL_UUID = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class Snapshot:
    path: Path
    metadata: dict[str, Any]


class Stage0Service:
    """Narrow service layer: discovery, worn attachment touch, and screenshot."""

    def __init__(
        self,
        leap: LeapConnection,
        capture_dir: Path,
        allowed_attachment_names: tuple[str, ...],
        *,
        request_timeout: float = 15.0,
        touch_cooldown: float = 1.0,
    ) -> None:
        self.leap = leap
        self.capture_dir = capture_dir.resolve()
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_attachment_names = tuple(dict.fromkeys(allowed_attachment_names))
        self.request_timeout = request_timeout
        self.touch_cooldown = touch_cooldown
        self._apis: dict[str, Any] | None = None
        self._touch_lock = threading.Lock()
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

        if attachment_name not in self.allowed_attachment_names:
            raise LeapError(
                f"Attachment {attachment_name!r} is not allowlisted for this bridge session"
            )
        if face < 0 or face > 31:
            raise LeapError("face must be between 0 and 31")
        if inventory_item_id is not None:
            try:
                inventory_item_id = str(uuid.UUID(inventory_item_id))
            except ValueError as exc:
                raise LeapError("inventory_item_id must be a UUID") from exc

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
        object_id = str(target.get("object_id", ""))
        try:
            uuid.UUID(object_id)
        except ValueError as exc:
            raise LeapError("Firestorm returned an invalid attachment object UUID") from exc

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

