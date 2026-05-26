import os
import json
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from langchain_groq import ChatGroq

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_PATH = os.path.join(PROJECT_ROOT, "profile.json")

class OverleafBot:
    def __init__(self):
        # Load profile safely
        self.profile = {}
        if os.path.exists(PROFILE_PATH):
            try:
                with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                    self.profile = json.load(f)
            except Exception as e:
                print(f"[OVERLEAF] Error loading profile: {e}")
        
        # Load API keys
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        # Setup directories and cookies paths
        self.cookies_dir = os.path.join(PROJECT_ROOT, "memory")
        os.makedirs(self.cookies_dir, exist_ok=True)
        self.cookies_path = os.path.join(self.cookies_dir, "overleaf_cookies.json")

    async def _init_browser(self):
        self.playwright = await async_playwright().start()
        
        # Launch with user data directory so cookies persist
        # and LinkedIn doesn't block it
        user_data_dir = os.path.join(os.getcwd(), "memory", "chrome_profile")
        
        self.browser = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--start-maximized',
            ],
            ignore_https_errors=True,
            # Make it look like real Chrome not automation
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
            java_script_enabled=True,
        )
        self.page = self.browser.pages[0] if self.browser.pages else await self.browser.new_page()
        
        # Remove automation flags that trigger "not safe" warning
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            window.chrome = {runtime: {}};
        """)

    async def _handle_login(self, page, context, project_url: str) -> None:
        """Handles session cookie restoring and manual login fallback."""
        # Restore cookies if exist
        if os.path.exists(self.cookies_path):
            try:
                with open(self.cookies_path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    await context.add_cookies(cookies)
                print("[OVERLEAF] Restored stored session cookies.")
            except Exception as e:
                print(f"[OVERLEAF] Warning: Failed to load cookies: {e}")

        # Navigate to project URL
        print(f"[OVERLEAF] Navigating to Overleaf project: {project_url}...")
        await page.goto(project_url, wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # Check if login is needed
        is_logged_in = False
        try:
            # Overleaf's editor has .cm-content element
            if await page.locator(".cm-content").is_visible():
                is_logged_in = True
        except Exception:
            pass

        if not is_logged_in:
            print("[OVERLEAF] Session expired or not logged in. Opening Overleaf login page...")
            if "login" not in page.url:
                await page.goto("https://www.overleaf.com/login", wait_until="domcontentloaded")
            
            print("[OVERLEAF] Awaiting manual user login (Timeout: 60s). Please log in now in the browser...")
            
            # Wait up to 60s for the editor panel to appear
            login_success = False
            for sec in range(60):
                await asyncio.sleep(1)
                if "project" in page.url:
                    try:
                        if await page.locator(".cm-content").is_visible():
                            login_success = True
                            break
                    except Exception:
                        pass
            
            if login_success:
                print("[OVERLEAF] Overleaf login detected! Saving session cookies...")
                cookies = await context.cookies()
                with open(self.cookies_path, "w", encoding="utf-8") as f:
                    json.dump(cookies, f, indent=2)
            else:
                raise RuntimeError("Overleaf login timed out. Please try running the bot again after logging in.")

    async def get_current_resume_text(self) -> str:
        """Open Overleaf, read the LaTeX source, and return it as text."""
        project_url = self.profile.get("overleaf", {}).get("project_url")
        if not project_url:
            raise ValueError("Overleaf project_url not configured in profile.json.")

        await self._init_browser()
        page = self.page
        context = self.browser

        try:
                await self._handle_login(page, context, project_url)
                
                # Fetch text content from CodeMirror editor
                editor = page.locator(".cm-content")
                await editor.wait_for(state="visible", timeout=15000)
                
                # Try evaluating the editor content directly using JS (highly reliable for CM6)
                content = await page.evaluate("""() => {
                    const el = document.querySelector('.cm-content');
                    if (el && el.cmView && el.cmView.view) {
                        return el.cmView.view.state.doc.toString();
                    }
                    return el ? el.innerText : '';
                }""")
                
                if not content or content.strip() == "":
                    content = await editor.text_content()
                
                return content
            finally:
                try:
                    await self.browser.close()
                    await self.playwright.stop()
                except Exception:
                    pass

    async def tailor_resume(self, job_description: str) -> str:
        """
        Tailors the LaTeX resume on Overleaf for a specific job description,
        recompiles the project, and downloads the compiled PDF.
        """
        project_url = self.profile.get("overleaf", {}).get("project_url")
        if not project_url:
            raise ValueError("Overleaf project_url not configured in profile.json.")

        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable is missing.")

        print("[OVERLEAF] Commencing resume tailoring workflow...")
        
        await self._init_browser()
        page = self.page
        context = self.browser

        try:
                # Step 1: Open project and get current resume LaTeX
                await self._handle_login(page, context, project_url)
                
                editor = page.locator(".cm-content")
                await editor.wait_for(state="visible", timeout=15000)
                
                print("[OVERLEAF] Reading current LaTeX source...")
                current_latex = await page.evaluate("""() => {
                    const el = document.querySelector('.cm-content');
                    if (el && el.cmView && el.cmView.view) {
                        return el.cmView.view.state.doc.toString();
                    }
                    return el ? el.innerText : '';
                }""")
                
                if not current_latex or current_latex.strip() == "":
                    current_latex = await editor.text_content()

                if not current_latex or current_latex.strip() == "":
                    raise RuntimeError("Failed to extract LaTeX source from Overleaf editor.")

                print(f"[OVERLEAF] Extracted LaTeX source code ({len(current_latex)} characters).")

                # Step 2: Tailor the LaTeX using Groq
                print("[OVERLEAF] Analyzing job description and tailoring resume via Groq...")
                llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=self.groq_api_key, temperature=0.2)
                
                profile_str = json.dumps(self.profile, indent=2)
                prompt = f"""
