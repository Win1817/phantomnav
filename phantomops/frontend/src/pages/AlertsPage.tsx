import React, { useEffect } from 'react';
import { Bell, BellOff } from 'lucide-react';
import { useStore } from '../store';
import { Alert } from '../types';
import { severityColor, severityLabel, formatTs, navModeLabel } from '../utils/format';

export function AlertsPage() {
  const { alerts, unreadAlerts, markAlertsRead } = useStore((s) => ({
    alerts:      s.alerts,
    unreadAlerts: s.unreadAlerts,
    markAlertsRead: s.markAlertsRead,
  }));

  useEffect(() => {
    markAlertsRead();
  }, []);

  const grouped: Record<number, Alert[]> = { 3: [], 2: [], 1: [], 0: [] };
  alerts.forEach(a => {
    const sev = Math.min(a.severity, 3);
    grouped[sev].push(a);
  });

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <Bell size={16} color="var(--accent)" />
        <span style={{ fontFamily: 'var(--font-label)', fontSize: 14, fontWeight: 600, letterSpacing: '0.1em' }}>
          ALERT LOG
        </span>
        {unreadAlerts > 0 && (
          <span className="badge" style={{ background: 'var(--red-dim)', border: '1px solid var(--red)', color: 'var(--red)' }}>
            {unreadAlerts} NEW
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)' }}>
          {alerts.length} total
        </span>
      </div>

      {alerts.length === 0 ? (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: 300,
          color: 'var(--text-dim)',
          gap: 12,
        }}>
          <BellOff size={32} style={{ opacity: 0.3 }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>NO ALERTS</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9 }}>SYSTEM NOMINAL</span>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {alerts.map((alert, i) => (
            <AlertRow key={i} alert={alert} />
          ))}
        </div>
      )}
    </div>
  );
}

function AlertRow({ alert }: { alert: Alert }) {
  const sev = Math.min(alert.severity, 3);
  const color = severityColor(sev);
  const label = severityLabel(sev);

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '10px 16px',
      background: 'var(--bg-panel)',
      border: '1px solid var(--border-dim)',
      borderLeft: `3px solid ${color}`,
      borderRadius: 4,
      animation: 'slide-in-right 0.2s ease',
    }}>
      {/* Severity */}
      <span className="badge" style={{
        background: `${color}18`,
        border: `1px solid ${color}50`,
        color,
        flexShrink: 0,
        width: 70,
        justifyContent: 'center',
      }}>{label}</span>

      {/* Drone + timestamp */}
      <div style={{ flexShrink: 0, minWidth: 80 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)' }}>{alert.drone_id}</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>
          {formatTs(alert.ts)}
        </div>
      </div>

      {/* Code */}
      <div style={{ flexShrink: 0, minWidth: 160 }}>
        <div style={{ fontFamily: 'var(--font-label)', fontSize: 10, color, letterSpacing: '0.08em' }}>
          {alert.code}
        </div>
        <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.06em' }}>
          {alert.source}
        </div>
      </div>

      {/* Message */}
      <div style={{
        flex: 1,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--text-secondary)',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {alert.message}
      </div>

      {/* Telemetry snapshot */}
      <div style={{ display: 'flex', gap: 10, flexShrink: 0 }}>
        {alert.confidence_at_alert !== undefined && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>CONF</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
              {alert.confidence_at_alert.toFixed(0)}
            </div>
          </div>
        )}
        {alert.nav_mode_at_alert !== undefined && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>MODE</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-secondary)' }}>
              {['GNSS_PRI', 'INS+SLAM', 'INS_ONLY', 'SAFE', 'EMRG'][alert.nav_mode_at_alert] ?? alert.nav_mode_at_alert}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
