# qr_token.py
import secrets
from datetime import datetime, timedelta

TOKEN = None
EXPIRY = None
TTL_SECONDS = 60  # token válido por 60s

def _now():
    return datetime.utcnow()

def gerar_token(ttl_seconds: int = None):
    global TOKEN, EXPIRY
    ttl = TTL_SECONDS if ttl_seconds is None else ttl_seconds
    TOKEN = secrets.token_urlsafe(12)
    EXPIRY = _now() + timedelta(seconds=ttl)
    return TOKEN

def token_atual():
    global TOKEN, EXPIRY
    if TOKEN is None or EXPIRY is None or _now() >= EXPIRY:
        return gerar_token()
    return TOKEN

def validar_token(token: str):
    global TOKEN, EXPIRY
    if not token or TOKEN is None:
        return False
    if token != TOKEN:
        return False
    if _now() >= EXPIRY:
        return False
    return True

def segundos_restantes():
    global EXPIRY
    if EXPIRY is None:
        return 0
    diff = (EXPIRY - _now()).total_seconds()
    return int(diff) if diff > 0 else 0

def invalidar_token():
    return gerar_token()
