import os
import json
import asyncio
from playwright.async_api import async_playwright

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class LinkedInProfileBot:
    def __init__(self):
        self.profile = {}
        profile_path = os.path.join(PROJECT_ROOT, "profile.json")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    self.profile = json.load(f)
            except Exception as e:
                print(f"[LINKEDIN_PROFILE] Error loading profile: {e}")

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

    async def update_profile(self) -> str:
        """Navigates to LinkedIn profile settings and verifies status."""
        await self._init_browser()
        page = self.page
        context = self.browser
        
        try:
            print("[LINKEDIN_PROFILE] Verifying login and accessing profile settings...")
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            if "login" in page.url or not ("feed" in page.url):
                print("[LINKEDIN_PROFILE] Manual login fallback triggered...")
                await page.goto("https://www.linkedin.com/login")
                # Wait up to 60s for manual login
                for _ in range(60):
                    await asyncio.sleep(1)
                    if "feed" in page.url:
                        break
            
            # Navigate to profile URL
            await page.goto("https://www.linkedin.com/in/", wait_until="domcontentloaded")
            await asyncio.sleep(3)
            return "LinkedIn profile page loaded successfully."
        finally:
            try:
                await self.browser.close()
                await self.playwright.stop()
            except Exception:
                pass
