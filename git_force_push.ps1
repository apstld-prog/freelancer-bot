param(
    [string[]]$Files = @(),
    [string]$Message = "Deploy: force push"
)

$ErrorActionPreference = "Stop"

function Pause-End {
    Write-Host ""
    Read-Host "Press ENTER to close..." | Out-Null
}

try {
    # Έλεγχος ότι υπάρχει git
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "[ERROR] Git not found in PATH."
    }

    # Stage συγκεκριμένων αρχείων ή όλων
    if ($Files.Count -gt 0) {
        foreach ($f in $Files) {
            if (Test-Path -LiteralPath $f) {
                git add -- "$f" | Out-Null
            } else {
                Write-Host "[WARN] File not found, skipping: $f"
            }
        }
    } else {
        git add -A | Out-Null
    }

    # Αν δεν υπάρχουν staged changes, γράφουμε marker για να υπάρχει diff
    $diff = git diff --cached --name-only
    if (-not $diff) {
        $tick = ".deploy_tick"
        $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        "deploy tick: $ts" | Out-File -FilePath $tick -Encoding utf8
        git add -- "$tick" | Out-Null
    }

    # Commit (επιτρέπει και empty)
    git commit -m "$Message" --allow-empty | Out-Null

    # Push
    git push | Out-Null

    Write-Host ""
    Write-Host "PUSH COMPLETED - Render will redeploy"
}
catch {
    Write-Host ""
    Write-Host "OPERATION FAILED"
    Write-Host ($_.Exception.Message)
}
finally {
    Pause-End
}
