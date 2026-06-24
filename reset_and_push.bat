@echo off
echo Borrando historial git y empezando limpio...
rmdir /s /q .git
git init
git add .
git commit -m "feat: agente clinica dental camila"
git branch -M main
git remote add origin https://github.com/mirko93-eng/agente-clinica-dental.git
git push -f origin main
echo.
echo LISTO. Codigo subido a GitHub sin secretos.
pause
