"""Leitura automática de talões de supermercado (fotografia ou PDF).

Como funciona:
1. A imagem é endireitada e reduzida (Pillow, que já vem com o Streamlit). Talões compridos são
   partidos em várias partes com sobreposição, para as letras continuarem legíveis.
2. As imagens (ou o PDF) vão para a API gratuita do Google Gemini (Google AI Studio), que devolve
   JSON estruturado: loja, data e, para cada artigo, o texto do talão, um nome claro e a quantidade.
   Só se usa a biblioteca `requests`; não é preciso instalar mais nada. Se o modelo escolhido não
   estiver disponível ou tiver esgotado a quota gratuita, tenta automaticamente o seguinte da lista.
3. Cada linha é associada a um produto que a casa já tem, por esta ordem:
   a) memória: o mesmo texto de talão já foi associado antes (aprende com as correções);
   b) a sugestão do modelo, se indicar exatamente um produto da casa;
   c) semelhança de nomes, depois de expandir abreviaturas (ex.: «LEITE MIMOSA M/G 1L»
      ↔ «Leite meio-gordo Mimosa»);
   d) caso contrário, é um produto novo com o nome claro sugerido.
4. A utilizadora revê tudo numa tabela antes de gravar.
"""
from __future__ import annotations

import base64
import io
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

import casa

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
MODELO_PADRAO = "gemini-3.8-flash"
# Alternativas, por ordem, se o modelo escolhido não existir para esta chave ou esgotar a quota gratuita
MODELOS_ALTERNATIVOS = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
MAX_PDF = 14 * 1024 * 1024  # o pedido inteiro (em base64) tem de ficar abaixo de 20 MB
MAX_IMAGEM_ORIGINAL = 25 * 1024 * 1024
LARGURA_MAX = 1200        # píxeis
ALTURA_PARTE = 1.4        # cada parte tem no máximo 1,4 × a largura
SOBREPOSICAO = 0.08
MAX_PARTES = 5
LIMIAR_SEMELHANCA = 0.7

TIPOS_IMAGEM = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class ErroLeitura(Exception):
    """Erro com mensagem já pronta para mostrar à utilizadora."""


# ---------------------------------------------------------------- preparar ficheiro
def _tipo(nome: str, mime: str | None) -> str:
    mime = (mime or "").lower()
    n = (nome or "").lower()
    if mime == "application/pdf" or n.endswith(".pdf"):
        return "application/pdf"
    if n.endswith((".heic", ".heif")) or "heic" in mime or "heif" in mime:
        raise ErroLeitura("Fotografias HEIC do iPhone não são suportadas. Em Definições → Câmara → Formatos, "
                          "escolha «Mais compatível», ou envie uma captura de ecrã do talão.")
    if mime in TIPOS_IMAGEM:
        return mime
    if n.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if n.endswith(".png"):
        return "image/png"
    if n.endswith(".webp"):
        return "image/webp"
    raise ErroLeitura("Formato não suportado. Use uma fotografia (JPG/PNG) ou um PDF.")


def _bloco_imagem(dados: bytes, mime: str) -> dict:
    """Parte «inline_data» do Gemini (imagem ou PDF em base64)."""
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(dados).decode("ascii")}}


def partes_imagem(conteudo: bytes) -> list[bytes]:
    """Endireita, reduz e, se o talão for comprido, parte-o em várias imagens JPEG."""
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(conteudo))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        raise ErroLeitura("Não consegui abrir a imagem. Tente outra fotografia.") from e

    if img.width > LARGURA_MAX:
        img = img.resize((LARGURA_MAX, round(img.height * LARGURA_MAX / img.width)), Image.LANCZOS)
    w, h = img.size
    alt = round(w * ALTURA_PARTE)
    if h > alt * MAX_PARTES * (1 - SOBREPOSICAO):  # muito comprido: reduz para caber em MAX_PARTES
        escala = (alt * MAX_PARTES * (1 - SOBREPOSICAO)) / h
        img = img.resize((max(1, round(w * escala)), max(1, round(h * escala))), Image.LANCZOS)
        w, h = img.size
        alt = round(w * ALTURA_PARTE)

    partes, topo = [], 0
    passo = max(1, round(alt * (1 - SOBREPOSICAO)))
    while True:
        fundo = min(topo + alt, h)
        buf = io.BytesIO()
        img.crop((0, topo, w, fundo)).save(buf, "JPEG", quality=85, optimize=True)
        partes.append(buf.getvalue())
        if fundo >= h or len(partes) >= MAX_PARTES:
            break
        topo += passo
    return partes


