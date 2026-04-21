"""
网易云音乐评论数查看器 - Android Kivy 版本
基于官方 HTTP API，无需加密，支持专辑和歌手两种查询模式。
"""
import os as _os
# ── 修复 Android Python DNS 解析问题 ─────────────────────────────────────────
# Android 上 Python 的 glibc 栈读不到 net.dns1（为空），导致 DNS 解析失败。
# 设置 RESOLVER_NAMESERVERS 环境变量，让 uDNS（若编译进 glibc）使用公共 DNS。
# 同时备用方案：直接用 IP + Host header（见 get_json 中的 fallback）。
_os.environ.setdefault('RESOLVER_NAMESERVERS', '223.5.5.5 180.76.76.76 8.8.8.8')

import re
import json
import threading
import socket
import urllib.request
import urllib.error
import time
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.resources import resource_find

# 注册中文字体（p4a 会把 fonts/ 目录打包进 app/）
import os as _os
import sys as _sys
import logging as _logging
_logging.basicConfig(level=_logging.INFO)
_logger = _logging.getLogger('font')

_font_names = [
    'fonts/NotoSansSC.otf',       # p4a app/ 子目录（正确 OTF 格式）
    'fonts/NotoSansSC.ttf',       # 备选
]
# 桌面调试用相对路径
_base = _os.path.dirname(_os.path.abspath(__file__)) if __name__ not in (None, '__main__') else '.'
for _n in list(_font_names):
    _font_names.append(_os.path.join(_base, _n))
_font_names.append(_os.path.join(_base, 'fonts', 'NotoSansSC.otf'))

FONT_PATH = None
for _p in _font_names:
    _found = resource_find(_p)
    if _found and _os.path.exists(_found):
        FONT_PATH = _found
        _logger.info(f'[FONT] Found: {_found}')
        break
    for _sp in _sys.path:
        _tp = _os.path.join(_sp, _p)
        if _os.path.exists(_tp):
            FONT_PATH = _tp
            _logger.info(f'[FONT] Found in sys.path: {_tp}')
            break
    if FONT_PATH:
        break

from kivy.clock import Clock
from kivy.metrics import dp

# Android / KivyMD 相关
try:
    from kivymd.app import MDApp
    from kivymd.uix.card import MDCard
    from kivymd.uix.button import MDRaisedButton, MDFlatButton
    from kivymd.uix.textfield import MDTextField
    from kivymd.uix.label import MDLabel
    from kivymd.uix.spinner import MDSpinner
    USE_KIVYM = True
except ImportError:
    USE_KIVYM = False

# ── 中文字体注册（必须在 KivyMD import 之后，覆盖其注册的 Roboto）────────
if FONT_PATH:
    LabelBase.register('Roboto', FONT_PATH)
    _logger.info(f'[FONT] Override Roboto with {FONT_PATH}')
else:
    _logger.warning('[FONT] NotoSansSC not found')

# ─────────────────────────────────────────────
# API 核心
# ─────────────────────────────────────────────

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/83.0.4103.106 Mobile Safari/537.36',
    'Referer': 'https://music.163.com/',
}


def parse_url(text: str) -> dict:
    """
    从任意文本中提取网易云音乐链接 ID。
    返回 dict: {'type': 'album'|'artist', 'id': int}
    """
    text = text.strip()

    # 专辑模式
    m = re.search(r'album[/=](\d+)', text)
    if m:
        return {'type': 'album', 'id': int(m.group(1))}

    # 歌手模式
    m = re.search(r'artist[/=](\d+)', text)
    if m:
        return {'type': 'artist', 'id': int(m.group(1))}

    return None


