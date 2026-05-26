import json
import os
import subprocess
import webbrowser
from datetime import datetime
from urllib.parse import quote_plus

from langchain_core.tools import tool

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROFILE_PATH = os.path.join(PROJECT_ROOT, "profile.json")
SCREENSHOT_DIR = os.path.join(PROJECT_ROOT, "screenshots")


def load_profile_safe() -> dict:
    """Safely load profile.json, initializing with default contents if empty or invalid."""
    default_profile = {
        "name": "Tony Stark",
        "title": "Cloud Solutions & Systems Integration Architect",
        "skills": {
            "cloud": ["Azure", "AWS", "GCP", "Kubernetes", "Python", "FastAPI"]
        }
    }
    if not os.path.exists(PROFILE_PATH) or os.path.getsize(PROFILE_PATH) == 0:
        try:
            with open(PROFILE_PATH, "w", encoding="utf-8") as f:
                json.dump(default_profile, f, indent=2)
            return default_profile
        except Exception:
            return default_profile
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return default_profile
            return data
    except Exception:
        return default_profile


@tool
def search_jobs(role: str, country: str) -> str:
    """Search LinkedIn jobs for a role in a country and open results in the browser."""
    keywords = quote_plus(f"{role} {country}")
    url = (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={keywords}&location={quote_plus(country)}"
    )
    webbrowser.open(url)
    return f"Opened LinkedIn job search for '{role}' in {country}: {url}"


@tool
def open_website(url: str) -> str:
    """Open a URL in the default web browser."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"


@tool
def run_system_command(command: str) -> str:
    """Run a shell command on Windows and return stdout/stderr."""
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=PROJECT_ROOT,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if not output.strip():
        output = f"Command finished with exit code {result.returncode}"
    return output.strip()[:4000]


@tool
def get_my_profile() -> str:
    """Read and return the user's profile.json."""
    profile = load_profile_safe()
    return json.dumps(profile, indent=2)


@tool
def write_linkedin_post(topic: str) -> str:
    """Generate LinkedIn post content for a topic using profile context."""
    profile = load_profile_safe()
    name = profile.get("name", "I")
    title = profile.get("title", "professional")
    skills = profile.get("skills", {}).get("cloud", [])[:4]
    skill_text = ", ".join(skills) if skills else "cloud integration"
    post = (
        f"🚀 {topic}\n\n"
        f"Excited to share thoughts on {topic} as an {title}. "
        f"My recent work spans {skill_text}.\n\n"
        f"Key takeaways:\n"
        f"• Practical patterns that scale in production\n"
        f"• Lessons from real integration projects\n"
        f"• What teams should prioritize next\n\n"
        f"What’s your experience with {topic}? "
        f"#Azure #Integration #Tech\n\n"
        f"— {name}"
    )
    return post


@tool
def take_screenshot() -> str:
    """Capture the primary screen and save a PNG screenshot."""
    import mss

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SCREENSHOT_DIR, f"screen_{timestamp}.png")
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = sct.grab(monitor)
        mss.tools.to_png(img.rgb, img.size, output=path)
    return f"Screenshot saved: {path}"


@tool
def apply_jobs(role: str, country: str) -> str:
    """Apply to jobs on LinkedIn using Easy Apply"""
    import asyncio
    from skills.job_apply import LinkedInApplyBot
    bot = LinkedInApplyBot()
    result = asyncio.run(bot.run(role, country))
    return result


@tool
def look_at_screen(question: str) -> str:
    """Look at the current screen and answer a question about it"""
    from vision.screen_agent import understand_screen
    return understand_screen(question)


@tool
def tailor_resume_for_job(job_description: str) -> str:
    """Tailor the LaTeX resume on Overleaf for a specific job description and download PDF"""
    import asyncio
    from skills.overleaf import OverleafBot
    bot = OverleafBot()
    result = asyncio.run(bot.tailor_resume(job_description))
    return result


ALL_TOOLS = [
    search_jobs,
    open_website,
    run_system_command,
    get_my_profile,
    write_linkedin_post,
    take_screenshot,
    apply_jobs,
    look_at_screen,
    tailor_resume_for_job,
]

TOOL_MAP = {t.name: t for t in ALL_TOOLS}

