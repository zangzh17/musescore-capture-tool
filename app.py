#!/usr/bin/env python3
"""
MuseScore 乐谱截取工具 - Web 服务
提供 Web 界面和 API 接口
"""

import os
import asyncio
import json
import uuid
from pathlib import Path
from datetime import datetime
from threading import Thread
from queue import Queue

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import threading

from src.capture import MuseScoreCapture

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
CORS(app)

# 配置
DOWNLOADS_DIR = Path("./downloads")
BROWSER_DATA_DIR = Path("./browser_data")
DOWNLOADS_DIR.mkdir(exist_ok=True)
BROWSER_DATA_DIR.mkdir(exist_ok=True)

# 任务状态存储
tasks = {}

# 全局截取器实例（用于保持登录状态）
capture_instance = None
capture_lock = threading.Lock()  # 使用 threading.Lock 而不是 asyncio.Lock


def get_event_loop():
    """获取或创建事件循环"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


async def get_capture_instance(headless=True):
    """获取或创建截取器实例"""
    global capture_instance

    with capture_lock:
        if capture_instance is None:
            capture_instance = MuseScoreCapture(
                output_dir=str(DOWNLOADS_DIR),
                user_data_dir=str(BROWSER_DATA_DIR),
                headless=headless
            )

    # start() 需要在锁外调用，因为它是异步的
    if capture_instance.page is None:
        await capture_instance.start()

    return capture_instance


def run_async(coro):
    """在新线程中运行异步函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        # 不要关闭循环，因为可能有持久对象引用它
        pass


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    """检查服务状态和登录状态（轻量检查，不启动浏览器）"""
    # 通过检查浏览器数据目录中的 Cookies 文件来判断是否曾经登录
    # 这样不需要启动浏览器，速度更快
    cookies_file = BROWSER_DATA_DIR / "Default" / "Cookies"
    login_state_file = BROWSER_DATA_DIR / ".logged_in"

    # 检查是否有登录标记文件（由完成登录时创建）
    logged_in = login_state_file.exists()

    return jsonify({"status": "ok", "logged_in": logged_in})


@app.route('/api/login/start', methods=['POST'])
def api_login_start():
    """开始登录流程（非无头模式）"""
    # 检查是否在无显示环境中运行（如 Docker）
    display = os.environ.get('DISPLAY')
    in_docker = os.path.exists('/.dockerenv')

    if in_docker and not display:
        return jsonify({
            "status": "error",
            "message": "登录功能在 Docker 容器中不可用（无图形界面）。请在本地运行应用，或使用已登录的浏览器数据目录。"
        }), 400

    async def start_login():
        global capture_instance
        import time
        import subprocess

        try:
            # 确保 DISPLAY 环境变量已设置（WSL 需要）
            if not os.environ.get('DISPLAY'):
                os.environ['DISPLAY'] = ':0'

            # 关闭现有实例
            if capture_instance:
                try:
                    await capture_instance.stop()
                except Exception:
                    pass
                capture_instance = None
                # 等待浏览器完全关闭
                time.sleep(2)

            # 强制终止可能残留的 Chrome 进程（使用 browser_data 目录的）
            try:
                subprocess.run(
                    ['pkill', '-f', f'--user-data-dir={BROWSER_DATA_DIR}'],
                    capture_output=True,
                    timeout=5
                )
                time.sleep(1)
            except Exception:
                pass

            # 清理可能残留的锁文件
            lock_files = ['SingletonLock', 'SingletonSocket', 'SingletonCookie']
            for lock_file in lock_files:
                lock_path = BROWSER_DATA_DIR / lock_file
                if lock_path.exists():
                    try:
                        lock_path.unlink()
                    except Exception:
                        pass

            # 创建非无头模式实例
            capture_instance = MuseScoreCapture(
                output_dir=str(DOWNLOADS_DIR),
                user_data_dir=str(BROWSER_DATA_DIR),
                headless=False  # 显示浏览器窗口
            )
            await capture_instance.start()

            # 导航到登录页面
            await capture_instance.page.goto("https://musescore.com/user/login")

            return {"status": "ok", "message": "请在弹出的浏览器窗口中完成登录"}
        except Exception as e:
            return {"status": "error", "message": f"启动浏览器失败: {str(e)}"}

    result = run_async(start_login())
    return jsonify(result)


@app.route('/api/login/check', methods=['GET'])
def api_login_check():
    """检查登录状态"""
    async def check_login():
        if capture_instance is None:
            return {"logged_in": False, "message": "浏览器未启动"}
        
        logged_in = await capture_instance.is_logged_in()
        return {"logged_in": logged_in}
    
    result = run_async(check_login())
    return jsonify(result)


