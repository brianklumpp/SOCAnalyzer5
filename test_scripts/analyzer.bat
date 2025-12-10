@echo off
REM Windows batch wrapper for analyzer.py
REM Usage: analyzer start|stop|restart
python "%~dp0analyzer.py" %*
