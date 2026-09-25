@echo off
title SHADER7 AI - Update Root Shortcuts
echo Updating root shortcuts for current drive...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$appDir = $PSScriptRoot;" ^
  "$rootDir = Split-Path -Parent $appDir;" ^
  "if (-not $rootDir) { $rootDir = (Get-Item $appDir).Parent.FullName };" ^
  "$wsh = New-Object -ComObject WScript.Shell;" ^
  "$sc1 = $wsh.CreateShortcut((Join-Path $rootDir 'Install.lnk'));" ^
  "$sc1.TargetPath = (Join-Path $appDir 'Install_To_PC.bat');" ^
  "$sc1.WorkingDirectory = $appDir;" ^
  "$sc1.IconLocation = (Join-Path $appDir 'app.ico') + ',0';" ^
  "$sc1.Save();" ^
  "$sc2 = $wsh.CreateShortcut((Join-Path $rootDir 'Launch Now in CPU.lnk'));" ^
  "$sc2.TargetPath = (Join-Path $appDir 'Launch_SHADER7_AI.vbs');" ^
  "$sc2.Arguments = 'cpu';" ^
  "$sc2.WorkingDirectory = $appDir;" ^
  "$sc2.IconLocation = (Join-Path $appDir 'app.ico') + ',0';" ^
  "$sc2.Save();" ^
  "$sc3 = $wsh.CreateShortcut((Join-Path $rootDir 'Launch Now in GPU.lnk'));" ^
  "$sc3.TargetPath = (Join-Path $appDir 'Launch_SHADER7_AI.vbs');" ^
  "$sc3.Arguments = 'gpu';" ^
  "$sc3.WorkingDirectory = $appDir;" ^
  "$sc3.IconLocation = (Join-Path $appDir 'app.ico') + ',0';" ^
  "$sc3.Save();" ^
  "Write-Host 'Root shortcuts updated successfully for drive letter:' (Split-Path -Qualifier $rootDir)"
echo.
pause
