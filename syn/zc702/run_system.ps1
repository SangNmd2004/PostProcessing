[CmdletBinding()]
param(
    [ValidateSet('validate', 'synth', 'implement', 'all')]
    [string]$Stage = 'validate',
    [string]$VivadoPath = 'D:\Xilinx\Vivado\2020.2\bin\vivado.bat'
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$taskOutput = Join-Path $taskRoot 'build\zc702'
if (-not (Test-Path -LiteralPath $VivadoPath -PathType Leaf)) { throw "Vivado not found: $VivadoPath" }
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
$taskStages = @($Stage)
if ($Stage -eq 'all') { $taskStages = @('validate', 'synth', 'implement') }
foreach ($taskStage in $taskStages) {
    $taskScript = Join-Path $PSScriptRoot 'build_system.tcl'
    $taskArguments = @('-tclargs', $taskStage)
    $taskMarker = "ZC702_SYSTEM_$($taskStage.ToUpper())_DONE"
    if ($taskStage -eq 'validate') {
        if (Test-Path -LiteralPath (Join-Path $taskOutput 'project\qkd_zc702.xpr')) {
            $taskValidateLog = Join-Path $taskOutput 'validate.log'
            $taskValidated = (Test-Path -LiteralPath $taskValidateLog) -and
                (Select-String -LiteralPath $taskValidateLog -Pattern '^ZC702_BD_VALIDATE_DONE$' -Quiet)
            if ($Stage -eq 'all' -and $taskValidated) {
                Write-Host 'Using existing validated project; skipping creation.'
                continue
            }
            throw 'Project exists. Continue with -Stage synth or -Stage implement.'
        }
        $taskScript = Join-Path $PSScriptRoot 'create_system.tcl'
        $taskArguments = @()
        $taskMarker = 'ZC702_BD_VALIDATE_DONE'
    }
    if ($taskStage -eq 'synth') {
        $taskValidateLog = Join-Path $taskOutput 'validate.log'
        if (-not ((Test-Path -LiteralPath $taskValidateLog) -and
            (Select-String -LiteralPath $taskValidateLog -Pattern '^ZC702_BD_VALIDATE_DONE$' -Quiet))) {
            throw 'Block design creation/validation is incomplete. Inspect validate.log first.'
        }
    }
    if ($taskStage -eq 'implement' -and -not (Test-Path -LiteralPath (Join-Path $taskOutput 'system_synth.dcp'))) {
        throw 'The system synthesis checkpoint is missing.'
    }
    $taskLog = "${taskStage}.log"
    Push-Location -LiteralPath $taskOutput
    try {
        Write-Host "ZC702 stage=$taskStage; threads=2; one Vivado process at a time."
        & $VivadoPath -mode batch -source $taskScript -log $taskLog -journal "${taskStage}.jou" @taskArguments
        if ($LASTEXITCODE -ne 0) { throw "Vivado failed. Inspect $taskOutput\$taskLog" }
        if (-not (Select-String -LiteralPath $taskLog -SimpleMatch $taskMarker -Quiet)) {
            throw "Missing completion marker. Inspect $taskOutput\$taskLog"
        }
    } finally { Pop-Location }
}
