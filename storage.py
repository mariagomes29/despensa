"""Guardar os dados num ficheiro JSON por casa.

    local:   dados/casas/<id-da-casa>.json
    GitHub:  <pasta>/<id-da-casa>.json  num repositório privado (com histórico de versões)

O <id-da-casa> é derivado do e-mail (ver acesso.py), por isso as famílias nunca se misturam.

* FicheiroLocal      -> bom para testar no computador ou em alojamentos com disco persistente.
* RepositorioGitHub  -> recomendado no Streamlit Community Cloud, onde o disco é apagado
                        sempre que a aplicação reinicia ou adormece.
* Armazem            -> cache, bloqueio e repetição em caso de conflito, para UMA casa.
* Gestor             -> dá o Armazem de cada casa (partilhado por todas as sessões).
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path


class ErroArmazenamento(Exception):
    """Erro com mensagem já pronta para mostrar à utilizadora."""


class _Conflito(Exception):
    """O ficheiro mudou desde a última leitura (ou já existia ao criar)."""


# --------------------------------------------------------------------------- local
class FicheiroLocal:
    descricao = "neste computador/servidor (ficheiro local)"

    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.copia = self.caminho.with_suffix(".json.bak")

    def ler(self):
        if not self.caminho.exists():
            return None, None
        try:
            return json.loads(self.caminho.read_text(encoding="utf-8")), self.caminho.stat().st_mtime_ns
        except (OSError, json.JSONDecodeError) as e:
            if self.copia.exists():  # ficheiro estragado: usa a última cópia boa
                return json.loads(self.copia.read_text(encoding="utf-8")), None
            raise ErroArmazenamento(f"Não consegui ler os dados ({e}).") from e

    def gravar(self, dados, ref, criar=False):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        existe = self.caminho.exists()
        if (criar and existe) or (ref is not None and existe and self.caminho.stat().st_mtime_ns != ref):
            raise _Conflito
        texto = json.dumps(dados, ensure_ascii=False, indent=1)
        fd, tmp = tempfile.mkstemp(dir=self.caminho.parent, prefix=".casa-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(texto)
                f.flush()
                os.fsync(f.fileno())
            if existe:
                shutil.copy2(self.caminho, self.copia)
            os.replace(tmp, self.caminho)  # troca atómica: nunca fica meio escrito
        except OSError as e:
            Path(tmp).unlink(missing_ok=True)
            raise ErroArmazenamento(f"Não consegui gravar os dados ({e}).") from e
        return self.caminho.stat().st_mtime_ns


# -------------------------------------------------------------------------- github
class RepositorioGitHub:
    descricao = "no GitHub (repositório privado, com histórico)"

    def __init__(self, sessao, repo: str, caminho: str, ramo: str = "main"):
        self.s = sessao
        self.url = f"https://api.github.com/repos/{repo}/contents/{caminho.lstrip('/')}"
        self.ramo = ramo

    def _pedido(self, metodo, **kw):
        try:
            return self.s.request(metodo, self.url, timeout=15, **kw)
        except Exception as e:  # sem rede, DNS, timeout…
            raise ErroArmazenamento("Sem ligação ao GitHub. Verifique a internet e tente outra vez.") from e

    @staticmethod
    def _verificar(r):
        if r.status_code < 300:
            return
        msg = {401: "O token do GitHub não é válido ou expirou.",
               403: "O token do GitHub não tem permissão para escrever no repositório.",
               404: "Repositório do GitHub não encontrado (confirme o nome e o token)."}
        raise ErroArmazenamento(msg.get(r.status_code, f"Erro do GitHub ({r.status_code})."))

    def ler(self):
        r = self._pedido("GET", params={"ref": self.ramo})
        if r.status_code == 404:
            return None, None
        self._verificar(r)
        j = r.json()
        if j.get("content"):
            texto = base64.b64decode(j["content"]).decode("utf-8")
        else:  # ficheiros > 1 MB vêm sem conteúdo; pede a versão "raw"
            r2 = self._pedido("GET", params={"ref": self.ramo},
                              headers={"Accept": "application/vnd.github.raw+json"})
            self._verificar(r2)
            texto = r2.text
        return json.loads(texto), j["sha"]

    def gravar(self, dados, ref, criar=False):
        texto = json.dumps(dados, ensure_ascii=False, indent=1)
        corpo = {"message": "Atualizar despensa",
                 "content": base64.b64encode(texto.encode("utf-8")).decode("ascii"),
                 "branch": self.ramo}
        if ref and not criar:
            corpo["sha"] = ref
        r = self._pedido("PUT", json=corpo)
        if r.status_code == 409 or (r.status_code == 422 and "sha" in r.text):
            raise _Conflito
        self._verificar(r)
        return r.json()["content"]["sha"]


def sessao_github(token: str):
    import requests
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                      "X-GitHub-Api-Version": "2022-11-28", "Cache-Control": "no-cache"})
    return s


# ------------------------------------------------------------------------- armazém
class Armazem:
    """Ficheiro de UMA casa, com cache, bloqueio e gravação com repetição."""

    def __init__(self, backend, preparar=None, validade_cache: float = 10.0):
        self.backend = backend
        self.preparar = preparar or (lambda d: d)
        self.validade = validade_cache
        self._lock = threading.RLock()
        self._dados = None
        self._ref = None
        self._t = None

    def _ler_fresco(self):
        dados, ref = self.backend.ler()
        self._dados, self._ref, self._t = self.preparar(dados), ref, time.monotonic()

    def carregar(self) -> dict | None:
        """Dados da casa, ou None se a casa ainda não existir."""
        with self._lock:
            if self._t is None or time.monotonic() - self._t > self.validade:
                self._ler_fresco()
            return copy.deepcopy(self._dados)

    def criar(self, dados: dict):
        with self._lock:
            try:
                ref = self.backend.gravar(dados, None, criar=True)
            except _Conflito:
                raise ErroArmazenamento("Esta casa já existe. Volte a entrar com o e-mail.") from None
            self._dados, self._ref, self._t = copy.deepcopy(dados), ref, time.monotonic()

    def atualizar(self, alteracao, tentativas: int = 3):
        """Aplica `alteracao(dados)` e grava. Devolve o que `alteracao` devolver.

        Tenta primeiro com a versão em cache (rápido); se outra pessoa da casa tiver gravado
        entretanto, volta a ler e repete a alteração sobre os dados mais recentes.
        """
        with self._lock:
            if self._t is None:
                self._ler_fresco()
            for i in range(tentativas):
                if self._dados is None:
                    raise ErroArmazenamento("Esta casa já não existe.")
                dados = copy.deepcopy(self._dados)
                resultado = alteracao(dados)
                try:
                    ref = self.backend.gravar(dados, self._ref)
                except _Conflito:
                    time.sleep(0.4 * (i + 1))
                    self._ler_fresco()
                    continue
                self._dados, self._ref, self._t = dados, ref, time.monotonic()
                return resultado
            raise ErroArmazenamento("Os dados mudaram noutro aparelho ao mesmo tempo. Tente outra vez.")


# -------------------------------------------------------------------------- gestor
_ID_SEGURO = re.compile(r"^[0-9a-f]{8,64}$")


class Gestor:
    """Um Armazem por casa. `fabrica(nome_ficheiro)` cria o backend de cada ficheiro."""

    def __init__(self, fabrica, descricao: str, preparar=None):
        self._fabrica = fabrica
        self.descricao = descricao
        self._preparar = preparar
        self._casas: dict[str, Armazem] = {}
        self._lock = threading.Lock()

    def casa(self, casa_id: str) -> Armazem:
        if not _ID_SEGURO.match(casa_id or ""):
            raise ErroArmazenamento("Identificador de casa inválido.")
        with self._lock:
            if casa_id not in self._casas:
                self._casas[casa_id] = Armazem(self._fabrica(f"{casa_id}.json"), self._preparar)
            return self._casas[casa_id]


def gestor_local(pasta: str | Path, preparar=None) -> Gestor:
    pasta = Path(pasta)
    return Gestor(lambda nome: FicheiroLocal(pasta / nome), FicheiroLocal.descricao, preparar)


def gestor_github(token: str, repo: str, pasta: str = "casas", ramo: str = "main",
                  preparar=None, sessao=None) -> Gestor:
    sessao = sessao or sessao_github(token)
    pasta = pasta.strip("/")
    return Gestor(lambda nome: RepositorioGitHub(sessao, repo, f"{pasta}/{nome}" if pasta else nome, ramo),
                  RepositorioGitHub.descricao, preparar)
