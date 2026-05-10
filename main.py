import os
import sys
import traceback
from threading import Thread

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from netease_api import parse_url, query_album, query_artist

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG       = (0.08, 0.08, 0.10, 1)
C_SURFACE  = (0.13, 0.13, 0.17, 1)
C_BORDER   = (0.22, 0.22, 0.28, 1)
C_RED      = (0.80, 0.20, 0.20, 1)
C_RED_DARK = (0.28, 0.06, 0.06, 1)
C_RED_TEXT = (1.00, 0.78, 0.78, 1)
C_ROW_A    = (0.10, 0.10, 0.13, 1)
C_ROW_B    = (0.13, 0.13, 0.17, 1)
C_TEXT     = (0.92, 0.92, 0.96, 1)
C_TEXT2    = (0.52, 0.52, 0.60, 1)
C_GRAY_BTN = (0.26, 0.26, 0.32, 1)
C_DIVIDER  = (0.20, 0.20, 0.26, 1)
# ─────────────────────────────────────────────────────────────────────────────


# ── Font ─────────────────────────────────────────────────────────────────────
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


def _flat_button(text, bg_color, font_name=_FONT, font_size="15sp"):
    btn = Button(
        text=text,
        font_name=font_name,
        font_size=font_size,
        background_normal="",
        background_down="",
        background_color=bg_color,
        color=C_TEXT,
        bold=True,
    )
    return btn


class SectionDivider(Widget):
    """1dp horizontal rule."""
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(1), **kwargs)
        with self.canvas:
            Color(*C_DIVIDER)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda w, _: setattr(self._rect, "pos", w.pos),
                  size=lambda w, _: setattr(self._rect, "size", w.size))


class ResultRow(RecycleDataViewBehavior, BoxLayout):
    """One row in the results list. Fixed height = dp(52) for all rows."""
    index     = NumericProperty(0)
    album     = StringProperty("")
    song      = StringProperty("")
    comments  = StringProperty("")
    is_header = BooleanProperty(False)

    _H = dp(52)

    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=self._H,
            padding=[dp(14), dp(2), dp(14), dp(2)],
            spacing=dp(10),
            **kwargs,
        )
        with self.canvas.before:
            self._bg_clr  = Color(*C_ROW_A)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
            self._div_clr = Color(*C_DIVIDER)
            self._div_rect = Rectangle(pos=self.pos, size=(self.width, dp(1)))
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        # Left label — song name or album name for headers
        self._lbl_main = Label(
            halign="left",
            valign="middle",
            font_name=_FONT,
            font_size=sp(14),
            color=C_TEXT,
            size_hint_x=1,
            shorten=True,
            shorten_from="right",
        )
        # KEY FIX: bind text_size to the label's own size so it updates after layout
        self._lbl_main.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))

        # Right label — comment count (fixed width)
        self._lbl_cnt = Label(
            halign="right",
            valign="middle",
            font_name=_FONT,
            font_size=sp(14),
            color=C_TEXT2,
            size_hint_x=None,
            width=dp(90),
        )
        self._lbl_cnt.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))

        self.add_widget(self._lbl_main)
        self.add_widget(self._lbl_cnt)

    def _upd_bg(self, *_):
        self._bg_rect.pos  = self.pos
        self._bg_rect.size = self.size
        self._div_rect.pos  = self.pos
        self._div_rect.size = (self.width, dp(1))

    def refresh_view_attrs(self, rv, index, data):
        super().refresh_view_attrs(rv, index, data)
        self.index     = index
        self.album     = data.get("album", "")
        self.song      = data.get("song", "")
        self.comments  = data.get("comments", "")
        self.is_header = data.get("is_header", False)

        if self.is_header:
            self._bg_clr.rgba       = C_RED_DARK
            self._div_clr.rgba      = (0.50, 0.12, 0.12, 1)
            self._lbl_main.text     = self.album
            self._lbl_main.bold     = True
            self._lbl_main.color    = C_RED_TEXT
            self._lbl_main.font_size = sp(14)
            # For album query: comments has the count; for artist query: song has "共N首|专辑评论X"
            if self.comments:
                self._lbl_cnt.text  = f"专辑评论\n{self.comments}"
                self._lbl_cnt.font_size = sp(11)
            else:
                self._lbl_cnt.text  = self.song
                self._lbl_cnt.font_size = sp(11)
            self._lbl_cnt.color     = (1.0, 0.62, 0.62, 0.85)
            self._lbl_cnt.halign    = "right"
        else:
            self._bg_clr.rgba       = C_ROW_A if index % 2 == 0 else C_ROW_B
            self._div_clr.rgba      = C_DIVIDER
            self._lbl_main.text     = self.song
            self._lbl_main.bold     = False
            self._lbl_main.color    = C_TEXT
            self._lbl_main.font_size = sp(14)
            self._lbl_cnt.text      = self.comments
            self._lbl_cnt.color     = C_TEXT2
            self._lbl_cnt.font_size = sp(14)
            self._lbl_cnt.halign    = "right"

        return self


