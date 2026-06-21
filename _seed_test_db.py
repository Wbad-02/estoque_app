# © Wbad-02 — Todos os direitos reservados.
# github.com/Wbad-02
"""
Seed de banco de dados para testes.
Cria categorias, grupos, materiais, movimentações, ativos e demais entidades
com dados fictícios realistas para um almoxarifado de TI.

Uso: python _seed_test_db.py
"""
from database import engine, SessionLocal, Base
from auth import hash_senha
from models import (
    Usuario, GrupoPermissao,
    Categoria, GrupoMaterial, Material, Movimentacao,
    UnidadePatrimonio, StatusUnidade,
    AtivoCategoria, AtivoGrupo, Ativo, AtivoItem,
    MotivoPersonalizado,
    Requerimento, ItemRequerimento, StatusRequerimento,
    SolicitacaoEstoque, StatusSolicitacao,
    NotificacaoEmail, NotificacaoTemplate,
    agora,
)
from datetime import timedelta

Base.metadata.create_all(bind=engine)
db = SessionLocal()

_agora = agora()


def ts(dias_atras: int = 0):
    return _agora - timedelta(days=dias_atras)


# ── Usuários ──────────────────────────────────────────────────
usuarios = [
    Usuario(nome="Administrador", email="admin@estoque.local",
            senha_hash=hash_senha("admin123"), grupo=GrupoPermissao.admin, criado_em=ts(90)),
    Usuario(nome="Carlos Editor", email="carlos@teste.local",
            senha_hash=hash_senha("teste123"), grupo=GrupoPermissao.editor, criado_em=ts(60)),
    Usuario(nome="Ana Financeiro", email="ana@teste.local",
            senha_hash=hash_senha("teste123"), grupo=GrupoPermissao.financeiro, criado_em=ts(45)),
    Usuario(nome="João Viewer", email="joao@teste.local",
            senha_hash=hash_senha("teste123"), grupo=GrupoPermissao.viewer, criado_em=ts(30)),
]
db.add_all(usuarios)
db.flush()

admin, carlos, ana, joao = usuarios

# ── Motivos Personalizados ────────────────────────────────────
motivos = [
    MotivoPersonalizado(nome="Manutenção preventiva"),
    MotivoPersonalizado(nome="Substituição por garantia"),
    MotivoPersonalizado(nome="Empréstimo temporário"),
]
db.add_all(motivos)

# ── Categorias + Grupos + Materiais (Estoque) ────────────────
cat_info = Categoria(nome="Informática", descricao="Equipamentos e periféricos de TI", criado_em=ts(80))
cat_escrit = Categoria(nome="Escritório", descricao="Material de escritório e papelaria", criado_em=ts(80))
cat_rede = Categoria(nome="Rede e Infraestrutura", descricao="Cabos, switches, roteadores", criado_em=ts(75))
cat_limpeza = Categoria(nome="Limpeza", descricao="Produtos de limpeza e higiene", criado_em=ts(70))
db.add_all([cat_info, cat_escrit, cat_rede, cat_limpeza])
db.flush()

# Grupos dentro de cada categoria
grp_computadores = GrupoMaterial(nome="Computadores", categoria_id=cat_info.id,
                                  quantidade_minima=3, criado_em=ts(78))
grp_perifericos = GrupoMaterial(nome="Periféricos", categoria_id=cat_info.id,
                                 quantidade_minima=5, criado_em=ts(78))
grp_monitores = GrupoMaterial(nome="Monitores", categoria_id=cat_info.id,
                               quantidade_minima=2, criado_em=ts(78))
grp_papel = GrupoMaterial(nome="Papel e Impressão", categoria_id=cat_escrit.id,
                           quantidade_minima=10, criado_em=ts(75))
grp_canetas = GrupoMaterial(nome="Canetas e Marcadores", categoria_id=cat_escrit.id,
                             quantidade_minima=20, criado_em=ts(75))
grp_cabos = GrupoMaterial(nome="Cabos", categoria_id=cat_rede.id,
                           quantidade_minima=15, criado_em=ts(70))
grp_equiprede = GrupoMaterial(nome="Equipamentos de Rede", categoria_id=cat_rede.id,
                               quantidade_minima=2, criado_em=ts(70))
grp_limpeza = GrupoMaterial(nome="Produtos Gerais", categoria_id=cat_limpeza.id,
                             quantidade_minima=5, criado_em=ts(65))

