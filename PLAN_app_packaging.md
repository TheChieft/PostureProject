# Plan: PostureProject → App Windows instalable

## Objetivo

Convertir PostureProject de un script Python ejecutado desde PowerShell a una
aplicación Windows de uso diario: doble clic para abrir, arranca con el sistema,
sin necesidad de tener Python instalado.

---

## Fase 1 — Ejecutable standalone (.exe) con PyInstaller

**Meta:** `PostureProject.exe` que funcione en cualquier PC Windows sin Python.

### Pasos

1. Instalar PyInstaller en Python 3.11 x64:
   ```powershell
   py -3.11-64 -m pip install pyinstaller
   ```

2. Adaptar los paths internos para modo "frozen" (PyInstaller extrae archivos
   a un directorio temporal `sys._MEIPASS` en runtime):
   - `pose.py`: el path del modelo `.task` debe usar `sys._MEIPASS` si está frozen
   - `logger.py`: el directorio `logs/` debe resolverse relativo al ejecutable,
     no al `.py`

3. Crear el spec file `PostureProject.spec` con:
   - `--onedir` (recomendado sobre `--onefile` por rendimiento de MediaPipe)
   - `--windowed` para ocultar la consola
   - `--add-data "pose_landmarker_lite.task;."` para incluir el modelo
   - Hooks para mediapipe (tiene imports dinámicos que PyInstaller no detecta solo)

4. Build y prueba:
   ```powershell
   py -3.11-64 -m PyInstaller PostureProject.spec
   # Resultado en dist/PostureProject/PostureProject.exe
   ```

### Riesgos conocidos
- MediaPipe usa `importlib` dinámico → puede requerir `--collect-all mediapipe`
- El modelo `.task` debe estar en el bundle correctamente
- El overlay de tkinter puede necesitar ajustes de DPI en Windows 11

---

## Fase 2 — Autostart con Windows

**Meta:** La app arranca automáticamente al iniciar sesión, sin intervención del usuario.

### Opción A — Carpeta Startup (más simple)
Agregar un shortcut `.lnk` a:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```

### Opción B — Registro de Windows (más limpio)
```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
"PostureProject" = "C:\Program Files\PostureProject\PostureProject.exe"
```

### Opción C — Task Scheduler (más control)
- Trigger: "At log on"
- Action: ejecutar `PostureProject.exe`
- Permite configurar delay, prioridad, condiciones de red/batería

El instalador (Fase 3) puede automatizar cualquiera de estas opciones.

---

## Fase 3 — Instalador .exe con Inno Setup

**Meta:** Un instalador `PostureProject_Setup.exe` con wizard estándar de Windows.

### Qué incluye
- Wizard de instalación con destino configurable
- Shortcut en escritorio y/o menú de inicio
- Checkbox "Iniciar con Windows" (implementa Fase 2 automáticamente)
- Uninstaller registrado en "Agregar o quitar programas"

### Herramienta
Inno Setup (gratuito, open source): https://jrsoftware.org/isinfo.php

Se escribe un archivo `.iss` (script de Inno Setup) que describe el instalador.
El resultado es un único `PostureProject_Setup.exe` distribuible.

---

## Fase 4 — System tray icon (mejora UX, opcional)

**Meta:** Reemplazar o complementar la barra overlay con un ícono en el system tray.

### Librería recomendada
`pystray` — puro Python, sin dependencias nativas pesadas.

### Funcionalidades
- Ícono en el tray que cambia de color según estado (GREEN/YELLOW/RED)
- Right-click menu:
  - Recalibrar
  - Pausar monitoreo
  - Abrir logs
  - Salir
- Notificaciones nativas de Windows (`plyer` o `win10toast`) como alternativa
  o complemento al beep de audio

---

## Orden de ejecución recomendado

| Fase | Prioridad | Complejidad | Valor |
|------|-----------|-------------|-------|
| 1 — .exe standalone | Alta | Media | Elimina dependencia de Python |
| 2 — Autostart | Alta | Baja | Uso diario sin friction |
| 3 — Instalador | Media | Media | Distribuible a otros |
| 4 — System tray | Baja | Media | Mejor UX |

Empezar por Fase 1 + 2. Las fases 3 y 4 son mejoras de pulido.

---

## Estado

- [ ] Fase 1: Ejecutable standalone
- [ ] Fase 2: Autostart
- [ ] Fase 3: Instalador
- [ ] Fase 4: System tray
