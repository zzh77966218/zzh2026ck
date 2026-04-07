# -*- coding: utf-8 -*-
"""
Android APK 构建脚本
用于在Windows环境下构建Android应用
"""

import os
import sys
import subprocess
import shutil

def run_command(cmd, cwd=None):
    """运行命令"""
    print(f"执行: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode == 0

def check_dependencies():
    """检查依赖"""
    print("=" * 50)
    print("检查构建环境...")
    print("=" * 50)
    
    # 检查Python
    try:
        version = sys.version_info
        print(f"✓ Python {version.major}.{version.minor}")
    except:
        print("✗ Python 未安装")
        return False
    
    # 检查pip
    if run_command("pip --version"):
        print("✓ pip 已安装")
    
    # 检查Java
    java_check = subprocess.run("java -version", capture_output=True, text=True)
    if java_check.returncode == 0:
        print("✓ Java 已安装")
    else:
        print("✗ Java 未安装")
    
    return True

def install_dependencies():
    """安装依赖"""
    print("\n" + "=" * 50)
    print("安装Python依赖...")
    print("=" * 50)
    
    requirements = [
        "kivy>=2.1.0",
        "kivymd>=1.1.0",
        "pillow>=9.0.0",
        "buildozer>=1.4.0"
    ]
    
    for req in requirements:
        print(f"安装 {req}...")
        os.system(f"pip install {req}")

def init_buildozer():
    """初始化Buildozer"""
    print("\n" + "=" * 50)
    print("初始化Buildozer...")
    print("=" * 50)
    
    # 检查spec文件
    if not os.path.exists("buildozer.spec"):
        print("创建 buildozer.spec 文件...")
        # 使用默认值创建spec文件
        spec_content = '''[app]

title = RemoteControl
package.name = remotecontrol
package.domain = com.remotectrl
source.include_exts = py,png,jpg,kv,atlas,json,ttf
requirements = python3,kivy,kivymd,pillow
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.minapi = 21
android.api = 29
android.landing_color = #1E88E5
android.status_bar_color = #1E88E5

[buildozer]
log_level = 2
warn_on_root = 1
'''
        with open("buildozer.spec", "w", encoding="utf-8") as f:
            f.write(spec_content)
        print("✓ buildozer.spec 已创建")

def build_debug_apk():
    """构建Debug APK"""
    print("\n" + "=" * 50)
    print("构建Debug APK...")
    print("=" * 50)
    
    # 创建bin目录
    os.makedirs("bin", exist_ok=True)
    
    # 使用buildozer构建
    success = run_command("buildozer android debug", cwd=os.getcwd())
    
    if success:
        print("\n" + "=" * 50)
        print("✓ 构建成功!")
        print("=" * 50)
        
        # 列出输出文件
        if os.path.exists("bin"):
            print("\n输出文件:")
            for f in os.listdir("bin"):
                if f.endswith(".apk"):
                    full_path = os.path.join(os.getcwd(), "bin", f)
                    size = os.path.getsize(full_path) / (1024 * 1024)
                    print(f"  - {f} ({size:.2f} MB)")
    else:
        print("\n" + "=" * 50)
        print("✗ 构建失败")
        print("=" * 50)
        print("\n提示:")
        print("1. 确保已安装Android SDK")
        print("2. 设置 ANDROID_HOME 环境变量")
        print("3. 在Linux/WSL环境下运行: buildozer android debug")

def main():
    """主函数"""
    print("=" * 50)
    print("  远程控制客户端 - APK构建工具")
    print("=" * 50)
    
    # 检查环境
    if not check_dependencies():
        input("\n按Enter键退出...")
        return
    
    # 安装依赖
    install_dependencies()
    
    # 初始化
    init_buildozer()
    
    # 构建
    build_debug_apk()
    
    print("\n" + "=" * 50)
    print("构建完成!")
    print("=" * 50)
    print("\n注意: 在Windows下完整构建需要:")
    print("1. 安装Linux子系统(WSL)或使用Linux系统")
    print("2. 安装Android SDK")
    print("3. 配置JAVA_HOME和ANDROID_HOME")

if __name__ == "__main__":
    main()
