# © Todos os direitos reservados – github.com/Wbad-02
# ============================================================
# Backup automático do banco de dados SQLite.
# Agende via Agendador de Tarefas do Windows para rodar diariamente.
#
# Para agendar: Agendador de Tarefas → Nova Tarefa → Ação:
#   powershell.exe -File "C:\Upgrade\gestta_refresh\estoque_app\security\backup_automatico.ps1"
# ============================================================

param(
    [string]$PastaApp    = "$PSScriptRoot\..",
    [string]$PastaBackup = "$PSScriptRoot\..\backups",
    [int]   $ManterDias  = 30    # remove backups com mais de N dias
)

$banco   = Join-Path $PastaApp "estoque.db"
$data    = Get-Date -Format "yyyy-MM-dd_HH-mm"
$destino = Join-Path $PastaBackup "estoque_$data.db"

# Criar pasta de backup se não existir
if (-not (Test-Path $PastaBackup)) {
    New-Item -ItemType Directory -Path $PastaBackup | Out-Null
}

# Copiar banco
if (Test-Path $banco) {
    Copy-Item -Path $banco -Destination $destino
    Write-Host "✅ Backup criado: $destino"
} else {
    Write-Host "❌ Banco não encontrado em: $banco"
    exit 1
}

# Remover backups antigos
$antigos = Get-ChildItem -Path $PastaBackup -Filter "estoque_*.db" |
    Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-$ManterDias) }

foreach ($arq in $antigos) {
    Remove-Item $arq.FullName
    Write-Host "🗑️  Backup antigo removido: $($arq.Name)"
}

$total = (Get-ChildItem -Path $PastaBackup -Filter "estoque_*.db").Count
Write-Host "📦 Total de backups mantidos: $total (últimos $ManterDias dias)"
