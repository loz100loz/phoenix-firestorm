[CmdletBinding()]
param(
    [Parameter()]
    [string]$ViewerPath = 'C:\Program Files\Firestorm-Releasex64\Firestorm-Releasex64.exe',

    [Parameter()]
    [string[]]$AllowedAttachmentName = @('MCP POC ROOT')
)

$ErrorActionPreference = 'Stop'
$bridgeRoot = $PSScriptRoot
$bridgePython = Join-Path $bridgeRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $ViewerPath -PathType Leaf)) {
    throw "Firestorm executable not found: $ViewerPath"
}
if (-not (Test-Path -LiteralPath $bridgePython -PathType Leaf)) {
    throw "Bridge virtual environment not found. Follow the Development setup in README.md first."
}

$runningViewer = Get-Process -Name 'Firestorm-Releasex64' -ErrorAction SilentlyContinue
if ($runningViewer) {
    throw 'Firestorm is already running. Close it normally first so no viewer state is lost.'
}

$bridgeArguments = @('"' + $bridgePython + '"', '-m', 'firestorm_mcp_bridge')
foreach ($name in $AllowedAttachmentName) {
    if ([string]::IsNullOrWhiteSpace($name)) {
        throw 'Allowed attachment names cannot be empty.'
    }
    $escapedName = $name.Replace('"', '\"')
    $bridgeArguments += @('--allow-attachment-name', '"' + $escapedName + '"')
}
$leapCommand = $bridgeArguments -join ' '

$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $ViewerPath
$startInfo.UseShellExecute = $true
$startInfo.ArgumentList.Add('--leap')
$startInfo.ArgumentList.Add($leapCommand)
$process = [System.Diagnostics.Process]::Start($startInfo)

[pscustomobject]@{
    ViewerProcessId = $process.Id
    ViewerPath = $ViewerPath
    LeapCommand = $leapCommand
    SessionFile = Join-Path $env:LOCALAPPDATA 'FirestormMCP\session.json'
}

