# 🎵 网易云评论数查看器（Android）

<!-- CI trigger -->

基于 Kivy/KivyMD 的 Android 应用，无需 Python 环境，直接安装 APK 使用。

## 功能

- 🎧 **专辑模式**：粘贴分享文本，自动提取专辑 ID，列出专辑内所有歌曲的评论数，并汇总专辑评论数
- 👤 **歌手模式**：粘贴歌手链接，自动遍历该歌手所有专辑，展开每张专辑的歌曲评论数
- 📊 **进度条**：实时显示抓取进度和当前歌曲名
- 📥 **导出 CSV**：一键导出为 Excel 可直接打开的 CSV 文件
- 🔗 **自动识别**：无需手动提取 URL，直接粘贴分享文本即可

## 截图预览

> （首次构建完成后，APK 产物会自动出现在 GitHub Actions 的 Artifacts 中）

## API 说明

本项目调用的是网易云音乐官方公开 HTTP API，无需登录、无需加密参数：

| 功能 | API 端点 |
|---|---|
| 专辑歌曲列表 | `GET /api/v1/album/{id}` |
| 歌手全部专辑 | `GET /api/artist/albums/{id}` |
| 歌曲评论数 | `GET /api/v1/resource/comments/R_SO_4_{songId}` |
| 专辑评论数 | `GET /api/v1/resource/comments/R_AL_3_{albumId}` |

> ⚠️ 仅供学习研究使用，请勿高频请求或用于商业用途，遵守网易云音乐服务条款。

## 本地开发

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 2. 安装依赖（桌面预览）
pip install kivy==2.3.0 kivymd pillow

# 3. 运行桌面预览
python main.py
```

## 构建 APK

### 方式一：GitHub Actions（推荐，无需本地 Linux）

1. 将代码推送到 GitHub 仓库
2. 打开 **Actions** 标签页，点击 **Build Android APK**
3. 构建完成后，在 Artifacts 中下载 `netease-comment-viewer-apk`
4. 将 APK 传到手机安装（需允许"未知来源"安装）

> 首次构建约需 20-30 分钟（下载 Android SDK/NDK），后续构建约 10 分钟。

### 方式二：本地 Buildozer（需 Linux/macOS + Android SDK）

```bash
pip install buildozer==1.5.0
buildozer android debug
# 产物在 bin/ 目录
```

## 项目结构

```
netease_kivy/
├── main.py              # Kivy 应用主入口
├── buildozer.spec       # Buildozer 构建配置
├── README.md            # 本文件
├── LICENSE              # MIT 许可证
└── .github/
    └── workflows/
        └── build.yml    # GitHub Actions 自动构建脚本
```

## 许可证

MIT License - 详见 [LICENSE](./LICENSE) 文件。
