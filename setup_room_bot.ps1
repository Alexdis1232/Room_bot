# =====================================================================
#  Setup + first run + Task Scheduler registration for room_bot
#  Run from PowerShell inside C:\Users\Alex\Downloads\room_bot
# =====================================================================

$ErrorActionPreference = "Stop"
$BotDir   = "C:\Users\Alex\Downloads\room_bot"
$TaskName = "RoomBot"
$ListenerTaskName = "RoomBotListener"

# Токен и chat_id больше не хранятся в этом файле — раньше тут был реальный
# токен бота прямым текстом, что небезопасно, если этот файл когда-нибудь
# попадёт в git/облако/резервную копию. Если TG_BOT_TOKEN/TG_MY_CHAT_ID уже
# сохранены через setx в прошлый запуск — они подхватятся сами, иначе
# скрипт спросит их один раз.
$BotToken = $env:TG_BOT_TOKEN
$ChatId   = $env:TG_MY_CHAT_ID
if (-not $BotToken) { $BotToken = Read-Host "Токен бота от @BotFather" }
if (-not $ChatId)   { $ChatId   = Read-Host "Твой chat_id (см. @userinfobot)" }

function Fail($msg) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    Write-Host "Copy this message and send it back so we can fix it." -ForegroundColor Yellow
    exit 1
}

# --- 0. Check folder and files ---
if (-not (Test-Path $BotDir)) { Fail "Folder $BotDir not found." }
Set-Location $BotDir
if (-not (Test-Path ".\room_bot.py"))      { Fail "room_bot.py not found in $BotDir." }
if (-not (Test-Path ".\requirements.txt")) { Fail "requirements.txt not found in $BotDir." }

# --- 1. Check Python ---
Write-Host "== 1. Checking Python ==" -ForegroundColor Cyan
try {
    $pyVersion = python --version 2>&1
    Write-Host "Found: $pyVersion"
} catch {
    Fail "Python not found in PATH. Install Python from python.org (check 'Add python.exe to PATH' during install) and re-run this script."
}

# --- 2. Install dependencies ---
Write-Host "== 2. Installing dependencies (pip install -r requirements.txt) ==" -ForegroundColor Cyan
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "pip install failed (exit code $LASTEXITCODE). See output above." }

# --- 3. Environment variables (persistent, via setx) ---
Write-Host "== 3. Saving environment variables (setx) ==" -ForegroundColor Cyan
setx TG_BOT_TOKEN $BotToken | Out-Null
setx TG_MY_CHAT_ID $ChatId | Out-Null
# setx does not affect the already-open session, so set them here too
# so the test run below works immediately
$env:TG_BOT_TOKEN  = $BotToken
$env:TG_MY_CHAT_ID = $ChatId
Write-Host "TG_BOT_TOKEN and TG_MY_CHAT_ID saved system-wide."

# --- 4. Test run ---
Write-Host "== 4. Test run: room_bot.py ==" -ForegroundColor Cyan
python room_bot.py
if ($LASTEXITCODE -ne 0) { Fail "room_bot.py exited with an error (code $LASTEXITCODE). Check the output above -- token, chat id, internet connection." }
Write-Host "Script ran without errors. Check Telegram -- you should have received a message from the bot." -ForegroundColor Green

# --- 5. Task Scheduler: run every 15 minutes, around the clock ---
Write-Host "== 5. Setting up Task Scheduler ==" -ForegroundColor Cyan
try {
    $pythonExe = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonExe) { $pythonExe = (Get-Command python.exe).Source }

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $action   = New-ScheduledTaskAction -Execute $pythonExe -Argument "room_bot.py" -WorkingDirectory $BotDir
    $trigger  = New-ScheduledTaskTrigger -Once -At (Get-Date) `
                    -RepetitionInterval (New-TimeSpan -Minutes 15) `
                    -RepetitionDuration (New-TimeSpan -Days 3650)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                    -StartWhenAvailable -MultipleInstances IgnoreNew

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
        -Description "room_bot: checks channels every 15 minutes" | Out-Null

    Write-Host "Task '$TaskName' created: runs every 15 minutes, working directory $BotDir." -ForegroundColor Green
    Write-Host "The task runs under your user account and requires you to be logged in to Windows (screen can be locked)." -ForegroundColor Yellow
} catch {
    Fail "Could not create the Task Scheduler task: $($_.Exception.Message)`nTry running PowerShell as Administrator and re-run this script."
}

# --- 6. Task Scheduler: continuous command/button listener (room_bot.py --listen) ---
# Without this task, /price, /metro, the inline filters menu etc. only work
# while someone happens to be running "python room_bot.py --listen" manually
# in an open terminal window.
Write-Host "== 6. Setting up Task Scheduler (command listener) ==" -ForegroundColor Cyan
try {
    Unregister-ScheduledTask -TaskName $ListenerTaskName -Confirm:$false -ErrorAction SilentlyContinue

    $listenerAction   = New-ScheduledTaskAction -Execute $pythonExe -Argument "room_bot.py --listen" -WorkingDirectory $BotDir
    $listenerTrigger  = New-ScheduledTaskTrigger -AtLogOn
    $listenerSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                    -StartWhenAvailable -MultipleInstances IgnoreNew `
                    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

    Register-ScheduledTask -TaskName $ListenerTaskName -Action $listenerAction -Trigger $listenerTrigger -Settings $listenerSettings `
        -Description "room_bot: continuous command/button listener (--listen)" | Out-Null

    Write-Host "Task '$ListenerTaskName' created: starts at logon, restarts itself if it ever exits." -ForegroundColor Green
    Start-ScheduledTask -TaskName $ListenerTaskName
    Write-Host "Started it now, so commands/buttons work immediately without waiting for next logon." -ForegroundColor Green
} catch {
    Fail "Could not create the listener Scheduled Task: $($_.Exception.Message)`nTry running PowerShell as Administrator and re-run this script."
}

Write-Host ""
Write-Host "DONE. All steps completed." -ForegroundColor Green
