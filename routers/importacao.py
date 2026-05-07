# © Todos os direitos reservados – github.com/Wbad-02
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_admin, registrar_log
import models

router = APIRouter(prefix="/api/importacao", tags=["importacao"])

# Namespace padrão NF-e 4.00
NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


def _txt(el, path: str, ns=NS) -> str:
    """Retorna texto de um subelemento ou string vazia."""
    node = el.find(path, ns)
    return node.text.strip() if node is not None and node.text else ""


def _extrair_chave(root) -> str:
    """
    Extrai a chave de acesso de 44 dígitos da NF-e.
    Tenta primeiro no protNFe/infProt/chNFe (mais confiável),
    depois no atributo Id de infNFe (sem o prefixo 'NFe').
    """
    # 1. Envelope processado: chNFe dentro de protNFe
    chave = _txt(root, ".//nfe:protNFe/nfe:infProt/nfe:chNFe")
    if chave and len(chave) == 44:
        return chave

    # 2. Atributo Id do infNFe (formato: "NFe" + 44 dígitos)
    inf = root.find(".//nfe:infNFe", NS)
    if inf is not None:
        id_attr = inf.get("Id", "")
        if id_attr.startswith("NFe") and len(id_attr) == 47:
            return id_attr[3:]  # remove prefixo "NFe"

    return ""


