import React from 'react';

const TABS = [
  { id: 'workspace', label: 'Workspace' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'metrics', label: 'Metrics' },
];

export default function Header({ view, setView, health }) {
  return (
    <header className="app-header">
      <div className="header-inner">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            ✦
          </span>
          <div>
            <h1>Extraction Copilot</h1>
            <p>Local-first structured extraction workspace</p>
          </div>
        </div>

        <nav className="nav-tabs" aria-label="Main navigation">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`nav-tab ${view === tab.id ? 'active' : ''}`}
              onClick={() => setView(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className={`health-pill ${health === 'ok' ? 'healthy' : 'unknown'}`}>
          <span className="health-dot" />
          {health === 'ok' ? 'Backend online' : 'Checking backend…'}
        </div>
      </div>
    </header>
  );
}
