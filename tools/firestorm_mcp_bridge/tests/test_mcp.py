from __future__ import annotations

import asyncio

from mcp import Client

from firestorm_mcp_bridge.server import create_mcp_server
from test_service import make_workspace_service


def test_mcp_tools_are_callable_in_process(tmp_path):
    service, _ = make_workspace_service(tmp_path)
    server = create_mcp_server(service)

    async def exercise() -> None:
        async with Client(server) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "viewer_status",
                "discover_viewer_apis",
                "list_attachments",
                "viewer_context",
                "inspect_selected_target",
                "revalidate_selected_target",
                "workspace_status",
                "touch_test_hud",
                "list_test_hud_scripts",
                "prove_test_hud_script_round_trip",
                "add_third_touch_color",
                "preview_test_hud_script_edit",
                "apply_test_hud_script_edit",
                "capture_viewer",
            }

            status = await client.call_tool("viewer_status", {})
            assert status.is_error is False
            assert status.structured_content["logged_in"] is True

            context = await client.call_tool("viewer_context", {})
            assert context.is_error is False
            assert context.structured_content["avatar_name"] == "ninja.nova"

            inspected = await client.call_tool("inspect_selected_target", {})
            workspace = await client.call_tool(
                "workspace_status",
                {
                    "workspace_key": "fixture-workspace",
                    "device_key": "fixture",
                    "script_key": "controller",
                    "target_handle": inspected.structured_content["target_handle"],
                },
            )
            assert workspace.is_error is False
            assert workspace.structured_content["status"] == "unchanged"

            screenshot = await client.call_tool(
                "capture_viewer",
                {"width": 800, "height": 600, "show_ui": False, "show_hud": True},
            )
            assert screenshot.is_error is False
            assert [block.type for block in screenshot.content] == ["text", "image"]

    asyncio.run(exercise())
