# © Todos os direitos reservados – github.com/Wbad-02
# ============================================================
# Script de configuração do Windows Firewall para o sistema
# de controle de estoque.
#
# EXECUTE COMO ADMINISTRADOR no Windows Server.
# PowerShell: clique direito → "Executar como Administrador"
# ============================================================

param(
    [string]$SubRede = "192.168.0.0/24",   # ← AJUSTE para sua sub-rede
    [int]   $Porta   = 8000
)

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  Configuração de Firewall — Controle de Estoque  ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Verificar se é administrador ────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ Execute este script como Administrador!" -ForegroundColor Red
    exit 1
}

# ── Remover regras antigas do sistema de estoque ────────────
Write-Host "🧹 Removendo regras antigas..." -ForegroundColor Yellow
Get-NetFirewallRule -DisplayName "Estoque*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

# ── Regra 1: Permitir acesso à porta do sistema somente da rede interna
Write-Host "🔒 Criando regra: permitir porta $Porta apenas de $SubRede..." -ForegroundColor Yellow
New-NetFirewallRule `
    -DisplayName "Estoque - Acesso Web Interno" `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort $Porta `
    -RemoteAddress $SubRede `
    -Action Allow `
    -Profile Domain,Private `
    -Description "Permite acesso ao sistema de estoque somente pela rede interna" | Out-Null

# ── Regra 2: Bloquear qualquer outro acesso à porta (internet, etc.) ──
Write-Host "🔒 Criando regra: bloquear acesso externo à porta $Porta..." -ForegroundColor Yellow
New-NetFirewallRule `
    -DisplayName "Estoque - Bloquear Externo" `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort $Porta `
    -RemoteAddress Any `
    -Action Block `
    -Profile Public `
    -Description "Bloqueia acesso externo ao sistema de estoque" | Out-Null

# ── Regra 3: Bloquear porta 8000 para saída externa (opcional — redundância) ──
New-NetFirewallRule `
    -DisplayName "Estoque - Bloquear Saida Externa" `
    -Direction Outbound `
    -Protocol TCP `
    -RemotePort $Porta `
    -RemoteAddress Internet `
    -Action Block `
    -Profile Public `
    -Description "Bloqueia saída do sistema para internet" | Out-Null

# ── Desativar perfil Public no adaptador de rede interno ────
Write-Host "🔒 Verificando perfil de rede..." -ForegroundColor Yellow
$adaptadores = Get-NetConnectionProfile
foreach ($ad in $adaptadores) {
    Write-Host "   Adaptador: $($ad.InterfaceAlias) | Perfil atual: $($ad.NetworkCategory)"
    if ($ad.NetworkCategory -eq "Public") {
        Write-Host "   ⚠️  Alterando para 'Private' (necessário para regras de domínio/privado)" -ForegroundColor Yellow
        Set-NetConnectionProfile -InterfaceIndex $ad.InterfaceIndex -NetworkCategory Private
    }
}

# ── Garantir que o Firewall está ativo em todos os perfis ──
Write-Host "🔒 Ativando Windows Firewall em todos os perfis..." -ForegroundColor Yellow
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True

# ── Desativar SMBv1 (protocolo legado e inseguro) ───────────
Write-Host "🔒 Desativando SMBv1 (protocolo legado)..." -ForegroundColor Yellow
Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force -ErrorAction SilentlyContinue

# ── Desativar LLMNR (Link-Local Multicast Name Resolution) ──
Write-Host "🔒 Desativando LLMNR via GPO local..." -ForegroundColor Yellow
$llmnrPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient"
if (-not (Test-Path $llmnrPath)) { New-Item -Path $llmnrPath -Force | Out-Null }
Set-ItemProperty -Path $llmnrPath -Name "EnableMulticast" -Value 0 -Type DWord

# ── Resumo ──────────────────────────────────────────────────
Write-Host ""
Write-Host "✅ Configuração concluída!" -ForegroundColor Green
Write-Host ""
Write-Host "Regras criadas:" -ForegroundColor Cyan
Get-NetFirewallRule -DisplayName "Estoque*" | Format-Table DisplayName, Direction, Action, Enabled -AutoSize
Write-Host ""
Write-Host "Sub-rede autorizada : $SubRede"  -ForegroundColor Green
Write-Host "Porta protegida     : $Porta"    -ForegroundColor Green
Write-Host ""
Write-Host "⚠️  Para alterar a sub-rede, execute:" -ForegroundColor Yellow
Write-Host "   .\configurar_firewall_windows.ps1 -SubRede '10.0.0.0/8' -Porta 8000" -ForegroundColor Gray
