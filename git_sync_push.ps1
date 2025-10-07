<# 
git_sync_push.ps1
- Normalizes line endings via .gitattributes (creates/updates if needed)
- Optional renormalize pass
- Safe pull --rebase + push
- Optional force-with-lease
- Clear guidance on conflicts
Usage:
  pwsh -ExecutionPolicy Bypass -File .\git_sync_push.ps1
  pwsh -ExecutionPolicy Bypass -File .\git_sync_push.ps1 -Renormalize
  pwsh -ExecutionPolicy Bypass -File .\git_sync_push.ps1 -ForcePush
#>

param(
  [switch]$Renormalize = $false,
  [switch]$ForcePush = $false
)

$ErrorActionPreference = "Stop"

function Write-Section($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Write-Warn($t)    { Write-Host $t -ForegroundColor Yellow }
function Write-Err($t)     { Write-Host $t -ForegroundColor Red }
function Exit-With($code)  { Write-Host ""; exit $code }

function Invoke-Git([string]$ArgsLine) {
  Write-Host "git $ArgsLine" -ForegroundColor DarkGray
  $p = Start-Process -FilePath "git" -ArgumentList $ArgsLine -NoNewWindow -PassThru -Wait -RedirectStandardOutput out.txt -RedirectStandardError err.txt
  $out = Get-Content out.txt -Raw
  $err = Get-Content err.txt -Raw
  if ($out.Trim()) { Write-Host $out.Trim() }
  if ($err.Trim()) { Write-Warn $err.Trim() }
  Remove-Item out.txt, err.txt -ErrorAction SilentlyContinue
  return $p.ExitCode
}

# 0) Sanity checks
Write-Section "Checking environment"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Err "Git not found in PATH."
  Exit-With 1
}
if (-not (Test-Path ".git")) {
  Write-Err "This folder is not a git repository."
  Exit-With 1
}

# 1) Ensure .gitattributes
Write-Section "Ensuring .gitattributes"
$gattr = ".gitattributes"
$desired = @"
# Normalize text by default
* text=auto

# Unix-style endings
*.sh    text eol=lf
*.py    text eol=lf
*.yml   text eol=lf
*.yaml  text eol=lf
*.json  text eol=lf
*.md    text eol=lf
*.txt   text eol=lf

# Windows-style endings
*.ps1   text eol=crlf
*.bat   text eol=crlf
*.cmd   text eol=crlf

# Images/binaries (no conversion)
*.png   binary
*.jpg   binary
*.jpeg  binary
*.gif   binary
*.ico   binary
*.zip   binary
"@

$needRenorm = $false
if (-not (Test-Path $gattr)) {
  $desired | Out-File -FilePath $gattr -Encoding utf8 -NoNewline
  Write-Host "Created .gitattributes"
  $needRenorm = $true
} else {
  $current = Get-Content $gattr -Raw
  if ($current -ne $desired) {
    $desired | Out-File -FilePath $gattr -Encoding utf8 -NoNewline
    Write-Host "Updated .gitattributes"
    $needRenorm = $true
  } else {
    Write-Host ".gitattributes is up-to-date"
  }
}

# 2) Optional renormalize (or required if .gitattributes changed)
if ($Renormalize -or $needRenorm) {
  Write-Section "Renormalizing line endings"
  if ( (Invoke-Git "add --renormalize .") -ne 0 ) { Exit-With 1 }
  $msg = "Normalize line endings via .gitattributes"
  $code = Invoke-Git "commit -m `"$msg`""
  if ($code -eq 0) {
    Write-Host "Commit created for renormalization."
  } else {
    Write-Host "No renormalization changes to commit."
  }
}

# 3) Stage + commit current changes (if any)
Write-Section "Staging + committing"
if ( (Invoke-Git "add -A") -ne 0 ) { Exit-With 1 }
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$code = Invoke-Git "commit -m `"Auto commit $ts`""
if ($code -eq 0) {
  Write-Host "Commit created."
} else {
  Write-Host "No changes to commit."
}

# 4) Fetch + pull --rebase
Write-Section "Sync with remote (fetch + rebase)"
if ( (Invoke-Git "fetch origin") -ne 0 ) { Exit-With 1 }
$pullCode = Invoke-Git "pull --rebase origin main"
if ($pullCode -ne 0) {
  Write-Err "Rebase failed. Resolve conflicts, then run:"
  Write-Host "  git status"
  Write-Host "  git add -A"
  Write-Host "  git rebase --continue"
  Write-Host "When done, re-run this script."
  Exit-With $pullCode
}

# 5) Push (or force-with-lease)
Write-Section "Pushing to origin/main"
$pushArgs = "push origin main"
if ($ForcePush) {
  Write-Warn "Using --force-with-lease"
  $pushArgs = "push --force-with-lease origin main"
}
$pushCode = Invoke-Git $pushArgs

if ($pushCode -ne 0) {
  Write-Warn "Push failed — attempting one more fetch+rebase+push cycle"
  if ( (Invoke-Git "fetch origin") -ne 0 ) { Exit-With 1 }
  if ( (Invoke-Git "pull --rebase origin main") -ne 0 ) {
    Write-Err "Rebase failed on retry. Resolve conflicts, then re-run."
    Exit-With 1
  }
  $pushCode = Invoke-Git $pushArgs
}

if ($pushCode -eq 0) {
  Write-Host "`n✅ Success! Changes pushed."
  Exit-With 0
} else {
  Write-Err "`nPush still failing."
  Write-Host "If you *must* overwrite remote history: git push --force-with-lease origin main"
  Exit-With $pushCode
}
