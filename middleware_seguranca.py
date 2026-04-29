# © Todos os direitos reservados – github.com/Wbad-02
"""
Middleware de segurança — aplica headers HTTP de proteção em todas as respostas
e restringe acesso por faixa de IP (máscara de rede).

Camadas implementadas:
  1. Restrição de IP por CIDR (whitelist de rede interna)
  2. Rate limiting por IP (brute-force protection)
  3. Security headers HTTP (XSS, Clickjacking, MIME sniffing, etc.)
  4. Bloqueio de métodos HTTP não utilizados
  5. Ocultação de informações do servidor
"""
import time
import ipaddress
from collections import defaultdict
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ─────────────────────────────────────────────────────────────
# CONFIGURAÇÃO — ajuste conforme sua rede
# ─────────────────────────────────────────────────────────────

# Faixas de IP permitidas (CIDR). Adicione as sub-redes da sua empresa.
# Exemplos comuns de redes internas:
#   192.168.0.0/24  → 192.168.0.1 até 192.168.0.254
#   192.168.1.0/24  → 192.168.1.1 até 192.168.1.254
#   10.0.0.0/8      → toda a faixa 10.x.x.x
#   172.16.0.0/12   → 172.16.x.x até 172.31.x.x
REDES_PERMITIDAS: list[str] = [
    "127.0.0.1/32",      # localhost (obrigatório — permite o próprio servidor)
    "::1/128",           # localhost IPv6
    "192.168.0.0/24",    # ← AJUSTE para sua sub-rede real
    "192.168.1.0/24",    # ← adicione outras faixas se necessário
    "10.0.0.0/8",        # faixa privada classe A (ampla — restrinja se possível)
]

# Rate limiting — tentativas por janela de tempo
RATE_LIMIT_TENTATIVAS = 60     # máximo de requisições
RATE_LIMIT_JANELA_SEG = 60     # por janela de N segundos
RATE_LIMIT_LOGIN_MAX  = 10     # máximo de tentativas de login por janela
RATE_LIMIT_LOGIN_JAN  = 300    # janela de 5 minutos para login

# Métodos HTTP permitidos
METODOS_PERMITIDOS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}

# ─────────────────────────────────────────────────────────────
# Estruturas de rate limiting (em memória — reinicia com o servidor)
# ─────────────────────────────────────────────────────────────
_contadores:       dict[str, list[float]] = defaultdict(list)   # IP → timestamps gerais
_contadores_login: dict[str, list[float]] = defaultdict(list)   # IP → timestamps de login


def _ip_permitido(ip: str) -> bool:
    """Verifica se o IP está dentro de alguma rede autorizada."""
    try:
        addr = ipaddress.ip_address(ip)
        return any(
            addr in ipaddress.ip_network(rede, strict=False)
            for rede in REDES_PERMITIDAS
        )
    except ValueError:
        return False


def _rate_limit_ok(store: dict, ip: str, max_req: int, janela: int) -> bool:
    """
    Janela deslizante: remove timestamps antigos e verifica se o IP
    ainda está dentro do limite.
    Retorna True se a requisição é permitida.
    """
    agora = time.time()
    store[ip] = [t for t in store[ip] if agora - t < janela]
    if len(store[ip]) >= max_req:
        return False
    store[ip].append(agora)
    return True


class MiddlewareSeguranca(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        ip = self._extrair_ip(request)

        # ── 1. Bloqueio de método não permitido ──────────────────
        if request.method not in METODOS_PERMITIDOS:
            return JSONResponse(
                status_code=405,
                content={"detail": "Método não permitido"},
            )

        # ── 2. Whitelist de IP / máscara de rede ─────────────────
        if not _ip_permitido(ip):
            return JSONResponse(
                status_code=403,
                content={"detail": "Acesso negado: rede não autorizada"},
                headers={"X-Blocked-IP": ip},
            )

        # ── 3. Rate limiting geral ────────────────────────────────
        if not _rate_limit_ok(_contadores, ip, RATE_LIMIT_TENTATIVAS, RATE_LIMIT_JANELA_SEG):
            return JSONResponse(
                status_code=429,
                content={"detail": "Muitas requisições. Aguarde e tente novamente."},
                headers={"Retry-After": str(RATE_LIMIT_JANELA_SEG)},
            )

        # ── 4. Rate limiting específico para login (anti brute-force) ──
        if request.url.path == "/api/auth/login" and request.method == "POST":
            if not _rate_limit_ok(_contadores_login, ip, RATE_LIMIT_LOGIN_MAX, RATE_LIMIT_LOGIN_JAN):
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Muitas tentativas de login. Aguarde {RATE_LIMIT_LOGIN_JAN // 60} minutos."},
                    headers={"Retry-After": str(RATE_LIMIT_LOGIN_JAN)},
                )

        # ── 5. Processar requisição ───────────────────────────────
        response = await call_next(request)

        # ── 6. Security headers HTTP ──────────────────────────────
        self._aplicar_security_headers(response)

        return response

    @staticmethod
    def _extrair_ip(request: Request) -> str:
        """
        Extrai o IP real do cliente.
        Considera X-Forwarded-For se houver proxy reverso (nginx, etc.).
        """
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "0.0.0.0"

    @staticmethod
    def _aplicar_security_headers(response: Response) -> None:
        """
        Headers de segurança HTTP aplicados em TODAS as respostas.

        X-Content-Type-Options   → impede MIME sniffing
        X-Frame-Options          → bloqueia clickjacking via iframe
        X-XSS-Protection         → proteção XSS em navegadores legados
        Referrer-Policy          → não vaza a URL em requisições externas
        Content-Security-Policy  → restringe origens de scripts/estilos
        Permissions-Policy       → desativa APIs do navegador não utilizadas
        Cache-Control            → evita cache de dados sensíveis
        Server                   → oculta informações do servidor
        """
        h = response.headers
        h["X-Content-Type-Options"]  = "nosniff"
        h["X-Frame-Options"]         = "DENY"
        h["X-XSS-Protection"]        = "1; mode=block"
        h["Referrer-Policy"]         = "no-referrer"
        h["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "   # unsafe-inline necessário para o SPA inline
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        h["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=(), "
            "payment=(), usb=(), bluetooth=()"
        )
        h["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        h["Server"]        = "Estoque/3.0"          # oculta que é uvicorn/python