@app.route('/api/login/finish', methods=['POST'])
def api_login_finish():
    """完成登录，切换回无头模式"""
    global capture_instance
    import subprocess
    import time

    logged_in = False

    if capture_instance:
        # 检查当前页面 URL 判断是否登录成功（同步方式）
        try:
            current_url = capture_instance.page.url
            logged_in = 'login' not in current_url.lower()
        except Exception:
            logged_in = False

        # 直接将实例置空，不调用异步 stop()
        capture_instance = None

    # 强制终止所有使用 browser_data 目录的 Chrome 进程
    try:
        subprocess.run(
            ['pkill', '-f', f'--user-data-dir={BROWSER_DATA_DIR}'],
            capture_output=True,
            timeout=5
        )
    except Exception:
        pass

    time.sleep(1)

    # 清理锁文件
    lock_files = ['SingletonLock', 'SingletonSocket', 'SingletonCookie']
    for lock_file in lock_files:
        lock_path = BROWSER_DATA_DIR / lock_file
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass

    # 创建或删除登录标记文件
    login_state_file = BROWSER_DATA_DIR / ".logged_in"
    if logged_in:
        login_state_file.touch()
    elif login_state_file.exists():
        try:
            login_state_file.unlink()
        except Exception:
            pass

    return jsonify({"status": "ok", "logged_in": logged_in})


@app.route('/api/capture', methods=['POST'])
def api_capture():
    """开始截取乐谱"""
    data = request.json
    url = data.get('url')

    if not url:
        return jsonify({"error": "请提供乐谱 URL"}), 400

    # 验证 URL
    if 'musescore.com' not in url:
        return jsonify({"error": "请提供有效的 MuseScore URL"}), 400

    # 创建任务
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "url": url,
        "status": "pending",
        "progress": 0,
        "total_pages": 0,
        "current_page": 0,
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }

    # 在后台线程中执行截取
    def run_capture():
        async def do_capture():
            # 为每个任务创建独立的浏览器实例，避免跨事件循环问题
            capture = MuseScoreCapture(
                output_dir=str(DOWNLOADS_DIR),
                user_data_dir=str(BROWSER_DATA_DIR),
                headless=True
            )
            try:
                await capture.start()
                tasks[task_id]["status"] = "running"

                def progress_callback(current, total):
                    tasks[task_id]["current_page"] = current
                    tasks[task_id]["total_pages"] = total
                    tasks[task_id]["progress"] = int(current / total * 100) if total > 0 else 0

                result = await capture.capture_score_pages(url, progress_callback)

                if "error" in result:
                    tasks[task_id]["status"] = "error"
                    tasks[task_id]["error"] = result["error"]
                else:
                    tasks[task_id]["status"] = "completed"
                    tasks[task_id]["result"] = result
                    tasks[task_id]["progress"] = 100

            except Exception as e:
                tasks[task_id]["status"] = "error"
                tasks[task_id]["error"] = str(e)
            finally:
                await capture.stop()

        run_async(do_capture())

    thread = Thread(target=run_capture)
    thread.start()

    return jsonify({"task_id": task_id, "status": "pending"})


@app.route('/api/task/<task_id>')
def api_task_status(task_id):
    """获取任务状态"""
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    return jsonify(task)


@app.route('/api/tasks')
def api_tasks():
    """获取所有任务列表"""
    return jsonify(list(tasks.values()))


@app.route('/api/download/<task_id>/<filename>')
def api_download(task_id, filename):
    """下载文件"""
    task = tasks.get(task_id)
    if not task or not task.get("result"):
        return jsonify({"error": "任务不存在或未完成"}), 404
    
    output_dir = task["result"]["output_dir"]
    file_path = os.path.join(output_dir, filename)
    
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    
    return jsonify({"error": "文件不存在"}), 404


@app.route('/api/download-pdf/<task_id>')
def api_download_pdf(task_id):
    """下载合并的 PDF"""
    task = tasks.get(task_id)
    if not task or not task.get("result"):
        return jsonify({"error": "任务不存在或未完成"}), 404
    
    pdf_file = task["result"].get("pdf_file")
    if pdf_file and os.path.exists(pdf_file):
        return send_file(pdf_file, as_attachment=True)
    
    return jsonify({"error": "PDF 文件不存在"}), 404


@app.route('/downloads/<path:filename>')
def serve_download(filename):
    """提供下载文件"""
    return send_from_directory(DOWNLOADS_DIR, filename)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=5000, help='监听端口')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    
    args = parser.parse_args()
    
    print(f"MuseScore 乐谱截取工具")
    print(f"访问 http://localhost:{args.port} 使用 Web 界面")
    print(f"API 文档: http://localhost:{args.port}/api/status")
    
    app.run(host=args.host, port=args.port, debug=args.debug)
