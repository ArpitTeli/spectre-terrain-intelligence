import React from 'react';

function StageRunner({ status, running, onStart, onStop, onRunStage, onRefresh }) {
  const stages = [
    { id: 'sample', name: 'SAMPLE', desc: 'Generate scenarios', count: status.sampled || 0 },
    { id: 'teacher', name: 'TEACHER', desc: 'LLM generates decisions', count: status.teacher_done || 0 },
    { id: 'geo_filter', name: 'GEO FILTER', desc: 'Spatial validation', count: status.geo_passed || 0 },
    { id: 'judge', name: 'JUDGE', desc: 'Dual judge verification', count: status.judged || 0 },
    { id: 'resolve', name: 'RESOLVE', desc: 'Verdict aggregation', count: status.accepted || 0 },
    { id: 'export', name: 'EXPORT', desc: 'JSONL for training', count: null }
  ];

  return (
    <div className="stages">
      <div className="stages__header">
        <h1 className="stages__title">PIPELINE STAGES</h1>
        <button className="btn btn--secondary" onClick={onRefresh}>
          REFRESH
        </button>
      </div>

      <div className="stages__controls">
        {!running ? (
          <button className="btn btn--primary btn--large" onClick={onStart}>
            RUN FULL PIPELINE
          </button>
        ) : (
          <button className="btn btn--danger btn--large" onClick={onStop}>
            STOP PIPELINE
          </button>
        )}
      </div>

      <div className="stages__list">
        {stages.map((stage, index) => (
          <div key={stage.id} className="stage-card">
            <div className="stage-card__number">{index + 1}</div>
            <div className="stage-card__info">
              <div className="stage-card__name">{stage.name}</div>
              <div className="stage-card__desc">{stage.desc}</div>
            </div>
            <div className="stage-card__count">
              {stage.count !== null ? stage.count : '—'}
            </div>
            <button
              className="btn btn--small"
              onClick={() => onRunStage(stage.id)}
              disabled={running}
            >
              RUN
            </button>
          </div>
        ))}
      </div>

      <div className="stages__info">
        <div className="info-card">
          <div className="info-card__title">COST ESTIMATE</div>
          <div className="info-card__value">
            ~${((status.total || 0) * 0.014).toFixed(2)}
          </div>
          <div className="info-card__hint">Based on current example count</div>
        </div>

        <div className="info-card">
          <div className="info-card__title">TARGET</div>
          <div className="info-card__value">
            {status.total || 0} / {status.target || 1000}
          </div>
          <div className="info-card__hint">Examples generated</div>
        </div>

        <div className="info-card">
          <div className="info-card__title">ACCEPTANCE RATE</div>
          <div className="info-card__value">
            {status.total > 0 ? ((status.accepted / status.total) * 100).toFixed(1) : 0}%
          </div>
          <div className="info-card__hint">Of generated examples</div>
        </div>
      </div>
    </div>
  );
}

export default StageRunner;
