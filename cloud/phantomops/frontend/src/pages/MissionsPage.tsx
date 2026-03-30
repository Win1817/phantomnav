import React, { useState } from 'react';
import { Navigation, Plus, Play, Square, Trash2, MapPin } from 'lucide-react';
import { api } from '../utils/api';
import { useStore } from '../store';
import { Mission, Waypoint } from '../types';

const BLANK_WAYPOINT = (): Waypoint => ({ seq: 0, x: 0, y: 0, z: -10 });

export function MissionsPage() {
  const drones = useStore((s) => Object.keys(s.drones));
  const [droneId, setDroneId] = useState(drones[0] ?? 'drone-001');
  const [missionName, setMissionName] = useState('');
  const [waypoints, setWaypoints] = useState<Waypoint[]>([BLANK_WAYPOINT()]);
  const [maxSpeed, setMaxSpeed] = useState(5);
  const [returnHome, setReturnHome] = useState(true);
  const [status, setStatus] = useState<{ type: 'ok' | 'error' | 'info'; msg: string } | null>(null);
  const [activeMissionId, setActiveMissionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const addWaypoint = () => {
    setWaypoints(prev => [...prev, { ...BLANK_WAYPOINT(), seq: prev.length }]);
  };

  const removeWaypoint = (i: number) => {
    setWaypoints(prev => prev.filter((_, idx) => idx !== i).map((w, idx) => ({ ...w, seq: idx })));
  };

  const updateWaypoint = (i: number, field: keyof Waypoint, value: number | string) => {
    setWaypoints(prev => prev.map((w, idx) => idx === i ? { ...w, [field]: value } : w));
  };

  const handleCreate = async () => {
    if (!missionName.trim()) { setStatus({ type: 'error', msg: 'Mission name required' }); return; }
    if (waypoints.length === 0) { setStatus({ type: 'error', msg: 'At least one waypoint required' }); return; }
    setLoading(true);
    try {
      const mission: Mission = {
        drone_id: droneId,
        name: missionName,
        waypoints: waypoints.map((w, i) => ({ ...w, seq: i })),
        max_speed_ms: maxSpeed,
        return_home: returnHome,
        gnss_required: false,
      };
      const result = await api.createMission(mission);
      setActiveMissionId(result.id);
      setStatus({ type: 'ok', msg: `Mission created: ${result.id}` });
    } catch (e: unknown) {
      setStatus({ type: 'error', msg: e instanceof Error ? e.message : 'Create failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleActivate = async () => {
    if (!activeMissionId) return;
    setLoading(true);
    try {
      await api.activateMission(activeMissionId);
      setStatus({ type: 'ok', msg: `Mission ${activeMissionId} activated → sent to ${droneId}` });
    } catch (e: unknown) {
      setStatus({ type: 'error', msg: e instanceof Error ? e.message : 'Activate failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleAbort = async () => {
    if (!activeMissionId) return;
    setLoading(true);
    try {
      await api.abortMission(activeMissionId);
      setStatus({ type: 'ok', msg: `Mission ${activeMissionId} ABORTED` });
      setActiveMissionId(null);
    } catch (e: unknown) {
      setStatus({ type: 'error', msg: e instanceof Error ? e.message : 'Abort failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleRtl = async () => {
    setLoading(true);
    try {
      await api.sendCommand(droneId, { event: 'RTL', ts: Date.now() / 1000 });
      setStatus({ type: 'ok', msg: `RTL command sent to ${droneId}` });
    } catch (e: unknown) {
      setStatus({ type: 'error', msg: e instanceof Error ? e.message : 'Command failed' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>

      {/* ── Left: Mission builder ─────────────────────────── */}
      <div style={{
        width: 400,
        flexShrink: 0,
        borderRight: '1px solid var(--border-dim)',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--bg-base)',
        overflow: 'auto',
      }}>
        <div className="panel-header" style={{ padding: '12px 16px' }}>
          <Navigation size={13} color="var(--accent)" />
          MISSION BUILDER
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Drone selector */}
          <Field label="TARGET UAV">
            <select
              className="input"
              value={droneId}
              onChange={e => setDroneId(e.target.value)}
              style={{ background: 'var(--bg-void)' }}
            >
              {drones.length > 0 ? drones.map(id => (
                <option key={id} value={id}>{id}</option>
              )) : <option value="drone-001">drone-001</option>}
            </select>
          </Field>

          <Field label="MISSION NAME">
            <input
              className="input"
              value={missionName}
              onChange={e => setMissionName(e.target.value)}
              placeholder="e.g. PATROL-ALPHA-01"
            />
          </Field>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Field label="MAX SPEED (M/S)">
              <input
                className="input"
                type="number"
                value={maxSpeed}
                onChange={e => setMaxSpeed(Number(e.target.value))}
                min={0.5}
                max={20}
                step={0.5}
              />
            </Field>
            <Field label="RETURN HOME">
              <div style={{ display: 'flex', gap: 8, paddingTop: 6 }}>
                {[true, false].map(v => (
                  <button
                    key={String(v)}
                    onClick={() => setReturnHome(v)}
                    className={`btn ${returnHome === v ? 'btn-primary' : ''}`}
                    style={{ flex: 1, justifyContent: 'center', padding: '5px' }}
                  >
                    {v ? 'YES' : 'NO'}
                  </button>
                ))}
              </div>
            </Field>
          </div>

          {/* Waypoints */}
          <div>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 8,
            }}>
              <span style={{ fontFamily: 'var(--font-label)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>
                WAYPOINTS ({waypoints.length})
              </span>
              <button onClick={addWaypoint} className="btn" style={{ padding: '3px 8px', fontSize: 10 }}>
                <Plus size={10} /> ADD
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {waypoints.map((wp, i) => (
                <WaypointRow
                  key={i}
                  wp={wp}
                  index={i}
                  onChange={(f, v) => updateWaypoint(i, f, v)}
                  onRemove={() => removeWaypoint(i)}
                />
              ))}
            </div>
          </div>

          {/* Status message */}
          {status && (
            <div style={{
              padding: '8px 12px',
              borderRadius: 4,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              background: status.type === 'ok' ? 'var(--green-dim)' : status.type === 'error' ? 'var(--red-dim)' : 'var(--accent-dim)',
              border: `1px solid ${status.type === 'ok' ? 'var(--green)' : status.type === 'error' ? 'var(--red)' : 'var(--accent)'}50`,
              color: status.type === 'ok' ? 'var(--green)' : status.type === 'error' ? 'var(--red)' : 'var(--accent)',
            }}>
              {status.msg}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleCreate} disabled={loading} style={{ flex: 1, justifyContent: 'center' }}>
              <Plus size={12} /> CREATE
            </button>
            {activeMissionId && (
              <>
                <button className="btn btn-success" onClick={handleActivate} disabled={loading} style={{ flex: 1, justifyContent: 'center' }}>
                  <Play size={12} /> ACTIVATE
                </button>
                <button className="btn btn-danger" onClick={handleAbort} disabled={loading} style={{ flex: 1, justifyContent: 'center' }}>
                  <Square size={12} /> ABORT
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Right: Quick commands ─────────────────────────── */}
      <div style={{ flex: 1, padding: 20, overflow: 'auto' }}>
        <div className="panel-header" style={{ padding: '0 0 12px', border: 'none' }}>
          <Navigation size={13} color="var(--accent)" />
          QUICK COMMANDS — {droneId}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, maxWidth: 600 }}>
          {[
            { label: 'RETURN TO LAUNCH', color: 'var(--amber)', icon: <Navigation size={16} />, action: handleRtl },
            { label: 'EMERGENCY HOLD',   color: 'var(--red)',   icon: <Square size={16} />,
              action: () => api.sendCommand(droneId, { event: 'EMERGENCY_HOLD' }).then(() => setStatus({ type: 'ok', msg: 'HOLD command sent' })) },
            { label: 'SAFE MODE',        color: 'var(--amber)', icon: <Square size={16} />,
              action: () => api.sendCommand(droneId, { event: 'SAFE_MODE' }).then(() => setStatus({ type: 'ok', msg: 'SAFE MODE command sent' })) },
          ].map(({ label, color, icon, action }) => (
            <button
              key={label}
              className="btn"
              onClick={action}
              style={{
                padding: '18px 14px',
                flexDirection: 'column',
                gap: 10,
                height: 90,
                justifyContent: 'center',
                border: `1px solid ${color}40`,
                color,
              }}
            >
              {icon}
              <span style={{ fontSize: 10 }}>{label}</span>
            </button>
          ))}
        </div>

        {/* Waypoint visualizer */}
        {waypoints.length > 0 && (
          <div style={{ marginTop: 24 }}>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.1em', marginBottom: 12 }}>
              MISSION PROFILE — ALTITUDE VIEW
            </div>
            <WaypointViz waypoints={waypoints} />
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{
        display: 'block',
        fontFamily: 'var(--font-label)',
        fontSize: 9,
        color: 'var(--text-dim)',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        marginBottom: 5,
      }}>{label}</label>
      {children}
    </div>
  );
}

function WaypointRow({ wp, index, onChange, onRemove }: {
  wp: Waypoint; index: number;
  onChange: (f: keyof Waypoint, v: number) => void;
  onRemove: () => void;
}) {
  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: '1px solid var(--border-dim)',
      borderRadius: 4,
      padding: '8px 10px',
      display: 'flex',
      alignItems: 'center',
      gap: 6,
    }}>
      <div style={{
        width: 20,
        height: 20,
        borderRadius: '50%',
        background: 'var(--accent-dim)',
        border: '1px solid var(--accent)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        color: 'var(--accent)',
        flexShrink: 0,
      }}>{index + 1}</div>

      {(['x','y','z'] as const).map(ax => (
        <div key={ax} style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--text-dim)', marginBottom: 2, letterSpacing: '0.1em' }}>{ax.toUpperCase()}</div>
          <input
            type="number"
            value={wp[ax]}
            onChange={e => onChange(ax, Number(e.target.value))}
            step={1}
            style={{
              background: 'var(--bg-void)',
              border: '1px solid var(--border-dim)',
              borderRadius: 3,
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              padding: '3px 5px',
              width: '100%',
              outline: 'none',
            }}
          />
        </div>
      ))}

      <button
        onClick={onRemove}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', padding: 2 }}
        onMouseEnter={e => (e.currentTarget.style.color = 'var(--red)')}
        onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-dim)')}
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}

function WaypointViz({ waypoints }: { waypoints: Waypoint[] }) {
  const maxAlt = Math.max(...waypoints.map(w => Math.abs(w.z)), 1);
  const w = 500, h = 100;
  const xStep = waypoints.length > 1 ? w / (waypoints.length - 1) : w / 2;

  const pts = waypoints.map((wp, i) => ({
    x: i === 0 ? 0 : i * xStep,
    y: h - (Math.abs(wp.z) / maxAlt) * (h - 10) - 5,
  }));

  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h + 20}`} style={{ maxWidth: 550 }}>
      {/* Ground line */}
      <line x1="0" y1={h} x2={w} y2={h} stroke="rgba(255,255,255,0.1)" strokeDasharray="4 4" />

      {/* Path */}
      {pts.length > 1 && (
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth={1.5} strokeDasharray="6 3" opacity={0.7} />
      )}

      {/* Waypoints */}
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={4} fill="var(--accent)" />
          <text x={p.x} y={h + 14} textAnchor="middle" fill="var(--text-dim)"
            fontFamily="var(--font-mono)" fontSize={8}>{i + 1}</text>
          <text x={p.x} y={p.y - 8} textAnchor="middle" fill="var(--accent)"
            fontFamily="var(--font-mono)" fontSize={8}>{waypoints[i].z}m</text>
        </g>
      ))}
    </svg>
  );
}
