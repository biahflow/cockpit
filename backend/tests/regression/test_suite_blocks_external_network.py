"""Regressões da cerca global de rede da suíte.

A guarda mora no ``conftest.py`` porque precisa alcançar todo teste antes de qualquer cliente HTTP.
Estes casos exercitam o contrato por fora: destino externo falha antes de DNS/conexão; loopback,
necessário ao job PostgreSQL/pgvector, continua disponível.
"""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest


def test_suite_blocks_external_hostname_with_clear_error() -> None:
    with pytest.raises(RuntimeError, match="External network access is blocked during tests"):
        socket.create_connection(("example.invalid", 443), timeout=0.01)


def test_suite_blocks_external_dns_resolution() -> None:
    with pytest.raises(RuntimeError, match="before DNS resolution"):
        socket.getaddrinfo("example.invalid", 443)


def test_suite_blocks_async_external_connection_before_dns() -> None:
    async def connect() -> None:
        await asyncio.open_connection("example.invalid", 443)

    with pytest.raises(RuntimeError, match="External network access is blocked during tests"):
        asyncio.run(connect())


def test_suite_blocks_httpx_async_client_before_dns() -> None:
    async def request() -> None:
        async with httpx.AsyncClient(trust_env=False) as client:
            await client.get("https://example.invalid")

    with pytest.raises(RuntimeError, match="External network access is blocked during tests"):
        asyncio.run(request())


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_suite_blocks_direct_external_socket_connections(method: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(RuntimeError, match="Mock the provider client"):
            getattr(client, method)(("203.0.113.1", 443))


def test_suite_blocks_external_udp_sendto() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(RuntimeError, match="External network access is blocked during tests"):
            client.sendto(b"probe", ("203.0.113.1", 53))


@pytest.mark.skipif(not hasattr(socket.socket, "sendmsg"), reason="sendmsg indisponível")
def test_suite_blocks_external_udp_sendmsg() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(RuntimeError, match="External network access is blocked during tests"):
            client.sendmsg([b"probe"], [], 0, ("203.0.113.1", 53))


def test_suite_allows_loopback_connections() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)

        with socket.create_connection(server.getsockname(), timeout=1) as client:
            accepted, _ = server.accept()
            with accepted:
                client.sendall(b"ok")
                assert accepted.recv(2) == b"ok"


def test_suite_allows_loopback_dns_and_udp() -> None:
    assert socket.getaddrinfo("localhost", 80)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(b"ok", receiver.getsockname())
            assert receiver.recvfrom(2)[0] == b"ok"
