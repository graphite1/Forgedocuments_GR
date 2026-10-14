@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "AC_BOOT_FILE=%~f0"
set "AC_APP_ARGS=%*"
powershell.exe -NoProfile -Command "$t=[IO.File]::ReadAllText($env:AC_BOOT_FILE);$m='#==POWERSHELL_START==';$s=$t.Substring($t.LastIndexOf($m)+$m.Length);& ([scriptblock]::Create($s))"
set "AC_EXIT=%errorlevel%"
if not "%AC_EXIT%"=="0" pause
exit /b %AC_EXIT%
#==POWERSHELL_START==
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$baseDir = Split-Path -LiteralPath $env:AC_BOOT_FILE
$env:PYTHONUTF8 = '1'

function Find-UsablePython {
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($cmdName in @('python.exe','python3.exe')) {
        $cmd = Get-Command $cmdName -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notmatch '\\WindowsApps\\') { $candidates.Add($cmd.Source) }
    }
    foreach ($registryRoot in @('HKCU:\Software\Python\PythonCore','HKLM:\Software\Python\PythonCore','HKLM:\Software\WOW6432Node\Python\PythonCore')) {
        if (Test-Path -LiteralPath $registryRoot) {
            foreach ($version in Get-ChildItem -LiteralPath $registryRoot) {
                $installKey = Join-Path $version.PSPath 'InstallPath'
                if (Test-Path -LiteralPath $installKey) {
                    $key = Get-Item -LiteralPath $installKey
                    $exe = $key.GetValue('ExecutablePath')
                    if ($exe) { $candidates.Add([string]$exe) }
                    $prefix = $key.GetValue('')
                    if ($prefix) { $candidates.Add((Join-Path $prefix 'python.exe')) }
                }
            }
        }
    }
    foreach ($pattern in @("$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:LOCALAPPDATA\Python\pythoncore-*\python.exe", "$env:LOCALAPPDATA\Programs\AcToyoakePython3143\python.exe")) {
        foreach ($item in Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue) { $candidates.Add($item.FullName) }
    }
    foreach ($exe in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { continue }
        try {
            & $exe -c 'import sys,tkinter,venv,ensurepip;assert (3,11)<=sys.version_info[:2]<(3,15);assert sys.maxsize>2**32' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $exe }
        } catch { }
    }
    return $null
}

try {
    if (-not (Test-Path -LiteralPath (Join-Path $baseDir 'app.py'))) { throw 'Place this file in the same folder as app.py, then run it again.' }
    if (-not (Test-Path -LiteralPath (Join-Path $baseDir 'bootstrap.py'))) { throw 'bootstrap.py is missing. Extract the full app ZIP first.' }
    $appPython = Join-Path $baseDir '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $appPython)) {
        Write-Host '[1/3] Checking Python...'
        $pythonExe = Find-UsablePython
        if (-not $pythonExe) {
            if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows 10/11 is required.' }
            Write-Host 'Downloading Python 3.14.3 from python.org (about 29 MB)...'
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $cacheDir = Join-Path $env:TEMP ('AcToyoakeSetup_' + [Guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $cacheDir | Out-Null
            $installer = Join-Path $cacheDir 'python-3.14.3-amd64.exe'
            try {
                Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.14.3/python-3.14.3-amd64.exe' -OutFile $installer
                $signature = Get-AuthenticodeSignature -LiteralPath $installer
                if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'The Python installer signature could not be verified. Installation stopped.' }
                Write-Host 'Installing Python for the current Windows user...'
                $targetDir = Join-Path $env:LOCALAPPDATA 'Programs\AcToyoakePython3143'
                $installLog = Join-Path $baseDir 'python_install.log'
                $arguments = @('/passive','/norestart','InstallAllUsers=0','Include_launcher=0','PrependPath=0','Include_tcltk=1','Include_pip=1','Include_test=0','Shortcuts=0',('TargetDir="' + $targetDir + '"'),'/log',('"' + $installLog + '"'))
                $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
                if ($process.ExitCode -notin @(0,3010)) { throw "Python installation failed (exit $($process.ExitCode)). See python_install.log." }
                $pythonExe = Join-Path $targetDir 'python.exe'
                if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = Find-UsablePython }
                if (-not $pythonExe) { throw 'Python was not found after installation. Restart Windows and try again.' }
            } finally {
                if (Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer -Force }
                if ((Test-Path -LiteralPath $cacheDir) -and -not (Get-ChildItem -LiteralPath $cacheDir)) { Remove-Item -LiteralPath $cacheDir }
            }
        } else { Write-Host "Using installed Python: $pythonExe" }
        Write-Host '[2/3] Setting up app dependencies...'
        & $pythonExe (Join-Path $baseDir 'bootstrap.py')
        if ($LASTEXITCODE -ne 0) { throw 'App setup failed. Check the message above and your internet connection.' }
    }
    else {
        Write-Host 'Checking app dependencies...'
        & $appPython (Join-Path $baseDir 'bootstrap.py')
        if ($LASTEXITCODE -ne 0) { throw 'App dependency setup failed.' }
    }
    Write-Host '[3/3] Starting the app...'
    if ($env:AC_APP_ARGS -eq '--smoke-test') { & $appPython (Join-Path $baseDir 'app.py') '--smoke-test' }
    else { & $appPython (Join-Path $baseDir 'app.py') }
    if ($LASTEXITCODE -ne 0) { throw 'The app reported an error. Check the message above.' }
    exit 0
} catch {
    Write-Host ('Failed: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
