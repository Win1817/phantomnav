import React, { useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  Radio, Map, Navigation, BarChart2, Bell, LogOut,
  Wifi, WifiOff, Activity, ChevronRight
} from 'lucide-react';
import { useStore } from '../store';
import { useWebSocket } from '../hooks/useWebSocket';
import styled from './AppShell.module';

const S = styled;

const NAV = [
  { to: '/',          icon: Map,         label: 'Fleet Map'    },
  { to: '/missions',  icon: Navigation,  label: 'Missions'     },
  { to: '/analytics', icon: BarChart2,   label: 'Analytics'    },
  { to: '/alerts',    icon: Bell,        label: 'Alerts'       },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  useWebSocket();
  const navigate = useNavigate();

  const { wsConnected, mqttConnected, unreadAlerts, clearAuth, drones } = useStore((s) => ({
    wsConnected:  s.wsConnected,
    mqttConnected: s.mqttConnected,
    unreadAlerts: s.unreadAlerts,
    clearAuth:    s.clearAuth,
    drones:       s.drones,
  }));

  const droneCount  = Object.keys(drones).length;
  const activeCount = Object.values(drones).filter(d => d.status === 'active').length;

  const handleLogout = () => { clearAuth(); navigate('/login'); };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg-void)' }}>

      {/* ── Sidebar ──────────────────────────────────────────── */}
      <aside style={{
        width: 220,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        borderRight: '1px solid var(--border-dim)',
        background: 'var(--bg-base)',
      }}>
        {/* Logo */}
        <div style={{
          padding: '20px 16px 16px',
          borderBottom: '1px solid var(--border-dim)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <Radio size={18} color="var(--accent)" style={{ flexShrink: 0 }} />
            <span style={{
              fontFamily: 'var(--font-label)',
              fontSize: 16,
              fontWeight: 700,
              letterSpacing: '0.12em',
              color: 'var(--text-primary)',
            }}>PHANTOM<span style={{ color: 'var(--accent)' }}>OPS</span></span>
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--text-dim)',
            letterSpacing: '0.1em',
          }}>UAV COMMAND PLATFORM</div>
        </div>

        {/* Status strip */}
        <div style={{
          padding: '10px 16px',
          borderBottom: '1px solid var(--border-dim)',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}>
          <StatusRow
            icon={wsConnected ? <Wifi size={11} /> : <WifiOff size={11} />}
            label="OPS LINK"
            value={wsConnected ? 'CONNECTED' : 'OFFLINE'}
            color={wsConnected ? 'var(--green)' : 'var(--red)'}
          />
          <StatusRow
            icon={<Activity size={11} />}
            label="MQTT"
            value={mqttConnected ? 'LIVE' : 'OFFLINE'}
            color={mqttConnected ? 'var(--green)' : 'var(--amber)'}
          />
          <StatusRow
            icon={<Radio size={11} />}
            label="FLEET"
            value={`${activeCount}/${droneCount} ACTIVE`}
            color={activeCount > 0 ? 'var(--green)' : 'var(--text-dim)'}
          />
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '8px 0' }}>
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '9px 16px',
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                background: isActive ? 'var(--accent-dim)' : 'transparent',
                borderLeft: isActive ? '2px solid var(--accent)' : '2px solid transparent',
                textDecoration: 'none',
                fontFamily: 'var(--font-label)',
                fontSize: 12,
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase' as const,
                transition: 'all 0.15s',
                position: 'relative' as const,
              })}
            >
              <Icon size={15} style={{ flexShrink: 0 }} />
              {label}
              {label === 'Alerts' && unreadAlerts > 0 && (
                <span style={{
                  marginLeft: 'auto',
                  background: 'var(--red)',
                  color: '#fff',
                  borderRadius: 10,
                  padding: '1px 6px',
                  fontSize: 9,
                  fontWeight: 700,
                }}>
                  {unreadAlerts > 99 ? '99+' : unreadAlerts}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Logout */}
        <button
          onClick={handleLogout}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '12px 16px',
            background: 'none',
            border: 'none',
            borderTop: '1px solid var(--border-dim)',
            color: 'var(--text-dim)',
            cursor: 'pointer',
            fontFamily: 'var(--font-label)',
            fontSize: 11,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            width: '100%',
            transition: 'color 0.15s',
          }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--red)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-dim)')}
        >
          <LogOut size={13} />
          Logout
        </button>
      </aside>

      {/* ── Main content ──────────────────────────────────────── */}
      <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {children}
      </main>
    </div>
  );
}

function StatusRow({ icon, label, value, color }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        color: 'var(--text-dim)',
        fontFamily: 'var(--font-label)',
        fontSize: 9,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
      }}>
        {icon} {label}
      </div>
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        color,
        letterSpacing: '0.05em',
      }}>{value}</span>
    </div>
  );
}

// Stub module export to avoid import errors
export default {};
