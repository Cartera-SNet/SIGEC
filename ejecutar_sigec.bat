@echo off
title SIGEC - Sistema de Inventario y Gestion de Equipos de Computo
cd /d "%~dp0"

echo.
echo ============================================
echo   SIGEC - Iniciando sistema...
echo   Sistema de Inventario y Gestion de Equipos
echo ============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo Instala Python desde: https://www.python.org/downloads/
    echo Marca la opcion "Add Python to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)
echo [OK] Python detectado.

if not exist ".env" (
    echo [ERROR] Falta el archivo .env con la conexion a la base de datos.
    echo Copia .env.example como .env y completa DATABASE_URL.
    pause
    exit /b 1
)

echo Instalando dependencias (solo tarda la primera vez)...
python -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] No se pudieron instalar las dependencias.
    echo Intenta manualmente: python -m pip install -r requirements.txt
    pause
    exit /b 1
)
echo [OK] Dependencias listas.
echo.
echo ============================================
echo   SIGEC en: http://localhost:5000
echo   Usuario inicial: Admin
echo   Presiona CTRL+C para detener el servidor
echo ============================================
echo.

start "" cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:5000"
python app.py

pause
