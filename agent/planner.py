import os
import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage


def plan_task(task: str) -> list[str]:
    """
    Deconstructs a complex request into a list of simplified sequential steps.
    Uses ChatGroq with llama-3.3-70b-versatile to generate the steps.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[Planner] Warning: GROQ_API_KEY is not set. Falling back to default plan.")
        return [f"Execute user task: '{task}'"]

    try:
        model = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.1,
            api_key=api_key
        )
        
        system_prompt = (
            "You are the planner module of J.A.R.V.I.S., a sophisticated AI. "
            "Your job is to take a user's complex instruction and deconstruct it into a list of "
            "clear, sequential, and logical execution steps.\n\n"
            "Format your output ONLY as a raw JSON list of strings, with no markdown tags, "
            "no backticks (do NOT wrap in ```json or ```), and no extra text. "
            "Example output: [\"Step 1 description\", \"Step 2 description\"]"
        )
        
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=task)
        ])
        
        content = response.content.strip()
        # Clean potential markdown block formatting
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        steps = json.loads(content)
        if isinstance(steps, list):
            return [str(step) for step in steps if step]
    except Exception as e:
        print(f"[Planner] Error during LLM planning: {e}. Falling back to default plan.")

    # Fallback if planning fails
    return [
        f"Analyze the request: '{task}'",
        "Select and execute the most appropriate system tools",
        "Formulate a helpful final response for the creator"
    ]
