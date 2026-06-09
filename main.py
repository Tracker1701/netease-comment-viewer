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
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from history_store import HistoryStore
from netease_api import parse_url, query_album, query_artist

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG       = (0.08, 0.08, 0.10, 1)
C_SURFACE  = (0.13, 0.13, 0.17, 1)
C_BORDER   = (0.22, 0.22, 0.28, 1)
C_RED      = (0.80, 0.20, 0.20, 1)
C_RED_DARK = (0.28, 0.06, 0.06, 1)
C_RED_TEXT = (1.00, 0.78, 0.78, 1)
C_ROW_A    = (0.10, 0.10, 0.14, 1)
C_ROW_B    = (0.15, 0.15, 0.19, 1)
C_TEXT     = (0.92, 0.92, 0.96, 1)
C_TEXT2    = (0.52, 0.52, 0.60, 1)
C_GRAY_BTN = (0.26, 0.26, 0.32, 1)
C_DIVIDER  = (0.20, 0.20, 0.26, 1)

_ROW_H = dp(52)
_CNT_W = dp(90)
_PAD_H = dp(14)   # horizontal padding inside each row (left + right each)
_GAP   = dp(10)   # spacing between left and right label
# ─────────────────────────────────────────────────────────────────────────────

_FONT = "Roboto"   # Kivy default; replaced below if a better font is found
_FONT_PATH = None


def _resolve_font():
    """
    Pick the best available font with BROAD Unicode coverage.
    Priority:
      1. Android system fonts (DroidSansFallback / NotoSansCJK / …)
      2. Bundled NotoSansSC.otf  (CJK + basic Latin)
      3. Roboto (Kivy built-in)
    Android system fonts cover Greek, symbols, CJK, Arabic, etc. –
    exactly what NotoSansSC.otf (SC subset) is missing.
    """
    cands = []

    # ── 1. Android system fonts (huge Unicode coverage) ────────────────────
    # DroidSansFallback.ttf exists on Android 4-5; newer versions use NotoSans*.
    # All are world-readable (/system/fonts/ mode 0644).
    if os.path.exists("/system/bin/app_process"):
        _sys_fonts = [
            "/system/fonts/DroidSansFallback.ttf",
            "/system/fonts/NotoSansCJK-Regular.ttc",
            "/system/fonts/NotoSans-Regular.ttf",
            "/system/fonts/NotoSansSC-Regular.otf",
            "/system/fonts/Roboto-Regular.ttf",
        ]
        for p in _sys_fonts:
            if os.path.isfile(p):
                cands.append(p)

    # ── 2. Bundled NotoSansSC.otf (CJK + basic Latin) ───────────────────
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

    # ── 3. Pick first candidate that actually exists ───────────────────────
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return None


try:
    _fp = _resolve_font()
    if _fp:
        _FONT_PATH = _fp
        # Kivy accepts a file path directly in font_name – no registration needed.
        # We still register an alias so widgets can use a short name.
        try:
            LabelBase.register(name="AppFont", fn_regular=_fp)
            _FONT = "AppFont"
        except Exception:
            # If registration fails (e.g. TTC format), use the path directly.
            _FONT = _fp
        print(f"[font] loaded {_fp}", file=sys.stderr)
    else:
        print("[font] No font found, using Roboto", file=sys.stderr)
except Exception as e:
    print(f"[font] {e}", file=sys.stderr)


# ── Widget helpers ────────────────────────────────────────────────────────────

def _attach_bg(widget, color):
    with widget.canvas.before:
        clr  = Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, _: setattr(rect, "pos",  w.pos),
                size=lambda w, _: setattr(rect, "size", w.size))
    return clr, rect


def _divider():
    w = Widget(size_hint_y=None, height=dp(1))
    with w.canvas:
        Color(*C_DIVIDER)
        r = Rectangle(pos=w.pos, size=w.size)
    w.bind(pos=lambda x, _: setattr(r, "pos",  x.pos),
           size=lambda x, _: setattr(r, "size", x.size))
    return w


