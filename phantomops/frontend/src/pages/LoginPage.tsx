import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Radio, Lock, User } from 'lucide-react';
import { useStore } from '../store';
import { api } from '../utils/api';

export function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useStore((s) => s.setAuth);
  const [droneId, setDroneId] = useState('drone-001');
  const [secret, setSecret] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.login({ drone_id: droneId, secret });
      setAuth(res.access_token, { drone_id: droneId });
      navigate('/');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  // Dev bypass — allow empty auth for local dev
  const devBypass = () => {
    setAuth('dev-token', { drone_id: 'dev', role: 'admin' });
    navigate('/');
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg-void)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: 'var(--font-body)',
    }}>
      {/* Grid background */}
      <div style={{
        position: 'fixed',
        inset: 0,
        backgroundImage: `
          linear-gradient(rgba(0,201,255,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,201,255,0.03) 1px, transparent 1px)
        `,
        backgroundSize: '40px 40px',
        pointerEvents: 'none',
      }} />

      <div style={{
        width: 380,
        background: 'var(--bg-panel)',
        border: '1px solid var(--border-mid)',
        borderRadius: 8,
        overflow: 'hidden',
        position: 'relative',
        boxShadow: '0 0 60px rgba(0,201,255,0.08)',
        animation: 'fade-in 0.4s ease',
      }}>
        {/* Header */}
        <div style={{
          padding: '28px 28px 24px',
          borderBottom: '1px solid var(--border-dim)',
          textAlign: 'center',
        }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 48,
            height: 48,
            borderRadius: '50%',
            background: 'var(--accent-dim)',
            border: '1px solid var(--accent)',
            marginBottom: 16,
            boxShadow: '0 0 20px var(--accent-dim)',
          }}>
            <Radio size={22} color="var(--accent)" />
          </div>
          <div style={{
            fontFamily: 'var(--font-label)',
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: '0.15em',
            color: 'var(--text-primary)',
          }}>
            PHANTOM<span style={{ color: 'var(--accent)' }}>OPS</span>
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--text-dim)',
            letterSpacing: '0.12em',
            marginTop: 4,
          }}>UAV COMMAND &amp; CONTROL PLATFORM</div>
        </div>

        {/* Form */}
        <form onSubmit={handleLogin} style={{ padding: 28 }}>
          <div style={{ marginBottom: 16 }}>
            <label style={{
              display: 'block',
              fontFamily: 'var(--font-label)',
              fontSize: 10,
              color: 'var(--text-dim)',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              marginBottom: 6,
            }}>Operator ID</label>
            <div style={{ position: 'relative' }}>
              <User size={13} style={{
                position: 'absolute', left: 10, top: '50%',
                transform: 'translateY(-50%)', color: 'var(--text-dim)',
              }} />
              <input
                className="input"
                style={{ paddingLeft: 30 }}
                value={droneId}
                onChange={e => setDroneId(e.target.value)}
                placeholder="drone-001"
                autoComplete="username"
              />
            </div>
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{
              display: 'block',
              fontFamily: 'var(--font-label)',
              fontSize: 10,
              color: 'var(--text-dim)',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              marginBottom: 6,
            }}>Access Key</label>
            <div style={{ position: 'relative' }}>
              <Lock size={13} style={{
                position: 'absolute', left: 10, top: '50%',
                transform: 'translateY(-50%)', color: 'var(--text-dim)',
              }} />
              <input
                className="input"
                style={{ paddingLeft: 30 }}
                type="password"
                value={secret}
                onChange={e => setSecret(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>
          </div>

          {error && (
            <div style={{
              background: 'var(--red-dim)',
              border: '1px solid var(--red)',
              borderRadius: 4,
              padding: '8px 12px',
              marginBottom: 16,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--red)',
            }}>{error}</div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{ width: '100%', justifyContent: 'center', padding: '10px' }}
          >
            {loading ? 'AUTHENTICATING...' : 'ACCESS PLATFORM'}
          </button>

          <button
            type="button"
            onClick={devBypass}
            style={{
              marginTop: 10,
              width: '100%',
              background: 'none',
              border: '1px dashed var(--border-dim)',
              borderRadius: 4,
              padding: '7px',
              color: 'var(--text-dim)',
              fontSize: 10,
              fontFamily: 'var(--font-label)',
              letterSpacing: '0.1em',
              cursor: 'pointer',
              textTransform: 'uppercase',
            }}
          >
            DEV BYPASS (LOCAL ONLY)
          </button>
        </form>
      </div>
    </div>
  );
}
