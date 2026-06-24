@echo off
echo Subiendo codigo a GitHub...
git remote add origin https://github.com/mirko93-eng/agente-clinica-dental.git
git branch -M main
git push -u origin main
echo.
echo LISTO. Codigo subido a GitHub.
pause
