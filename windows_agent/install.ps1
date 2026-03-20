# koclaw Windows Agent installer
# Run: powershell -ExecutionPolicy Bypass -File install.ps1
# Works from any location including \\wsl.localhost\... paths.

$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  koclaw Windows Agent Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Install dir is always on the Windows native filesystem so that
# the .venv runs fast regardless of where this script is located
# (e.g. \\wsl.localhost\... share).
$InstallDir   = Join-Path $env:USERPROFILE "koclaw-agent"
$ServerScript = Join-Path $PSScriptRoot "server.py"   # may be a WSL UNC path — that is intentional

Write-Host "      Install dir : $InstallDir" -ForegroundColor DarkGray
Write-Host "      server.py   : $ServerScript" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}

# ── [1/5] Find Python ────────────────────────────────────

Write-Host "[1/5] Checking Python..." -ForegroundColor Yellow

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

# ── [2/5] Create virtualenv ──────────────────────────────

Write-Host "[2/5] Creating virtual environment..." -ForegroundColor Yellow

$venvDir = Join-Path $InstallDir ".venv"

if (Test-Path $venvDir) {
    Write-Host "      Existing .venv found — reusing" -ForegroundColor DarkGray
} else {
    & $python -m venv $venvDir
    Write-Host "      Created: $venvDir" -ForegroundColor Green
}

$pip       = Join-Path $venvDir "Scripts\pip.exe"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"

# ── [3/5] Install packages ───────────────────────────────

Write-Host "[3/5] Installing packages..." -ForegroundColor Yellow

$packages = @(
    "fastapi>=0.110.0",
    "uvicorn>=0.29.0",
    "pyautogui>=0.9.54",
    "pyperclip>=1.8.2",
    "pillow>=10.0.0",
    "pydantic>=2.0.0",
    "playwright>=1.40.0"
)

foreach ($pkg in $packages) {
    Write-Host "      $pkg" -ForegroundColor DarkGray
    & $pip install $pkg --quiet
}

Write-Host "      Packages installed" -ForegroundColor Green

# Playwright 브라우저 설치 (chromium)
Write-Host "      Installing Playwright Chromium browser..." -ForegroundColor DarkGray
$playwrightExe = Join-Path $venvDir "Scripts\playwright.exe"
& $playwrightExe install chromium | Out-Null
Write-Host "      Playwright Chromium installed" -ForegroundColor Green

# ── [4/5] Generate API key & .env ───────────────────────

Write-Host "[4/5] Generating API key..." -ForegroundColor Yellow

$envFile = Join-Path $InstallDir ".env"
$apiKey  = ""

if (Test-Path $envFile) {
    $existing = Get-Content $envFile | Where-Object { $_ -match "^WINDOWS_AGENT_API_KEY=" }
    if ($existing) {
        $apiKey = ($existing -split "=", 2)[1].Trim()
        Write-Host "      Existing API key found — reusing" -ForegroundColor DarkGray
    }
}

if (-not $apiKey) {
    $bytes  = New-Object byte[] 16
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $apiKey = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
    Add-Content -Path $envFile -Value "WINDOWS_AGENT_API_KEY=$apiKey" -Encoding UTF8
    Write-Host "      API key generated and saved to .env" -ForegroundColor Green
}

Write-Host "      API Key: $apiKey" -ForegroundColor Cyan

# ── [5/5] Create start script ────────────────────────────

Write-Host "[5/5] Creating start.ps1..." -ForegroundColor Yellow

$startScript = Join-Path $InstallDir "start.ps1"

# $ServerScript and $pythonExe are expanded at install time so start.ps1
# always knows where server.py lives (even if it's on a WSL UNC path).
$startContent = @"
# koclaw Windows Agent — auto-generated by install.ps1
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

`$pythonExe    = "$pythonExe"
`$serverScript  = "$ServerScript"
`$envFile       = "$envFile"

# Load .env
if (Test-Path `$envFile) {
    Get-Content `$envFile | ForEach-Object {
        if (`$_ -match "^([^#][^=]*)=(.*)$") {
            [System.Environment]::SetEnvironmentVariable(`$Matches[1].Trim(), `$Matches[2].Trim(), "Process")
        }
    }
}

Write-Host ""
Write-Host "koclaw Windows Agent starting..." -ForegroundColor Cyan
Write-Host "Port : 7777" -ForegroundColor Cyan
Write-Host "View : http://localhost:7777/view" -ForegroundColor Cyan
Write-Host "Stop : Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

& `$pythonExe `$serverScript
"@

Set-Content -Path $startScript -Value $startContent -Encoding UTF8
Write-Host "      start.ps1 created: $startScript" -ForegroundColor Green

# ── Autostart (optional) ─────────────────────────────────

Write-Host ""
$autoAnswer = Read-Host "Register autostart on Windows login? (y/N)"
if ($autoAnswer -match "^[yY]") {
    $taskName = "koclaw-windows-agent"
    $psExe    = "powershell.exe"
    $psArgs   = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScript`""
    $action   = New-ScheduledTaskAction -Execute $psExe -Argument $psArgs
    $trigger  = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -Force | Out-Null
        Write-Host "      Autostart registered: $taskName" -ForegroundColor Green
    } catch {
        Write-Host "      Autostart failed (try running as Administrator): $_" -ForegroundColor Red
    }

    # WSL koclaw 자동 시작
    $wslTask   = "koclaw-bot"
    $wslArgs   = "-e bash -lc 'cd ~/koclaw && ./start.sh >> ~/koclaw/koclaw.log 2>&1 &'"
    $wslAction = New-ScheduledTaskAction -Execute "wsl.exe" -Argument $wslArgs
    try {
        Unregister-ScheduledTask -TaskName $wslTask -Confirm:$false -ErrorAction SilentlyContinue
        Register-ScheduledTask -TaskName $wslTask -Action $wslAction -Trigger $trigger -Settings $settings -RunLevel Limited -Force | Out-Null
        Write-Host "      Autostart registered: $wslTask (WSL koclaw)" -ForegroundColor Green
    } catch {
        Write-Host "      WSL autostart failed: $_" -ForegroundColor Red
    }
}

# ── Done ─────────────────────────────────────────────────

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Start the agent:" -ForegroundColor White
Write-Host "     powershell -ExecutionPolicy Bypass -File `"$startScript`"" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2. Check Windows IP from WSL:" -ForegroundColor White
Write-Host "     ip route | grep default | awk '{print `$3}'" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3. Add to koclaw .env (WSL):" -ForegroundColor White
Write-Host "     WINDOWS_AGENT_URL=http://<IP>:7777" -ForegroundColor Cyan
Write-Host "     WINDOWS_AGENT_API_KEY=$apiKey" -ForegroundColor Cyan
Write-Host ""
Write-Host "  4. Watch screen in browser:" -ForegroundColor White
Write-Host "     http://localhost:7777/view" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To update server.py later, just re-run this install.ps1." -ForegroundColor DarkGray
Write-Host "  The .venv and API key will be reused automatically." -ForegroundColor DarkGray
Write-Host ""

$answer = Read-Host "Start the agent now? (y/N)"
if ($answer -match "^[yY]") {
    Write-Host ""
    & $pythonExe $ServerScript
}