db.add_all([grp_computadores, grp_perifericos, grp_monitores,
            grp_papel, grp_canetas, grp_cabos, grp_equiprede, grp_limpeza])
db.flush()

# Materiais
materiais_dados = [
    # Computadores (com patrimônio)
    dict(nome="Notebook Dell Latitude 5540", descricao="i7 13ª gen, 16GB RAM, 512GB SSD",
         quantidade=5, unidade="un", grupo_id=grp_computadores.id, usa_patrimonio=True,
         valor_unitario=5200.00, tag="novo", fator_embalagem=1.0, criado_em=ts(60)),
    dict(nome="Desktop HP ProDesk 400 G9", descricao="i5 12ª gen, 8GB RAM, 256GB SSD",
         quantidade=3, unidade="un", grupo_id=grp_computadores.id, usa_patrimonio=True,
         valor_unitario=3800.00, tag="novo", fator_embalagem=1.0, criado_em=ts(55)),

    # Periféricos
    dict(nome="Teclado Logitech K120", quantidade=12, unidade="un",
         grupo_id=grp_perifericos.id, valor_unitario=79.90, tag="novo", criado_em=ts(50)),
    dict(nome="Mouse Logitech M190", quantidade=15, unidade="un",
         grupo_id=grp_perifericos.id, valor_unitario=49.90, tag="novo", criado_em=ts(50)),
    dict(nome="Headset Plantronics HW510", quantidade=4, unidade="un",
         grupo_id=grp_perifericos.id, valor_unitario=320.00, tag="usado", criado_em=ts(40)),
    dict(nome="Webcam Logitech C920", quantidade=6, unidade="un",
         grupo_id=grp_perifericos.id, valor_unitario=280.00, tag="novo", criado_em=ts(35)),

    # Monitores (com patrimônio)
    dict(nome="Monitor LG 24'' IPS Full HD", descricao="24MK430H, HDMI/VGA",
         quantidade=8, unidade="un", grupo_id=grp_monitores.id, usa_patrimonio=True,
         valor_unitario=890.00, tag="novo", criado_em=ts(50)),
    dict(nome="Monitor Samsung 27'' Curvo", descricao="LC27F390, Full HD",
         quantidade=2, unidade="un", grupo_id=grp_monitores.id, usa_patrimonio=True,
         valor_unitario=1350.00, tag="usado", criado_em=ts(30)),

    # Papel e Impressão
    dict(nome="Resma Papel A4 Chamex 500fls", quantidade=45, unidade="resma",
         grupo_id=grp_papel.id, valor_unitario=28.90, fator_embalagem=10.0, criado_em=ts(40)),
    dict(nome="Toner HP CF258A", descricao="Compatível HP LaserJet Pro M404",
         quantidade=8, unidade="un", grupo_id=grp_papel.id, valor_unitario=189.00, criado_em=ts(35)),
    dict(nome="Cartucho HP 664 Preto", quantidade=6, unidade="un",
         grupo_id=grp_papel.id, valor_unitario=59.90, criado_em=ts(30)),

    # Canetas
    dict(nome="Caneta BIC Cristal Azul", quantidade=50, unidade="un",
         grupo_id=grp_canetas.id, valor_unitario=1.80, fator_embalagem=50.0, criado_em=ts(45)),
    dict(nome="Marcador para Quadro Branco", quantidade=24, unidade="un",
         grupo_id=grp_canetas.id, valor_unitario=5.50, criado_em=ts(40)),
    dict(nome="Pincel Atômico Preto", quantidade=12, unidade="un",
         grupo_id=grp_canetas.id, valor_unitario=4.20, criado_em=ts(38)),

    # Cabos
    dict(nome="Cabo de Rede Cat6 2m", quantidade=30, unidade="un",
         grupo_id=grp_cabos.id, valor_unitario=12.90, criado_em=ts(50)),
    dict(nome="Cabo HDMI 1.8m", quantidade=10, unidade="un",
         grupo_id=grp_cabos.id, valor_unitario=24.90, criado_em=ts(45)),
    dict(nome="Cabo USB-C para USB-A 1m", quantidade=20, unidade="un",
         grupo_id=grp_cabos.id, valor_unitario=19.90, criado_em=ts(40)),
    dict(nome="Extensão Elétrica 3m 3 tomadas", quantidade=8, unidade="un",
         grupo_id=grp_cabos.id, valor_unitario=35.00, criado_em=ts(35)),

    # Equipamentos de Rede (com patrimônio)
    dict(nome="Switch TP-Link 24 portas Gigabit", descricao="TL-SG1024D",
         quantidade=3, unidade="un", grupo_id=grp_equiprede.id, usa_patrimonio=True,
         valor_unitario=650.00, tag="novo", criado_em=ts(60)),
    dict(nome="Roteador Wi-Fi 6 TP-Link AX1500", descricao="Archer AX12",
         quantidade=2, unidade="un", grupo_id=grp_equiprede.id, usa_patrimonio=True,
         valor_unitario=380.00, tag="novo", criado_em=ts(50)),

    # Limpeza
    dict(nome="Álcool Isopropílico 1L", quantidade=6, unidade="L",
         grupo_id=grp_limpeza.id, valor_unitario=32.00, criado_em=ts(30)),
    dict(nome="Flanela Antiestática (pacote 5un)", quantidade=4, unidade="pct",
         grupo_id=grp_limpeza.id, valor_unitario=18.00, criado_em=ts(30)),
    dict(nome="Spray Limpa Contato 300ml", quantidade=3, unidade="un",
         grupo_id=grp_limpeza.id, valor_unitario=27.50, criado_em=ts(25)),
]

