import json
import os
import re
import ssl
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    "Referer": "https://music.163.com/",
}

try:
    _SSL_CTX = ssl._create_unverified_context()
except Exception:
    _SSL_CTX = None

_IS_ANDROID = os.path.exists("/system/bin/app_process")


def _java_http_get(url: str) -> dict:
    """Use Android's native HTTP stack via pyjnius (bypasses Python DNS/SSL entirely)."""
    from jnius import autoclass
    URL = autoclass("java.net.URL")
    BufferedReader = autoclass("java.io.BufferedReader")
    InputStreamReader = autoclass("java.io.InputStreamReader")

    java_url = URL(url)
    conn = java_url.openConnection()
    conn.setConnectTimeout(15000)
    conn.setReadTimeout(15000)
    conn.setRequestProperty("User-Agent", HEADERS["User-Agent"])
    conn.setRequestProperty("Referer", HEADERS["Referer"])

    code = conn.getResponseCode()
    if code < 200 or code >= 300:
        raise OSError(f"HTTP {code}")

    reader = BufferedReader(InputStreamReader(conn.getInputStream(), "UTF-8"))
    lines = []
    line = reader.readLine()
    while line is not None:
        lines.append(line)
        line = reader.readLine()
    reader.close()
    conn.disconnect()

    return json.loads("".join(lines))


def _resolve_host(host: str) -> str:
    """Try multiple DNS strategies: Java InetAddress → ping → DoH → fail."""
    # 1. Android Java InetAddress (most reliable on Android/HarmonyOS)
    if _IS_ANDROID:
        try:
            from jnius import autoclass
            InetAddress = autoclass("java.net.InetAddress")
            return InetAddress.getByName(host).getHostAddress()
        except Exception as e:
            print(f"[dns] java InetAddress failed: {e}", file=sys.stderr)

    # 2. System ping
    try:
        import subprocess
        output = subprocess.check_output(
            ["/system/bin/ping", "-c", "1", "-W", "3", host],
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", output.decode("utf-8", errors="ignore"))
        if m:
            return m.group(1)
    except Exception as e:
        print(f"[dns] ping failed: {e}", file=sys.stderr)

    # 3. DNS-over-HTTPS via Cloudflare 1.1.1.1 (hard-coded IP — no DNS needed)
    try:
        doh_url = f"https://1.1.1.1/dns-query?name={urllib.parse.quote(host)}&type=A"
        req = urllib.request.Request(doh_url, headers={"Accept": "application/dns-json"})
        ctx_kw = {"context": _SSL_CTX} if _SSL_CTX else {}
        with urllib.request.urlopen(req, timeout=8, **ctx_kw) as r:
            data = json.loads(r.read())
            for ans in data.get("Answer", []):
                if ans.get("type") == 1:  # A record
                    return ans["data"]
    except Exception as e:
        print(f"[dns] DoH failed: {e}", file=sys.stderr)

    raise socket.gaierror(f"failed to resolve {host} (all DNS methods exhausted)")


def _get(url: str) -> dict:
    """Fetch URL and return parsed JSON.  On Android, tries native Java HTTP first."""
    # Android: native Java HTTP bypasses Python's DNS and SSL stacks entirely
    if _IS_ANDROID:
        try:
            return _java_http_get(url)
        except Exception as e:
            print(f"[net] Java HTTP failed ({e}), falling back to urllib", file=sys.stderr)

    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    ctx_kw = {"timeout": 15}
    if _SSL_CTX:
        ctx_kw["context"] = _SSL_CTX

    def resolve_and_retry() -> dict:
        ip = _resolve_host(host)
        netloc = f"{ip}:{parsed.port}" if parsed.port else ip
        url_ip = urllib.parse.urlunparse((
            parsed.scheme, netloc, parsed.path,
            parsed.params, parsed.query, parsed.fragment,
        ))
        hdrs = dict(HEADERS)
        hdrs["Host"] = host
        req2 = urllib.request.Request(url_ip, headers=hdrs)
        with urllib.request.urlopen(req2, **ctx_kw) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, **ctx_kw) as r:
            return json.loads(r.read().decode("utf-8"))
    except socket.gaierror:
        return resolve_and_retry()
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.gaierror):
            return resolve_and_retry()
        raise


