import ipaddress
import socket
from urllib.parse import urlsplit

from email_validator import validate_email


def validate_public_url(url: str, *, resolve: bool = True) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTPS URLs without credentials are permitted")
    if parsed.port not in (None, 443):
        raise ValueError("Only HTTPS port 443 is permitted")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private destination blocked")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = (
            [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, 443)]
            if resolve
            else []
        )
    if any(not addr.is_global for addr in addresses):
        raise ValueError("Private destination blocked")
    return url


def normalize_email(value: str) -> str:
    return validate_email(value.strip(), check_deliverability=False).normalized.lower()
