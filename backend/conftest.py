"""Configuração compartilhada da suíte (apps/core/tests/ e tests/regression/).

O throttle do DRF conta requisições no cache. Como não há `CACHES` configurado, o Django
usa `LocMemCache` — um dicionário de processo que sobrevive de um teste para o outro. E o
`AnonRateThrottle` chaveia por IP, que na suíte é sempre `127.0.0.1`: sem limpar, o contador
de um teste de limite estoura o teste seguinte, e a ordem dos testes passa a importar.

A suíte também é hermética por padrão: conexões para fora da máquina falham antes de DNS ou
handshake. Loopback e Unix sockets seguem disponíveis para os testes PostgreSQL/pgvector e para
servidores locais deliberados. Integração com fornecedor se testa no limite do adapter, com mock.
"""

import ipaddress
import socket

import pytest
from django.core.cache import cache
from django.test import override_settings

# **A suíte nunca fala com o bucket.** `STORAGES["default"]` passou a ser escolhido por
# `GCS_MEDIA_BUCKET` (FDD 017), e uma variável de ambiente vazada para o ambiente de teste
# faria dezenas de testes gravarem objeto de verdade — os que sobem documento e os nove que
# fazem `override_settings(MEDIA_ROOT=...)`, que com storage remoto viram no-op silencioso.
# Fixar aqui é a única forma de a suíte afirmar sobre disco sem depender de quem a invoca.
_ARMAZENAMENTO_LOCAL = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
)

_SOCKET_CONNECT = socket.socket.connect
_SOCKET_CONNECT_EX = socket.socket.connect_ex
_SOCKET_SENDTO = socket.socket.sendto
_SOCKET_SENDMSG = getattr(socket.socket, "sendmsg", None)
_CREATE_CONNECTION = socket.create_connection
_GETADDRINFO = socket.getaddrinfo


class ExternalNetworkAccessBlocked(RuntimeError):
    """Um teste tentou atravessar o limite do processo sem substituir o provider."""


def _assert_local_connection(address: object) -> None:
    """Aceita loopback/Unix socket e recusa qualquer destino que possa sair da máquina."""
    if not isinstance(address, tuple):
        # AF_UNIX usa um caminho (str/bytes), não um par host/porta.
        return
    host = address[0]
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="replace")
    host_text = str(host).strip("[]")
    try:
        local = ipaddress.ip_address(host_text).is_loopback
    except ValueError:
        local = host_text.lower() == "localhost"
    if local:
        return
    raise ExternalNetworkAccessBlocked(
        "External network access is blocked during tests. "
        f"Attempted destination: {host_text!r}. Mock the provider client; "
        "only loopback and Unix sockets are allowed. Blocked before DNS resolution or socket I/O."
    )


def _guarded_connect(sock: socket.socket, address: object) -> None:
    _assert_local_connection(address)
    _SOCKET_CONNECT(sock, address)  # type: ignore[arg-type]


def _guarded_connect_ex(sock: socket.socket, address: object) -> int:
    _assert_local_connection(address)
    return _SOCKET_CONNECT_EX(sock, address)  # type: ignore[arg-type]


def _guarded_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
    # `socket.create_connection` resolveria DNS antes de alcançar `socket.connect`; barrar aqui
    # garante falha determinística também para hostnames inexistentes ou lentos.
    _assert_local_connection(address)
    return _CREATE_CONNECTION(address, *args, **kwargs)


def _guarded_getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
    # `asyncio` resolve em executor antes de chamar `socket.connect`; esta é a cerca que mantém o
    # caminho async tão hermético quanto `socket.create_connection`.
    if host is not None:
        _assert_local_connection((host, 0))
    return _GETADDRINFO(host, *args, **kwargs)


def _guarded_sendto(sock: socket.socket, data, *args):  # type: ignore[no-untyped-def]
    # Assinaturas: sendto(data, address) e sendto(data, flags, address).
    if args:
        _assert_local_connection(args[-1])
    return _SOCKET_SENDTO(sock, data, *args)


def _guarded_sendmsg(sock: socket.socket, buffers, *args):  # type: ignore[no-untyped-def]
    # Assinatura: sendmsg(buffers[, ancdata[, flags[, address]]]). Sem `address`, o socket já foi
    # conectado e passou por `_guarded_connect`.
    if len(args) >= 3:
        _assert_local_connection(args[2])
    if _SOCKET_SENDMSG is None:  # pragma: no cover - só plataformas sem sendmsg
        raise AttributeError("socket.sendmsg indisponível")
    return _SOCKET_SENDMSG(sock, buffers, *args)


def pytest_configure() -> None:
    _ARMAZENAMENTO_LOCAL.enable()
    socket.getaddrinfo = _guarded_getaddrinfo
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    socket.socket.sendto = _guarded_sendto
    if _SOCKET_SENDMSG is not None:
        socket.socket.sendmsg = _guarded_sendmsg
    socket.create_connection = _guarded_create_connection


def pytest_unconfigure() -> None:
    socket.create_connection = _CREATE_CONNECTION
    if _SOCKET_SENDMSG is not None:
        socket.socket.sendmsg = _SOCKET_SENDMSG
    socket.socket.sendto = _SOCKET_SENDTO
    socket.socket.connect_ex = _SOCKET_CONNECT_EX
    socket.socket.connect = _SOCKET_CONNECT
    socket.getaddrinfo = _GETADDRINFO
    _ARMAZENAMENTO_LOCAL.disable()


@pytest.fixture(autouse=True)
def clear_throttle_cache() -> None:
    cache.clear()
