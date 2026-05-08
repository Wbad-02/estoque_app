# Sistema de Controle de Estoque — Documentação de Deploy

## Arquitetura

```
Usuário (internet)
    ↓ HTTPS
Cloudflare Edge (estoque.upgradecontabilidade.com)
    ↓ Tunnel QUIC
cloudflared.exe (C:\cloudflared\)
    ↓ HTTP
FastAPI/Uvicorn (localhost:8000)
    ↓
SQLite (C:\estoque_app\estoque.db)
```

---

## Servidor (nova máquina)

- **OS:** Windows Server (Administrator)
- **Python:** 3.12 em `C:\Program Files\Python312\`
- **App:** `C:\estoque_app\`
- **Cloudflare Tunnel:** `C:\cloudflared\`
- **URL pública:** https://estoque.upgradecontabilidade.com

---

## Variáveis de Ambiente (obrigatórias)

| Variável | Valor | Onde definir |
|---|---|---|
| `ESTOQUE_SECRET_KEY` | chave hex 64 chars | Variáveis do sistema Windows |
| `DESABILITAR_WHITELIST_IP` | `true` | Definida no comando de inicialização |
| `CORS_ORIGINS` | `https://estoque.upgradecontabilidade.com` | Definida no comando de inicialização |

**Verificar ESTOQUE_SECRET_KEY:**
```powershell
[System.Environment]::GetEnvironmentVariable("ESTOQUE_SECRET_KEY", "Machine")
```

**Gerar nova chave se necessário:**
```powershell
& "C:\Program Files\Python312\python.exe" -c "import secrets; print(secrets.token_hex(32))"
```

**Definir chave permanentemente:**
```powershell
[System.Environment]::SetEnvironmentVariable("ESTOQUE_SECRET_KEY", "SUA_CHAVE_AQUI", "Machine")
```

---

## Inicialização do Sistema

### Iniciar em background (uso normal)

```powershell
# Sistema de estoque
Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command `"cd C:\estoque_app; `$env:ESTOQUE_SECRET_KEY='SUA_CHAVE_AQUI'; `$env:DESABILITAR_WHITELIST_IP='true'; `$env:CORS_ORIGINS='https://estoque.upgradecontabilidade.com'; & 'C:\Program Files\Python312\python.exe' -m uvicorn main:app --host 0.0.0.0 --port 8000`""

# Cloudflare Tunnel
Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command `"C:\cloudflared\cloudflared.exe --config C:\cloudflared\config.yml tunnel run estoque`""
```

### Iniciar com janela visível (debug)

**Terminal 1 — Sistema:**
```powershell
cd C:\estoque_app
$env:ESTOQUE_SECRET_KEY = "SUA_CHAVE_AQUI"
$env:DESABILITAR_WHITELIST_IP = "true"
$env:CORS_ORIGINS = "https://estoque.upgradecontabilidade.com"
& "C:\Program Files\Python312\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — Tunnel:**
```powershell
C:\cloudflared\cloudflared.exe --config C:\cloudflared\config.yml tunnel run estoque
```

### Encerrar tudo

```powershell
Stop-Process -Name python -Force
Stop-Process -Name cloudflared -Force
```

---

## Verificação de Saúde

### Checklist completo

```powershell
# 1. Sistema respondendo localmente?
Invoke-WebRequest -Uri "http://localhost:8000" -UseBasicParsing -TimeoutSec 5 | Select-Object StatusCode

# 2. Porta 8000 ativa?
netstat -ano | findstr :8000

# 3. Tunnel rodando?
Get-Process cloudflared

# 4. Tunnel conectado à Cloudflare?
C:\cloudflared\cloudflared.exe tunnel info estoque

# 5. DNS propagado?
Resolve-DnsName upgradecontabilidade.com -Type NS

# 6. URL externa respondendo?
Invoke-WebRequest -Uri "https://estoque.upgradecontabilidade.com" -UseBasicParsing -TimeoutSec 10 | Select-Object StatusCode
```

### Saúde esperada

