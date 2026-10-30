[CmdletBinding()]
param(
    [Alias('Profile')]
    [ValidateSet('low_memory', 'quality')]
    [string]$BuildProfile = 'low_memory',
    [switch]$ReportsOnly,
    [string]$VivadoPath = 'D:\Xilinx\Vivado\2020.2\bin\vivado.bat'
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $VivadoPath -PathType Leaf)) {
    throw "Vivado not found: $VivadoPath"
}

# Run one foreground batch process. Do not launch GUI, simulation, or other jobs.
$taskOutput = Join-Path $PSScriptRoot $BuildProfile
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
$taskScript = 'synth_zc702.tcl'
$taskLog = 'vivado_synth.log'
$taskJournal = 'vivado_synth.jou'
$taskMarker = 'ZC702_REVIEW_SYNTH_DONE'
if ($ReportsOnly) {
    $taskScript = 'report_zc702.tcl'
    $taskLog = 'vivado_reports.log'
    $taskJournal = 'vivado_reports.jou'
    $taskMarker = 'ZC702_REVIEW_REPORTS_DONE'
    if (-not (Test-Path -LiteralPath (Join-Path $taskOutput 'qkd_pp_axi_synth.dcp'))) {
        throw 'Run synthesis successfully before requesting reports.'
    }
}

$taskOS = Get-CimInstance Win32_OperatingSystem
$taskFreeGB = [math]::Round($taskOS.FreePhysicalMemory / 1MB, 2)
Write-Host "Available physical RAM: $taskFreeGB GB. Profile: $BuildProfile. Threads: 2."
if ($taskFreeGB -lt 2) {
    Write-Warning 'Less than 2 GB RAM is free. Close browsers, Vivado GUI, and simulations before a full run.'
}

$taskExitCode = 1
Push-Location -LiteralPath $taskOutput
try {
    & $VivadoPath -mode batch -source (Join-Path $PSScriptRoot $taskScript) -log $taskLog -journal $taskJournal -tclargs $BuildProfile
    $taskExitCode = $LASTEXITCODE
    if ($taskExitCode -eq 0 -and -not (Select-String -LiteralPath $taskLog -SimpleMatch $taskMarker -Quiet)) {
        throw "Vivado exited without the completion marker. Inspect $taskOutput\$taskLog"
    }
    if ($taskExitCode -ne 0) {
        throw "Vivado failed with exit code $taskExitCode. Inspect $taskOutput\$taskLog"
    }
    Write-Host "Completed. Outputs: $taskOutput"
} finally {
    Pop-Location
}
