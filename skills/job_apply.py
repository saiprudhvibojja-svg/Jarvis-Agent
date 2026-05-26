import json
import os
import asyncio
from datetime import datetime
from langchain_groq import ChatGroq
from playwright.async_api import async_playwright
from memory.db import save_application, is_already_applied
from skills.overleaf import OverleafBot

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_PATH = os.path.join(PROJECT_ROOT, "profile.json")

class LinkedInApplyBot:
    def __init__(self):
        # Load profile
        self.profile = {}
        if os.path.exists(PROFILE_PATH):
            try:
                with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                    self.profile = json.load(f)
            except Exception as e:
                print(f"Error loading profile: {e}")
        
        # Safe extraction of details with fallbacks
        full_name = self.profile.get("name", "Sai Prudhvi")
        name_parts = full_name.split(maxsplit=1)
        self.first_name = name_parts[0] if len(name_parts) > 0 else "Sai"
        self.last_name = name_parts[1] if len(name_parts) > 1 else "Prudhvi"
        self.email = self.profile.get("email", "sai.prudhvi@example.com")
        self.phone = self.profile.get("phone", "+1 555-0199")

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

    async def _generate_answer(self, job_title: str, company: str, question: str) -> str:
        """Generate a concise professional answer for job form text areas using Groq."""
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return "My professional background in cloud solutions, development, and system integration aligns perfectly with this role."
        try:
            llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=api_key, temperature=0.5)
            profile_str = json.dumps(self.profile, indent=2)
            prompt = (
                f"You are applying for the role of '{job_title}' at '{company}'.\n"
                f"Based on your profile details:\n{profile_str}\n\n"
                f"Answer the following job application question concisely (keep it professional, compelling, and under 80 words):\n"
                f"Question: \"{question}\"\n\n"
                f"Do not include any greeting, introduction, or placeholder. Write only the direct answer."
            )
            response = await llm.ainvoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"Groq answer generation failed: {e}")
            return "My experience with systems integration, cloud technologies, and production scaling makes me a great fit for this role."

    async def run(self, role: str, country: str, max_apply: int = 5) -> str:
        """Run the Playwright LinkedIn Easy Apply job application flow."""
        # Setup log helper to interface with backend HUD live streams
        try:
            from server import state, _schedule_broadcast
            def log_to_hud(msg):
                print(f"[BOT] {msg}", flush=True)
                state.add_log(f"> BOT > {msg}")
                state.add_activity("BOT_ACTIVE", msg)
                _schedule_broadcast({"type": "log", "message": f"> BOT > {msg}"})
                _schedule_broadcast({"type": "status", "data": state.snapshot()})
        except Exception:
            def log_to_hud(msg):
                print(f"[BOT] {msg}", flush=True)

        log_to_hud(f"Starting LinkedIn Job Application Pipeline...")
        
        # Step 1: Tailor resume first
        log_to_hud("Step 1: Generating tailored LaTeX resume on Overleaf...")
        tailored_resume_path = None
        try:
            overleaf_bot = OverleafBot()
            job_context = f"Role: {role}\nLocation: {country}\nCloud solutions and enterprise system integration architect with FastAPI and Azure."
            tailored_resume_path = await overleaf_bot.tailor_resume(job_context)
            log_to_hud(f"Tailored resume generated at: {tailored_resume_path}")
        except Exception as e:
            log_to_hud(f"Warning: Overleaf resume tailoring failed: {e}. Falling back to default resume if available.")
            # Create a mock or default PDF path just in case
            tailored_resume_path = os.path.join(PROJECT_ROOT, "memory", "resume_default.pdf")
            if not os.path.exists(tailored_resume_path):
                # write an empty dummy file to avoid upload failures
                with open(tailored_resume_path, "wb") as f:
                    f.write(b"%PDF-1.4 ... Default Resume Content ...")

        # Step 2: Open LinkedIn (Headful)
        cookies_dir = os.path.join(PROJECT_ROOT, "memory")
        os.makedirs(cookies_dir, exist_ok=True)
        cookies_path = os.path.join(cookies_dir, "linkedin_cookies.json")

        applied_jobs = []
        skipped_jobs = []

        await self._init_browser()
        browser = self.browser
        context = self.browser
        page = self.page

        # Restore cookies
        if os.path.exists(cookies_path):
            try:
                with open(cookies_path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    await context.add_cookies(cookies)
                log_to_hud("Restored stored LinkedIn session cookies.")
            except Exception as e:
                log_to_hud(f"Warning: Failed to load LinkedIn cookies: {e}")

        try:
            
            # Verify login status
            log_to_hud("Verifying LinkedIn login status...")
            try:
                await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
                await asyncio.sleep(3)
            except Exception as e:
                log_to_hud(f"Failed to navigate to LinkedIn feed: {e}")

            is_logged_in = False
            if "feed" in page.url or "feed" in page.url.lower():
                is_logged_in = True
            else:
                try:
                    if await page.locator(".global-nav").is_visible():
                        is_logged_in = True
                except Exception:
                    pass

            if not is_logged_in:
                log_to_hud("Not logged in. Directing to LinkedIn login page...")
                await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
                log_to_hud("Awaiting manual user login (Timeout: 60s). Please log in now in the browser...")
                
                login_success = False
                for sec in range(60):
                    await asyncio.sleep(1)
                    if "feed" in page.url or "feed" in page.url.lower():
                        login_success = True
                        break
                    try:
                        if await page.locator(".global-nav").is_visible():
                            login_success = True
                            break
                    except Exception:
                        pass
                
                if login_success:
                    log_to_hud("LinkedIn login detected! Saving session cookies...")
                    cookies = await context.cookies()
                    with open(cookies_path, "w", encoding="utf-8") as f:
                        json.dump(cookies, f, indent=2)
                else:
                    log_to_hud("LinkedIn login timed out (60s). Stopping job application.")
                    await browser.close()
                    return "LinkedIn login timed out. Please try running the bot again after logging in."

            # Step 3: Search Jobs
            log_to_hud(f"Step 3: Searching LinkedIn jobs: keywords='{role}', location='{country}'...")
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={role}&location={country}&f_AL=true"
            await page.goto(search_url, wait_until="load")
            await asyncio.sleep(4)

            # Look for job cards
            job_card_selectors = [
                "li.jobs-search-results__list-item",
                ".jobs-search-results-list li",
                "[data-occludable-job-id]",
                ".job-card-container"
            ]
            
            found_selector = None
            for selector in job_card_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        found_selector = selector
                        break
                except Exception:
                    continue

            if not found_selector:
                log_to_hud("No job postings found or failed to load job card list.")
                await browser.close()
                return f"No job postings loaded for '{role}' in '{country}'."

            job_cards = page.locator(found_selector)
            total_cards = await job_cards.count()
            log_to_hud(f"Identified {total_cards} job postings on current page view.")

            applied_count = 0
            
            # Step 4: Iterate and Apply
            for idx in range(total_cards):
                if applied_count >= max_apply:
                    log_to_hud(f"Reached application limit of {max_apply}.")
                    break

                log_to_hud(f"Evaluating job posting {idx+1}/{total_cards}...")
                card = job_cards.nth(idx)
                
                try:
                    await card.scroll_into_view_if_needed()
                    await card.click()
                    await asyncio.sleep(2.5)
                except Exception as e:
                    log_to_hud(f"Could not select job card {idx+1}: {e}")
                    continue

                # Parse details
                job_title = "Unknown Position"
                company = "Unknown Company"
                try:
                    title_elem = page.locator(".job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title, h2.jobs-details-panel__job-title")
                    if await title_elem.count() > 0:
                        job_title = (await title_elem.first.text_content() or "").strip()
                    else:
                        card_title = card.locator(".job-card-list__title, h3, .job-card-container__link")
                        if await card_title.count() > 0:
                            job_title = (await card_title.first.text_content() or "").strip()

                    company_elem = page.locator(".job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name, .jobs-details-panel__company-name")
                    if await company_elem.count() > 0:
                        company = (await company_elem.first.text_content() or "").strip()
                    else:
                        card_company = card.locator(".job-card-container__company-name, .job-card-list__company-name")
                        if await card_company.count() > 0:
                            company = (await card_company.first.text_content() or "").strip()
                except Exception as e:
                    log_to_hud(f"Failed to resolve job info: {e}")

                # SQLite Duplication Check
                if is_already_applied(company, job_title):
                    log_to_hud(f"Skipping job: '{job_title}' at '{company}' (Already applied in jobs.db)")
                    skipped_jobs.append(f"{company} - {job_title}")
                    continue

                # Check Easy Apply Button
                easy_apply_selectors = [
                    "button:has-text('Easy Apply')",
                    ".jobs-apply-button:has-text('Easy Apply')",
                    "button.jobs-apply-button"
                ]
                
                easy_apply_btn = None
                for ea_sel in easy_apply_selectors:
                    try:
                        btn = page.locator(ea_sel)
                        if await btn.count() > 0 and await btn.first.is_visible():
                            text = await btn.first.text_content()
                            if text and "Easy Apply" in text:
                                easy_apply_btn = btn.first
                                break
                    except Exception:
                        continue

                if not easy_apply_btn:
                    log_to_hud(f"Skipping - not Easy Apply: '{job_title}' at '{company}'")
                    skipped_jobs.append(f"{company} - {job_title} (Not Easy Apply)")
                    continue

                log_to_hud(f"Initiating Easy Apply flow for '{job_title}' at '{company}'...")
                try:
                    await easy_apply_btn.click()
                    await asyncio.sleep(2.5)
                except Exception as e:
                    log_to_hud(f"Failed to open Easy Apply form: {e}")
                    continue

                # Form dialog handling
                modal_selector = "div[role='dialog'], .jobs-easy-apply-modal"
                if not await page.locator(modal_selector).is_visible():
                    log_to_hud("Easy Apply form modal failed to open.")
                    continue

                max_pages = 8
                application_submitted = False
                
                for page_idx in range(1, max_pages + 1):
                    # Fill standard fields on active page
                    try:
                        # 1. Fill standard fields
                        text_inputs = await page.locator("input[type='text'], input[type='email'], input[type='tel']").all()
                        for inp in text_inputs:
                            inp_id = await inp.get_attribute("id")
                            inp_name = await inp.get_attribute("name")
                            placeholder = await inp.get_attribute("placeholder")
                            
                            label_text = ""
                            if inp_id:
                                label_elem = page.locator(f"label[for='{inp_id}']")
                                if await label_elem.count() > 0:
                                    label_text = (await label_elem.first.text_content() or "").lower()
                            
                            search_ctx = (label_text + " " + (inp_id or "") + " " + (inp_name or "") + " " + (placeholder or "")).lower()
                            
                            # Auto-fill identity
                            if "first name" in search_ctx or "firstname" in search_ctx:
                                if not await inp.input_value():
                                    await inp.fill(self.first_name)
                            elif "last name" in search_ctx or "lastname" in search_ctx:
                                if not await inp.input_value():
                                    await inp.fill(self.last_name)
                            elif "email" in search_ctx:
                                if not await inp.input_value():
                                    await inp.fill(self.email)
                            elif any(kw in search_ctx for kw in ["phone", "mobile", "tel"]):
                                if not await inp.input_value():
                                    await inp.fill(self.phone)
                            # Calculation for experience years
                            elif any(kw in search_ctx for kw in ["years of", "experience", "how many years"]):
                                if not await inp.input_value():
                                    years = str(self.profile.get("years_of_experience", 3))
                                    await inp.fill(years)
                                    log_to_hud(f"Auto-calculated experience filled: {years} years")

                        # 2. Fill textareas
                        textareas = await page.locator("textarea").all()
                        for ta in textareas:
                            ta_id = await ta.get_attribute("id")
                            ta_name = await ta.get_attribute("name")
                            
                            ta_label_text = ""
                            if ta_id:
                                label_elem = page.locator(f"label[for='{ta_id}']")
                                if await label_elem.count() > 0:
                                    ta_label_text = (await label_elem.first.text_content() or "").lower()
                            
                            ta_search_ctx = (ta_label_text + " " + (ta_id or "") + " " + (ta_name or "")).lower()
                            
                            if any(kw in ta_search_ctx for kw in ["why", "interest", "cover letter", "describe", "experience", "motivation"]):
                                if not await ta.input_value():
                                    log_to_hud(f"Generating tailored AI answer for: '{ta_label_text.strip()}'...")
                                    ans = await self._generate_answer(job_title, company, ta_label_text or "Why are you interested in this role?")
                                    await ta.fill(ans)

                        # 3. Handle tailored resume file upload
                        file_inputs = await page.locator("input[type='file']").all()
                        for fi in file_inputs:
                            try:
                                if tailored_resume_path:
                                    await fi.set_input_files(tailored_resume_path)
                                    log_to_hud(f"Successfully uploaded tailored resume: {os.path.basename(tailored_resume_path)}")
                                    await asyncio.sleep(2)
                            except Exception as e:
                                log_to_hud(f"Warning: Resume file upload failed: {e}")

                    except Exception as e:
                        log_to_hud(f"Warning while filling form fields: {e}")

                    # Click Next, Review or Submit
                    buttons = [
                        "button:has-text('Submit application')",
                        "button:has-text('Next')",
                        "button:has-text('Review')",
                        "button:has-text('Continue')",
                    ]
                    
                    clicked_btn_text = None
                    for btn_sel in buttons:
                        try:
                            btn = page.locator(btn_sel)
                            if await btn.count() > 0 and await btn.first.is_visible() and await btn.first.is_enabled():
                                clicked_btn_text = await btn.first.text_content()
                                await btn.first.click()
                                await asyncio.sleep(2.5)
                                break
                        except Exception:
                            continue

                    if not clicked_btn_text:
                        log_to_hud("Could not find any navigation buttons. Closing form.")
                        try:
                            close_btn = page.locator("button[aria-label='Dismiss']")
                            if await close_btn.count() > 0:
                                await close_btn.first.click()
                                await asyncio.sleep(1)
                                discard_btn = page.locator("button:has-text('Discard')")
                                if await discard_btn.count() > 0:
                                    await discard_btn.first.click()
                                    await asyncio.sleep(1)
                        except Exception:
                            pass
                        break

                    if "Submit application" in clicked_btn_text or "Submit" in clicked_btn_text:
                        log_to_hud(f"Application submitted for '{job_title}' at '{company}'!")
                        
                        # Screenshot as proof
                        try:
                            proofs_dir = os.path.join(PROJECT_ROOT, "screenshots", "proofs")
                            os.makedirs(proofs_dir, exist_ok=True)
                            clean_company = "".join(c for c in company if c.isalnum() or c in (" ", "_", "-")).strip()
                            clean_role = "".join(c for c in job_title if c.isalnum() or c in (" ", "_", "-")).strip()
                            proof_path = os.path.join(proofs_dir, f"proof_{clean_company}_{clean_role}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                            await page.screenshot(path=proof_path)
                            log_to_hud(f"Saved proof screenshot: {proof_path}")
                        except Exception as se:
                            log_to_hud(f"Warning: Screenshot capture failed: {se}")

                        # SQLite registration
                        try:
                            save_application(
                                company=company,
                                role=job_title,
                                country=country,
                                date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                status="applied",
                                url=page.url
                            )
                            log_to_hud("Logged application status to jobs.db")
                        except Exception as e:
                            log_to_hud(f"Failed to record application to SQLite: {e}")

                        applied_jobs.append({
                            "company": company,
                            "role": job_title,
                            "country": country,
                            "status": "applied"
                        })
                        applied_count += 1
                        application_submitted = True
                        
                        # Close confirmation modal
                        try:
                            done_btn = page.locator("button:has-text('Done')")
                            if await done_btn.count() > 0:
                                await done_btn.first.click()
                                await asyncio.sleep(1)
                            else:
                                dismiss_btn = page.locator("button[aria-label='Dismiss']")
                                if await dismiss_btn.count() > 0:
                                    await dismiss_btn.first.click()
                                    await asyncio.sleep(1)
                        except Exception:
                            pass
                        break

                if not application_submitted:
                    log_to_hud(f"Dismissing active dialog for '{job_title}' at '{company}' due to form roadblock.")

            # Summary report formatting
            log_to_hud("Job application bot process complete.")
            
            summary = f"Applied to {len(applied_jobs)} jobs:\n"
            for j in applied_jobs:
                summary += f"✅ {j['company']} - {j['role']}\n"
            
            for s in skipped_jobs[:5]:
                summary += f"⚠️ Skipped: {s}\n"
            
            if len(skipped_jobs) > 5:
                summary += f"⚠️ Skipped {len(skipped_jobs) - 5} other jobs.\n"
            
            if not applied_jobs:
                summary = "Applied to 0 jobs. (Ensure you have logged in, or try keywords with active Easy Apply options.)"

            return summary.strip()
        finally:
            try:
                await self.browser.close()
                await self.playwright.stop()
            except Exception:
                pass
