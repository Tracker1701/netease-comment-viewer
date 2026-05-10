[app]

# App 元信息
title = 云评
package.name = netease_comment_viewer
package.domain = org.netease

# 源码
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,otf,svg,java,xml

# 入口文件
mainmodule = main

# Kivy 版本（固定兼容版本）
version = 1.0.0

# 依赖（仅使用核心 Kivy，不引入未使用的 KivyMD）
requirements = python3,kivy==2.3.0,pillow

# Android 最低版本
android.minapi = 21
android.api = 34

# 权限（网络）
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# Java 源码目录（CloudHttpHelper.java）
android.add_src = java

# 网络安全配置资源目录（含 res/xml/network_security_config.xml）
android.res = android/res

# manifest application 属性：启用网络安全配置
android.manifest.application_attributes = android:networkSecurityConfig="@xml/network_security_config"

# App 图标：项目根目录 icon.png（512×512）
icon.filename = icon.png

# 启动画面（可选）
# splashimage.filename = %(source.dir)s/splash.png

# 日志等级
log_level = 2

# 忽略警告
warn_on_root = 0

# 架构：仅 arm64-v8a（省去 armeabi-v7a 避免 p4a dist 复用 bug）
android.archs = arm64-v8a

# 打包方式
fullscreen = 0

[pyaes]

[shepherd]

[buildozer]

# Android SDK（CI 用 GitHub Actions 提供的路径）
android.sdk = /usr/local/lib/android/sdk

# 日志文件
log_file = buildozer.log

# 构建输出目录
bin_dir = .