def _flat_btn(text, bg):
    return Button(
        text=text, font_name=_FONT, font_size=sp(15), bold=True,
        background_normal="", background_down="",
        background_color=bg, color=C_TEXT,
    )


# ── Row factory ───────────────────────────────────────────────────────────────

def _make_row(index, data, main_w):
    """
    Build one result row.

    main_w is the exact pixel width available for the main (left) label,
    computed once from Window.width when results arrive.  By setting
    text_size at construction time we avoid all timing / binding issues
    that plague width-based callbacks on Android.
    """
    is_hdr   = data.get("is_header", False)
    album    = data.get("album", "")
    song     = data.get("song", "")
    comments = data.get("comments", "")

    bg_clr = C_RED_DARK if is_hdr else (C_ROW_A if index % 2 == 0 else C_ROW_B)

    row = BoxLayout(
        orientation="horizontal",
        size_hint_y=None,
        height=_ROW_H,
        padding=[_PAD_H, dp(4), _PAD_H, dp(4)],
        spacing=_GAP,
    )
    _attach_bg(row, bg_clr)

    # Bottom hairline
    with row.canvas.after:
        Color(*(0.50, 0.12, 0.12, 1) if is_hdr else C_DIVIDER)
        div = Rectangle(pos=row.pos, size=(row.width, dp(1)))
    row.bind(pos=lambda w, _: setattr(div, "pos",  w.pos),
             size=lambda w, _: setattr(div, "size", (w.width, dp(1))))

    if is_hdr:
        # Left: album name
        lbl_main = Label(
            text=album,
            text_size=(main_w, None),   # ← set immediately, no binding needed
            size_hint_x=1,
            halign="left", valign="middle",
            font_name=_FONT, font_size=sp(14),
            bold=True, color=C_RED_TEXT,
            shorten=True, shorten_from="right",
        )
        # Right: album comment count or "共N首|评论" for artist queries
        cnt_text = f"专辑\n{comments}" if comments else song
        lbl_cnt  = Label(
            text=cnt_text,
            text_size=(_CNT_W, None),
            size_hint_x=None, width=_CNT_W,
            halign="right", valign="middle",
            font_name=_FONT, font_size=sp(11),
            color=(1.0, 0.62, 0.62, 0.85),
        )
    else:
        # Left: song name
        lbl_main = Label(
            text=song,
            text_size=(main_w, None),   # ← set immediately, no binding needed
            size_hint_x=1,
            halign="left", valign="middle",
            font_name=_FONT, font_size=sp(14),
            bold=False, color=C_TEXT,
            shorten=True, shorten_from="right",
        )
        # Right: comment count
        lbl_cnt = Label(
            text=comments,
            text_size=(_CNT_W, None),
            size_hint_x=None, width=_CNT_W,
            halign="right", valign="middle",
            font_name=_FONT, font_size=sp(14),
            color=C_TEXT2,
        )

    row.add_widget(lbl_main)
    row.add_widget(lbl_cnt)
    return row


def _col_header():
    hdr = BoxLayout(
        orientation="horizontal",
        size_hint_y=None, height=dp(34),
        padding=[_PAD_H, 0, _PAD_H, 0],
        spacing=_GAP,
    )
    _attach_bg(hdr, (0.16, 0.16, 0.20, 1))
    lbl_l = Label(
        text="专辑 / 歌曲",
        halign="left", valign="middle",
        font_name=_FONT, font_size=sp(11), bold=True, color=C_TEXT2,
        size_hint_x=1,
    )
    lbl_l.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    lbl_r = Label(
        text="评论数",
        text_size=(_CNT_W, None),
        halign="right", valign="middle",
        font_name=_FONT, font_size=sp(11), bold=True, color=C_TEXT2,
        size_hint_x=None, width=_CNT_W,
    )
    hdr.add_widget(lbl_l)
    hdr.add_widget(lbl_r)
    return hdr


