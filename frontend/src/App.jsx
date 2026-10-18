import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, BookOpen,
  Check, CheckCircle2, ChevronDown, CircleHelp, Clock3, Command, Download,
  FileCode2, FileText, Gauge, GitBranch, History, LayoutDashboard, LifeBuoy,
  LoaderCircle, LockKeyhole, Menu, MoreHorizontal, Play, Plus, RefreshCw,
  Search, Settings2, ShieldCheck, Sparkles, Terminal, UploadCloud, Workflow, X,
  Zap
} from 'lucide-react';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? '' : 'https://runbook-following-agent2.onrender.com')).replace(/\/$/, '');
async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const type = response.headers.get('content-type') || '';
  const data = type.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(data?.detail || data?.message || `Request failed (${response.status})`);
  return data;
}
const navItems = [
  { label: 'Overview', icon: LayoutDashboard },
  { label: 'Runbooks', icon: BookOpen },
  { label: 'Executions', icon: Workflow },
  { label: 'Activity logs', icon: History },
  { label: 'Reports', icon: FileText }
];

function CoreScene() {
  const mountRef = useRef(null);
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let renderer, frame, observer;
    try {
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
      camera.position.set(0, 0, 8);
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7));
      renderer.setSize(mount.clientWidth, mount.clientHeight);
      renderer.setClearColor(0x000000, 0);
      mount.appendChild(renderer.domElement);
      const group = new THREE.Group();
      scene.add(group);
      scene.add(new THREE.AmbientLight(0x7aa9ff, 1.8));
      const key = new THREE.PointLight(0x4385ff, 30, 20);
      key.position.set(3, 2, 4); scene.add(key);
      const core = new THREE.Mesh(
        new THREE.IcosahedronGeometry(1.05, 4),
        new THREE.MeshPhysicalMaterial({ color: 0x2767e8, metalness: .35, roughness: .24, transmission: .12, transparent: true, opacity: .92, emissive: 0x08245e, emissiveIntensity: .65, clearcoat: 1 })
      );
      group.add(core);
      const wire = new THREE.Mesh(
        new THREE.IcosahedronGeometry(1.28, 2),
        new THREE.MeshBasicMaterial({ color: 0x5da7ff, wireframe: true, transparent: true, opacity: .25 })
      );
      group.add(wire);
      [1.75, 2.05].forEach((radius, i) => {
        const ring = new THREE.Mesh(new THREE.TorusGeometry(radius, .009, 8, 160), new THREE.MeshBasicMaterial({ color: i ? 0x4d72bd : 0x64cfff, transparent: true, opacity: i ? .38 : .72 }));
        ring.rotation.x = i ? 1.03 : .55;
        ring.rotation.y = i ? -.35 : .4;
        group.add(ring);
      });
      const points = new THREE.BufferGeometry();
      const positions = [];
      for (let i = 0; i < 520; i++) {
        const r = 2.5 + Math.random() * 1.7, a = Math.random() * Math.PI * 2, y = (Math.random() - .5) * 3.7;
        positions.push(Math.cos(a) * r, y, Math.sin(a) * r);
      }
      points.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      const stars = new THREE.Points(points, new THREE.PointsMaterial({ color: 0x82b6ff, size: .018, transparent: true, opacity: .7 }));
      scene.add(stars);
      const resize = () => {
        if (!mount.clientWidth || !mount.clientHeight) return;
        camera.aspect = mount.clientWidth / mount.clientHeight; camera.updateProjectionMatrix();
        renderer.setSize(mount.clientWidth, mount.clientHeight);
      };
      observer = new ResizeObserver(resize); observer.observe(mount);
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const animate = () => {
        frame = requestAnimationFrame(animate);
        if (!reduceMotion) { group.rotation.y += .0025; group.rotation.x = Math.sin(Date.now() * .00022) * .08; stars.rotation.y -= .0002; }
        renderer.render(scene, camera);
      };
      animate();
    } catch {
      mount.classList.add('scene-fallback');
    }
    return () => {
      cancelAnimationFrame(frame); observer?.disconnect();
      if (renderer) { renderer.dispose(); renderer.domElement.remove(); }
    };
  }, []);
  return <div className="core-scene" ref={mountRef} aria-label="Animated 3D operations core" role="img"><div className="scene-fallback-orb" /></div>;
}

