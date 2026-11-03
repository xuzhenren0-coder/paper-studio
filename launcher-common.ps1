function Get-PaperStudioPaths {
    param([string]$Root, [string]$DataDirectory)
    $pythonPath = Join-Path $Root 'runtime/python.exe'
    $portable = Test-Path -LiteralPath $pythonPath
    if (-not $portable) { $pythonPath = Join-Path $Root '.venv/Scripts/python.exe' }
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        $pythonPath = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    }
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw '未找到运行环境。普通用户请下载 Windows 免安装包；源码用户请按 README 创建 .venv。' }
    if (-not $DataDirectory) { $DataDirectory = $env:PAPER_DATA_DIR }
    if (-not $DataDirectory) {
        if ($portable) { $DataDirectory = Join-Path $env:LOCALAPPDATA 'PaperStudio' }
        else { $DataDirectory = Join-Path $Root '.local' }
    }
    $DataDirectory = [IO.Path]::GetFullPath($DataDirectory)
    $identity = (([IO.Path]::GetFullPath($Root)) + '|' + $DataDirectory).Replace('\','/').ToLowerInvariant()
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $instance = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($identity)))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
    return @{ Python=$pythonPath; Data=$DataDirectory; Instance=$instance }
}
