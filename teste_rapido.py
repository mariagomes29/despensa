"""Testes rápidos da lógica (não precisa do Streamlit).   Executar:  python teste_rapido.py

* Aprendizagem pela frequência de compra (leite semanal, café quinzenal, detergente mensal…)
* Lista «Em breve» e «Lista do mês», compras a dobrar, produtos que deixaram de se comprar
* Acesso por e-mail + código, e separação dos dados entre casas (local e GitHub)
* Conversão de ficheiros da versão anterior (com stock)
"""
import base64
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import acesso
import casa
import previsao as pv
import storage

HOJE = date(2026, 3, 2)


def d(dias_atras: int) -> str:
    return (HOJE - timedelta(days=dias_atras)).isoformat()


def produto(an, nome):
    return next(r for r in an["produtos"] if r["nome"] == nome)


def teste_frequencia():
    dados = casa.dados_novos(acesso.nova_casa("mae@exemplo.pt", None), d(70))
    h = HOJE.isoformat()
    for k in range(10):                       # leite: 6 todas as semanas, última há 4 dias
        casa.registar_compra(dados, "Leite meio-gordo", 6, d(4 + 7 * k), h)
    for k in range(5):                        # café: de 14 em 14 dias, última há 20 dias (atrasado)
        casa.registar_compra(dados, "café moído", 1, d(20 + 14 * k), h)
    for k in range(3):                        # detergente: todos os meses, última há 10 dias
        casa.registar_compra(dados, "Detergente roupa", None, d(10 + 30 * k), h)
    casa.registar_compra(dados, "Pão", 2, d(3), h)       # só 1 compra -> a aprender
    casa.registar_compra(dados, "Pão", 1, d(3), h)       # mesmo dia: conta como uma compra de 3
    for k in range(4):                        # pilhas: semanais, mas a última foi há 80 dias -> inativo
        casa.registar_compra(dados, "Pilhas", 2, d(80 + 7 * k), h)
    casa.registar_compra(dados, "Iogurtes", 8, d(45), h)  # 2 compras e mais de 30 dias -> já tem padrão
    casa.registar_compra(dados, "Iogurtes", 8, d(5), h)

    an = pv.analisar(dados, HOJE)
    leite, cafe = produto(an, "Leite meio-gordo"), produto(an, "Café moído")
    deterg, pao, pilhas, iog = (produto(an, n) for n in ("Detergente roupa", "Pão", "Pilhas", "Iogurtes"))

    assert leite["pronto"] and leite["intervalo"] == 7 and leite["frequencia"] == "Todas as semanas"
    assert leite["dias_ate"] == 3 and leite["em_breve"] and leite["habitual"] == 6
    assert leite["vezes_mes"] == 4 and leite["quantidade_mes"] == 24, leite   # dias 3, 10, 17, 24
    assert cafe["dias_ate"] == -6 and cafe["em_breve"] and pv.quando_texto(cafe["dias_ate"]) == "Atrasado 6 dias"
    assert deterg["frequencia"] == "Todos os meses" and deterg["dias_ate"] == 20 and not deterg["em_breve"]
    assert deterg["no_mes"] and deterg["quantidade_mes"] == 1 and deterg["habitual"] == 1
    assert not pao["pronto"] and pao["n_compras"] == 1 and pao["habitual"] == 3
    assert pilhas["inativo"] and not pilhas["em_breve"] and not pilhas["no_mes"]
    assert iog["pronto"] and iog["intervalo"] == 40
    assert [r["nome"] for r in an["em_breve"]] == ["Café moído", "Leite meio-gordo"]
    assert not an["em_aprendizagem"]
    print("Em breve:", [(r["nome"], pv.quando_texto(r["dias_ate"])) for r in an["em_breve"]])
    print("Mês:     ", [(r["nome"], r["quantidade_mes"]) for r in an["mensal"]])
    print("A aprender:", [r["nome"] for r in an["a_aprender"]])

    # Comprei hoje o dobro do leite -> próxima compra só daqui a ~14 dias
    casa.registar_compra(dados, "Leite meio-gordo", 12, h, h)
    leite = produto(pv.analisar(dados, HOJE), "Leite meio-gordo")
    assert 13 <= leite["dias_ate"] <= 15 and not leite["em_breve"], leite

    # Um intervalo estranho (esqueceu-se de registar uma compra) não estraga o padrão
    dados2 = casa.dados_novos({}, d(90))
    for dias in (60, 53, 46, 25, 18, 11, 4):  # falta a compra de há 32/39 dias
        casa.registar_compra(dados2, "Leite", 6, d(dias), h)
    l2 = produto(pv.analisar(dados2, HOJE), "Leite")
    assert 7 <= l2["intervalo"] <= 9, l2
    print("OK: frequência, listas, compras a dobrar, valores estranhos, inativos")


