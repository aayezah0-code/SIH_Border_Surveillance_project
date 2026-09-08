import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import loginBg from '../assets/login_bg.png';

const LOGIN_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

.auth-root {
  font-family: 'Outfit', system-ui, sans-serif;
  min-height: 100vh;
  background-color: #010b0f;
  background-image: 
    linear-gradient(180deg, rgba(1, 11, 15, 0.35) 0%, rgba(1, 15, 22, 0.25) 100%),
    url('${loginBg}');
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  display: flex;
  align-items: stretch;
  color: #e2f0ef;
  overflow: hidden;
}

/* ── Left brand panel ── */
.auth-brand {
  flex: 1.15;
  background-image: 
    linear-gradient(180deg, rgba(1, 14, 23, 0.20) 0%, rgba(1, 25, 37, 0.10) 45%, rgba(0, 25, 18, 0.35) 100%),
    radial-gradient(circle at 40% 40%, rgba(0, 212, 176, 0.04) 0%, transparent 60%),
    url('${loginBg}');
  background-size: cover;
  background-position: left center;
  background-repeat: no-repeat;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 3.5rem 4rem;
  position: relative;
  overflow: hidden;
  border-right: 1px solid rgba(0,200,170,0.18);
}

.auth-brand-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(0,210,180,0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,210,180,0.035) 1px, transparent 1px);
  background-size: 36px 36px;
  pointer-events: none;
}

.auth-brand-orb {
  position: absolute;
  width: 520px; height: 520px;
  border-radius: 50%;
  bottom: -160px; left: -140px;
  background: radial-gradient(circle, rgba(0,180,150,0.18) 0%, transparent 70%);
  pointer-events: none;
  filter: blur(80px);
}

/* ── Mountain terrain & watchtower SVG background ── */
.auth-brand-terrain {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 240px;
  pointer-events: none;
  opacity: 0.45;
}

/* ── Tactical radar sweep motif ── */
.auth-radar-ring {
  position: absolute;
  top: 18%;
  right: 8%;
  width: 320px;
  height: 320px;
  border-radius: 50%;
  border: 1px solid rgba(0, 212, 176, 0.12);
  pointer-events: none;
}
.auth-radar-ring::before {
  content: '';
  position: absolute;
  inset: 22%;
  border-radius: 50%;
  border: 1px dashed rgba(6, 182, 212, 0.1);
}
.auth-radar-ring::after {
  content: '';
  position: absolute;
  inset: 48%;
  border-radius: 50%;
  border: 1px solid rgba(0, 212, 176, 0.15);
}

.auth-brand-header {
  position: relative;
  z-index: 2;
}

