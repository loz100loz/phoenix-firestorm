"""Authenticated localhost MCP server backed by a Firestorm LEAP connection."""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import hmac
import json
import logging
import os
import re
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Image
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ImageContent, TextContent
from pydantic import AnyHttpUrl

from . import __version__
from .leap import LeapConnection
from .service import Stage0Service

LOGGER = logging.getLogger("firestorm_mcp_bridge")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PATH = "/mcp"
DEFAULT_ALLOWED_ATTACHMENT = "MCP POC ROOT"


class SessionTokenVerifier(TokenVerifier):
    def __init__(self, token: str, resource_url: str) -> None:
        self._token = token
        self._resource_url = resource_url

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, self._token):
            return None
        return AccessToken(
            token=token,
            client_id="firestorm-local-session",
            scopes=["firestorm:stage0"],
            resource=self._resource_url,
        )


def create_mcp_server(
    service: Stage0Service,
    *,
    token: str | None = None,
    resource_url: str | None = None,
) -> MCPServer:
    kwargs: dict[str, Any] = {}
    if token is not None and resource_url is not None:
        kwargs.update(
            token_verifier=SessionTokenVerifier(token, resource_url),
            auth=AuthSettings(
                issuer_url=AnyHttpUrl(resource_url),
                resource_server_url=AnyHttpUrl(resource_url),
                required_scopes=["firestorm:stage0"],
                validate_token_resource=True,
            ),
        )

    mcp = MCPServer(
        name="Firestorm MCP Proof of Concept",
        description=(
            "Proof-of-concept bridge for viewer discovery, read-only selected-target "
            "identity, workspace comparison and push planning, worn test-HUD touch, "
            "HUD-visible screenshots, and guarded write/compile/verify transactions "
            "limited to the sole script in an exact allowlisted worn test HUD."
        ),
        version=__version__,
        **kwargs,
    )

    @mcp.tool(structured_output=True)
    def viewer_status() -> dict[str, Any]:
        """Report LEAP connectivity, login state, required APIs, and the touch allowlist."""

        return service.viewer_status()

    @mcp.tool(structured_output=True)
    def discover_viewer_apis(refresh: bool = False) -> dict[str, Any]:
        """Enumerate the event APIs exposed by this running Firestorm viewer."""

        return service.discover_viewer_apis(refresh=refresh)

    @mcp.tool(structured_output=True)
    def list_attachments() -> list[dict[str, Any]]:
        """List objects and HUD roots currently attached to the logged-in avatar."""

        return service.list_attachments()

    @mcp.tool(structured_output=True)
    def viewer_context() -> dict[str, Any]:
        """Report the non-secret avatar, grid, region, and per-viewer session identity."""

        return service.viewer_context()

    @mcp.tool(structured_output=True)
    def inspect_selected_target() -> dict[str, Any]:
        """Inspect one selected linkset and issue a handle only for a safe self-owned target."""

        return service.inspect_selected_target()

    @mcp.tool(structured_output=True)
    def revalidate_selected_target(target_handle: str) -> dict[str, Any]:
        """Verify that a selected target still exactly matches an unexpired handle."""

        return service.revalidate_selected_target(target_handle)

    @mcp.tool(structured_output=True)
    def workspace_status(
        workspace_key: str,
        device_key: str,
        script_key: str,
        target_handle: str,
    ) -> dict[str, Any]:
        """Compare one allowlisted local LSL mapping with a revalidated selected target."""

        return service.workspace_status(
            workspace_key=workspace_key,
            device_key=device_key,
            script_key=script_key,
            target_handle=target_handle,
        )

    @mcp.tool(structured_output=True)
    def preview_workspace_push(
        workspace_key: str,
        device_key: str,
        script_key: str,
        target_handle: str,
    ) -> dict[str, Any]:
        """Create an outside-Git local-to-world plan and diff without uploading."""

        return service.preview_workspace_push(
            workspace_key=workspace_key,
            device_key=device_key,
            script_key=script_key,
            target_handle=target_handle,
        )

    @mcp.tool(structured_output=True)
    def touch_test_hud(
        attachment_name: str = DEFAULT_ALLOWED_ATTACHMENT,
        inventory_item_id: str | None = None,
        face: int = 0,
    ) -> dict[str, Any]:
        """Touch an allowlisted, currently worn test HUD root; arbitrary object IDs are rejected."""

        return service.touch_test_hud(
            attachment_name=attachment_name,
            inventory_item_id=inventory_item_id,
            face=face,
        )

    @mcp.tool(structured_output=True)
    def list_test_hud_scripts(
        attachment_name: str = DEFAULT_ALLOWED_ATTACHMENT,
    ) -> list[dict[str, Any]]:
        """List LSL scripts inside one exact allowlisted, currently worn test HUD."""

        return service.list_test_hud_scripts(attachment_name=attachment_name)

    @mcp.tool(structured_output=True)
    def prove_test_hud_script_round_trip(
        attachment_name: str = DEFAULT_ALLOWED_ATTACHMENT,
    ) -> dict[str, Any]:
        """Back up, mark, compile, verify, restore, and recompile the sole test-HUD script."""

        return service.prove_test_hud_script_round_trip(
            attachment_name=attachment_name,
        )

    @mcp.tool(structured_output=True)
    def add_third_touch_color(
        attachment_name: str = DEFAULT_ALLOWED_ATTACHMENT,
    ) -> dict[str, Any]:
        """Persistently extend the exact test-HUD red/green touch cycle with blue."""

        return service.add_third_touch_color(attachment_name=attachment_name)

    @mcp.tool(structured_output=True)
    def preview_test_hud_script_edit(
        operation: str,
        find_text: str,
        replacement_text: str,
        expected_occurrences: int = 1,
    ) -> dict[str, Any]:
        """Preview an exact replace or append edit for MCP POC ROOT without uploading."""

        return service.preview_test_hud_script_edit(
            operation=operation,
            find_text=find_text,
            replacement_text=replacement_text,
            expected_occurrences=expected_occurrences,
        )

    @mcp.tool(structured_output=True)
    def apply_test_hud_script_edit(
        plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        """Apply one previewed MCP POC ROOT edit with backup, compile, and rollback."""

        return service.apply_test_hud_script_edit(
            plan_id=plan_id,
            confirmation=confirmation,
        )

    @mcp.tool()
    def capture_viewer(
        width: int = 1600,
        height: int = 900,
        show_ui: bool = False,
        show_hud: bool = True,
    ) -> list[TextContent | ImageContent]:
        """Capture Firestorm and return the PNG, showing HUDs and hiding private viewer UI by default."""

        snapshot = service.capture_viewer(
            width=width,
            height=height,
            show_ui=show_ui,
            show_hud=show_hud,
        )
        return [
            TextContent(type="text", text=json.dumps(snapshot.metadata, sort_keys=True)),
            Image(path=snapshot.path).to_image_content(),
        ]

    return mcp


def default_session_file() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / ".firestorm-mcp"
    return base / "FirestormMCP" / "session.json"


def default_capture_dir() -> Path:
    return default_session_file().parent / "captures"


def default_script_backup_dir() -> Path:
    return default_session_file().parent / "script-backups"


def decode_launch_config(value: str) -> dict[str, Any]:
    if len(value) > 16_384:
        raise ValueError("launch config is too large")
    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        config = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("launch config is not valid base64url JSON") from exc
    if not isinstance(config, dict):
        raise ValueError("launch config must be a JSON object")
    supported = {
        "port",
        "session_file",
        "capture_dir",
        "script_backup_dir",
        "allowed_attachment_names",
        "workspace_roots",
    }
    unknown = sorted(set(config) - supported)
    if unknown:
        raise ValueError(f"launch config contains unsupported fields: {', '.join(unknown)}")
    return config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--launch-config",
        help="Base64url JSON launch settings used by the Windows launcher to avoid nested quoting.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, choices=[DEFAULT_HOST])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--session-file", type=Path, default=default_session_file())
    parser.add_argument("--capture-dir", type=Path, default=default_capture_dir())
    parser.add_argument(
        "--script-backup-dir",
        type=Path,
        default=default_script_backup_dir(),
    )
    parser.add_argument(
        "--allow-attachment-name",
        action="append",
        dest="allowed_attachment_names",
        default=None,
        help="Exact worn attachment name allowed for touch; may be repeated.",
    )
    parser.add_argument(
        "--workspace-root",
        action="append",
        dest="workspace_root_specs",
        default=[],
        metavar="KEY=PATH",
        help="Allowlist a named workspace root; may be repeated.",
    )
    parser.add_argument("--request-timeout", type=float, default=15.0)
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    args = parser.parse_args(argv)
    args.workspace_roots = {}
    for spec in args.workspace_root_specs:
        key, separator, value = spec.partition("=")
        if not separator or not key.strip() or not value.strip():
            parser.error("--workspace-root must use KEY=PATH")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key):
            parser.error(f"invalid workspace key: {key}")
        if key in args.workspace_roots:
            parser.error(f"duplicate workspace key: {key}")
        args.workspace_roots[key] = Path(value)
    del args.workspace_root_specs
    if args.launch_config:
        try:
            config = decode_launch_config(args.launch_config)
            if "port" in config:
                args.port = int(config["port"])
            if "session_file" in config:
                if not isinstance(config["session_file"], str) or not config["session_file"].strip():
                    raise ValueError("session_file must be a non-empty string")
                args.session_file = Path(config["session_file"])
            if "capture_dir" in config:
                if not isinstance(config["capture_dir"], str) or not config["capture_dir"].strip():
                    raise ValueError("capture_dir must be a non-empty string")
                args.capture_dir = Path(config["capture_dir"])
            if "script_backup_dir" in config:
                if (
                    not isinstance(config["script_backup_dir"], str)
                    or not config["script_backup_dir"].strip()
                ):
                    raise ValueError("script_backup_dir must be a non-empty string")
                args.script_backup_dir = Path(config["script_backup_dir"])
            if "allowed_attachment_names" in config:
                names = config["allowed_attachment_names"]
                if (
                    not isinstance(names, list)
                    or not names
                    or not all(isinstance(name, str) and name.strip() for name in names)
                ):
                    raise ValueError("allowed_attachment_names must be a non-empty list of non-empty strings")
                args.allowed_attachment_names = names
            if "workspace_roots" in config:
                roots = config["workspace_roots"]
                if (
                    not isinstance(roots, dict)
                    or not all(
                        isinstance(key, str)
                        and key.strip()
                        and isinstance(value, str)
                        and value.strip()
                        for key, value in roots.items()
                    )
                ):
                    raise ValueError("workspace_roots must map non-empty keys to non-empty paths")
                for key, value in roots.items():
                    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key):
                        raise ValueError(f"invalid workspace key: {key}")
                    if key in args.workspace_roots:
                        raise ValueError(f"duplicate workspace key: {key}")
                    args.workspace_roots[key] = Path(value)
        except (TypeError, ValueError) as exc:
            parser.error(f"invalid --launch-config: {exc}")
    if args.port < 1024 or args.port > 65535:
        parser.error("--port must be between 1024 and 65535")
    if not args.path.startswith("/"):
        parser.error("--path must begin with /")
    if args.request_timeout <= 0 or args.request_timeout > 120:
        parser.error("--request-timeout must be greater than 0 and at most 120 seconds")
    if not args.allowed_attachment_names:
        args.allowed_attachment_names = [DEFAULT_ALLOWED_ATTACHMENT]
    return args


