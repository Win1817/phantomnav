import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, CartesianGrid
} from 'recharts';
import { ArrowLeft, Activity, Navigation, Satellite, Zap, Wind } from 'lucide-react';
import { useStore } from '../store';
import { confidenceColor, navModeLabel, navModeColor, formatTs, formatAge } from '../utils/format';
import { ConfidenceData } from '../types';

export function DronePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const drone_id = id ?? '';

  const { drone, confHistory } = useStore((s) => ({
    drone:       s.drones[drone_id],
    confHistory: s.confidenceHistory[drone_id] ?? [],
  }));

  const conf = drone?.confidence ?? 0;
  const tel = drone?.telemetry;

  // Chart data — last 120 points
  const chartData = confHistory.slice(-120).map((c: ConfidenceData) => ({
    t:    formatTs(c.ts),
    conf: Math.round(c.score),
    imu:  Math.round((c.sub_scores?.imu_stability ?? 0) * 100),
    slam: Math.round((c.sub_scores?.slam_quality ?? 0) * 100),
  }));

  if (!drone_id) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* ── Top bar ──────────────────────────────────────────── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 20px',
        borderBottom: '1px solid var(--border-dim)',
        background: 'var(--bg-base)',
        flexShrink: 0,
      }}>
        <button
          onClick={() => navigate('/')}
          className="btn"
          style={{ padding: '5px 10px' }}
        >
          <ArrowLeft size={13} /> FLEET
        </button>

        <div style={{ width: 1, height: 20, background: 'var(--border-dim)' }} />

        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 16,
          fontWeight: 500,
          color: 'var(--text-primary)',
        }}>{drone_id}</div>

        {drone?.nav_mode && (
          <span className="badge" style={{
            background: `${navModeColor(drone.nav_mode)}18`,
            border: `1px solid ${navModeColor(drone.nav_mode)}50`,
            color: navModeColor(drone.nav_mode),
          }}>
            {navModeLabel(drone.nav_mode)}
          </span>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          {drone?.gnss_valid !== undefined && (
            <span className="badge" style={{
              background: drone.gnss_valid ? 'var(--green-dim)' : 'var(--amber-dim)',
              border: `1px solid ${drone.gnss_valid ? 'var(--green)' : 'var(--amber)'}50`,
              color: drone.gnss_valid ? 'var(--green)' : 'var(--amber)',
            }}>
              <Satellite size={9} />
              {drone.gnss_valid ? 'GNSS LOCK' : 'NO GNSS'}
            </span>
          )}
          {drone?.last_seen && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
              {formatAge(drone.last_seen)}
            </span>
          )}
        </div>
      </div>

      {/* ── Body ─────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>

        {/* Row 1: KPI cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          <KpiCard
            icon={<Activity size={14} />}
            label="CONFIDENCE"
            value={conf.toFixed(1)}
            unit="%"
            color={confidenceColor(conf)}
            subtext={drone?.conf_level ?? ''}
          />
          <KpiCard
            icon={<Navigation size={14} />}
            label="NAV MODE"
            value={drone?.nav_mode ? navModeLabel(drone.nav_mode) : '—'}
            color={drone?.nav_mode ? navModeColor(drone.nav_mode) : 'var(--text-dim)'}
          />
          <KpiCard
            icon={<Wind size={14} />}
            label="DRIFT"
            value={tel?.fusion?.drift_m?.toFixed(2) ?? '—'}
            unit="m"
            color="var(--blue)"
          />
          <KpiCard
            icon={<Zap size={14} />}
            label="SLAM WEIGHT"
            value={tel?.fusion?.w_slam !== undefined ? (tel.fusion.w_slam * 100).toFixed(0) : '—'}
            unit="%"
            color="var(--purple)"
          />
        </div>

        {/* Row 2: Confidence gauge + chart */}
        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 12 }}>
          {/* Gauge */}
          <div className="panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <div className="panel-header" style={{ padding: 0, border: 'none', fontSize: 10 }}>
              <Activity size={11} color="var(--accent)" /> CONFIDENCE SCORE
            </div>
            <ConfidenceGauge score={conf} />
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 36,
              fontWeight: 500,
              color: confidenceColor(conf),
              lineHeight: 1,
            }}>{conf.toFixed(0)}</div>
            <div style={{
              fontFamily: 'var(--font-label)',
              fontSize: 11,
              color: confidenceColor(conf),
              letterSpacing: '0.1em',
            }}>{drone?.conf_level ?? 'UNKNOWN'}</div>
          </div>

          {/* Chart */}
          <div className="panel">
            <div className="panel-header">
              <Activity size={11} color="var(--accent)" /> CONFIDENCE HISTORY
              <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 9 }}>
                {chartData.length} samples
              </span>
            </div>
            <div style={{ padding: '12px 8px 8px', height: 180 }}>
              {chartData.length > 1 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                    <XAxis dataKey="t" tick={{ fontFamily: 'var(--font-mono)', fontSize: 8, fill: 'var(--text-dim)' }} interval="preserveStartEnd" />
                    <YAxis domain={[0, 100]} tick={{ fontFamily: 'var(--font-mono)', fontSize: 8, fill: 'var(--text-dim)' }} width={28} />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-mid)', fontFamily: 'var(--font-mono)', fontSize: 11 }}
                      labelStyle={{ color: 'var(--text-dim)' }}
                    />
                    <ReferenceLine y={70} stroke="var(--green)" strokeDasharray="3 3" strokeOpacity={0.4} />
                    <ReferenceLine y={40} stroke="var(--amber)" strokeDasharray="3 3" strokeOpacity={0.4} />
                    <ReferenceLine y={20} stroke="var(--red)" strokeDasharray="3 3" strokeOpacity={0.4} />
                    <Line type="monotone" dataKey="conf" stroke="var(--accent)" strokeWidth={1.5} dot={false} name="Overall" />
                    <Line type="monotone" dataKey="imu"  stroke="var(--green)" strokeWidth={1} dot={false} strokeOpacity={0.6} name="IMU Stab" />
                    <Line type="monotone" dataKey="slam" stroke="var(--purple)" strokeWidth={1} dot={false} strokeOpacity={0.6} name="SLAM" />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                  AWAITING TELEMETRY...
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Row 3: Position + fusion state */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>

          {/* Position */}
          <div className="panel">
            <div className="panel-header"><Navigation size={11} color="var(--accent)" /> POSITION (NED)</div>
            <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              {(['x','y','z'] as const).map(axis => (
                <div key={axis}>
                  <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.1em', marginBottom: 4 }}>
                    {axis.toUpperCase()} — {axis === 'x' ? 'NORTH' : axis === 'y' ? 'EAST' : 'DOWN'}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, color: 'var(--text-primary)' }}>
                    {tel?.pose?.[axis]?.toFixed(2) ?? '—'}
                    <span style={{ fontSize: 10, color: 'var(--text-dim)', marginLeft: 3 }}>m</span>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ padding: '0 14px 14px', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              {(['vx','vy','vz'] as const).map(v => (
                <div key={v}>
                  <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.1em', marginBottom: 2 }}>{v.toUpperCase()}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--blue)' }}>
                    {tel?.velocity?.[v]?.toFixed(2) ?? '—'}
                    <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 2 }}>m/s</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Fusion state */}
          <div className="panel">
            <div className="panel-header"><Zap size={11} color="var(--accent)" /> FUSION STATE</div>
            <div style={{ padding: 14 }}>
              {tel?.fusion ? (
                <>
                  <FusionWeightBar wIns={tel.fusion.w_ins} wSlam={tel.fusion.w_slam} />
                  <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <Metric label="INS WEIGHT"  value={`${(tel.fusion.w_ins * 100).toFixed(0)}%`}  color="var(--blue)" />
                    <Metric label="SLAM WEIGHT" value={`${(tel.fusion.w_slam * 100).toFixed(0)}%`} color="var(--purple)" />
                    <Metric label="DRIFT EST."  value={`${tel.fusion.drift_m?.toFixed(2) ?? '—'} m`} color="var(--amber)" />
                    <Metric label="GNSS VALID"  value={tel.gnss_valid ? 'YES' : 'NO'} color={tel.gnss_valid ? 'var(--green)' : 'var(--red)'} />
                  </div>
                </>
              ) : (
                <div style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11, padding: '20px 0', textAlign: 'center' }}>
                  NO FUSION DATA
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Row 4: Sub-scores */}
        {confHistory.length > 0 && (
          <SubScorePanel latest={confHistory[confHistory.length - 1]} />
        )}
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, unit, color, subtext }: {
  icon: React.ReactNode; label: string; value: string;
  unit?: string; color: string; subtext?: string;
}) {
  return (
    <div className="panel" style={{ padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
        <span style={{ color: 'var(--text-dim)' }}>{icon}</span>
        <span style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>{label}</span>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 500, color, lineHeight: 1 }}>
        {value}
        {unit && <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 3 }}>{unit}</span>}
      </div>
      {subtext && <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color, letterSpacing: '0.1em', marginTop: 4 }}>{subtext}</div>}
    </div>
  );
}

