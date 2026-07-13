$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port = 8000
$AppUrl = "http://127.0.0.1:$Port/"
$TrackerScript = Join-Path $ProjectRoot "activity_tracker.py"

function Test-Port {
    param([Parameter(Mandatory = $true)][int] $Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(300)) { return $false }
        $client.EndConnect($async)
        return $true
    }
    catch { return $false }
    finally { $client.Close() }
}

function Start-ActivityTracker {
    if (-not (Test-Path $TrackerScript)) { return }
    $running = Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*$TrackerScript*" }
    if ($running) { return }

    $pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
    $python = if ($pythonCmd) { $pythonCmd.Source } else { $null }
    if (-not $python) { return }

    $outLog = Join-Path $ProjectRoot "activity_tracker.log"
    $errLog = Join-Path $ProjectRoot "activity_tracker_err.log"
    Start-Process -FilePath $python `
        -ArgumentList "`"$TrackerScript`"" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog
}

Start-ActivityTracker

if (Test-Port -Port $Port) {
    Start-Process $AppUrl
    exit 0
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/d /s /c `"chcp 65001 > nul && cd /d `"`"$ProjectRoot`"`" && uvicorn main:app --host 127.0.0.1 --port $Port --reload`""
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$psi.CreateNoWindow = $true
[System.Diagnostics.Process]::Start($psi) | Out-Null

$deadline = (Get-Date).AddSeconds(20)
do {
    if (Test-Port -Port $Port) { break }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

if (-not (Test-Port -Port $Port)) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "AI 日记本服务未能正常启动，请检查 $ProjectRoot 下的环境。",
        "启动失败",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

Start-Process $AppUrl
