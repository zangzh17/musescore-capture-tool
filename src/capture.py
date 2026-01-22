#!/usr/bin/env python3
"""
MuseScore 乐谱截取核心模块
使用 Playwright 实现浏览器自动化，支持登录和乐谱截取
"""

import os
import re
import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime

from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import cairosvg
from PyPDF2 import PdfMerger


class MuseScoreCapture:
    """MuseScore 乐谱截取器"""
    
    def __init__(self, 
                 output_dir: str = "./downloads",
                 user_data_dir: str = "./browser_data",
                 headless: bool = True):
        """
        初始化截取器
        
        Args:
            output_dir: 输出文件目录
            user_data_dir: 浏览器用户数据目录（用于保存登录状态）
            headless: 是否使用无头模式
        """
        self.output_dir = Path(output_dir)
        self.user_data_dir = Path(user_data_dir)
        self.headless = headless
        
        # 创建必要目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
    
    async def start(self):
        """启动浏览器"""
        self.playwright = await async_playwright().start()

        # 构建启动参数
        args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-setuid-sandbox'
        ]

        # 非无头模式时添加窗口显示相关参数
        if not self.headless:
            args.extend([
                '--start-maximized',
                '--disable-gpu',  # WSL 兼容性
            ])

        # 使用持久化上下文以保存登录状态
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=self.headless,
            viewport={"width": 1920, "height": 1080} if self.headless else None,
            args=args
        )
        
        # 获取或创建页面
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()
    
    async def stop(self):
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def is_logged_in(self) -> bool:
        """检查是否已登录"""
        await self.page.goto("https://musescore.com/")
        await self.page.wait_for_load_state("networkidle")
        
        # 检查是否存在登录按钮（未登录状态）
        login_button = await self.page.query_selector('button:has-text("Log in")')
        return login_button is None
    
    async def wait_for_login(self, timeout: int = 300) -> bool:
        """
        等待用户手动登录
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            是否登录成功
        """
        await self.page.goto("https://musescore.com/user/login")
        await self.page.wait_for_load_state("networkidle")
        
        print("请在浏览器中完成登录...")
        
        # 等待登录完成（URL 变化或登录按钮消失）
        try:
            await self.page.wait_for_url(
                lambda url: "login" not in url,
                timeout=timeout * 1000
            )
            return True
        except:
            return False
    
    async def get_score_info(self, url: str) -> Dict:
        """
        获取乐谱信息
        
        Args:
            url: MuseScore 乐谱页面 URL
        
        Returns:
            乐谱信息字典
        """
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)  # 等待乐谱加载
        
        # 获取乐谱标题
        title = await self.page.evaluate('''() => {
            const titleEl = document.querySelector('h1') || document.querySelector('[class*="title"]');
            return titleEl ? titleEl.textContent.trim() : 'Unknown';
        }''')
        
        # 获取作曲家
        composer = await self.page.evaluate('''() => {
            const composerEl = document.querySelector('[class*="composer"]') || 
                              document.querySelector('a[href*="/user/"]');
            return composerEl ? composerEl.textContent.trim() : 'Unknown';
        }''')
        
        # 获取页数和 SVG URL
        score_info = await self.page.evaluate('''() => {
            const imgs = document.querySelectorAll('img[src*="score_"]');
            const scoreImgs = [];
            
            imgs.forEach(img => {
                const src = img.src;
                const alt = img.alt || '';
                
                // 只获取主乐谱图片（排除缩略图）
                if (src.includes('scoredata') && !src.includes('@') && !src.includes('bgclr')) {
                    // 从 alt 文本中提取页数信息
                    const pageMatch = alt.match(/(\\d+)\\s*of\\s*(\\d+)\\s*pages?/i);
                    scoreImgs.push({
                        src: src,
                        alt: alt,
                        currentPage: pageMatch ? parseInt(pageMatch[1]) : 1,
                        totalPages: pageMatch ? parseInt(pageMatch[2]) : 1
                    });
                }
            });
            
            return scoreImgs[0] || null;
        }''')
        
        return {
            "title": title,
            "composer": composer,
            "url": url,
            "score_info": score_info
        }
    
    async def capture_score_pages(self, url: str, progress_callback=None) -> Dict:
        """
        截取乐谱所有页面

        Args:
            url: MuseScore 乐谱页面 URL
            progress_callback: 进度回调函数

        Returns:
            截取结果
        """
        # 获取乐谱信息
        info = await self.get_score_info(url)

        if not info["score_info"]:
            return {"error": "无法获取乐谱信息，请确保已登录且有权限查看"}

        score_info = info["score_info"]
        total_pages = score_info["totalPages"]

        # 生成安全的文件名
        safe_title = re.sub(r'[^\w\s-]', '', info["title"])[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_subdir = self.output_dir / f"{safe_title}_{timestamp}"
        output_subdir.mkdir(parents=True, exist_ok=True)

        results = {
            "title": info["title"],
            "composer": info["composer"],
            "total_pages": total_pages,
            "output_dir": str(output_subdir),
            "pages": [],
            "pdf_file": None
        }

        pdf_files = []

        # 收集所有页面的 SVG URL（通过滚动页面触发懒加载）
        all_svg_urls = await self._collect_all_svg_urls(total_pages)

        if not all_svg_urls:
            return {"error": "无法获取乐谱 SVG URL，请确保已登录且有权限查看完整乐谱"}

        for page_num, svg_url in enumerate(all_svg_urls):
            if progress_callback:
                progress_callback(page_num + 1, len(all_svg_urls))

            # 下载 SVG
            svg_content = await self._download_svg(svg_url)

            if svg_content:
                svg_file = output_subdir / f"page_{page_num + 1}.svg"
                png_file = output_subdir / f"page_{page_num + 1}.png"
                pdf_file = output_subdir / f"page_{page_num + 1}.pdf"

                # 保存 SVG
                with open(svg_file, 'wb') as f:
                    f.write(svg_content)

                # 转换为 PNG
                try:
                    cairosvg.svg2png(
                        bytestring=svg_content,
                        write_to=str(png_file),
                        scale=2
                    )
                except Exception as e:
                    print(f"PNG 转换失败: {e}")

                # 转换为 PDF
                try:
                    cairosvg.svg2pdf(
                        bytestring=svg_content,
                        write_to=str(pdf_file)
                    )
                    pdf_files.append(str(pdf_file))
                except Exception as e:
                    print(f"PDF 转换失败: {e}")

                results["pages"].append({
                    "page": page_num + 1,
                    "svg": str(svg_file),
                    "png": str(png_file),
                    "pdf": str(pdf_file)
                })

        # 更新实际获取的页数
        results["total_pages"] = len(results["pages"])

        # 合并 PDF
        if len(pdf_files) > 0:
            merged_pdf = output_subdir / f"{safe_title}_complete.pdf"
            self._merge_pdfs(pdf_files, str(merged_pdf))
            results["pdf_file"] = str(merged_pdf)

        return results

    async def _collect_all_svg_urls(self, expected_pages: int) -> List[str]:
        """通过滚动页面收集所有 SVG URL"""
        collected_urls = set()

        # 先获取当前可见的 SVG
        await self._extract_svg_urls(collected_urls)

        # 尝试滚动页面加载更多
        scroller = await self.page.query_selector('#jmuse-scroller-component')
        if not scroller:
            scroller = await self.page.query_selector('[class*="score"]')

        if scroller:
            # 多次滚动以触发懒加载
            for _ in range(expected_pages + 5):
                await self.page.evaluate('''(scroller) => {
                    if (scroller) {
                        scroller.scrollTop += 800;
                    } else {
                        window.scrollBy(0, 800);
                    }
                }''', scroller)
                await asyncio.sleep(0.3)
                await self._extract_svg_urls(collected_urls)

                # 如果已经收集到足够的页面，提前结束
                if len(collected_urls) >= expected_pages:
                    break

        # 排序 URL（按页码）
        sorted_urls = sorted(collected_urls, key=lambda x: self._extract_page_num(x))
        return sorted_urls

    async def _extract_svg_urls(self, url_set: set):
        """从页面提取 SVG URL 并添加到集合"""
        urls = await self.page.evaluate('''() => {
            const urls = [];
            // 查找 img 标签中的 SVG
            document.querySelectorAll('img[src*="score_"]').forEach(img => {
                const src = img.src;
                if (src.includes('scoredata') && !src.includes('@') && !src.includes('bgclr')) {
                    urls.push(src);
                }
            });
            // 也查找可能的 object/embed 标签
            document.querySelectorAll('object[data*=".svg"], embed[src*=".svg"]').forEach(el => {
                const src = el.data || el.src;
                if (src && src.includes('score')) {
                    urls.push(src);
                }
            });
            return urls;
        }''')

        for url in urls:
            url_set.add(url)

    def _extract_page_num(self, url: str) -> int:
        """从 URL 中提取页码"""
        match = re.search(r'score_(\d+)', url)
        return int(match.group(1)) if match else 0
    
    async def _download_svg(self, url: str) -> Optional[bytes]:
        """通过浏览器下载 SVG 内容"""
        try:
            response = await self.page.request.get(url)
            if response.ok:
                return await response.body()
            else:
                print(f"下载失败: {url} (Status: {response.status})")
                return None
        except Exception as e:
            print(f"下载异常: {e}")
            return None
    
    def _merge_pdfs(self, pdf_files: List[str], output_path: str):
        """合并多个 PDF 文件"""
        merger = PdfMerger()
        for pdf in pdf_files:
            if os.path.exists(pdf):
                merger.append(pdf)
        merger.write(output_path)
        merger.close()
    
    async def capture_by_screenshot(self, url: str, progress_callback=None) -> Dict:
        """
        通过截图方式截取乐谱（备用方案）
        
        当 SVG 下载失败时，可以使用此方法通过页面截图获取乐谱
        """
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        # 获取乐谱信息
        info = await self.get_score_info(url)
        
        safe_title = re.sub(r'[^\w\s-]', '', info["title"])[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_subdir = self.output_dir / f"{safe_title}_{timestamp}"
        output_subdir.mkdir(parents=True, exist_ok=True)
        
        results = {
            "title": info["title"],
            "output_dir": str(output_subdir),
            "pages": []
        }
        
        # 进入全屏模式
        fullscreen_btn = await self.page.query_selector('button[aria-label*="Fullscreen"], button[hint*="Fullscreen"]')
        if fullscreen_btn:
            await fullscreen_btn.click()
            await asyncio.sleep(1)
        
        # 隐藏侧边栏
        hide_sidebar_btn = await self.page.query_selector('button[aria-label*="Hide sidebar"], button[hint*="Hide sidebar"]')
        if hide_sidebar_btn:
            await hide_sidebar_btn.click()
            await asyncio.sleep(0.5)
        
        # 获取乐谱容器
        score_container = await self.page.query_selector('#jmuse-scroller-component, [class*="score"]')
        
        if score_container:
            # 截取当前可见的乐谱
            screenshot_path = output_subdir / "score_screenshot.png"
            await score_container.screenshot(path=str(screenshot_path))
            results["pages"].append({
                "page": 1,
                "png": str(screenshot_path)
            })
        
        return results


# 命令行接口
async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="MuseScore 乐谱截取工具")
    parser.add_argument("url", nargs="?", help="MuseScore 乐谱 URL")
    parser.add_argument("--login", action="store_true", help="执行登录操作")
    parser.add_argument("--headless", action="store_true", help="使用无头模式")
    parser.add_argument("--output", "-o", default="./downloads", help="输出目录")
    
    args = parser.parse_args()
    
    capture = MuseScoreCapture(
        output_dir=args.output,
        headless=args.headless
    )
    
    try:
        await capture.start()
        
        if args.login:
            print("正在打开登录页面...")
            logged_in = await capture.wait_for_login()
            if logged_in:
                print("登录成功！")
            else:
                print("登录超时或失败")
                return
        
        if args.url:
            print(f"正在截取乐谱: {args.url}")
            
            def progress(current, total):
                print(f"进度: {current}/{total}")
            
            result = await capture.capture_score_pages(args.url, progress_callback=progress)
            
            if "error" in result:
                print(f"错误: {result['error']}")
            else:
                print(f"\n截取完成!")
                print(f"标题: {result['title']}")
                print(f"页数: {result['total_pages']}")
                print(f"输出目录: {result['output_dir']}")
                if result['pdf_file']:
                    print(f"PDF 文件: {result['pdf_file']}")
    
    finally:
        await capture.stop()


if __name__ == "__main__":
    asyncio.run(main())
