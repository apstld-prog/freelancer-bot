<#
fix_bot_syntax.ps1  — PowerShell 5/7
Clean up bot.py (or any file) from merge markers & invisible chars, normalize newlines,
validate with Python AST, and optionally commit/push.

USAGE:
  powershell -ExecutionPolicy Bypass -File .\fix_bot_syntax.ps1
  powershell -ExecutionPolicy Bypass -File .\fix_bot_syntax.ps1 -File bot.py -Push -Branch main
#>

param(
  [string]$File = "bot.py",
  [switch]$Push,
  [string]$Branch = ""
)

$ErrorActionPreference = "Stop"

function Section($t){ Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Warn($t){ Write-Host $t -ForegroundColor Yellow }
function Err($t){ Write-Host $t -ForegroundColor Red }

Section "Checks"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Err "Git not found"; exit 1 }
if (-not (Test-Path ".git")) { Err "Not a git repo"; exit 1 }
if (-not (Test-Path $File)) { Err "File not found: $File"; exit 1 }

# Backup
$stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
$bak = "$File.$stamp.bak"
Copy-Item -LiteralPath $File -Destination $bak -Force
Write-Host "Backup: $bak"

# Load raw text
$text = [System.IO.File]::ReadAllText((Resolve-Path $File))

Section "Sanitize conflict markers & invisible chars"

# Remove UTF-8 BOM if present
if ($text.Length -gt 0 -and $text[0] -eq [char]0xFEFF) {
  $text = $text.Substring(1)
  Write-Host "Removed BOM"
}

# Normalize newlines to LF
$text = $text -replace "`r`n","`n" -replace "`r","`n"

# Remove zero-width & other weird control chars (keep tabs/newlines)
$ZW = "[`u200B-`u200F`u202A-`u202E`u2060-`u206F`u00A0]"
$text = [regex]::Replace($text, $ZW, "")
# Remove stray NULLs etc (control chars except tabs/newlines)
$text = ($text.ToCharArray() | ForEach-Object {
  $c = [int]$_
  if (($c -eq 9) -or ($c -eq 10) -or ($c -eq 13) -or ($c -ge 32)) { [char]$c }
}) -join ""

# Resolve Git conflict markers by KEEPING "ours" (above =======)
# If θέλεις "theirs", άλλαξε το $keepSide σε "theirs"
$keepSide = "ours"
$lines = $text -split "`n"
$sb = New-Object System.Text.StringBuilder
$in = $false; $takingOurs = $false; $takingTheirs = $false

foreach ($line in $lines) {
  if ($line -like '<<<<<<<*') { $in=$true; $takingOurs=($keepSide -eq 'ours'); $takingTheirs=($keepSide -eq 'theirs'); continue }
  if ($in -and $line -like '=======') { $takingOurs=($keepSide -eq 'theirs'); $takingTheirs=($keepSide -eq 'ours'); continue }
  if ($in -and $line -like '>>>>>>>*') { $in=$false; $takingOurs=$false; $takingTheirs=$false; continue }
  if (-not $in) {
    [void]$sb.AppendLine($line)
  } else {
    if ( ($keepSide -eq 'ours'   -and $takingOurs) -or
         ($keepSide -eq 'theirs' -and $takingTheirs) ) {
      [void]$sb.AppendLine($line)
    }
  }
}

$text = $sb.ToString()

# Final sanity: remove any leftover markers just in case (comment out instead of delete if προτιμάς)
$text = $text -replace '(?m)^\s*<<<<<<<.*$','' -replace '(?m)^\s*=======$','' -replace '(?m)^\s*>>>>>>>.*$',''

# Ensure file ends with newline
if (-not $text.EndsWith("`n")) { $text += "`n" }

# Save back (UTF-8 no BOM)
[System.IO.File]::WriteAllText((Resolve-Path $File), $text, [System.Text.UTF8Encoding]::new($false))
Write-Host "Sanitized & saved: $File"

Section "Validate Python syntax (AST parse)"
# Try python commands (py/python/python3)
$py = $null
foreach ($cand in @("py","python","python3")) {
  $p = (Get-Command $cand -ErrorAction SilentlyContinue)
  if ($p) { $py = $p.Source; break }
}
if (-not $py) {
  Warn "Python not found in PATH. Skipping AST validation."
} else {
  $code = @"
import ast, sys
p = r'''$((Resolve-Path $File).Path)'''
with open(p, 'r', encoding='utf-8') as f:
    src = f.read()
try:
    ast.parse(src, filename=p)
except SyntaxError as e:
    print("SYNTAX_ERROR", e.lineno, e.offset or 1, e.msg)
    print("-----CONTEXT-----")
    lines = src.splitlines()
    i = max(0, e.lineno-11); j = min(len(lines), e.lineno+10)
    for idx in range(i, j):
        mark = ">>" if (idx+1)==e.lineno else "  "
        print(f"{mark} {idx+1:5d}: {lines[idx]}")
    sys.exit(2)
print("OK")
"@
  $tmp = Join-Path $env:TEMP "astcheck_$(Get-Random).py"
  Set-Content -Path $tmp -Value $code -Encoding UTF8
  $p = Start-Process -FilePath $py -ArgumentList $tmp -NoNewWindow -PassThru -Wait
  Remove-Item $tmp -ErrorAction SilentlyContinue
  if ($p.ExitCode -ne 0) {
    Err "Python AST validation failed. See context above. Fix that line range and re-run."
    exit $p.ExitCode
  } else {
    Write-Host "AST: OK"
  }
}

Section "Git stage/commit"
git add -- "$File" | Out-Null
$ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
$commitMsg = "Fix: sanitize & resolve syntax/merge issues in $File at $ts"
# Commit if there is something staged
$needCommit = (git diff --cached --name-only) -ne $null
if ($needCommit) {
  git commit -m "$commitMsg" | Out-Null
  Write-Host "Committed."
} else {
  Write-Host "Nothing to commit."
}

# Determine branch if missing
if (-not $Branch) {
  $Branch = (& git rev-parse --abbrev-ref HEAD).Trim()
  if (-not $Branch) { $Branch = "main" }
}

if ($Push) {
  Section "Fetch + pull --rebase --autostash + push"
  git fetch origin | Out-Null
  $p1 = Start-Process git -ArgumentList "pull","--rebase","--autostash","origin",$Branch -NoNewWindow -PassThru -Wait
  if ($p1.ExitCode -ne 0) { Err "pull --rebase failed. Resolve conflicts and re-run."; exit $p1.ExitCode }
  $p2 = Start-Process git -ArgumentList "push","origin",$Branch -NoNewWindow -PassThru -Wait
  if ($p2.ExitCode -ne 0) { Err "push failed. Consider --force-with-lease if you intend to overwrite."; exit $p2.ExitCode }
  Write-Host "✅ Pushed to origin/$Branch"
} else {
  Write-Host "✅ Done (no push). Use -Push to push automatically."
}