You are an expert LaTeX editor and elite technical resume tailorer.
Here is the current LaTeX source code of the user's resume:
```latex
{current_latex}
```

Here is the profile information of the user:
```json
{profile_str}
```

Here is the job description they are applying for:
```
{job_description}
```

Please tailor the resume to precisely match this job description:
1. Tailor the professional summary / objective section to align with the job description.
2. Tailor the skills section (reorder to highlight matching skills first, and add relevant matching ones from the job description and user profile).
3. Tailor the work experience bullet points to emphasize relevant achievements, systems integration keywords, and architectural components that match the requirements.
4. Maintain all other sections, layout, contact details, styling, and formatting EXACTLY as they are in the original LaTeX.
5. Ensure the resulting LaTeX code is 100% syntactically correct and will compile without any errors in Overleaf.

Return ONLY the complete modified LaTeX code. Do NOT wrap it in markdown code blocks, do NOT include any introductory or concluding text, and do not include explanation. Just start with \\documentclass or whatever the original code started with.
"""
                response = await llm.ainvoke(prompt)
                tailored_latex = response.content.strip()
                
                # Strip markdown blocks if the LLM output wrapped them
                if tailored_latex.startswith("```latex"):
                    tailored_latex = tailored_latex[8:]
                elif tailored_latex.startswith("```"):
                    tailored_latex = tailored_latex[3:]
                
                if tailored_latex.endswith("```"):
                    tailored_latex = tailored_latex[:-3]
                
                tailored_latex = tailored_latex.strip()

                print(f"[OVERLEAF] Tailored LaTeX generated successfully ({len(tailored_latex)} characters).")

                # Step 3: Write tailored LaTeX to Overleaf editor
                print("[OVERLEAF] Updating Overleaf editor content...")
                await editor.click()
                await page.keyboard.press("Control+A")
                await page.evaluate("text => document.execCommand('insertText', false, text)", tailored_latex)
                await asyncio.sleep(3)

                # Step 4: Recompile project
                print("[OVERLEAF] Recompiling project...")
                recompile_selectors = [
                    "button.btn-recompile",
                    "button:has-text('Recompile')",
                    ".btn-recompile",
                    ".recompile-button"
                ]
                
                recompiled = False
                for selector in recompile_selectors:
                    try:
                        btn = page.locator(selector)
                        if await btn.count() > 0 and await btn.first.is_visible():
                            await btn.first.click()
                            recompiled = True
                            break
                    except Exception:
                        continue

                if not recompiled:
                    # Fallback shortcut Ctrl+Enter
                    await page.keyboard.press("Control+Enter")
                    print("[OVERLEAF] Triggered compilation via keyboard shortcut Ctrl+Enter.")
                
                # Await compile to finish
                print("[OVERLEAF] Waiting 10 seconds for compilation to complete...")
                await asyncio.sleep(10)

                # Step 5: Download PDF
                print("[OVERLEAF] Finding download button...")
                download_selectors = [
                    "a.btn-download",
                    "a[data-original-title='Download PDF']",
                    "[aria-label='Download PDF']",
                    "button.download-pdf",
                    "a.pdf-viewer-download",
                    "button:has-text('Download')"
                ]
                
                download_btn = None
                for selector in download_selectors:
                    try:
                        btn = page.locator(selector)
                        if await btn.count() > 0 and await btn.first.is_visible():
                            download_btn = btn.first
                            break
                    except Exception:
                        continue

                if not download_btn:
                    # Let's save a screenshot to debug
                    debug_path = os.path.join(PROJECT_ROOT, "screenshots", "overleaf_compile_error.png")
                    os.makedirs(os.path.dirname(debug_path), exist_ok=True)
                    await page.screenshot(path=debug_path)
                    raise RuntimeError(f"Could not find the 'Download PDF' button. Screenshot saved at {debug_path}")

                print("[OVERLEAF] Clicked download. Saving file...")
                async with page.expect_download() as download_info:
                    await download_btn.click()
                download = await download_info.value
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                download_path = os.path.join(self.cookies_dir, f"resume_tailored_{timestamp}.pdf")
                await download.save_as(download_path)
                
                print(f"[OVERLEAF] Resume tailored and saved to: {download_path}")
                return download_path

            finally:
                try:
                    await self.browser.close()
                    await self.playwright.stop()
                except Exception:
                    pass
