@echo off
:: Thin wrapper — forwards all arguments to setup.ps1
:: Usage: setup.bat [same flags as setup.ps1]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
