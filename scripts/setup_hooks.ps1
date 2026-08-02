# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

$ErrorActionPreference = 'Stop'

$HookFile = '.git/hooks/pre-push'

# Git on Windows runs hooks via Git Bash, so the hook body must be bash.
$HookBody = @'
#!/usr/bin/env bash
# Pre-push hook (no auto-sweep)
bash scripts/_pyrun.sh scripts/submit_log.py || true
exit 0
'@

# Write the hook without a UTF-8 BOM and normalize to LF line endings (BOM/CRLF break bash shebangs).
$hookText = $HookBody -replace "`r`n", "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($HookFile, $hookText, $utf8NoBom)

# If bash is available (Git Bash), make the hook executable using a Unix-style path.
try {
    $bash = Get-Command bash -ErrorAction SilentlyContinue
    if ($bash) {
        $hookPathUnix = (Get-Item $HookFile).FullName -replace '\\','/'
        & bash -lc "chmod +x '$hookPathUnix'" 2>$null
    }
} catch { }

Write-Host "[ai-log] Git pre-push hook installed."

if (-not (Test-Path .ai-log)) { New-Item -ItemType Directory -Path .ai-log | Out-Null }
if (-not (Test-Path .ai-log/.gitkeep)) { New-Item -ItemType File -Path .ai-log/.gitkeep | Out-Null }

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