def write_session_descriptor(
    path: Path,
    *,
    endpoint: str,
    token: str,
    allowed_attachment_names: list[str],
) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = {
        "version": __version__,
        "pid": os.getpid(),
        "started_at": datetime.now(UTC).isoformat(),
        "endpoint": endpoint,
        "authorization": f"Bearer {token}",
        "allowed_attachment_names": allowed_attachment_names,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def remove_session_descriptor(path: Path) -> None:
    try:
        descriptor = json.loads(path.read_text(encoding="utf-8"))
        if descriptor.get("pid") == os.getpid():
            path.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


async def run_server(
    mcp: MCPServer,
    leap: LeapConnection,
    *,
    host: str,
    port: int,
    path: str,
    log_level: str,
) -> None:
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"127.0.0.1:{port}", f"localhost:{port}"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*"],
    )
    app = mcp.streamable_http_app(
        streamable_http_path=path,
        json_response=True,
        stateless_http=True,
        max_request_body_size=1 * 1024 * 1024,
        max_sessions=8,
        session_idle_timeout=300,
        transport_security=security,
        host=host,
    )
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)

    async def stop_when_viewer_closes() -> None:
        await asyncio.to_thread(leap.wait_closed)
        LOGGER.info("Firestorm closed the LEAP connection; stopping MCP")
        server.should_exit = True

    monitor = asyncio.create_task(stop_when_viewer_closes())
    try:
        await server.serve()
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # stdout is exclusively the LEAP protocol. Never log or print to it.
    leap = LeapConnection.accept(sys.stdin.buffer, sys.stdout.buffer)
    endpoint = f"http://{args.host}:{args.port}{args.path}"
    token = secrets.token_urlsafe(32)
    service = Stage0Service(
        leap,
        args.capture_dir,
        tuple(args.allowed_attachment_names),
        script_backup_dir=args.script_backup_dir,
        request_timeout=args.request_timeout,
        workspace_roots=args.workspace_roots,
    )
    mcp = create_mcp_server(service, token=token, resource_url=endpoint)

    write_session_descriptor(
        args.session_file,
        endpoint=endpoint,
        token=token,
        allowed_attachment_names=args.allowed_attachment_names,
    )
    LOGGER.info("Firestorm MCP proof of concept listening at %s", endpoint)
    LOGGER.info("Session descriptor: %s", args.session_file.resolve())

    try:
        asyncio.run(
            run_server(
                mcp,
                leap,
                host=args.host,
                port=args.port,
                path=args.path,
                log_level=args.log_level,
            )
        )
    finally:
        remove_session_descriptor(args.session_file.resolve())


if __name__ == "__main__":
    main()
