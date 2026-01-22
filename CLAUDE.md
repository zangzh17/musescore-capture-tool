# MuseScore 乐谱截取工具 - 开发指南

## 项目概述

这是一个 Web 应用，用于从 MuseScore.com 截取乐谱并保存为 PNG/PDF 文件。通过 Playwright 进行浏览器自动化，支持用户登录以访问需要会员权限的完整乐谱。

## 技术架构

- **后端**: Flask + Playwright (异步浏览器自动化)
- **前端**: 原生 HTML/CSS/JavaScript
- **文件处理**: CairoSVG (SVG 转 PNG/PDF), PyPDF2 (PDF 合并)

### 核心文件

```
app.py              # Flask Web 服务，API 端点
src/capture.py      # 核心截取逻辑，Playwright 浏览器操作
templates/index.html # 前端界面
browser_data/       # 浏览器用户数据目录（保存登录状态）
downloads/          # 截取的乐谱输出目录
```

## 运行方式

```bash
# 本地运行
source .venv/bin/activate && python app.py --port 5000

# Docker 运行
docker-compose up -d --build
```

## 关键技术问题与解决方案

### 1. WSL 环境下浏览器窗口不显示

**问题**: 在 WSL 中运行时，Playwright 启动的浏览器窗口不显示。

**原因**: Flask 进程可能没有继承 `DISPLAY` 环境变量。

**解决方案** (`app.py:api_login_start`):
```python
# 确保 DISPLAY 环境变量已设置（WSL 需要）
if not os.environ.get('DISPLAY'):
    os.environ['DISPLAY'] = ':0'
```

**注意**: WSL 需要 WSLg 或 X11 转发才能显示 GUI 窗口。

### 2. browser_data 目录权限问题

**问题**: `browser_data` 目录如果被 root 用户创建（如之前用 sudo 运行过），普通用户无法写入，导致 `SingletonLock: Permission denied`。

**解决方案**:
```bash
# 修复权限
sudo chown -R $USER:$USER browser_data/

# 或删除重建
rm -rf browser_data/
```

### 3. SingletonLock 锁文件冲突

**问题**: Chromium 使用 `browser_data/SingletonLock` 防止多实例，如果浏览器异常退出，锁文件可能残留。

**解决方案** (`app.py`):
```python
# 清理可能残留的锁文件
lock_files = ['SingletonLock', 'SingletonSocket', 'SingletonCookie']
for lock_file in lock_files:
    lock_path = BROWSER_DATA_DIR / lock_file
    if lock_path.exists():
        lock_path.unlink()
```

### 4. Flask 异步函数与事件循环问题

**问题**: `run_async()` 每次创建新事件循环，导致跨事件循环的异步对象操作失败（如 `capture_instance.stop()` 卡住）。

**解决方案**: 对于需要关闭浏览器的操作，改用同步方式直接 `pkill` 终止进程：
```python
# 不调用异步 stop()，直接终止进程
capture_instance = None
subprocess.run(['pkill', '-f', f'--user-data-dir={BROWSER_DATA_DIR}'], ...)
```

### 5. SVG 下载 404 错误

**问题**: 只有第一页 SVG 下载成功，其他页面返回 404。

**原因**: MuseScore 页面使用懒加载，只有滚动到相应位置才会加载对应页面的 SVG。

**解决方案** (`src/capture.py:_collect_all_svg_urls`):
```python
# 通过滚动页面触发懒加载，收集所有 SVG URL
for _ in range(expected_pages + 5):
    await self.page.evaluate('scroller.scrollTop += 800')
    await asyncio.sleep(0.3)
    await self._extract_svg_urls(collected_urls)
```

### 6. 首次加载登录按钮无反应

**问题**: 首次访问时点击登录无反应，刷新后才正常。

**原因**: `/api/status` 会启动浏览器检查登录状态，阻塞且占用 `browser_data` 目录。

**解决方案**: `/api/status` 改为轻量检查，不启动浏览器：
```python
@app.route('/api/status')
def api_status():
    # 通过检查登录标记文件判断，不启动浏览器
    login_state_file = BROWSER_DATA_DIR / ".logged_in"
    logged_in = login_state_file.exists()
    return jsonify({"status": "ok", "logged_in": logged_in})
```

## Playwright 启动参数

```python
# 非无头模式（用于登录）
args = [
    '--disable-blink-features=AutomationControlled',  # 绕过自动化检测
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--start-maximized',  # 窗口最大化
    '--disable-gpu',      # WSL 兼容性
]
```

## 常见问题排查

### 浏览器无法启动
```bash
# 检查 Chrome 进程
ps aux | grep chrom

# 清理锁文件
rm -f browser_data/Singleton*

# 检查目录权限
ls -la browser_data/
```

### 登录状态丢失
登录状态保存在 `browser_data/` 目录中。如果删除该目录，需要重新登录。

### 乐谱截取失败
1. 确认已登录 MuseScore 账户
2. 检查乐谱 URL 是否正确
3. 查看控制台日志中的错误信息

## 开发注意事项

1. **异步与同步混用**: Flask 是同步框架，Playwright 是异步库。使用 `run_async()` 包装异步函数，但要注意事件循环的生命周期。

2. **浏览器实例管理**: 全局 `capture_instance` 需要小心管理，避免多个请求同时操作导致冲突。

3. **Docker 环境**: Docker 中无法显示 GUI，登录功能不可用。需要在本地登录后，将 `browser_data/` 目录复制到 Docker 中。

4. **MuseScore 网站变化**: 如果截取功能失效，可能是 MuseScore 网站结构变化，需要检查 `src/capture.py` 中的选择器和 URL 规则。
