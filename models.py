# © Todos os direitos reservados – github.com/Wbad-02
from datetime import datetime, timezone, timedelta
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text, Enum
)
from sqlalchemy.orm import relationship
from database import Base
import enum

_BR = timezone(timedelta(hours=-3))

def agora() -> datetime:
    return datetime.now(_BR).replace(tzinfo=None)


class GrupoPermissao(str, enum.Enum):
    mestre = "mestre"   # oculto — acima do admin
    admin  = "admin"
    editor = "editor"
    viewer = "viewer"


class MotivoRetirada(str, enum.Enum):
    colaborador = "colaborador"
    defeito     = "defeito"


class MotivoPersonalizado(Base):
    __tablename__ = "motivos_personalizados"
    id        = Column(Integer, primary_key=True, index=True)
    nome      = Column(String(100), nullable=False, unique=True)
    ativo     = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=agora)


class Usuario(Base):
    __tablename__ = "usuarios"
    id         = Column(Integer, primary_key=True, index=True)
    nome       = Column(String(100), nullable=False)
    email      = Column(String(150), unique=True, index=True, nullable=False)
    senha_hash = Column(String(200), nullable=False)
    grupo      = Column(Enum(GrupoPermissao), nullable=False, default=GrupoPermissao.viewer)
    ativo      = Column(Boolean, default=True)
    criado_em  = Column(DateTime, default=agora)
    logs          = relationship("LogAuditoria", back_populates="usuario")
    movimentacoes = relationship("Movimentacao", back_populates="usuario")


class Categoria(Base):
    __tablename__ = "categorias"
    id        = Column(Integer, primary_key=True, index=True)
    nome      = Column(String(100), unique=True, nullable=False)
    descricao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=agora)
    grupos = relationship("GrupoMaterial", back_populates="categoria", cascade="all, delete-orphan")


class GrupoMaterial(Base):
    __tablename__ = "grupos_material"
    id                = Column(Integer, primary_key=True, index=True)
    nome              = Column(String(100), nullable=False)
    descricao         = Column(Text, nullable=True)
    quantidade_minima = Column(Float, default=0.0)
    categoria_id      = Column(Integer, ForeignKey("categorias.id"), nullable=False)
    criado_em         = Column(DateTime, default=agora)
    categoria = relationship("Categoria", back_populates="grupos")
    materiais = relationship("Material", back_populates="grupo", cascade="all, delete-orphan")


class Material(Base):
    __tablename__ = "materiais"
    id            = Column(Integer, primary_key=True, index=True)
    nome          = Column(String(150), nullable=False)
    descricao     = Column(Text, nullable=True)
    quantidade    = Column(Float, default=0.0)
    unidade       = Column(String(30), default="un")
    grupo_id      = Column(Integer, ForeignKey("grupos_material.id", ondelete="CASCADE"), nullable=False)
    ativo         = Column(Boolean, default=True)
    criado_em     = Column(DateTime, default=agora)
    atualizado_em = Column(DateTime, default=agora, onupdate=agora)
    usa_patrimonio = Column(Boolean, default=False)

    grupo         = relationship("GrupoMaterial", back_populates="materiais")
    movimentacoes = relationship("Movimentacao", back_populates="material", order_by="Movimentacao.criado_em.desc()")
    unidades      = relationship("UnidadePatrimonio", back_populates="material", order_by="UnidadePatrimonio.criado_em.asc()")

    @property
    def categoria(self):
        return self.grupo.categoria if self.grupo else None

    @property
    def quantidade_minima(self):
        return self.grupo.quantidade_minima if self.grupo else 0.0

    @property
    def alerta_minimo(self):
        minimo = self.quantidade_minima
        if not minimo:
            return False
        total_grupo = sum(m.quantidade for m in self.grupo.materiais if m.ativo)
        return total_grupo <= minimo

    valor_unitario = Column(Float, nullable=True)
    tag            = Column(String(10), nullable=True)  # 'novo', 'usado'

    @property
    def ultima_retirada(self):
        for m in sorted(self.movimentacoes, key=lambda x: x.criado_em, reverse=True):
            if m.tipo == "saida":
                return m.criado_em
        return None



class StatusUnidade(str, enum.Enum):
    ativo    = "ativo"     # disponível em estoque
    retirado = "retirado"  # saiu do estoque