def _parse_nfe(xml_bytes: bytes) -> dict:
    """
    Extrai do XML NF-e 4.00:
      - chave de acesso (44 dígitos)
      - dados do emitente
      - lista de itens (det)
    Retorna dict com 'chave', 'emitente', 'nf_numero', 'nf_data' e 'itens'.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise HTTPException(400, f"XML inválido: {e}")

    chave = _extrair_chave(root)
    if not chave:
        raise HTTPException(400, "Chave de acesso não encontrada no XML")

    # Suporte a envelope nfeProc ou NFe direto
    nfe = root.find(".//nfe:NFe", NS) or root
    inf = nfe.find("nfe:infNFe", NS)
    if inf is None:
        raise HTTPException(400, "Estrutura de NF-e não reconhecida (infNFe não encontrado)")

    # Emitente
    emit = inf.find("nfe:emit", NS)
    emitente = {
        "cnpj":  _txt(emit, "nfe:CNPJ"),
        "nome":  _txt(emit, "nfe:xNome"),
    } if emit is not None else {"cnpj": "", "nome": "Desconhecido"}

    # NF número + data
    ide = inf.find("nfe:ide", NS)
    nf_num  = _txt(ide, "nfe:nNF")   if ide is not None else ""
    nf_data = _txt(ide, "nfe:dhEmi")[:10] if ide is not None else ""

    # Itens
    itens = []
    for det in inf.findall("nfe:det", NS):
        prod = det.find("nfe:prod", NS)
        if prod is None:
            continue
        itens.append({
            "codigo":     _txt(prod, "nfe:cProd"),
            "nome":       _txt(prod, "nfe:xProd"),
            "quantidade": float(_txt(prod, "nfe:qCom") or "0"),
            "unidade":    _txt(prod, "nfe:uCom").lower() or "un",
            "valor_unit": float(_txt(prod, "nfe:vUnCom") or "0"),
        })

    if not itens:
        raise HTTPException(422, "Nenhum item (det) encontrado no XML")

    return {
        "chave":     chave,
        "emitente":  emitente,
        "nf_numero": nf_num,
        "nf_data":   nf_data,
        "itens":     itens,
    }


@router.post("/preview")
async def preview_xml(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    """
    Recebe o XML, faz o parse e devolve os itens para revisão.
    Também informa se a NF-e já foi importada anteriormente.
    Não grava nada no banco.
    """
    conteudo = await arquivo.read()
    dados = _parse_nfe(conteudo)

    ja_importada = db.query(models.NfeImportada).filter(
        models.NfeImportada.chave == dados["chave"]
    ).first()

    return {
        **dados,
        "ja_importada": ja_importada is not None,
        "importado_em": ja_importada.importado_em.isoformat() if ja_importada else None,
    }


@router.post("/confirmar")
async def confirmar_importacao(
    arquivo:  UploadFile = File(...),
    grupo_id: int = 0,
    db:       Session = Depends(get_db),
    atual:    models.Usuario = Depends(requer_admin),
):
    """
    Importa TODOS os itens do XML para o banco (suporta NF-e com múltiplos produtos).
    - Rejeita com 409 se a chave de acesso já foi importada.
    - Por item: soma quantidade se material já existir no grupo, cria se não existir.
    - Registra movimentação de entrada para cada item importado.
    - Salva a chave de acesso para impedir reimportação.
    """
    if not grupo_id:
        raise HTTPException(400, "Informe o grupo_id de destino")

    grupo = db.query(models.GrupoMaterial).filter(
        models.GrupoMaterial.id == grupo_id
    ).first()
    if not grupo:
        raise HTTPException(404, "Grupo não encontrado")

    conteudo = await arquivo.read()
    dados    = _parse_nfe(conteudo)

    # ── Verificar duplicata pela chave de acesso ────────────────────────────
    ja_importada = db.query(models.NfeImportada).filter(
        models.NfeImportada.chave == dados["chave"]
    ).first()
    if ja_importada:
        raise HTTPException(
            409,
            f"NF-e já importada anteriormente "
            f"(chave: {dados['chave']}, "
            f"em: {ja_importada.importado_em.strftime('%d/%m/%Y %H:%M')})"
        )

    criados     = []
    atualizados = []

    for item in dados["itens"]:
        nome_norm = item["nome"].strip()
        qtd       = item["quantidade"]

        existente = db.query(models.Material).filter(
            models.Material.grupo_id == grupo_id,
            models.Material.ativo    == True,
            models.Material.nome.ilike(nome_norm),
        ).first()

        valor_unit = item["valor_unit"]

        if existente:
            existente.quantidade += qtd
            if not existente.valor_unitario:
                existente.valor_unitario = valor_unit
            db.flush()
            mat = existente
            atualizados.append({"nome": mat.nome, "qtd_adicionada": qtd})
        else:
            mat = models.Material(
                nome=nome_norm,
                descricao=f"Cód: {item['codigo']} | NF-e {dados['nf_numero']} ({dados['nf_data']})",
                quantidade=qtd,
                unidade=item["unidade"].lower() or "un",
                grupo_id=grupo_id,
                valor_unitario=valor_unit,
            )
            db.add(mat)
            db.flush()
            criados.append({"nome": mat.nome, "qtd": qtd})

        mov = models.Movimentacao(
            material_id=mat.id,
            usuario_id=atual.id,
            tipo="entrada",
            quantidade=qtd,
            valor_unitario=valor_unit,
            observacao=f"NF-e {dados['nf_numero']} | {dados['emitente']['nome']}",
        )
        db.add(mov)
        db.flush()

        if mat.usa_patrimonio:
            for i in range(int(qtd)):
                uni = models.UnidadePatrimonio(
                    material_id=mat.id,
                    status=models.StatusUnidade.ativo,
                    origem="xml",
                    nf_numero=dados["nf_numero"],
                    observacao=f"{dados['emitente']['nome']} — item {i+1}/{int(qtd)}",
                    valor_unitario=valor_unit,
                    tag="novo",
                    movimentacao_saida_id=None,
                )
                db.add(uni)

    # ── Registrar chave para impedir reimportação ───────────────────────────
    db.add(models.NfeImportada(
        chave=dados["chave"],
        nf_numero=dados["nf_numero"],
        emitente=dados["emitente"]["nome"],
        usuario_id=atual.id,
    ))

    db.commit()

    registrar_log(
        db, atual.id, "importar", "nfe", None,
        f"NF-e {dados['nf_numero']} | chave {dados['chave']} | "
        f"{dados['emitente']['nome']} | "
        f"criados={len(criados)} atualizados={len(atualizados)} itens={len(dados['itens'])}"
    )

    return {
        "sucesso":     True,
        "chave":       dados["chave"],
        "emitente":    dados["emitente"]["nome"],
        "nf_numero":   dados["nf_numero"],
        "total_itens": len(dados["itens"]),
        "criados":     [i["nome"] for i in criados],
        "atualizados": [i["nome"] for i in atualizados],
        "total":       len(criados) + len(atualizados),
    }


@router.get("/historico")
def historico_nfe(
    db:   Session = Depends(get_db),
    _:    models.Usuario = Depends(requer_admin),
):
    """Lista todas as NF-e já importadas, da mais recente para a mais antiga."""
    registros = (
        db.query(models.NfeImportada)
        .order_by(models.NfeImportada.importado_em.desc())
        .all()
    )
    return [
        {
            "chave":        r.chave,
            "nf_numero":    r.nf_numero,
            "emitente":     r.emitente,
            "importado_em": r.importado_em.strftime("%d/%m/%Y %H:%M"),
        }
        for r in registros
    ]
