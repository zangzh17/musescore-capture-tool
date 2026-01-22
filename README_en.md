**English** | [中文](README.md)

<div align="center">

# MuseScore Capture Tool

A self-hosted web application for capturing sheet music from MuseScore.com and saving it as PNG images and merged PDF files.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![Playwright](https://img.shields.io/badge/Playwright-Automation-orange.svg)](https://playwright.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

</div>

---

## Features

- **Web Interface** - Simple and intuitive UI, just paste the score link to start
- **User Login** - Support manual login to MuseScore account with persistent session
- **Auto Pagination** - Automatically detect total pages and capture each page
- **High Quality Output** - Convert from original SVG vector files for maximum clarity
- **Multiple Formats** - Generate individual PNG/PDF for each page, plus a merged PDF
- **Task Management** - Async task processing with real-time progress display

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask (Python) |
| Browser Automation | Playwright |
| SVG Processing | CairoSVG |
| PDF Merging | PyPDF2 |
| Frontend | HTML / CSS / JavaScript |

## Quick Start

### Docker 

```bash
docker-compose up -d --build
```

### Local Development (Recommended)

```bash
# Using uv
uv run app.py --port 5000

# Or using pip
pip install -r requirements.txt
python app.py --port 5000
```

Then open `http://localhost:5000` in your browser.

## Usage

### 1. Login to MuseScore

Click the **Login** button to open a browser window. Complete your MuseScore login, then click **Finish Login** in the web interface.

> Note: For remote servers, VNC or X11 forwarding is required to see the browser window.

### 2. Capture Sheet Music

1. Copy the URL of a score from MuseScore.com
2. Paste it into the input field
3. Click **Start Capture**

### 3. Download Results

- View real-time progress (e.g., "Capturing: 3/10 pages")
- Download the merged PDF or individual PNG images

## Project Structure

```
musescore-capture-tool/
├── app.py                  # Flask web application
├── src/
│   └── capture.py          # Core capture logic
├── templates/
│   └── index.html          # Frontend template
├── static/                 # Static assets
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── downloads/              # Output directory (auto-created)
└── browser_data/           # Browser session data (auto-created)
```

## License

MIT
