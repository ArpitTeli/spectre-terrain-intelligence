import React, { useEffect, useRef, useState } from 'react';

function LogConsole({ logs }) {
  const consoleRef = useRef(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [logs]);

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour12: false });
  };

  const getLogClass = (type) => {
    switch (type) {
      case 'error': return 'log--error';
      case 'warn': return 'log--warn';
      case 'success': return 'log--success';
      case 'info': return 'log--info';
      default: return 'log--default';
    }
  };

  return (
    <div className={`console ${collapsed ? 'console--collapsed' : ''}`}>
      <div className="console__header" onClick={() => setCollapsed(!collapsed)}>
        <span className="console__title">CONSOLE</span>
        <span className="console__count">{logs.length}</span>
        <span className="console__toggle">{collapsed ? '▲' : '▼'}</span>
      </div>
      {!collapsed && (
        <div className="console__body" ref={consoleRef}>
          {logs.length === 0 ? (
            <div className="console__empty">No logs yet...</div>
          ) : (
            logs.map((log, index) => (
              <div key={index} className={`log ${getLogClass(log.type)}`}>
                <span className="log__time">{formatTime(log.time)}</span>
                <span className="log__text">{log.text}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default LogConsole;
