import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import loginBg from '../assets/login_bg.png';

// Re-use the same auth CSS injected by LoginPage / RegisterPage.
// The style tag is only added once (shared id "auth-styles").
const AUTH_CSS = `
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

.auth-brand-header { position: relative; z-index: 2; }

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
  margin-bottom: 1.5rem;
  text-align: center;
}

.auth-field {
  width: 100%;
  margin-bottom: 0.85rem;
}
.auth-label {
  display: block;
  font-size: 0.72rem;
  color: #5a9e95;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 0.35rem;
}
.auth-input {
  width: 100%;
  background: rgba(0,25,35,0.8);
  border: 1px solid rgba(0,200,170,0.18);
  border-radius: 8px;
  padding: 0.65rem 1rem;
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

.auth-success-msg {
  background: rgba(0,212,176,0.08);
  border: 1px solid rgba(0,212,176,0.25);
  border-radius: 7px;
  padding: 0.65rem 0.9rem;
  font-size: 0.8rem;
  color: #6ae8d6;
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

.auth-switch {
  text-align: center;
  font-size: 0.82rem;
  color: #5a9e95;
  margin-top: 0.75rem;
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

// ── OTP digit-box component ────────────────────────────────────────────────────
// 6 individual character boxes, keyboard/paste-aware
function OTPInput({ value, onChange, disabled }) {
  const inputs = useRef([]);

  const digits = (value + '      ').slice(0, 6).split('');

  const handleKey = (e, idx) => {
    if (e.key === 'Backspace') {
      e.preventDefault();
      const next = value.slice(0, idx) + value.slice(idx + 1);
      onChange(next);
      if (idx > 0) inputs.current[idx - 1]?.focus();
      return;
    }
    if (e.key === 'ArrowLeft' && idx > 0) { inputs.current[idx - 1]?.focus(); return; }
    if (e.key === 'ArrowRight' && idx < 5) { inputs.current[idx + 1]?.focus(); return; }
  };

  const handleInput = (e, idx) => {
    const char = e.target.value.replace(/\D/g, '').slice(-1);
    if (!char) return;
    const arr = (value + '      ').slice(0, 6).split('');
    arr[idx] = char;
    const next = arr.join('').trimEnd();
    onChange(next);
    if (idx < 5) inputs.current[idx + 1]?.focus();
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    onChange(pasted);
    const focusIdx = Math.min(pasted.length, 5);
    inputs.current[focusIdx]?.focus();
  };

  return (
    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', margin: '0.5rem 0 1.25rem' }}>
      {[0,1,2,3,4,5].map(i => (
        <input
          key={i}
          ref={el => (inputs.current[i] = el)}
          id={`otp-digit-${i}`}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={digits[i].trim()}
          disabled={disabled}
          onChange={e => handleInput(e, i)}
          onKeyDown={e => handleKey(e, i)}
          onPaste={handlePaste}
          autoComplete="one-time-code"
          style={{
            width: '52px',
            height: '62px',
            background: 'rgba(0,25,35,0.8)',
            border: '1px solid rgba(0,200,170,0.25)',
            borderRadius: '10px',
            color: '#00d4b0',
            fontSize: '1.65rem',
            fontWeight: '700',
            textAlign: 'center',
            fontFamily: "'JetBrains Mono', monospace",
            outline: 'none',
            transition: 'all 0.18s',
            caretColor: '#00d4b0',
            boxSizing: 'border-box',
          }}
          onFocus={e => {
            e.target.style.borderColor = 'rgba(0,212,176,0.55)';
            e.target.style.boxShadow = '0 0 0 3px rgba(0,212,176,0.12)';
            e.target.style.background = 'rgba(0,32,44,0.9)';
          }}
          onBlur={e => {
            e.target.style.borderColor = 'rgba(0,200,170,0.25)';
            e.target.style.boxShadow = 'none';
            e.target.style.background = 'rgba(0,25,35,0.8)';
          }}
        />
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function VerifyOTPPage({ pendingId, email, onSuccess, onBack }) {
  const { login } = useAuth();
  const [otp, setOtp]           = useState('');
  const [error, setError]       = useState('');
  const [success, setSuccess]   = useState('');
  const [loading, setLoading]   = useState(false);
  const [resending, setResending] = useState(false);
  const [countdown, setCountdown] = useState(0); // resend cooldown in seconds

  // Inject CSS once
  useEffect(() => {
    if (!document.getElementById('auth-styles')) {
      const el = document.createElement('style');
      el.id = 'auth-styles';
      el.textContent = AUTH_CSS;
      document.head.appendChild(el);
    }
  }, []);

  // Countdown timer for resend
  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const handleVerify = async (e) => {
    e?.preventDefault();
    if (otp.length < 6) { setError('Please enter the complete 6-digit code.'); return; }
    setError('');
    setLoading(true);
    try {
      const res = await fetch('/api/v1/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pending_id: pendingId, otp_code: otp }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || 'Verification failed. Please try again.');
        if (res.status === 410) {
          // expired — let parent know to go back to register
          setTimeout(() => onBack?.(), 3000);
        }
        return;
      }
      // Successful verification → log in
      login(data.access_token, data.user);
      onSuccess?.();
    } catch {
      setError('Connection error. Please check if the server is running.');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (resending || countdown > 0) return;
    setError('');
    setSuccess('');
    setResending(true);
    // We ask the user to go back to Register to re-submit the form, which will
    // clean up the pending record and re-send a fresh OTP.
    // Alternatively, we can expose a dedicated /resend endpoint.
    // For now we redirect back to register with a message.
    setSuccess('Please go back to the registration form and submit again to receive a new code.');
    setCountdown(30);
    setResending(false);
  };

  const maskedEmail = email
    ? email.replace(/^(.)(.*)(@.*)$/, (_, a, b, c) => a + '*'.repeat(Math.max(b.length - 2, 1)) + b.slice(-2) + c)
    : '';

  return (
    <div className="auth-root">
      {/* ── Left brand panel ── */}
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
            Identity<br />Verification
          </h2>

          <p className="auth-brand-sub">
            Your operator registration is almost complete. Enter the
            6-digit code sent to your email to confirm your identity and
            activate your Sentinel AI account.
          </p>
        </div>

        <div className="auth-status-badges">
          {[
            'OTP Delivered via Secure Mail Channel',
            'Code Valid for 15 Minutes',
            'AES-256 Encrypted Session',
          ].map(s => (
            <div key={s} className="auth-status-badge">
              <span className="auth-status-dot" />
              {s}
            </div>
          ))}
        </div>

        <div className="auth-brand-footer">
          <span>LAT: 34.5201° N · LON: 74.8820° E</span>
          <span>OTP VERIFICATION GATEWAY</span>
        </div>
      </div>

      {/* ── Right form panel ── */}
      <div className="auth-form-panel">
        <button id="otp-back-btn" className="auth-back-link" onClick={onBack}>
          ← Back to Register
        </button>

        {/* Shield icon */}
        <div style={{
          width: 64, height: 64,
          background: 'rgba(0,180,150,0.1)',
          border: '1.5px solid rgba(0,210,180,0.35)',
          borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginBottom: '1.25rem',
          boxShadow: '0 0 24px rgba(0,212,176,0.15)',
        }}>
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L3 6v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V6l-9-4z"
                  stroke="#00d4b0" strokeWidth="1.5" fill="rgba(0,212,176,0.12)"/>
            <path d="M9 12l2 2 4-4" stroke="#00d4b0" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>

        <h1 className="auth-form-title">Verify Your Email</h1>
        <p className="auth-form-sub">
          We sent a 6-digit code to<br />
          <strong style={{ color: '#00d4b0' }}>{maskedEmail}</strong>
        </p>

        {error && (
          <div className="auth-error-msg">
            <span>⚠</span> {error}
          </div>
        )}
        {success && (
          <div className="auth-success-msg">
            <span>✓</span> {success}
          </div>
        )}

        <form onSubmit={handleVerify} style={{ width: '100%' }}>
          <label className="auth-label" style={{ textAlign: 'center', display: 'block', marginBottom: '0.5rem' }}>
            Enter Verification Code
          </label>

          <OTPInput value={otp} onChange={setOtp} disabled={loading} />

          <button
            id="otp-verify-btn"
            type="submit"
            className="auth-submit-btn"
            disabled={loading || otp.length < 6}
          >
            {loading ? 'Verifying…' : '✓ Verify & Activate Account'}
          </button>
        </form>

        <div style={{ marginTop: '1.25rem', textAlign: 'center', width: '100%' }}>
          <p style={{ color: '#3a7068', fontSize: '0.8rem', marginBottom: '0.5rem' }}>
            Didn't receive the code?
          </p>
          <button
            id="otp-resend-btn"
            className="auth-switch-link"
            onClick={handleResend}
            disabled={resending || countdown > 0}
            style={{ opacity: countdown > 0 ? 0.5 : 1 }}
          >
            {countdown > 0 ? `Resend in ${countdown}s` : 'Go back & resend'}
          </button>
        </div>

        <div style={{
          marginTop: '1.5rem',
          padding: '0.75rem',
          background: 'rgba(0,25,35,0.5)',
          border: '1px solid rgba(0,200,170,0.1)',
          borderRadius: '8px',
          width: '100%',
          boxSizing: 'border-box',
        }}>
          <p style={{ color: '#3a7068', fontSize: '0.72rem', fontFamily: "'JetBrains Mono', monospace", margin: 0, lineHeight: 1.6 }}>
            ℹ️ Check your spam/junk folder if the email is not in your inbox.
            The code expires in 15 minutes.
          </p>
        </div>
      </div>
    </div>
  );
}
