param(
    [string]$RemoteCommand = "source .venv/bin/activate && python -m pytest tests/",
    [string]$RemoteHost = "jsmith@pop-os",
    [string]$RemotePath = "/home/jsmith/staffNinja"
)

$ErrorActionPreference = "Stop"

$escapedPath = $RemotePath.Replace("'", "'\''")
$escapedCommand = $RemoteCommand.Replace("'", "'\''")
$sshCommand = "cd '$escapedPath' && bash -lc '$escapedCommand'"

& ssh $RemoteHost $sshCommand
exit $LASTEXITCODE
