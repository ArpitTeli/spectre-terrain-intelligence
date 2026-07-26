import React, { useState, useEffect, useCallback } from 'react';
import TitleBar from './components/TitleBar';
import Dashboard from './components/Dashboard';
import ConfigPanel from './components/ConfigPanel';
import StageRunner from './components/StageRunner';
import LogConsole from './components/LogConsole';

const API = window.pipelineAPI;

function App() {
  const [status, setStatus] = useState({
    total: 0,
    sampled: 0,
    teacher_done: 0,
    geo_passed: 0,
    judged: 0,
    accepted: 0,
    rejected: 0,
    flagged: 0
  });
  const [config, setConfig] = useState({
    openrouterApiKey: '',
    teacherModel: 'anthropic/claude-3.5-sonnet',
    judgeAModel: 'anthropic/claude-3.5-haiku',
    judgeBModel: 'openai/gpt-4o-mini',
    targetExamples: 1000,
    mapName: 'stratis'
  });
  const [logs, setLogs] = useState([]);
  const [running, setRunning] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard');

  // Load config on mount
  useEffect(() => {
    loadConfig();
    getStatus();
  }, []);

  // Listen for pipeline messages
  useEffect(() => {
    if (!API) return;

    const handleLog = (msg) => {
      setLogs(prev => [...prev.slice(-500), { type: 'log', text: msg, time: Date.now() }]);
    };

    const handleMessage = (msg) => {
      if (msg.type === 'status') {
        setStatus(msg.data);
      } else if (msg.type === 'stage_complete') {
        getStatus();
      } else if (msg.type === 'log') {
        setLogs(prev => [...prev.slice(-500), { type: 'info', text: msg.text, time: Date.now() }]);
      }
    };

    const handleStopped = () => {
      setRunning(false);
      setLogs(prev => [...prev.slice(-500), { type: 'warn', text: 'Pipeline stopped', time: Date.now() }]);
    };

    const handleError = (err) => {
      setLogs(prev => [...prev.slice(-500), { type: 'error', text: err.error, time: Date.now() }]);
    };

    API.onLog(handleLog);
    API.onMessage(handleMessage);
    API.onStopped(handleStopped);
    API.onError(handleError);

    return () => {
      API.removeAllListeners();
    };
  }, []);

  const loadConfig = async () => {
    if (!API) return;
    const envContent = await API.getConfig();
    if (envContent) {
      const parsed = {};
      envContent.split('\n').forEach(line => {
        const [key, ...valueParts] = line.split('=');
        if (key && valueParts.length) {
          parsed[key.trim()] = valueParts.join('=').trim();
        }
      });
      setConfig(prev => ({
        ...prev,
        openrouterApiKey: parsed.OPENROUTER_API_KEY || '',
        teacherModel: parsed.TEACHER_MODEL || prev.teacherModel,
        judgeAModel: parsed.JUDGE_A_MODEL || prev.judgeAModel,
        judgeBModel: parsed.JUDGE_B_MODEL || prev.judgeBModel,
        targetExamples: parseInt(parsed.TARGET_EXAMPLES) || prev.targetExamples,
        mapName: parsed.MAP_NAME || prev.mapName
      }));
    }
  };

  const saveConfig = async () => {
    if (!API) return;
    const envContent = [
      `OPENROUTER_API_KEY=${config.openrouterApiKey}`,
      `TEACHER_MODEL=${config.teacherModel}`,
      `JUDGE_A_MODEL=${config.judgeAModel}`,
      `JUDGE_B_MODEL=${config.judgeBModel}`,
      `TARGET_EXAMPLES=${config.targetExamples}`,
      `MAP_NAME=${config.mapName}`
    ].join('\n');
    await API.saveConfig(envContent);
    setLogs(prev => [...prev.slice(-500), { type: 'success', text: 'Configuration saved', time: Date.now() }]);
  };

  const getStatus = async () => {
    if (!API) return;
    await API.getStatus();
  };

  const startPipeline = async () => {
    if (!API) return;
    if (!config.openrouterApiKey) {
      setLogs(prev => [...prev.slice(-500), { type: 'error', text: 'OpenRouter API key not set', time: Date.now() }]);
      return;
    }
    setRunning(true);
    await API.startPipeline(config);
    setLogs(prev => [...prev.slice(-500), { type: 'info', text: 'Pipeline started', time: Date.now() }]);
  };

  const stopPipeline = async () => {
    if (!API) return;
    await API.stopPipeline();
    setRunning(false);
  };

  const runStage = async (stage) => {
    if (!API) return;
    await API.runStage(stage, 10);
    setLogs(prev => [...prev.slice(-500), { type: 'info', text: `Running stage: ${stage}`, time: Date.now() }]);
  };

  return (
    <div className="app">
      <TitleBar />
      <div className="app__content">
        <div className="app__sidebar">
          <div className="sidebar__tabs">
            <button
              className={`sidebar__tab ${activeTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => setActiveTab('dashboard')}
            >
              DASHBOARD
            </button>
            <button
              className={`sidebar__tab ${activeTab === 'config' ? 'active' : ''}`}
              onClick={() => setActiveTab('config')}
            >
              CONFIG
            </button>
            <button
              className={`sidebar__tab ${activeTab === 'stages' ? 'active' : ''}`}
              onClick={() => setActiveTab('stages')}
            >
              STAGES
            </button>
          </div>
        </div>

        <div className="app__main">
          {activeTab === 'dashboard' && (
            <Dashboard status={status} running={running} />
          )}
          {activeTab === 'config' && (
            <ConfigPanel config={config} setConfig={setConfig} onSave={saveConfig} />
          )}
          {activeTab === 'stages' && (
            <StageRunner
              status={status}
              running={running}
              onStart={startPipeline}
              onStop={stopPipeline}
              onRunStage={runStage}
              onRefresh={getStatus}
            />
          )}
        </div>
      </div>

      <LogConsole logs={logs} />
    </div>
  );
}

export default App;
