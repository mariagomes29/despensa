"""Aprendizagem pela frequência de compra e geração da lista de compras.

Sem stock: a aplicação só sabe *quando* e *quanto* se compra de cada produto.

1. Compras do mesmo produto no mesmo dia contam como uma só (somam-se as quantidades).
2. Fase de aprendizagem: um produto precisa de 3 compras em dias diferentes, ou de 2 compras
   com pelo menos 30 dias entre a primeira e hoje. Até lá aparece como «A aprender».
3. Intervalo habitual: dos últimos 8 intervalos entre compras, corta os valores estranhos
   (menos de metade ou mais do dobro da mediana) e faz uma média ponderada em que as compras
   recentes valem mais (o peso cai para metade a cada 3 compras para trás).
4. Quantidade habitual: mediana das últimas 6 compras.
5. Próxima compra = última compra + intervalo habitual × (quantidade da última ÷ habitual).
   Assim, se se comprou o dobro, a próxima compra fica para mais tarde.
6. Listas:
   * «Em breve»: próxima compra nos próximos 7 dias (ou já atrasada).
   * «Lista do mês»: tudo o que se prevê comprar nos próximos 30 dias, com a quantidade total
     do mês (quantidade habitual × número de vezes que se costuma comprar nesse período).
   * Se passar mais de 3× o intervalo habitual sem comprar, o produto deixa de ser sugerido
     (talvez já não se compre); volta a ser sugerido logo que se registe uma compra.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

import casa

DIAS_APRENDIZAGEM = 30
MIN_COMPRAS = 3           # compras (dias diferentes) para ter padrão
MIN_COMPRAS_APOS_MES = 2  # …ou 2, se a primeira já tiver 30 dias
JANELA = 8                # últimos intervalos considerados
MEIA_VIDA = 3             # em número de compras
EM_BREVE = 7              # dias
MES = 30                  # dias
INATIVO = 3               # × intervalo habitual


def _d(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


def quando_texto(dias: int | None) -> str:
    if dias is None:
        return ""
    if dias < 0:
        return "Atrasado" if dias == -1 else f"Atrasado {-dias} dias"
    if dias == 0:
        return "Hoje"
    if dias == 1:
        return "Amanhã"
    return f"Em {dias} dias"


def frequencia_texto(intervalo: float | None) -> str:
    if not intervalo:
        return ""
    d = round(intervalo)
    if d <= 1:
        return "Todos os dias"
    if 6 <= d <= 8:
        return "Todas as semanas"
    if 13 <= d <= 16:
        return "De 2 em 2 semanas"
    if 27 <= d <= 33:
        return "Todos os meses"
    if 55 <= d <= 65:
        return "De 2 em 2 meses"
    return f"De {d} em {d} dias"


def intervalo_habitual(intervalos: list[int]) -> float:
    ult = intervalos[-JANELA:]
    m = statistics.median(ult)
    cortados = [min(max(x, m / 2), m * 2) for x in ult]
    n = len(cortados)
    pesos = [0.5 ** ((n - 1 - i) / MEIA_VIDA) for i in range(n)]
    return sum(w * x for w, x in zip(pesos, cortados)) / sum(pesos)


def analisar_produto(pid: str, p: dict, compras: list[dict], hoje: date) -> dict:
    por_dia: dict[date, float] = {}
    for c in compras:
        d = min(_d(c["data"]), hoje)
        por_dia[d] = por_dia.get(d, 0) + float(c["quantidade"])
    datas = sorted(por_dia)
    qts = [por_dia[d] for d in datas]
    n = len(datas)

    habitual = max(1, round(statistics.median(qts[-6:]))) if n else 1
    dias_1a = (hoje - datas[0]).days if n else 0
    pronto = n >= MIN_COMPRAS or (n >= MIN_COMPRAS_APOS_MES and dias_1a >= DIAS_APRENDIZAGEM)

    r = {
        "id": pid, "nome": p["nome"], "categoria": p.get("categoria", "Outros"),
        "icone": casa.icone(p.get("categoria")), "n_compras": n, "habitual": habitual,
        "ultima": datas[-1].isoformat() if n else None,
        "pronto": pronto, "progresso": 1.0 if pronto else min(n / MIN_COMPRAS, 0.99),
        "intervalo": None, "frequencia": "", "proxima": None, "dias_ate": None,
        "inativo": False, "em_breve": False, "no_mes": False, "vezes_mes": 0, "quantidade_mes": 0,
    }
    if not pronto:
        return r

    intervalos = [(b - a).days for a, b in zip(datas, datas[1:])]
    intervalo = intervalo_habitual(intervalos)
    fator = min(max(qts[-1] / habitual, 0.5), 3.0)
    espera = intervalo * fator
    proxima = datas[-1] + timedelta(days=round(espera))
    dias_ate = (proxima - hoje).days
    inativo = (hoje - datas[-1]).days > INATIVO * espera

    r.update(intervalo=round(intervalo, 1), frequencia=frequencia_texto(intervalo),
             proxima=proxima.isoformat(), dias_ate=dias_ate, inativo=inativo)
    if not inativo:
        r["em_breve"] = dias_ate <= EM_BREVE
        inicio = max(dias_ate, 0)
        if inicio <= MES:
            vezes = math.floor((MES - inicio) / intervalo) + 1
            r.update(no_mes=True, vezes_mes=vezes, quantidade_mes=int(vezes * habitual))
    return r


def analisar(dados: dict, hoje: date) -> dict:
    por = casa.compras_por_produto(dados)
    produtos = [analisar_produto(pid, p, por.get(pid, []), hoje) for pid, p in dados["produtos"].items()]
    produtos.sort(key=lambda r: casa.normalizar(r["nome"]))

    n = len(produtos)
    prontos = [r for r in produtos if r["pronto"]]
    dias_app = (hoje - _d(dados.get("criado_em", hoje.isoformat()))).days + 1
    em_aprendizagem = n == 0 or not prontos or (dias_app < DIAS_APRENDIZAGEM and len(prontos) < math.ceil(n / 2))

    def ordem(r):
        return (r["dias_ate"], casa.normalizar(r["nome"]))

    return {
        "produtos": produtos,
        "em_breve": sorted((r for r in prontos if r["em_breve"]), key=ordem),
        "mensal": sorted((r for r in prontos if r["no_mes"]), key=ordem),
        "a_aprender": [r for r in produtos if not r["pronto"]],
        "n_produtos": n, "n_prontos": len(prontos), "dias_app": dias_app,
        "em_aprendizagem": em_aprendizagem,
        "progresso": (sum(r["progresso"] for r in produtos) / n) if n else 0.0,
    }
