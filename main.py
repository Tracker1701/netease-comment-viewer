import os
import sys
import traceback
from threading import Thread

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from netease_api import parse_url, query_album, query_artist

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG        = (0.08, 0.08, 0.10, 1)
C_SURFACE   = (0.13, 0.13, 0.17, 1)
C_BORDER    = (0.22, 0.22, 0.28, 1)
C_RED       = (0.80, 0.20, 0.20, 1)
C_RED_DARK  = (0.28, 0.06, 0.06, 1)
C_RED_TEXT  = (1.00, 0.78, 0.78, 1)
C_ROW_A     = (0.10, 0.10, 0.13, 1)
C_ROW_B     = (0.14, 0.14, 0.18, 1)
C_TEXT      = (0.92, 0.92, 0.96, 1)
C_TEXT2     = (0.52, 0.52, 0.60, 1)
C_GRAY_BTN  = (0.26, 0.26, 0.32, 1)
C_DIVIDER   = (0.20, 0.20, 0.26, 1)
# ─────────────────────────────────────────────────────────────────────────────


# ── Font registration ─────────────────────────────────────────────────────────
_FONT = "Roboto"


def _resolve_font():
    cands = []
    try:
        from kivy.resources import resource_find
        f = resource_find("fonts/NotoSansSC.otf")
        if f:
            cands.append(f)
    except Exception:
        pass
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        cands.append(os.path.join(base, "fonts", "NotoSansSC.otf"))
    except Exception:
        pass
    ap = os.environ.get("ANDROID_PRIVATE", "")
    if ap:
        cands.append(os.path.join(ap, "fonts", "NotoSansSC.otf"))
    cands.append(os.path.join(os.getcwd(), "fonts", "NotoSansSC.otf"))
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return None


try:
    _fp = _resolve_font()
    if _fp:
        LabelBase.register(name="NotoSansSC", fn_regular=_fp)
        _FONT = "NotoSansSC"
        print(f"[font] loaded {_fp}", file=sys.stderr)
    else:
        print("[font] NotoSansSC not found, using Roboto", file=sys.stderr)
except Exception as e:
    print(f"[font] {e}", file=sys.stderr)
# ─────────────────────────────────────────────────────────────────────────────


# ── KV rule for ResultRow ─────────────────────────────────────────────────────
# Defining layout in KV ensures `text_size: self.width, None` is a live Kivy
# binding — it re-evaluates every time the label's width changes after layout,
# which is what makes text actually visible in RecycleView rows.
Builder.load_string(f"""
<ResultRow>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(52)
    padding: dp(14), dp(4), dp(14), dp(4)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: root._bg_color
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: root._div_color
        Rectangle:
            pos: self.pos
            size: self.width, dp(1)
    Label:
        id: lbl_main
        size_hint_x: 1
        halign: 'left'
        valign: 'middle'
        font_name: '{_FONT}'
        text_size: self.width, None
        shorten: True
        shorten_from: 'right'
    Label:
        id: lbl_cnt
        size_hint_x: None
        width: dp(90)
        halign: 'right'
        valign: 'middle'
        font_name: '{_FONT}'
        text_size: self.width, None
""")
# ─────────────────────────────────────────────────────────────────────────────


class ResultRow(RecycleDataViewBehavior, BoxLayout):
    _bg_color  = ListProperty(list(C_ROW_A))
    _div_color = ListProperty(list(C_DIVIDER))

    def refresh_view_attrs(self, rv, index, data):
        super().refresh_view_attrs(rv, index, data)

        lbl_main = self.ids.lbl_main
        lbl_cnt  = self.ids.lbl_cnt
        is_hdr   = data.get("is_header", False)
        album    = data.get("album", "")
        song     = data.get("song", "")
        comments = data.get("comments", "")

        if is_hdr:
            self._bg_color    = list(C_RED_DARK)
            self._div_color   = [0.50, 0.12, 0.12, 1]
            lbl_main.text     = album
            lbl_main.bold     = True
            lbl_main.color    = list(C_RED_TEXT)
            lbl_main.font_size = sp(14)
            # artist query: song = "共N首 | 专辑评论X", comments = ""
            # album query:  song = "专辑评论数",         comments = count
            if comments:
                lbl_cnt.text      = f"专辑评论\n{comments}"
            else:
                lbl_cnt.text      = song
            lbl_cnt.font_size = sp(11)
            lbl_cnt.color     = [1.0, 0.62, 0.62, 0.85]
            lbl_cnt.bold      = False
        else:
            self._bg_color    = list(C_ROW_A if index % 2 == 0 else C_ROW_B)
            self._div_color   = list(C_DIVIDER)
            lbl_main.text     = song
            lbl_main.bold     = False
            lbl_main.color    = list(C_TEXT)
            lbl_main.font_size = sp(14)
            lbl_cnt.text      = comments
            lbl_cnt.font_size = sp(14)
            lbl_cnt.color     = list(C_TEXT2)
            lbl_cnt.bold      = False

        return self


