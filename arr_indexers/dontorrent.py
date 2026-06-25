#!/usr/bin/env python3
import argparse
import hashlib
import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


DEFAULT_PROXY_SOURCE_URL = "https://donproxies.com/"
DEFAULT_BASE_URL = "auto"
SITE_ID = "dontorrent"
USER_AGENT = "Mozilla/5.0 (compatible; DonTorrentProwlarr/1.0)"

CAPS_CATEGORIES = {
    "2000": "Movies",
    "5000": "TV",
    "5080": "Documentary",
}

ET.register_namespace("torznab", "http://torznab.com/schemas/2015/feed")


def http_request(url, method="GET", data=None, headers=None, timeout=30):
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if headers:
        request_headers.update(headers)

    body = None
    if data is not None:
        if isinstance(data, bytes):
            body = data
        elif request_headers.get("Content-Type") == "application/json":
            body = json.dumps(data).encode("utf-8")
        else:
            body = urllib.parse.urlencode(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.headers, response.geturl()


def strip_tags(value):
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def absolute_url(base_url, path):
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path)


def discover_dontorrent_base_url(source_url=DEFAULT_PROXY_SOURCE_URL):
    content, _, _ = http_request(source_url)
    text = content.decode("utf-8", errors="replace")
    candidates = []

    for href in re.findall(r"""href=["']([^"']+)["']""", text, flags=re.IGNORECASE):
        href = html.unescape(href).strip()
        if not href:
            continue

        parsed = urllib.parse.urlparse(href)
        if parsed.scheme not in {"http", "https"}:
            continue

        host = parsed.netloc.lower()
        if "donproxies.com" in host or "t.me" in host or ".onion" in host:
            continue
        if "don" in host or "mirror" in host:
            candidates.append(f"{parsed.scheme}://{parsed.netloc}")

    if not candidates:
        raise RuntimeError(f"could not discover DonTorrent proxy from {source_url}")

    return candidates[0].rstrip("/")


def infer_category(path, badge):
    haystack = f"{path} {badge}".lower()
    if "documental" in haystack:
        return "5080"
    if "serie" in haystack:
        return "5000"
    return "2000"


def infer_table(path):
    if path.startswith("/serie/"):
        return "series"
    if path.startswith("/documental/"):
        return "documentales"
    return "peliculas"


def infer_download_id(path):
    parts = [part for part in path.split("/") if part]
    numbers = [part for part in parts if part.isdigit()]
    if not numbers:
        return None

    if parts[0] in {"serie", "documental"} and len(numbers) > 1:
        return numbers[1]

    return numbers[0]


def parse_date(date_text):
    if not date_text:
        return None

    try:
        parsed = time.strptime(date_text, "%Y-%m-%d")
        return time.strftime("%a, %d %b %Y 00:00:00 +0000", parsed)
    except ValueError:
        return None


