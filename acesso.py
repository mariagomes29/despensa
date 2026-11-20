"""Acesso simples por e-mail da casa (+ código opcional de 4 algarismos).

Não é um sistema de contas com palavra-passe: serve para cada família ter a sua cozinha
separada e para ninguém entrar na casa errada por engano.

* Cada casa é identificada por um código derivado do e-mail (não se vê o e-mail no nome do ficheiro).
* O código de 4 algarismos é guardado apenas como "hash" (PBKDF2 com sal), nunca em claro.
* A «chave» é um segredo aleatório da casa que vai no link do browser, para não ter de
  voltar a escrever o e-mail sempre que se abre a aplicação.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")
_ID = re.compile(r"^[0-9a-f]{20}$")
ITERACOES = 120_000


def normalizar_email(email: str) -> str:
    return str(email or "").strip().lower()


def email_valido(email: str) -> bool:
    return bool(_EMAIL.match(normalizar_email(email)))


def pin_valido(pin: str) -> bool:
    return bool(re.fullmatch(r"\d{4}", str(pin or "")))


def casa_id(email: str) -> str:
    return hashlib.sha256(("despensa:" + normalizar_email(email)).encode()).hexdigest()[:20]


def id_valido(cid: str) -> bool:
    return bool(_ID.match(str(cid or "")))


def _hash_pin(pin: str, sal: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(sal), ITERACOES).hex()


def nova_casa(email: str, pin: str | None) -> dict:
    """Bloco "casa" para um ficheiro novo."""
    info = {"email": normalizar_email(email), "chave": secrets.token_urlsafe(18), "pin_hash": "", "sal": ""}
    if pin:
        info["sal"] = secrets.token_hex(16)
        info["pin_hash"] = _hash_pin(pin, info["sal"])
    return info


def tem_pin(info: dict) -> bool:
    return bool(info.get("pin_hash"))


def verificar_pin(pin: str, info: dict) -> bool:
    if not tem_pin(info):
        return True
    if not pin_valido(pin):
        return False
    return hmac.compare_digest(_hash_pin(pin, info["sal"]), info["pin_hash"])


def definir_pin(info: dict, pin: str | None):
    """Muda (ou remove, com pin vazio) o código da casa."""
    if pin:
        info["sal"] = secrets.token_hex(16)
        info["pin_hash"] = _hash_pin(pin, info["sal"])
    else:
        info["sal"] = info["pin_hash"] = ""


def token_link(cid: str, info: dict) -> str:
    return f"{cid}.{info['chave']}"


def ler_token(token: str) -> tuple[str, str] | None:
    if not token or "." not in token:
        return None
    cid, chave = token.split(".", 1)
    return (cid, chave) if id_valido(cid) and chave else None


def chave_correta(info: dict, chave: str) -> bool:
    return bool(info.get("chave")) and hmac.compare_digest(info["chave"], chave)
