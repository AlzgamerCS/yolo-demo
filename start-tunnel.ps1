param(
    [ValidateRange(1024,65535)][int]$Port = 8765,
    [string]$AllowedEmail
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw 'cloudflared not found. Install with: winget install --id Cloudflare.cloudflared -e'
}
try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 5
} catch {
    throw "YOLO Studio is not reachable at http://127.0.0.1:$Port. Start start-web.ps1 first."
}
Write-Host 'Starting a Cloudflare Quick Tunnel for YOLO Studio.'
Write-Host 'Share the HTTPS URL printed below. Keep this window open; Ctrl+C stops sharing.'
if ($AllowedEmail) {
    & cloudflared tunnel --url "http://127.0.0.1:$Port" --protocol http2 --allowed-mail $AllowedEmail
} else {
    Write-Host 'Anyone with the URL can access the dashboard, including server-camera and phone options.'
    & cloudflared tunnel --url "http://127.0.0.1:$Port" --protocol http2
}
