import React, { useEffect, useState } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine
} from 'recharts';
import { BarChart2, TrendingDown, Satellite, RefreshCw } from 'lucide-react';
import { api } from '../utils/api';
import { useStore } from '../store';
import { formatTs } from '../utils/format';

export function AnalyticsPage() {
  const drones = useStore((s) => Object.keys(s.drones));
  const [droneId, setDroneId] = useState(drones[0] ?? 'drone-001');
  const [windowH, setWindowH] = useState(1);
  const [driftData, setDriftData] = useState<Record<string, unknown> | null>(null);
  const [trendData, setTrendData] = useState<Record<string, unknown> | null>(null);
  const [gnssEvents, setGnssEvents] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(false);

  const fetch = async () => {
    setLoading(true);
    try {
      const [drift, trend, gnss] = await Promise.all([
        api.getDriftSummary(droneId, windowH * 3600),
        api.getConfidenceTrend(droneId, windowH * 3600, 60),
        api.getGnssEvents(droneId),
      ]);
      setDriftData(drift as Record<string, unknown>);
      setTrendData(trend as Record<string, unknown>);
      const evts = gnss as { events?: unknown[] };
      setGnssEvents(evts?.events ?? []);
    } catch {
      // Service may not have data yet
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetch(); }, [droneId, windowH]);

  const trendBuckets = ((trendData as { trend_buckets?: Array<{ t_start: number; mean: number; min: number }> })?.trend_buckets ?? [])
    .map((b) => ({
      t:    formatTs(b.t_start),
      mean: b.mean,
      min:  b.min,
    }));

  const driftStats = (driftData as { drift_m?: { mean: number; std: number; max: number; p95: number } } | null)?.drift_m;
  const sampleCount = (driftData as { sample_count?: number } | null)?.sample_count ?? 0;
  const driftRate = (driftData as { drift_rate_m_per_s?: number } | null)?.drift_rate_m_per_s ?? 0;
  const gnssLoss = (driftData as { gnss_loss_segments?: number } | null)?.gnss_loss_segments ?? 0;
  const overallConf = (trendData as { overall?: { mean: number; min: number; p5: number } } | null)?.overall;
  const levelDist = (trendData as { level_distribution?: Record<string, number> } | null)?.level_distribution ?? {};
  const degEvents = (trendData as { degradation_events?: number } | null)?.degradation_events ?? 0;

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: 20 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <BarChart2 size={16} color="var(--accent)" />
        <span style={{ fontFamily: 'var(--font-label)', fontSize: 14, fontWeight: 600, letterSpacing: '0.1em' }}>
          ANALYTICS
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* Drone selector */}
          <select
            className="input"
            value={droneId}
            onChange={e => setDroneId(e.target.value)}
            style={{ width: 140, background: 'var(--bg-panel)' }}
          >
            {drones.length > 0 ? drones.map(id => <option key={id} value={id}>{id}</option>)
              : <option value="drone-001">drone-001</option>}
          </select>

          {/* Window selector */}
          {[1, 6, 24].map(h => (
            <button
              key={h}
              onClick={() => setWindowH(h)}
              className={`btn ${windowH === h ? 'btn-primary' : ''}`}
              style={{ padding: '5px 10px', fontSize: 10 }}
            >
              {h}H
            </button>
          ))}

          <button className="btn" onClick={fetch} disabled={loading} style={{ padding: '5px 10px' }}>
            <RefreshCw size={11} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          </button>
        </div>
      </div>

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 16 }}>
        {[
          { label: 'SAMPLES',    value: sampleCount.toString(),         color: 'var(--text-primary)' },
          { label: 'MEAN DRIFT', value: driftStats ? `${driftStats.mean.toFixed(2)}m` : '—', color: 'var(--blue)' },
          { label: 'MAX DRIFT',  value: driftStats ? `${driftStats.max.toFixed(2)}m`  : '—', color: 'var(--amber)' },
          { label: 'DRIFT RATE', value: `${(driftRate * 100).toFixed(1)} cm/s`, color: 'var(--amber)' },
          { label: 'GNSS LOSS',  value: `${gnssLoss} segs`,             color: gnssLoss > 0 ? 'var(--red)' : 'var(--green)' },
        ].map(({ label, value, color }) => (
          <div key={label} className="panel" style={{ padding: '12px 14px' }}>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.1em', marginBottom: 6 }}>{label}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, color }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>

        {/* Confidence trend */}
        <div className="panel">
          <div className="panel-header"><BarChart2 size={11} color="var(--accent)" /> CONFIDENCE TREND</div>
          <div style={{ padding: '10px 8px 8px', height: 220 }}>
            {trendBuckets.length > 1 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendBuckets}>
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                  <XAxis dataKey="t" tick={{ fontFamily: 'var(--font-mono)', fontSize: 8, fill: 'var(--text-dim)' }} interval="preserveStartEnd" />
                  <YAxis domain={[0, 100]} tick={{ fontFamily: 'var(--font-mono)', fontSize: 8, fill: 'var(--text-dim)' }} width={28} />
                  <Tooltip contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-mid)', fontFamily: 'var(--font-mono)', fontSize: 11 }} />
                  <ReferenceLine y={70} stroke="var(--green)" strokeDasharray="3 3" strokeOpacity={0.3} />
                  <ReferenceLine y={40} stroke="var(--amber)" strokeDasharray="3 3" strokeOpacity={0.3} />
                  <Line type="monotone" dataKey="mean" stroke="var(--accent)" strokeWidth={1.5} dot={false} name="Mean" />
                  <Line type="monotone" dataKey="min"  stroke="var(--red)"   strokeWidth={1}   dot={false} name="Min" strokeOpacity={0.7} />
                </LineChart>
              </ResponsiveContainer>
            ) : <NoData />}
          </div>
        </div>

        {/* Level distribution */}
        <div className="panel">
          <div className="panel-header"><TrendingDown size={11} color="var(--accent)" /> CONFIDENCE LEVEL DISTRIBUTION</div>
          <div style={{ padding: '14px', height: 220 }}>
            {Object.keys(levelDist).length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 10 }}>
                {[
                  { level: 'NOMINAL',  color: 'var(--green)' },
                  { level: 'DEGRADED', color: 'var(--amber)' },
                  { level: 'CRITICAL', color: 'var(--red)' },
                  { level: 'UNSAFE',   color: 'var(--crimson)' },
                ].map(({ level, color }) => {
                  const count = levelDist[level] ?? 0;
                  const total = Object.values(levelDist).reduce((a: number, b) => a + (b as number), 0);
                  const pct = total > 0 ? (count as number / total) * 100 : 0;
                  return (
                    <div key={level}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontFamily: 'var(--font-label)', fontSize: 10, color, letterSpacing: '0.1em' }}>{level}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>{pct.toFixed(1)}%</span>
                      </div>
                      <div style={{ height: 6, background: 'var(--bg-elevated)', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width 0.5s' }} />
                      </div>
                    </div>
                  );
                })}
                {overallConf && (
                  <div style={{ marginTop: 10, padding: '10px', background: 'var(--bg-elevated)', borderRadius: 4, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                    <Stat label="MEAN" value={overallConf.mean.toFixed(1)} />
                    <Stat label="MIN"  value={overallConf.min.toFixed(1)} />
                    <Stat label="P5"   value={overallConf.p5.toFixed(1)} />
                  </div>
                )}
              </div>
            ) : <NoData />}
          </div>
        </div>
      </div>

      {/* GNSS events */}
      <div className="panel">
        <div className="panel-header">
          <Satellite size={11} color="var(--accent)" />
          GNSS EVENT LOG
          <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 9 }}>
            {gnssEvents.length} events
          </span>
          {degEvents > 0 && (
            <span className="badge" style={{ background: 'var(--red-dim)', border: '1px solid var(--red)', color: 'var(--red)', marginLeft: 6 }}>
              {degEvents} DROPS
            </span>
          )}
        </div>
        <div style={{ maxHeight: 200, overflowY: 'auto' }}>
          {gnssEvents.length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              NO GNSS EVENTS RECORDED
            </div>
          ) : (
            gnssEvents.map((evt: unknown, i) => {
              const e = evt as { ts?: number; code?: string; message?: string; confidence_at?: number };
              const isLost = e.code === 'GNSS_LOST';
              return (
                <div key={i} style={{
                  padding: '8px 16px',
                  borderBottom: '1px solid var(--border-dim)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  animation: 'fade-in 0.3s ease',
                }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', flexShrink: 0 }}>
                    {e.ts ? formatTs(e.ts) : '—'}
                  </span>
                  <span className="badge" style={{
                    background: isLost ? 'var(--red-dim)' : 'var(--green-dim)',
                    border: `1px solid ${isLost ? 'var(--red)' : 'var(--green)'}50`,
                    color: isLost ? 'var(--red)' : 'var(--green)',
                  }}>{e.code}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {e.message}
                  </span>
                  {e.confidence_at !== undefined && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', flexShrink: 0 }}>
                      conf: {e.confidence_at.toFixed(0)}
                    </span>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.1em', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}

function NoData() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
      NO DATA FOR WINDOW
    </div>
  );
}
