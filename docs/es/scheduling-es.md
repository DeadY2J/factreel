# Programación

## Windows (Programador de tareas)

Cree `daily.bat` en la carpeta de su canal:

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
factreel run -q >> logs\scheduled.log 2>&1
```

Luego, en PowerShell:

```powershell
schtasks /Create /TN "FactReel daily" /TR "C:\ruta\hacia\mi-canal\daily.bat" /SC DAILY /ST 17:55
schtasks /Create /TN "FactReel voice check" /TR "factreel doctor --voices --log -c C:\ruta\hacia\mi-canal" /SC HOURLY /MO 3
```

Consejo: en las propiedades de la tarea marque "Ejecutar tanto si el usuario ha iniciado sesión como si no" (Run whether user is logged on or not) y "Activar el equipo para ejecutar la tarea" (Wake the computer to run).

## Linux / macOS (cron)

```cron
55 17 * * *  cd /home/yo/mi-canal && factreel run -q >> logs/scheduled.log 2>&1
0 */3 * * *  factreel doctor --voices --log -c /home/yo/mi-canal
```

## GitHub Actions

Puede renderizar en la nube con un flujo de trabajo programado (scheduled workflow): instale FFmpeg (`sudo apt-get install -y ffmpeg`),
`pip install "factreel[youtube]"`, almacene sus claves como secretos del repositorio y el token de YouTube como un archivo secreto. Mantenga el repositorio del canal **privado**.