| Verificação | Resultado esperado |
|---|---|
| Porta 8000 | `LISTENING` |
| Get-Process cloudflared | Processo listado |
| tunnel info | `active connection` |
| NS do domínio | `irena.ns.cloudflare.com` |
| URL externa | StatusCode 200 |

---

## Backup

**Agendamento:** diário às 02:00 via Windows Task Scheduler
**Retenção:** 30 dias
**Local:** `C:\estoque_app\backups\`

```powershell
# Verificar status do agendamento
Get-ScheduledTask -TaskName "EstoqueBackupDiario"

# Rodar backup manualmente
Start-ScheduledTask -TaskName "EstoqueBackupDiario"

# Rodar backup manual direto
& "C:\Program Files\Python312\python.exe" C:\estoque_app\backup.py
```

---

## Cloudflare Tunnel

**Tunnel ID:** `86b50779-7d5a-4908-ac66-3278537a4068`
**Config:** `C:\cloudflared\config.yml`
**Credenciais:** `C:\cloudflared\86b50779-7d5a-4908-ac66-3278537a4068.json`

```powershell
# Info do tunnel
C:\cloudflared\cloudflared.exe tunnel info estoque

# Métricas em tempo real
Invoke-WebRequest -Uri "http://127.0.0.1:20241/metrics" -UseBasicParsing | Select-Object -ExpandProperty Content | Select-String "ha_connections|total_requests"
```

Resultado esperado: `cloudflared_tunnel_ha_connections 4`

---

## DNS

**Registrador:** HostGator Brasil
**DNS:** Cloudflare (nameservers alterados em 08/05/2026)

| Nameserver | |
|---|---|
| Primário | `irena.ns.cloudflare.com` |
| Secundário | `tim.ns.cloudflare.com` |

**CNAME no Cloudflare:**
```
estoque.upgradecontabilidade.com → 86b50779-7d5a-4908-ac66-3278537a4068.cfargotunnel.com
```

**Reverter nameservers (se necessário):**
Na HostGator: Domínios → upgradecontabilidade.com → Configurar domínio → Servidor personalizado
```
ns156.hostgator.com.br
ns157.hostgator.com.br
```

---

## Troubleshooting

### Sistema não inicia — Python não encontrado
```powershell
# Usar caminho completo do Python
& "C:\Program Files\Python312\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Tunnel sem conexão ativa
```powershell
Stop-Process -Name cloudflared -Force
Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command `"C:\cloudflared\cloudflared.exe --config C:\cloudflared\config.yml tunnel run estoque`""
```

### Login inválido no sistema
```powershell
cd C:\estoque_app
& "C:\Program Files\Python312\python.exe" -c "
from database import get_db
from models import Usuario
from auth import hash_senha
db = next(get_db())
admin = db.query(Usuario).filter(Usuario.email == 'admin@estoque.local').first()
if admin:
    admin.senha_hash = hash_senha('nova_senha_aqui')
    admin.ativo = True
    db.commit()
    print('Senha redefinida')
"
```

### Verificar usuários ativos
```powershell
cd C:\estoque_app
& "C:\Program Files\Python312\python.exe" -c "
from database import get_db
from models import Usuario
db = next(get_db())
for u in db.query(Usuario).all():
    print(f'{u.email} | ativo={u.ativo} | grupo={u.grupo}')
"
```

### URL externa com timeout — DNS não propagou
```powershell
Resolve-DnsName upgradecontabilidade.com -Type NS
# Aguardar irena.ns.cloudflare.com aparecer (pode levar até 24h)
```

### Porta 8000 já em uso
```powershell
netstat -ano | findstr :8000
# Anote o PID e encerre:
Stop-Process -Id SEU_PID -Force
```

---

## Atualização do Sistema

Na máquina de desenvolvimento (origem):
```powershell
git add .
git commit -m "descricao da mudanca"
git push privado master
```

Na máquina servidora:
```powershell
Stop-Process -Name python -Force
cd C:\estoque_app
git pull
# Reiniciar sistema normalmente
```

---

## Repositório

- **Privado:** https://github.com/Wbad-02/estoque_privado
- **Público (referência):** https://github.com/Wbad-02/estoque_app
- **Branch:** master
