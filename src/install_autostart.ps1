# Installs per-user autostart (no admin required): copies the hidden
# launcher into the current user's Startup folder, then starts it now.
$ErrorActionPreference = 'Stop'
$startup = [Environment]::GetFolderPath('Startup')
Copy-Item 'D:\IslamicResourceHub\src\start_hub_hidden.vbs' $startup -Force
Write-Host "Installed to: $startup\start_hub_hidden.vbs"
Write-Host 'Worker will start automatically at every logon.'
