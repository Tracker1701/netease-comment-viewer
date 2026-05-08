import os
from threading import Thread

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.textinput import TextInput

from netease_api import parse_url, query_album, query_artist

# ── 注册中文字体 ──────────────────────────────────────────────────────────────
# fonts/NotoSansSC.otf 与 main.py 同目录（source.dir = .）
_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "NotoSansSC.otf")
LabelBase.register(name="NotoSansSC", fn_regular=_FONT_PATH)

_FONT = "NotoSansSC"
# ─────────────────────────────────────────────────────────────────────────────


class ResultRow(RecycleDataViewBehavior, BoxLayout):
    album = StringProperty("")
    song = StringProperty("")
    comments = StringProperty("")
    is_header = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(54), **kwargs)
        self.padding = [dp(10), dp(6), dp(10), dp(6)]
        self.spacing = dp(8)
        self.album_label = Label(
            halign="left", valign="middle", size_hint_x=0.34, font_name=_FONT
        )
        self.song_label = Label(
            halign="left", valign="middle", size_hint_x=0.46, font_name=_FONT
        )
        self.comments_label = Label(
            halign="right", valign="middle", size_hint_x=0.2, font_name=_FONT
        )
        self.add_widget(self.album_label)
        self.add_widget(self.song_label)
        self.add_widget(self.comments_label)

    def refresh_view_attrs(self, rv, index, data):
        super().refresh_view_attrs(rv, index, data)
        self.album = data.get("album", "")
        self.song = data.get("song", "")
        self.comments = data.get("comments", "")
        self.is_header = data.get("is_header", False)
        color = (0.78, 0.18, 0.18, 1) if self.is_header else (0.16, 0.16, 0.16, 1)
        self.album_label.text = self.album
        self.song_label.text = self.song
        self.comments_label.text = self.comments
        for label in (self.album_label, self.song_label, self.comments_label):
            label.color = color
            label.bold = self.is_header
            label.text_size = (label.width, None)
        return self


class ResultsView(RecycleView):
    data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.viewclass = "ResultRow"
        layout = RecycleBoxLayout(
            default_size=(None, dp(54)),
            default_size_hint=(1, None),
            size_hint_y=None,
            orientation="vertical",
        )
        layout.bind(minimum_height=layout.setter("height"))
        self.add_widget(layout)


class Root(BoxLayout):
    progress = NumericProperty(0)
    status = StringProperty("就绪")
    summary = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(10), **kwargs)
        self.rows = []

        title = Label(
            text="网易云音乐评论数查看器",
            size_hint_y=None,
            height=dp(42),
            bold=True,
            font_size="20sp",
            font_name=_FONT,
            color=(0.78, 0.18, 0.18, 1),
        )
        self.add_widget(title)

        self.input_text = TextInput(
            hint_text="粘贴网易云音乐专辑或歌手分享链接",
            text="http://music.163.com/album/165230666/",
            multiline=True,
            size_hint_y=None,
            height=dp(96),
            font_size="16sp",
            font_name=_FONT,
        )
        self.add_widget(self.input_text)

        button_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        self.query_button = Button(
            text="开始查询",
            background_color=(0.78, 0.18, 0.18, 1),
            font_name=_FONT,
        )
        self.query_button.bind(on_press=self.start_query)
        clear_button = Button(
            text="清空",
            background_color=(0.55, 0.55, 0.55, 1),
            font_name=_FONT,
        )
        clear_button.bind(on_press=self.clear)
        button_row.add_widget(self.query_button)
        button_row.add_widget(clear_button)
        self.add_widget(button_row)

        self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(10))
        self.add_widget(self.progress_bar)
        self.bind(progress=lambda _obj, value: setattr(self.progress_bar, "value", value))

        self.status_label = Label(
            text=self.status,
            size_hint_y=None,
            height=dp(30),
            halign="left",
            valign="middle",
            font_name=_FONT,
            color=(0.42, 0.42, 0.42, 1),
        )
        self.status_label.bind(size=lambda label, _size: setattr(label, "text_size", label.size))
        self.bind(status=lambda _obj, value: setattr(self.status_label, "text", value))
        self.add_widget(self.status_label)

        self.results = ResultsView()
        self.add_widget(self.results)

        self.summary_label = Label(
            text="",
            size_hint_y=None,
            height=dp(52),
            halign="left",
            valign="middle",
            bold=True,
            font_name=_FONT,
            color=(0.78, 0.18, 0.18, 1),
        )
        self.summary_label.bind(size=lambda label, _size: setattr(label, "text_size", label.size))
        self.bind(summary=lambda _obj, value: setattr(self.summary_label, "text", value))
        self.add_widget(self.summary_label)

    def clear(self, *_args):
        self.input_text.text = ""
        self.results.data = []
        self.progress = 0
        self.status = "就绪"
        self.summary = ""

    def start_query(self, *_args):
        parsed = parse_url(self.input_text.text.strip())
        if not parsed:
            self.status = "未识别到专辑或歌手链接"
            return

        self.results.data = []
        self.progress = 0
        self.summary = ""
        self.query_button.disabled = True
        kind, entity_id = parsed
        Thread(target=self._run_query, args=(kind, entity_id), daemon=True).start()

    def _run_query(self, kind: str, entity_id: str):
        try:
            def on_progress(current, total, message):
                Clock.schedule_once(lambda _dt: self._set_progress(current, total, message))

            if kind == "album":
                rows, summary = query_album(entity_id, on_progress)
            else:
                rows, summary = query_artist(entity_id, on_progress)

            Clock.schedule_once(lambda _dt: self._show_result(rows, summary))
        except Exception as exc:
            Clock.schedule_once(lambda _dt: self._show_error(str(exc)))
        finally:
            Clock.schedule_once(lambda _dt: setattr(self.query_button, "disabled", False))

    def _set_progress(self, current: int, total: int, message: str):
        self.progress = current / max(total, 1) * 100
        self.status = message

    def _show_result(self, rows: list[dict], summary: str):
        self.results.data = rows
        self.progress = 100
        self.status = "完成"
        self.summary = summary

    def _show_error(self, message: str):
        self.status = f"请求失败：{message}"


class NeteaseCommentApp(App):
    def build(self):
        self.title = "网易云评论查看器"
        return Root()


if __name__ == "__main__":
    NeteaseCommentApp().run()
