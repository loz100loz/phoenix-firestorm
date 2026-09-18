[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter()]
    [string]$ViewerPath = 'C:\Program Files\Firestorm-Releasex64\Firestorm-Releasex64.exe',

    [Parameter()]
    [string[]]$AllowedAttachmentName = @('MCP POC ROOT'),

    [Parameter()]
    [switch]$Multiple,

    [Parameter()]
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,

    [Parameter()]
    [string]$SessionFile,

    [Parameter()]
    [string]$CaptureDirectory
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

$viewerProcessName = [System.IO.Path]::GetFileNameWithoutExtension($ViewerPath)
$runningViewer = Get-Process -Name $viewerProcessName -ErrorAction SilentlyContinue
if ($runningViewer -and -not $Multiple) {
    throw "$viewerProcessName is already running. Close it normally first so no viewer state is lost."
}

function Get-AvailableLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    try {
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }
}

$localDataRoot = Join-Path $env:LOCALAPPDATA 'FirestormMCP'
if ($Multiple) {
    $sessionId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
    if (-not $PSBoundParameters.ContainsKey('Port')) {
        $Port = Get-AvailableLoopbackPort
    }
    if ([string]::IsNullOrWhiteSpace($SessionFile)) {
        $SessionFile = Join-Path $localDataRoot "sessions\session-$sessionId.json"
    }
    if ([string]::IsNullOrWhiteSpace($CaptureDirectory)) {
        $CaptureDirectory = Join-Path $localDataRoot "captures\$sessionId"
    }
}
else {
    if ([string]::IsNullOrWhiteSpace($SessionFile)) {
        $SessionFile = Join-Path $localDataRoot 'session.json'
    }
    if ([string]::IsNullOrWhiteSpace($CaptureDirectory)) {
        $CaptureDirectory = Join-Path $localDataRoot 'captures'
    }
}

if (Test-Path -LiteralPath $SessionFile) {
    throw "Session descriptor already exists; refusing to overwrite it: $SessionFile"
}

foreach ($name in $AllowedAttachmentName) {
    if ([string]::IsNullOrWhiteSpace($name)) {
        throw 'Allowed attachment names cannot be empty.'
    }
}

$leapExecutable = $bridgePython.Replace('\', '/')
if ($leapExecutable -match '\s') {
    throw "The bridge Python path cannot contain whitespace because Firestorm reparses --leap commands: $bridgePython"
}

$launchConfig = @{
    port = $Port
    session_file = $SessionFile
    capture_dir = $CaptureDirectory
    allowed_attachment_names = @($AllowedAttachmentName)
}
$launchConfigJson = $launchConfig | ConvertTo-Json -Compress
$launchConfigToken = [Convert]::ToBase64String(
    [System.Text.Encoding]::UTF8.GetBytes($launchConfigJson)
).TrimEnd('=').Replace('+', '-').Replace('/', '_')
$leapCommand = "$leapExecutable -m firestorm_mcp_bridge --launch-config $launchConfigToken"

$viewerVersion = [version](Get-Item -LiteralPath $ViewerPath).VersionInfo.ProductVersion
if ($viewerVersion -ge [version]'7.2.5.0') {
    # Current viewers map --leap to an LLSD setting and therefore expect LLSD
    # notation. LLSD's URI notation accepts an arbitrary delimiter, so this
    # form survives both Windows argument quoting and Firestorm's quote-aware
    # command-line tokenizer without exposing inner quote characters.
    if ($leapCommand.Contains('|')) {
        throw 'The LEAP command cannot contain a pipe for this Firestorm version.'
    }
    $leapArgument = "l|$leapCommand|"
}
else {
    $leapArgument = $leapCommand
}

$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $ViewerPath
$startInfo.UseShellExecute = $true
$viewerArguments = @()
if ($Multiple) {
    $viewerArguments += '--multiple'
}
$viewerArguments += @('--leap', $leapArgument)
foreach ($argument in $viewerArguments) {
    $startInfo.ArgumentList.Add($argument)
}

$process = $null
if ($PSCmdlet.ShouldProcess($ViewerPath, 'Launch Firestorm with the Stage 0 MCP bridge')) {
    $process = [System.Diagnostics.Process]::Start($startInfo)
}

[pscustomobject]@{
    ViewerProcessId = if ($process) { $process.Id } else { $null }
    ViewerPath = $ViewerPath
    Multiple = [bool]$Multiple
    ViewerArguments = $viewerArguments
    LeapCommand = $leapCommand
    LeapArgument = $leapArgument
    Port = $Port
    SessionFile = $SessionFile
    CaptureDirectory = $CaptureDirectory
}
