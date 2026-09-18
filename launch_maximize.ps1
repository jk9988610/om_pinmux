# OM6239 PinMux - start maximized
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\launch.ps1" --maximize @args
exit $LASTEXITCODE