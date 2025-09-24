# Fix Secret Leak - Simple ASCII PowerShell Script

param(
  [string] $Branch = "main",
  [switch] $SkipPipInstall
)

function Fail($msg) { Write-Host "ERROR: $msg"; exit 1 }

# 1) Checks
if (-not (Test-Path ".git")) { Fail ".git folder not found. Run this in your repo root." }

git --version *> $null 2>&1
if ($LASTEXITCODE -ne 0) { Fail "git not found in PATH." }

python --version *> $null 2>&1
if ($LASTEXITCODE -ne 0) { Fail "python not found in PATH." }

$remote = (git remote get-url origin) 2>$null
if (-not $remote) { Fail "No 'origin' remote is set. Example: git remote add origin https://github.com/USER/REPO.git" }
Write-Host "Remote origin: $remote"

# 2) Backup
$repoName = Split-Path -Leaf (Get-Location)
$now = Get-Date -Format "yyyyMMdd-HHmmss"
$bundlePath = Join-Path (Split-Path -Parent (Get-Location)) "$repoName-backup-$now.bundle"
Write-Host "Creating backup bundle: $bundlePath"
git bundle create "$bundlePath" --all
if ($LASTEXITCODE -ne 0) { Fail "Failed to create backup bundle." }

# 3) .gitignore and untrack .env
$gitignore = @"
# Env & secrets
.env
.env.*
!.env.example

# Python
__pycache__/
*.pyc
.venv/
venv/

# OS/IDE
.DS_Store
Thumbs.db
.vscode/
.idea/

# Office/Binary
*.xlsx
*.xls
*.docx
*.pptx

# Logs
*.log
"@

if (-not (Test-Path ".gitignore")) {
  Set-Content -Path ".gitignore" -Value $gitignore -NoNewline
} else {
  $existing = Get-Content ".gitignore" -Raw
  if ($existing -notmatch "\.env") { Add-Content ".gitignore" "`r`n.env`r`n.env.*`r`n!.env.example" }
  if ($existing -notmatch "__pycache__") { Add-Content ".gitignore" "`r`n__pycache__/`r`n*.pyc" }
}

# Remove .env from index if tracked
git ls-files --error-unmatch .env *> $null 2>&1
if ($LASTEXITCODE -eq 0) { git rm --cached .env }

git add .gitignore
git commit -m "Add/Update .gitignore and untrack .env" *> $null 2>&1

# 4) Install git-filter-repo
if (-not $SkipPipInstall) {
  Write-Host "Installing/Updating git-filter-repo..."
  python -m pip install --upgrade git-filter-repo
  if ($LASTEXITCODE -ne 0) { Fail "pip install git-filter-repo failed." }
}

# 5) Replace PostgreSQL URIs and purge .env from history
$repl = @"
regex:postgresql(\+psycopg2)?:\/\/[^\s'"]+==>REDACTED_DB_URL
"@
Set-Content -Path "replacements.txt" -Value $repl -NoNewline

# Remove .env entirely (if it ever existed in history)
git filter-repo --path .env --invert-paths --force *> $null 2>&1

# Replace DB URIs everywhere
git filter-repo --replace-text replacements.txt --force *> $null 2>&1
if ($LASTEXITCODE -ne 0) { Fail "git-filter-repo rewrite failed." }

# 6) Force push
Write-Host "Force pushing cleaned history..."
git push --force --tags origin $Branch
if ($LASTEXITCODE -ne 0) { Fail "Force push failed." }

# 7) Pre-commit hook to block .env commits
$hookPath = ".git/hooks/pre-commit"
$hook = @"
#!/bin/sh
if git diff --cached --name-only | grep -E '(^|/)\.env($|\.|/)' >/dev/null; then
  echo 'Blocked: .env is staged. Remove it before commit.'
  exit 1
fi
exit 0
"@
Set-Content -Path $hookPath -Value $hook -NoNewline
git update-index --chmod=+x $hookPath *> $null 2>&1

Write-Host "Done. Next steps:"
Write-Host "1) Rotate tokens (e.g., Telegram BOT_TOKEN via BotFather /token)."
Write-Host "2) Update Render Environment with new secrets."
Write-Host "3) Redeploy service."