class ResultsView(RecycleView):
    data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.viewclass = "ResultRow"
        layout = RecycleBoxLayout(
            default_size=(None, dp(52)),
            default_size_hint=(1, None),
            size_hint_y=None,
            orientation="vertical",
        )
        layout.bind(minimum_height=layout.setter("height"))
        self.add_widget(layout)


def _flat_btn(text, bg):
    return Button(
        text=text,
        font_name=_FONT,
        font_size=sp(15),
        bold=True,
        background_normal="",
        background_down="",
        background_color=bg,
        color=C_TEXT,
    )


class SectionDivider(Widget):
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(1), **kwargs)
        with self.canvas:
            Color(*C_DIVIDER)
            r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda w, _: setattr(r, "pos", w.pos),
                  size=lambda w, _: setattr(r, "size", w.size))


class ListHeader(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None, height=dp(34),
            padding=[dp(14), 0, dp(14), 0],
            spacing=dp(10),
            **kwargs,
        )
        with self.canvas.before:
            Color(0.16, 0.16, 0.20, 1)
            r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda w, _: setattr(r, "pos", w.pos),
                  size=lambda w, _: setattr(r, "size", w.size))

        lbl_left = Label(
            text="专辑 / 歌曲", halign="left", valign="middle",
            font_name=_FONT, font_size=sp(11),
            bold=True, color=C_TEXT2, size_hint_x=1,
        )
        lbl_left.bind(size=lambda w, s: setattr(w, "text_size", s))
        lbl_right = Label(
            text="评论数", halign="right", valign="middle",
            font_name=_FONT, font_size=sp(11),
            bold=True, color=C_TEXT2,
            size_hint_x=None, width=dp(90),
        )
        lbl_right.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(lbl_left)
        self.add_widget(lbl_right)


