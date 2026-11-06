# OM6239 PinMux desktop launcher (WebView2)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Error "Python not found. Install Python and add it to PATH."
    exit 1
}
& $py.Source app.py @args
exit $LASTEXITCODE