# ─────────────────────────────────────────────────────────────────────────────


class Root(BoxLayout):
    progress = NumericProperty(0)
    status   = StringProperty("就绪")
    summary  = StringProperty("")

    def __init__(self, history_store=None, open_history=None, **kwargs):
        super().__init__(
            orientation="vertical",
            padding=[dp(14), dp(12), dp(14), dp(10)],
            spacing=0,
            **kwargs,
        )
        _attach_bg(self, C_BG)
        self.history_store = history_store
        self.open_history = open_history
        self._active_query = None

        # Title
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

        # Input card
        card = BoxLayout(
            orientation="vertical",
            size_hint_y=None, height=dp(84),
            padding=[dp(1), dp(1), dp(1), dp(1)],
        )
        with card.canvas.before:
            Color(*C_BORDER)
            br = Rectangle(pos=card.pos, size=card.size)
            Color(*C_SURFACE)
            ir = Rectangle(pos=card.pos, size=card.size)
        def _upd_card(w, _):
            br.pos = w.pos; br.size = w.size
            ir.pos  = (w.x + dp(1), w.y + dp(1))
            ir.size = (w.width - dp(2), w.height - dp(2))
        card.bind(pos=_upd_card, size=_upd_card)
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
        card.add_widget(self.input_text)
        self.add_widget(card)
        self.add_widget(Widget(size_hint_y=None, height=dp(10)))

        # Buttons
        btn_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.query_btn = _flat_btn("开始查询", C_RED)
        self.query_btn.bind(on_press=self.start_query)
        self.clear_btn = _flat_btn("清  空", C_GRAY_BTN)
        self.clear_btn.bind(on_press=self.clear)
        self.history_btn = _flat_btn("历史记录", C_GRAY_BTN)
        self.history_btn.bind(on_press=lambda *_: self.open_history and self.open_history())
        btn_row.add_widget(self.query_btn)
        btn_row.add_widget(self.clear_btn)
        btn_row.add_widget(self.history_btn)
        self.add_widget(btn_row)
        self.add_widget(Widget(size_hint_y=None, height=dp(10)))

        # Progress bar
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

        # Status
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

        # Column header (hidden until results arrive)
        self._col_hdr = _col_header()
        self._col_hdr.opacity = 0
        self.add_widget(self._col_hdr)
        self.add_widget(_divider())

        # ScrollView → rows_box
        self._scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self._rows_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=0,
            spacing=0,
        )
        self._rows_box.bind(minimum_height=self._rows_box.setter("height"))
        self._scroll.add_widget(self._rows_box)
        self.add_widget(self._scroll)
        self.add_widget(_divider())

        # Summary
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

    # ── helpers ───────────────────────────────────────────────────────────────

    def _compute_main_w(self):
        """
        Compute the pixel width available for the main (left) label in each row.

        We use Window.width because self._scroll.width may not yet reflect the
        final layout on the first query.  Window.width is always reliable.
        Root outer padding: dp(14) each side.
        Row inner padding:  dp(14) each side.
        Spacing between labels: dp(10).
        Right label width: dp(90).
        """
        return max(
            Window.width - dp(14)*2 - _PAD_H*2 - _GAP - _CNT_W,
            dp(60),
        )

    # ── actions ───────────────────────────────────────────────────────────────

    def clear(self, *_):
        self.input_text.text   = ""
        self._rows_box.clear_widgets()
        self._rows_box.height  = 0
        self.progress          = 0
        self.status            = "就绪"
        self.summary           = ""
        self._col_hdr.opacity  = 0

    def start_query(self, *_):
        parsed = parse_url(self.input_text.text.strip())
        if not parsed:
            self.status = "未识别到专辑或歌手链接"
            return
        self._rows_box.clear_widgets()
        self._rows_box.height   = 0
        self.progress           = 0
        self.summary            = ""
        self._col_hdr.opacity   = 0
        self.query_btn.disabled = True
        kind, eid = parsed
        self._active_query = {
            "category": kind,
            "entity_id": eid,
            "source_text": self.input_text.text.strip(),
        }
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
        self._rows_box.clear_widgets()

        # Compute main label width once — reliable because Window is fully sized.
        main_w = self._compute_main_w()

        for i, data in enumerate(rows):
            self._rows_box.add_widget(_make_row(i, data, main_w))

        # Set height explicitly right now; minimum_height binding also keeps it
        # correct after Kivy's next layout pass.
        self._rows_box.height = _ROW_H * len(rows)

        self.progress         = 100
        self.status           = f"完成，共 {len(rows)} 条记录"
        self.summary          = summary
        self._col_hdr.opacity = 1 if rows else 0
        self._scroll.scroll_y = 1
        self._save_history(rows, summary)

    def _save_history(self, rows, summary):
        if not self.history_store or not self._active_query:
            return
        try:
            query = self._active_query
            if query["category"] == "album" and rows:
                title = rows[0].get("album") or f"专辑 #{query['entity_id']}"
            else:
                title = f"歌手 #{query['entity_id']}"
            self.history_store.add(
                query["category"],
                query["entity_id"],
                query["source_text"],
                title,
                summary,
                rows,
            )
            self.status = f"{self.status}，已保存到历史记录"
        except Exception as exc:
            print(f"[history] save failed: {exc}", file=sys.stderr)
            self.status = f"{self.status}，历史记录保存失败"

    def _show_error(self, msg):
        self.status = f"请求失败：{msg}"