class Root(BoxLayout):
    progress = NumericProperty(0)
    status   = StringProperty("就绪")
    summary  = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            padding=[dp(14), dp(12), dp(14), dp(10)],
            spacing=0,
            **kwargs,
        )
        with self.canvas.before:
            Color(*C_BG)
            bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda w, _: setattr(bg, "pos", w.pos),
                  size=lambda w, _: setattr(bg, "size", w.size))

        # ── Title ─────────────────────────────────────────────────────────────
        title = Label(
            text="网易云音乐评论查看器",
            size_hint_y=None, height=dp(48),
            font_name=_FONT, font_size=sp(20),
            bold=True, color=C_RED,
            halign="center", valign="middle",
        )
        title.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(title)
        self.add_widget(Widget(size_hint_y=None, height=dp(6)))

        # ── Input card ────────────────────────────────────────────────────────
        input_card = BoxLayout(
            orientation="vertical",
            size_hint_y=None, height=dp(84),
            padding=[dp(1), dp(1), dp(1), dp(1)],
        )
        with input_card.canvas.before:
            Color(*C_BORDER)
            b_rect = Rectangle(pos=input_card.pos, size=input_card.size)
            Color(*C_SURFACE)
            i_rect = Rectangle(pos=input_card.pos, size=input_card.size)
        def _upd(w, _):
            b_rect.pos = w.pos; b_rect.size = w.size
            i_rect.pos = (w.x+dp(1), w.y+dp(1))
            i_rect.size = (w.width-dp(2), w.height-dp(2))
        input_card.bind(pos=_upd, size=_upd)

        self.input_text = TextInput(
            hint_text="粘贴网易云音乐专辑或歌手分享链接…",
            text="http://music.163.com/album/165230666/",
            multiline=True,
            font_name=_FONT, font_size=sp(13),
            background_color=C_SURFACE,
            foreground_color=C_TEXT,
            hint_text_color=(*C_TEXT2[:3], 0.6),
            cursor_color=C_RED,
            padding=[dp(10), dp(8)],
        )
        input_card.add_widget(self.input_text)
        self.add_widget(input_card)
        self.add_widget(Widget(size_hint_y=None, height=dp(10)))

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        self.query_btn = _flat_btn("开始查询", C_RED)
        self.query_btn.bind(on_press=self.start_query)
        clear_btn = _flat_btn("清  空", C_GRAY_BTN)
        clear_btn.bind(on_press=self.clear)
        btn_row.add_widget(self.query_btn)
        btn_row.add_widget(clear_btn)
        self.add_widget(btn_row)
        self.add_widget(Widget(size_hint_y=None, height=dp(10)))

        # ── Progress bar ──────────────────────────────────────────────────────
        pb = BoxLayout(size_hint_y=None, height=dp(5))
        with pb.canvas.before:
            Color(0.18, 0.18, 0.22, 1)
            pb_bg = Rectangle(pos=pb.pos, size=pb.size)
            Color(*C_RED)
            self._pb_fill = Rectangle(pos=pb.pos, size=(0, dp(5)))
        def _upd_pb(w, _):
            pb_bg.pos = w.pos; pb_bg.size = w.size
            self._pb_fill.pos  = w.pos
            self._pb_fill.size = (w.width * self.progress / 100, w.height)
        pb.bind(pos=_upd_pb, size=_upd_pb)
        self.bind(progress=lambda *_: _upd_pb(pb, None))
        self.add_widget(pb)
        self.add_widget(Widget(size_hint_y=None, height=dp(6)))

        # ── Status ────────────────────────────────────────────────────────────
        self._status_lbl = Label(
            text=self.status,
            size_hint_y=None, height=dp(24),
            font_name=_FONT, font_size=sp(12),
            color=C_TEXT2, halign="left", valign="middle",
        )
        self._status_lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.bind(status=lambda _, v: setattr(self._status_lbl, "text", v))
        self.add_widget(self._status_lbl)
        self.add_widget(Widget(size_hint_y=None, height=dp(4)))

        # ── Column header ─────────────────────────────────────────────────────
        self._list_hdr = ListHeader()
        self._list_hdr.opacity = 0
        self.add_widget(self._list_hdr)
        self.add_widget(SectionDivider())

        # ── Results list ──────────────────────────────────────────────────────
        self.results = ResultsView()
        self.add_widget(self.results)
        self.add_widget(SectionDivider())

        # ── Summary ───────────────────────────────────────────────────────────
        self._summary_lbl = Label(
            text="",
            size_hint_y=None, height=dp(54),
            font_name=_FONT, font_size=sp(13),
            color=C_RED_TEXT, bold=True,
            halign="left", valign="middle",
        )
        self._summary_lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.bind(summary=lambda _, v: setattr(self._summary_lbl, "text", v))
        self.add_widget(self._summary_lbl)

    # ── Actions ───────────────────────────────────────────────────────────────
    def clear(self, *_):
        self.input_text.text     = ""
        self.results.data        = []
        self.progress            = 0
        self.status              = "就绪"
        self.summary             = ""
        self._list_hdr.opacity   = 0

    def start_query(self, *_):
        parsed = parse_url(self.input_text.text.strip())
        if not parsed:
            self.status = "未识别到专辑或歌手链接"
            return
        self.results.data        = []
        self.progress            = 0
        self.summary             = ""
        self._list_hdr.opacity   = 0
        self.query_btn.disabled  = True
        kind, eid = parsed
        Thread(target=self._run_query, args=(kind, eid), daemon=True).start()

    def _run_query(self, kind, eid):
        try:
            def on_prog(cur, tot, msg):
                Clock.schedule_once(lambda _: self._set_progress(cur, tot, msg))

            rows, summary = (query_album if kind == "album" else query_artist)(eid, on_prog)
            Clock.schedule_once(lambda _: self._show_result(rows, summary))
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            print(f"[query] {traceback.format_exc()}", file=sys.stderr)
            Clock.schedule_once(lambda _: self._show_error(msg))
        finally:
            Clock.schedule_once(lambda _: setattr(self.query_btn, "disabled", False))

    def _set_progress(self, cur, tot, msg):
        self.progress = cur / max(tot, 1) * 100
        self.status   = msg

    def _show_result(self, rows, summary):
        self.results.data       = rows
        self.progress           = 100
        self.status             = f"完成，共 {len(rows)} 条记录"
        self.summary            = summary
        self._list_hdr.opacity  = 1 if rows else 0

    def _show_error(self, msg):
        self.status = f"请求失败：{msg}"


class NeteaseCommentApp(App):
    def build(self):
        self.title = "网易云评论查看器"
        Window.clearcolor = C_BG
        return Root()


if __name__ == "__main__":
    NeteaseCommentApp().run()
