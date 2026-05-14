# © Todos os direitos reservados – github.com/Wbad-02
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from models import GrupoPermissao
import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _validar_email(v: str) -> str:
    if not _EMAIL_RE.match(v):
        raise ValueError("E-mail inválido")
    return v.lower().strip()


# ── Auth ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    senha: str

    @field_validator("email")
    @classmethod
    def email_valido(cls, v): return _validar_email(v)

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    grupo:        str
    nome:         str


# ── Usuário ───────────────────────────────────────────
class UsuarioCreate(BaseModel):
    nome:  str
    email: str
    senha: str
    grupo: GrupoPermissao = GrupoPermissao.viewer

    @field_validator("email")
    @classmethod
    def email_valido(cls, v): return _validar_email(v)

    @field_validator("senha")
    @classmethod
    def senha_minima(cls, v):
        if len(v) < 6: raise ValueError("Senha deve ter ao menos 6 caracteres")
        return v

class UsuarioUpdate(BaseModel):
    nome:  Optional[str]            = None
    grupo: Optional[GrupoPermissao] = None
    ativo: Optional[bool]           = None

class UsuarioOut(BaseModel):
    id: int; nome: str; email: str
    grupo: GrupoPermissao; ativo: bool; criado_em: Optional[datetime] = None
    model_config = {"from_attributes": True}




# ── Senha ─────────────────────────────────────────────
class AlterarSenhaAdmin(BaseModel):
    """Admin altera a senha de qualquer usuário (sem precisar da senha antiga)."""
    nova_senha: str

    @field_validator("nova_senha")
    @classmethod
    def minima(cls, v):
        if len(v) < 6: raise ValueError("Senha deve ter ao menos 6 caracteres")
        return v


class AlterarSenhaPropria(BaseModel):
    """Usuário altera a própria senha — exige senha atual para confirmar identidade."""
    senha_atual: str
    nova_senha:  str

    @field_validator("nova_senha")
    @classmethod
    def minima(cls, v):
        if len(v) < 6: raise ValueError("Nova senha deve ter ao menos 6 caracteres")
        return v


class AtualizarPerfil(BaseModel):
    """Usuário atualiza o próprio nome."""
    nome: str

# ── Categoria ─────────────────────────────────────────
class CategoriaCreate(BaseModel):
    nome: str; descricao: Optional[str] = None

class CategoriaUpdate(BaseModel):
    nome: Optional[str] = None; descricao: Optional[str] = None

class CategoriaOut(BaseModel):
    id: int; nome: str; descricao: Optional[str]; criado_em: datetime
    model_config = {"from_attributes": True}


# ── Grupo ─────────────────────────────────────────────
class GrupoCreate(BaseModel):
    nome: str; descricao: Optional[str] = None
    quantidade_minima: float = 0.0; categoria_id: int

    @field_validator("quantidade_minima")
    @classmethod
    def nao_neg(cls, v):
        if v < 0: raise ValueError("Não pode ser negativo")
        return v

class GrupoUpdate(BaseModel):
    nome: Optional[str] = None; descricao: Optional[str] = None
    quantidade_minima: Optional[float] = None; categoria_id: Optional[int] = None

    @field_validator("quantidade_minima", mode="before")
    @classmethod
    def nao_neg(cls, v):
        if v is not None and v < 0: raise ValueError("Não pode ser negativo")
        return v

class GrupoOut(BaseModel):
    id: int; nome: str; descricao: Optional[str]
    quantidade_minima: float; categoria_id: int
    categoria: CategoriaOut; criado_em: datetime
    model_config = {"from_attributes": True}


