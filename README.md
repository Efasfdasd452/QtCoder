# 🚀 QtCoder - 开发工具箱

基于 **Python + PyQt5** 的桌面工具，集成编码/加解密、cURL 转代码、电子书转换、视频压缩、端口扫描等常用功能，**本地运行、数据不上传**。

---

## ✨ 功能概览

### 🔤 编码转换
- **编码 / 解码** — Base64、URL、Hex、Unicode、摩尔斯等
- **JSON 格式化** — 美化、压缩、语法验证
- **HTML 美化** — 格式化，XPath / 正则搜索
- **简繁转换** — 简体 / 繁体 / 台湾 / 香港变体
- **乱码修复** — 自动检测编码并修复
- **汉字笔画** — 统计笔画数
- **Base64→图片** — 批量解码并保存为图片

### 🛡️ 加密安全
- **加密 / 解密** — AES、3DES、ChaCha20、Salsa20 等
- **哈希 / 摘要** — MD5、SHA、BLAKE2、HMAC
- **密文识别** — 识别 MD5、bcrypt、JWT 等
- **SSH 密钥** — RSA / Ed25519 / ECDSA 生成与导出
- **OpenSSL 密钥** — PEM/DER/OpenSSH 导出
- **自签名证书** — HTTPS 证书（含 SAN，nginx/Apache 可用）
- **UUID 生成** — v1/v3/v4/v5 批量生成

### 🔧 开发辅助
- **时区转换** — 世界时钟、Unix 时间戳 ↔ 日期时间
- **JWT 解析** — 解码并检查过期
- **Cookie 解析** — 解析请求头 / Set-Cookie，生成 requests 代码
- **URL 解析** — 解析查询参数，生成 Python 代码
- **配置格式转换** — JSON / YAML / TOML 互转
- **文件哈希** — 批量 MD5/SHA，支持校验
- **Doc → PDF** — 批量 .doc/.docx 转 PDF
- **电子书转换** — EPUB / PDF / MOBI 互转（依赖 Calibre）
- **cURL 转换** — 转为 Python / Go / Java / PHP 等
- **JSON 转代码** — 转 C++ / Java / Python / PHP / TypeScript 类定义
- **下划线↔驼峰** — 命名风格互转
- **正则测试** — 实时匹配与高亮
- **字符串比对** — 逐行/逐字符差异高亮

### 🌐 网络工具
- **端口扫描** — TCP 端口检测与服务识别
- **代理测试** — HTTP / SOCKS5 代理测试
- **防火墙规则** — iptables/ufw/firewalld/nftables/netsh 生成
- **种子↔磁力** — 种子转磁力（本地）/ 磁力转种子（需联网）

### 🎬 媒体工具
- **水印检测** — 隐藏水印检测 / 嵌入 / 提取
- **视频压缩** — FFmpeg，H.264/H.265/AV1，支持硬件加速
- **图片压缩** — 批量 JPEG/PNG/WebP 压缩

---

## 📦 安装与运行

### 1. 克隆仓库

```bash
git clone https://github.com/yourname/QtCoder.git
cd QtCoder
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 3. 启动程序

```bash
python main.py
```

---

## 📤 打包发布

如需打包成独立可执行文件（如 `dist/QtCoder/QtCoder.exe`），使用项目自带的 `build.py`。

### 打包前需要准备

| 内容 | 说明 | 必须 |
|------|------|------|
| **Python 虚拟环境** | 项目根目录下 `.venv`，且已 `pip install -r requirements.txt` | ✅ |
| **FFmpeg** | 用于视频压缩、水印等。按目标平台放入对应目录： | ✅ |
| | **Windows**：将 FFmpeg 的 `bin` 目录内容放入 `vendor/ffmpeg/bin/` | |
| | **Linux**：放入 `linux_ffmpeg/ffmpeg/bin/` | |
| | 也可先不放，执行 `python build.py --download-ffmpeg` 自动下载本机平台 FFmpeg | |
| **Calibre**（电子书转换） | 将 [Calibre 便携版](https://calibre-ebook.com/download) 解压到 `bin/calibre/`，打包时会一并复制到发行目录；不准备则打包后不包含，用户需自行下载并解压到**路径少于 59 字符**的目录，再在软件内「指定路径」 | 可选 |
| **nmap**（端口扫描） | 将 nmap 放入 `bin/nmap/`，打包时会打进发行包；不准备则端口扫描功能不可用 | 可选 |

### 打包命令

```bash
# 激活虚拟环境后执行
python build.py
```

常用参数：

- `python build.py` — 自动检测本机平台，完整打包（会先清理 build/dist）
- `python build.py --target win64` — 指定目标平台为 Windows x64
- `python build.py --download-ffmpeg` — 仅下载本机平台 FFmpeg，不打包
- `python build.py --clean` — 仅清理 `build/` 和 `dist/`
- `python build.py --no-clean` — 打包前不清理旧文件

### 打包结果

- 输出目录：`dist/QtCoder/`
- 内含：`QtCoder.exe`（或 Linux 下无后缀可执行文件）、依赖库、`ffmpeg/`、若准备了则还有 `bin/calibre/` 等。
- 若未包含 Calibre：运行后可在「电子书转换」面板中按提示，将 Calibre 解压到短路径（如 `C:\ec\calibre`），再通过「浏览」指定 `ebook-convert.exe`。

---

## 🛠️ 技术栈

- Python 3.x
- PyQt5
- PyCryptodome / cryptography
- 其他见 `requirements.txt`

---

## 📄 License

MIT License。

---

如对你有帮助，欢迎 ⭐ Star。
