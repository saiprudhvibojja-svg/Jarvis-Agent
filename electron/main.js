const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const PROJECT_ROOT = path.join(__dirname, "..");
const JARVIS_ROOT = "C:\\Jarvis-agent";

let mainWindow = null;
let pythonProcess = null;
let weStartedPython = false;

function isServerUp() {
  return new Promise((resolve) => {
    const req = http.get("http://127.0.0.1:8000/status", (res) => {
      resolve(res.statusCode === 200);
      res.resume();
    });
    req.on("error", () => resolve(false));
    req.setTimeout(800, () => {
      req.destroy();
      resolve(false);
    });
  });
}

function startPythonBackend() {
  const cmd = `cd /d ${JARVIS_ROOT} && venv\\Scripts\\python.exe main_server.py`;

  pythonProcess = spawn("cmd", ["/c", cmd], {
    cwd: JARVIS_ROOT,
    windowsHide: true,
    stdio: "inherit",
  });

  weStartedPython = true;

  pythonProcess.on("error", (err) => {
    console.error("[JARVIS] Failed to start Python backend:", err);
  });

  pythonProcess.on("exit", (code) => {
    console.log("[JARVIS] Python backend exited with code", code);
    pythonProcess = null;
    weStartedPython = false;
  });
}

function killPythonBackend() {
  if (!weStartedPython || !pythonProcess) return;
  try {
    spawn("taskkill", ["/pid", String(pythonProcess.pid), "/f", "/t"], {
      windowsHide: true,
    });
  } catch (e) {
    console.error("[JARVIS] Error stopping Python:", e);
  }
  pythonProcess = null;
  weStartedPython = false;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    frame: false,
    transparent: false,
    backgroundColor: "#000000",
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.loadURL("http://localhost:8000");

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  const alreadyRunning = await isServerUp();
  if (!alreadyRunning) {
    startPythonBackend();
  } else {
    console.log("[JARVIS] Backend already running (started by start.bat)");
  }

  setTimeout(() => {
    createWindow();
  }, 2000);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

ipcMain.on("window-minimize", () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on("window-close", () => {
  if (mainWindow) mainWindow.close();
});

app.on("window-all-closed", () => {
  killPythonBackend();
  app.quit();
});

app.on("before-quit", () => {
  killPythonBackend();
});