.auth-brand-logo {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 2.5rem;
  position: relative;
}
.auth-brand-icon {
  width: 44px; height: 44px;
  border: 1.5px solid rgba(0,210,180,0.5);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,180,150,0.12);
  box-shadow: 0 0 16px rgba(0,210,180,0.25);
}
.auth-brand-name {
  font-size: 1.3rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  background: linear-gradient(135deg, #00d4b0, #06b6d4);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.auth-brand-tagline {
  position: relative;
  font-size: clamp(1.8rem, 3vw, 2.6rem);
  font-weight: 700;
  line-height: 1.15;
  background: linear-gradient(160deg, #ffffff 0%, #dff7f4 50%, #00d4b0 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  filter: drop-shadow(0 2px 16px rgba(0,0,0,0.85));
  margin-bottom: 1.25rem;
}
.auth-brand-sub {
  position: relative;
  color: #c4ede7;
  font-size: 0.92rem;
  line-height: 1.7;
  max-width: 420px;
  font-weight: 450;
  text-shadow: 0 2px 12px rgba(0,0,0,0.9);
  margin-bottom: 2rem;
}

.auth-status-badges {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  margin-bottom: 1.5rem;
}
.auth-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.76rem;
  color: #bceae4;
  font-family: 'JetBrains Mono', monospace;
  background: rgba(0, 25, 35, 0.65);
  border: 1px solid rgba(0, 212, 176, 0.25);
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
  width: fit-content;
  backdrop-filter: blur(10px);
  text-shadow: 0 1px 6px rgba(0,0,0,0.8);
}
.auth-status-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #00d4b0;
  box-shadow: 0 0 8px #00d4b0;
  flex-shrink: 0;
  animation: auth-pulse 2.5s infinite;
}
@keyframes auth-pulse {
  0%,100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.auth-brand-footer {
  position: relative;
  z-index: 2;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid rgba(0, 212, 176, 0.1);
  padding-top: 1.2rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  color: #3b736b;
}

/* ── Right form panel ── */
.auth-form-panel {
  width: 480px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 3.5rem;
  background: rgba(1,16,24,0.95);
  position: relative;
  box-shadow: -10px 0 40px rgba(0,0,0,0.5);
}
.auth-form-panel::before {
  content: '';
  position: absolute;
  top: 0; bottom: 0; left: 0;
  width: 1px;
  background: linear-gradient(180deg, transparent, rgba(0,212,176,0.3), transparent);
}

.auth-form-title {
  font-size: 1.7rem;
  font-weight: 700;
  color: #e2f0ef;
  margin-bottom: 0.35rem;
  text-align: center;
}
.auth-form-sub {
  font-size: 0.85rem;
  color: #5a9e95;
  margin-bottom: 2rem;
  text-align: center;
}

.auth-field {
  width: 100%;
  margin-bottom: 1rem;
}
.auth-label {
  display: block;
  font-size: 0.72rem;
  color: #5a9e95;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 0.4rem;
}
.auth-input {
  width: 100%;
  background: rgba(0,25,35,0.8);
  border: 1px solid rgba(0,200,170,0.18);
  border-radius: 8px;
  padding: 0.7rem 1rem;
  color: #e2f0ef;
  font-size: 0.9rem;
  font-family: 'Outfit', sans-serif;
  outline: none;
  transition: all 0.2s;
  box-sizing: border-box;
}
.auth-input::placeholder { color: #2d5e57; }
.auth-input:focus {
  border-color: rgba(0,212,176,0.5);
  box-shadow: 0 0 0 3px rgba(0,212,176,0.1);
  background: rgba(0,32,44,0.9);
}
.auth-input.auth-input-error {
  border-color: rgba(220,38,38,0.5);
}

.auth-error-msg {
  background: rgba(220,38,38,0.10);
  border: 1px solid rgba(220,38,38,0.25);
  border-radius: 7px;
  padding: 0.65rem 0.9rem;
  font-size: 0.8rem;
  color: #fca5a5;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  box-sizing: border-box;
}

.auth-submit-btn {
  width: 100%;
  background: linear-gradient(135deg, #00b896, #06b6d4);
  border: none;
  color: #000e0c;
  padding: 0.8rem;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: all 0.25s;
  font-family: 'Outfit', sans-serif;
  box-shadow: 0 0 20px rgba(0,184,150,0.3);
  margin-top: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}
.auth-submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 0 35px rgba(0,184,150,0.5);
}
.auth-submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auth-divider {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1.25rem 0;
}
.auth-divider-line { flex: 1; height: 1px; background: rgba(0,200,170,0.10); }
.auth-divider-text { font-size: 0.7rem; color: #2d5e57; font-family: 'JetBrains Mono', monospace; }

.auth-switch {
  text-align: center;
  font-size: 0.82rem;
  color: #5a9e95;
  margin-top: 1rem;
}
.auth-switch-link {
  color: #00d4b0;
  cursor: pointer;
  font-weight: 600;
  background: none;
  border: none;
  font-family: inherit;
  font-size: inherit;
  padding: 0;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.auth-switch-link:hover { color: #6ae8d6; }

.auth-back-link {
  position: absolute;
  top: 1.5rem;
  left: 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.78rem;
  color: #3a7068;
  cursor: pointer;
  background: none;
  border: none;
  font-family: 'Outfit', sans-serif;
  transition: color 0.2s;
  padding: 0;
}
.auth-back-link:hover { color: #00d4b0; }

@media (max-width: 900px) {
  .auth-brand { display: none; }
  .auth-form-panel { width: 100%; }
}
`;

export default function LoginPage({ onSuccess, onRegister, onBack }) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  useEffect(() => {
    if (!document.getElementById('auth-styles')) {
      const el = document.createElement('style');
      el.id = 'auth-styles';
      el.textContent = LOGIN_CSS;
      document.head.appendChild(el);
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!username.trim() || !password.trim()) {
      setError('Please fill in all fields.');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || 'Login failed. Check your credentials.');
        return;
      }
      login(data.access_token, data.user);
      onSuccess?.();
    } catch {
      setError('Connection error. Please check if the server is running.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-root">
      {/* Left brand panel */}
      <div className="auth-brand">
        <div className="auth-brand-grid" />
        <div className="auth-brand-orb" />
        <div className="auth-radar-ring" />

        <div className="auth-brand-header">
          <div className="auth-brand-logo">
            <div className="auth-brand-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L2 7v10l10 5 10-5V7L12 2z" stroke="#00d4b0" strokeWidth="1.5" fill="none"/>
                <circle cx="12" cy="12" r="3" fill="#00d4b0" opacity="0.8"/>
              </svg>
            </div>
            <span className="auth-brand-name">SENTINEL AI</span>
          </div>

          <h2 className="auth-brand-tagline">
            Command Access // <br />Authorized Personnel Only
          </h2>
          <p className="auth-brand-sub">
            High-security terminal gateway for border reconnaissance, AI threat detection, and autonomous perimeter surveillance.
          </p>
        </div>

        <div className="auth-status-badges">
          {[
            'AI Detection Engine — Active (YOLOv8 + ByteTrack)',
            'Sector 04 Perimeter Grid — Armed & Monitored',
            'Secure Encrypted Protocol — 256-bit Mil-Spec',
          ].map(s => (
            <div key={s} className="auth-status-badge">
              <span className="auth-status-dot" />
              {s}
            </div>
          ))}
        </div>

        <div className="auth-brand-footer">
          <span>LAT: 34.5201° N · LON: 74.8820° E</span>
          <span>STATION: ALPHA-01 // LEVEL 3 CLEARANCE</span>
        </div>
      </div>

      {/* Right form panel */}
      <div className="auth-form-panel">
        <button id="login-back-btn" className="auth-back-link" onClick={onBack}>
          ← Back
        </button>

        <h1 className="auth-form-title">Operator Sign In</h1>
        <p className="auth-form-sub">Enter your credentials to access the command dashboard</p>

        {error && (
          <div className="auth-error-msg">
            <span>⚠</span> {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ width: '100%' }}>
          <div className="auth-field">
            <label className="auth-label" htmlFor="login-username">Username or Email</label>
            <input
              id="login-username"
              className={`auth-input${error ? ' auth-input-error' : ''}`}
              type="text"
              placeholder="operator@sentinel.ai"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
            />
          </div>
          <div className="auth-field">
            <label className="auth-label" htmlFor="login-password">Password</label>
            <input
              id="login-password"
              className={`auth-input${error ? ' auth-input-error' : ''}`}
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>

          <button
            id="login-submit-btn"
            type="submit"
            className="auth-submit-btn"
            disabled={loading}
          >
            {loading ? (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{animation:'spin 1s linear infinite'}}>
                  <circle cx="12" cy="12" r="10" stroke="rgba(0,0,0,0.3)" strokeWidth="3"/>
                  <path d="M12 2a10 10 0 0 1 10 10" stroke="#000" strokeWidth="3" strokeLinecap="round"/>
                </svg>
                Authenticating...
              </>
            ) : (
              'Sign In to Dashboard'
            )}
          </button>
        </form>

        <div className="auth-divider">
          <div className="auth-divider-line" />
          <span className="auth-divider-text">OR</span>
          <div className="auth-divider-line" />
        </div>

        <div className="auth-switch">
          Don't have an account?{' '}
          <button id="login-go-register-btn" className="auth-switch-link" onClick={onRegister}>
            Create Account
          </button>
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
