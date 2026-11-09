param([ValidatePattern('^[a-f0-9]{32}$')][string]$RunId)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$voiceWork = Join-Path $project 'work\voice'
if ($RunId) { $voiceWork = Join-Path $voiceWork ('managed\' + $RunId) }
$configFile = Join-Path $voiceWork 'sion-infer.yaml'
$cancelled = Join-Path $voiceWork 'cancelled'
$backend = $env:SION_GPT_SOVITS_DIR
$pythonExe = $env:SION_VOICE_PYTHON
$gptWeights = $env:SION_VOICE_GPT_WEIGHTS
$sovitsWeights = $env:SION_VOICE_SOVITS_WEIGHTS
if (!$backend -or !$pythonExe -or !$gptWeights -or !$sovitsWeights) { throw '请先按 README 设置本机配音环境，或直接连接已运行的配音服务。' }
foreach ($item in @($pythonExe,(Join-Path $backend 'api_v2.py'),$gptWeights,$sovitsWeights)) {
    if (-not (Test-Path -LiteralPath $item -PathType Leaf)) { throw "缺少本机语音依赖：$item" }
}
$existing = Get-NetTCPConnection -State Listen -LocalPort 9880 -ErrorAction SilentlyContinue
if ($existing) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($existing[0].OwningProcess)" -ErrorAction SilentlyContinue
    if ($owner -and $owner.CommandLine -and $owner.CommandLine.Contains($configFile) -and $owner.CommandLine.Contains('api_v2.py')) {
        Write-Output '本项目诗音语音服务已经运行。'; exit
    }
    throw '9880 端口已被其他服务占用，未替换或停止它。'
}
New-Item -ItemType Directory -Force $voiceWork | Out-Null
$config = @"
custom:
  bert_base_path: GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large
  cnhuhbert_base_path: GPT_SoVITS/pretrained_models/chinese-hubert-base
  device: cuda
  is_half: true
  version: v2
  t2s_weights_path: '$($gptWeights.Replace('\','/'))'
  vits_weights_path: '$($sovitsWeights.Replace('\','/'))'
"@
[System.IO.File]::WriteAllText($configFile,$config,[System.Text.UTF8Encoding]::new($false))
if ($RunId -and (Test-Path -LiteralPath $cancelled)) { exit }
$arguments = 'api_v2.py -a 127.0.0.1 -p 9880 -c "' + $configFile + '"'
$process = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $voiceWork 'stdout.log') -RedirectStandardError (Join-Path $voiceWork 'stderr.log')
@{ pid=$process.Id; config=$configFile; backend=$backend } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $voiceWork 'process.json')
if ($RunId -and (Test-Path -LiteralPath $cancelled)) { & (Join-Path $PSScriptRoot 'Stop-Voice.ps1') -RunId $RunId; exit }
Write-Output '已启动独立诗音语音进程；模型加载需要时间。日志位于本项目 work\voice。请确认日志成功后再测试合成。'
