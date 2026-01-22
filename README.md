[English](README_en.md) | **中文**

<div align="center">

# MuseScore 乐谱截取工具

一个可自部署的 Web 应用，用于从 MuseScore.com 截取乐谱，保存为 PNG 图片和 PDF 文件。

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![Playwright](https://img.shields.io/badge/Playwright-自动化-orange.svg)](https://playwright.dev/)
[![Docker](https://img.shields.io/badge/Docker-支持-blue.svg)](https://www.docker.com/)

</div>

---

## 功能特性

- **Web 界面** - 简单易用，粘贴乐谱链接即可开始
- **用户登录** - 支持登录 MuseScore 账户，持久化保存登录状态
- **自动分页** - 自动检测乐谱总页数并逐页截取
- **高质量输出** - 下载原始 SVG 矢量文件转换，确保最高清晰度
- **多种格式** - 为每页生成 PNG 和 PDF，并提供合并后的完整 PDF
- **任务管理** - 异步任务处理，实时显示进度
- **容器化部署** - Docker Compose 一键部署

## 技术架构

| 组件 | 技术 |
|------|------|
| 后端 | Flask (Python) |
| 浏览器自动化 | Playwright |
| SVG 处理 | CairoSVG |
| PDF 合并 | PyPDF2 |
| 前端 | HTML / CSS / JavaScript |

## 快速开始

### Docker 部署（推荐）

```bash
docker-compose up -d --build
```

### 本地开发

```bash
# 使用 uv
uv run app.py --port 5000

# 或使用 pip
pip install -r requirements.txt
python app.py --port 5000
```

启动后访问 `http://localhost:5000`

## 使用方法

### 1. 登录 MuseScore

点击 **登录** 按钮，在弹出的浏览器窗口中完成登录，然后点击 **完成登录**。

> 注意：远程服务器需要配置 VNC 或 X11 转发才能看到浏览器窗口。

### 2. 截取乐谱

1. 在 MuseScore 网站复制乐谱 URL
2. 粘贴到输入框
3. 点击 **开始截取**

### 3. 下载结果

- 实时查看进度（如："正在截取: 3/10 页"）
- 下载合并后的 PDF 或单独的 PNG 图片

## 项目结构

```
musescore-capture-tool/
├── app.py                  # Flask Web 应用
├── src/
│   └── capture.py          # 核心截取逻辑
├── templates/
│   └── index.html          # 前端模板
├── static/                 # 静态资源
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── downloads/              # 输出目录（自动创建）
└── browser_data/           # 浏览器数据（自动创建）
```

## 许可证

MIT
