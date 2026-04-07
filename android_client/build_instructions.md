# Android APK 构建指南

## 环境准备

### 1. 安装Python依赖
```bash
pip install -r requirements.txt
```

### 2. 安装Buildozer (Linux) 或 使用Git Bash

**Linux/Ubuntu:**
```bash
pip install buildozer
```

**Windows (使用WSL或Git Bash):**
```bash
pip install buildozer
```

### 3. 安装Android SDK

**Linux:**
```bash
# 安装Java JDK
sudo apt install openjdk-11-jdk

# 安装Android SDK
mkdir -p ~/android-sdk
cd ~/android-sdk
wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip
unzip commandlinetools-linux-9477386_latest.zip
mkdir cmdline-tools/latest
mv cmdline-tools/* cmdline-tools/latest/

# 设置环境变量
export ANDROID_HOME=~/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools
```

## 构建APK

### 方法一：使用buildozer命令
```bash
# 初始化buildozer
buildozer init

# 构建APK
buildozer android debug
```

### 方法二：使用构建脚本
```bash
python build_apk.py
```

## 输出文件

构建完成后，APK文件位于：
```
bin/remotecontrol-1.0.0-arm64-v8a_armeabi-v7a-debug.apk
```

## 安装到手机

```bash
# 通过USB安装
adb install bin/remotecontrol-1.0.0-...-debug.apk

# 或将APK文件复制到手机直接安装
```

## 使用方法

1. 确保手机和电脑在同一网络
2. 在电脑上运行 `RemoteControlServer.exe`
3. 记录显示的服务器IP地址和端口
4. 在手机上打开客户端
5. 输入服务器IP和端口
6. 点击"连接"按钮

## 功能说明

- **触摸屏幕**: 在远程电脑上进行鼠标移动和点击
- **左键/右键/双击**: 模拟鼠标按钮
- **屏幕显示**: 实时显示远程电脑画面

## 网络要求

- 手机和电脑需要在同一局域网内
- 或通过端口映射从外网访问
- 默认端口: 8888