function ConfidenceGauge({ score }: { score: number }) {
  const size = 120;
  const strokeWidth = 8;
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const arc = circ * 0.75;
  const offset = arc - (arc * Math.min(score, 100)) / 100;
  const color = confidenceColor(score);

  return (
    <svg width={size} height={size * 0.8} viewBox={`0 0 ${size} ${size}`} style={{ overflow: 'visible' }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--bg-elevated)" strokeWidth={strokeWidth}
        strokeDasharray={`${arc} ${circ - arc}`} strokeDashoffset={circ * 0.125}
        strokeLinecap="round" transform={`rotate(135 ${size/2} ${size/2})`} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
        strokeDasharray={`${arc - offset} ${circ - (arc - offset)}`} strokeDashoffset={circ * 0.125}
        strokeLinecap="round" transform={`rotate(135 ${size/2} ${size/2})`}
        style={{ transition: 'stroke-dasharray 0.5s ease', filter: `drop-shadow(0 0 6px ${color})` }} />
    </svg>
  );
}

function FusionWeightBar({ wIns, wSlam }: { wIns: number; wSlam: number }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--blue)', letterSpacing: '0.1em' }}>INS</span>
        <span style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--purple)', letterSpacing: '0.1em' }}>SLAM</span>
      </div>
      <div style={{ height: 6, background: 'var(--bg-elevated)', borderRadius: 3, overflow: 'hidden', display: 'flex' }}>
        <div style={{ width: `${wIns * 100}%`, background: 'var(--blue)', transition: 'width 0.5s' }} />
        <div style={{ width: `${wSlam * 100}%`, background: 'var(--purple)', transition: 'width 0.5s' }} />
      </div>
    </div>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.1em', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color }}>{value}</div>
    </div>
  );
}

function SubScorePanel({ latest }: { latest: ConfidenceData }) {
  const scores = [
    { label: 'IMU STABILITY', value: latest.sub_scores?.imu_stability ?? 0, color: 'var(--green)' },
    { label: 'SLAM QUALITY',  value: latest.sub_scores?.slam_quality ?? 0,  color: 'var(--purple)' },
    { label: 'DRIFT PENALTY', value: latest.sub_scores?.drift_penalty ?? 0, color: 'var(--amber)' },
    { label: 'GNSS FACTOR',   value: latest.sub_scores?.gnss_factor ?? 0,   color: 'var(--blue)' },
  ];

  return (
    <div className="panel">
      <div className="panel-header"><Activity size={11} color="var(--accent)" /> CONFIDENCE SUB-SCORES</div>
      <div style={{ padding: 14, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {scores.map(({ label, value, color }) => (
          <div key={label}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>{label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color }}>{(value * 100).toFixed(0)}</span>
            </div>
            <div style={{ height: 4, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${value * 100}%`, background: color, transition: 'width 0.5s', borderRadius: 2 }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
