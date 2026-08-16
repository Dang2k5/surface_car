# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

$ErrorActionPreference = 'Stop'

$HookFile = '.git/hooks/pre-push'

# Git on Windows runs hooks via Git Bash, so the hook body must be bash.
$HookBody = @'
#!/usr/bin/env bash
# Pre-push: sweep recent Antigravity / Gemini prompts, then submit AI logs.
bash scripts/_pyrun.sh scripts/log_antigravity.py --auto || true
bash scripts/_pyrun.sh scripts/submit_log.py || true
exit 0
'@

# Write the hook without a UTF-8 BOM and normalize to LF line endings (BOM/CRLF break bash shebangs).
$hookText = $HookBody -replace "`r`n", "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($HookFile, $hookText, $utf8NoBom)

# <<<<<<< fearch_vth
# # Resolve Git Bash explicitly. `Get-Command bash` may select WSL's
# # C:\Windows\System32\bash.exe, which cannot execute Git hooks reliably.
# try {
#     $gitCommand = Get-Command git -ErrorAction Stop
#     $gitRoot = Split-Path (Split-Path $gitCommand.Source -Parent) -Parent
#     $gitBash = Join-Path $gitRoot 'bin\bash.exe'
#     if (Test-Path $gitBash) {
#         $hookPathUnix = (Get-Item $HookFile).FullName -replace '\\','/'
#         & $gitBash -lc "chmod +x '$hookPathUnix'"
#         if ($LASTEXITCODE -ne 0) {
#             throw "Git Bash chmod failed with exit code $LASTEXITCODE"
#         }
#     } else {
#         throw "Git Bash not found at $gitBash"
#     }
# } catch {
#     throw "Could not make the pre-push hook executable: $($_.Exception.Message)"
# }
# =======
# # If bash is available (Git Bash), make the hook executable using a Unix-style path.
# try {
#     $bash = Get-Command bash -ErrorAction SilentlyContinue
#     if ($bash) {
#         $hookPathUnix = (Get-Item $HookFile).FullName -replace '\\','/'
#         & bash -lc "chmod +x '$hookPathUnix'" 2>$null
#     }
# } catch { }
# >>>>>>> main

Write-Host "[ai-log] Git pre-push hook installed."

if (-not (Test-Path .ai-log)) { New-Item -ItemType Directory -Path .ai-log | Out-Null }
if (-not (Test-Path .ai-log/.gitkeep)) { New-Item -ItemType File -Path .ai-log/.gitkeep | Out-Null }

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
