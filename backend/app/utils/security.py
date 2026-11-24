"""Security, SSRF protection, IP validation, and path traversal guards."""
import ipaddress
import os
import re
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Private, link-local, and reserved IP networks to block for SSRF prevention
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),       # Link-local & Cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),       # Carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),        # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),     # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),      # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),         # Multicast
    ipaddress.ip_network("240.0.0.0/4"),         # Reserved
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),             # Loopback
    ipaddress.ip_network("fc00::/7"),            # Unique local address
    ipaddress.ip_network("fe80::/10"),           # Link-local
    ipaddress.ip_network("ff00::/8"),            # Multicast
    ipaddress.ip_network("::ffff:0:0/96"),       # IPv4-mapped IPv6
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
    "metadata",
}


def is_ip_allowed(ip_str: str) -> bool:
    """Check if an IP address is a safe public IP (not loopback, private, or metadata)."""
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check against blocked networks
        for net in BLOCKED_NETWORKS:
            if ip in net:
                return False
        # Also check standard ip properties
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
        return True
    except ValueError:
        return False


def validate_target_url(url: str) -> None:
    """
    Validate target URL for SSRF vulnerabilities and protocol safety.
    Raises ValueError if URL is unsafe or prohibited.
    """
    if not url:
        raise ValueError("URL cannot be empty.")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL structure: {e}")

    # Restrict scheme strictly to http and https
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Prohibited protocol '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must have a valid hostname.")

    hostname_clean = hostname.strip().lower()

    if hostname_clean in BLOCKED_HOSTNAMES:
        raise ValueError(f"Access to host '{hostname}' is forbidden.")

    # Resolve hostname to verify IP addresses
    try:
        # Resolve all IPv4 and IPv6 addresses for the hostname
        addr_info = socket.getaddrinfo(hostname_clean, None)
        if not addr_info:
            raise ValueError(f"Could not resolve host '{hostname}'.")

        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            if not is_ip_allowed(ip_str):
                raise ValueError(
                    f"Forbidden destination: '{hostname}' resolves to restricted/internal IP {ip_str}."
                )
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for '{hostname}': {e}")


def sanitize_filename(name: str, max_length: int = 150) -> str:
    """
    Sanitize filename to prevent path traversal and remove invalid filesystem characters.
    """
    # Remove null bytes, directory separators, and control characters
    cleaned = re.sub(r'[\x00-\x1f\x7f/\\:*"<>|?]', "", name)
    # Remove leading dots to prevent hidden files or traversal
    cleaned = cleaned.lstrip(".")
    # Replace whitespace and multiple spaces/underscores
    cleaned = re.sub(r"[\s_]+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "paper"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    if not cleaned.lower().endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


def safe_resolve_path(base_dir: Path, filename: str) -> Path:
    """
    Ensure the resolved path stays strictly within base_dir (preventing directory traversal).
    """
    clean_name = os.path.basename(filename)
    resolved = (base_dir / clean_name).resolve()
    base_resolved = base_dir.resolve()
    if not str(resolved).startswith(str(base_resolved)):
        raise ValueError("Path traversal attempt detected.")
    return resolved