class ListHeader(BoxLayout):
    """Static column header row above the RecycleView."""
    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            padding=[dp(14), 0, dp(14), 0],
            spacing=dp(10),
            **kwargs,
        )
        with self.canvas.before:
            Color(0.16, 0.16, 0.20, 1)
            r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda w, _: setattr(r, "pos", w.pos),
                  size=lambda w, _: setattr(r, "size", w.size))

        self.add_widget(Label(
            text="专辑 / 歌曲",
            halign="left", valign="middle",
            font_name=_FONT, font_size=sp(12),
            color=C_TEXT2, bold=True,
            size_hint_x=1,
        ))
        self.add_widget(Label(
            text="评论数",
            halign="right", valign="middle",
            font_name=_FONT, font_size=sp(12),
            color=C_TEXT2, bold=True,
            size_hint_x=None, width=dp(90),
        ))


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
        # App-wide dark background
        with self.canvas.before:
            Color(*C_BG)
            bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda w, _: setattr(bg, "pos", w.pos),
                  size=lambda w, _: setattr(bg, "size", w.size))

        # ── Title ────────────────────────────────────────────────────────────
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

        # ── Input card ───────────────────────────────────────────────────────
        input_card = BoxLayout(
            orientation="vertical",
            size_hint_y=None, height=dp(86),
            padding=[dp(2), dp(2), dp(2), dp(2)],
        )
        with input_card.canvas.before:
            Color(*C_BORDER)
            border_rect = Rectangle(pos=input_card.pos, size=input_card.size)
            Color(*C_SURFACE)
            inner_rect = Rectangle(
                pos=(input_card.x + dp(1), input_card.y + dp(1)),
                size=(input_card.width - dp(2), input_card.height - dp(2)),
            )
        def _upd_card(w, _):
            border_rect.pos  = w.pos
            border_rect.size = w.size
            inner_rect.pos   = (w.x + dp(1), w.y + dp(1))
            inner_rect.size  = (w.width - dp(2), w.height - dp(2))
        input_card.bind(pos=_upd_card, size=_upd_card)

        self.input_text = TextInput(
            hint_text="粘贴网易云音乐专辑或歌手分享链接…",
            text="http://music.163.com/album/165230666/",
            multiline=True,
            font_name=_FONT,
            font_size=sp(14),
            background_color=C_SURFACE,
            foreground_color=C_TEXT,
            hint_text_color=(*C_TEXT2[:3], 0.7),
            cursor_color=C_RED,
            padding=[dp(10), dp(8)],
        )
        input_card.add_widget(self.input_text)
        self.add_widget(input_card)

        self.add_widget(Widget(size_hint_y=None, height=dp(10)))

        # ── Button row ───────────────────────────────────────────────────────
        btn_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        self.query_btn = _flat_button("开始查询", C_RED)
        self.query_btn.bind(on_press=self.start_query)
        clear_btn = _flat_button("清  空", C_GRAY_BTN)
        clear_btn.bind(on_press=self.clear)
        btn_row.add_widget(self.query_btn)
        btn_row.add_widget(clear_btn)
        self.add_widget(btn_row)

        self.add_widget(Widget(size_hint_y=None, height=dp(10)))

        # ── Progress bar (custom slim) ────────────────────────────────────────
        pbar_wrap = BoxLayout(size_hint_y=None, height=dp(6))
        with pbar_wrap.canvas.before:
            Color(0.18, 0.18, 0.22, 1)
            pbar_bg = Rectangle(pos=pbar_wrap.pos, size=pbar_wrap.size)
            Color(*C_RED)
            self._pbar_fill = Rectangle(pos=pbar_wrap.pos, size=(0, dp(6)))
        def _upd_pbar(w, _):
            pbar_bg.pos  = w.pos
            pbar_bg.size = w.size
            self._pbar_fill.pos  = w.pos
            self._pbar_fill.size = (w.width * self.progress / 100, w.height)
        pbar_wrap.bind(pos=_upd_pbar, size=_upd_pbar)
        self.bind(progress=lambda *_: _upd_pbar(pbar_wrap, None))
        self.add_widget(pbar_wrap)

        self.add_widget(Widget(size_hint_y=None, height=dp(6)))

        # ── Status ───────────────────────────────────────────────────────────
        self._status_lbl = Label(
            text=self.status,
            size_hint_y=None, height=dp(26),
            font_name=_FONT, font_size=sp(12),
            color=C_TEXT2,
            halign="left", valign="middle",
        )
        self._status_lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.bind(status=lambda _, v: setattr(self._status_lbl, "text", v))
        self.add_widget(self._status_lbl)

        self.add_widget(Widget(size_hint_y=None, height=dp(4)))

        # ── Column header + list ─────────────────────────────────────────────
        self._list_header = ListHeader()
        self._list_header.opacity = 0  # hidden until first result
        self.add_widget(self._list_header)

        self.add_widget(SectionDivider())

        self.results = ResultsView()
        self.add_widget(self.results)

        self.add_widget(SectionDivider())

        # ── Summary footer ───────────────────────────────────────────────────
        self._summary_lbl = Label(
            text="",
            size_hint_y=None, height=dp(56),
            font_name=_FONT, font_size=sp(13),
            color=C_RED_TEXT,
            halign="left", valign="middle",
            bold=True,
        )
        self._summary_lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.bind(summary=lambda _, v: setattr(self._summary_lbl, "text", v))
        self.add_widget(self._summary_lbl)

    # ── Actions ──────────────────────────────────────────────────────────────
    def clear(self, *_):
        self.input_text.text = ""
        self.results.data    = []
        self.progress        = 0
        self.status          = "就绪"
        self.summary         = ""
        self._list_header.opacity = 0

    def start_query(self, *_):
        parsed = parse_url(self.input_text.text.strip())
        if not parsed:
            self.status = "未识别到专辑或歌手链接"
            return
        self.results.data         = []
        self.progress             = 0
        self.summary              = ""
        self._list_header.opacity = 0
        self.query_btn.disabled   = True
        kind, eid = parsed
        Thread(target=self._run_query, args=(kind, eid), daemon=True).start()

    def _run_query(self, kind, eid):
        try:
            def on_prog(cur, tot, msg):
                Clock.schedule_once(lambda _: self._set_progress(cur, tot, msg))

            if kind == "album":
                rows, summary = query_album(eid, on_prog)
            else:
                rows, summary = query_artist(eid, on_prog)

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
        self.results.data         = rows
        self.progress             = 100
        self.status               = f"完成，共 {len(rows)} 条记录"
        self.summary              = summary
        self._list_header.opacity = 1 if rows else 0

    def _show_error(self, msg):
        self.status = f"请求失败：{msg}"


class NeteaseCommentApp(App):
    def build(self):
        self.title = "网易云评论查看器"
        Window.clearcolor = C_BG
        return Root()


if __name__ == "__main__":
    NeteaseCommentApp().run()
