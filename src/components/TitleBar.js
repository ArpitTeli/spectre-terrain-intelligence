import React from 'react';

const API = window.pipelineAPI;

function TitleBar() {
  return (
    <div className="titlebar">
      <div className="titlebar__drag">
        <span className="titlebar__title">SPECTRE</span>
        <span className="titlebar__subtitle">TRAINING PIPELINE</span>
      </div>
      <div className="titlebar__controls">
        <button className="titlebar__btn" onClick={() => API?.minimize()}>─</button>
        <button className="titlebar__btn" onClick={() => API?.maximize()}>□</button>
        <button className="titlebar__btn titlebar__btn--close" onClick={() => API?.close()}>×</button>
      </div>
    </div>
  );
}

export default TitleBar;
