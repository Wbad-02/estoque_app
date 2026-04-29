# © Todos os direitos reservados – github.com/Wbad-02
# ============================================================
# Configuração de IP estático e máscara de rede para o servidor.
#
# Um IP fixo é essencial: se o servidor mudar de IP,
# os clientes perdem o acesso e os bookmarks quebram.
#
# EXECUTE COMO ADMINISTRADOR.
# ============================================================

param(
    [string]$IPServidor    = "192.168.0.10",    # ← IP fixo desejado para este servidor
    [string]$MascaraRede   = "255.255.255.0",   # /24 → até 254 hosts na rede
    [string]$Gateway       = "192.168.0.1",     # ← IP do roteador/gateway
    [string]$DNS1          = "192.168.0.1",     # DNS primário (roteador)
    [string]$DNS2          = "8.8.8.8",         # DNS secundário (Google — fallback)
    [string]$Adaptador     = ""                 # Nome do adaptador (deixe vazio para listar)
)

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  Configuração de Rede — Controle de Estoque      ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Host "❌ Execute como Administrador!" -ForegroundColor Red; exit 1 }

# ── Listar adaptadores disponíveis ──────────────────────────
$adapts = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }
Write-Host "Adaptadores de rede ativos:" -ForegroundColor Cyan
$adapts | Format-Table Name, InterfaceDescription, LinkSpeed -AutoSize

if (-not $Adaptador) {
    Write-Host "⚠️  Informe o nome do adaptador com -Adaptador 'Nome'" -ForegroundColor Yellow
    Write-Host "   Exemplo: .\configurar_rede_windows.ps1 -Adaptador 'Ethernet'" -ForegroundColor Gray
    Write-Host ""

    # Mostrar configuração atual de cada adaptador
    Write-Host "Configuração atual de IP:" -ForegroundColor Cyan
    foreach ($ad in $adapts) {
        $ip = Get-NetIPAddress -InterfaceAlias $ad.Name -AddressFamily IPv4 -ErrorAction SilentlyContinue
        Write-Host "  $($ad.Name): $($ip.IPAddress)/$($ip.PrefixLength)"
    }
    exit 0
}

Write-Host ""
Write-Host "📋 Configuração que será aplicada:" -ForegroundColor Cyan
Write-Host "   Adaptador : $Adaptador"
Write-Host "   IP fixo   : $IPServidor"
Write-Host "   Máscara   : $MascaraRede  (/24 = até 254 dispositivos na rede)"
Write-Host "   Gateway   : $Gateway"
Write-Host "   DNS       : $DNS1, $DNS2"
Write-Host ""

$confirmar = Read-Host "Confirmar? (s/N)"
if ($confirmar -notmatch "^[sS]$") { Write-Host "Cancelado."; exit 0 }

# ── Calcular prefixo CIDR a partir da máscara ───────────────
$bytes   = ($MascaraRede -split '\.') | ForEach-Object { [Convert]::ToString([int]$_, 2).PadLeft(8,'0') }
$prefixo = ($bytes -join '').ToCharArray() | Where-Object { $_ -eq '1' } | Measure-Object | Select-Object -Expand Count

# ── Remover IPs existentes no adaptador ─────────────────────
Write-Host "🔧 Removendo configuração DHCP atual..." -ForegroundColor Yellow
Remove-NetIPAddress -InterfaceAlias $Adaptador -Confirm:$false -ErrorAction SilentlyContinue
Remove-NetRoute     -InterfaceAlias $Adaptador -Confirm:$false -ErrorAction SilentlyContinue

# ── Aplicar IP estático ─────────────────────────────────────
Write-Host "🔧 Aplicando IP estático $IPServidor/$prefixo..." -ForegroundColor Yellow
New-NetIPAddress `
    -InterfaceAlias $Adaptador `
    -IPAddress      $IPServidor `
    -PrefixLength   $prefixo `
    -DefaultGateway $Gateway | Out-Null

# ── Aplicar DNS ─────────────────────────────────────────────
Write-Host "🔧 Configurando DNS..." -ForegroundColor Yellow
Set-DnsClientServerAddress -InterfaceAlias $Adaptador -ServerAddresses $DNS1,$DNS2

Write-Host ""
Write-Host "✅ IP estático configurado com sucesso!" -ForegroundColor Green
Write-Host ""
Write-Host "Os clientes devem acessar o sistema em:" -ForegroundColor Cyan
Write-Host "   http://${IPServidor}:8000" -ForegroundColor White
Write-Host ""
Write-Host "⚠️  Atualize o arquivo middleware_seguranca.py:" -ForegroundColor Yellow

# Calcular a faixa de rede para exibir no middleware
$partes = $IPServidor -split '\.'
$rede   = "$($partes[0]).$($partes[1]).$($partes[2]).0/$prefixo"
Write-Host "   REDES_PERMITIDAS = ['127.0.0.1/32', '$rede']" -ForegroundColor Gray
