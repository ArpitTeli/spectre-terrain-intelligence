import React, { useState } from 'react';

const API = window.pipelineAPI;

function ConfigPanel({ config, setConfig, onSave }) {
  const [showKey, setShowKey] = useState(false);

  const handleChange = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  };

  const maskKey = (key) => {
    if (!key) return '';
    if (key.length <= 10) return '••••••••';
    return key.substring(0, 8) + '••••' + key.substring(key.length - 4);
  };

  return (
    <div className="config">
      <div className="config__header">
        <h1 className="config__title">CONFIGURATION</h1>
      </div>

      <div className="config__section">
        <div className="config__section-title">API ACCESS</div>

        <div className="config__field">
          <label className="config__label">OPENROUTER API KEY</label>
          <div className="config__input-group">
            <input
              className="config__input"
              type={showKey ? 'text' : 'password'}
              value={config.openrouterApiKey}
              onChange={(e) => handleChange('openrouterApiKey', e.target.value)}
              placeholder="sk-or-..."
            />
            <button
              className="config__btn config__btn--toggle"
              onClick={() => setShowKey(!showKey)}
            >
              {showKey ? 'HIDE' : 'SHOW'}
            </button>
          </div>
          <div className="config__hint">
            Get your key at <a href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">openrouter.ai/keys</a>
          </div>
        </div>
      </div>

      <div className="config__section">
        <div className="config__section-title">MODEL SELECTION</div>

        <div className="config__field">
          <label className="config__label">TEACHER MODEL</label>
          <input
            className="config__input"
            type="text"
            value={config.teacherModel}
            onChange={(e) => handleChange('teacherModel', e.target.value)}
            placeholder="anthropic/claude-3.5-sonnet"
          />
          <div className="config__hint">Generates tactical decisions for training</div>
        </div>

        <div className="config__field">
          <label className="config__label">JUDGE A MODEL</label>
          <input
            className="config__input"
            type="text"
            value={config.judgeAModel}
            onChange={(e) => handleChange('judgeAModel', e.target.value)}
            placeholder="anthropic/claude-3.5-haiku"
          />
          <div className="config__hint">First judge for tactical validation</div>
        </div>

        <div className="config__field">
          <label className="config__label">JUDGE B MODEL</label>
          <input
            className="config__input"
            type="text"
            value={config.judgeBModel}
            onChange={(e) => handleChange('judgeBModel', e.target.value)}
            placeholder="openai/gpt-4o-mini"
          />
          <div className="config__hint">Second judge (different provider for independence)</div>
        </div>
      </div>

      <div className="config__section">
        <div className="config__section-title">PIPELINE SETTINGS</div>

        <div className="config__field">
          <label className="config__label">TARGET EXAMPLES</label>
          <input
            className="config__input config__input--number"
            type="number"
            value={config.targetExamples}
            onChange={(e) => handleChange('targetExamples', parseInt(e.target.value) || 1000)}
            min="100"
            max="10000"
          />
          <div className="config__hint">Recommended: 500-5000</div>
        </div>

        <div className="config__field">
          <label className="config__label">MAP</label>
          <select
            className="config__select"
            value={config.mapName}
            onChange={(e) => handleChange('mapName', e.target.value)}
          >
            <option value="stratis">Stratis</option>
            <option value="altis">Altis</option>
            <option value="tanoa">Tanoa</option>
            <option value="malden">Malden</option>
          </select>
        </div>
      </div>

      <div className="config__actions">
        <button className="btn btn--primary" onClick={onSave}>
          SAVE CONFIGURATION
        </button>
      </div>
    </div>
  );
}

export default ConfigPanel;
