# © Todos os direitos reservados – github.com/Wbad-02
# Execute este script como Administrador UMA UNICA VEZ na maquina servidora.
# Ele baixa o cloudflared, cria o tunel, aponta o DNS e instala como servico Windows.

$DOMINIO     = "estoque.upgradecontabilidade.com"
$NOME_TUNNEL = "estoque"
$PASTA       = "C:\cloudflared"
$EXE         = "$PASTA\cloudflared.exe"
$CONFIG      = "$PASTA\config.yml"

Write-Host "============================================"
Write-Host " Instalacao do Cloudflare Tunnel"
Write-Host " Dominio: $DOMINIO"
Write-Host "============================================"
Write-Host ""

# 1. Criar pasta
New-Item -ItemType Directory -Force -Path $PASTA | Out-Null
Write-Host "[1/7] Pasta criada: $PASTA"

# 2. Baixar cloudflared
Write-Host "[2/7] Baixando cloudflared.exe..."
$url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
Invoke-WebRequest -Uri $url -OutFile $EXE -UseBasicParsing
Write-Host "      OK: $EXE"

# 3. Login (abre o navegador — autorize a conta Cloudflare)
Write-Host ""
Write-Host "[3/7] Abrindo navegador para autenticar no Cloudflare..."
Write-Host "      Autorize a conta que gerencia o dominio upgradecontabilidade.com"
Write-Host ""
& $EXE login
if ($LASTEXITCODE -ne 0) { Write-Host "ERRO no login. Abortando."; exit 1 }

# 4. Criar tunel e capturar UUID
Write-Host ""
Write-Host "[4/7] Criando tunel '$NOME_TUNNEL'..."
$output = & $EXE tunnel create $NOME_TUNNEL 2>&1 | Out-String
$uuid   = [regex]::Match($output, '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}').Value

if (-not $uuid) {
    Write-Host "ERRO: nao foi possivel extrair o UUID do tunel."
    Write-Host "Saida: $output"
    exit 1
}
Write-Host "      UUID: $uuid"

# 5. Apontar DNS
Write-Host "[5/7] Criando registro DNS: $DOMINIO -> tunel..."
& $EXE tunnel route dns $NOME_TUNNEL $DOMINIO
if ($LASTEXITCODE -ne 0) { Write-Host "AVISO: falha ao criar DNS. Verifique manualmente no painel Cloudflare." }

# 6. Escrever config.yml
Write-Host "[6/7] Gravando configuracao em $CONFIG..."
$credsFile = "$env:USERPROFILE\.cloudflared\$uuid.json"

@"
tunnel: $uuid
credentials-file: $credsFile

ingress:
  - hostname: $DOMINIO
    service: http://localhost:8000
  - service: http_status:404
"@ | Set-Content -Path $CONFIG -Encoding UTF8

Write-Host "      OK: $CONFIG"

# 7. Instalar como servico Windows (inicia automaticamente com o sistema)
Write-Host "[7/7] Instalando cloudflared como servico Windows..."
& $EXE --config $CONFIG service install
if ($LASTEXITCODE -eq 0) {
    Start-Service -Name cloudflared -ErrorAction SilentlyContinue
    Write-Host "      Servico instalado e iniciado."
} else {
    Write-Host "      AVISO: falha ao instalar servico. Inicie manualmente com iniciar_tunnel.ps1"
}

Write-Host ""
Write-Host "============================================"
Write-Host " Instalacao concluida!"
Write-Host " URL: https://$DOMINIO"
Write-Host ""
Write-Host " Comandos uteis:"
Write-Host "   sc query cloudflared        -> status do servico"
Write-Host "   sc start cloudflared        -> iniciar"
Write-Host "   sc stop cloudflared         -> parar"
Write-Host "============================================"