class UnidadePatrimonio(Base):
    """
    Rastreia cada unidade física individualmente.
    Usada apenas para materiais com usa_patrimonio=True
    (ex: monitor, notebook, gabinete).
    """
    __tablename__ = "unidades_patrimonio"

    id            = Column(Integer, primary_key=True, index=True)
    material_id   = Column(Integer, ForeignKey("materiais.id", ondelete="CASCADE"), nullable=False)
    codigo        = Column(String(100), nullable=True)   # número de patrimônio (ex: TI-001)
    observacao    = Column(Text, nullable=True)
    status        = Column(Enum(StatusUnidade), default=StatusUnidade.ativo, nullable=False)
    origem        = Column(String(20), default="manual")  # "manual" | "xml" | "sistema"
    nf_numero     = Column(String(50), nullable=True)     # NF-e de origem quando vim de XML
    valor_unitario = Column(Float, nullable=True)
    tag            = Column(String(10), nullable=True)    # "novo" | "usado"
    criado_em     = Column(DateTime, default=agora)
    retirado_em   = Column(DateTime, nullable=True)

    # FK para a movimentação de saída que retirou esta unidade
    movimentacao_saida_id = Column(Integer, ForeignKey("movimentacoes.id", ondelete="SET NULL"), nullable=True)

    material         = relationship("Material", back_populates="unidades")
    movimentacao_saida = relationship("Movimentacao", foreign_keys=[movimentacao_saida_id])


class Movimentacao(Base):
    __tablename__ = "movimentacoes"
    id             = Column(Integer, primary_key=True, index=True)
    material_id    = Column(Integer, ForeignKey("materiais.id"), nullable=False)
    usuario_id     = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    unidade_id     = Column(Integer, ForeignKey("unidades_patrimonio.id", ondelete="SET NULL"), nullable=True)
    tipo           = Column(String(10), nullable=False)           # "entrada" | "saida"
    quantidade     = Column(Float, nullable=False)
    motivo         = Column(String(100), nullable=True)            # só para saídas
    observacao     = Column(Text, nullable=True)
    valor_unitario = Column(Float, nullable=True)                 # valor na época da entrada
    tag            = Column(String(10), nullable=True)            # "novo" | "usado" (lotes)
    nf_numero      = Column(String(50), nullable=True)
    criado_em      = Column(DateTime, default=agora)
    material = relationship("Material", back_populates="movimentacoes")
    usuario  = relationship("Usuario",  back_populates="movimentacoes")


class AtivoCategoria(Base):
    __tablename__ = "ativos_categorias"
    id        = Column(Integer, primary_key=True, index=True)
    nome      = Column(String(100), unique=True, nullable=False)
    descricao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=agora)
    grupos    = relationship("AtivoGrupo", back_populates="categoria", cascade="all, delete-orphan")


class AtivoGrupo(Base):
    __tablename__ = "ativos_grupos"
    id           = Column(Integer, primary_key=True, index=True)
    nome         = Column(String(100), nullable=False)
    descricao    = Column(Text, nullable=True)
    categoria_id = Column(Integer, ForeignKey("ativos_categorias.id"), nullable=False)
    criado_em    = Column(DateTime, default=agora)
    categoria    = relationship("AtivoCategoria", back_populates="grupos")
    ativos       = relationship("Ativo", back_populates="grupo", cascade="all, delete-orphan")


class Ativo(Base):
    __tablename__ = "ativos"
    id        = Column(Integer, primary_key=True, index=True)
    nome      = Column(String(150), nullable=False)
    descricao = Column(Text, nullable=True)
    grupo_id  = Column(Integer, ForeignKey("ativos_grupos.id"), nullable=False)
    ativo     = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=agora)
    grupo     = relationship("AtivoGrupo", back_populates="ativos")
    itens     = relationship("AtivoItem", back_populates="ativo_obj", cascade="all, delete-orphan")


class AtivoItem(Base):
    """Material em uso por um Ativo (ex: colaborador usando um equipamento)."""
    __tablename__ = "ativos_itens"
    id           = Column(Integer, primary_key=True, index=True)
    ativo_id     = Column(Integer, ForeignKey("ativos.id"), nullable=False)
    material_id  = Column(Integer, ForeignKey("materiais.id"), nullable=False)
    unidade_id   = Column(Integer, ForeignKey("unidades_patrimonio.id", ondelete="SET NULL"), nullable=True)
    quantidade   = Column(Float, default=1.0)
    observacao   = Column(Text, nullable=True)
    atribuido_em = Column(DateTime, default=agora)
    devolvido_em = Column(DateTime, nullable=True)
    ativo_obj    = relationship("Ativo", back_populates="itens")
    material     = relationship("Material")
    unidade_patr = relationship("UnidadePatrimonio", foreign_keys=[unidade_id])


