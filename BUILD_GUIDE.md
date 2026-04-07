# GitHub Actions 构建指南

## 快速开始

### 1. 创建 GitHub 仓库

1. 登录 [GitHub](https://github.com)
2. 点击 "New repository" 创建新仓库
3. 仓库名：`remote-control`（或其他名称）
4. 选择 **Public**（免费）
5. 点击 "Create repository"

### 2. 上传代码

**方法A：命令行上传**
```bash
# 在项目根目录执行
cd F:\000-CodeBuddy-work\remote_control

git init
git add .
git commit -m "Initial commit"

# 替换为你的仓库URL
git remote add origin https://github.com/你的用户名/remote-control.git
git push -u origin main
```

**方法B：网页上传**
1. 在仓库页面点击 "uploading an existing file"
2. 将 `server/` 和 `android_client/` 文件夹拖入
3. 点击 "Commit changes"

### 3. 触发构建

代码上传后，构建会自动开始：

1. 进入仓库的 **Actions** 页面
2. 看到 "Build Android APK" workflow 正在运行
3. 等待 10-15 分钟构建完成
4. 点击 workflow → Artifacts → 下载 APK

### 4. 手动触发构建

如果需要重新构建：
1. 进入仓库 → Actions 页面
2. 左侧选择 "Build Android APK"
3. 右侧点击 "Run workflow" → "Run workflow"

---

## APK 输出位置

构建成功后，APK 文件位于：
```
android_client/bin/remotecontrol-1.0.0-arm64-v8a_armeabi-v7a-debug.apk
```

---

## 安装到手机

1. 下载 APK 文件到电脑
2. 通过 USB/微信/QQ/网盘 传输到手机
3. 在手机上打开 APK 文件安装
4. 如果提示"禁止安装未知来源应用"，需要在设置中开启

---

## 常见问题

### Q: 构建失败怎么办？
A: 点击失败的 workflow 查看日志，根据错误信息修复代码后重新提交

### Q: 需要修改代码后重新构建？
A: 修改后重新 `git add . && git commit && git push`，构建会自动触发

### Q: APK 文件太大？
A: 当前是 debug 版本，约 50-80MB。正式发布可用 release 版本更小