function StatCard({ icon: Icon, label, value, hint, tone = 'blue', trend }) {
  return <article className="stat-card">
    <div className={`stat-icon ${tone}`}><Icon size={18} /></div>
    <div className="stat-copy"><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>
    {trend && <span className="stat-trend"><ArrowUpRight size={13} />{trend}</span>}
  </article>;
}

function App() {
  const [active, setActive] = useState('Overview');
  const [mobileNav, setMobileNav] = useState(false);
  const [apiStatus, setApiStatus] = useState('checking');
  const [logs, setLogs] = useState([]);
  const [report, setReport] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState(null);
  const [search, setSearch] = useState('');
  const [uploaded, setUploaded] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [showUpload, setShowUpload] = useState(false);

  const refreshData = useCallback(async () => {
    setRefreshing(true);
    try {
      const [health, logData, reportData] = await Promise.allSettled([
        api('/openapi.json'), api('/logs'), api('/report')
      ]);
      setApiStatus(health.status === 'fulfilled' ? 'online' : 'offline');
      if (logData.status === 'fulfilled') {
        const d = logData.value;
        setLogs(Array.isArray(d) ? d : (d?.logs || d?.entries || d?.items || []));
      }
      if (reportData.status === 'fulfilled') setReport(reportData.value);
    } finally { setRefreshing(false); }
  }, []);
  useEffect(() => { refreshData(); }, [refreshData]);

  const uploadRunbook = async (event) => {
    event.preventDefault();
    if (!file) { setNotice({ type: 'error', text: 'Choose a Markdown runbook first.' }); return; }
    setUploading(true); setNotice(null);
    try {
      const form = new FormData(); form.append('file', file);
      const result = await api('/upload', { method: 'POST', body: form });
      setUploadResult(result); setUploaded(true);
      setNotice({ type: 'success', text: 'Runbook uploaded. Review its parsed steps before execution.' });
      setActive('Runbooks');
    } catch (error) {
      setNotice({ type: 'error', text: `Upload failed: ${error.message}. Check the backend API and expected upload format.` });
    } finally { setUploading(false); }
  };

  const metrics = useMemo(() => {
    const obj = report && typeof report === 'object' ? report : {};
    const total = obj.total_executions ?? obj.total_runs ?? obj.total ?? (Array.isArray(logs) ? logs.length : 0);
    const success = obj.success ?? obj.successful ?? obj.success_count ?? 0;
    const failed = obj.failed ?? obj.failure_count ?? obj.fail_count ?? 0;
    return { total, success, failed };
  }, [report, logs]);

  const filteredLogs = useMemo(() => {
    const q = search.trim().toLowerCase();
    return logs.filter(item => !q || JSON.stringify(item).toLowerCase().includes(q)).slice(0, 8);
  }, [logs, search]);

  const downloadReport = async () => {
    try {
      const response = await fetch(`${API_BASE}/report/pdf`);
      if (!response.ok) throw new Error(`Report request failed (${response.status})`);
      const blob = await response.blob(), url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'runbook-report.pdf'; a.click();
      URL.revokeObjectURL(url);
    } catch (error) { setNotice({ type: 'error', text: error.message }); }
  };

  const title = active === 'Overview' ? 'Operations overview' : active;
  const statusLabel = apiStatus === 'online' ? 'API connected' : apiStatus === 'offline' ? 'API unavailable' : 'Connecting…';

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? 'mobile-open' : ''}`}>
      <div className="brand">
        <div className="brand-mark"><Command size={21} strokeWidth={2.2} /></div>
        <div><strong>runbook<span>.</span>os</strong><small>AGENT PLATFORM</small></div>
        <button className="icon-button mobile-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={18}/></button>
      </div>
      <div className="workspace-label">WORKSPACE <ChevronDown size={13}/></div>
      <div className="workspace-card"><div className="workspace-avatar">O</div><div><strong>Operations team</strong><small>Personal workspace</small></div><MoreHorizontal size={17}/></div>
      <nav className="nav-list" aria-label="Main navigation">
        <span className="nav-caption">PLATFORM</span>
        {navItems.map(({ label, icon: Icon }) => <button key={label} className={`nav-item ${active === label ? 'active' : ''}`} onClick={() => { setActive(label); setMobileNav(false); }}>
          <Icon size={17}/><span>{label}</span>{label === 'Executions' && <span className="nav-count">{logs.length || '—'}</span>}
        </button>)}
        <span className="nav-caption nav-caption-spaced">PREFERENCES</span>
        <button className={`nav-item ${active === 'Settings' ? 'active' : ''}`} onClick={() => setActive('Settings')}><Settings2 size={17}/><span>Settings</span></button>
      </nav>
      <div className="sidebar-bottom">
        <div className="security-card"><div className="security-icon"><ShieldCheck size={17}/></div><strong>Safety-first execution</strong><p>Risky actions stay gated behind explicit approval.</p><div className="security-link"><LockKeyhole size={12}/> Guardrails enabled</div></div>
        <div className="profile-row"><div className="profile-avatar">H</div><div className="profile-copy"><strong>Workspace owner</strong><small>Local session</small></div><MoreHorizontal size={17}/></div>
      </div>
    </aside>

    <main className="main-panel">
      <header className="topbar">
        <div className="topbar-left"><button className="icon-button menu-button" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={20}/></button><span className="breadcrumb-muted">Workspace</span><span className="breadcrumb-slash">/</span><strong>{title}</strong></div>
        <div className="topbar-actions"><div className={`connection-pill ${apiStatus}`}><span className="connection-dot"/>{statusLabel}</div><button className="icon-button" onClick={refreshData} aria-label="Refresh data" title="Refresh data"><RefreshCw size={17} className={refreshing ? 'spin' : ''}/></button><button className="help-button" onClick={() => setNotice({ type: 'info', text: 'Upload a Markdown runbook, review its steps, then use the backend-supported execution controls.'})}><CircleHelp size={16}/><span>Help</span></button></div>
      </header>

      <div className="content">
        {notice && <div className={`notice ${notice.type}`} role="status"><span>{notice.text}</span><button onClick={() => setNotice(null)} aria-label="Dismiss notice"><X size={15}/></button></div>}
        {active === 'Overview' && <>
          <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-dot"/> YOUR OPERATIONS, IN CONTROL</div><h1>Good afternoon.<br/><span>Let's run things smoothly.</span></h1><p>One workspace to orchestrate runbooks, monitor execution, and keep every operation accountable.</p></div><button className="primary-button" onClick={() => { setActive('Runbooks'); setShowUpload(true); }}><Plus size={17}/> New runbook <ArrowRight size={15}/></button></section>

          <section className="hero-card">
            <div className="hero-grid"/>
            <div className="hero-copy"><div className="hero-kicker"><Sparkles size={14}/> RUNBOOK INTELLIGENCE</div><h2>From instructions<br/>to <span>safe execution.</span></h2><p>Turn operational playbooks into traceable workflows—with validation and human approval where it matters.</p><button className="hero-button" onClick={() => { setActive('Runbooks'); setShowUpload(true); }}>Open runbook workspace <ArrowRight size={15}/></button><div className="hero-foot"><span><ShieldCheck size={14}/> Approval-aware</span><span><Activity size={14}/> Execution visibility</span></div></div>
            <div className="hero-visual"><CoreScene/><div className="orbit-label orbit-label-top"><span className="pulse-dot"/> AGENT CORE <small>READY STATE</small></div><div className="orbit-label orbit-label-bottom"><div className="mini-wave"><i/><i/><i/><i/><i/><i/></div><div><strong>Execution engine</strong><small>Waiting for a runbook</small></div></div><div className="floating-chip chip-one"><CheckCircle2 size={14}/> Guardrails active</div><div className="floating-chip chip-two"><GitBranch size={14}/> Workflow aware</div></div>
          </section>

          <section className="section-heading"><div><h2>Workspace pulse</h2><p>Live data from your connected backend</p></div><button className="text-button" onClick={refreshData}><RefreshCw size={14}/> Refresh</button></section>
          <section className="stats-grid">
            <StatCard icon={BookOpen} label="Runbook activity" value={String(metrics.total)} hint="Reported executions / log entries" tone="blue"/>
            <StatCard icon={CheckCircle2} label="Successful steps" value={String(metrics.success)} hint="From available report data" tone="green"/>
            <StatCard icon={AlertTriangle} label="Failed steps" value={String(metrics.failed)} hint="Requires review if non-zero" tone="orange"/>
            <StatCard icon={Gauge} label="Backend status" value={apiStatus === 'online' ? 'Online' : apiStatus === 'offline' ? 'Offline' : 'Checking'} hint="API documentation endpoint" tone="purple"/>
          </section>

          <section className="lower-grid">
            <div className="panel activity-panel"><div className="panel-heading"><div><h3>Recent activity</h3><p>Latest records returned by the API</p></div><button className="icon-button" onClick={() => setActive('Activity logs')} aria-label="View activity logs"><ArrowUpRight size={17}/></button></div>
              {filteredLogs.length ? <div className="activity-list">{filteredLogs.slice(0,5).map((item, i) => <ActivityRow key={item.id || item.execution_id || i} item={item}/>)}</div> : <EmptyState icon={History} title="Nothing to show yet" text={apiStatus === 'online' ? 'Runbook events will appear here when the backend has records.' : 'Connect the backend to load execution activity.'}/>}
              <button className="panel-footer-link" onClick={() => setActive('Activity logs')}>View activity log <ArrowRight size={14}/></button>
            </div>
            <div className="panel quick-panel"><div className="panel-heading"><div><h3>Quick actions</h3><p>Pick up where your work starts</p></div><Zap size={17} className="heading-accent"/></div>
              <button className="quick-action" onClick={() => { setActive('Runbooks'); setShowUpload(true); }}><div className="quick-icon blue"><UploadCloud size={18}/></div><div><strong>Upload a runbook</strong><small>Import a Markdown playbook</small></div><ArrowRight size={15}/></button>
              <button className="quick-action" onClick={() => setActive('Executions')}><div className="quick-icon purple"><Workflow size={18}/></div><div><strong>Monitor executions</strong><small>Review current run state</small></div><ArrowRight size={15}/></button>
              <button className="quick-action" onClick={() => setActive('Reports')}><div className="quick-icon green"><FileText size={18}/></div><div><strong>View reports</strong><small>Inspect available summaries</small></div><ArrowRight size={15}/></button>
              <div className="tip-card"><Sparkles size={15}/><p><strong>Built for safe operations.</strong> Review commands and approvals before high-impact actions.</p></div>
            </div>
          </section>
        </>}

        {active === 'Runbooks' && <section className="page-section"><PageHeading title="Runbook library" subtitle="Import and prepare operational playbooks for execution." action={<button className="primary-button" onClick={() => setShowUpload(v => !v)}><Plus size={16}/> Upload runbook</button>}/>{showUpload && <form className="upload-card" onSubmit={uploadRunbook}><div className="upload-drop"><UploadCloud size={26}/><strong>Bring your runbook</strong><span>Markdown files (.md) with numbered operational steps</span><input type="file" accept=".md,text/markdown,text/plain" onChange={e => setFile(e.target.files?.[0] || null)}/>{file && <div className="selected-file"><FileCode2 size={15}/>{file.name}<button type="button" onClick={() => setFile(null)} aria-label="Remove file"><X size={14}/></button></div>}</div><button className="primary-button" disabled={uploading || !file}>{uploading ? <LoaderCircle className="spin" size={16}/> : <UploadCloud size={16}/>} {uploading ? 'Uploading…' : 'Upload and validate'}</button>{uploadResult && <pre className="result-preview">{JSON.stringify(uploadResult, null, 2)}</pre>}</form>}<div className="panel library-empty"><EmptyState icon={BookOpen} title={uploaded ? 'Runbook uploaded' : 'Your runbook library starts here'} text={uploaded ? 'The backend accepted the upload. Review the server response and confirm parsing before execution.' : 'Upload a Markdown runbook to begin. Existing runbooks will appear here when the API exposes a listing endpoint.'}/>{uploaded && <button className="secondary-button" onClick={() => setNotice({type:'info',text:'The README documents /parse and /execute. Their exact request schemas are not exposed in this interface yet, so execution has not been started automatically.'})}>Review next steps</button>}</div></section>}

        {active === 'Executions' && <section className="page-section"><PageHeading title="Execution center" subtitle="Observe execution records and investigate failures." action={<button className="secondary-button" onClick={refreshData}><RefreshCw size={15}/> Refresh state</button>}/><div className="panel execution-intro"><div className="execution-icon"><Workflow size={23}/></div><div><h3>Workflow monitor</h3><p>This view uses the records available from your current backend. No execution is started automatically.</p><div className="workflow-steps">{['Runbook input','Validation','Approval gate','Execution','Results'].map((s,i)=><div className="workflow-step" key={s}><span>{String(i+1).padStart(2,'0')}</span><strong>{s}</strong>{i<4&&<ArrowRight size={13}/>}</div>)}</div></div></div><div className="panel"><div className="panel-heading"><div><h3>Execution records</h3><p>Derived from /logs and /report responses</p></div><span className="soft-tag">{logs.length} records</span></div><LogsTable logs={logs}/></div></section>}

        {active === 'Activity logs' && <section className="page-section"><PageHeading title="Activity logs" subtitle="Search and inspect operational events returned by the backend." action={<button className="secondary-button" onClick={refreshData}><RefreshCw size={15}/> Refresh</button>}/><div className="panel"><div className="table-toolbar"><div className="search-box"><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search activity records…"/></div><span className="soft-tag">{filteredLogs.length} shown</span></div><LogsTable logs={filteredLogs}/></div></section>}

        {active === 'Reports' && <section className="page-section"><PageHeading title="Reports & insights" subtitle="Review the backend's current summary and export the available PDF report." action={<button className="primary-button" onClick={downloadReport}><Download size={15}/> Export PDF</button>}/><div className="stats-grid"><StatCard icon={Activity} label="Reported activity" value={String(metrics.total)} hint="Backend summary" tone="blue"/><StatCard icon={CheckCircle2} label="Success count" value={String(metrics.success)} hint="Backend summary" tone="green"/><StatCard icon={AlertTriangle} label="Failure count" value={String(metrics.failed)} hint="Backend summary" tone="orange"/><StatCard icon={ShieldCheck} label="Safety posture" value="Approval-gated" hint="Product workflow principle" tone="purple"/></div><div className="panel report-panel"><div className="panel-heading"><div><h3>Raw report payload</h3><p>Showing the actual API response, when available</p></div><FileText size={18}/></div>{report ? <pre className="result-preview">{JSON.stringify(report,null,2)}</pre> : <EmptyState icon={FileText} title="No report data loaded" text="Refresh to request /report from the backend."/ >}</div></section>}

        {active === 'Settings' && <section className="page-section"><PageHeading title="Workspace settings" subtitle="Connection and safety configuration for this interface."/><div className="panel settings-list"><div className="setting-row"><div className="setting-icon"><Activity size={18}/></div><div><strong>Backend API</strong><p>{API_BASE || 'Relative URL (Vite proxy in local development)'}</p></div><span className={`soft-tag ${apiStatus}`}>{statusLabel}</span></div><div className="setting-row"><div className="setting-icon"><ShieldCheck size={18}/></div><div><strong>Execution safety</strong><p>Keep server-side allowlists and risky-command confirmation enabled.</p></div><span className="soft-tag">Protected</span></div><div className="setting-row"><div className="setting-icon"><Gauge size={18}/></div><div><strong>Reduced motion</strong><p>The 3D scene respects your device's reduced-motion preference.</p></div><span className="soft-tag">Automatic</span></div><div className="setting-row"><div className="setting-icon"><LifeBuoy size={18}/></div><div><strong>API documentation</strong><p>Inspect the backend's supported endpoints and request schemas.</p></div><a className="text-link" href={`${API_BASE}/docs`} target="_blank" rel="noreferrer">Open docs <ArrowUpRight size={13}/></a></div></div></section>}
        <footer className="footer"><span><span className="footer-mark"/> Runbook OS <span className="footer-divider">·</span> Safety-first operations</span><span>API-aware interface <span className="footer-divider">·</span> Build 1.0</span></footer>
      </div>
    </main>
  </div>;
}

function ActivityRow({ item }) {
  const raw = item.status || item.state || item.event || item.action || 'Activity record';
  const status = String(raw).toLowerCase();
  const ok = /success|complete|passed|done/.test(status);
  const bad = /fail|error|blocked|risk/.test(status);
  const label = String(item.message || item.command || item.description || item.step || item.event || raw);
  const time = item.timestamp || item.created_at || item.time || item.started_at || '';
  return <div className="activity-row"><div className={`activity-state ${ok ? 'ok' : bad ? 'bad' : 'neutral'}`}>{ok ? <Check size={14}/> : bad ? <AlertTriangle size={14}/> : <Terminal size={14}/>}</div><div className="activity-detail"><strong>{label.length > 66 ? label.slice(0,63)+'…' : label}</strong><small>{item.runbook || item.filename || item.execution_id || 'Execution event'}</small></div><div className="activity-meta"><span className={`status-text ${ok?'ok':bad?'bad':''}`}>{String(raw).replaceAll('_',' ')}</span><small>{time ? String(time).replace('T',' ').slice(0,16) : 'Time unavailable'}</small></div></div>;
}
function EmptyState({ icon: Icon, title, text }) { return <div className="empty-state"><div className="empty-icon"><Icon size={21}/></div><strong>{title}</strong><p>{text}</p></div>; }
function PageHeading({ title, subtitle, action }) { return <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> OPERATIONS WORKSPACE</div><h1>{title}</h1><p>{subtitle}</p></div>{action}</div>; }
function LogsTable({ logs }) {
  if (!logs?.length) return <EmptyState icon={History} title="No records found" text="The backend has not returned any log records for this view yet."/>;
  return <div className="logs-table-wrap"><table className="logs-table"><thead><tr><th>Event / step</th><th>Runbook / execution</th><th>Status</th><th>Timestamp</th></tr></thead><tbody>{logs.map((item,i)=>{const status=String(item.status||item.state||item.event||'Recorded');const lower=status.toLowerCase();const state=/success|complete|passed|done/.test(lower)?'success':/fail|error|blocked|risk/.test(lower)?'danger':'neutral';return <tr key={item.id||item.execution_id||i}><td><strong>{String(item.message||item.command||item.description||item.step||item.event||'Activity record')}</strong></td><td>{String(item.runbook||item.filename||item.execution_id||'—')}</td><td><span className={`table-status ${state}`}>{status.replaceAll('_',' ')}</span></td><td>{String(item.timestamp||item.created_at||item.time||'—').replace('T',' ').slice(0,19)}</td></tr>})}</tbody></table></div>;
}
export default App;