materiais = []
for dados in materiais_dados:
    m = Material(**dados)
    materiais.append(m)
db.add_all(materiais)
db.flush()

# ── Unidades de Patrimônio (para materiais com usa_patrimonio) ─
unidades = []
patrimonio_counter = {}
for mat in materiais:
    if not mat.usa_patrimonio:
        continue
    prefix = mat.nome[:3].upper().replace(" ", "")
    patrimonio_counter.setdefault(prefix, 0)
    for i in range(int(mat.quantidade)):
        patrimonio_counter[prefix] += 1
        cod = f"TI-{prefix}-{patrimonio_counter[prefix]:03d}"
        u = UnidadePatrimonio(
            material_id=mat.id, codigo=cod,
            status=StatusUnidade.ativo, origem="manual",
            valor_unitario=mat.valor_unitario,
            tag=mat.tag, criado_em=mat.criado_em,
        )
        unidades.append(u)
db.add_all(unidades)
db.flush()

# ── Movimentações (entradas e saídas) ─────────────────────────
movimentacoes = []

for mat in materiais:
    movimentacoes.append(Movimentacao(
        material_id=mat.id, usuario_id=admin.id,
        tipo="entrada", quantidade=mat.quantidade,
        observacao="Entrada inicial de estoque",
        valor_unitario=mat.valor_unitario, tag=mat.tag,
        criado_em=mat.criado_em,
    ))

saidas = [
    (materiais[0], 1, "colaborador", "Entregue para novo funcionário - Depto Financeiro"),
    (materiais[2], 3, "colaborador", "Teclados para sala de reunião"),
    (materiais[3], 2, "defeito", "Mouse com clique duplo involuntário"),
    (materiais[6], 2, "colaborador", "Monitores para home office"),
    (materiais[8], 5, "colaborador", "Resmas para impressora do RH"),
    (materiais[9], 2, "colaborador", "Toner para impressora recepção"),
    (materiais[11], 10, "colaborador", "Canetas para sala de treinamento"),
    (materiais[14], 5, "colaborador", "Cabos de rede para novo andar"),
    (materiais[16], 4, "colaborador", "Cabos USB-C para notebooks novos"),
    (materiais[20], 2, "colaborador", "Limpeza dos equipamentos do CPD"),
]

for mat, qtd, motivo, obs in saidas:
    movimentacoes.append(Movimentacao(
        material_id=mat.id, usuario_id=carlos.id,
        tipo="saida", quantidade=qtd,
        motivo=motivo, observacao=obs,
        criado_em=ts(max(0, 15)),
    ))
    mat.quantidade -= qtd

db.add_all(movimentacoes)
db.flush()

# ── Ativos (Categorias + Grupos + Ativos) ─────────────────────
ativo_cat_depto = AtivoCategoria(nome="Departamentos", descricao="Setores da empresa", criado_em=ts(70))
ativo_cat_colab = AtivoCategoria(nome="Colaboradores", descricao="Funcionários ativos", criado_em=ts(70))
db.add_all([ativo_cat_depto, ativo_cat_colab])
db.flush()

