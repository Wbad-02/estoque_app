# Todos os direitos reservados - github.com/Wbad-02
# Registra o backup diario do banco no Agendador de Tarefas do Windows.
# Execute como Administrador UMA UNICA VEZ apos instalar o sistema.

$PASTA_APP = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON    = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $PYTHON) {
    Write-Host "ERRO: Python nao encontrado. Instale o Python e tente novamente."
    exit 1
}

$SCRIPT_BACKUP = Join-Path $PASTA_APP "backup.py"

if (-not (Test-Path $SCRIPT_BACKUP)) {
    Write-Host "ERRO: backup.py nao encontrado em $SCRIPT_BACKUP"
    exit 1
}

$action    = New-ScheduledTaskAction -Execute $PYTHON -Argument "`"$SCRIPT_BACKUP`""
$trigger   = New-ScheduledTaskTrigger -Daily -At "02:00"
$settings  = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable $true
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

Register-ScheduledTask `
    -TaskName    "EstoqueBackupDiario" `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -Principal   $principal `
    -Description "Backup diario do Sistema de Estoque - retencao de 30 dias" `
    -Force | Out-Null

Write-Host "============================================"
Write-Host " Backup agendado com sucesso!"
Write-Host " Horario: diariamente as 02:00"
Write-Host " Retencao: 30 dias"
Write-Host " Script: $SCRIPT_BACKUP"
Write-Host ""
Write-Host " Comandos uteis:"
Write-Host "   Get-ScheduledTask -TaskName EstoqueBackupDiario"
Write-Host "   Start-ScheduledTask -TaskName EstoqueBackupDiario"
Write-Host "============================================"
