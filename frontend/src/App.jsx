import React, { useCallback, useEffect, useState } from 'react';
import { api } from './api.js';
import Header from './components/Header.jsx';
import TaskSubmission from './components/TaskSubmission.jsx';
import TaskList from './components/TaskList.jsx';
import TaskDetail from './components/TaskDetail.jsx';
import MetricsPanel from './components/MetricsPanel.jsx';

export default function App() {
  const [view, setView] = useState('workspace');
  const [health, setHealth] = useState('');
  const [tasks, setTasks] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [globalError, setGlobalError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [nextTasks, nextMetrics] = await Promise.all([
        api.listTasks(statusFilter),
        api.metrics(),
      ]);
      setTasks(nextTasks);
      setMetrics(nextMetrics);
      setGlobalError('');
    } catch (err) {
      setGlobalError(err.message);
    }
  }, [statusFilter]);

  useEffect(() => {
    api
      .health()
      .then((result) => setHealth(result.status))
      .catch(() => setHealth('unreachable'));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const selectedTask = tasks.find((task) => task.id === selectedId) || null;

  function handleCreated(created) {
    setSelectedId(created.id);
    refresh();
  }

  function handleUpdated(updated) {
    refresh();
  }

  function handleSelect(id) {
    setSelectedId(id);
    setView('tasks');
  }

  const listProps = {
    tasks,
    status: statusFilter,
    setStatus: setStatusFilter,
    onSelect: handleSelect,
    selectedId,
  };

  return (
    <div className="app-shell">
      <Header view={view} setView={setView} health={health} />

      <main className="app-main">
        {globalError && (
          <div className="alert error global">
            {globalError} — is the FastAPI backend running on port 8000?
          </div>
        )}

        {view === 'workspace' && (
          <>
            <TaskSubmission onCreated={handleCreated} />
            <TaskList {...listProps} />
          </>
        )}

        {view === 'tasks' && (
          <div className="tasks-layout">
            <TaskList {...listProps} />
            <TaskDetail task={selectedTask} onUpdated={handleUpdated} />
          </div>
        )}

        {view === 'metrics' && <MetricsPanel metrics={metrics} />}
      </main>

      <footer className="app-footer">
        <span>Local-first stack · Ollama + SQLite + FastAPI + React</span>
        <span>No paid APIs · No external cloud services</span>
      </footer>
    </div>
  );
}
