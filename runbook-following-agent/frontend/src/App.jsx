import { useCallback, useEffect, useRef, useState } from 'react'
import {
  uploadRunbook,
  parseRunbook,
  startExecution,
  confirmStep,
  pauseExecution,
  resumeExecution,
  retryStep,
  getExecutionState,
  getLogs,
  getReport,
  downloadReportPdf,
} from './api/client'

const STATUS_COLORS = {
  pending: 'text-devops-muted',
  running: 'text-devops-accent animate-pulse',
  success: 'text-devops-success',
  failed: 'text-devops-danger',
  blocked: 'text-devops-warning',
  skipped: 'text-devops-muted',
  waiting_confirmation: 'text-devops-warning',
}

function StatusBadge({ status }) {
  return (
    <span className={`text-xs font-mono uppercase tracking-wide ${STATUS_COLORS[status] || 'text-devops-muted'}`}>
      {status?.replace('_', ' ')}
    </span>
  )
}

function ProgressBar({ percent, status }) {
  const color =
    status === 'failed' ? 'bg-devops-danger' :
    status === 'completed' ? 'bg-devops-success' :
    status === 'paused' ? 'bg-devops-warning' :
    'bg-devops-accent'

  return (
    <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${Math.min(100, percent)}%` }}
      />
    </div>
  )
}

function TerminalLine({ line }) {
  const colorClass =
    line.type === 'error' ? 'text-devops-danger' :
    line.type === 'success' ? 'text-devops-success' :
    line.type === 'warning' ? 'text-devops-warning' :
    line.type === 'command' ? 'text-devops-accent' :
    'text-devops-muted'

  return (
    <div className={`font-mono text-sm leading-relaxed animate-slide-in ${colorClass}`}>
      {line.text}
    </div>
  )
}

export default function App() {
  const [filename, setFilename] = useState(null)
  const [steps, setSteps] = useState([])
  const [stepsDetail, setStepsDetail] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [execState, setExecState] = useState(null)
  const [terminalLines, setTerminalLines] = useState([])
  const [logs, setLogs] = useState([])
  const [report, setReport] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [executing, setExecuting] = useState(false)
  const [error, setError] = useState(null)
  const [pendingConfirm, setPendingConfirm] = useState(null)
  const [dragOver, setDragOver] = useState(false)

  const terminalRef = useRef(null)
  const pollRef = useRef(null)
  const eventSourceRef = useRef(null)

  const addTerminalLine = useCallback((text, type = 'info') => {
    setTerminalLines((prev) => [...prev, { text, type, id: Date.now() + Math.random() }])
  }, [])

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
    }
  }, [terminalLines])

  const fetchReport = useCallback(async (sid) => {
    try {
      const res = await getReport(sid)
      setReport(res.data)
    } catch {
      // Report may not be ready yet
    }
  }, [])

  const fetchLogs = useCallback(async (sid) => {
    try {
      const res = await getLogs(sid)
      setLogs(res.data.entries || [])
    } catch {
      // ignore
    }
  }, [])

  const pollState = useCallback(async (sid) => {
    try {
      const res = await getExecutionState(sid)
      setExecState(res.data)
      if (res.data.pending_confirmation) {
        setPendingConfirm(res.data.pending_confirmation)
      }
      if (res.data.status === 'completed' || res.data.status === 'failed') {
        setExecuting(false)
        await fetchReport(sid)
        await fetchLogs(sid)
        if (pollRef.current) clearInterval(pollRef.current)
      }
    } catch {
      // ignore polling errors
    }
  }, [fetchReport, fetchLogs])

  const connectSSE = useCallback((sid) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const es = new EventSource(`/api/execute/stream/${sid}`)
    eventSourceRef.current = es

    es.onmessage = (event) => {
      const data = JSON.parse(event.data)
      switch (data.type) {
        case 'step_start':
          addTerminalLine(`▶ Step ${data.step}: ${data.command}`, 'command')
          break
        case 'step_complete':
          addTerminalLine(
            data.status === 'success'
              ? `✓ Step ${data.step} completed (${data.execution_time_ms}ms)`
              : `✗ Step ${data.step} failed (exit ${data.exit_code})`,
            data.status === 'success' ? 'success' : 'error'
          )
          if (data.stdout) addTerminalLine(data.stdout.trim(), 'info')
          if (data.stderr) addTerminalLine(data.stderr.trim(), 'error')
          break
        case 'confirmation_required':
          addTerminalLine(`⚠ Risky command detected at step ${data.step}: ${data.command}`, 'warning')
          addTerminalLine('  Awaiting confirmation...', 'warning')
          setPendingConfirm({ step: data.step, command: data.command, message: 'Risky command detected. Continue?' })
          break
        case 'step_skipped':
          addTerminalLine(`⊘ Step ${data.step} skipped by user`, 'warning')
          break
        case 'paused':
          addTerminalLine('⏸ Execution paused', 'warning')
          break
        case 'resumed':
          addTerminalLine('▶ Execution resumed', 'info')
          break
        case 'execution_complete':
          addTerminalLine('✓ Runbook execution completed', 'success')
          setExecuting(false)
          fetchReport(sid)
          fetchLogs(sid)
          es.close()
          break
        case 'execution_failed':
          addTerminalLine('✗ Execution stopped due to failure', 'error')
          setExecuting(false)
          fetchReport(sid)
          fetchLogs(sid)
          es.close()
          break
        default:
          break
      }
      pollState(sid)
    }

    es.onerror = () => es.close()
  }, [addTerminalLine, fetchReport, fetchLogs, pollState])

  const handleUpload = async (file) => {
    if (!file || !file.name.endsWith('.md')) {
      setError('Please upload a .md runbook file')
      return
    }
    setError(null)
    setUploading(true)
    setSteps([])
    setStepsDetail([])
    setReport(null)
    setLogs([])
    setTerminalLines([])
    setSessionId(null)
    setExecState(null)
    setPendingConfirm(null)

    try {
      const res = await uploadRunbook(file)
      setFilename(res.data.filename)
      addTerminalLine(`Uploaded runbook: ${res.data.filename}`, 'success')
      await handleParse(res.data.filename)
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleParse = async (fname) => {
    setParsing(true)
    try {
      const res = await parseRunbook(fname)
      setSteps(res.data.steps)
      setStepsDetail(res.data.steps_detail || [])
      addTerminalLine(`Parsed ${res.data.total_steps} steps from runbook`, 'info')
    } catch (err) {
      setError(err.response?.data?.detail || 'Parse failed')
    } finally {
      setParsing(false)
    }
  }

  const handleExecute = async () => {
    if (!filename) return
    setExecuting(true)
    setError(null)
    setReport(null)
    setPendingConfirm(null)
    addTerminalLine('Starting runbook execution...', 'command')

    try {
      const res = await startExecution(filename, sessionId)
      const sid = res.data.session_id
      setSessionId(sid)
      setExecState(res.data.state)
      connectSSE(sid)
      pollRef.current = setInterval(() => pollState(sid), 1500)
    } catch (err) {
      setError(err.response?.data?.detail || 'Execution failed to start')
      setExecuting(false)
    }
  }

  const handleConfirm = async (approved) => {
    if (!sessionId || !pendingConfirm) return
    try {
      await confirmStep(sessionId, pendingConfirm.step, approved)
      setPendingConfirm(null)
      addTerminalLine(approved ? 'User approved risky command' : 'User declined risky command', approved ? 'warning' : 'info')
      pollState(sessionId)
    } catch (err) {
      setError(err.response?.data?.detail || 'Confirmation failed')
    }
  }

  const handlePause = async () => {
    if (!sessionId) return
    await pauseExecution(sessionId)
    pollState(sessionId)
  }

  const handleResume = async () => {
    if (!sessionId) return
    setExecuting(true)
    await resumeExecution(sessionId)
    pollState(sessionId)
  }

  const handleRetry = async (stepNum) => {
    if (!sessionId) return
    setExecuting(true)
    addTerminalLine(`Retrying step ${stepNum}...`, 'command')
    await retryStep(sessionId, stepNum)
    pollState(sessionId)
  }

  const handleDownloadPdf = async () => {
    if (!sessionId) return
    try {
      const res = await downloadReportPdf(sessionId)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `runbook-report-${sessionId.slice(0, 8)}.pdf`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch {
      setError('PDF download failed')
    }
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    handleUpload(file)
  }

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (eventSourceRef.current) eventSourceRef.current.close()
    }
  }, [])

  const progress = execState?.progress_percent || 0
  const execStatus = execState?.status || 'idle'

  return (
    <div className="min-h-screen bg-devops-bg">
      {/* Header */}
      <header className="border-b border-devops-border bg-devops-panel/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-devops-accent/20 border border-devops-accent/40 flex items-center justify-center">
              <span className="text-devops-accent text-lg font-bold">RB</span>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Runbook Following Agent</h1>
              <p className="text-xs text-devops-muted">Safe automated runbook execution</p>
            </div>
          </div>
          {sessionId && (
            <div className="text-xs font-mono text-devops-muted hidden sm:block">
              session: {sessionId.slice(0, 8)}...
            </div>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {error && (
          <div className="panel border-red-500/50 bg-red-500/10 text-red-300 text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Upload Panel */}
          <section className="panel">
            <h2 className="text-sm font-semibold text-devops-muted uppercase tracking-wider mb-4">
              Upload Runbook
            </h2>
            <div
              className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${
                dragOver ? 'border-devops-accent bg-devops-accent/5' : 'border-devops-border hover:border-devops-accent/50'
              }`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => document.getElementById('file-input').click()}
            >
              <input
                id="file-input"
                type="file"
                accept=".md"
                className="hidden"
                onChange={(e) => handleUpload(e.target.files[0])}
              />
              <div className="text-4xl mb-3">📄</div>
              <p className="text-white font-medium">Drop your .md runbook here</p>
              <p className="text-devops-muted text-sm mt-1">or click to browse</p>
              {filename && (
                <p className="mt-3 text-devops-accent font-mono text-sm">{filename}</p>
              )}
              {(uploading || parsing) && (
                <p className="mt-2 text-devops-accent text-sm animate-pulse">
                  {uploading ? 'Uploading...' : 'Parsing...'}
                </p>
              )}
            </div>
          </section>

          {/* Execution Controls */}
          <section className="panel">
            <h2 className="text-sm font-semibold text-devops-muted uppercase tracking-wider mb-4">
              Execution Controls
            </h2>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-devops-muted">Progress</span>
                  <span className="font-mono text-devops-accent">{progress.toFixed(0)}%</span>
                </div>
                <ProgressBar percent={progress} status={execStatus} />
                <p className="text-xs text-devops-muted mt-1 capitalize">{execStatus.replace('_', ' ')}</p>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  className="btn-primary flex-1 min-w-[120px]"
                  onClick={handleExecute}
                  disabled={!filename || steps.length === 0 || executing}
                >
                  {executing ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-slate-900 animate-pulse-dot" />
                      Executing...
                    </span>
                  ) : 'Execute Runbook'}
                </button>
                {executing && execStatus !== 'paused' && (
                  <button className="btn-secondary" onClick={handlePause}>Pause</button>
                )}
                {execStatus === 'paused' && (
                  <button className="btn-secondary" onClick={handleResume}>Resume</button>
                )}
              </div>

              {pendingConfirm && (
                <div className="border border-devops-warning/50 bg-yellow-500/10 rounded-lg p-4 animate-slide-in">
                  <p className="text-devops-warning font-medium text-sm mb-1">⚠ Risky Command Detected</p>
                  <p className="font-mono text-sm text-white mb-1">{pendingConfirm.command}</p>
                  <p className="text-devops-muted text-xs mb-3">{pendingConfirm.message}</p>
                  <div className="flex gap-2">
                    <button className="btn-success flex-1" onClick={() => handleConfirm(true)}>Yes, Continue</button>
                    <button className="btn-danger flex-1" onClick={() => handleConfirm(false)}>No, Skip</button>
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>

        {/* Parsed Steps */}
        {steps.length > 0 && (
          <section className="panel">
            <h2 className="text-sm font-semibold text-devops-muted uppercase tracking-wider mb-4">
              Parsed Steps ({steps.length})
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-devops-muted text-left border-b border-devops-border">
                    <th className="pb-2 pr-4 font-medium">Step</th>
                    <th className="pb-2 pr-4 font-medium">Command</th>
                    <th className="pb-2 pr-4 font-medium">Risk</th>
                    <th className="pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {stepsDetail.map((s) => {
                    const result = execState?.results?.find((r) => r.step === s.step)
                    const status = result?.status || s.status || 'pending'
                    return (
                      <tr key={s.step} className="border-b border-devops-border/50 hover:bg-slate-800/30">
                        <td className="py-2.5 pr-4 font-mono text-devops-accent">{s.step}</td>
                        <td className="py-2.5 pr-4 font-mono">{s.command}</td>
                        <td className="py-2.5 pr-4">
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            s.risk_level === 'risky' ? 'bg-yellow-500/20 text-yellow-300' :
                            s.risk_level === 'safe' ? 'bg-green-500/20 text-green-300' :
                            'bg-red-500/20 text-red-300'
                          }`}>
                            {s.risk_level}
                          </span>
                        </td>
                        <td className="py-2.5 flex items-center gap-2">
                          <StatusBadge status={status} />
                          {status === 'failed' && sessionId && (
                            <button
                              className="text-xs text-devops-accent hover:underline"
                              onClick={() => handleRetry(s.step)}
                            >
                              retry
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Live Terminal */}
          <section className="panel">
            <h2 className="text-sm font-semibold text-devops-muted uppercase tracking-wider mb-4 flex items-center gap-2">
              Live Terminal
              {executing && <span className="w-2 h-2 rounded-full bg-devops-success animate-pulse-dot" />}
            </h2>
            <div
              ref={terminalRef}
              className="terminal-scroll bg-slate-950 border border-devops-border rounded-lg p-4 h-64 overflow-y-auto space-y-1"
            >
              {terminalLines.length === 0 ? (
                <p className="text-devops-muted font-mono text-sm">Waiting for execution...</p>
              ) : (
                terminalLines.map((line) => <TerminalLine key={line.id} line={line} />)
              )}
            </div>
          </section>

          {/* Execution Logs */}
          <section className="panel">
            <h2 className="text-sm font-semibold text-devops-muted uppercase tracking-wider mb-4">
              Execution Logs
            </h2>
            <div className="terminal-scroll bg-slate-950 border border-devops-border rounded-lg p-4 h-64 overflow-y-auto space-y-2">
              {logs.length === 0 ? (
                <p className="text-devops-muted font-mono text-sm">No logs yet</p>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className="text-xs font-mono border-b border-devops-border/30 pb-2">
                    <div className="flex justify-between text-devops-muted">
                      <span>{log.timestamp?.slice(11, 19)}</span>
                      <StatusBadge status={log.status} />
                    </div>
                    <div className="text-white mt-0.5">Step {log.step}: {log.command}</div>
                    {log.stdout && <div className="text-devops-muted truncate">{log.stdout}</div>}
                    {log.stderr && <div className="text-devops-danger truncate">{log.stderr}</div>}
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        {/* Final Report */}
        {report && (
          <section className="panel animate-slide-in">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-devops-muted uppercase tracking-wider">
                Final Report
              </h2>
              <button className="btn-secondary text-sm" onClick={handleDownloadPdf}>
                Download PDF
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-4">
              {[
                { label: 'Total Steps', value: report.total_steps },
                { label: 'Successful', value: report.successful, color: 'text-devops-success' },
                { label: 'Failed', value: report.failed, color: 'text-devops-danger' },
                { label: 'Blocked', value: report.blocked, color: 'text-devops-warning' },
                { label: 'Skipped', value: report.skipped, color: 'text-devops-muted' },
                { label: 'Duration (ms)', value: report.execution_duration_ms?.toFixed(0) },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-slate-800/50 rounded-lg p-3 text-center">
                  <div className={`text-2xl font-bold ${color || 'text-white'}`}>{value}</div>
                  <div className="text-xs text-devops-muted mt-1">{label}</div>
                </div>
              ))}
            </div>
            <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${
              report.overall_status === 'success' ? 'bg-green-500/20 text-green-300' :
              report.overall_status === 'failed' ? 'bg-red-500/20 text-red-300' :
              'bg-yellow-500/20 text-yellow-300'
            }`}>
              Overall Status: {report.overall_status?.toUpperCase()}
            </div>
          </section>
        )}
      </main>

      <footer className="border-t border-devops-border mt-8 py-4 text-center text-xs text-devops-muted">
        Runbook Following Agent — Hackathon MVP
      </footer>
    </div>
  )
}
