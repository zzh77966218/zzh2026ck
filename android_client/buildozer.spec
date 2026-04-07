[app]

# 应用标题
title = RemoteControl

# 应用标识（需要唯一）
package.name = remotecontrol
package.domain = com.remotectrl

# 应用版本
version = 1.0.0

# 源代码目录
source.dir = .

# 支持的源文件
source.include_exts = py,png,jpg,kv,atlas,json,ttf

# 需要的Python版本
pydir_version = 3.8

# 依赖库
requirements = python3,kivy,kivymd,pillow,pyzbar,opensdl2

# 屏幕方向
orientation = portrait

# 全屏
fullscreen = 0

# Android配置
android.permissions = INTERNET,ACCESS_NETWORK_STATE,CAMERA

# Android元数据
android.meta_data = com.google.android.gms.version=@integer/google_play_services_version

# 图标（如果有的话）
# android.icon = 

# Android启动画面
android.landing_color = #1E88E5

# Android状态栏颜色
android.status_bar_color = #1E88E5

# Android需求
android.minapi = 21
android.api = 29

# iOS配置（不需要可以忽略）
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master
ios.ios_deploy_url = https://github.com/phonegap/ios-deploy
ios.ios_deploy_branch = 1.10.0

[buildozer]

# 构建日志级别
log_level = 2

# 构建警告
warn_on_root = 1

# 构建目录
build_dir = ./.buildozer

# 打包目录
bin_dir = ./bin

# 是否使用setup.py
setup_requires = 0

# PyInstaller配置（用于打包exe）
