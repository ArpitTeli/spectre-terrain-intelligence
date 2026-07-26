const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pipelineAPI', {
  // Window controls
  minimize: () => ipcRenderer.invoke('minimize-window'),
  maximize: () => ipcRenderer.invoke('maximize-window'),
  close: () => ipcRenderer.invoke('close-window'),

  // Pipeline controls
  startPipeline: (config) => ipcRenderer.invoke('start-pipeline', config),
  runStage: (stage, count) => ipcRenderer.invoke('run-stage', { stage, count }),
  getStatus: () => ipcRenderer.invoke('get-status'),
  stopPipeline: () => ipcRenderer.invoke('stop-pipeline'),

  // Config
  getConfig: () => ipcRenderer.invoke('get-config'),
  saveConfig: (config) => ipcRenderer.invoke('save-config', config),

  // Directory selection
  selectDirectory: () => ipcRenderer.invoke('select-directory'),

  // Event listeners
  onLog: (callback) => ipcRenderer.on('pipeline-log', (event, data) => callback(data)),
  onMessage: (callback) => ipcRenderer.on('pipeline-message', (event, data) => callback(data)),
  onStopped: (callback) => ipcRenderer.on('pipeline-stopped', (event, data) => callback(data)),
  onError: (callback) => ipcRenderer.on('pipeline-error', (event, data) => callback(data)),

  // Remove listeners
  removeAllListeners: () => {
    ipcRenderer.removeAllListeners('pipeline-log');
    ipcRenderer.removeAllListeners('pipeline-message');
    ipcRenderer.removeAllListeners('pipeline-stopped');
    ipcRenderer.removeAllListeners('pipeline-error');
  }
});
