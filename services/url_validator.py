import socket, ipaddress
from urllib.parse import urlparse

BLOCKED = [
    ipaddress.ip_network("0.0.0.0/8"), ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"), ipaddress.ip_network("fe80::/10")
]

PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be"],
    "facebook": ["facebook.com", "fb.watch"],
    "instagram": ["instagram.com"],
    "tiktok": ["tiktok.com"],
    "pinterest": ["pinterest.com", "pin.it"],
    "twitter": ["twitter.com", "x.com"]
}

def validate_and_sanitize_url(url: str):
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ["http", "https"]: raise ValueError("Invalid scheme.")
    hostname = parsed.hostname
    if not hostname: raise ValueError("Invalid hostname.")
    addr_info = socket.getaddrinfo(hostname, None)
    for addr in addr_info:
        ip = ipaddress.ip_address(addr[4][0])
        for b in BLOCKED:
            if ip in b: raise ValueError(f"Restricted host: {ip}")
    plat = "custom"
    for p, domains in PLATFORMS.items():
        if any(hostname == d or hostname.endswith("." + d) for d in domains):
            plat = p; break
    return url.strip(), plat