class LogAuditoria(Base):
    __tablename__ = "logs_auditoria"
    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    acao        = Column(String(50), nullable=False)
    entidade    = Column(String(50), nullable=False)
    entidade_id = Column(Integer, nullable=True)
    detalhe     = Column(Text, nullable=True)
    criado_em   = Column(DateTime, default=agora)
    usuario = relationship("Usuario", back_populates="logs")


class NotificacaoEmail(Base):
    """E-mails cadastrados para receber notificações."""
    __tablename__ = "notificacoes_emails"
    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String(150), nullable=False)
    tipo           = Column(String(20), nullable=False)  # "retirada" | "entrada" | "alerta"
    ativo          = Column(Boolean, default=True)
    intervalo_dias = Column(Integer, nullable=True)      # periodicidade de envio automático (alertas)
    criado_em      = Column(DateTime, default=agora)


class NotificacaoTemplate(Base):
    """Template de e-mail por tipo de notificação."""
    __tablename__ = "notificacoes_templates"
    id           = Column(Integer, primary_key=True, index=True)
    tipo         = Column(String(20), nullable=False, unique=True)  # "retirada" | "entrada" | "alerta"
    assunto      = Column(String(200), nullable=False)
    corpo        = Column(Text, nullable=False)
    atualizado_em = Column(DateTime, default=agora, onupdate=agora)


class StatusRequerimento(str, enum.Enum):
    aguardando = "aguardando"
    aprovado   = "aprovado"
    rejeitado  = "rejeitado"


class Requerimento(Base):
    __tablename__ = "requerimentos"
    id            = Column(Integer, primary_key=True, index=True)
    titulo        = Column(String(200), nullable=False)
    status        = Column(Enum(StatusRequerimento), default=StatusRequerimento.aguardando)
    criado_por    = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    aprovado_por  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    observacao    = Column(Text, nullable=True)
    criado_em     = Column(DateTime, default=agora)
    atualizado_em = Column(DateTime, default=agora, onupdate=agora)
    criador   = relationship("Usuario", foreign_keys=[criado_por])
    aprovador = relationship("Usuario", foreign_keys=[aprovado_por])
    itens     = relationship("ItemRequerimento", back_populates="requerimento", cascade="all, delete-orphan")


class ItemRequerimento(Base):
    __tablename__ = "requerimentos_itens"
    id              = Column(Integer, primary_key=True, index=True)
    requerimento_id = Column(Integer, ForeignKey("requerimentos.id", ondelete="CASCADE"), nullable=False)
    nome            = Column(String(200), nullable=False)
    quantidade      = Column(Float, nullable=False, default=1.0)
    valor           = Column(Float, nullable=False)
    requerimento    = relationship("Requerimento", back_populates="itens")


class StatusSolicitacao(str, enum.Enum):
    aguardando = "aguardando"
    aprovado   = "aprovado"
    rejeitado  = "rejeitado"


class SolicitacaoEstoque(Base):
    __tablename__ = "solicitacoes_estoque"
    id            = Column(Integer, primary_key=True, index=True)
    material_id   = Column(Integer, ForeignKey("materiais.id"), nullable=False)
    ativo_id      = Column(Integer, ForeignKey("ativos.id"), nullable=True)
    unidade_id    = Column(Integer, ForeignKey("unidades_patrimonio.id"), nullable=True)
    quantidade    = Column(Float, nullable=False, default=1.0)
    motivo        = Column(Text, nullable=False)
    status        = Column(Enum(StatusSolicitacao), default=StatusSolicitacao.aguardando)
    criado_por    = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    decidido_por  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    observacao    = Column(Text, nullable=True)
    criado_em     = Column(DateTime, default=agora)
    atualizado_em = Column(DateTime, default=agora, onupdate=agora)
    material   = relationship("Material",         foreign_keys=[material_id])
    ativo      = relationship("Ativo",            foreign_keys=[ativo_id])
    unidade    = relationship("UnidadePatrimonio", foreign_keys=[unidade_id])
    criador    = relationship("Usuario",          foreign_keys=[criado_por])
    decididor  = relationship("Usuario",          foreign_keys=[decidido_por])


class NfeImportada(Base):
    """
    Registro de NF-e já importadas.
    A chave de acesso (44 dígitos) é o identificador único nacional de cada NF-e,
    usado como chave primária para impedir importações duplicadas.
    """
    __tablename__ = "nfe_importadas"
    chave        = Column(String(44), primary_key=True)   # chave de acesso SEFAZ
    nf_numero    = Column(String(20),  nullable=True)
    emitente     = Column(String(200), nullable=True)
    usuario_id   = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    importado_em = Column(DateTime, default=agora)
