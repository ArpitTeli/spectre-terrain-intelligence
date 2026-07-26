const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let pythonProcess = null;
let pipelineRunning = false;

// Get Python path
function getPythonPath() {
  // Check for bundled Python first
  const bundledPython = path.join(process.resourcesPath, 'python', 'python.exe');
  if (fs.existsSync(bundledPython)) {
    return bundledPython;
  }
  // Fall back to system Python
  return 'python';
}

// Get backend path
function getBackendPath() {
  // Check for bundled backend first
  const bundledBackend = path.join(process.resourcesPath, 'backend');
  if (fs.existsSync(bundledBackend)) {
    return bundledBackend;
  }
  // Fall back to local backend
  return path.join(__dirname, '..', 'backend');
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    titleBarStyle: 'hidden',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    backgroundColor: '#0a0a0a'
  });

  // Load React app
  const isDev = process.env.ELECTRON_DEV === 'true';
  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'build', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
    killPythonProcess();
  });
}

// Python process management
function startPythonProcess() {
  if (pythonProcess) {
    return;
  }

  const pythonPath = getPythonPath();
  const backendPath = getBackendPath();
  const runnerScript = path.join(backendPath, 'pipeline_runner.py');

  pythonProcess = spawn(pythonPath, [runnerScript], {
    cwd: backendPath,
    stdio: ['pipe', 'pipe', 'pipe']
  });

  pythonProcess.stdout.on('data', (data) => {
    const lines = data.toString().split('\n').filter(l => l.trim());
    for (const line of lines) {
      try {
        const msg = JSON.parse(line);
        if (mainWindow) {
          mainWindow.webContents.send('pipeline-message', msg);
        }
      } catch (e) {
        // Plain text log
        if (mainWindow) {
          mainWindow.webContents.send('pipeline-log', line);
        }
      }
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    const msg = data.toString().trim();
    if (msg && mainWindow) {
      mainWindow.webContents.send('pipeline-log', msg);
    }
  });

  pythonProcess.on('close', (code) => {
    pythonProcess = null;
    pipelineRunning = false;
    if (mainWindow) {
      mainWindow.webContents.send('pipeline-stopped', { code });
    }
  });

  pythonProcess.on('error', (err) => {
    console.error('Python process error:', err);
    pythonProcess = null;
    pipelineRunning = false;
    if (mainWindow) {
      mainWindow.webContents.send('pipeline-error', { error: err.message });
    }
  });
}

function killPythonProcess() {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
    pipelineRunning = false;
  }
}

function sendToPython(command) {
  if (!pythonProcess) {
    startPythonProcess();
  }
  pythonProcess.stdin.write(JSON.stringify(command) + '\n');
}

// IPC Handlers
ipcMain.handle('minimize-window', () => mainWindow?.minimize());
ipcMain.handle('maximize-window', () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});
ipcMain.handle('close-window', () => mainWindow?.close());

ipcMain.handle('start-pipeline', (event, config) => {
  if (pipelineRunning) {
    return { error: 'Pipeline already running' };
  }
  pipelineRunning = true;
  startPythonProcess();
  sendToPython({ command: 'start', config });
  return { success: true };
});

ipcMain.handle('run-stage', (event, { stage, count }) => {
  sendToPython({ command: 'run_stage', stage, count });
  return { success: true };
});

ipcMain.handle('get-status', () => {
  sendToPython({ command: 'status' });
  return { success: true };
});

ipcMain.handle('stop-pipeline', () => {
  killPythonProcess();
  return { success: true };
});

ipcMain.handle('get-config', () => {
  const configPath = path.join(getBackendPath(), '.env');
  if (fs.existsSync(configPath)) {
    return fs.readFileSync(configPath, 'utf8');
  }
  return '';
});

ipcMain.handle('save-config', (event, config) => {
  const configPath = path.join(getBackendPath(), '.env');
  fs.writeFileSync(configPath, config);
  return { success: true };
});

ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  return result.canceled ? null : result.filePaths[0];
});

// App lifecycle
app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  killPythonProcess();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  killPythonProcess();
});
