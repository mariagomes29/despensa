"""A minha despensa — compras da casa com aprendizagem pela frequência de compra.

Executar no computador:   streamlit run app.py
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

import acesso
import casa
import faturas
import previsao as pv
import storage
from estilo import CSS

FUSO = ZoneInfo("Europe/Lisbon")
PASTA = Path(__file__).parent
MAX_FALHAS = 5          # tentativas de código erradas antes de esperar
ESPERA_FALHAS = 60      # segundos

st.set_page_config(page_title="A minha despensa", page_icon="🧺", layout="centered",
                   initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)


# ------------------------------------------------------------------ utilitários
def agora() -> datetime:
    return datetime.now(FUSO)


def hoje_iso() -> str:
    return agora().date().isoformat()


def esc(t) -> str:
    return html.escape(str(t))


def esc_md(t) -> str:
    return re.sub(r"([\\`*_\[\]<>#|~$])", r"\\\1", str(t))


def fmt_qtd(q) -> str:
    q = float(q)
    return str(int(q)) if q == int(q) else f"{q:.1f}".replace(".", ",")


def fmt_data(iso: str) -> str:
    a, m, d = iso[:10].split("-")
    return f"{d}/{m}/{a}"


def saudacao() -> str:
    h = agora().hour
    return "Bom dia!" if 6 <= h < 13 else "Boa tarde!" if 13 <= h < 20 else "Boa noite!"


def pilula(texto: str, tipo: str = "") -> str:
    return f"<span class='pilula {tipo}'>{esc(texto)}</span>" if texto else ""


def pilula_quando(r: dict) -> str:
    if not r["pronto"]:
        return pilula(f"A aprender · {r['n_compras']} de {pv.MIN_COMPRAS} compras", "neutra")
    if r["inativo"]:
        return pilula("Sem compras há muito tempo", "neutra")
    return pilula(pv.quando_texto(r["dias_ate"]), "aviso" if r["dias_ate"] < 0 else "")


def cinza(texto: str) -> str:
    return f"<span class='cinza'>{esc(texto)}</span>"


# ------------------------------------------------------------------ armazenamento
def _segredos_github() -> dict | None:
    try:
        s = dict(st.secrets["github"])
        return s if s.get("token") and s.get("repo") else None
    except Exception:
        return None


@st.cache_resource
def obter_gestor() -> storage.Gestor:
    gh = _segredos_github()
    if gh:
        return storage.gestor_github(gh["token"], gh["repo"], gh.get("pasta", "casas"), gh.get("ramo", "main"),
                                     preparar=casa.preparar)
    return storage.gestor_local(PASTA / "dados" / "casas", preparar=casa.preparar)


gestor = obter_gestor()


def armazem() -> storage.Armazem:
    return gestor.casa(st.session_state["casa_id"])


def executar(alteracao, desfazer_texto: str | None = None):
    """Aplica uma alteração aos dados da casa e grava. Guarda o necessário para «Desfazer»."""
    try:
        ids = armazem().atualizar(alteracao)
    except storage.ErroArmazenamento as e:
        st.session_state["erro"] = str(e)
        return None
    if desfazer_texto and ids:
        st.session_state["ultima"] = {"ids": list(ids), "texto": desfazer_texto, "t": time.time()}
    return ids


# ------------------------------------------------------------------ entrada / saída
def entrar(cid: str, info: dict):
    st.session_state.update(casa_id=cid, email=info.get("email", ""), falhas=0)
    for k in ("pendente", "ultima"):
        st.session_state.pop(k, None)
    st.query_params["c"] = acesso.token_link(cid, info)  # «lembrar-me» neste aparelho
    st.session_state["pagina"] = "Início"


def sair():
    for k in ("casa_id", "email", "ultima", "pendente"):
        st.session_state.pop(k, None)
    st.query_params.clear()


def entrar_por_link() -> bool:
    tok = acesso.ler_token(st.query_params.get("c", ""))
    if not tok:
        return False
    cid, chave = tok
    try:
        dados = gestor.casa(cid).carregar()
    except storage.ErroArmazenamento:
        return False
    if dados and acesso.chave_correta(dados.get("casa", {}), chave):
        st.session_state.update(casa_id=cid, email=dados["casa"].get("email", ""))
        return True
    st.query_params.clear()
    return False


def processar_entrada(email: str, pin: str):
    s = st.session_state
    s.pop("pendente", None)
    if time.time() < s.get("bloqueado_ate", 0):
        s["erro"] = "Demasiadas tentativas. Espere um minuto e tente outra vez."
        return
    email, pin = acesso.normalizar_email(email), (pin or "").strip()
    if not acesso.email_valido(email):
        s["erro"] = "Escreva um e-mail válido, por exemplo nome@exemplo.pt."
        return
    if pin and not acesso.pin_valido(pin):
        s["erro"] = "O código tem de ter 4 algarismos."
        return
    cid = acesso.casa_id(email)
    try:
        dados = gestor.casa(cid).carregar()
    except storage.ErroArmazenamento as e:
        s["erro"] = str(e)
        return
    if dados is None:
        s["pendente"] = {"email": email, "pin": pin}
        return
    info = dados.get("casa", {})
    if acesso.tem_pin(info) and not pin:
        s["erro"] = "Esta casa tem código. Escreva o código de 4 algarismos."
        return
    if not acesso.verificar_pin(pin, info):
        s["falhas"] = s.get("falhas", 0) + 1
        if s["falhas"] >= MAX_FALHAS:
            s["bloqueado_ate"], s["falhas"] = time.time() + ESPERA_FALHAS, 0
        s["erro"] = "O código não está certo."
        return
    if not info.get("chave"):  # casas antigas sem chave de link
        def juntar_chave(d):
            d["casa"]["chave"] = acesso.nova_casa(email, None)["chave"]
        gestor.casa(cid).atualizar(juntar_chave)
        info = gestor.casa(cid).carregar()["casa"]
    entrar(cid, info)
    st.rerun()


def criar_casa():
    p = st.session_state.get("pendente")
    if not p:
        return
    cid = acesso.casa_id(p["email"])
    info = acesso.nova_casa(p["email"], p["pin"] or None)
    try:
        gestor.casa(cid).criar(casa.dados_novos(info, hoje_iso()))
    except storage.ErroArmazenamento as e:
        st.session_state["erro"] = str(e)
        return
    entrar(cid, info)
    st.session_state["aviso"] = "Casa criada. Comece por registar as compras que fizer."


def ecra_entrada():
    st.markdown("<div class='marca'>A minha despensa</div>"
                "<p class='saudacao'>Olá!</p>"
                "<p class='subtitulo'>Entre com o e-mail da sua casa. Quem usar o mesmo e-mail "
                "vê a mesma lista de compras.</p>", unsafe_allow_html=True)
    if erro := st.session_state.pop("erro", None):
        st.error(erro, icon=":material/error:")

    with st.form("entrar", border=False):
        email = st.text_input("E-mail da casa", placeholder="nome@exemplo.pt", autocomplete="email")
        pin = st.text_input("Código da casa (opcional)", type="password", max_chars=4,
                            placeholder="4 algarismos", help="Serve para ninguém entrar na sua casa por engano.")
        enviar = st.form_submit_button("Entrar", icon=":material/login:")
    if enviar:
        processar_entrada(email, pin)
        if st.session_state.get("erro"):
            st.rerun()

    p = st.session_state.get("pendente")
    if p:
        extra = ("Fica protegida com o código que escreveu." if p["pin"] else
                 "Sem código, quem souber o e-mail pode entrar. Pode juntar um código de 4 algarismos acima.")
        st.markdown(f"<div class='aprender'><b>Ainda não existe nenhuma casa com {esc(p['email'])}</b>"
                    f"<p>Quer criar uma casa nova? {esc(extra)}</p></div>", unsafe_allow_html=True)
        a, b = st.columns(2)
        a.button("Criar casa", icon=":material/add_home:", on_click=criar_casa)
        b.button("Corrigir e-mail", on_click=lambda: st.session_state.pop("pendente", None))


# ------------------------------------------------------------------ ações (callbacks)
def acao_comprei(pid: str, nome: str, chave_qtd: str | None = None, quantidade=None):
    q = st.session_state.get(chave_qtd) if chave_qtd else quantidade
    q = q or 1
    executar(lambda d: casa.registar_compra(d, pid, q, hoje_iso(), hoje_iso()),
             f"Comprou {fmt_qtd(q)} × {nome} hoje")


def acao_comprei_tudo(itens: list[tuple[str, str]]):
    def alterar(d):
        ids = []
        for pid, chave in itens:
            ids += casa.registar_compra(d, pid, st.session_state.get(chave) or 1, hoje_iso(), hoje_iso())
        return ids
    executar(alterar, f"Registou {len(itens)} produto(s) comprados hoje")


def acao_desfazer():
    ult = st.session_state.pop("ultima", None)
    if ult:
        executar(lambda d: casa.remover_compras(d, ult["ids"]))
        st.session_state["aviso"] = "Desfeito."


def acao_registar_compra():
    s = st.session_state
    nome = (s.get("f_produto") or "").strip()
    if not nome:
        s["erro"] = "Escolha ou escreva o nome do produto."
        return
    q = s.get("f_qtd") or 1
    data_iso = s["f_data"].isoformat() if s.get("f_data") else hoje_iso()
    cat = s.get("f_categoria")
    cat = None if cat in (None, "Automática") else cat
    ids = executar(lambda d: casa.registar_compra(d, nome, q, data_iso, hoje_iso(), cat),
                   f"Registou {fmt_qtd(q)} × {casa.nome_bonito(nome)}")
    if ids:
        s["aviso"] = f"Compra guardada: {fmt_qtd(q)} × {casa.nome_bonito(nome)} ({fmt_data(data_iso)})."
        s["f_produto"], s["f_qtd"] = None, 1


def acao_apagar_compra(cid: str):
    executar(lambda d: casa.remover_compras(d, [cid]))
    st.session_state["aviso"] = "Compra apagada."


def acao_editar(pid: str):
    s = st.session_state
    executar(lambda d: casa.editar_produto(d, pid, s.get(f"g_nome_{pid}"), s.get(f"g_cat_{pid}")))
    s["aviso"] = "Produto atualizado."


def acao_apagar_produto(pid: str, nome: str):
    executar(lambda d: casa.apagar_produto(d, pid))
    st.session_state["aviso"] = f"{nome} foi apagado."
    st.session_state.pop("ultima", None)


def acao_mudar_pin():
    s = st.session_state
    novo = (s.get("novo_pin") or "").strip()
    if novo and not acesso.pin_valido(novo):
        s["erro"] = "O código tem de ter 4 algarismos (ou ficar vazio para tirar o código)."
        return
    executar(lambda d: acesso.definir_pin(d["casa"], novo or None))
    s["aviso"] = "Código da casa alterado." if novo else "A casa deixou de ter código."
    s["novo_pin"] = ""


def ir_para(pagina: str):
    st.session_state["pagina"] = pagina


# ------------------------------------------------------------------ peças de interface
def cabecalho_pagina(titulo: str, subtitulo: str = ""):
    st.markdown(f"<p class='titulo-pag'>{esc(titulo)}</p>"
                + (f"<p class='subtitulo'>{esc(subtitulo)}</p>" if subtitulo else ""),
                unsafe_allow_html=True)


def mensagens():
    if erro := st.session_state.pop("erro", None):
        st.error(erro, icon=":material/error:")
    if aviso := st.session_state.pop("aviso", None):
        st.success(aviso, icon=":material/check_circle:")
    ult = st.session_state.get("ultima")
    if ult and time.time() - ult["t"] < 600:
        with st.container(key="linha_desfazer"):
            a, b = st.columns([5, 2], vertical_alignment="center")
            a.markdown(cinza(ult["texto"]), unsafe_allow_html=True)
            b.button("Desfazer", key="btn_desfazer", on_click=acao_desfazer, icon=":material/undo:")


def aviso_aprendizagem(an: dict):
    st.markdown(
        "<div class='aprender'><b>Ainda estou a aprender de quanto em quanto tempo compra cada produto</b>"
        f"<p>Registe as compras sempre que for ao supermercado. Com {pv.MIN_COMPRAS} compras de um produto "
        "(ou 2, ao fim de um mês) já consigo prever quando volta a precisar dele e preparar a lista do mês.</p></div>",
        unsafe_allow_html=True)
    st.progress(max(an["progresso"], 0.02))


def nome_com_icone(col, r: dict, extra_html: str = ""):
    col.markdown(f":material/{r['icone']}:&nbsp;&nbsp;{esc_md(r['nome'])}")
    if extra_html:
        col.markdown(extra_html, unsafe_allow_html=True)


def linha_info(chave: str, r: dict, extra: str, direita: str):
    with st.container(key=f"linha_{chave}"):
        a, b = st.columns([5, 2], vertical_alignment="center")
        nome_com_icone(a, r, extra)
        b.markdown(f"<div class='qtd'>{direita}</div>", unsafe_allow_html=True)


# ------------------------------------------------------------------ páginas
def pagina_inicio(dados: dict, an: dict):
    st.markdown(f"<p class='saudacao'>{saudacao()}</p>"
                "<p class='subtitulo'>Aqui está o estado das compras da tua casa.</p>",
                unsafe_allow_html=True)
    st.markdown(
        "<div class='cartoes'>"
        f"<div class='cartao'><div class='num'>{an['n_produtos']}</div><div class='rotulo'>Produtos registados</div></div>"
        f"<div class='cartao'><div class='num'>{len(an['em_breve'])}</div><div class='rotulo'>Produtos a comprar</div></div>"
        "</div>", unsafe_allow_html=True)
    mensagens()

    if an["n_produtos"] == 0:
        st.markdown("<div class='aprender'><b>Vamos começar</b><p>Sempre que fizer compras, registe o que "
                    "comprou e a data. Não precisa de contar o que gasta: eu aprendo de quanto em quanto "
                    "tempo compra cada coisa e depois preparo a lista do mês.</p></div>", unsafe_allow_html=True)
        st.button("Registar compra", icon=":material/add_shopping_cart:", on_click=ir_para, args=("Nova compra",))
        seccao_casa(dados)
        return

    if an["em_aprendizagem"]:
        aviso_aprendizagem(an)

    if an["em_breve"]:
        st.markdown("<p class='secao'>Próximas compras</p>", unsafe_allow_html=True)
        for r in an["em_breve"][:8]:
            linha_info(f"ini_{r['id']}", r, pilula_quando(r), fmt_qtd(r["habitual"]))
    elif an["n_prontos"]:
        st.markdown("<p class='secao'>Próximas compras</p>", unsafe_allow_html=True)
        st.markdown("Esta semana não deve ser preciso comprar nada. :material/sentiment_satisfied:")
        nxt = [r for r in an["mensal"]][:3]
        for r in nxt:
            linha_info(f"ini_{r['id']}", r, pilula_quando(r), fmt_qtd(r["habitual"]))

    st.write("")
    c1, c2 = st.columns(2)
    c1.button("Registar compra", icon=":material/add_shopping_cart:", on_click=ir_para, args=("Nova compra",))
    c2.button("Ver lista do mês", icon=":material/list_alt:", on_click=ir_para, args=("A comprar",))
    seccao_casa(dados)


def _linhas_compra(lista: list[dict], prefixo: str, campo_qtd: str):
    itens = []
    for r in lista:
        chave = f"{prefixo}_q_{r['id']}"
        extra = pilula_quando(r)
        if r["frequencia"]:
            extra += f" {cinza(r['frequencia'])}"
        with st.container(key=f"linha_{prefixo}_{r['id']}"):
            a, b, c = st.columns([4.2, 2, 2.2], vertical_alignment="center")
            nome_com_icone(a, r, extra)
            b.number_input("Quantidade", min_value=1, step=1, value=int(r[campo_qtd] or 1), key=chave,
                           label_visibility="collapsed")
            c.button("Comprei", key=f"{prefixo}_ok_{r['id']}", on_click=acao_comprei,
                     args=(r["id"], r["nome"], chave))
        itens.append((r["id"], chave))
    return itens


def pagina_comprar(dados: dict, an: dict):
    cabecalho_pagina("A comprar", "Carregue em «Comprei» e a compra fica registada com a data de hoje.")
    mensagens()
    if an["em_aprendizagem"]:
        aviso_aprendizagem(an)

    t_breve, t_mes = st.tabs([f"Em breve ({len(an['em_breve'])})", f"Lista do mês ({len(an['mensal'])})"])
    with t_breve:
        st.caption(f"O que costuma comprar nos próximos {pv.EM_BREVE} dias, na quantidade habitual.")
        if an["em_breve"]:
            itens = _linhas_compra(an["em_breve"], "b", "habitual")
            st.write("")
            st.button("Comprei tudo", key="tudo_b", icon=":material/done_all:", on_click=acao_comprei_tudo,
                      args=(itens,))
        elif an["n_prontos"]:
            st.markdown("Esta semana não deve ser preciso comprar nada. :material/sentiment_satisfied:")
        else:
            st.markdown("As sugestões aparecem aqui quando eu já souber o ritmo de compra dos produtos.")

    with t_mes:
        st.caption(f"Tudo o que costuma comprar nos próximos {pv.MES} dias, com a quantidade para o mês inteiro.")
        if an["mensal"]:
            itens = _linhas_compra(an["mensal"], "m", "quantidade_mes")
            st.write("")
            st.button("Comprei tudo", key="tudo_m", icon=":material/done_all:", on_click=acao_comprei_tudo,
                      args=(itens,))
            with st.expander("Lista em texto (para copiar ou enviar)", icon=":material/content_copy:"):
                texto = "\n".join(f"- {r['nome']}: {fmt_qtd(r['quantidade_mes'])}" for r in an["mensal"])
                st.code(f"Lista do mês ({fmt_data(hoje_iso())})\n{texto}", language=None)
        else:
            st.markdown("A lista do mês aparece aqui quando eu já souber o ritmo de compra dos produtos.")

    if an["a_aprender"]:
        st.markdown("<p class='secao'>Ainda a aprender</p>", unsafe_allow_html=True)
        st.caption("Estes produtos ainda têm poucas compras registadas. Pode marcá-los na página «Produtos».")
        for r in an["a_aprender"][:12]:
            linha_info(f"apr_{r['id']}", r, pilula_quando(r), "")


def pagina_produtos(dados: dict, an: dict):
    cabecalho_pagina("Produtos", "Carregue em + quando comprar: regista a quantidade habitual com a data de hoje.")
    mensagens()
    produtos = an["produtos"]
    if not produtos:
        st.markdown("Ainda não há produtos. Registe a primeira compra.")
        st.button("Registar compra", icon=":material/add_shopping_cart:", on_click=ir_para, args=("Nova compra",))
        return

    if len(produtos) > 12:
        procura = st.text_input("Procurar", placeholder="Procurar produto…", label_visibility="collapsed",
                                icon=":material/search:")
        if procura:
            alvo = casa.normalizar(procura)
            produtos = [r for r in produtos if alvo in casa.normalizar(r["nome"])]

    ordem = list(casa.CATEGORIAS)
    produtos = sorted(produtos, key=lambda r: (ordem.index(r["categoria"]) if r["categoria"] in ordem else 99,
                                               casa.normalizar(r["nome"])))
    cat_atual = None
    for r in produtos:
        if r["categoria"] != cat_atual:
            cat_atual = r["categoria"]
            st.markdown(f"<p class='secao'>{esc(cat_atual)}</p>", unsafe_allow_html=True)
        extra = pilula_quando(r)
        if r["frequencia"]:
            extra += f" {cinza(r['frequencia'])}"
        elif r["ultima"]:
            extra += f" {cinza('Última: ' + fmt_data(r['ultima']))}"
        with st.container(key=f"linha_p_{r['id']}"):
            a, c = st.columns([6, 1.3], vertical_alignment="center")
            nome_com_icone(a, r, extra)
            c.button("+", key=f"mais_{r['id']}", on_click=acao_comprei,
                     kwargs={"pid": r["id"], "nome": r["nome"], "quantidade": r["habitual"]},
                     help=f"Comprei hoje ({fmt_qtd(r['habitual'])})")

    st.write("")
    with st.expander("Histórico, mudar nome ou apagar", icon=":material/edit:"):
        nomes = {r["id"]: r["nome"] for r in an["produtos"]}
        pid = st.selectbox("Produto", list(nomes), format_func=nomes.get, key="g_produto")
        r = next(x for x in an["produtos"] if x["id"] == pid)
        st.markdown("**Compras registadas**")
        for c in casa.compras_recentes(dados, 12, pid):
            with st.container(key=f"linha_h_{c['id']}"):
                a, b, x = st.columns([4, 2, 1.3], vertical_alignment="center")
                a.markdown(fmt_data(c["data"]))
                b.markdown(f"<div class='qtd'>{fmt_qtd(c['quantidade'])}</div>", unsafe_allow_html=True)
                x.button("×", key=f"mais_apagar_{c['id']}", on_click=acao_apagar_compra, args=(c["id"],),
                         help="Apagar esta compra")
        st.markdown("**Nome e categoria**")
        st.text_input("Nome", value=r["nome"], key=f"g_nome_{pid}")
        cats = list(casa.CATEGORIAS)
        st.selectbox("Categoria", cats, index=cats.index(r["categoria"]) if r["categoria"] in cats else len(cats) - 1,
                     key=f"g_cat_{pid}")
        st.button("Guardar alterações", on_click=acao_editar, args=(pid,))
        st.markdown("**Apagar**")
        conf = st.checkbox(f"Sim, quero apagar «{r['nome']}» e todas as suas compras", key=f"g_conf_{pid}")
        st.button("Apagar produto", on_click=acao_apagar_produto, args=(pid, r["nome"]), disabled=not conf,
                  icon=":material/delete:")


def config_ia() -> dict | None:
    """Configuração da leitura de talões em st.secrets["ia"] (None = desativada)."""
    try:
        s = dict(st.secrets["ia"])
    except Exception:
        return None
    chave = s.get("chave_gemini") or s.get("api_key") or s.get("gemini_api_key")
    if not chave:
        return None
    return {"chave": chave, "modelo": s.get("modelo") or faturas.MODELO_PADRAO,
            "limite": int(s.get("limite_diario", 20))}


def _limpar_talao():
    st.session_state.pop("talao", None)
    st.session_state["talao_n"] = st.session_state.get("talao_n", 0) + 1  # repõe o carregador


def _texto(v) -> str:
    return "" if v is None or (isinstance(v, float) and v != v) else " ".join(str(v).split())


def seccao_talao(dados: dict):
    cfg = config_ia()
    if not cfg:
        st.markdown("<div class='aprender'><b>A leitura de talões ainda não está ativa</b><p>É preciso juntar "
                    "uma chave gratuita do Google Gemini nos «Secrets» da aplicação (veja o README). Entretanto, use "
                    "«Escrever à mão».</p></div>", unsafe_allow_html=True)
        return
    if st.session_state.get("talao"):
        revisao_talao(dados)
        return

    n = st.session_state.get("talao_n", 0)
    f = st.file_uploader("Fotografia ou PDF do talão", type=["jpg", "jpeg", "png", "webp", "pdf"],
                         key=f"talao_ficheiro_{n}")
    st.caption("No telemóvel pode tirar a fotografia na hora. Talão inteiro, direito, bem esticado e com boa luz.")
    if f is None:
        return
    usadas = casa.leituras_hoje(dados, hoje_iso())
    if usadas >= cfg["limite"]:
        st.warning(f"Já foram lidos {usadas} talões hoje nesta casa, que é o limite diário. "
                   "Amanhã pode ler mais; hoje use «Escrever à mão».")
        return
    if not st.button("Ler talão", icon=":material/document_scanner:", type="primary"):
        return
    nomes = [p["nome"] for p in dados["produtos"].values()]
    with st.spinner("A ler o talão… pode demorar uns segundos."):
        try:
            talao = faturas.ler_talao(f.getvalue(), f.name, f.type, nomes, cfg["chave"], agora().date(),
                                      cfg["modelo"])
        except faturas.ErroLeitura as e:
            st.error(str(e), icon=":material/error:")
            return
    executar(lambda d: casa.registar_leitura(d, hoje_iso()))
    if not talao["legivel"]:
        st.error("Não consegui encontrar artigos neste talão. Tente uma fotografia mais nítida, "
                 "com o talão todo à vista.", icon=":material/error:")
        return
    st.session_state["talao"] = {"loja": talao["loja"], "data": talao["data"],
                                 "linhas": faturas.linhas_para_revisao(dados, talao)}
    st.rerun()


def revisao_talao(dados: dict):
    import pandas as pd

    rev = st.session_state["talao"]
    n = st.session_state.get("talao_n", 0)
    titulo = "Confirme o talão" + (f" do {rev['loja']}" if rev["loja"] else "")
    st.markdown(f"<p class='secao'>{esc(titulo)}</p>", unsafe_allow_html=True)
    st.caption("Corrija os nomes e as quantidades, tire o visto ao que não interessa (sacos, por exemplo) "
               "e acrescente o que faltar na última linha.")

    hoje = agora().date()
    data_ini = datetime.fromisoformat(rev["data"]).date() if rev["data"] else hoje
    data = st.date_input("Data da compra", value=data_ini, key=f"talao_data_{n}", format="DD/MM/YYYY",
                         max_value=hoje)
    if not rev["data"]:
        st.caption("Não encontrei a data no talão: confirme-a acima.")

    df = pd.DataFrame(rev["linhas"], columns=["incluir", "produto", "quantidade", "associacao", "talao"])
    editado = st.data_editor(
        df, key=f"talao_tabela_{n}", num_rows="dynamic", hide_index=True,
        column_config={
            "incluir": st.column_config.CheckboxColumn("✓", default=True, width="small"),
            "produto": st.column_config.TextColumn("Produto", width="medium"),
            "quantidade": st.column_config.NumberColumn("Qtd.", min_value=1, max_value=99, step=1, default=1,
                                                        width="small"),
            "associacao": st.column_config.TextColumn("", disabled=True, width="small"),
            "talao": st.column_config.TextColumn("No talão", disabled=True),
        })

    linhas = []
    for _, r in editado.iterrows():
        nome = _texto(r.get("produto"))
        inc = r.get("incluir")
        incluido = True if inc is None or (isinstance(inc, float) and inc != inc) else bool(inc)
        if not nome or not incluido:
            continue
        q = r.get("quantidade")
        q = 1 if q is None or (isinstance(q, float) and q != q) else max(1, int(q))
        linhas.append({"produto": nome, "quantidade": q, "talao": _texto(r.get("talao"))})
    novos = sorted({l["produto"] for l in linhas if not casa.encontrar_produto(dados, l["produto"])},
                   key=casa.normalizar)
    resumo = f"Vai registar {len(linhas)} produto(s) com a data {data.strftime('%d/%m/%Y')}."
    if novos:
        resumo += f" Produtos novos: {', '.join(novos)}."
    st.markdown(cinza(resumo), unsafe_allow_html=True)

    a, b = st.columns([3, 2])
    if a.button(f"Guardar {len(linhas)} compras", icon=":material/check:", type="primary",
                disabled=not linhas, key=f"talao_guardar_{n}"):
        ids = executar(lambda d: casa.registar_varias(d, linhas, data.isoformat(), hoje_iso()),
                       f"Registou {len(linhas)} compras do talão")
        if ids:
            _limpar_talao()
            st.session_state["aviso"] = f"Talão guardado: {len(linhas)} compras registadas."
        st.rerun()
    b.button("Cancelar", key=f"talao_cancelar_{n}", on_click=_limpar_talao)


def pagina_nova_compra(dados: dict, an: dict):
    cabecalho_pagina("Registar compra", "Leia o talão de uma vez, ou escreva um produto de cada vez.")
    mensagens()
    t_talao, t_manual = st.tabs(["Ler talão", "Escrever à mão"])
    with t_talao:
        seccao_talao(dados)
    with t_manual:
        formulario_manual(dados)
    compras_recentes_lista(dados)

def formulario_manual(dados: dict):
    s = st.session_state
    s.setdefault("f_qtd", 1)
    s.setdefault("f_data", agora().date())

    nomes = sorted((p["nome"] for p in dados["produtos"].values()), key=casa.normalizar)
    st.selectbox("Produto", nomes, index=None, key="f_produto", accept_new_options=True,
                 placeholder="Escolha ou escreva um produto novo")
    a, b = st.columns(2)
    a.number_input("Quantidade", min_value=1, step=1, key="f_qtd")
    b.date_input("Data da compra", key="f_data", format="DD/MM/YYYY", max_value=agora().date())
    if s.get("f_produto") and not casa.encontrar_produto(dados, s["f_produto"]):
        st.selectbox("Categoria (produto novo)", ["Automática"] + list(casa.CATEGORIAS), key="f_categoria",
                     help=f"Automática: {casa.adivinhar_categoria(s['f_produto'])}")
    st.button("Guardar compra", icon=":material/check:", on_click=acao_registar_compra, type="primary")


def compras_recentes_lista(dados: dict):
    recentes = casa.compras_recentes(dados)
    if recentes:
        st.markdown("<p class='secao'>Compras recentes</p>", unsafe_allow_html=True)
        for c in recentes:
            p = dados["produtos"][c["produto_id"]]
            r = {"nome": p["nome"], "icone": casa.icone(p.get("categoria"))}
            extra = fmt_data(c["data"]) + (" · talão" if c.get("origem") == "talao" else "")
            linha_info(f"r_{c['id']}", r, cinza(extra), fmt_qtd(c["quantidade"]))


def seccao_casa(dados: dict):
    st.write("")
    info = dados.get("casa", {})
    with st.expander("A minha casa e cópia de segurança", icon=":material/home:"):
        st.markdown(f"Casa: **{esc_md(info.get('email', ''))}** · "
                    f"{'com código' if acesso.tem_pin(info) else 'sem código'}")
        st.caption("Para partilhar com a família: envie o link do site, o e-mail da casa e o código. "
                   "Quem entrar com eles vê e edita a mesma lista.")
        a, b = st.columns([3, 2], vertical_alignment="bottom")
        a.text_input("Novo código (vazio = sem código)", type="password", max_chars=4, key="novo_pin")
        b.button("Mudar código", on_click=acao_mudar_pin)

        st.caption(f"Os dados desta casa estão guardados {gestor.descricao}.")
        copia = {k: v for k, v in dados.items() if k != "casa"}
        st.download_button("Descarregar cópia (JSON)", json.dumps(copia, ensure_ascii=False, indent=1),
                           file_name=f"despensa-{hoje_iso()}.json", mime="application/json",
                           icon=":material/download:")
        f = st.file_uploader("Repor a partir de uma cópia", type=["json"])
        if f is not None:
            try:
                novos = casa.preparar(json.loads(f.getvalue().decode("utf-8")), hoje_iso())
                assert isinstance(novos.get("produtos"), dict) and isinstance(novos.get("compras"), list)
            except Exception:
                st.error("Este ficheiro não é uma cópia válida da despensa.")
            else:
                st.warning(f"A cópia tem {len(novos['produtos'])} produtos e {len(novos['compras'])} compras. "
                           "Repor substitui os dados atuais desta casa.")
                if st.button("Repor esta cópia", icon=":material/restore:"):
                    def repor(d):
                        guardar = d["casa"]
                        d.clear()
                        d.update(novos)
                        d["casa"] = guardar  # o e-mail e o código continuam os desta casa
                    executar(repor)
                    st.session_state["aviso"] = "Cópia reposta."
                    st.rerun()
        st.write("")
        st.button("Sair desta casa", icon=":material/logout:", on_click=sair)


# ------------------------------------------------------------------ principal
PAGINAS = {
    "Início": (":material/home:", pagina_inicio),
    "A comprar": (":material/shopping_cart:", pagina_comprar),
    "Produtos": (":material/kitchen:", pagina_produtos),
    "Nova compra": (":material/add_shopping_cart:", pagina_nova_compra),
}


def _manter_pagina():
    if st.session_state.get("pagina") is None:  # carregou na página já escolhida
        st.session_state["pagina"] = st.session_state.get("pagina_ant", "Início")
    st.session_state["pagina_ant"] = st.session_state["pagina"]


def main():
    st.session_state.setdefault("pagina", "Início")
    if not st.session_state.get("casa_id") and not entrar_por_link():
        ecra_entrada()
        return

    st.markdown("<div class='marca'>A minha despensa</div>", unsafe_allow_html=True)
    try:
        dados = armazem().carregar()
    except storage.ErroArmazenamento as e:
        st.error(f"Não consegui abrir os dados. {e}", icon=":material/cloud_off:")
        st.button("Tentar outra vez", icon=":material/refresh:")
        st.stop()
    if dados is None:  # a casa foi apagada noutro lado
        sair()
        st.rerun()
    an = pv.analisar(dados, agora().date())

    n = len(an["em_breve"])
    st.segmented_control(
        "Navegação", list(PAGINAS), key="pagina", on_change=_manter_pagina, label_visibility="collapsed",
        format_func=lambda p: f"{PAGINAS[p][0]} {p}" + (f" ({n})" if p == "A comprar" and n else ""))
    PAGINAS[st.session_state["pagina"]][1](dados, an)


main()
