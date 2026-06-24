@echo off
echo Eliminando .env del historial de git...
git rm --cached .env
git add .gitignore
git commit -m "fix: remove .env from tracking, add gitignore"
echo.
echo Subiendo a GitHub...
git push -u origin main
echo.
echo LISTO.
pause
