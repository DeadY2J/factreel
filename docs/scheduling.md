# Scheduling

## Windows (Task Scheduler)

Create `daily.bat` in your channel folder:

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
factreel run -q >> logs\scheduled.log 2>&1
```

Then, in PowerShell:

```powershell
schtasks /Create /TN "FactReel daily" /TR "C:\path\to\my-channel\daily.bat" /SC DAILY /ST 17:55
schtasks /Create /TN "FactReel voice check" /TR "factreel doctor --voices --log -c C:\path\to\my-channel" /SC HOURLY /MO 3
```

Tip: in the task properties tick "Run whether user is logged on or not" and "Wake the computer to run".

## Linux / macOS (cron)

```cron
55 17 * * *  cd /home/me/my-channel && factreel run -q >> logs/scheduled.log 2>&1
0 */3 * * *  factreel doctor --voices --log -c /home/me/my-channel
```

## GitHub Actions

You can render in the cloud with a scheduled workflow: install FFmpeg (`sudo apt-get install -y ffmpeg`),
`pip install "factreel[youtube]"`, store your keys as repository secrets and the YouTube token as a secret
file. Keep the channel repository **private**.
