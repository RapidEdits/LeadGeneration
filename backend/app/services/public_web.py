"""Small public-web reader. Every connection pins a validated public IP.

No cookies, credentials, browser execution, proxy inheritance, or unlimited downloads.
"""
import http.client
import ipaddress
import json
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from email_validator import EmailNotValidError, validate_email

USER_AGENT = "LeadGeneratorBot/1.0"
MAX_BYTES = 1_000_000


def public_target(url: str) -> tuple[str, str, int, str]:
    p = urlsplit(url)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("Only public HTTP(S) websites without credentials are supported")
    port = p.port or (443 if p.scheme == "https" else 80)
    if port not in {80, 443}:
        raise ValueError("Only standard website ports are supported")
    hostname = p.hostname.encode("idna").decode("ascii")
    addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    ips = {row[4][0] for row in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("Private, local and reserved network addresses are not allowed")
    path = urlunsplit(("", "", p.path or "/", p.query, ""))
    return hostname, sorted(ips)[0], port, path


def _request(url: str) -> tuple[int, dict, str]:
    host, ip, port, path = public_target(url)
    connection_type = http.client.HTTPSConnection if urlsplit(url).scheme == "https" else http.client.HTTPConnection
    conn = connection_type(host, port=port, timeout=8)
    # Pin the validated destination while preserving Host and TLS hostname checks.
    conn._create_connection = lambda address, timeout, source_address=None: socket.create_connection(
        (ip, port), timeout, source_address
    )
    try:
        conn.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        response = conn.getresponse()
        headers = {k.lower(): v for k, v in response.getheaders()}
        chunks, size, deadline = [], 0, time.monotonic() + 12
        while True:
            chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES or time.monotonic() > deadline:
                raise ValueError("Website response exceeded the download budget")
            chunks.append(chunk)
        if headers.get("content-encoding", "identity") != "identity":
            raise ValueError("Unsupported compressed response")
        return response.status, headers, b"".join(chunks).decode("utf-8", errors="replace")
    finally:
        conn.close()


class PublicWeb:
    def __init__(self):
        self.robots: dict[str, RobotFileParser] = {}

    def fetch(self, url: str) -> tuple[str, str]:
        for _ in range(4):
            p = urlsplit(url)
            origin = f"{p.scheme}://{p.netloc}"
            if origin not in self.robots:
                code, _, body = _request(origin + "/robots.txt")
                rp = RobotFileParser()
                if code in {404, 410}:
                    rp.parse([])
                elif code == 200:
                    rp.parse(body.splitlines())
                else:
                    raise ValueError("Website robots policy could not be verified")
                self.robots[origin] = rp
            if not self.robots[origin].can_fetch(USER_AGENT, url):
                raise ValueError("Website robots policy disallows this page")
            delay = self.robots[origin].crawl_delay(USER_AGENT) or 0
            if delay > 10:
                raise ValueError("Website crawl delay exceeds this run's budget")
            time.sleep(max(0.5, delay))
            code, headers, body = _request(url)
            if code in {301, 302, 303, 307, 308}:
                url = urljoin(url, headers.get("location", ""))
                continue
            if code != 200:
                raise ValueError(f"Website returned HTTP {code}")
            if not any(t in headers.get("content-type", "") for t in ("text/html", "text/plain", "application/xhtml+xml")):
                raise ValueError("Only HTML and plain text pages are supported")
            return url, body
        raise ValueError("Too many redirects")


class Page(HTMLParser):
    def __init__(self, html: str, url: str):
        super().__init__(convert_charrefs=True)
        self.url, self.parts, self.links, self.title_parts = url, [], [], []
        self.hidden, self.in_title, self.structured = 0, False, []
        self.json_script, self.script_parts = False, []
        self.feed(html)
        self.text = re.sub(r"\s+", " ", " ".join(self.parts))[:60000]
        self.title = " ".join(self.title_parts).strip()[:255]

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag == "script" and attr.get("type") == "application/ld+json":
            self.json_script, self.script_parts = True, []
        if tag == "title":
            self.in_title = True
        if tag == "a" and attr.get("href"):
            self.links.append(urljoin(self.url, attr["href"]))

    def handle_endtag(self, tag):
        if tag == "script" and self.json_script:
            try:
                self.structured.append(json.loads("".join(self.script_parts)))
            except (ValueError, RecursionError):
                pass
            self.json_script = False
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.json_script:
            self.script_parts.append(data)
        if not self.hidden:
            self.parts.append(data)
            if self.in_title:
                self.title_parts.append(data)

    def emails(self) -> list[str]:
        observed = self.text + " " + " ".join(unquote(s[7:].split("?")[0]) for s in self.links if s.startswith("mailto:"))
        emails = set()
        for match in re.findall(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", observed):
            try:
                email = validate_email(match.strip("."), check_deliverability=False).normalized.lower()
                if not email.startswith(("noreply@", "no-reply@", "example@")):
                    emails.add(email)
            except EmailNotValidError:
                continue
        return sorted(emails)

    def coordinates(self) -> list[tuple[float, float]]:
        found = []
        def walk(obj, depth=0):
            if depth > 12:
                return
            if isinstance(obj, dict):
                if "latitude" in obj and "longitude" in obj:
                    try:
                        lat, lon = float(obj["latitude"]), float(obj["longitude"])
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            found.append((lat, lon))
                    except (TypeError, ValueError):
                        pass
                for value in obj.values():
                    walk(value, depth + 1)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value, depth + 1)
        for obj in self.structured:
            walk(obj)
        return found
