import os
import tempfile
import mss
from PIL import Image
import google.generativeai as genai

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

def capture_screenshot() -> str:
    """Capture full primary screen and return the temporary file path."""
    with mss.mss() as sct:
        # Get primary monitor (index 1 is primary monitor, index 0 is all monitors)
        monitor = sct.monitors[1]
        img = sct.grab(monitor)
        
        # Save to a temporary file
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "jarvis_temp_screen.png")
        mss.tools.to_png(img.rgb, img.size, output=temp_path)
        return temp_path

def understand_screen(question: str = "what is on the screen?") -> str:
    """
    Captures a screenshot of the primary display, sends it to Gemini 1.5 Flash 
    with the given question, and returns the descriptive text.
    """
    temp_path = capture_screenshot()
    
    try:
        pil_img = Image.open(temp_path)
        response = model.generate_content([question, pil_img])
        return response.text.strip()
    except Exception as e:
        return f"Error understanding screen via Gemini Vision API: {e}"
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

def find_element_on_screen(element: str = "Easy Apply button") -> str:
    """
    Captures a screenshot and queries Gemini 1.5 Flash to locate a specific element 
    and provide its screen coordinates.
    """
    question = f"Where is the {element}? Give pixel coordinates"
    return understand_screen(question)
