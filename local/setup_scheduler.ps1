# Configura il Task Scheduler di Windows per pubblicare 3 Short al giorno.
# Esegui UNA VOLTA come Amministratore:
#   Tasto destro su PowerShell > "Esegui come amministratore"
#   cd "C:\Users\nicco\Desktop\tiktok"
#   .\local\setup_scheduler.ps1

$TaskName   = "TikTok-Pipeline-3xDay"
$ScriptPath = "C:\Users\nicco\Desktop\tiktok\local\auto_run.bat"
$WorkDir    = "C:\Users\nicco\Desktop\tiktok"

# Tre orari di pubblicazione al giorno (modificabili)
$Times = @("09:00", "14:00", "19:00")

# Rimuovi task precedenti se esistono
foreach ($name in @($TaskName, "TikTok-Pipeline-AutoRun")) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Task precedente rimosso: $name"
    }
}

# Azione: esegui auto_run.bat
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$ScriptPath`"" `
    -WorkingDirectory $WorkDir

# Trigger: uno per ciascun orario, ogni giorno
$triggers = @()
foreach ($t in $Times) {
    $triggers += New-ScheduledTaskTrigger -Daily -At $t
}

# Impostazioni
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -WakeToRun `
    -RunOnlyIfNetworkAvailable `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

# Registra il task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host ""
Write-Host "Task '$TaskName' creato!"
Write-Host "  Pubblica 1 Short a ciascuno di questi orari, ogni giorno:"
foreach ($t in $Times) { Write-Host "    - $t" }
Write-Host ""
Write-Host "  = 3 Short al giorno, in automatico."
Write-Host ""
Write-Host "Test immediato:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Per rimuovere:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host "Log in:          $WorkDir\logs\"
