$ErrorActionPreference = "Stop"

$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = (Join-Path $workspace ".venv\Scripts\python.exe")

try {
    $candidates = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq "python.exe" -and
            $_.ExecutablePath -and
            $_.ExecutablePath -ieq $venvPython -and
            $_.CommandLine -and
            $_.CommandLine -match "(^| )-m pytest( |$)|pytest"
        } |
        Sort-Object ProcessId
} catch {
    Write-Host "Kunne ikke lese prosessdetaljer via CIM. Ingen prosesser ble stoppet."
    Write-Host "Kjor i stedet PowerShell som vanlig bruker/admin og prov igjen."
    exit 1
}

if (-not $candidates) {
    Write-Host "Ingen hengende pytest-prosesser funnet for denne workspacen."
    exit 0
}

foreach ($proc in $candidates) {
    Write-Host ("Stopper pytest-prosess PID {0}" -f $proc.ProcessId)
    Stop-Process -Id $proc.ProcessId -Force
}

Write-Host ("Stoppet {0} pytest-prosess(er)." -f $candidates.Count)
