from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit


Resolver = Callable[[str, int], Awaitable[set[str]]]


async def _resolve(host: str, port: int) -> set[str]:
    loop = asyncio.get_running_loop()
    answers = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return {answer[4][0] for answer in answers}


async def validate_agent_url(
    value: str,
    *,
    allow_private: bool = False,
    resolver: Resolver = _resolve,
) -> str:
    raw = value.strip()
    parsed = urlsplit(raw if "://" in raw else f"http://{raw}")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Agent URL must use http or https")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("Agent URL must contain a safe hostname")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("Agent URL contains an invalid port") from exc

    try:
        addresses = {str(ipaddress.ip_address(parsed.hostname))}
    except ValueError:
        try:
            addresses = await resolver(parsed.hostname, port)
        except (OSError, socket.gaierror) as exc:
            raise ValueError("Agent URL hostname cannot be resolved") from exc
    if not addresses:
        raise ValueError("Agent URL hostname cannot be resolved")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        always_blocked = (
            ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or (ip.is_reserved and not (allow_private and ip.is_loopback))
        )
        if always_blocked or ((ip.is_private or ip.is_loopback) and not allow_private):
            raise ValueError("Agent URL resolves to a blocked address")

    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
