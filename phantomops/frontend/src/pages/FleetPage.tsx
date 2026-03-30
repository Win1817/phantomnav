import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import { api } from '../utils/api';
import { DroneState } from '../types';
import { confidenceColor, statusColor, navModeLabel, navModeColor, formatAge } from '../utils/format';
import { MapPin, Signal, Crosshair, ChevronRight, RefreshCw } from 'lucide-react';

export function FleetPage() {
  const navigate = useNavigate();
  const { drones, setSelectedDrone } = useStore((s) => ({
    drones: s.drones,
    setSelectedDrone: s.setSelectedDrone,
  }));
  const [loading, setLoading] = useState(false);

  // Initial fleet load
  useEffect(() => {
    setLoading(true);
    api.getFleetSummary()
      .then((data: unknown) => {
        const summary = data as { drones: DroneState[] };
        if (summary?.drones) {
          summary.drones.forEach(d => useStore.getState().upsertDrone(d));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const droneList = Object.values(drones);
  const counts = {
    active:   droneList.filter(d => d.status === 'active').length,
    warning:  droneList.filter(d => d.status === 'warning').length,
    critical: droneList.filter(d => d.status === 'critical').length,
    offline:  droneList.filter(d => d.status === 'offline').length,
  };

  const handleSelect = (drone: DroneState) => {
    setSelectedDrone(drone.drone_id);
    navigate(`/drone/${drone.drone_id}`);
  };

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>

      {/* ── Left panel: drone list ─────────────────────────── */}
      <div style={{
        width: 320,
        flexShrink: 0,
        borderRight: '1px solid var(--border-dim)',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--bg-base)',
      }}>
        {/* Header */}
        <div className="panel-header" style={{ padding: '12px 16px' }}>
          <Crosshair size={13} color="var(--accent)" />
          FLEET STATUS
          <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 10 }}>
            {droneList.length} UAVs
          </span>
          {loading && <RefreshCw size={11} style={{ animation: 'spin 1s linear infinite', marginLeft: 4 }} />}
        </div>

        {/* Summary chips */}
        <div style={{
          display: 'flex',
          gap: 6,
          padding: '10px 14px',
          borderBottom: '1px solid var(--border-dim)',
        }}>
          {([
            ['ACTIVE',   counts.active,   'var(--green)'],
            ['WARN',     counts.warning,  'var(--amber)'],
            ['CRITICAL', counts.critical, 'var(--red)'],
            ['OFFLINE',  counts.offline,  'var(--text-dim)'],
          ] as [string, number, string][]).map(([label, count, color]) => (
            <div key={label} style={{
              flex: 1,
              textAlign: 'center',
              padding: '6px 4px',
              background: 'var(--bg-panel)',
              border: '1px solid var(--border-dim)',
              borderRadius: 4,
            }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 500, color }}>{count}</div>
              <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>{label}</div>
            </div>
          ))}
        </div>

        {/* Drone cards */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {droneList.length === 0 ? (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: 200,
              color: 'var(--text-dim)',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              gap: 8,
            }}>
              <Signal size={24} style={{ opacity: 0.3 }} />
              <span>NO UAVs DETECTED</span>
              <span style={{ fontSize: 9 }}>AWAITING MQTT TELEMETRY</span>
            </div>
          ) : (
            droneList.map(drone => (
              <DroneCard key={drone.drone_id} drone={drone} onClick={() => handleSelect(drone)} />
            ))
          )}
        </div>
      </div>

      {/* ── Right panel: map placeholder / grid view ─────────── */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden', background: 'var(--bg-void)' }}>
        <MapView drones={droneList} onSelect={handleSelect} />
      </div>
    </div>
  );
}

