import React from 'react';

function Dashboard({ status, running }) {
  const cards = [
    { label: 'SAMPLED', value: status.sampled || 0, color: 'cyan' },
    { label: 'TEACHER', value: status.teacher_done || 0, color: 'blue' },
    { label: 'GEO PASSED', value: status.geo_passed || 0, color: 'yellow' },
    { label: 'JUDGED', value: status.judged || 0, color: 'purple' },
    { label: 'ACCEPTED', value: status.accepted || 0, color: 'green' },
    { label: 'REJECTED', value: status.rejected || 0, color: 'red' },
    { label: 'FLAGGED', value: status.flagged || 0, color: 'orange' },
    { label: 'TOTAL', value: status.total || 0, color: 'white' }
  ];

  const acceptanceRate = status.total > 0
    ? ((status.accepted / status.total) * 100).toFixed(1)
    : 0;

  return (
    <div className="dashboard">
      <div className="dashboard__header">
        <h1 className="dashboard__title">PIPELINE STATUS</h1>
        {running && <span className="dashboard__status dashboard__status--running">RUNNING</span>}
        {!running && <span className="dashboard__status dashboard__status--idle">IDLE</span>}
      </div>

      <div className="dashboard__cards">
        {cards.map(card => (
          <div key={card.label} className={`stat-card stat-card--${card.color}`}>
            <div className="stat-card__value">{card.value}</div>
            <div className="stat-card__label">{card.label}</div>
          </div>
        ))}
      </div>

      <div className="dashboard__progress">
        <div className="progress__header">
          <span className="progress__label">ACCEPTANCE RATE</span>
          <span className="progress__value">{acceptanceRate}%</span>
        </div>
        <div className="progress__bar">
          <div
            className="progress__fill progress__fill--green"
            style={{ width: `${acceptanceRate}%` }}
          />
        </div>
      </div>

      <div className="dashboard__pipeline">
        <div className="pipeline__header">PIPELINE FLOW</div>
        <div className="pipeline__stages">
          <div className={`pipeline__stage ${status.sampled > 0 ? 'complete' : ''}`}>
            <div className="pipeline__stage-icon">1</div>
            <div className="pipeline__stage-label">SAMPLE</div>
            <div className="pipeline__stage-count">{status.sampled || 0}</div>
          </div>
          <div className="pipeline__arrow">→</div>
          <div className={`pipeline__stage ${status.teacher_done > 0 ? 'complete' : ''}`}>
            <div className="pipeline__stage-icon">2</div>
            <div className="pipeline__stage-label">TEACHER</div>
            <div className="pipeline__stage-count">{status.teacher_done || 0}</div>
          </div>
          <div className="pipeline__arrow">→</div>
          <div className={`pipeline__stage ${status.geo_passed > 0 ? 'complete' : ''}`}>
            <div className="pipeline__stage-icon">3</div>
            <div className="pipeline__stage-label">GEO FILTER</div>
            <div className="pipeline__stage-count">{status.geo_passed || 0}</div>
          </div>
          <div className="pipeline__arrow">→</div>
          <div className={`pipeline__stage ${status.judged > 0 ? 'complete' : ''}`}>
            <div className="pipeline__stage-icon">4</div>
            <div className="pipeline__stage-label">JUDGE</div>
            <div className="pipeline__stage-count">{status.judged || 0}</div>
          </div>
          <div className="pipeline__arrow">→</div>
          <div className={`pipeline__stage ${status.accepted > 0 ? 'complete' : ''}`}>
            <div className="pipeline__stage-icon">5</div>
            <div className="pipeline__stage-label">ACCEPTED</div>
            <div className="pipeline__stage-count">{status.accepted || 0}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