def parse_results(base_url, content):
    text = content.decode("utf-8", errors="replace")
    results = []

    search_pattern = re.compile(
        r"<p><span><a\s+href=['\"](?P<href>/[^'\"]+)['\"][^>]*>"
        r"(?P<title>.*?)</a>\s*(?:<span>\((?P<quality>[^<]+)\)</span>)?"
        r".*?<span[^>]*badge[^>]*>(?P<badge>[^<]+)</span></p>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in search_pattern.finditer(text):
        path = html.unescape(match.group("href"))
        title = strip_tags(match.group("title"))
        quality = strip_tags(match.group("quality") or "")
        badge = strip_tags(match.group("badge") or "")
        results.append(build_result(base_url, path, title, quality, badge, None))

    browse_pattern = re.compile(
        r"<a\s+href=\"(?P<href>/(?:pelicula|serie|documental)/[^\"]+)\"[^>]*>"
        r"<img[^>]+src=\"(?P<img>[^\"]+)\"[^>]+data-popover-type=\"(?P<badge>[^\"]+)\"[^>]*>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in browse_pattern.finditer(text):
        path = html.unescape(match.group("href"))
        img = html.unescape(match.group("img"))
        title = path.rstrip("/").split("/")[-1].replace("-", " ")
        quality_match = re.search(r"\[([^\]]+)\]-\[DonTorrent\]", img)
        quality = quality_match.group(1) if quality_match else ""
        badge = strip_tags(match.group("badge"))
        results.append(build_result(base_url, path, title, quality, badge, None))

    deduped = {}
    for result in results:
        deduped[result["guid"]] = result
    return list(deduped.values())


def build_result(base_url, path, title, quality, badge, pub_date):
    category = infer_category(path, badge)
    table = infer_table(path)
    download_id = infer_download_id(path)
    details = absolute_url(base_url, path)
    params = urllib.parse.urlencode({"site": SITE_ID, "id": download_id or "", "tabla": table})
    download = f"/download?{params}"

    if quality:
        title = f"{title} [{quality}]"

    return {
        "title": title,
        "guid": details,
        "details": details,
        "download": download,
        "category": category,
        "pub_date": pub_date,
        "size": 0,
    }


def build_caps_xml():
    root = ET.Element("caps")
    server = ET.SubElement(root, "server")
    server.set("title", "DonTorrent")
    server.set("version", "1.0")

    limits = ET.SubElement(root, "limits")
    limits.set("max", "100")
    limits.set("default", "100")

    searching = ET.SubElement(root, "searching")
    for search_type in ("search", "movie-search", "tv-search"):
        item = ET.SubElement(searching, search_type)
        item.set("available", "yes")
        item.set("supportedParams", "q")

    categories = ET.SubElement(root, "categories")
    for cat_id, name in CAPS_CATEGORIES.items():
        item = ET.SubElement(categories, "category")
        item.set("id", cat_id)
        item.set("name", name)

    return xml_response(root)


def xml_response(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_feed_xml(base_url, public_url, items):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "DonTorrent"
    ET.SubElement(channel, "description").text = "DonTorrent Torznab proxy"
    ET.SubElement(channel, "link").text = base_url

    for result in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = result["title"]
        ET.SubElement(item, "guid", isPermaLink="true").text = result["guid"]
        ET.SubElement(item, "link").text = urllib.parse.urljoin(public_url, result["download"])
        ET.SubElement(item, "comments").text = result["details"]
        ET.SubElement(item, "category").text = result["category"]
        ET.SubElement(item, "size").text = str(result["size"])
        if result["pub_date"]:
            ET.SubElement(item, "pubDate").text = result["pub_date"]

        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", urllib.parse.urljoin(public_url, result["download"]))
        enclosure.set("length", str(result["size"]))
        enclosure.set("type", "application/x-bittorrent")

        attr = ET.SubElement(item, "{http://torznab.com/schemas/2015/feed}attr")
        attr.set("name", "category")
        attr.set("value", result["category"])

    return xml_response(rss)


def compute_pow(challenge, difficulty=3):
    target = "0" * difficulty
    nonce = 0
    while True:
        digest = hashlib.sha256(f"{challenge}{nonce}".encode("utf-8")).hexdigest()
        if digest.startswith(target):
            return nonce
        nonce += 1


class DonTorrentServer(BaseHTTPRequestHandler):
    configured_base_url = DEFAULT_BASE_URL
    proxy_source_url = DEFAULT_PROXY_SOURCE_URL
    base_url = None
    api_key = None

    @classmethod
    def get_base_url(cls, force_refresh=False):
        if cls.configured_base_url and cls.configured_base_url != "auto":
            return cls.configured_base_url.rstrip("/")

        if force_refresh or not cls.base_url:
            cls.base_url = discover_dontorrent_base_url(cls.proxy_source_url)
            logging.info("discovered DonTorrent proxy URL: %s", cls.base_url)

        return cls.base_url

    def log_message(self, fmt, *args):
        logging.info("%s - %s", self.address_string(), fmt % args)

    def send_bytes(self, body, status=200, content_type="application/xml; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json_error(self, message, status=500):
        self.send_bytes(json.dumps({"error": message}).encode("utf-8"), status, "application/json")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        try:
            if parsed.path == "/api":
                self.handle_api(params)
            elif parsed.path == "/download":
                self.handle_download(params)
            elif parsed.path == "/health":
                self.send_bytes(b"ok\n", content_type="text/plain; charset=utf-8")
            else:
                self.send_bytes(b"Not found\n", status=404, content_type="text/plain; charset=utf-8")
        except Exception as exc:
            logging.exception("request failed")
            self.send_json_error(str(exc), 500)

    def authorized(self, params):
        if not self.api_key:
            return True
        return params.get("apikey", [""])[0] == self.api_key

    def validate_site(self, params):
        site = params.get("site", [""])[0].strip().lower()
        if not site:
            self.send_json_error("missing required site parameter; use site=dontorrent", 400)
            return False
        if site != SITE_ID:
            self.send_json_error(f"unsupported site parameter: {site}", 400)
            return False
        return True

    def public_url(self):
        host = self.headers.get("Host", "127.0.0.1")
        return f"http://{host}/"

    def handle_api(self, params):
        if not self.validate_site(params):
            return

        if not self.authorized(params):
            self.send_bytes(b"Forbidden\n", status=403, content_type="text/plain; charset=utf-8")
            return

        torznab_type = params.get("t", ["search"])[0]
        if torznab_type == "caps":
            self.send_bytes(build_caps_xml())
            return

        query = params.get("q", [""])[0].strip()
        items = self.search(query)
        self.send_bytes(build_feed_xml(self.get_base_url(), self.public_url(), items))

    def search(self, query):
        return self.with_proxy_refresh(lambda base_url: self.search_with_base_url(base_url, query))

    def search_with_base_url(self, base_url, query):
        if query:
            body, _, _ = http_request(
                absolute_url(base_url, "/buscar"),
                method="POST",
                data={"valor": query, "Buscar": "Buscar"},
            )
            return parse_results(base_url, body)

        body, _, _ = http_request(absolute_url(base_url, "/ultimos"))
        return parse_results(base_url, body)

    def handle_download(self, params):
        if not self.validate_site(params):
            return

        if not self.authorized(params):
            self.send_bytes(b"Forbidden\n", status=403, content_type="text/plain; charset=utf-8")
            return

        content_id = params.get("id", [""])[0]
        table = params.get("tabla", [""])[0]
        if not content_id.isdigit() or table not in {"peliculas", "series", "documentales"}:
            self.send_bytes(b"Bad download parameters\n", status=400, content_type="text/plain; charset=utf-8")
            return

        download_url = self.with_proxy_refresh(lambda base_url: self.resolve_download_url(base_url, content_id, table))
        self.send_response(302)
        self.send_header("Location", download_url)
        self.end_headers()

    def with_proxy_refresh(self, callback):
        base_url = self.get_base_url()
        try:
            return callback(base_url)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, RuntimeError):
            if self.configured_base_url and self.configured_base_url != "auto":
                raise

            logging.warning("DonTorrent proxy request failed; refreshing proxy URL and retrying once", exc_info=True)
            return callback(self.get_base_url(force_refresh=True))

    def resolve_download_url(self, base_url, content_id, table):
        api_url = absolute_url(base_url, "/api_validate_pow.php")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        generate_body, _, _ = http_request(
            api_url,
            method="POST",
            data={"action": "generate", "content_id": int(content_id), "tabla": table},
            headers=headers,
        )
        generated = json.loads(generate_body.decode("utf-8"))
        if not generated.get("success"):
            raise RuntimeError(generated.get("error") or "failed to generate proof-of-work challenge")

        nonce = compute_pow(generated["challenge"], 3)
        validate_body, _, _ = http_request(
            api_url,
            method="POST",
            data={"action": "validate", "challenge": generated["challenge"], "nonce": nonce},
            headers=headers,
        )
        validated = json.loads(validate_body.decode("utf-8"))
        if not validated.get("success"):
            raise RuntimeError(validated.get("error") or validated.get("status") or "proof-of-work validation failed")

        download_url = validated.get("download_url")
        if not download_url:
            raise RuntimeError("proof-of-work response did not include a download URL")

        return absolute_url(base_url, download_url)


def main(argv=None):
    parser = argparse.ArgumentParser(description="DonTorrent Torznab proxy for Prowlarr")
    parser.add_argument("--host", default=os.getenv("ARR_INDEXERS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ARR_INDEXERS_PORT", "9697")))
    parser.add_argument("--base-url", default=os.getenv("DONTORENT_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--proxy-source-url", default=os.getenv("DONTORENT_PROXY_SOURCE_URL", DEFAULT_PROXY_SOURCE_URL))
    parser.add_argument("--api-key", default=os.getenv("ARR_INDEXERS_API_KEY"))
    parser.add_argument("--log-level", default=os.getenv("ARR_INDEXERS_LOG_LEVEL", "INFO"))
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s: %(message)s")
    DonTorrentServer.configured_base_url = args.base_url.rstrip("/") if args.base_url else DEFAULT_BASE_URL
    DonTorrentServer.proxy_source_url = args.proxy_source_url
    DonTorrentServer.api_key = args.api_key

    server = ThreadingHTTPServer((args.host, args.port), DonTorrentServer)
    logging.info("serving DonTorrent Torznab proxy on http://%s:%s/api", args.host, args.port)
    logging.info("configured DonTorrent base URL: %s", DonTorrentServer.configured_base_url)
    logging.info("DonTorrent proxy source URL: %s", DonTorrentServer.proxy_source_url)
    server.serve_forever()


if __name__ == "__main__":
    main()
