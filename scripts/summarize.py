#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""summarize.py —— 抓取单篇新闻正文并用 llm.config.json 配置的大模型生成中文摘要。
纯标准库。供 server.py POST /api/summarize 调用。
"""
import os, re, html, ipaddress, socket
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import llm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAX_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT = 20
TEXT_LIMIT = 12000
MIN_TEXT = 80
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SYS = (
    "你是中文行业新闻助手。根据给定的文章标题与正文，写一段中文摘要："
    "3–6 句要点式客观陈述，突出事实、主体与关键数字；不要编造正文没有的信息；"
    "不要给出投资建议或买卖建议。只输出摘要正文，不要标题或前缀标签。"
)


def is_safe_url(url):
    if not url or not isinstance(url, str):
        return False
    try:
        p = urlparse(url.strip())
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        return False
    # block literal IPs in private / loopback / link-local / metadata ranges
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
        # cloud metadata
        if str(ip) == "169.254.169.254":
            return False
    except ValueError:
        # hostname — still block obvious local names
        if host in ("0.0.0.0",):
            return False
    return True


def _strip_tags(s):
    s = re.sub(r"(?is)<(script|style|noscript|svg|iframe)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<!--.*?-->", " ", s)
    # prefer article / main block if present
    m = re.search(r"(?is)<article\b[^>]*>(.*?)</article>", s)
    if not m:
        m = re.search(r"(?is)<main\b[^>]*>(.*?)</main>", s)
    chunk = m.group(1) if m else s
    chunk = re.sub(r"(?is)<br\s*/?>", "\n", chunk)
    chunk = re.sub(r"(?is)</p>", "\n", chunk)
    chunk = re.sub(r"(?is)<[^>]+>", " ", chunk)
    chunk = html.unescape(chunk)
    chunk = re.sub(r"[ \t\f\v]+", " ", chunk)
    chunk = re.sub(r"\n\s*\n+", "\n", chunk)
    return chunk.strip()


def extract_text(html_src, limit=TEXT_LIMIT):
    if not html_src:
        return ""
    text = _strip_tags(html_src)
    if len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return text


def fetch_html(url):
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=FETCH_TIMEOUT) as r:
        ctype = (r.headers.get("Content-Type") or "").lower()
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        data = data[:MAX_BYTES]
    # charset guess
    charset = "utf-8"
    if "charset=" in ctype:
        charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def summarize(url, title=""):
    url = (url or "").strip()
    title = (title or "").strip()
    if not is_safe_url(url):
        return {"ok": False, "error": "非法或不安全的链接"}
    try:
        page = fetch_html(url)
    except HTTPError as e:
        return {"ok": False, "error": "抓取失败: HTTP %s" % e.code}
    except (URLError, socket.timeout, TimeoutError) as e:
        return {"ok": False, "error": "抓取失败: %s" % (getattr(e, "reason", None) or e)}
    except Exception as e:
        return {"ok": False, "error": "抓取失败: %s" % e}

    text = extract_text(page)
    if len(text) < MIN_TEXT:
        return {"ok": False, "error": "无法从该页提取正文（可能需登录/反爬/纯前端渲染）"}

    cfg = llm.load_config(ROOT)
    user = "标题: %s\n链接: %s\n\n正文:\n%s" % (title or "(无)", url, text)
    try:
        out = (llm.call(SYS, user, cfg, timeout=120) or "").strip()
    except Exception as e:
        return {"ok": False, "error": "模型调用失败: %s" % e}
    if not out:
        return {"ok": False, "error": "模型返回空摘要"}
    return {"ok": True, "summary": out, "title": title}
