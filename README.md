# J.A.R.V.I.S — Autonomous AI Agent

<div align="center">

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=chainlink&logoColor=white)](#)
[![Groq](https://img.shields.io/badge/Groq-F55A42?style=for-the-badge&logo=fastapi&logoColor=white)](#)
[![Gemini](https://img.shields.io/badge/Gemini-8E75C2?style=for-the-badge&logo=google-gemini&logoColor=white)](#)
[![Playwright](https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**A high-performance, futuristic autonomous AI assistant running locally on Windows. Equipped with an Iron Man-inspired HUD desktop interface, dynamic voice interaction, screen understanding, and automated agentic workflow execution.**

[Add your HUD screenshot here]

</div>

---

## 🤖 What it Does

J.A.R.V.I.S. is a fully autonomous virtual agent designed to run as a local background system on Windows with a stunning, interactive HUD interface. It accepts voice commands and text instructions to perform complex desktop automation, vision-based screen understanding, job search and application processes, and LaTeX resume tailoring.

Key capabilities include:
*   **🎙️ Hands-Free Voice Control**: Monitors system voice inputs for the `"JARVIS"` wake word, responds with audio cues, and processes full commands natively.
*   **🖥️ Screen Vision & Analysis**: Captures screenshots and understands the exact state of your screen using advanced multimodal Gemini models to guide operations or answer user queries.
*   **💼 Automated Job Applying**: Employs Playwright to search LinkedIn for specified target roles, locations, and qualifications, auto-filling "Easy Apply" job applications on your behalf.
*   **📄 LaTeX Resume Tailoring**: Automatically accesses specified Overleaf resume drafts, updates content in real-time to match target job descriptions, compiles, and downloads custom PDFs.
*   **📊 Immersive HUD Dashboard**: Features a gorgeous sci-fi GUI (FastAPI & WebSockets backend driving Chrome App Mode) displaying CPU, RAM, battery, uptime, action logs, and agent thought-processes.
*   **🐚 OS & Web Integration**: Capable of executing secure system commands on Windows, opening web pages, and generating LinkedIn social posts aligned with your professional profile.

---

## 🛠️ Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Core Runtime** | Python 3.10+ | Primary logic, execution loop, and custom libraries |
| **Agent Framework** | LangChain | Structured tool usage, AI system prompt engineering, memory state |
| **LLM Inference** | Groq (`llama-3.3-70b-versatile`) | Ultra-fast reasoning model for core decisions and orchestrating tools |
| **Multimodal Vision** | Google Gemini API | Screen image analysis and real-time environment understanding |
| **GUI Interface** | HTML5 / Vanilla CSS / WebSockets | Immersive Iron Man HUD interface running in Chrome App Mode |
| **Backend Web Server** | FastAPI & Uvicorn | Direct integration with HUD frontend, handling states and REST endpoints |
| **Automation Engine** | Playwright | Dynamic headful/headless web interaction for LinkedIn & Overleaf |
| **System Utilities** | `mss` & `psutil` | Real-time screenshot capture and hardware resource tracking |

---

## 🚀 Quick Start Installation Guide

Follow these steps to set up and run J.A.R.V.I.S. on your local machine:

### 1. Clone the Repository
```bash
git clone https://github.com/saiprudhvibojja-svg/Jarvis-Agent.git
cd Jarvis-Agent
```

### 2. Create and Activate a Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate on Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Activate on Windows (CMD)
.\venv\Scripts\activate.bat
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the template environment file and add your API keys:
```bash
cp .env.example .env
```
Open `.env` and fill in the values:
```env
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here
```

### 5. Start J.A.R.V.I.S.
Run the startup entrypoint. This spins up the FastAPI backend, activates the speech listeners, and launches the HUD interface directly in a Chrome application window:
```bash
python main.py
```

---

## ✨ Features Breakdown

*   **🗣️ Voice Wake-Word Detection**: Activates with acoustic alerts on recognizing `"JARVIS"`, answers vocally, and interprets commands immediately.
*   **🧠 Multi-Round Execution Loop**: Uses an up-to-8-round agent loop with tool outputs feeding back to the core brain recursively.
*   **🛠️ Desktop Control & Command Execution**: Secure execution of command-line tools to manipulate files, run local builds, and check system conditions.
*   **🎨 Live Profile Customization**: Customizes interactions based on a local `profile.json` detailing target titles, skills, and countries.
*   **📊 Hardware HUD**: Real-time diagnostic telemetry tracking CPU usage, RAM utilization, network status, battery level, and execution logs.

---

## 🤝 Contributing

Contributions to J.A.R.V.I.S. are always welcome! If you have ideas, bug fixes, or enhancements:

1. Fork the project.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

Please make sure to document any new skills, features, or environment variables in your PR.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
