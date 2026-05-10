# 云评 — 网易云音乐评论数查看器

查看网易云音乐专辑或歌手的每首歌评论数，无需电脑，直接在 Android 手机上使用。

## 下载安装

前往 [Releases](https://github.com/Tracker1701/netease-comment-viewer/releases/latest) 下载最新 APK，传到手机后允许"未知来源"安装即可。

## 功能

- **专辑模式**：粘贴专辑分享链接，列出每首歌的评论数并汇总
- **歌手模式**：粘贴歌手链接，遍历全部专辑并展示每首歌评论数
- **实时进度**：进度条 + 当前正在查询的歌名
- **深色主题**：暗红配色，护眼舒适

## 使用方法

1. 在网易云音乐 App 里分享专辑或歌手页面，复制链接
2. 粘贴进输入框
3. 点击「开始查询」

支持的链接格式：
```
http://music.163.com/album/165230666/
http://music.163.com/artist?id=144290
分享歌手KIV： http://music.163.com/artist?id=144290&userid=...（来自@网易云音乐）
```

## API 说明

调用网易云音乐官方公开 HTTP API，无需登录：

| 功能 | 端点 |
|---|---|
| 专辑歌曲列表 | `GET /api/v1/album/{id}` |
| 歌手全部专辑 | `GET /api/artist/albums/{id}` |
| 歌曲评论数 | `GET /api/v1/resource/comments/R_SO_4_{songId}` |
| 专辑评论数 | `GET /api/v1/resource/comments/R_AL_3_{albumId}` |

> 仅供学习研究，请勿高频请求或商业使用，遵守网易云音乐服务条款。

## 本地运行（桌面预览）

```bash
pip install kivy==2.3.0 pillow
python main.py
```

## 构建 APK

推送到 main 分支后 GitHub Actions 自动构建，产物在 Actions → Artifacts。

## 项目结构

```
├── main.py                  # Kivy 应用主体
├── netease_api.py           # 网易云 API 封装
├── buildozer.spec           # 构建配置
├── fonts/NotoSansSC.otf     # 中文字体
├── icon.png                 # 应用图标
├── android/res/             # 自适应图标资源 + 网络安全配置
├── java/                    # Android Java 辅助类（HTTP）
└── .github/workflows/       # GitHub Actions CI
```

## 许可证

MIT — 详见 [LICENSE](./LICENSE)
