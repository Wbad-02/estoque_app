# © Todos os direitos reservados – github.com/Wbad-02
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_editor_ou_admin, registrar_log
import models

router = APIRouter(prefix="/api/importacao", tags=["importacao"])

# Namespace padrão NF-e 4.00
NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


def _txt(el, path: str, ns=NS) -> str:
    """Retorna texto de um subelemento ou string vazia."""
    node = el.find(path, ns)
    return node.text.strip() if node is not None and node.text else ""


def _parse_nfe(xml_bytes: bytes) -> dict:
    """
    Extrai do XML NF-e 4.00:
      - dados do emitente
      - lista de itens (det)
    Retorna dict com 'emitente' e 'itens'.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise HTTPException(400, f"XML inválido: {e}")

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
    nf_num  = _txt(ide, "nfe:nNF")  if ide is not None else ""
    nf_data = _txt(ide, "nfe:dhEmi")[:10] if ide is not None else ""

    # Itens
    itens = []
    for det in inf.findall("nfe:det", NS):
        prod = det.find("nfe:prod", NS)
        if prod is None:
            continue
        itens.append({
            "codigo":    _txt(prod, "nfe:cProd"),
            "nome":      _txt(prod, "nfe:xProd"),
            "quantidade": float(_txt(prod, "nfe:qCom") or "0"),
            "unidade":   _txt(prod, "nfe:uCom").lower() or "un",
            "valor_unit": float(_txt(prod, "nfe:vUnCom") or "0"),
        })

    if not itens:
        raise HTTPException(422, "Nenhum item (det) encontrado no XML")

    return {
        "emitente": emitente,
        "nf_numero": nf_num,
        "nf_data":   nf_data,
        "itens":     itens,
    }


@router.post("/preview")
async def preview_xml(
    arquivo: UploadFile = File(...),
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    """
    Recebe o XML, faz o parse e devolve os itens para o usuário
    revisar antes de confirmar o cadastro.
    Não grava nada no banco.
    """
    conteudo = await arquivo.read()
    return _parse_nfe(conteudo)


@router.post("/confirmar")
async def confirmar_importacao(
    arquivo:  UploadFile = File(...),
    grupo_id: int = 0,
    db:       Session = Depends(get_db),
    atual:    models.Usuario = Depends(requer_editor_ou_admin),
):
    """
    Importa TODOS os itens do XML para o banco (suporta NF-e com múltiplos produtos).
    - Por item: soma quantidade se material já existir no grupo, cria se não existir.
    - Registra movimentação de entrada para cada item importado.
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

        # Registrar movimentação de ENTRADA para rastreabilidade
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

        # Se material usa patrimônio, criar unidades individuais com origem=xml
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

    db.commit()

    registrar_log(
        db, atual.id, "importar", "nfe", None,
        f"NF-e {dados['nf_numero']} | {dados['emitente']['nome']} | "
        f"criados={len(criados)} atualizados={len(atualizados)} itens={len(dados['itens'])}"
    )

    return {
        "sucesso":     True,
        "emitente":    dados["emitente"]["nome"],
        "nf_numero":   dados["nf_numero"],
        "total_itens": len(dados["itens"]),
        "criados":     [i["nome"] for i in criados],
        "atualizados": [i["nome"] for i in atualizados],
        "total":       len(criados) + len(atualizados),
    }
