<#
.SYNOPSIS
  启动 management-system 后端（Windows PowerShell 版）
.DESCRIPTION
  等价于 run-backend-poetry-app.sh 的 PowerShell 实现。
  会自动构建前端，然后启动 Flask 后端。

.PARAMETER Mode
  1 = real（钉钉登录，默认），2 = mock（账号密码登录）
.EXAMPLE
  .\run-backend-poetry-app.ps1          # 默认 mode=1 (real)
  .\run-backend-poetry-app.ps1 2        # mode=2 (mock)
  .\run-backend-poetry-app.ps1 mode=1   # 显式指定
#>

param(
  [string]$Mode = "mode=1"
)

$Script:ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script:BackendDir = Join-Path $ScriptDir "backend"
$Script:FrontendDir = Join-Path $ScriptDir "frontend-react"

$Script:AppHost = if ($env:APP_HOST) { $env:APP_HOST } else { "0.0.0.0" }
$Script:AppPort = if ($env:APP_PORT) { $env:APP_PORT } else { "5001" }

# 确保 Python 和 Poetry 在 PATH 中（避免 Windows 别名干扰）
$pyDir = "C:\Users\Admin\AppData\Local\Programs\Python\Python312"
$scriptsDir = "$pyDir\Scripts"
$env:Path = "$pyDir;$scriptsDir;$env:Path"

# 解析 mode 参数
$modeValue = ""
if ($Mode -match "^mode=(.+)$") {
  $modeValue = $Matches[1]
} else {
  $modeValue = $Mode
}

switch ($modeValue) {
  "1" { $Script:FrontendApiMode = "real" }
  "2" { $Script:FrontendApiMode = "mock" }
  default {
    Write-Host "[tb_tool_bt] ERROR: invalid mode: $Mode" -ForegroundColor Red
    Write-Host "[tb_tool_bt] Usage: .\run-backend-poetry-app.ps1 [mode=1|mode=2]" -ForegroundColor Yellow
    Write-Host "[tb_tool_bt]   mode=1 => real (DingTalk login)" -ForegroundColor Yellow
    Write-Host "[tb_tool_bt]   mode=2 => mock (account/password login)" -ForegroundColor Yellow
    exit 1
  }
}

# 检查 npm
$npmPath = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmPath) {
  Write-Host "[tb_tool_bt] ERROR: npm not found" -ForegroundColor Red
  Write-Host "[tb_tool_bt] Please install Node.js and npm first." -ForegroundColor Yellow
  exit 1
}

# 检查前端目录
if (-not (Test-Path $FrontendDir)) {
  Write-Host "[tb_tool_bt] ERROR: frontend directory not found: $FrontendDir" -ForegroundColor Red
  exit 1
}

# 构建前端
Push-Location $FrontendDir
try {
  $vitePath = Join-Path (Join-Path "node_modules" ".bin") "vite"
  if (-not (Test-Path "node_modules") -or -not (Test-Path $vitePath)) {
    Write-Host "[tb_tool_bt] frontend dependencies missing/incomplete, running install"
    if (Test-Path "package-lock.json") {
      npm ci
    } else {
      npm install
    }
  }

  Write-Host "[tb_tool_bt] Building frontend mode=${modeValue} (VITE_API_MODE=${Script:FrontendApiMode})"
  $env:VITE_API_MODE = $Script:FrontendApiMode
  npm run build
} finally {
  Pop-Location
}

# 进入后端目录
Push-Location $BackendDir
try {
  # 如果 .env 不存在，从 .env.example 复制
  $envExamplePath = Join-Path $BackendDir ".env.example"
  $envPath = Join-Path $BackendDir ".env"
  if ((Test-Path $envExamplePath) -and -not (Test-Path $envPath)) {
    Copy-Item $envExamplePath $envPath
    Write-Host "[tb_tool_bt] Copied backend\.env.example -> backend\.env (please fill DingTalk keys if needed)." -ForegroundColor Yellow
  }

  # 检查 poetry
  $poetryPath = Get-Command poetry -ErrorAction SilentlyContinue
  if (-not $poetryPath) {
    Write-Host "[tb_tool_bt] ERROR: poetry not found" -ForegroundColor Red
    Write-Host "[tb_tool_bt] Please install Poetry, e.g.: (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python3 -" -ForegroundColor Yellow
    exit 1
  }

  # 设置环境变量
  $env:FLASK_RUN_HOST = $AppHost
  $env:FLASK_RUN_PORT = $AppPort
  if (-not $env:AI_TTYD_BASE_URL) { $env:AI_TTYD_BASE_URL = "http://127.0.0.1:{port}/" }
  if (-not $env:AI_TTYD_PORT_BASE) { $env:AI_TTYD_PORT_BASE = "8800" }
  if (-not $env:AI_TTYD_PORT_SPAN) { $env:AI_TTYD_PORT_SPAN = "400" }

  Write-Host "[tb_tool_bt] Starting backend: http://${AppHost}:${AppPort} (frontend mode=${modeValue})" -ForegroundColor Green
  Write-Host "[tb_tool_bt] AI ttyd base: ${env:AI_TTYD_BASE_URL} (base=${env:AI_TTYD_PORT_BASE}, span=${env:AI_TTYD_PORT_SPAN})"
  Write-Host "[tb_tool_bt] Press Ctrl+C to stop." -ForegroundColor Cyan

  poetry run python app.py
} finally {
  Pop-Location
}
