param([ValidateRange(1024,65535)][int]$Port=8765, [string]$DataDirectory)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'launcher-common.ps1')
$paths = Get-PaperStudioPaths -Root $PSScriptRoot -DataDirectory $DataDirectory
$pidFile = Join-Path $paths.Data "server-$Port.json"
if (Test-Path -LiteralPath $pidFile) {
    $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $serverProcessId = [int]$record.pid
    $expectedScript = $record.script
} elseif ($Port -eq 8765 -and (Test-Path -LiteralPath (Join-Path $paths.Data 'server.pid'))) {
    $serverProcessId = [int](Get-Content -LiteralPath (Join-Path $paths.Data 'server.pid'))
    $expectedScript = Join-Path $PSScriptRoot 'server.py'
} else { Write-Host '未找到启动器的服务记录。'; exit 0 }
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $serverProcessId" -ErrorAction SilentlyContinue
$portPattern = '--port\s+' + $Port + '(?:\s|$)'
if ($processInfo -and $processInfo.CommandLine -and $processInfo.CommandLine.Contains($expectedScript) -and $processInfo.CommandLine -match $portPattern) {
    Stop-Process -Id $serverProcessId
    Write-Host '研读本地服务已停止，论文与笔记保留。'
} else { Write-Host '服务已退出，或进程不匹配；未停止其他程序。' }