function DroneCard({ drone, onClick }: { drone: DroneState; onClick: () => void }) {
  const color = statusColor(drone.status);
  const conf = drone.confidence ?? 0;

  return (
    <div
      onClick={onClick}
      style={{
        padding: '12px 16px',
        borderBottom: '1px solid var(--border-dim)',
        cursor: 'pointer',
        transition: 'background 0.1s',
        position: 'relative',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
    >
      {/* Left accent bar */}
      <div style={{
        position: 'absolute',
        left: 0, top: 0, bottom: 0,
        width: 2,
        background: color,
      }} />

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        {/* Status dot */}
        <div
          className={`status-dot ${drone.status === 'active' ? 'live' : ''}`}
          style={{ background: color, marginTop: 5 }}
        />

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              fontWeight: 500,
              color: 'var(--text-primary)',
            }}>{drone.drone_id}</span>
            <ChevronRight size={13} color="var(--text-dim)" />
          </div>

          {/* Nav mode */}
          {drone.nav_mode && (
            <div style={{
              fontFamily: 'var(--font-label)',
              fontSize: 10,
              color: navModeColor(drone.nav_mode),
              letterSpacing: '0.08em',
              marginTop: 2,
            }}>{navModeLabel(drone.nav_mode)}</div>
          )}

          {/* Confidence bar */}
          <div style={{ marginTop: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
              <span style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>CONFIDENCE</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: confidenceColor(conf) }}>
                {conf.toFixed(0)}
              </span>
            </div>
            <div style={{
              height: 3,
              background: 'var(--bg-elevated)',
              borderRadius: 2,
              overflow: 'hidden',
            }}>
              <div style={{
                height: '100%',
                width: `${Math.min(conf, 100)}%`,
                background: confidenceColor(conf),
                borderRadius: 2,
                transition: 'width 0.5s ease, background 0.3s',
              }} />
            </div>
          </div>

          {/* Last seen */}
          <div style={{
            marginTop: 6,
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--text-dim)',
          }}>
            {drone.last_seen ? formatAge(drone.last_seen) : '—'}
            {drone.gnss_valid !== undefined && (
              <span style={{
                marginLeft: 8,
                color: drone.gnss_valid ? 'var(--green)' : 'var(--amber)',
              }}>
                {drone.gnss_valid ? '◉ GNSS' : '◯ NO GNSS'}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MapView({ drones, onSelect }: { drones: DroneState[]; onSelect: (d: DroneState) => void }) {
  return (
    <div style={{
      width: '100%',
      height: '100%',
      position: 'relative',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    }}>
      {/* Radar grid background */}
      <div style={{
        position: 'absolute',
        inset: 0,
        backgroundImage: `
          radial-gradient(circle, rgba(0,201,255,0.04) 1px, transparent 1px),
          linear-gradient(rgba(0,201,255,0.025) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,201,255,0.025) 1px, transparent 1px)
        `,
        backgroundSize: '60px 60px, 60px 60px, 60px 60px',
      }} />

      {/* Radar rings */}
      {[160, 280, 400].map(r => (
        <div key={r} style={{
          position: 'absolute',
          width: r * 2,
          height: r * 2,
          border: '1px solid rgba(0,201,255,0.06)',
          borderRadius: '50%',
          pointerEvents: 'none',
        }} />
      ))}

      {/* Center crosshair */}
      <div style={{ position: 'absolute', width: 1, height: 60, background: 'rgba(0,201,255,0.15)', top: '50%', left: '50%', transform: 'translate(-50%,-100%)' }} />
      <div style={{ position: 'absolute', width: 1, height: 60, background: 'rgba(0,201,255,0.15)', bottom: '50%', left: '50%', transform: 'translate(-50%, 100%)' }} />
      <div style={{ position: 'absolute', height: 1, width: 60, background: 'rgba(0,201,255,0.15)', top: '50%', left: '50%', transform: 'translate(-100%,-50%)' }} />
      <div style={{ position: 'absolute', height: 1, width: 60, background: 'rgba(0,201,255,0.15)', top: '50%', right: '50%', transform: 'translate(100%,-50%)' }} />

      {/* Drone blips */}
      {drones.map((drone, i) => {
        const angle = (i / Math.max(drones.length, 1)) * 2 * Math.PI;
        const radius = 120 + (i % 3) * 80;
        const cx = Math.cos(angle) * radius;
        const cy = Math.sin(angle) * radius;
        const color = statusColor(drone.status);
        const conf = drone.confidence ?? 0;

        return (
          <div
            key={drone.drone_id}
            onClick={() => onSelect(drone)}
            style={{
              position: 'absolute',
              left: '50%',
              top: '50%',
              transform: `translate(calc(-50% + ${cx}px), calc(-50% + ${cy}px))`,
              cursor: 'pointer',
              zIndex: 10,
            }}
          >
            {/* Pulse ring */}
            {drone.status === 'active' && (
              <div style={{
                position: 'absolute',
                inset: -8,
                borderRadius: '50%',
                border: `1px solid ${color}`,
                opacity: 0.3,
                animation: 'pulse-dot 2s ease-in-out infinite',
              }} />
            )}
            {/* Blip */}
            <div style={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: color,
              boxShadow: `0 0 8px ${color}`,
            }} />
            {/* Label */}
            <div style={{
              position: 'absolute',
              left: 14,
              top: '50%',
              transform: 'translateY(-50%)',
              whiteSpace: 'nowrap',
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color,
                textShadow: `0 0 8px ${color}`,
              }}>{drone.drone_id}</div>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 9,
                color: 'var(--text-dim)',
              }}>{conf.toFixed(0)}%</div>
            </div>
          </div>
        );
      })}

      {/* Map label */}
      <div style={{
        position: 'absolute',
        bottom: 16,
        right: 16,
        fontFamily: 'var(--font-label)',
        fontSize: 9,
        color: 'var(--text-dim)',
        letterSpacing: '0.12em',
      }}>
        TACTICAL DISPLAY — RELATIVE COORDINATES
      </div>

      {/* Map note */}
      {drones.length === 0 && (
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--text-dim)',
          textAlign: 'center',
          zIndex: 5,
        }}>
          <MapPin size={20} style={{ display: 'block', margin: '0 auto 8px', opacity: 0.3 }} />
          SCANNING FOR CONTACTS...
        </div>
      )}
    </div>
  );
}
