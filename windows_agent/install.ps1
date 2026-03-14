# koclaw Windows Agent installer
# Run: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  koclaw Windows Agent Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── [1/4] Find Python ────────────────────────────────────

Write-Host "[1/4] Checking Python..." -ForegroundColor Yellow

function Find-Python {
    # PATH 에서 확인
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 9) {
                return $cmd
            }
        } catch {}
    }
    # 직접 경로 확인 (PATH 미등록 시)
    $dirs = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312",
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python310",
        "C:\Python312", "C:\Python311", "C:\Python310",
        "C:\Program Files\Python312", "C:\Program Files\Python311"
    )
    foreach ($dir in $dirs) {
        $exe = Join-Path $dir "python.exe"
        if (Test-Path $exe) {
            $ver = & $exe --version 2>&1
            if ($ver -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 9) {
                return $exe
            }
        }
    }
    return $null
}

$python = Find-Python

if (-not $python) {
    Write-Host "      Python not found. Installing via winget..." -ForegroundColor Yellow

    $winget = $null
    try { $winget = Get-Command winget -ErrorAction Stop } catch {}

    if ($winget) {
        Write-Host "      Installing Python 3.12 (please wait)..." -ForegroundColor DarkGray
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $python = Find-Python
    }

    if (-not $python) {
        Write-Host ""
        Write-Host "[ERROR] Python installation failed." -ForegroundColor Red
        Write-Host "        Please install manually: https://www.python.org/downloads/" -ForegroundColor Cyan
        Write-Host "        (Check 'Add Python to PATH' during install)" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
}

Write-Host "      Python OK: $(& $python --version 2>&1)" -ForegroundColor Green

# ── [2/4] Create virtualenv ──────────────────────────────

Write-Host "[2/4] Creating virtual environment..." -ForegroundColor Yellow

$venvDir = Join-Path $PSScriptRoot ".venv"

if (Test-Path $venvDir) {
    Write-Host "      Existing .venv found — reusing" -ForegroundColor DarkGray
} else {
    & $python -m venv $venvDir
    Write-Host "      Created: $venvDir" -ForegroundColor Green
}

$pip       = Join-Path $venvDir "Scripts\pip.exe"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"

# ── [3/4] Install packages ───────────────────────────────

Write-Host "[3/4] Installing packages..." -ForegroundColor Yellow

$packages = @(
    "fastapi>=0.110.0",
    "uvicorn>=0.29.0",
    "pyautogui>=0.9.54",
    "pyperclip>=1.8.2",
    "pillow>=10.0.0",
    "pydantic>=2.0.0"
)

foreach ($pkg in $packages) {
    Write-Host "      $pkg" -ForegroundColor DarkGray
    & $pip install $pkg --quiet
}

Write-Host "      Packages installed" -ForegroundColor Green

# ── [4/4] Create start script ────────────────────────────

Write-Host "[4/4] Creating start.ps1..." -ForegroundColor Yellow

$startScript  = Join-Path $PSScriptRoot "start.ps1"
$serverScript = Join-Path $PSScriptRoot "server.py"

$startContent = @"
# koclaw Windows Agent
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

`$pythonExe   = Join-Path `$PSScriptRoot ".venv\Scripts\python.exe"
`$serverScript = Join-Path `$PSScriptRoot "server.py"

Write-Host ""
Write-Host "koclaw Windows Agent starting..." -ForegroundColor Cyan
Write-Host "Port : 7777" -ForegroundColor Cyan
Write-Host "View : http://localhost:7777/view" -ForegroundColor Cyan
Write-Host "Stop : Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

& `$pythonExe `$serverScript
"@

Set-Content -Path $startScript -Value $startContent -Encoding UTF8
Write-Host "      start.ps1 created" -ForegroundColor Green

# ── Done ─────────────────────────────────────────────────

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Start the agent:" -ForegroundColor White
Write-Host "     powershell -ExecutionPolicy Bypass -File start.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2. Check Windows IP from WSL:" -ForegroundColor White
Write-Host "     cat /etc/resolv.conf | grep nameserver" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3. Add to koclaw .env (WSL):" -ForegroundColor White
Write-Host "     WINDOWS_AGENT_URL=http://<IP from step 2>:7777" -ForegroundColor Cyan
Write-Host ""
Write-Host "  4. Watch screen in browser:" -ForegroundColor White
Write-Host "     http://localhost:7777/view" -ForegroundColor Cyan
Write-Host ""

$answer = Read-Host "Start the agent now? (y/N)"
if ($answer -match "^[yY]") {
    Write-Host ""
    & $pythonExe $serverScript
}
