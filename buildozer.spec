[app]

# App 元信息
title = 网易云评论数查看器
package.name = netease_comment_viewer
package.domain = org.netease

# 源码
source.dir = .
source.include_exts = py,png,jpg,kv,atlas

# 入口文件
mainmodule = main

# Kivy 版本（固定兼容版本）
version = 0.1.0

# 依赖（核心 Kivy + KivyMD）
requirements = python3,kivy==2.3.0,KivyMD==1.1.1,pillow,urllib3

# Android 最低版本
android.minapi = 21
android.api = 34

# 权限（网络）
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# 主题：深色沉浸
android.theme = Theme_Dark_NoTitleBar

# 禁止点击水波纹（可选）
android.backdrop_color = 0.1, 0.1, 0.1, 1

# App 图标（默认用 Kivy 内置）
# icon.filename = %(source.dir)s/icon.png

# 启动画面（可选）
# splashimage.filename = %(source.dir)s/splash.png

# 日志等级
log_level = 2

# 忽略警告
warn_on_root = 0

# 架构：同时支持 arm64-v8a 和 armeabi-v7a
android.archs = arm64-v8a, armeabi-v7a

# 打包方式
fullscreen = 0

[pyaes]

[shepherd]

[buildozer]

# 日志文件
log_file = buildozer.log

# 构建输出目录
bin_dir = .
