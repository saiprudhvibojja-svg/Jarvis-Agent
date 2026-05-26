import os
import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from agent.tools import ALL_TOOLS, TOOL_MAP, load_profile_safe


SYSTEM_PROMPT = """
You are JARVIS, an AI assistant running on Windows.
You can use tools BUT only when the user explicitly asks.

IMPORTANT RULES:
1. For greetings ("hello", "hi", "hey") → just respond warmly, NO tools
2. For questions about yourself → explain your capabilities, NO tools  
3. For "search jobs" → use search_jobs tool
4. For "apply jobs" → use apply_jobs tool (ask for confirmation first)
5. For "look at screen" → use look_at_screen tool
6. For "open X" → use open_website tool
7. NEVER open LinkedIn or Overleaf unless explicitly told to
8. ALWAYS respond with text first, then use tools if needed
9. Keep responses concise - max 3 sentences

User profile: Sai Prudhvi, Integration Architect, 3 years experience
Skills: Azure, Python, FastAPI, Dynamics 365 BC
Target countries: Canada, Germany, Netherlands, UK, Australia
"""


def run_agent(task: str, log_callback) -> str:
    """
    Executes the J.A.R.V.I.S. agent loop.
    Binds the tools and executes an up to 8-round loop using llama-3.3-70b-versatile.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        err_msg = "GROQ_API_KEY environment variable is missing. Please set it in your .env file."
        log_callback(err_msg)
        return err_msg

    system_prompt = SYSTEM_PROMPT

    log_callback("Initializing ChatGroq llama-3.3-70b-versatile...")
    
    # Initialize ChatGroq LLM
    model = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        api_key=api_key
    )

    # Bind the tools
    model_with_tools = model.bind_tools(ALL_TOOLS)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=task)
    ]

    log_callback(f"Starting execution loop for task: '{task}'")

    for round_idx in range(1, 9):
        log_callback(f"Execution Round {round_idx}/8: Consulting J.A.R.V.I.S. core model...")
        
        try:
            response = model_with_tools.invoke(messages)
        except Exception as e:
            err_msg = f"LLM invocation failed: {e}"
            log_callback(err_msg)
            return f"I encountered an error consulting my core brain: {e}"

        messages.append(response)

        # Check if there are tool calls
        if not response.tool_calls:
            log_callback("J.A.R.V.I.S. finished executing the task.")
            return response.content

        # Handle all tool calls requested by the model in this round
        for tool_call in response.tool_calls:
            t_name = tool_call["name"]
            t_args = tool_call["args"]
            t_id = tool_call["id"]

            log_callback(f"J.A.R.V.I.S. requested tool: '{t_name}' with args: {json.dumps(t_args)}")

            if t_name in TOOL_MAP:
                try:
                    tool_result = TOOL_MAP[t_name].invoke(t_args)
                except Exception as e:
                    tool_result = f"Error executing tool '{t_name}': {e}"
            else:
                tool_result = f"Error: Tool '{t_name}' is not registered."

            log_callback(f"Tool '{t_name}' returned: {tool_result}")

            # Append the tool result back as a ToolMessage
            tool_msg = ToolMessage(content=str(tool_result), tool_call_id=t_id)
            messages.append(tool_msg)

    log_callback("Reached maximum loop execution depth of 8 rounds.")
    return "I have completed all possible execution rounds but could not reach a final conclusion."
