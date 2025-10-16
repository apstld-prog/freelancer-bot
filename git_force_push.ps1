param(
    [string[]]$Files = @(),                 # π.χ. -Files bot.py, worker_runner.py
    [string]$Message = "Deploy: force push" # μήνυμα commit
)

$ErrorActionPreference = "Stop"

function Pause-End {
    Write-Host ""
    Read-Host "Press ENTER to close..." | Out-Null
}

try {
    # Έλεγχος εργαλείων
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "[ERROR] Git not found in PATH."
    }

    # Stage αρχείων
    if ($Files.Count -gt 0) {
        foreach ($f in $Files) {
            if (Test-Path $f) {
                git add -- "$f" | Out-Null
            } else {
                Write-Host "[WARN] File not found, skipping: $f" -ForegroundColor Yellow
            }
        }
    } else {
        git add -A | Out-Null
    }

    # Έλεγχος αν υπάρχουν staged changes
    $diff = git diff --cached --name-only
    if (-not $diff) {
        # Δεν υπάρχουν αλλαγές — φτιάξε/ενημέρωσε marker για «τεχνητή» αλλαγή
        $tick = ".deploy_tick"
        $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        "deploy tick: $ts" | Out-File -FilePath $tick -Encoding utf8
        git add -- "$tick" | Out-Null
    }

    # Commit (ακόμα κι αν είναι «κενό»)
    git commit -m "$Message" --allow-empty
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[INFO] Nothing to commit (working tree clean)." -ForegroundColor Yellow
    }

    # Push
    git push
    if ($LASTEXITCODE -ne 0) { throw "[ERROR] git push failed." }

    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "  PUSH COMPLETED — Render will redeploy" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "  OPERATION FAILED" -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host ($_.Exception.Message) -ForegroundColor Red
}
finally {
    Pause-End
}
