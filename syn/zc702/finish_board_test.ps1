[CmdletBinding()]
param([switch]$WaitForImplementation, [string]$Port = 'COM3',
      [ValidateSet('implement.log','export.log')][string]$CompletionLog = 'implement.log')
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$taskOutput = Join-Path $taskRoot 'build\zc702'
Push-Location -LiteralPath $taskRoot
try {
    if ($WaitForImplementation) {
        $taskDeadline = (Get-Date).AddMinutes(15)
        do {
            $taskLog = Join-Path $taskOutput $CompletionLog
            if (Select-String -LiteralPath $taskLog -Pattern '^ERROR:' -Quiet) {
                throw 'Implementation failed; no board programming was attempted.'
            }
            if (Select-String -LiteralPath $taskLog -Pattern '^ZC702_SYSTEM_IMPLEMENT_DONE$' -Quiet) { break }
            if ((Get-Date) -gt $taskDeadline) { throw 'Timed out waiting for implementation.' }
            Start-Sleep -Seconds 2
        } while ($true)
    }
    & python .\syn\zc702\verify_bundle.py
    if ($LASTEXITCODE -ne 0) { throw 'Hardware bundle verification failed.' }
    $taskBuildLog = Join-Path $taskOutput 'smoke_fixed_build.log'
    # Windows PowerShell 5.1 treats native stderr (including compiler notes) as
    # ErrorRecords when redirected. Judge native tools by exit code + markers.
    $taskSavedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & 'D:\Xilinx\Vitis\2020.2\bin\xsct.bat' .\syn\zc702\build_smoke.tcl *> $taskBuildLog
    $taskBuildExitCode = $LASTEXITCODE
    $ErrorActionPreference = $taskSavedPreference
    if ($taskBuildExitCode -ne 0 -or -not (Select-String -LiteralPath $taskBuildLog -Pattern '^ZC702_SMOKE_BUILD_DONE$' -Quiet)) {
        Get-Content -LiteralPath $taskBuildLog -Tail 25
        throw 'Firmware build failed; no board programming was attempted.'
    }
    $taskIncludes = Join-Path $taskOutput 'vitis\qkd_zc702_platform\ps7_cortexa9_0\standalone_domain\bsp\ps7_cortexa9_0\include'
    $ErrorActionPreference = 'Continue'
    & 'D:\Xilinx\Vitis\2020.2\gnu\aarch32\nt\gcc-arm-none-eabi\bin\arm-none-eabi-gcc.exe' -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard -std=c11 -Wall -Wextra -Werror -fsyntax-only -I $taskIncludes .\firmware\zc702\smoke_main.c *> (Join-Path $taskOutput 'strict_compile.log')
    $taskCompileExitCode = $LASTEXITCODE
    $ErrorActionPreference = $taskSavedPreference
    if ($taskCompileExitCode -ne 0) { throw 'Strict firmware compilation check failed; inspect strict_compile.log.' }
    if (-not (Test-Path -LiteralPath (Join-Path $taskOutput 'vitis\qkd_smoke\Debug\qkd_smoke.elf'))) {
        throw 'Firmware ELF is missing.'
    }
    & python .\syn\zc702\verify_bundle.py
    if ($LASTEXITCODE -ne 0) { throw 'Firmware/BSP bundle verification failed.' }
    & python .\syn\zc702\run_board_test.py --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Physical board test did not pass; inspect board_runs evidence.' }
    & python .\syn\zc702\verify_bundle.py
    if ($LASTEXITCODE -ne 0) { throw 'Post-test evidence verification failed.' }
} finally { Pop-Location }