ativo_grp_ti = AtivoGrupo(nome="TI", categoria_id=ativo_cat_depto.id, criado_em=ts(65))
ativo_grp_rh = AtivoGrupo(nome="RH", categoria_id=ativo_cat_depto.id, criado_em=ts(65))
ativo_grp_fin = AtivoGrupo(nome="Financeiro", categoria_id=ativo_cat_depto.id, criado_em=ts(65))
ativo_grp_devs = AtivoGrupo(nome="Desenvolvedores", categoria_id=ativo_cat_colab.id, criado_em=ts(60))
ativo_grp_admin_colab = AtivoGrupo(nome="Administrativo", categoria_id=ativo_cat_colab.id, criado_em=ts(60))
db.add_all([ativo_grp_ti, ativo_grp_rh, ativo_grp_fin, ativo_grp_devs, ativo_grp_admin_colab])
db.flush()

ativo_maria = Ativo(nome="Maria Silva", descricao="Desenvolvedora Pleno", grupo_id=ativo_grp_devs.id, criado_em=ts(50))
ativo_pedro = Ativo(nome="Pedro Santos", descricao="Analista de RH", grupo_id=ativo_grp_rh.id, criado_em=ts(50))
ativo_lucia = Ativo(nome="Lúcia Ferreira", descricao="Coordenadora Financeira", grupo_id=ativo_grp_fin.id, criado_em=ts(45))
ativo_rafael = Ativo(nome="Rafael Costa", descricao="Desenvolvedor Junior", grupo_id=ativo_grp_devs.id, criado_em=ts(40))
ativo_sala_ti = Ativo(nome="Sala TI", descricao="Sala do departamento de TI", grupo_id=ativo_grp_ti.id, criado_em=ts(60))
db.add_all([ativo_maria, ativo_pedro, ativo_lucia, ativo_rafael, ativo_sala_ti])
db.flush()

# Atribuições de itens a ativos
atribuicoes = [
    AtivoItem(ativo_id=ativo_maria.id, material_id=materiais[0].id,
              unidade_id=unidades[0].id, quantidade=1,
              observacao="Notebook principal", atribuido_em=ts(40)),
    AtivoItem(ativo_id=ativo_maria.id, material_id=materiais[6].id,
              unidade_id=unidades[8].id, quantidade=1,
              observacao="Monitor externo", atribuido_em=ts(40)),
    AtivoItem(ativo_id=ativo_pedro.id, material_id=materiais[1].id,
              unidade_id=unidades[5].id, quantidade=1,
              observacao="Desktop de trabalho", atribuido_em=ts(35)),
    AtivoItem(ativo_id=ativo_lucia.id, material_id=materiais[0].id,
              unidade_id=unidades[1].id, quantidade=1,
              observacao="Notebook para reuniões externas", atribuido_em=ts(30)),
    AtivoItem(ativo_id=ativo_rafael.id, material_id=materiais[0].id,
              unidade_id=unidades[2].id, quantidade=1,
              observacao="Notebook dev", atribuido_em=ts(20)),
    AtivoItem(ativo_id=ativo_sala_ti.id, material_id=materiais[18].id,
              unidade_id=unidades[16].id, quantidade=1,
              observacao="Switch principal do rack", atribuido_em=ts(55)),
]
db.add_all(atribuicoes)
db.flush()

for item in atribuicoes:
    if item.unidade_id:
        u = db.query(UnidadePatrimonio).get(item.unidade_id)
        if u:
            u.tag = "atribuido"

# ── Requerimentos de Compra ───────────────────────────────────
req1 = Requerimento(
    titulo="Compra de SSDs para upgrade", status=StatusRequerimento.aprovado,
    criado_por=carlos.id, aprovado_por=admin.id,
    observacao="Aprovado — upgrade necessário para o time de dev",
    criado_em=ts(20), atualizado_em=ts(18),
)
req2 = Requerimento(
    titulo="Cadeiras ergonômicas para TI", status=StatusRequerimento.aguardando,
    criado_por=ana.id,
    observacao="Solicitação do RH após avaliação ergonômica",
    criado_em=ts(5),
)
req3 = Requerimento(
    titulo="Licenças Microsoft 365 Business", status=StatusRequerimento.rejeitado,
    criado_por=carlos.id, aprovado_por=admin.id,
    observacao="Rejeitado — já temos contrato ativo até dez/2026",
    criado_em=ts(25), atualizado_em=ts(22),
)
db.add_all([req1, req2, req3])
db.flush()