def teste_aprendizagem_inicial():
    dados = casa.dados_novos({}, d(5))
    casa.registar_compra(dados, "Arroz", 2, d(5), HOJE.isoformat())
    casa.registar_compra(dados, "Arroz", 2, d(1), HOJE.isoformat())
    an = pv.analisar(dados, HOJE)
    assert an["em_aprendizagem"] and not produto(an, "Arroz")["pronto"]
    assert an["em_breve"] == [] and an["mensal"] == []
    print("OK: fase de aprendizagem")


def teste_acesso():
    assert acesso.normalizar_email("  Maria@Exemplo.PT ") == "maria@exemplo.pt"
    assert acesso.email_valido("maria@exemplo.pt") and not acesso.email_valido("maria@")
    assert acesso.casa_id("Maria@exemplo.pt ") == acesso.casa_id("maria@exemplo.pt")
    assert acesso.casa_id("maria@exemplo.pt") != acesso.casa_id("joao@exemplo.pt")
    info = acesso.nova_casa("maria@exemplo.pt", "1234")
    assert "1234" not in json.dumps(info)
    assert acesso.verificar_pin("1234", info) and not acesso.verificar_pin("4321", info)
    assert not acesso.verificar_pin("", info)
    sem = acesso.nova_casa("joao@exemplo.pt", None)
    assert acesso.verificar_pin("", sem)
    cid = acesso.casa_id("maria@exemplo.pt")
    tok = acesso.ler_token(acesso.token_link(cid, info))
    assert tok and tok[0] == cid and acesso.chave_correta(info, tok[1])
    assert not acesso.chave_correta(info, "errada") and acesso.ler_token("../x.y") is None
    print("OK: acesso (e-mail, código, link)")


def teste_casas_separadas_local():
    pasta = Path(tempfile.mkdtemp())
    g = storage.gestor_local(pasta, casa.preparar)
    h = HOJE.isoformat()
    mae, outra = acesso.casa_id("mae@exemplo.pt"), acesso.casa_id("vizinha@exemplo.pt")
    assert g.casa(mae).carregar() is None
    g.casa(mae).criar(casa.dados_novos(acesso.nova_casa("mae@exemplo.pt", "1111"), h))
    g.casa(outra).criar(casa.dados_novos(acesso.nova_casa("vizinha@exemplo.pt", None), h))
    g.casa(mae).atualizar(lambda x: casa.registar_compra(x, "Leite", 6, h, h))
    g.casa(outra).atualizar(lambda x: casa.registar_compra(x, "Café", 1, h, h))

    # o pai entra com o mesmo e-mail noutro aparelho (outro gestor = outro processo)
    pai = storage.gestor_local(pasta, casa.preparar).casa(acesso.casa_id("MAE@exemplo.pt"))
    pai.atualizar(lambda x: casa.registar_compra(x, "Pão", 4, h, h))
    g.casa(mae)._t = None  # força nova leitura
    nomes_mae = sorted(p["nome"] for p in g.casa(mae).carregar()["produtos"].values())
    nomes_outra = sorted(p["nome"] for p in g.casa(outra).carregar()["produtos"].values())
    assert nomes_mae == ["Leite", "Pão"] and nomes_outra == ["Café"], (nomes_mae, nomes_outra)
    assert sorted(f.name for f in pasta.glob("*.json")) == sorted([f"{mae}.json", f"{outra}.json"])
    try:
        g.casa(mae).criar(casa.dados_novos({}, h))
        raise AssertionError("não devia criar por cima de uma casa existente")
    except storage.ErroArmazenamento:
        pass
    try:
        g.casa("../../etc/passwd")
        raise AssertionError("id inseguro aceite")
    except storage.ErroArmazenamento:
        pass
    print("OK: casas separadas (local), mesma casa em dois aparelhos")