def parse_url(text: str):
    """Return ("album", id), ("artist", id), or None from shared NetEase text."""
    for pattern in (
        r"music\.163\.com/album/(\d+)",
        r"music\.163\.com/#?/album\?[^\"'\s]*?id=(\d+)",
        r"music\.163\.com/album\?[^\"'\s]*?id=(\d+)",
    ):
        match = re.search(pattern, text)
        if match:
            return "album", match.group(1)

    for pattern in (
        r"music\.163\.com/artist/(\d+)",
        r"music\.163\.com/#?/artist\?[^\"'\s]*?id=(\d+)",
        r"music\.163\.com/artist\?[^\"'\s]*?id=(\d+)",
    ):
        match = re.search(pattern, text)
        if match:
            return "artist", match.group(1)

    return None


def get_album_detail(album_id: str) -> tuple:
    data = _get(f"https://music.163.com/api/v1/album/{album_id}")
    album_name = data.get("album", {}).get("name") or f"专辑 #{album_id}"
    songs = [{"id": str(song["id"]), "name": song["name"]} for song in data.get("songs", [])]
    return album_name, songs


def get_song_comment_count(song_id: str) -> int:
    try:
        url = f"https://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}?limit=1&offset=0"
        data = _get(url)
        return int(data.get("total", 0))
    except Exception:
        return -1


def get_album_comment_count(album_id: str) -> int:
    try:
        url = f"https://music.163.com/api/v1/resource/comments/R_AL_3_{album_id}?limit=1&offset=0"
        data = _get(url)
        return int(data.get("total", 0))
    except Exception:
        return -1


def get_artist_albums(artist_id: str) -> list:
    albums = []
    offset = 0
    limit = 30

    while True:
        url = (
            f"https://music.163.com/api/artist/albums/{artist_id}"
            f"?offset={offset}&limit={limit}&total=true"
        )
        data = _get(url)
        batch = data.get("hotAlbums", [])

        for album in batch:
            albums.append({
                "id": str(album["id"]),
                "name": album.get("name", f"专辑 #{album['id']}"),
                "publishTime": album.get("publishTime", 0),
            })

        if not data.get("more", False) or not batch:
            break

        offset += limit
        time.sleep(0.3)

    return albums


def format_count(count: int) -> str:
    return f"{count:,}" if count >= 0 else "获取失败"


def query_album(album_id: str, on_progress=None) -> tuple:
    album_name, songs = get_album_detail(album_id)
    album_comments = get_album_comment_count(album_id)
    total_song_comments = 0
    rows = [
        {
            "album": album_name,
            "song": "专辑评论数",
            "comments": format_count(album_comments),
            "is_header": True,
        }
    ]

    total = len(songs) or 1
    for index, song in enumerate(songs, 1):
        if on_progress:
            on_progress(index, total, f"正在查询 {song['name']}")

        count = get_song_comment_count(song["id"])
        if count >= 0:
            total_song_comments += count
        rows.append({
            "album": album_name,
            "song": song["name"],
            "comments": format_count(count),
            "is_header": False,
        })
        time.sleep(0.15)

    summary = (
        f"专辑《{album_name}》共 {len(songs)} 首，"
        f"歌曲评论合计 {total_song_comments:,}，专辑评论 {format_count(album_comments)}"
    )
    return rows, summary


def query_artist(artist_id: str, on_progress=None) -> tuple:
    albums = get_artist_albums(artist_id)
    rows = []
    grand_songs = 0
    grand_comments = 0
    total_albums = len(albums) or 1

    for album_index, album in enumerate(albums, 1):
        if on_progress:
            on_progress(album_index, total_albums, f"正在读取专辑《{album['name']}》")

        try:
            _, songs = get_album_detail(album["id"])
        except Exception:
            songs = []

        album_comments = get_album_comment_count(album["id"])
        rows.append({
            "album": album["name"],
            "song": f"共 {len(songs)} 首 | 专辑评论 {format_count(album_comments)}",
            "comments": "",
            "is_header": True,
        })

        for song_index, song in enumerate(songs, 1):
            if on_progress:
                on_progress(
                    album_index,
                    total_albums,
                    f"《{album['name']}》 {song_index}/{len(songs)} {song['name']}",
                )

            count = get_song_comment_count(song["id"])
            if count >= 0:
                grand_comments += count
            rows.append({
                "album": album["name"],
                "song": song["name"],
                "comments": format_count(count),
                "is_header": False,
            })
            time.sleep(0.15)

        grand_songs += len(songs)
        time.sleep(0.3)

    summary = f"共 {len(albums)} 张专辑，{grand_songs} 首歌，歌曲评论合计 {grand_comments:,}"
    return rows, summary
