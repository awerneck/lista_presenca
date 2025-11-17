import time
import secrets

TOKEN_VALIDO = None
EXPIRA = 0


def gerar_token():
    global TOKEN_VALIDO, EXPIRA
    TOKEN_VALIDO = secrets.token_hex(3)
    EXPIRA = time.time() + 60  # expira em 60s
    return TOKEN_VALIDO


def validar_token(token):
    return token == TOKEN_VALIDO and time.time() < EXPIRA


def token_atual():
    if time.time() >= EXPIRA:
        return gerar_token()
    return TOKEN_VALIDO
