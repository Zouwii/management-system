import { useState } from 'react';

function todayStr() {
  const d = new Date();
  return fmtDate(d);
}

function yesterdayStr() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return fmtDate(d);
}

function fmtDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

const quickBtnStyle = {
  padding: '4px 8px',
  background: '#334155', color: '#e2e8f0',
  border: '1px solid #475569', borderRadius: 6,
  fontSize: 11, cursor: 'pointer', whiteSpace: 'nowrap',
};

export default function ApiMonitorBadge() {
  const [stats, setStats] = useState(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const [day, setDay] = useState(todayStr());

  const fetchStats = async (d) => {
    setError('');
    try {
      const url = '/api/bt/monitor/api-stats' + (d ? '?day=' + d : '');
      const resp = await fetch(url);
      const json = await resp.json();
      if (json.code === 200) {
        setStats(json.data);
      } else {
        setError(json.error || 'fetch failed');
      }
    } catch (e) {
      setError('unreachable');
    }
  };

  const handleToggle = () => {
    const willOpen = !open;
    setOpen(willOpen);
    if (willOpen) {
      fetchStats(day);
    }
  };

  const handleDayChange = (d) => {
    setDay(d);
    fetchStats(d);
  };

  const total = stats?.total_calls || 0;
  const errors = stats?.total_errors || 0;
  const disabled = stats?.disabled || false;

  return (
    <div style={{ position: 'fixed', bottom: 0, left: 0, zIndex: 9998 }}>
      {open && (
        <div style={{
          position: 'absolute', bottom: '100%', left: 0,
          width: 340, maxHeight: 500, overflow: 'auto',
          background: '#1e293b', borderRadius: '12px 12px 0 0',
          boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
          border: '1px solid #334155',
          padding: 14, marginBottom: 0, marginLeft: 0,
          color: '#e2e8f0', fontSize: 12,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontWeight: 700, fontSize: 14 }}>📡 API Monitor</span>
            <button onClick={() => setOpen(false)}
              style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 16 }}>
              ✕
            </button>
          </div>
          <div style={{ marginBottom: 8, display: 'flex', gap: 6, alignItems: 'center' }}>
            <button onClick={() => handleDayChange(yesterdayStr())}
              style={quickBtnStyle}>
              ◀ 前一天
            </button>
            <input
              type="date"
              value={day}
              onChange={(e) => handleDayChange(e.target.value)}
              max={todayStr()}
              style={{
                flex: 1, padding: '4px 6px',
                background: '#0f172a', color: '#e2e8f0',
                border: '1px solid #4ade80', borderRadius: 6,
                fontSize: 12, cursor: 'pointer',
                colorScheme: 'dark',
              }}
            />
            <button onClick={() => handleDayChange(todayStr())}
              style={quickBtnStyle}>
              今天
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6, marginBottom: 10 }}>
            <StatBox label="Today" value={stats?.day || '-'} />
            <StatBox label="Calls" value={total} color={errors > 0 ? '#f87171' : '#4ade80'} />
            <StatBox label="Errors" value={`${stats?.error_rate_pct || 0}%`} color={errors > 0 ? '#f87171' : '#94a3b8'} />
          </div>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>
            Uptime: {stats?.uptime || '-'} &nbsp;|&nbsp; Sync: {disabled ? '🔴 OFF' : '🟢 ON'}
          </div>
          {stats?.all_endpoints && Object.keys(stats.all_endpoints).length > 0 && (
            <>
              <div style={{ fontWeight: 600, marginBottom: 4, color: '#94a3b8' }}>
                Endpoints ({Object.keys(stats.all_endpoints).length})
              </div>
              {Object.entries(stats.all_endpoints).map(([ep, s]) => (
                <div key={ep} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '3px 0', borderBottom: '1px solid #1e293b',
                }}>
                  <code style={{ fontSize: 10, color: '#7dd3fc', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {ep}
                  </code>
                  <span style={{ display: 'flex', gap: 8, fontSize: 11 }}>
                    <span style={{ color: '#e2e8f0' }}>{s.calls}</span>
                    {s.errors > 0 && <span style={{ color: '#f87171' }}>{s.errors}✗</span>}
                    <span style={{ color: '#64748b' }}>{s.avg_latency_ms}ms</span>
                  </span>
                </div>
              ))}
            </>
          )}
          {stats?.recent && stats.recent.length > 0 && (
            <>
              <div style={{ fontWeight: 600, marginBottom: 4, marginTop: 8, color: '#94a3b8' }}>Recent</div>
              {stats.recent.slice(0, 10).map((r, i) => (
                <div key={i} style={{
                  display: 'flex', gap: 6, padding: '1px 0',
                  fontSize: 10, fontFamily: 'monospace',
                }}>
                  <span style={{ color: r.status >= 400 ? '#f87171' : '#4ade80', minWidth: 28 }}>
                    {r.status}
                  </span>
                  <code style={{ color: '#7dd3fc', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {r.endpoint}
                  </code>
                  <span style={{ color: '#64748b' }}>{r.latency_ms}ms</span>
                </div>
              ))}
            </>
          )}
          {error && <div style={{ color: '#f87171', marginTop: 8 }}>⚠ {error}</div>}
          <button onClick={fetchStats}
            style={{
              marginTop: 8, width: '100%', padding: '4px 0',
              background: '#334155', border: 'none', borderRadius: 6,
              color: '#94a3b8', fontSize: 11, cursor: 'pointer',
            }}>
            🔄 Refresh
          </button>
        </div>
      )}
      <button
        onClick={handleToggle}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: 36, height: 36,
          border: 'none',
          background: 'transparent',
          color: '#cbd5e1', fontSize: 18, cursor: 'pointer',
          opacity: 0.5,
          transition: 'opacity 0.2s',
        }}
        title={`📡 DingTalk API — ${total} calls today`}
      >
        <span style={{ lineHeight: 1 }}>📡</span>
      </button>
    </div>
  );
}

function StatBox({ label, value, color = '#e2e8f0' }) {
  return (
    <div style={{
      background: '#0f172a', borderRadius: 8, padding: '6px 8px', textAlign: 'center',
    }}>
      <div style={{ fontSize: 10, color: '#64748b' }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}
