import json
import re
import ssl
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import subprocess


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    "Referer": "https://music.163.com/",
}

# p4a 打包的 Python 没有系统 CA bundle，
# _create_unverified_context 完全跳过证书验证，不会尝试加载系统 CA
try:
    _SSL_CTX = ssl._create_unverified_context()
except Exception:
    _SSL_CTX = None


def _resolve_host(host: str) -> str:
    """
    p4a/Android: socket.gethostbyname 依赖 /etc/resolv.conf，但 Android 的
    DNS proxy (127.0.0.1:53) 在 Python 子进程命名空间里不可达，
    导致 Errno 7 (No address associated with hostname)。

    直接使用 subprocess 调用 /system/bin/ping 命令，利用系统的DNS解析能力。
    ping 能正常工作是因为它运行在更高级别的Android系统上下文里。
    """
    try:
        output = subprocess.check_output(
            ["/system/bin/ping", "-c", "1", "-W", "3", host],
            stderr=subprocess.STDOUT,
            timeout=5
        )
        output_str = output.decode("utf-8", errors="ignore")
        # 解析 ping 输出中的 IP 地址
        # 格式: PING host (IP) 56(...) bytes of data.
        match = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", output_str)
        if match:
            return match.group(1)
    except Exception:
        pass

    raise socket.gaierror(f"failed to resolve {host}")


def _get(url: str) -> dict:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname

    kwargs = {"timeout": 15}
    if _SSL_CTX is not None:
        kwargs["context"] = _SSL_CTX

    def resolve_and_retry():
        """DNS 失败 → 用 8.8.8.8 直接解析，然后用 IP 直连"""
        ip = _resolve_host(host)
        if parsed.port:
            netloc = f"{ip}:{parsed.port}"
        else:
            netloc = ip
        url_with_ip = urllib.parse.urlunparse((
            parsed.scheme, netloc, parsed.path,
            parsed.params, parsed.query, parsed.fragment,
        ))
        new_headers = dict(HEADERS)
        new_headers["Host"] = host
        req2 = urllib.request.Request(url_with_ip, headers=new_headers)
        with urllib.request.urlopen(req2, **kwargs) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, **kwargs) as response:
            return json.loads(response.read().decode("utf-8"))
    except socket.gaierror:
        # socket 直接报错（极少数）
        return resolve_and_retry()
    except urllib.error.URLError as e:
        # urlopen 把 socket.gaierror 包装成 URLError，reason 属性才是原始错误
        if isinstance(e.reason, socket.gaierror):
            return resolve_and_retry()
        else:
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


def get_album_detail(album_id: str) -> tuple[str, list[dict]]:
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


def get_artist_albums(artist_id: str) -> list[dict]:
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
            albums.append(
                {
                    "id": str(album["id"]),
                    "name": album.get("name", f"专辑 #{album['id']}"),
                    "publishTime": album.get("publishTime", 0),
                }
            )

        if not data.get("more", False) or not batch:
            break

        offset += limit
        time.sleep(0.3)

    return albums


def format_count(count: int) -> str:
    return f"{count:,}" if count >= 0 else "获取失败"


def query_album(album_id: str, on_progress=None) -> tuple[list[dict], str]:
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
        rows.append(
            {
                "album": album_name,
                "song": song["name"],
                "comments": format_count(count),
                "is_header": False,
            }
        )
        time.sleep(0.15)

    summary = (
        f"专辑《{album_name}》共 {len(songs)} 首，"
        f"歌曲评论合计 {total_song_comments:,}，专辑评论 {format_count(album_comments)}"
    )
    return rows, summary


def query_artist(artist_id: str, on_progress=None) -> tuple[list[dict], str]:
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
        rows.append(
            {
                "album": album["name"],
                "song": f"共 {len(songs)} 首 | 专辑评论 {format_count(album_comments)}",
                "comments": "",
                "is_header": True,
            }
        )

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
            rows.append(
                {
                    "album": album["name"],
                    "song": song["name"],
                    "comments": format_count(count),
                    "is_header": False,
                }
            )
            time.sleep(0.15)

        grand_songs += len(songs)
        time.sleep(0.3)

    summary = f"共 {len(albums)} 张专辑，{grand_songs} 首歌，歌曲评论合计 {grand_comments:,}"
    return rows, summary
