# Fake LSL game workspace

This workspace is synthetic. It exists only to test manifest validation and
debounced local-save detection without reading or changing the user's real game
project or any live Second Life object.

- `development-hud` demonstrates two scripts in one worn device.
- `training-door` demonstrates an automatically synced rezzed device.
- `score-board` demonstrates a script that remains manual.

The object and task-script names are deliberately fake. Detection of an
`on_save` event does not authorize a live upload. The folder may be launch-
allowlisted to exercise workspace validation and MCP status routing, but its
names intentionally cannot match the user's live objects. Status is read-only
and push remains a separate guarded stage.

Validate it from the bridge directory:

```powershell
.\.venv\Scripts\python.exe -m firestorm_mcp_bridge.workspace validate .\examples\fake_lsl_game
```

Watch it for saves:

```powershell
.\.venv\Scripts\python.exe -m firestorm_mcp_bridge.workspace watch .\examples\fake_lsl_game
```