def preparar_ficheiro(conteudo: bytes, nome: str = "", mime: str | None = None) -> list[dict]:
    """Converte o ficheiro carregado em partes «inline_data» para a API do Gemini."""
    if not conteudo:
        raise ErroLeitura("O ficheiro está vazio.")
    tipo = _tipo(nome, mime)
    if tipo == "application/pdf":
        if len(conteudo) > MAX_PDF:
            raise ErroLeitura("O PDF é demasiado grande (máximo 14 MB).")
        return [_bloco_imagem(conteudo, "application/pdf")]
    if len(conteudo) > MAX_IMAGEM_ORIGINAL:
        raise ErroLeitura("A fotografia é demasiado grande (máximo 25 MB).")
    try:
        return [_bloco_imagem(p, "image/jpeg") for p in partes_imagem(conteudo)]
    except ImportError:  # sem Pillow: envia tal como está, se não for grande demais
        if len(conteudo) > 3_700_000:
            raise ErroLeitura("A fotografia é demasiado grande. Tente uma com menos resolução.") from None
        return [_bloco_imagem(conteudo, tipo)]


# ---------------------------------------------------------------- pedido à API
# JSON Schema da resposta. Sem tipos "null" (data e existente vêm como "" quando não há),
# para funcionar tanto com responseJsonSchema como com modelos mais antigos.
ESQUEMA = {
    "type": "object",
    "properties": {
        "legivel": {"type": "boolean", "description": "false se a imagem não for um talão ou estiver ilegível"},
        "loja": {"type": "string", "description": "Nome da loja/cadeia (ex.: Continente, Pingo Doce, Lidl). Vazio se não souber."},
        "data": {"type": "string", "description": "Data de emissão no formato AAAA-MM-DD, ou vazio."},
        "linhas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Descrição do artigo tal como está no talão, sem preço nem quantidade."},
                    "nome": {"type": "string", "description": "Nome claro em português de Portugal, sem abreviaturas, sem tamanho/peso. Ex.: 'Leite meio-gordo Mimosa'."},
                    "quantidade": {"type": "number", "description": "Unidades compradas. 1 se não for explícito; produtos a peso = 1."},
                    "tipo": {"type": "string", "enum": ["produto", "saco", "outro"]},
                    "existente": {"type": "string", "description": "Nome EXATO de um produto da lista da casa, só se for claramente o mesmo produto; senão vazio."},
                },
                "required": ["texto", "nome", "quantidade", "tipo", "existente"],
            },
        },
    },
    "required": ["legivel", "loja", "data", "linhas"],
}

INSTRUCOES = """És um assistente que lê talões e faturas de supermercados portugueses \
(Continente, Pingo Doce, Lidl, Mercadona, Recheio, Intermarché, Aldi, Minipreço, Auchan, etc.).
Lê o talão e responde APENAS com JSON segundo o esquema pedido. Regras:
- Uma entrada por artigo comprado. Se o mesmo artigo aparecer em várias linhas, junta-as e soma a quantidade.
- Ignora totais, subtotais, IVA, formas de pagamento, troco, NIF, cartão/pontos, cupões, vales, \
descontos e promoções (linhas negativas ou "DESC", "POUPANÇA", "PROMO").
- Quantidade: "2 X 0,89" ou "2 UN" significa 2. Artigos vendidos a peso (kg) contam como 1.
- Sacos de compras: tipo "saco". Depósitos, taras, serviços ou outras linhas que não sejam artigos: tipo "outro".
- Data: a data de emissão. Os talões portugueses escrevem DD-MM-AAAA ou DD/MM/AA; devolve AAAA-MM-DD. \
Vazio se não houver data.
- nome: expande abreviaturas (M/G = meio-gordo, IOG = iogurte, DET = detergente, P.HIG = papel higiénico, \
S/ = sem, C/ = com…), escreve em português de Portugal com maiúscula só no início e nos nomes próprios, \
inclui a marca se for clara, não incluas tamanhos, pesos nem embalagens (1L, 500G, X6, PACK).
- existente: se te der a lista de produtos da casa, usa o nome exato de um deles quando for claramente \
o mesmo produto (mesmo que a marca seja diferente ou não apareça). Em caso de dúvida, vazio.
- Se o talão vier em várias imagens, são partes seguidas do mesmo talão, de cima para baixo, com uma pequena \
zona repetida entre partes: não contes duas vezes os artigos dessa zona.
- Se não for um talão ou estiver ilegível, legivel=false e linhas vazia."""


