<#
fix_bot_conflict.ps1  (PowerShell 5/7 compatible)
- Cleans Git conflict markers from a file (default: bot.py)
- Keeps either "ours" or "theirs" side
- Stages the file; if a rebase is in progress -> rebase --continue
- Optional push (safe pull --rebase --autostash beforehand)

USAGE EXAMPLES:
  powershell -ExecutionPolicy Bypass -File .\fix_bot_conflict.ps1
  powershell -ExecutionPolicy Bypass -File .\fix_bot_conflict.ps1 -File bot.py -Side ours
  powershell -ExecutionPolicy Bypass -File .\fix_bot_conflict.ps1 -File bot.py -Side theirs -Push -Branch main
#>

param(
  [string]$File = "bot.py",
  [ValidateSet("ours","theirs")]
  [string]$Side = "ours",
  [string]$Branch = "",
  [switch]$Push
)

$ErrorActionPreference = "Stop"

function Write-Section($t){ Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Write-Warn($t){ Write-Host $t -ForegroundColor Yellow }
function Write-Err($t){ Write-Host $t -ForegroundColor Red }

# --- Sanity checks ---
Write-Section "Checks"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Err "Git not found."; exit 1 }
if (-not (Test-Path ".git")) { Write-Err "Not a git repo."; exit 1 }
if (-not (Test-Path $File)) { Write-Err "File not found: $File"; exit 1 }

# --- Backup ---
$stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
$backup = "$File.$stamp.bak"
Copy-Item -LiteralPath $File -Destination $backup -Force
Write-Host "Backup created: $backup"

# --- Load file content (PS5/PS7 compatible) ---
Write-Section "Resolving conflict markers ($Side)"
$text = [System.IO.File]::ReadAllText((Resolve-Path $File))
# Split lines in a way that works across CRLF/LF
$lines = $text -split "(`r`n|`n)"

# State machine to keep one side:
# between <<<<<<< and ======= is OURS; between ======= and >>>>>>> is THEIRS
$sb = New-Object System.Text.StringBuilder
$inConflict = $false
$takingOurs = $false
$takingTheirs = $false

foreach ($line in $lines) {
  if ($line -like '<<<<<<<*') {
    $inConflict = $true
    $takingOurs = ($Side -eq 'ours')
    $takingTheirs = ($Side -eq 'theirs')
    continue
  }
  if ($inConflict -and $line -like '=======') {
    # flip to the other half of the conflict
    $takingOurs   = ($Side -eq 'theirs')
    $takingTheirs = ($Side -eq 'ours')
    continue
  }
  if ($inConflict -and $line -like '>>>>>>>*') {
    # end of conflict block
    $inConflict = $false
    $takingOurs = $false
    $takingTheirs = $false
    continue
  }

  if (-not $inConflict) {
    [void]$sb.AppendLine($line)
  } else {
    if ( ($Side -eq 'ours'   -and $takingOurs)   -or
         ($Side -eq 'theirs' -and $takingTheirs) ) {
      [void]$sb.AppendLine($line)
    }
  }
}

$resolved = $sb.ToString()

# Basic sanity: warn if markers still present
if ($resolved -match '<<<<<<<|=======|>>>>>>>') {
  Write-Warn "Markers still detected after parse. Please review the file manually."
}

# Write back with UTF-8 (no BOM)
[System.IO.File]::WriteAllText((Resolve-Path $File), $resolved, [System.Text.UTF8Encoding]::new($false))
Write-Host "File resolved: $File"

# --- Git stage and continue rebase (if any) ---
Write-Section "Git stage + continue"
git add -- "%File%" | Out-Null

$inRebase = Test-Path ".git/rebase-merge" -PathType Container
if ($inRebase) {
  Write-Host "Rebase detected → git rebase --continue"
  $p = Start-Process git -ArgumentList "rebase","--continue" -NoNewWindow -PassThru -Wait
  if ($p.ExitCode -ne 0) {
    Write-Err "git rebase --continue failed. Fix remaining conflicts and re-run."
    exit $p.ExitCode
  }
} else {
  # Commit to keep history clean if not rebasing
  $msg = "Fix: resolve merge markers in $File"
  # If nothing to commit, this will just no-op
  $cp = Start-Process git -ArgumentList "commit","-m",$msg -NoNewWindow -PassThru -Wait
}

# Determine branch if not provided
if (-not $Branch) {
  $Branch = (& git rev-parse --abbrev-ref HEAD).Trim()
  if (-not $Branch) { $Branch = "main" }
}

# --- Optional push ---
if ($Push) {
  Write-Section "Push to origin/$Branch"
  Start-Process git -ArgumentList "fetch","origin" -NoNewWindow -PassThru -Wait | Out-Null
  $p1 = Start-Process git -ArgumentList "pull","--rebase","--autostash","origin",$Branch -NoNewWindow -PassThru -Wait
  if ($p1.ExitCode -ne 0) {
    Write-Warn "pull --rebase failed. Resolve conflicts, then re-run with -Push."
    exit $p1.ExitCode
  }
  $p2 = Start-Process git -ArgumentList "push","origin",$Branch -NoNewWindow -PassThru -Wait
  if ($p2.ExitCode -ne 0) {
    Write-Warn "git push failed. Consider manual push or --force-with-lease if needed."
    exit $p2.ExitCode
  }
  Write-Host "✅ Pushed to origin/$Branch"
} else {
  Write-Host "✅ Done. File fixed and staged/committed. (Use -Push to push automatically.)"
}