class _Resp:
    def __init__(self, code, data=None):
        self.status_code, self._d, self.text = code, data, json.dumps(data or {})

    def json(self):
        return self._d


class GitHubFalso:
    """Imita a API de conteúdos do GitHub (um ficheiro por caminho, com 'sha')."""

    def __init__(self):
        self.headers, self.ficheiros, self.n = {}, {}, 0

    def request(self, metodo, url, timeout=None, params=None, json=None, headers=None):
        atual = self.ficheiros.get(url)
        if metodo == "GET":
            if atual is None:
                return _Resp(404)
            return _Resp(200, {"content": base64.b64encode(atual[0]).decode(), "sha": atual[1]})
        if atual is not None and json.get("sha") != atual[1]:
            return _Resp(409 if json.get("sha") else 422, {"message": "sha mismatch"})
        self.n += 1
        self.ficheiros[url] = (base64.b64decode(json["content"]), f"sha{self.n}")
        return _Resp(201, {"content": {"sha": f"sha{self.n}"}})


def teste_github():
    gh = GitHubFalso()
    h = HOJE.isoformat()
    g1 = storage.gestor_github("tok", "eu/despensa-dados", sessao=gh, preparar=casa.preparar)
    g2 = storage.gestor_github("tok", "eu/despensa-dados", sessao=gh, preparar=casa.preparar)
    mae, viz = acesso.casa_id("mae@exemplo.pt"), acesso.casa_id("vizinha@exemplo.pt")
    g1.casa(mae).criar(casa.dados_novos(acesso.nova_casa("mae@exemplo.pt", None), h))
    g1.casa(viz).criar(casa.dados_novos(acesso.nova_casa("vizinha@exemplo.pt", None), h))
    g1.casa(mae).atualizar(lambda x: casa.registar_compra(x, "Pão", 4, h, h))
    g2.casa(mae).carregar()
    g1.casa(mae).atualizar(lambda x: casa.registar_compra(x, "Leite", 6, h, h))
    g2.casa(mae).atualizar(lambda x: casa.registar_compra(x, "Ovos", 12, h, h))  # cache antiga -> conflito
    caminhos = sorted(u.rsplit("/contents/", 1)[1] for u in gh.ficheiros)
    assert caminhos == sorted([f"casas/{mae}.json", f"casas/{viz}.json"]), caminhos
    final = json.loads(gh.ficheiros[next(u for u in gh.ficheiros if mae in u)][0])
    assert sorted(p["nome"] for p in final["produtos"].values()) == ["Leite", "Ovos", "Pão"]
    assert json.loads(gh.ficheiros[next(u for u in gh.ficheiros if viz in u)][0])["produtos"] == {}
    print("OK: GitHub — um ficheiro por casa, conflito resolvido sem perder dados")


def teste_migracao_v1():
    v1 = {"versao": 1, "criado_em": "2026-01-01",
          "produtos": {"p1": {"nome": "Leite", "categoria": "Laticínios e ovos"}},
          "movimentos": [
              {"id": "a", "produto_id": "p1", "tipo": "compra", "quantidade": 6, "data": "2026-01-01"},
              {"id": "b", "produto_id": "p1", "tipo": "consumo", "quantidade": -1, "data": "2026-01-02"},
              {"id": "c", "produto_id": "p1", "tipo": "compra", "quantidade": 6, "data": "2026-01-08"}]}
    v2 = casa.preparar(v1)
    assert v2["versao"] == 2 and "movimentos" not in v2
    assert [c["id"] for c in v2["compras"]] == ["a", "c"]
    print("OK: conversão de ficheiros da versão anterior")


if __name__ == "__main__":
    teste_frequencia()
    teste_aprendizagem_inicial()
    teste_acesso()
    teste_casas_separadas_local()
    teste_github()
    teste_migracao_v1()