def montar_pedido(partes: list[dict], nomes_existentes: list[str]) -> dict:
    """Corpo do pedido generateContent (o modelo vai no URL)."""
    nomes = sorted(set(nomes_existentes), key=casa.normalizar)[:300]
    lista = "\n".join(f"- {n}" for n in nomes) if nomes else "(ainda não há produtos)"
    n_img = sum(p["inline_data"]["mime_type"].startswith("image/") for p in partes if "inline_data" in p)
    texto = (f"{'Talão em ' + str(n_img) + ' partes seguidas. ' if n_img > 1 else ''}"
             f"Produtos já registados nesta casa:\n{lista}")
    return {
        "systemInstruction": {"parts": [{"text": INSTRUCOES}]},
        "contents": [{"role": "user", "parts": partes + [{"text": texto}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseJsonSchema": ESQUEMA,
        },
    }


def _extrair_json(texto: str) -> dict:
    t = texto.strip()
    if t.startswith("```"):  # por precaução, se vier entre ```json … ```
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        dados = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            raise
        dados = json.loads(m.group(0))
    if not isinstance(dados, dict):
        raise json.JSONDecodeError("não é um objeto", t, 0)
    return dados


def _mensagem_erro(r) -> tuple[str, bool]:
    """(mensagem para a utilizadora, vale a pena tentar outro modelo?)"""
    try:
        erro = r.json().get("error", {})
    except Exception:
        erro = {}
    detalhe = str(erro.get("message", ""))
    estado = str(erro.get("status", ""))
    codigo = r.status_code
    if codigo == 400 and ("API_KEY_INVALID" in json.dumps(erro) or "API key not valid" in detalhe):
        return "A chave do Gemini não é válida. Confirme-a nos «Secrets» da aplicação.", False
    if codigo == 400 and "location is not supported" in detalhe.lower():
        return "O Gemini gratuito não está disponível na região do servidor da aplicação.", False
    if codigo == 403:
        return "A chave do Gemini não tem permissão (confirme que a API está ativa no Google AI Studio).", False
    if codigo == 404 or (codigo == 400 and "model" in detalhe.lower() and "not" in detalhe.lower()):
        return "O modelo do Gemini indicado não está disponível para esta chave.", True
    if codigo == 429 or estado == "RESOURCE_EXHAUSTED":
        if "day" in detalhe.lower() or "PerDay" in json.dumps(erro):
            return "Esgotou-se a quota gratuita diária do Gemini. Amanhã volta a funcionar; hoje use «Escrever à mão».", True
        return "Foram feitos muitos pedidos seguidos (limite gratuito do Gemini). Espere um minuto e tente outra vez.", True
    if codigo in (500, 503, 504) or estado in ("UNAVAILABLE", "INTERNAL"):
        return "O Gemini está sobrecarregado. Tente daqui a pouco.", True
    if codigo == 413:
        return "O ficheiro é demasiado grande para ser lido.", False
    return f"O Gemini devolveu um erro ({codigo}). {detalhe}".strip(), False


def chamar_api(pedido: dict, chave: str, modelos: list[str] | None = None, sessao=None,
               timeout: int = 120) -> dict:
    """Envia o pedido ao Gemini e devolve o JSON da resposta (dict).

    Tenta os modelos por ordem: se um não existir para esta chave, esgotar a quota gratuita ou
    estiver sobrecarregado, passa ao seguinte.
    """
    if sessao is None:
        import requests
        sessao = requests
    modelos = modelos or [MODELO_PADRAO]
    ultimo_erro = "Não consegui ler o talão."
    for modelo in modelos:
        try:
            r = sessao.post(API_URL.format(modelo=modelo), json=pedido, timeout=timeout,
                            headers={"x-goog-api-key": chave, "content-type": "application/json"})
        except Exception as e:
            raise ErroLeitura("Sem ligação ao Gemini. Verifique a internet e tente outra vez.") from e
        if r.status_code != 200:
            ultimo_erro, tentar_outro = _mensagem_erro(r)
            if tentar_outro:
                continue
            raise ErroLeitura(ultimo_erro)
        resposta = r.json()
        if resposta.get("promptFeedback", {}).get("blockReason"):
            raise ErroLeitura("O Gemini recusou ler esta imagem. Tente outra fotografia do talão.")
        candidatos = resposta.get("candidates") or []
        texto = "".join(p.get("text", "") for c in candidatos[:1]
                        for p in (c.get("content") or {}).get("parts", []) if not p.get("thought"))
        if not texto.strip():
            motivo = (candidatos[0].get("finishReason") if candidatos else "") or ""
            ultimo_erro = ("O talão é demasiado comprido para uma só leitura." if motivo == "MAX_TOKENS"
                           else "Não consegui ler o talão. Tente uma fotografia mais nítida.")
            continue
        try:
            return _extrair_json(texto)
        except json.JSONDecodeError:
            ultimo_erro = "A resposta do Gemini veio incompleta. Tente outra vez."
            continue
    raise ErroLeitura(ultimo_erro)


def lista_modelos(preferido: str | None) -> list[str]:
    ordem = [preferido] if preferido else []
    return ordem + [m for m in MODELOS_ALTERNATIVOS if m not in ordem]


# ---------------------------------------------------------------- interpretar
def _data_valida(valor, hoje: date) -> str | None:
    if not valor:
        return None
    s = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            d = datetime.strptime(s[:10], fmt).date()
            break
        except ValueError:
            continue
    else:
        return None
    if d > hoje or d < hoje - timedelta(days=400):
        return None
    return d.isoformat()


def _quantidade(valor) -> int:
    try:
        q = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return 1
    if q <= 0 or q > 99:
        return 1
    return max(1, round(q)) if q >= 1 else 1


def interpretar(entrada: dict, hoje: date) -> dict:
    linhas = []
    for l in entrada.get("linhas") or []:
        texto = " ".join(str(l.get("texto") or "").split())
        nome = casa.nome_bonito(str(l.get("nome") or "").strip() or texto.title())
        if not nome:
            continue
        tipo = l.get("tipo") if l.get("tipo") in ("produto", "saco", "outro") else "produto"
        linhas.append({"texto": texto, "nome": nome, "quantidade": _quantidade(l.get("quantidade")),
                       "tipo": tipo, "existente": (str(l.get("existente") or "").strip() or None)})
    return {"legivel": bool(entrada.get("legivel", True)) and bool(linhas),
            "loja": str(entrada.get("loja") or "").strip(),
            "data": _data_valida(entrada.get("data"), hoje), "linhas": linhas}


def ler_talao(conteudo: bytes, nome: str, mime: str | None, nomes_existentes: list[str], chave: str,
              hoje: date, modelo: str | None = None, sessao=None) -> dict:
    partes = preparar_ficheiro(conteudo, nome, mime)
    pedido = montar_pedido(partes, nomes_existentes)
    return interpretar(chamar_api(pedido, chave, lista_modelos(modelo), sessao), hoje)


# ---------------------------------------------------------------- associação
_PADROES = [
    (r"\bm\s*/\s*g\b|\bm\.g\.?", " meio gordo "), (r"\bs\s*/\s*", " sem "), (r"\bc\s*/\s*", " com "),
    (r"\bp\s*/\s*", " para "), (r"\bpap?\.?\s*hig\w*", " papel higienico "), (r"\bp\.\s*", " p "),
]
_ABREV = {
    "mg": "meio gordo", "mgordo": "meio gordo", "m": "", "gd": "gordo", "mag": "magro", "magr": "magro",
    "iog": "iogurte", "iogur": "iogurte", "iogs": "iogurte", "nat": "natural", "det": "detergente",
    "detg": "detergente", "deterg": "detergente", "liq": "liquido", "bol": "bolacha", "bolach": "bolacha",
    "choc": "chocolate", "chocol": "chocolate", "qj": "queijo", "qjo": "queijo", "fiamb": "fiambre",
    "cong": "congelado", "refrig": "refrigerante", "integ": "integral", "amac": "amaciador",
    "hig": "higienico", "guard": "guardanapo", "esparg": "esparguete", "manteig": "manteiga",
    "cereal": "cereal", "sumo": "sumo", "lix": "lixivia", "past": "pasta", "dent": "dentes",
}
_IGNORAR = {"de", "da", "do", "das", "dos", "e", "a", "o", "com", "para", "p", "emb", "un", "uni", "und",
            "pack", "cx", "caixa", "garrafa", "gf", "lata", "frasco", "embalagem", "promo", "kg", "g", "gr",
            "l", "lt", "ml", "cl"}
_DISTINTIVAS = {"sem", "gas", "zero", "light", "descafeinado", "biologico", "bio"}  # já em radical
_TAMANHO = re.compile(r"^(x?\d+([.,]\d+)?(x\d+)?(g|gr|grs|kg|l|lt|ml|cl|un|und|uni|cps|pcs|d|dos|doses|r|rl|rol|rolos|sq|saq|cap|caps|m|mt|lav)?|x\d+)$")


def _sem_acentos(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _radical(t: str) -> str:
    for fim, novo in (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el")):
        if t.endswith(fim) and len(t) > 4:
            return t[: -len(fim)] + novo
    if t.endswith("s") and len(t) > 3:
        return t[:-1]
    return t


def tokens(texto: str) -> list[str]:
    t = _sem_acentos(texto)
    for padrao, novo in _PADROES:
        t = re.sub(padrao, novo, t)
    saida = []
    for tok in casa.normalizar(t).split():
        if _TAMANHO.match(tok):
            continue
        for parte in _ABREV.get(tok, tok).split():
            if parte and parte not in _IGNORAR:
                saida.append(_radical(parte))
    return saida


def _iguais(a: str, b: str) -> bool:
    if a == b:
        return True
    curto, longo = sorted((a, b), key=len)
    if len(curto) >= 3 and longo.startswith(curto):
        return True
    return min(len(a), len(b)) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.85


def semelhanca(talao: str, produto: str) -> float:
    """0 a 1. Metade é a semelhança geral; a outra metade é quanto do nome do produto da casa
    aparece no talão (os talões têm marca e pormenores que os nomes da casa normalmente não têm)."""
    ta, tb = tokens(talao), tokens(produto)
    if not ta or not tb:
        return 0.0
    livres, iguais = list(tb), 0
    for x in ta:
        for y in livres:
            if _iguais(x, y):
                livres.remove(y)
                iguais += 1
                break
    s = 0.5 * (2 * iguais / (len(ta) + len(tb))) + 0.5 * (iguais / len(tb))
    for palavra in _DISTINTIVAS:  # «sem sal», «com gás», «zero»… é outro produto
        if (palavra in ta) != (palavra in tb):
            s *= 0.5
    return s


def associar(dados: dict, linha: dict) -> tuple[str | None, str, str]:
    """Devolve (produto_id ou None, nome a usar, como: memória/sugestão/parecido/novo)."""
    produtos = dados["produtos"]
    pid = dados.get("aliases", {}).get(casa.chave_alias(linha["texto"])) if linha.get("texto") else None
    if pid in produtos:
        return pid, produtos[pid]["nome"], "memória"
    if linha.get("existente"):
        pid = casa.encontrar_produto(dados, linha["existente"])
        if pid:
            return pid, produtos[pid]["nome"], "sugestão"
    melhor, pontos = None, 0.0
    for pid, p in produtos.items():
        s = max(semelhanca(linha.get("texto", ""), p["nome"]), semelhanca(linha["nome"], p["nome"]))
        if s > pontos:
            melhor, pontos = pid, s
    if melhor and pontos >= LIMIAR_SEMELHANCA:
        return melhor, produtos[melhor]["nome"], "parecido"
    pid = casa.encontrar_produto(dados, linha["nome"])
    if pid:
        return pid, produtos[pid]["nome"], "parecido"
    return None, linha["nome"], "novo"


def linhas_para_revisao(dados: dict, talao: dict) -> list[dict]:
    """Linhas prontas para a tabela de revisão (junta repetidos do mesmo produto)."""
    saida: list[dict] = []
    por_nome: dict[str, dict] = {}
    for l in talao["linhas"]:
        pid, nome, como = associar(dados, l)
        chave = pid or casa.normalizar(nome)
        if l["tipo"] == "produto" and chave in por_nome:
            por_nome[chave]["quantidade"] += l["quantidade"]
            continue
        linha = {"incluir": l["tipo"] == "produto", "produto": nome, "quantidade": l["quantidade"],
                 "talao": l["texto"], "associacao": "Novo" if como == "novo" else "Já existe"}
        saida.append(linha)
        if l["tipo"] == "produto":
            por_nome[chave] = linha
    return saida