def _resolve_dns(host: str) -> str | None:
    """
    通过 HTTPS DNS-over-HTTPS API 解析 hostname。
    Android SELinux 阻止 raw UDP socket，改用 HTTPS（走 443 端口）做 DNS 查询。
    """
    import json as _json
    try:
        # Google DNS-over-HTTPS API
        doh_url = f'https://dns.google/resolve?name={host}&type=A'
        req = urllib.request.Request(doh_url, headers={
            'User-Agent': 'python-requests/2.28.0',
            'Accept': 'application/dns-json',
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode('utf-8'))
            answers = data.get('Answer', [])
            for ans in answers:
                if ans.get('type') == 1:  # A record
                    ip = ans['data']
                    _logger.info(f'[DNS] DoH {host} -> {ip}')
                    return ip
    except Exception as e:
        _logger.warning(f'[DNS] DoH {host} failed: {e}')
    return None


def _java_get(url: str) -> dict:
    """
    通过 pyjnius 调用 Java OkHttp3 发起请求。
    OkHttp 能正确使用华为 aserviceproxy_s 系统代理（SOCKS/HTTP），
    绕过 Python urllib 在华为鸿蒙上 TCP connect EPERM 的问题。
    如果 OkHttp 不可用，则 fallback 到 java.net.URL。
    """
    # 优先用 OkHttp（支持华为 aserviceproxy_s）
    result = _java_okhttp(url)
    if result:
        return result
    # Fallback：java.net.URL
    return _java_url(url)


def _init_pyjnius_classloader():
    """
    修复 pyjnius 在 p4a APK 环境下找不到 APK 内编译的 OkHttp 类的问题。
    p4a --depend 注入的 OkHttp 会被编译进 APK DEX，但 pyjnius 默认的 ClassLoader
    只包含 BOOT CLASSPATH，没有 APK 的 DexPathList。
    这里把当前线程的 context ClassLoader（= app 的 PathClassLoader）注入给 pyjnius，
    确保 autoclass 能找到 APK 内编译的 okhttp3 类。
    """
    try:
        from jnius import autoclass
        Thread = autoclass('java.lang.Thread')
        # 拿到 app 的 ClassLoader（PathClassLoader，包含 APK 的所有 DEX）
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        app_classloader = PythonActivity.getApplicationContext().getClassLoader()
        # 设为当前线程 context ClassLoader，pyjnius 的 autoclass 链会用到它
        Thread.currentThread().setContextClassLoader(app_classloader)
    except Exception as e:
        pass  # 桌面环境没有这些类，正常忽略


# 全局标记，避免重复初始化
_pyjnius_classloader_inited = False


def _java_okhttp(url: str) -> dict:
    """通过 OkHttp 发送请求（华为 aserviceproxy_s 兼容）"""
    global _pyjnius_classloader_inited
    if not _pyjnius_classloader_inited:
        _init_pyjnius_classloader()
        _pyjnius_classloader_inited = True

    try:
        from jnius import autoclass

        # OkHttp3 API
        OkHttpClient = autoclass('okhttp3.OkHttpClient')
        Request = autoclass('okhttp3.Request')
        Request.Builder = autoclass('okhttp3.Request.Builder')

        client = OkHttpClient()
        builder = Request.Builder()
        for k, v in HEADERS.items():
            builder.addHeader(k, v)
        builder.url(url)
        builder.get()
        request = builder.build()

        resp = client.newCall(request).execute()
        code = resp.code()
        body_bytes = resp.body().bytes()
        resp.close()

        result = json.loads(body_bytes.decode('utf-8'))
        _logger.info(f'[API-OkHttp] GET {url[:60]} -> code={code}')
        return result
    except Exception as e:
        _logger.warning(f'[API-OkHttp] failed: {type(e).__name__}: {e}')
        return {}


def _java_url(url: str) -> dict:
    """通过 java.net.URL 发送请求（fallback）"""
    try:
        from jnius import autoclass
        URL = autoclass('java.net.URL')
        HttpURLConnection = autoclass('java.net.HttpURLConnection')

        java_url = URL(url)
        conn = java_url.openConnection()
        conn.setConnectTimeout(20000)
        conn.setReadTimeout(20000)
        for k, v in HEADERS.items():
            conn.setRequestProperty(k, v)
        conn.connect()

        code = conn.getResponseCode()
        stream = conn.getInputStream() if code < 400 else conn.getErrorStream()
        data = b''
        buf = bytearray(4096)
        while True:
            n = stream.read(buf)
            if n <= 0:
                break
            data += buf[:n]
        stream.close()
        conn.disconnect()

        result = json.loads(data.decode('utf-8'))
        _logger.info(f'[API-JAVA] GET {url[:60]} -> code={code}')
        return result
    except Exception as e:
        _logger.warning(f'[API-JAVA] FAILED: {e}')
        return {}


def get_json(url: str) -> dict:
    """带超时和错误处理的 GET 请求。"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            _logger.info(f'[API] GET {url[:60]} -> code={resp.status}')
            return result
    except Exception as e:
        err_str = str(e)
        if 'No address associated with hostname' in err_str or \
           'Name or service not known' in err_str or \
           'Operation not permitted' in err_str:
            # Python urllib 被系统限制时，用 Java 网络栈（自动走系统代理）
            result = _java_get(url)
            if result:
                return result
        _logger.warning(f'[API] GET {url[:60]} FAILED: {e}')
        return {}


def get_album_songs(album_id: int) -> tuple:
    """
    获取专辑内所有歌曲。
    返回 (album_name, songs: list[dict])
    """
    url = f'https://music.163.com/api/v1/album/{album_id}'
    data = get_json(url)
    album_name = data.get('album', {}).get('name', '未知专辑')
    songs = data.get('songs', [])
    return album_name, songs


def get_artist_albums(artist_id: int) -> list:
    """
    获取歌手所有专辑（自动翻页，最多 50 页 × 30 = 1500 张）。
    """
    albums = []
    page_size = 30
    for offset in range(0, 1500, page_size):
        url = (f'https://music.163.com/api/artist/albums/{artist_id}'
               f'?offset={offset}&total=true&limit={page_size}')
        data = get_json(url)
        chunk = data.get('hotAlbums', [])
        albums.extend(chunk)
        if len(chunk) < page_size:
            break
        time.sleep(0.15)
    return albums


def get_song_comment_count(song_id: int) -> int:
    """获取单首歌曲的评论数。"""
    url = (f'https://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}'
           '?limit=1&offset=0')
    data = get_json(url)
    total = data.get('total', 0)
    return total if isinstance(total, int) else 0


def get_album_comment_count(album_id: int) -> int:
    """获取专辑的评论数。"""
    url = (f'https://music.163.com/api/v1/resource/comments/R_AL_3_{album_id}'
           '?limit=1&offset=0')
    data = get_json(url)
    total = data.get('total', 0)
    return total if isinstance(total, int) else 0


def format_num(n: int) -> str:
    if n >= 10000:
        return f'{n / 10000:.1f}万'
    return str(n)


# ─────────────────────────────────────────────
# KivyMD UI（Material Design）
# ─────────────────────────────────────────────

class ResultRow(BoxLayout):
    """单行结果展示：序号 | 歌曲名 | 评论数"""

    def __init__(self, index, name, comment, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(44)
        self.padding = [dp(8), dp(4)]
        self.spacing = dp(6)

        # 序号
        idx_lbl = Label(
            text=str(index),
            font_size='13sp',
            color=(0.5, 0.5, 0.5, 1),
            size_hint_x=0.08,
            halign='center',
            valign='middle',
        )
        idx_lbl.bind(size=lambda s, w: setattr(s, 'text_size', w))

        # 歌曲名
        name_lbl = Label(
            text=name,
            font_size='14sp',
            color=(1, 1, 1, 1),
            size_hint_x=0.62,
            halign='left',
            valign='middle',
            shorten=True,
            shorten_from='right',
        )
        name_lbl.bind(size=lambda s, w: setattr(s, 'text_size', w))

        # 评论数
        comment_lbl = Label(
            text=format_num(comment),
            font_size='14sp',
            color=(0.3, 0.8, 1.0, 1),
            size_hint_x=0.30,
            halign='right',
            valign='middle',
        )
        comment_lbl.bind(size=lambda s, w: setattr(s, 'text_size', w))

        self.add_widget(idx_lbl)
        self.add_widget(name_lbl)
        self.add_widget(comment_lbl)


class AlbumSection(BoxLayout):
    """专辑分组：专辑标题 + 歌曲列表"""

    def __init__(self, album_name, album_id, album_comment, songs, start_index=1, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.padding = [dp(8), dp(6)]
        spacing = dp(4)

        # 专辑标题行
        header = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(38),
            padding=[dp(8), 0],
            spacing=dp(6),
        )
        icon_lbl = Label(
            text='[专辑]',
            font_size='14sp',
            color=(1, 0.8, 0.2, 1),
            size_hint_x=0.1,
            halign='center',
            valign='middle',
        )
        icon_lbl.bind(size=lambda s, w: setattr(s, 'text_size', w))

        name_lbl = Label(
            text=album_name,
            font_size='15sp',
            color=(1, 0.9, 0.5, 1),
            bold=True,
            size_hint_x=0.50,
            halign='left',
            valign='middle',
            shorten=True,
            shorten_from='right',
        )
        name_lbl.bind(size=lambda s, w: setattr(s, 'text_size', w))

        album_cmt_lbl = Label(
            text=f'专辑 {format_num(album_comment)}',
            font_size='12sp',
            color=(0.6, 0.6, 0.6, 1),
            size_hint_x=0.40,
            halign='right',
            valign='middle',
        )
        album_cmt_lbl.bind(size=lambda s, w: setattr(s, 'text_size', w))

        header.add_widget(icon_lbl)
        header.add_widget(name_lbl)
        header.add_widget(album_cmt_lbl)
        self.add_widget(header)

        # 歌曲列表
        for i, song in enumerate(songs):
            self.add_widget(ResultRow(
                index=start_index + i,
                name=song.get('name', '未知'),
                comment=song.get('comment', 0),
            ))


class MainScreen(BoxLayout):
    """主界面"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._setup_ui()

    def _setup_ui(self, *args):
        if USE_KIVYM:
            self._setup_kivymd()
        else:
            self._setup_kivy()

    # ── KivyMD 布局 ──────────────────────────────

    def _setup_kivymd(self):
        app = MDApp.get_running_app()
        app.theme_cls.theme_style = 'Dark'
        app.theme_cls.primary_palette = 'DeepPurple'
        app.theme_cls.accent_palette = 'Teal'

        self.orientation = 'vertical'
        self.padding = dp(12)
        self.spacing = dp(10)

        # 标题
        self.add_widget(MDLabel(
            text='网易云评论数查看器',
            font_style='H5',
            bold=True,
            size_hint_y=None,
            height=dp(48),
            halign='center',
        ))

        # 输入框
        self.input_field = MDTextField(
            hint_text='粘贴分享文本或专辑/歌手链接',
            mode='rectangle',
            font_size='15sp',
        )
        self.add_widget(self.input_field)

        # 按钮行
        btn_row = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(10),
        )
        self.query_btn = MDRaisedButton(
            text='查询',
            on_press=lambda _: self.start_query(),
        )
        self.export_btn = MDRaisedButton(
            text='导出 CSV',
            on_press=lambda _: self.export_csv(),
            disabled=True,
        )
        btn_row.add_widget(self.query_btn)
        btn_row.add_widget(self.export_btn)
        self.add_widget(btn_row)

        # 进度条
        self.progress_bar = ProgressBar(
            max=100,
            value=0,
            size_hint_y=None,
            height=dp(8),
        )
        self.add_widget(self.progress_bar)

        # 状态标签
        self.status_lbl = MDLabel(
            text='就绪',
            font_size='13sp',
            color=(0.6, 0.6, 0.6, 1),
            size_hint_y=None,
            height=dp(28),
        )
        self.add_widget(self.status_lbl)

        # 结果区域（ScrollView + 垂直列表）
        self.results_container = BoxLayout(
            orientation='vertical',
            size_hint_y=1,
            spacing=dp(2),
        )
        scroll = ScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
        )
        scroll.add_widget(self.results_container)
        self.add_widget(scroll)

        self.all_results = []   # 全量数据，用于导出

    # ── 纯 Kivy 布局（备选） ───────────────────────

    def _setup_kivy(self):
        self.orientation = 'vertical'
        self.padding = 12
        self.spacing = 10

        self.add_widget(Label(
            text='网易云评论数查看器',
            font_size=20,
            size_hint_y=None,
            height=48,
            bold=True,
        ))

        self.input_field = TextInput(
            hint_text='粘贴分享文本或专辑/歌手链接',
            font_size=15,
            size_hint_y=None,
            height=80,
            multiline=True,
        )
        self.add_widget(self.input_field)

        btn_row = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=48,
            spacing=10,
        )
        self.query_btn = Button(
            text='查询',
            background_color=(0.2, 0.4, 0.8, 1),
            on_press=lambda _: self.start_query(),
        )
        self.export_btn = Button(
            text='导出 CSV',
            background_color=(0.2, 0.7, 0.3, 1),
            on_press=lambda _: self.export_csv(),
            disabled=True,
        )
        btn_row.add_widget(self.query_btn)
        btn_row.add_widget(self.export_btn)
        self.add_widget(btn_row)

        self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=8)
        self.add_widget(self.progress_bar)

        self.status_lbl = Label(
            text='就绪',
            font_size=13,
            color=(0.6, 0.6, 0.6, 1),
            size_hint_y=None,
            height=28,
        )
        self.add_widget(self.status_lbl)

        self.results_container = BoxLayout(
            orientation='vertical',
            size_hint_y=1,
            spacing=2,
        )
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        scroll.add_widget(self.results_container)
        self.add_widget(scroll)

        self.all_results = []

    # ── 查询逻辑 ─────────────────────────────────

    def start_query(self):
        raw_text = self.input_field.text.strip()
        if not raw_text:
            self._set_status('⚠️ 请先粘贴分享文本')
            return

        parsed = parse_url(raw_text)
        if not parsed:
            self._set_status('⚠️ 无法识别链接，请粘贴完整的分享文本')
            return

        self._set_status('⏳ 正在查询...')
        self.query_btn.disabled = True
        self.progress_bar.value = 0
        self.results_container.clear_widgets()
        self.all_results = []

        # 子线程执行网络请求
        thread = threading.Thread(
            target=self._query_thread,
            args=(parsed['type'], parsed['id']),
            daemon=True,
        )
        thread.start()

    def _query_thread(self, qtype: str, qid: int):
        try:
            if qtype == 'album':
                results = self._fetch_album(qid)
            else:
                results = self._fetch_artist(qid)
            Clock.schedule_once(lambda _: self._show_results(results))
        except Exception as e:
            Clock.schedule_once(lambda _: self._set_status(f'[X] 错误: {e}'))

    def _fetch_album(self, album_id: int) -> list:
        """专辑模式：专辑信息 + 所有歌曲评论数"""
        album_name, songs = get_album_songs(album_id)
        album_comment = get_album_comment_count(album_id)

        total = len(songs)
        results = []
        song_comments = []

        for i, song in enumerate(songs):
            sid = song['id']
            song_name = song.get('name', '未知')
            count = get_song_comment_count(sid) if sid else 0
            song_comments.append({'name': song_name, 'comment': count})
            results.append({
                'album': album_name,
                'song': song_name,
                'song_comment': count,
                'album_comment': album_comment,
            })
            pct = int((i + 1) / total * 100)
            Clock.schedule_once(
                lambda _, p=pct, s=song_name:
                    self._set_progress(p, f'⏳ 正在获取: {s[:12]}')
            )
            time.sleep(0.15)

        self._final_results = results
        self._final_results.append({
            '__meta__': {
                'type': 'album',
                'album_name': album_name,
                'album_id': album_id,
                'song_comments': song_comments,
                'album_comment': album_comment,
                'total_song_comment': sum(r['song_comment'] for r in results),
            }
        })
        return self._final_results

    def _fetch_artist(self, artist_id: int) -> list:
        """歌手模式：遍历所有专辑，每个专辑下获取所有歌曲评论数"""
        albums = get_artist_albums(artist_id)
        total_albums = len(albums)
        results = []

        for ai, album in enumerate(albums):
            a_id = album['id']
            a_name = album.get('name', '未知专辑')
            a_time = album.get('publishTime', 0)

            try:
                _, songs = get_album_songs(a_id)
            except Exception:
                songs = []

            album_cmt = get_album_comment_count(a_id)

            for song in songs:
                sid = song['id']
                s_name = song.get('name', '未知')
                count = get_song_comment_count(sid) if sid else 0
                results.append({
                    'album': a_name,
                    'album_time': a_time,
                    'song': s_name,
                    'song_comment': count,
                    'album_comment': album_cmt,
                })

            overall = (ai + 1) / total_albums * 100
            Clock.schedule_once(
                lambda _, p=overall, n=a_name:
                    self._set_progress(int(p), f'⏳ 专辑 {ai+1}/{total_albums}: {n[:10]}')
            )
            time.sleep(0.15)

        meta = {
            '__meta__': {
                'type': 'artist',
                'album_count': total_albums,
                'song_count': len(songs),
                'total_song_comment': sum(r['song_comment'] for r in results),
                'albums': albums,
                'results': results,
            }
        }
        return results + [meta]

    def _show_results(self, results: list):
        self.results_container.clear_widgets()

        # 提取 meta
        meta = None
        data = results
        if results and '__meta__' in results[-1]:
            meta = results[-1]['__meta__']
            data = results[:-1]

        self.all_results = data
        self.export_btn.disabled = False

        if meta and meta.get('type') == 'album':
            self._show_album_results(meta, data)
        elif meta and meta.get('type') == 'artist':
            self._show_artist_results(meta)
        else:
            self._set_status('⚠️ 未获取到有效数据')

    def _show_album_results(self, meta: dict, data: list):
        """展示专辑模式结果"""
        album_name = meta['album_name']
        album_comment = meta['album_comment']
        song_comments = meta['song_comments']
        total_song_comment = meta['total_song_comment']

        # 汇总行
        self.results_container.add_widget(ResultRow(
            index='#',
            name=f'【{album_name}】',
            comment=album_comment,
        ))

        # 表头
        self.results_container.add_widget(self._make_header())

        # 歌曲列表
        for i, item in enumerate(song_comments):
            self.results_container.add_widget(ResultRow(
                index=i + 1,
                name=item['name'],
                comment=item['comment'],
            ))

        # 汇总
        self.results_container.add_widget(self._make_footer(
            f'歌曲评论总计: {format_num(total_song_comment)}  |  '
            f'专辑评论: {format_num(album_comment)}'
        ))
        self._set_progress(100, '[OK] 查询完成')
        self.query_btn.disabled = False

    def _show_artist_results(self, meta: dict):
        """展示歌手模式结果：按专辑分组"""
        albums = meta.get('albums', [])
        results = meta.get('results', [])

        # 汇总信息
        total_song_comment = sum(r['song_comment'] for r in results)
        self.results_container.add_widget(self._make_header())
        self.results_container.add_widget(self._make_footer(
            f'共 {len(albums)} 张专辑  |  '
            f'歌曲评论总计: {format_num(total_song_comment)}'
        ))

        # 按专辑分组展示
        album_map = {}
        for r in results:
            aname = r['album']
            if aname not in album_map:
                album_map[aname] = {
                    'songs': [],
                    'album_comment': r.get('album_comment', 0),
                }
            album_map[aname]['songs'].append({
                'name': r['song'],
                'comment': r['song_comment'],
            })

        for album_name, info in album_map.items():
            section = AlbumSection(
                album_name=album_name,
                album_id=0,
                album_comment=info['album_comment'],
                songs=info['songs'],
                start_index=1,
            )
            self.results_container.add_widget(section)

        self._set_progress(100, '[OK] 查询完成')
        self.query_btn.disabled = False

    def _make_header(self) -> Label:
        h = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(32),
            padding=[dp(8), 0],
            spacing=dp(6),
        )
        for text, width, color in [
            ('#', 0.08, (0.5, 0.5, 0.5, 1)),
            ('歌曲', 0.62, (0.7, 0.7, 0.7, 1)),
            ('评论数', 0.30, (0.7, 0.7, 0.7, 1)),
        ]:
            lbl = Label(
                text=text,
                font_size='12sp',
                color=color,
                size_hint_x=width,
                halign='center' if text == '#' else ('right' if text == '评论数' else 'left'),
                valign='middle',
                bold=True,
            )
            lbl.bind(size=lambda s, w: setattr(s, 'text_size', w))
            h.add_widget(lbl)
        return h

    def _make_footer(self, text: str) -> Label:
        lbl = Label(
            text=text,
            font_size='13sp',
            color=(0.3, 0.9, 0.5, 1),
            size_hint_y=None,
            height=dp(36),
            halign='center',
            valign='middle',
        )
        lbl.bind(size=lambda s, w: setattr(s, 'text_size', w))
        return lbl

    # ── 进度 & 状态 ─────────────────────────────

    def _set_progress(self, value: int, status: str = ''):
        self.progress_bar.value = value
        if status:
            self._set_status(status)

    def _set_status(self, text: str):
        self.status_lbl.text = text

    # ── 导出 CSV ─────────────────────────────────

    def export_csv(self):
        if not self.all_results:
            self._set_status('⚠️ 没有可导出的数据')
            return
        try:
            import os
            # Android 上用 App.user_data_dir，桌面用当前目录
            try:
                from kivy.app import App
                out_dir = App.get_running_app().user_data_dir
            except Exception:
                out_dir = os.getcwd()

            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(out_dir, f'netease_comments_{timestamp}.csv')

            with open(filename, 'w', encoding='utf-8-sig') as f:
                f.write('\uFEFF')  # BOM for Excel
                if 'album' in self.all_results[0]:
                    f.write('专辑名,歌曲,歌曲评论数,专辑评论数\n')
                    for r in self.all_results:
                        f.write(f'"{r["album"]}","{r["song"]}",{r["song_comment"]},{r["album_comment"]}\n')
                else:
                    f.write('歌曲,评论数\n')
                    for r in self.all_results:
                        f.write(f'"{r["song"]}",{r["song_comment"]}\n')

            self._set_status(f'已导出: {filename}')
        except Exception as e:
            self._set_status(f'[X] 导出失败: {e}')


# ─────────────────────────────────────────────
# App 入口
# ─────────────────────────────────────────────

class NeteaseApp(MDApp if USE_KIVYM else App):

    def build(self):
        return MainScreen()

    def on_start(self):
        # Android 状态栏沉浸
        try:
            import android
            androidardware = __import__('android', fromlist=['hardware'])
            androidhardware.hardware.vibrator.vibrate(0)
        except Exception:
            pass


if __name__ == '__main__':
    if USE_KIVYM:
        NeteaseApp().run()
    else:
        # 桌面测试用黑色主题
        from kivy.core.window import Window
        Window.clearcolor = (0.1, 0.1, 0.1, 1)
        NeteaseApp().run()
