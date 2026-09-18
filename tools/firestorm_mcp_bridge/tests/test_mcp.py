from __future__ import annotations

import asyncio

from mcp import Client

from firestorm_mcp_bridge.server import create_mcp_server
from test_service import FakeLeap
from firestorm_mcp_bridge.service import Stage0Service


def test_mcp_tools_are_callable_in_process(tmp_path):
    service = Stage0Service(
        FakeLeap(),
        tmp_path / "captures",
        ("MCP POC ROOT",),
        touch_cooldown=0,
    )
    server = create_mcp_server(service)

    async def exercise() -> None:
        async with Client(server) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "viewer_status",
                "discover_viewer_apis",
                "list_attachments",
                "touch_test_hud",
                "list_test_hud_scripts",
                "prove_test_hud_script_round_trip",
                "add_third_touch_color",
                "capture_viewer",
            }

            status = await client.call_tool("viewer_status", {})
            assert status.is_error is False
            assert status.structured_content["logged_in"] is True

            screenshot = await client.call_tool(
                "capture_viewer",
                {"width": 800, "height": 600, "show_ui": False, "show_hud": True},
            )
            assert screenshot.is_error is False
            assert [block.type for block in screenshot.content] == ["text", "image"]

    asyncio.run(exercise())
