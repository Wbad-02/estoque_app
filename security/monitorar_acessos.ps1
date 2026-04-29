# © Todos os direitos reservados – github.com/Wbad-02
# ============================================================
# Monitor de acessos — exibe tentativas de conexão bloqueadas
# e acessos ativos na porta do sistema de estoque.
#
# Execute em qualquer PowerShell (não precisa ser admin).
# ============================================================

param([int]$Porta = 8000, [int]$IntervaloSeg = 10)

Write-Host "🔍 Monitorando porta $Porta (atualiza a cada ${IntervaloSeg}s). Ctrl+C para sair." -ForegroundColor Cyan

while ($true) {
    Clear-Host
    Write-Host "═══ Monitor de Conexões — Estoque — $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss') ═══" -ForegroundColor Cyan
    Write-Host ""

    # Conexões ativas na porta do sistema
    $conexoes = Get-NetTCPConnection -LocalPort $Porta -ErrorAction SilentlyContinue |
        Where-Object { $_.State -ne "Listen" }

    Write-Host "Conexões ativas na porta $Porta :" -ForegroundColor Yellow
    if ($conexoes) {
        $conexoes | Format-Table LocalAddress,LocalPort,RemoteAddress,RemotePort,State -AutoSize
    } else {
        Write-Host "   Nenhuma conexão ativa no momento." -ForegroundColor Gray
    }

    # IPs únicos conectados
    $ips = $conexoes | Select-Object -ExpandProperty RemoteAddress -Unique
    if ($ips) {
        Write-Host "IPs conectados agora: $($ips -join ', ')" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "Regras de firewall do Estoque:" -ForegroundColor Yellow
    Get-NetFirewallRule -DisplayName "Estoque*" -ErrorAction SilentlyContinue |
        Format-Table DisplayName,Direction,Action,Enabled -AutoSize

    Start-Sleep -Seconds $IntervaloSeg
}
