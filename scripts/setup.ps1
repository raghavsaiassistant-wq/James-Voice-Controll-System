<#
  Voice Mode setup for Windows 10/11.

  Checks every dependency, installs only what is missing, downloads the offline models and
  runs a self-check. Safe to run again at any time: finished steps are skipped.

    setup.bat               normal install (CPU, ~4 GB disk)
    setup.bat -NoLaya       skip the Laya model (rules only, less RAM)
    setup.bat -Gpu          CUDA build of PyTorch (NVIDIA GPU)
    setup.bat -NoShortcut   don't create the desktop shortcut

  After this, everything runs offline.
#>
param(
    [switch]$NoLaya,
    [switch]$Gpu,
    [switch]$NoShortcut
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'      # Invoke-WebRequest is 10x slower with the progress bar
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$Venv = Join-Path $Root '.venv'
$VPy = Join-Path $Venv 'Scripts\python.exe'
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'logs') | Out-Null
try { Start-Transcript -Path (Join-Path $Root 'logs\setup.log') -Append | Out-Null } catch {}

function Step([string]$msg) { Write-Host ''; Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok([string]$msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Info([string]$msg) { Write-Host "  ...  $msg" }
function Warn([string]$msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Die([string]$msg) {
    Write-Host ''
    Write-Host "  [X]  $msg" -ForegroundColor Red
    Write-Host ''
    Write-Host 'Setup ruk gaya. Upar ka error dekho, fix karke setup.bat dobara chalao (jo ho chuka hai wo skip hoga).'
    Write-Host 'Poora log: logs\setup.log'
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}

# ---------------------------------------------------------------- helpers

function Get-PyVersion([string]$exe, [string[]]$pre) {
    # Returns a [version] for a working 64-bit Python 3.10-3.13, else $null.
    $out = $null
    try {
        $out = & $exe @pre -c "import sys; print('%d.%d' % sys.version_info[:2]); print(sys.maxsize > 2**32)" 2>$null
    } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    $lines = @($out)
    if ($lines.Count -lt 2 -or "$($lines[1])".Trim() -ne 'True') { return $null }
    try { $v = [version]("$($lines[0])".Trim()) } catch { return $null }
    if ($v.Major -eq 3 -and $v.Minor -ge 10 -and $v.Minor -le 13) { return $v }
    return $null
}

function Find-Python {
    $cands = New-Object System.Collections.ArrayList
    foreach ($m in @('3.12', '3.11', '3.13', '3.10')) { [void]$cands.Add(@('py', @("-$m"))) }
    [void]$cands.Add(@('python', @()))
    [void]$cands.Add(@('python3', @()))
    foreach ($d in @('Python312', 'Python311', 'Python313', 'Python310')) {
        [void]$cands.Add(@((Join-Path $env:LOCALAPPDATA "Programs\Python\$d\python.exe"), @()))
        [void]$cands.Add(@((Join-Path $env:ProgramFiles "$d\python.exe"), @()))
    }
    foreach ($c in $cands) {
        $exe = [string]$c[0]
        $pre = [string[]]@($c[1])
        if ($exe.Contains('\')) {
            if (-not (Test-Path -LiteralPath $exe)) { continue }
        } elseif (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $v = Get-PyVersion $exe $pre
        if ($v) { return @{ Exe = $exe; Pre = $pre; Version = $v } }
    }
    return $null
}

function Install-Python {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info 'winget se Python 3.12 install ho raha hai...'
        winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
        $py = Find-Python
        if ($py) { return $py }
        Warn 'winget se nahi hua, python.org se try kar raha hoon'
    }
    $url = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
    $exe = Join-Path $env:TEMP 'python-3.12.10-amd64.exe'
    Info "Download: $url"
    try { Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing } catch { Die "Python download failed: $($_.Exception.Message)" }
    Info 'Python install ho raha hai (1-2 minute)...'
    $p = Start-Process -FilePath $exe -Wait -PassThru -ArgumentList @(
        '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1', 'Include_test=0', 'Include_tcltk=1')
    if ($p.ExitCode -ne 0) { Die "Python installer failed (exit $($p.ExitCode))" }
    return Find-Python
}

function Test-VCRedist {
    $sys = Join-Path $env:SystemRoot 'System32'
    return (Test-Path (Join-Path $sys 'msvcp140.dll')) -and (Test-Path (Join-Path $sys 'vcruntime140_1.dll'))
}

function Install-VCRedist {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info 'winget se Microsoft Visual C++ Runtime install ho raha hai (admin permission maang sakta hai)...'
        winget install -e --id Microsoft.VCRedist.2015+.x64 --silent --accept-package-agreements --accept-source-agreements | Out-Host
        if (Test-VCRedist) { return $true }
    }
    $url = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'
    $exe = Join-Path $env:TEMP 'vc_redist.x64.exe'
    Info "Download: $url"
    try { Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing } catch { return $false }
    Info 'Install ho raha hai (Windows admin permission ka popup aayega - Yes dabao)...'
    try {
        $p = Start-Process -FilePath $exe -ArgumentList '/install', '/quiet', '/norestart' -Verb RunAs -Wait -PassThru
        if (@(0, 1638, 3010) -notcontains $p.ExitCode) { Warn "VC++ installer exit code $($p.ExitCode)" }
    } catch { return $false }
    return (Test-VCRedist)
}

function Test-Import([string]$module) {
    & $VPy -c "import $module" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Run-Checked([string]$what, [string[]]$argv) {
    & $VPy @argv
    if ($LASTEXITCODE -ne 0) { Die "$what failed (exit $LASTEXITCODE)" }
}

# ---------------------------------------------------------------- 1. system

Write-Host ''
Write-Host 'Voice Mode setup' -ForegroundColor White
Write-Host "Folder: $Root"

Step '1/7  Windows check'
if (-not [Environment]::Is64BitOperatingSystem) { Die '64-bit Windows chahiye.' }
$os = [Environment]::OSVersion.Version
if ($os.Major -lt 10) { Die "Windows 10 ya 11 chahiye (mila: $os)." }
Ok "Windows $($os.Major) (build $($os.Build)), 64-bit"
try {
    $drive = (Get-Item -LiteralPath $Root).PSDrive
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    if ($freeGB -lt 5) { Warn "Disk pe sirf $freeGB GB free hai; ~5 GB chahiye." } else { Ok "Disk space: $freeGB GB free" }
} catch {}
try {
    $ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    if ($ramGB -lt 7.5) { Warn "RAM $ramGB GB hai. 8 GB se kam pe Laya band rakho: setup.bat -NoLaya" } else { Ok "RAM: $ramGB GB" }
} catch {}

# ---------------------------------------------------------------- 2. python

Step '2/7  Python (3.10 - 3.13, 64-bit)'
$py = Find-Python
if ($py) {
    Ok "Python $($py.Version) mil gaya: $($py.Exe) $($py.Pre -join ' ')"
} else {
    Warn 'Sahi Python nahi mila, install kar raha hoon'
    $py = Install-Python
    if (-not $py) { Die 'Python install ke baad bhi nahi mila. Computer restart karke setup.bat dobara chalao.' }
    Ok "Python $($py.Version) install ho gaya"
}

Step '3/7  Microsoft Visual C++ Runtime (PyTorch ke liye)'
if (Test-VCRedist) { Ok 'Already installed' }
elseif (Install-VCRedist) { Ok 'Install ho gaya' }
else { Warn 'Install nahi ho paya. Agar baad me "DLL load failed" aaye to https://aka.ms/vs/17/release/vc_redist.x64.exe install karo.' }

# ---------------------------------------------------------------- 3. venv + packages

Step '4/7  Python environment (.venv) aur packages'
if (Test-Path -LiteralPath $VPy) {
    if (Get-PyVersion $VPy @()) { Ok '.venv already hai' }
    else {
        Warn '.venv kharab hai, dobara bana raha hoon'
        Remove-Item -Recurse -Force -LiteralPath $Venv
    }
}
if (-not (Test-Path -LiteralPath $VPy)) {
    Info '.venv bana raha hoon...'
    & $py.Exe @($py.Pre) -m venv $Venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VPy)) { Die 'python -m venv failed' }
    Ok '.venv ban gaya'
}
Run-Checked 'pip upgrade' @('-m', 'pip', 'install', '--upgrade', 'pip', '--disable-pip-version-check', '-q')

if (Test-Import 'torch') {
    Ok 'PyTorch already installed'
} else {
    $index = 'https://download.pytorch.org/whl/cpu'
    if ($Gpu) { $index = 'https://download.pytorch.org/whl/cu128' }
    Info "PyTorch install ho raha hai ($index) - ye sabse bada download hai, thoda time lagega..."
    Run-Checked 'PyTorch install' @('-m', 'pip', 'install', 'torch', '--index-url', $index, '--disable-pip-version-check')
    Ok 'PyTorch install ho gaya'
}

Info 'Baaki packages check/install ho rahe hain (jo already hain wo skip)...'
Run-Checked 'package install' @('-m', 'pip', 'install', '-r', (Join-Path $Root 'requirements.txt'), '--disable-pip-version-check')
$missing = @()
foreach ($m in @('torch', 'transformers', 'laya', 'sounddevice', 'pynput', 'rapidfuzz', 'playwright', 'pycaw', 'tkinter')) {
    if (-not (Test-Import $m)) { $missing += $m }
}
if ($missing.Count -gt 0) {
    if ($missing -contains 'tkinter') { Warn 'tkinter nahi hai: screen wala status bar nahi dikhega (baaki sab chalega).' }
    $hard = @($missing | Where-Object { $_ -ne 'tkinter' })
    if ($hard.Count -gt 0) { Die "Ye packages import nahi ho rahe: $($hard -join ', ')" }
}
Ok 'Saare packages ready'

# ---------------------------------------------------------------- 4. browser

Step '5/7  Browser (Chromium for Playwright)'
Run-Checked 'Chromium install' @('-m', 'playwright', 'install', 'chromium')
Ok 'Chromium ready'

# ---------------------------------------------------------------- 5. models

Step '6/7  Offline models (speech + Laya)'
$margs = @('-m', 'voicemode.setup_models')
if ($NoLaya) { $margs += '--no-laya' }
Run-Checked 'model download' $margs
if ($NoLaya) {
    & $VPy -c "import json,pathlib; p=pathlib.Path('settings.json'); d=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}; d['use_laya']=False; p.write_text(json.dumps(d, indent=2), encoding='utf-8')"
    Ok 'settings.json: use_laya = false'
}

# ---------------------------------------------------------------- 6. check + shortcut

Step '7/7  Self-check (offline)'
& $VPy -m voicemode --check
$checkOk = ($LASTEXITCODE -eq 0)

if (-not $NoShortcut) {
    try {
        $desk = [Environment]::GetFolderPath('Desktop')
        $lnk = Join-Path $desk 'Voice Mode.lnk'
        $sh = New-Object -ComObject WScript.Shell
        $s = $sh.CreateShortcut($lnk)
        $s.TargetPath = Join-Path $Root 'run.bat'
        $s.WorkingDirectory = $Root
        $s.IconLocation = (Join-Path $env:SystemRoot 'System32\SndVol.exe') + ',0'
        $s.Description = 'Voice Mode - hold Right Alt and speak'
        $s.Save()
        Ok "Desktop shortcut: $lnk"
    } catch { Warn "Shortcut nahi bana: $($_.Exception.Message)" }
}

Write-Host ''
if ($checkOk) {
    Write-Host 'Setup complete!' -ForegroundColor Green
} else {
    Write-Host 'Setup complete, lekin self-check me kuch warnings hain (upar dekho).' -ForegroundColor Yellow
}
Write-Host ''
Write-Host '  Start:   run.bat  (ya Desktop pe "Voice Mode")'
Write-Host '  Use:     Right Alt dabake rakho, bolo, chhod do'
Write-Host '  Test mic: run.bat --mic-test'
Write-Host ''
try { Stop-Transcript | Out-Null } catch {}
if ($checkOk) { exit 0 } else { exit 2 }