# ── Material ──────────────────────────────────────────
class MaterialCreate(BaseModel):
    nome: str; descricao: Optional[str] = None
    quantidade: float = 0.0; unidade: str = "un"; grupo_id: int
    usa_patrimonio: bool = False
    valor_unitario: Optional[float] = None
    codigo_patrimonio: Optional[str] = None

    @field_validator("quantidade")
    @classmethod
    def nao_neg(cls, v):
        if v < 0: raise ValueError("Não pode ser negativo")
        return v

    @field_validator("codigo_patrimonio")
    @classmethod
    def validar_codigo(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if not v:
            return None
        if len(v) > 8:
            raise ValueError("Código de patrimônio deve ter no máximo 8 caracteres")
        if not v.isalnum():
            raise ValueError("Código de patrimônio deve conter apenas letras e números")
        return v

class MaterialUpdate(BaseModel):
    nome: Optional[str] = None; descricao: Optional[str] = None
    quantidade: Optional[float] = None; unidade: Optional[str] = None
    grupo_id: Optional[int] = None; ativo: Optional[bool] = None
    usa_patrimonio: Optional[bool] = None
    valor_unitario: Optional[float] = None
    tag: Optional[str] = None

    @field_validator("quantidade", mode="before")
    @classmethod
    def nao_neg(cls, v):
        if v is not None and v < 0: raise ValueError("Não pode ser negativo")
        return v

class MaterialOut(BaseModel):
    id: int; nome: str; descricao: Optional[str]
    quantidade: float; unidade: str; grupo_id: int
    grupo: GrupoOut; ativo: bool; alerta_minimo: bool = False
    usa_patrimonio: bool = False
    valor_unitario: Optional[float] = None
    tag: Optional[str] = None
    criado_em: datetime; atualizado_em: datetime
    ultima_retirada: Optional[datetime] = None
    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_alert(cls, obj):
        data = cls.model_validate(obj)
        data.alerta_minimo   = bool(obj.alerta_minimo)
        data.ultima_retirada = obj.ultima_retirada
        data.usa_patrimonio  = bool(obj.usa_patrimonio)
        data.valor_unitario  = obj.valor_unitario
        data.tag             = obj.tag
        return data



# ── Patrimônio ────────────────────────────────────────────────
class UnidadeCreate(BaseModel):
    codigo:        Optional[str]   = None   # ex: TI-001, MON-005
    observacao:    Optional[str]   = None
    origem:        str             = "manual"   # "manual" | "xml"
    nf_numero:     Optional[str]   = None
    valor_unitario: Optional[float] = None
    tag:           Optional[str]   = None   # "novo" | "usado"

    @field_validator("codigo")
    @classmethod
    def validar_codigo(cls, v):
        if v is None:
            return v
        import re
        # Aceita formatos como TI-001, MON-005, NB001, PC-2024-01
        if not re.match(r"^[A-Za-z]{1,10}[-_]?[0-9]{1,6}$", v.strip()):
            raise ValueError("Código deve ter letras seguidas de números (ex: TI-001, MON-005)")
        return v.strip().upper()


class UnidadeOut(BaseModel):
    id:             int
    material_id:    int
    codigo:         Optional[str]
    observacao:     Optional[str]
    status:         str
    origem:         str = "manual"
    nf_numero:      Optional[str]   = None
    valor_unitario: Optional[float] = None
    tag:            Optional[str]   = None
    criado_em:      datetime
    retirado_em:    Optional[datetime] = None
    # campos enriquecidos pelo router
    nome_material:  str = ""
    retirado_por:   str = ""
    motivo_saida:   str = ""
    ativo_nome:     str = ""
    ativo_categoria: str = ""
    model_config = {"from_attributes": True}


class EditarCodigoUnidade(BaseModel):
    """Atualizar código de patrimônio de uma unidade."""
    codigo: str

    @field_validator("codigo")
    @classmethod
    def validar_codigo(cls, v):
        import re
        v = v.strip().upper()
        if not v:
            raise ValueError("Código não pode ser vazio")
        if len(v) > 20:
            raise ValueError("Código deve ter no máximo 20 caracteres")
        if not re.match(r"^[A-Z0-9][A-Z0-9\-_]*$", v):
            raise ValueError("Código deve conter apenas letras, números, hífen ou underscore")
        return v


class RetiradaPatrimonioCreate(BaseModel):
    """Retirada de uma unidade específica com patrimônio."""
    unidade_id:  int
    motivo:      str
    observacao:  Optional[str] = None


# ── Ativos Categorias ─────────────────────────────────
class AtivoCategoriaCreate(BaseModel):
    nome: str; descricao: Optional[str] = None

class AtivoCategoriaUpdate(BaseModel):
    nome: Optional[str] = None; descricao: Optional[str] = None

class AtivoCategoriaOut(BaseModel):
    id: int; nome: str; descricao: Optional[str]; criado_em: datetime
    model_config = {"from_attributes": True}


# ── Ativos Grupos ──────────────────────────────────────
class AtivoGrupoCreate(BaseModel):
    nome: str; descricao: Optional[str] = None; categoria_id: int

class AtivoGrupoUpdate(BaseModel):
    nome: Optional[str] = None; descricao: Optional[str] = None
    categoria_id: Optional[int] = None

class AtivoGrupoOut(BaseModel):
    id: int; nome: str; descricao: Optional[str]
    categoria_id: int; categoria: AtivoCategoriaOut; criado_em: datetime
    model_config = {"from_attributes": True}


# ── Ativos ─────────────────────────────────────────────
class AtivoCreate(BaseModel):
    nome: str; descricao: Optional[str] = None; grupo_id: int

class AtivoUpdate(BaseModel):
    nome: Optional[str] = None; descricao: Optional[str] = None
    grupo_id: Optional[int] = None; ativo: Optional[bool] = None

class AtivoItemOut(BaseModel):
    id: int; material_id: int; quantidade: float
    observacao: Optional[str]; atribuido_em: datetime
    devolvido_em: Optional[datetime] = None
    nome_material: str = ""; categoria_nome: str = ""; grupo_nome: str = ""
    unidade: str = ""
    unidade_codigo: Optional[str] = None
    model_config = {"from_attributes": True}

class AtivoOut(BaseModel):
    id: int; nome: str; descricao: Optional[str]
    grupo_id: int; grupo: AtivoGrupoOut; ativo: bool
    criado_em: datetime; itens_ativos: int = 0
    model_config = {"from_attributes": True}

class AtribuirMaterialCreate(BaseModel):
    material_id: int
    unidade_id: int
    observacao: Optional[str] = None


# Incluir unidade_id opcional no schema de saída da movimentação
# ── Movimentação ──────────────────────────────────────
class RetiradaCreate(BaseModel):
    material_id: int
    quantidade:  float
    motivo:      str
    observacao:  Optional[str] = None

    @field_validator("quantidade")
    @classmethod
    def maior_zero(cls, v):
        if v <= 0: raise ValueError("Quantidade deve ser maior que zero")
        return v

    @field_validator("motivo")
    @classmethod
    def motivo_nao_vazio(cls, v):
        if not v or not v.strip():
            raise ValueError("Motivo é obrigatório")
        return v.strip()

class MovimentacaoOut(BaseModel):
    id: int; material_id: int; tipo: str
    quantidade: float; motivo: Optional[str]
    observacao: Optional[str]; criado_em: datetime
    tag:             Optional[str] = None
    nome_material:   str = ""
    nome_usuario:    str = ""
    grupo_nome:      str = ""
    categoria_nome:  str = ""
    unidade_codigo:  Optional[str] = None
    model_config = {"from_attributes": True}


# ── Entrada de Material ───────────────────────────────
class EntradaMaterialCreate(BaseModel):
    quantidade:        float
    valor_unitario:    Optional[float] = None
    usa_patrimonio:    Optional[bool]  = None
    observacao:        Optional[str]   = None
    codigo_patrimonio: Optional[str]   = None

    @field_validator("quantidade")
    @classmethod
    def maior_zero(cls, v):
        if v <= 0: raise ValueError("Quantidade deve ser maior que zero")
        return v

    @field_validator("codigo_patrimonio")
    @classmethod
    def validar_codigo(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if not v:
            return None
        if len(v) > 8:
            raise ValueError("Código de patrimônio deve ter no máximo 8 caracteres")
        if not v.isalnum():
            raise ValueError("Código de patrimônio deve conter apenas letras e números")
        return v


# ── Notificações ──────────────────────────────────────
class NotificacaoEmailCreate(BaseModel):
    email:          str
    tipo:           str           # "retirada" | "entrada" | "alerta"
    intervalo_dias: Optional[int] = None

    @field_validator("email")
    @classmethod
    def email_valido(cls, v): return _validar_email(v)

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v):
        if v not in ("retirada", "entrada", "alerta", "requerimento", "requerimento_decisao"):
            raise ValueError("Tipo deve ser: retirada, entrada, alerta ou requerimento")
        return v

class NotificacaoEmailOut(BaseModel):
    id: int; email: str; tipo: str; ativo: bool
    intervalo_dias: Optional[int] = None
    criado_em: datetime
    model_config = {"from_attributes": True}


# ── Motivos personalizados ─────────────────────────────
class MotivoPersonalizadoCreate(BaseModel):
    nome: str

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Nome não pode ser vazio")
        return v

class MotivoPersonalizadoOut(BaseModel):
    id: int; nome: str; ativo: bool; criado_em: datetime
    model_config = {"from_attributes": True}


class NotificacaoTemplateCreate(BaseModel):
    tipo:    str
    assunto: str
    corpo:   str

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v):
        if v not in ("retirada", "entrada", "alerta", "requerimento", "requerimento_decisao"):
            raise ValueError("Tipo deve ser: retirada, entrada, alerta ou requerimento")
        return v

class NotificacaoTemplateOut(BaseModel):
    id: int; tipo: str; assunto: str; corpo: str; atualizado_em: datetime
    model_config = {"from_attributes": True}


# ── Requerimento de Compra ─────────────────────────────
class ItemRequerimentoCreate(BaseModel):
    nome:  str
    valor: float

class RequerimentoCreate(BaseModel):
    titulo: str
    itens:  list[ItemRequerimentoCreate]

class AprovarRequerimentoBody(BaseModel):
    observacao: Optional[str] = None

class RejeitarRequerimentoBody(BaseModel):
    observacao: str

class ItemRequerimentoOut(BaseModel):
    id: int; nome: str; valor: float
    model_config = {"from_attributes": True}

class RequerimentoOut(BaseModel):
    id: int; titulo: str; status: str
    criado_em: datetime; atualizado_em: datetime
    observacao: Optional[str] = None
    criador_nome:  str = ""
    aprovador_nome: str = ""
    total: float = 0.0
    itens: list[ItemRequerimentoOut] = []
    model_config = {"from_attributes": True}
