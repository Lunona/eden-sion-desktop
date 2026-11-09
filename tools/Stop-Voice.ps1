param([ValidatePattern('^[a-f0-9]{32}$')][string]$RunId)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$voiceWork = Join-Path $project 'work\voice'
if ($RunId) {
    $voiceWork = Join-Path $voiceWork ('managed\' + $RunId)
    New-Item -ItemType Directory -Force $voiceWork | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $voiceWork 'cancelled'), '')
}
$expected = Join-Path $voiceWork 'sion-infer.yaml'
$record = Join-Path $voiceWork 'process.json'
$info = $null
if (Test-Path -LiteralPath $record) {
    $info = Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
    if ($info.config -ne $expected) { throw '进程记录与本项目不匹配，未停止。' }
} elseif (!$RunId) { Write-Output '没有本项目启动的语音进程记录。'; exit }
# A Windows virtualenv launcher can have a separate python-base child. Match
# the exact project config in every process instead of killing a generic tree.
$targets = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($expected) -and $_.CommandLine.Contains('api_v2.py')
})
if (-not $targets.Count) { Write-Output '本项目语音进程已退出。'; exit }
$targets | Sort-Object @{Expression={if($_.ParentProcessId -eq [int]$info.pid){0}else{1}}} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
}
Write-Output '已停止本项目语音服务及其匹配的 Python 启动进程。'
