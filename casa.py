"""Operações sobre os dados de uma casa: produtos e compras (sem controlo de stock).

Cada casa tem o seu próprio ficheiro JSON:
{
  "versao": 2,
  "criado_em": "2026-11-20",                       # início da fase de aprendizagem
  "casa": {"email": "maria@exemplo.pt", "pin_hash": "…", "sal": "…",   # pin_hash vazio = sem código
           "chave": "…"},                           # segredo usado no link "lembrar-me"
  "produtos": {
     "a1b2c3d4e5": {"nome": "Leite meio-gordo", "categoria": "Laticínios e ovos",
                    "criado_em": "2026-11-20"}
  },
  "compras": [
     {"id": "…", "produto_id": "a1b2c3d4e5", "quantidade": 6, "data": "2026-11-20",
      "registado_em": "2026-11-20T15:30:00+00:00"}
  ]
}
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone

VERSAO = 2

# Categoria -> ícone (Material Symbols, traço fino)
CATEGORIAS = {
    "Laticínios e ovos": "egg",
    "Padaria": "bakery_dining",
    "Fruta e legumes": "nutrition",
    "Carne e peixe": "set_meal",
    "Mercearia": "kitchen",
    "Bebidas": "local_drink",
    "Congelados": "ac_unit",
    "Limpeza": "cleaning_services",
    "Higiene": "soap",
    "Outros": "shopping_basket",
}

_PALAVRAS = {
    "Laticínios e ovos": "leite iogurte iogurtes queijo manteiga natas ovo ovos requeijao kefir",
    "Padaria": "pao paes broa bolo bolos tosta tostas croissant bolachas bolacha cereais",
    "Fruta e legumes": "maca macas banana bananas laranja laranjas pera peras batata batatas cebola cebolas "
                       "alho tomate tomates alface cenoura cenouras fruta legumes limao limoes couve "
                       "abobora pepino pimento espinafres brocolos",
    "Carne e peixe": "frango peru carne bife bifes porco vaca peixe pescada bacalhau salmao atum "
                     "fiambre chourico salsichas presunto",
    "Mercearia": "arroz massa esparguete azeite oleo acucar sal farinha feijao grao cafe cha "
                 "conserva conservas molho ketchup maionese vinagre mel compota",
    "Bebidas": "agua sumo sumos vinho cerveja refrigerante coca",
    "Congelados": "congelado congelados gelado gelados ervilhas",
    "Limpeza": "detergente lixivia esfregao esfregoes guardanapos rolo sacos lava loica amaciador",
    "Higiene": "papel higienico champo gel banho pasta dentes escova sabonete desodorizante "
               "pensos fraldas toalhitas",
}


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def novo_id() -> str:
    return uuid.uuid4().hex[:10]


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", t).split())


def nome_bonito(nome: str) -> str:
    nome = " ".join(str(nome).split())
    return nome[:1].upper() + nome[1:]


def adivinhar_categoria(nome: str) -> str:
    palavras = set(normalizar(nome).split())
    for cat, lista in _PALAVRAS.items():
        if palavras & set(lista.split()):
            return cat
    return "Outros"


def icone(categoria: str | None) -> str:
    return CATEGORIAS.get(categoria or "Outros", CATEGORIAS["Outros"])


# ---------------------------------------------------------------- estrutura
def dados_novos(info_casa: dict, hoje_iso: str) -> dict:
    return {"versao": VERSAO, "criado_em": hoje_iso, "casa": dict(info_casa), "produtos": {}, "compras": []}


def preparar(dados: dict | None, hoje_iso: str | None = None) -> dict | None:
    """Completa a estrutura e converte ficheiros da versão 1 (com stock) para a versão 2."""
    if dados is None:
        return None
    hoje_iso = hoje_iso or date.today().isoformat()
    dados.setdefault("criado_em", hoje_iso)
    dados.setdefault("casa", {})
    dados.setdefault("produtos", {})
    if "compras" not in dados:  # versão 1: só as entradas de stock eram compras
        dados["compras"] = [
            {"id": m["id"], "produto_id": m["produto_id"], "quantidade": abs(m["quantidade"]),
             "data": m["data"], "registado_em": m.get("registado_em", agora_iso())}
            for m in dados.get("movimentos", []) if m.get("tipo") == "compra"]
    dados.pop("movimentos", None)
    dados["versao"] = VERSAO
    return dados


# ------------------------------------------------------------------ produtos
def encontrar_produto(dados: dict, nome: str) -> str | None:
    alvo = normalizar(nome)
    for pid, p in dados["produtos"].items():
        if normalizar(p["nome"]) == alvo:
            return pid
    return None


def obter_ou_criar_produto(dados: dict, nome: str, hoje_iso: str, categoria: str | None = None) -> str:
    pid = encontrar_produto(dados, nome)
    if pid:
        return pid
    pid = novo_id()
    dados["produtos"][pid] = {
        "nome": nome_bonito(nome),
        "categoria": categoria if categoria in CATEGORIAS else adivinhar_categoria(nome),
        "criado_em": hoje_iso,
    }
    return pid


def editar_produto(dados: dict, pid: str, nome: str | None = None, categoria: str | None = None):
    p = dados["produtos"][pid]
    if nome and nome.strip():
        p["nome"] = nome_bonito(nome)
    if categoria in CATEGORIAS:
        p["categoria"] = categoria


def apagar_produto(dados: dict, pid: str):
    dados["produtos"].pop(pid, None)
    dados["compras"] = [c for c in dados["compras"] if c["produto_id"] != pid]


# ------------------------------------------------------------------- compras
def registar_compra(dados: dict, nome_ou_pid: str, quantidade: float | None, data_iso: str,
                    hoje_iso: str, categoria: str | None = None) -> list[str]:
    """Regista uma compra. Devolve a lista de ids criados (para «Desfazer»)."""
    pid = nome_ou_pid if nome_ou_pid in dados["produtos"] else \
        obter_ou_criar_produto(dados, nome_ou_pid, hoje_iso, categoria)
    q = float(quantidade or 1)
    q = int(q) if q == int(q) else q
    c = {"id": novo_id(), "produto_id": pid, "quantidade": q, "data": data_iso, "registado_em": agora_iso()}
    dados["compras"].append(c)
    return [c["id"]]


def remover_compras(dados: dict, ids) -> int:
    ids = set(ids)
    antes = len(dados["compras"])
    dados["compras"] = [c for c in dados["compras"] if c["id"] not in ids]
    return antes - len(dados["compras"])


def compras_por_produto(dados: dict) -> dict[str, list]:
    por = defaultdict(list)
    for c in dados["compras"]:
        por[c["produto_id"]].append(c)
    return por


def compras_recentes(dados: dict, n: int = 8, pid: str | None = None) -> list[dict]:
    lista = [c for c in dados["compras"] if c["produto_id"] in dados["produtos"]
             and (pid is None or c["produto_id"] == pid)]
    lista.sort(key=lambda c: (c["data"], c["registado_em"]), reverse=True)
    return lista[:n]