def _confirm_delete(message, on_confirm):
    content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))
    label = Label(
        text=message,
        font_name=_FONT,
        font_size=sp(14),
        color=C_TEXT,
        halign="center",
        valign="middle",
    )
    label.bind(size=lambda w, s: setattr(w, "text_size", s))
    buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
    cancel = _flat_btn("取消", C_GRAY_BTN)
    confirm = _flat_btn("删除", C_RED)
    buttons.add_widget(cancel)
    buttons.add_widget(confirm)
    content.add_widget(label)
    content.add_widget(buttons)
    popup = Popup(
        title="确认删除",
        title_font=_FONT,
        content=content,
        size_hint=(0.88, None),
        height=dp(190),
        auto_dismiss=False,
    )
    cancel.bind(on_press=popup.dismiss)

    def do_delete(*_):
        popup.dismiss()
        on_confirm()

    confirm.bind(on_press=do_delete)
    popup.open()


class HistoryScreen(Screen):
    def __init__(self, history_store, open_detail, **kwargs):
        super().__init__(**kwargs)
        self.history_store = history_store
        self.open_detail = open_detail
        self.selected = set()
        self.select_mode = False

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(12), dp(14), dp(10)],
            spacing=dp(8),
        )
        _attach_bg(root, C_BG)
        top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        back = _flat_btn("返回", C_GRAY_BTN)
        back.bind(on_press=lambda *_: setattr(self.manager, "current", "query"))
        self.mode_btn = _flat_btn("多选", C_GRAY_BTN)
        self.mode_btn.bind(on_press=self.toggle_select_mode)
        self.all_btn = _flat_btn("全选", C_GRAY_BTN)
        self.all_btn.bind(on_press=self.toggle_all)
        self.delete_btn = _flat_btn("删除", C_RED)
        self.delete_btn.bind(on_press=self.delete_selected)
        top.add_widget(back)
        top.add_widget(self.mode_btn)
        top.add_widget(self.all_btn)
        top.add_widget(self.delete_btn)
        root.add_widget(top)

        self.status_label = Label(
            text="解析历史",
            size_hint_y=None,
            height=dp(34),
            font_name=_FONT,
            font_size=sp(18),
            bold=True,
            color=C_RED,
            halign="left",
            valign="middle",
        )
        self.status_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.status_label)

        scroll = ScrollView(do_scroll_x=False)
        self.rows_box = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(8)
        )
        self.rows_box.bind(minimum_height=self.rows_box.setter("height"))
        scroll.add_widget(self.rows_box)
        root.add_widget(scroll)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.refresh()

    def refresh(self):
        self.records = self.history_store.load()
        valid_ids = {record["history_id"] for record in self.records}
        self.selected.intersection_update(valid_ids)
        self.rows_box.clear_widgets()
        self.all_btn.disabled = not self.select_mode or not self.records
        self.delete_btn.disabled = not self.select_mode or not self.selected
        self.mode_btn.text = "退出多选" if self.select_mode else "多选"
        self.status_label.text = (
            f"已选 {len(self.selected)} 条"
            if self.select_mode
            else f"解析历史（{len(self.records)}）"
        )

        if not self.records:
            self.rows_box.add_widget(
                Label(
                    text="暂无解析历史\n返回首页完成一次解析后会自动保存",
                    size_hint_y=None,
                    height=dp(130),
                    font_name=_FONT,
                    font_size=sp(14),
                    color=C_TEXT2,
                    halign="center",
                )
            )
            return

        for record in self.records:
            self.rows_box.add_widget(self._make_history_row(record))

    def _make_history_row(self, record):
        row = BoxLayout(
            size_hint_y=None,
            height=dp(112),
            padding=[dp(8), dp(8), dp(8), dp(8)],
            spacing=dp(8),
        )
        _attach_bg(row, C_SURFACE)
        history_id = record["history_id"]
        category = {"album": "专辑", "artist": "歌手"}.get(
            record.get("category"), "未知"
        )
        created_at = record.get("created_at", "").replace("T", " ")[:16]
        text = (
            f"[{category}] {record.get('title', '未命名解析记录')}\n"
            f"{created_at} · {record.get('row_count', len(record.get('rows', [])))} 条\n"
            f"{record.get('summary', '')}"
        )
        if self.select_mode:
            checkbox = CheckBox(
                active=history_id in self.selected,
                size_hint_x=None,
                width=dp(38),
                color=C_RED,
            )
            checkbox.bind(
                active=lambda _, active, hid=history_id: self.set_selected(hid, active)
            )
            row.add_widget(checkbox)
        main = Button(
            text=text,
            font_name=_FONT,
            font_size=sp(12),
            color=C_TEXT,
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            halign="left",
            valign="middle",
        )
        main.bind(size=lambda w, s: setattr(w, "text_size", s))
        if self.select_mode:
            main.bind(
                on_press=lambda *_args, hid=history_id: self.set_selected(
                    hid, hid not in self.selected
                )
            )
        else:
            main.bind(on_press=lambda *_args, hid=history_id: self.open_detail(hid))
        row.add_widget(main)
        if not self.select_mode:
            delete = _flat_btn("删除", C_RED)
            delete.size_hint_x = None
            delete.width = dp(64)
            delete.bind(on_press=lambda *_args, hid=history_id: self.delete_one(hid))
            row.add_widget(delete)
        return row

    def toggle_select_mode(self, *_):
        self.select_mode = not self.select_mode
        self.selected.clear()
        self.refresh()

    def set_selected(self, history_id, active):
        if active:
            self.selected.add(history_id)
        else:
            self.selected.discard(history_id)
        self.refresh()

    def toggle_all(self, *_):
        all_ids = {record["history_id"] for record in self.records}
        self.selected = set() if self.selected == all_ids else all_ids
        self.refresh()

    def delete_one(self, history_id):
        _confirm_delete(
            "确定删除这条解析记录吗？删除后无法恢复。",
            lambda: self._delete_ids([history_id]),
        )

    def delete_selected(self, *_):
        if not self.selected:
            return
        count = len(self.selected)
        _confirm_delete(
            f"确定删除已选择的 {count} 条解析记录吗？删除后无法恢复。",
            lambda: self._delete_ids(list(self.selected)),
        )

    def _delete_ids(self, history_ids):
        self.history_store.delete_many(history_ids)
        self.selected.difference_update(history_ids)
        self.refresh()