itens_req = [
    ItemRequerimento(requerimento_id=req1.id, nome="SSD NVMe Kingston 1TB",
                     quantidade=5, valor=389.90),
    ItemRequerimento(requerimento_id=req1.id, nome="Adaptador M.2 para Desktop",
                     quantidade=3, valor=45.00),
    ItemRequerimento(requerimento_id=req2.id, nome="Cadeira Ergonômica Flexform Uni",
                     quantidade=4, valor=1890.00),
    ItemRequerimento(requerimento_id=req3.id, nome="Microsoft 365 Business Standard (anual)",
                     quantidade=15, valor=540.00),
]
db.add_all(itens_req)

# ── Solicitações de Estoque ───────────────────────────────────
sol1 = SolicitacaoEstoque(
    material_id=materiais[2].id, ativo_id=ativo_rafael.id,
    quantidade=1, motivo="Teclado novo para estação de trabalho",
    status=StatusSolicitacao.aprovado,
    criado_por=joao.id, decidido_por=carlos.id,
    observacao="Aprovado e entregue",
    criado_em=ts(10), atualizado_em=ts(9),
)
sol2 = SolicitacaoEstoque(
    material_id=materiais[4].id,
    quantidade=1, motivo="Headset para reuniões remotas",
    status=StatusSolicitacao.aguardando,
    criado_por=joao.id,
    criado_em=ts(2),
)
db.add_all([sol1, sol2])

# ── Notificações por E-mail ──────────────────────────────────
notifs = [
    NotificacaoEmail(email="ti@empresa.local", tipo="retirada", ativo=True),
    NotificacaoEmail(email="ti@empresa.local", tipo="alerta", ativo=True, intervalo_dias=7),
    NotificacaoEmail(email="compras@empresa.local", tipo="alerta", ativo=True, intervalo_dias=3),
]
db.add_all(notifs)

# ── Templates de E-mail ──────────────────────────────────────
templates = [
    NotificacaoTemplate(
        tipo="retirada",
        assunto="Retirada de material: {material}",
        corpo="Material: {material}\nQuantidade: {quantidade}\nResponsável: {usuario}\nMotivo: {motivo}\nData: {data}",
    ),
    NotificacaoTemplate(
        tipo="entrada",
        assunto="Entrada de material: {material}",
        corpo="Material: {material}\nQuantidade: {quantidade}\nResponsável: {usuario}\nData: {data}",
    ),
    NotificacaoTemplate(
        tipo="alerta",
        assunto="Alerta de estoque mínimo",
        corpo="Os seguintes materiais estão abaixo do estoque mínimo:\n\n{itens}",
    ),
    NotificacaoTemplate(
        tipo="requerimento",
        assunto="Novo requerimento de compra: {titulo}",
        corpo="Titulo: {titulo}\nCriado por: {criador}\nItens: {itens_count}\nTotal: {total}\n\nAcesse para aprovar: {link}",
    ),
    NotificacaoTemplate(
        tipo="requerimento_decisao",
        assunto="Requerimento '{titulo}' foi {status}",
        corpo="Titulo: {titulo}\nStatus: {status}\nDecisao por: {aprovador}\nObservacao: {observacao}",
    ),
    NotificacaoTemplate(
        tipo="solicitacao",
        assunto="Nova solicitação de estoque: {material}",
        corpo="Material: {material}\nQuantidade: {quantidade}\nSolicitante: {criador}\nMotivo: {motivo}\nData: {data}",
    ),
    NotificacaoTemplate(
        tipo="solicitacao_decisao",
        assunto="Solicitação de '{material}' foi {status}",
        corpo="Material: {material}\nStatus: {status}\nDecidido por: {decididor}\nObservação: {observacao}",
    ),
]
db.add_all(templates)

# ── Commit final ──────────────────────────────────────────────
db.commit()
db.close()

print("=" * 60)
print("  Banco de testes criado com sucesso!")
print("=" * 60)
print()
print("  Usuários:")
print("    admin@estoque.local  / admin123  (admin)")
print("    carlos@teste.local   / teste123  (editor)")
print("    ana@teste.local      / teste123  (financeiro)")
print("    joao@teste.local     / teste123  (viewer)")
print()
print(f"  Categorias: 4")
print(f"  Grupos: 8")
print(f"  Materiais: {len(materiais)}")
print(f"  Unidades patrimônio: {len(unidades)}")
print(f"  Movimentações: {len(movimentacoes) + len(saidas)}")
print(f"  Ativos: 5 (3 colaboradores + 1 sala + 1 departamento)")
print(f"  Requerimentos: 3")
print(f"  Solicitações: 2")
print()
print("  Pronto para usar: python -m uvicorn main:app --port 8000")
print("=" * 60)
