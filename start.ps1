param([switch]$NoBrowser, [ValidateRange(1024,65535)][int]$Port=8765, [string]$DataDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
. (Join-Path $projectRoot 'launcher-common.ps1')
$paths = Get-PaperStudioPaths -Root $projectRoot -DataDirectory $DataDirectory
$env:PAPER_DATA_DIR = $paths.Data
$url = "http://127.0.0.1:$Port"
$running = $false
$health = $null
try { $health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 2 } catch { }
if ($health) {
    if ($health.app -eq 'paper-studio' -and $health.instance -eq $paths.Instance) { $running = $true }
    else { throw '端口已被其他版本或资料库占用。请先停止旧版，或用 -Port 指定其他端口。' }
}
if (-not $running) {
    New-Item -ItemType Directory -Path $paths.Data -Force | Out-Null
    $arguments = @(('"' + (Join-Path $projectRoot 'server.py') + '"'), '--port', "$Port")
    $process = Start-Process -FilePath $paths.Python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $paths.Data "server-$Port.error.log") -RedirectStandardOutput (Join-Path $paths.Data "server-$Port.log")
    @{ pid=$process.Id; script=(Join-Path $projectRoot 'server.py'); instance=$paths.Instance } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $paths.Data "server-$Port.json") -Encoding UTF8
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 200
        try {
            $health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 1
            if ($health.app -eq 'paper-studio' -and $health.instance -eq $paths.Instance) { $running=$true; break }
        } catch { }
    }
}
if (-not $running) { throw "启动失败，请查看 $($paths.Data) 中的 server-$Port.error.log。" }
Write-Host "研读已启动：$url"
Write-Host "学习数据：$($paths.Data)"
if (-not $NoBrowser) { Start-Process $url }