class HistoryDetailScreen(Screen):
    def __init__(self, history_store, **kwargs):
        super().__init__(**kwargs)
        self.history_store = history_store
        self.history_id = None

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(12), dp(14), dp(10)],
            spacing=dp(8),
        )
        _attach_bg(root, C_BG)
        top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        back = _flat_btn("返回历史", C_GRAY_BTN)
        back.bind(on_press=lambda *_: setattr(self.manager, "current", "history"))
        delete = _flat_btn("删除当前记录", C_RED)
        delete.bind(on_press=self.delete_current)
        top.add_widget(back)
        top.add_widget(delete)
        root.add_widget(top)
        self.meta = Label(
            text="",
            size_hint_y=None,
            height=dp(132),
            font_name=_FONT,
            font_size=sp(12),
            color=C_RED_TEXT,
            halign="left",
            valign="middle",
        )
        self.meta.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.meta)
        scroll = ScrollView(do_scroll_x=False)
        self.rows_box = BoxLayout(orientation="vertical", size_hint_y=None)
        self.rows_box.bind(minimum_height=self.rows_box.setter("height"))
        scroll.add_widget(self.rows_box)
        root.add_widget(scroll)
        self.add_widget(root)

    def show_record(self, history_id):
        self.history_id = history_id
        record = self.history_store.get(history_id)
        self.rows_box.clear_widgets()
        if not record:
            self.meta.text = "记录不存在"
            return
        category = {"album": "专辑", "artist": "歌手"}.get(
            record.get("category"), "未知"
        )
        self.meta.text = (
            f"[{category}] {record.get('title', '未命名解析记录')}\n"
            f"解析时间：{record.get('created_at', '').replace('T', ' ')[:19]}\n"
            f"对象 ID：{record.get('entity_id', '')}\n"
            f"原始输入：{record.get('source_text', '')}\n"
            f"{record.get('summary', '')}"
        )
        main_w = max(
            Window.width - dp(14) * 2 - _PAD_H * 2 - _GAP - _CNT_W, dp(60)
        )
        rows = record.get("rows", [])
        for index, data in enumerate(rows):
            self.rows_box.add_widget(_make_row(index, data, main_w))
        self.rows_box.height = _ROW_H * len(rows)

    def delete_current(self, *_):
        if not self.history_id:
            return
        _confirm_delete(
            "确定删除这条解析记录吗？删除后无法恢复。",
            self._delete_current,
        )

    def _delete_current(self):
        self.history_store.delete(self.history_id)
        self.history_id = None
        self.manager.current = "history"


class NeteaseCommentApp(App):
    def build(self):
        self.title = "网易云评论查看器"
        Window.clearcolor = C_BG
        self.history_store = HistoryStore(self.user_data_dir)
        self.manager = ScreenManager()
        query_screen = Screen(name="query")
        query_screen.add_widget(
            Root(history_store=self.history_store, open_history=self.open_history)
        )
        self.history_screen = HistoryScreen(
            self.history_store, self.open_detail, name="history"
        )
        self.detail_screen = HistoryDetailScreen(
            self.history_store, name="history_detail"
        )
        self.manager.add_widget(query_screen)
        self.manager.add_widget(self.history_screen)
        self.manager.add_widget(self.detail_screen)
        return self.manager

    def open_history(self):
        self.history_screen.select_mode = False
        self.history_screen.selected.clear()
        self.manager.current = "history"

    def open_detail(self, history_id):
        self.detail_screen.show_record(history_id)
        self.manager.current = "history_detail"


if __name__ == "__main__":
    NeteaseCommentApp().run()
