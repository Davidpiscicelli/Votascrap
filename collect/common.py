"""Outils partagés par les collecteurs : HTTP poli, normalisation de texte, dates, fichiers."""

import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "config")
DATA_DIR = os.path.join(ROOT, "site", "data")
CACHE_DIR = os.path.join(ROOT, "cache")

_last_hit = {}


def load_config(name):
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as f:
        return json.load(f)


SITE = load_config("site.json")
USER_AGENT = SITE.get("user_agent", "veille-parlementaire/1.0")
DELAY = float(SITE.get("delai_entre_requetes", 0.6))


def log(*args):
    print("[veille]", *args, file=sys.stderr, flush=True)


def fetch(url, data=None, timeout=120, retries=3, binary=False):
    """GET (ou POST si data) avec délai par hôte, nouvelles tentatives et User-Agent identifiable."""
    host = urllib.parse.urlparse(url).netloc
    wait = DELAY - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else data
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                _last_hit[host] = time.time()
                if binary:
                    return raw
                charset = r.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404):
                break
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"échec {url}: {last_err}")


def fetch_json(url, **kw):
    txt = fetch(url, **kw).lstrip("﻿")
    # certains serveurs préfixent la réponse par un commentaire HTML
    txt = re.sub(r"^\s*<!--.*?-->\s*", "", txt, flags=re.S)
    return json.loads(txt)


def clean(s):
    """Texte propre : entités HTML décodées, balises retirées, espaces normalisés."""
    if s is None:
        return ""
    s = html.unescape(str(s))
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def fold(s):
    """Minuscules sans accents, pour les comparaisons et la recherche."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("’", "'").replace("œ", "oe")
    return re.sub(r"\s+", " ", s).strip()


def name_key(s):
    """Clé de rapprochement des noms de personnes (ordre des mots ignoré)."""
    s = fold(s)
    s = re.sub(r"[^a-z ]", " ", s.replace("-", " "))
    return " ".join(sorted(w for w in s.split() if len(w) > 1))


def date_fr(d):
    """'09/10/2026' -> '2026-10-09' (None si invalide)."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", d or "")
    if not m:
        return None
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, obj, compact=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def data_path(name):
    return os.path.join(DATA_DIR, name)


def cache_path(name):
    return os.path.join(CACHE_DIR, name)
