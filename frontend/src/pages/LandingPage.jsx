import React, { useEffect, useRef } from 'react';
import landingBg from '../assets/landing_bg.png';

// ─── Scoped CSS injected once ─────────────────────────────────────────────────
const LANDING_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');

.lp-root {
  font-family: 'Outfit', system-ui, sans-serif;
  background: #010b0f;
  min-height: 100vh;
  color: #e2f0ef;
  overflow-x: hidden;
  position: relative;
}

/* ── Military Border Atmospheric Background Layer ── */
.lp-bg-image {
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(180deg, rgba(1, 11, 15, 0.20) 0%, rgba(1, 15, 22, 0.08) 35%, rgba(1, 11, 15, 0.40) 100%),
    radial-gradient(circle at 50% 20%, rgba(0, 212, 176, 0.04) 0%, transparent 70%),
    url('${landingBg}');
  background-size: cover;
  background-position: center top;
  background-repeat: no-repeat;
  pointer-events: none;
  z-index: 0;
}

/* ── Ambient background grid ── */
.lp-grid-bg {
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(0,210,180,0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,210,180,0.02) 1px, transparent 1px);
  background-size: 44px 44px;
  pointer-events: none;
  z-index: 0;
}

/* ── Topographic contour layer ── */
.lp-topo-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.12;
  background-image: radial-gradient(circle at 50% 30%, transparent 20%, rgba(0,212,176,0.03) 40%, transparent 60%);
}

/* ── Border terrain silhouette SVG background ── */
.lp-terrain-bg {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 380px;
  pointer-events: none;
  z-index: 0;
  opacity: 0.35;
}

/* ── Tactical radar sweep motif in background ── */
.lp-radar-layer {
  position: fixed;
  top: 15%;
  right: 5%;
  width: 500px;
  height: 500px;
  border-radius: 50%;
  border: 1px solid rgba(0, 212, 176, 0.08);
  pointer-events: none;
  z-index: 0;
}
.lp-radar-layer::before {
  content: '';
  position: absolute;
  inset: 20%;
  border-radius: 50%;
  border: 1px dashed rgba(0, 212, 176, 0.06);
}
.lp-radar-layer::after {
  content: '';
  position: absolute;
  inset: 45%;
  border-radius: 50%;
  border: 1px solid rgba(6, 182, 212, 0.1);
}

/* ── Radial glow orbs ── */
.lp-orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(100px);
  pointer-events: none;
  z-index: 0;
}
.lp-orb-1 {
  width: 550px; height: 550px;
  top: -140px; left: -120px;
  background: radial-gradient(circle, rgba(0,180,150,0.16) 0%, transparent 70%);
}
.lp-orb-2 {
  width: 450px; height: 450px;
  bottom: 80px; right: -100px;
  background: radial-gradient(circle, rgba(6,182,212,0.12) 0%, transparent 70%);
}
.lp-orb-3 {
  width: 320px; height: 320px;
  top: 45%; left: 50%;
  transform: translate(-50%,-50%);
  background: radial-gradient(circle, rgba(16,185,129,0.08) 0%, transparent 70%);
}

/* ── Tactical coordinate markers on outer page ── */
.lp-coord-tag {
  position: absolute;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem;
  color: #2e5953;
  letter-spacing: 0.12em;
  pointer-events: none;
  user-select: none;
}
.lp-coord-tl { top: 1.5rem; left: 2rem; }
.lp-coord-tr { top: 1.5rem; right: 2rem; }

/* ── Navbar ── */
.lp-nav {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 3rem;
  border-bottom: 1px solid rgba(0,200,170,0.12);
  backdrop-filter: blur(16px);
  background: rgba(1,15,22,0.75);
}
.lp-nav-logo {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.lp-nav-logo-icon {
  width: 36px; height: 36px;
  border: 1.5px solid rgba(0,210,180,0.5);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,180,150,0.12);
  box-shadow: 0 0 12px rgba(0,210,180,0.2);
}
.lp-nav-logo-text {
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  background: linear-gradient(135deg, #00d4b0, #06b6d4);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.lp-nav-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  color: #00d4b0;
  border: 1px solid rgba(0,212,176,0.3);
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  letter-spacing: 0.12em;
}
.lp-nav-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
.lp-btn-ghost {
  background: transparent;
  border: 1px solid rgba(0,200,170,0.3);
  color: #a0d8cf;
  padding: 0.45rem 1.2rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  letter-spacing: 0.03em;
  transition: all 0.2s;
  font-family: inherit;
}
.lp-btn-ghost:hover {
  border-color: rgba(0,200,170,0.7);
  color: #00d4b0;
  background: rgba(0,200,170,0.08);
}
.lp-btn-primary {
  background: linear-gradient(135deg, #00b896, #06b6d4);
  border: none;
  color: #000e0c;
  padding: 0.5rem 1.4rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 700;
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: all 0.2s;
  font-family: inherit;
  box-shadow: 0 0 16px rgba(0,184,150,0.35);
}
.lp-btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 28px rgba(0,184,150,0.55);
}

/* ── Hero ── */
.lp-hero {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 5.5rem 2rem 4rem;
  gap: 1.5rem;
}
.lp-hero-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  letter-spacing: 0.2em;
  color: #00d4b0;
  text-transform: uppercase;
  border: 1px solid rgba(0,212,176,0.25);
  background: rgba(0,212,176,0.06);
  padding: 0.35rem 1rem;
  border-radius: 50px;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  box-shadow: 0 0 15px rgba(0,212,176,0.1);
}
.lp-hero-tag::before {
  content: '';
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #00d4b0;
  box-shadow: 0 0 8px #00d4b0;
  animation: lp-pulse 2s infinite;
}
@keyframes lp-pulse {
  0%,100% { opacity: 1; }
  50%      { opacity: 0.35; }
}
.lp-hero-title {
  font-size: clamp(2.5rem, 6vw, 4.5rem);
  font-weight: 800;
  line-height: 1.08;
  letter-spacing: -0.02em;
  max-width: 840px;
  background: linear-gradient(160deg, #ffffff 0%, #dff7f4 40%, #00d4b0 80%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  filter: drop-shadow(0 2px 16px rgba(0,0,0,0.85));
}
.lp-hero-sub {
  font-size: clamp(1rem, 2.5vw, 1.2rem);
  color: #bceae4;
  max-width: 620px;
  line-height: 1.65;
  font-weight: 450;
  text-shadow: 0 2px 12px rgba(0,0,0,0.9);
}
.lp-hero-cta {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 0.5rem;
}
.lp-btn-cta-primary {
  background: linear-gradient(135deg, #00b896, #06b6d4);
  border: none;
  color: #000e0c;
  padding: 0.85rem 2.2rem;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 700;
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: all 0.25s;
  font-family: inherit;
  box-shadow: 0 0 30px rgba(0,184,150,0.4);
  display: inline-flex; align-items: center; gap: 0.5rem;
}
.lp-btn-cta-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 50px rgba(0,184,150,0.6);
}
.lp-btn-cta-secondary {
  background: rgba(1, 20, 28, 0.6);
  border: 1.5px solid rgba(0,200,170,0.35);
  color: #a0d8cf;
  padding: 0.85rem 2.2rem;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: all 0.25s;
  font-family: inherit;
  backdrop-filter: blur(8px);
}
.lp-btn-cta-secondary:hover {
  border-color: rgba(0,200,170,0.7);
  color: #00d4b0;
  background: rgba(0,200,170,0.12);
  transform: translateY(-1px);
}

/* ── Hero visual ── */
.lp-hero-visual {
  position: relative;
  margin-top: 2.5rem;
  width: 100%;
  max-width: 920px;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid rgba(0,200,170,0.22);
  box-shadow: 0 0 70px rgba(0,180,150,0.18), 0 0 120px rgba(0,0,0,0.6);
}
.lp-hero-visual-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1rem;
  background: rgba(1,20,28,0.95);
  border-bottom: 1px solid rgba(0,200,170,0.12);
}
.lp-dot { width: 10px; height: 10px; border-radius: 50%; }
.lp-dot-r { background: #ff5f57; }
.lp-dot-y { background: #febc2e; }
.lp-dot-g { background: #28c840; }
.lp-visual-url {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #5a9e95;
  margin-left: 0.5rem;
}
.lp-hero-dashboard {
  background: #011218;
  padding: 1.5rem;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 0.75rem;
}
.lp-stat-mini {
  background: rgba(0,30,42,0.85);
  border: 1px solid rgba(0,200,170,0.14);
  border-radius: 8px;
  padding: 0.75rem 1rem;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}
.lp-stat-mini-label {
  font-size: 0.65rem;
  color: #5a9e95;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-family: 'JetBrains Mono', monospace;
}
.lp-stat-mini-value {
  font-size: 1.4rem;
  font-weight: 700;
  color: #00d4b0;
  margin-top: 0.25rem;
}
.lp-stat-mini-sub {
  font-size: 0.65rem;
  color: #3a7068;
  margin-top: 0.1rem;
}
.lp-feed-row {
  grid-column: 1/-1;
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 0.75rem;
}
.lp-feed-cam {
  background: rgba(0,20,28,0.9);
  border: 1px solid rgba(0,200,170,0.12);
  border-radius: 8px;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

/* ── Camera feed with real video ── */
.lp-cam-placeholder {
  aspect-ratio: 16/9;
  background: #010f15;
  border-radius: 6px;
  border: 1px solid rgba(0,200,170,0.12);
  position: relative;
  overflow: hidden;
}

/* Real surveillance video */
.lp-surv-video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.82;
  filter: brightness(0.75) contrast(1.1) saturate(0.7);
}

/* Night-vision teal tint overlay */
.lp-video-tint {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    rgba(0,20,28,0.35) 0%,
    rgba(0,180,150,0.04) 50%,
    rgba(0,10,18,0.45) 100%
  );
  pointer-events: none;
}

/* Scanline sweep — CSS-only, no JS, no requestAnimationFrame */
.lp-cam-scan-line {
  position: absolute;
  left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(0,212,176,0.08) 20%,
    rgba(0,212,176,0.55) 50%,
    rgba(0,212,176,0.08) 80%,
    transparent 100%
  );
  box-shadow: 0 0 8px rgba(0,212,176,0.4), 0 0 2px rgba(0,212,176,0.8);
  animation: lp-scan 4s linear infinite;
  pointer-events: none;
  z-index: 5;
}
@keyframes lp-scan {
  0%   { top: -2px; }
  100% { top: 100%; }
}

/* HUD corner brackets */
.lp-hud-corner {
  position: absolute;
  width: 16px;
  height: 16px;
  pointer-events: none;
  z-index: 4;
}
.lp-hud-corner-tl { top: 8px; left: 8px; border-top: 1.5px solid #00d4b0; border-left: 1.5px solid #00d4b0; }
.lp-hud-corner-tr { top: 8px; right: 8px; border-top: 1.5px solid #00d4b0; border-right: 1.5px solid #00d4b0; }
.lp-hud-corner-bl { bottom: 8px; left: 8px; border-bottom: 1.5px solid #00d4b0; border-left: 1.5px solid #00d4b0; }
.lp-hud-corner-br { bottom: 8px; right: 8px; border-bottom: 1.5px solid #00d4b0; border-right: 1.5px solid #00d4b0; }

/* HUD header bar */
.lp-hud-header {
  position: absolute;
  top: 0; left: 0; right: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  background: linear-gradient(180deg, rgba(0,10,18,0.82) 0%, transparent 100%);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  pointer-events: none;
  z-index: 6;
}
.lp-hud-live {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  color: #00d4b0;
  letter-spacing: 0.1em;
  font-weight: 500;
}
.lp-hud-live-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #00d4b0;
  box-shadow: 0 0 6px #00d4b0;
  animation: lp-pulse 1.8s ease-in-out infinite;
}
.lp-hud-cam-id {
  color: #4a9a90;
  letter-spacing: 0.08em;
}
.lp-hud-timestamp {
  color: #3a7068;
  font-size: 0.55rem;
}

/* HUD footer bar */
.lp-hud-footer {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  background: linear-gradient(0deg, rgba(0,10,18,0.85) 0%, transparent 100%);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.55rem;
  color: #3a7068;
  letter-spacing: 0.06em;
  pointer-events: none;
  z-index: 6;
}
.lp-hud-footer-left { display: flex; flex-direction: column; gap: 0.15rem; }
.lp-hud-ai-badge {
  color: #00d4b0;
  font-size: 0.55rem;
  letter-spacing: 0.08em;
  animation: lp-pulse 2.4s ease-in-out infinite;
}

/* Decorative AI detection boxes — no AI calls, purely presentational */
.lp-det-box {
  position: absolute;
  border: 1px solid;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  z-index: 4;
}
.lp-det-label {
  position: absolute;
  top: -18px;
  left: -1px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.55rem;
  padding: 1px 5px;
  white-space: nowrap;
  letter-spacing: 0.04em;
}
.lp-det-conf {
  font-size: 0.5rem;
  opacity: 0.8;
}

/* Detection box colors */
.lp-det-person {
  border-color: rgba(0,212,176,0.7);
  box-shadow: 0 0 6px rgba(0,212,176,0.2), inset 0 0 12px rgba(0,212,176,0.04);
  animation: lp-det-pulse 3.2s ease-in-out infinite;
}
.lp-det-person .lp-det-label {
  background: rgba(0,212,176,0.15);
  color: #00d4b0;
  border: 1px solid rgba(0,212,176,0.4);
}
.lp-det-vehicle {
  border-color: rgba(234,179,8,0.6);
  box-shadow: 0 0 6px rgba(234,179,8,0.15);
  animation: lp-det-pulse 4s ease-in-out infinite 0.8s;
}
.lp-det-vehicle .lp-det-label {
  background: rgba(234,179,8,0.12);
  color: #fde047;
  border: 1px solid rgba(234,179,8,0.35);
}
.lp-det-unknown {
  border-color: rgba(239,68,68,0.6);
  box-shadow: 0 0 6px rgba(239,68,68,0.15);
  animation: lp-det-pulse 2.8s ease-in-out infinite 0.4s;
}
.lp-det-unknown .lp-det-label {
  background: rgba(239,68,68,0.12);
  color: #fca5a5;
  border: 1px solid rgba(239,68,68,0.35);
}
@keyframes lp-det-pulse {
  0%,100% { opacity: 1; }
  45%      { opacity: 0.6; }
  50%      { opacity: 0.9; }
}

/* Video fallback */
.lp-video-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  color: #2d5e57;
  letter-spacing: 0.1em;
}
.lp-cam-label {
  font-size: 0.65rem;
  color: #3a7068;
  font-family: 'JetBrains Mono', monospace;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.lp-cam-live { color: #00d4b0; }
.lp-alert-list {
  background: rgba(0,20,28,0.9);
  border: 1px solid rgba(0,200,170,0.10);
  border-radius: 8px;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.lp-alert-item {
  padding: 0.4rem 0.6rem;
  border-radius: 5px;
  font-size: 0.65rem;
  font-family: 'JetBrains Mono', monospace;
  border-left: 2px solid;
}
.lp-alert-critical { background: rgba(220,38,38,0.08); border-color: #dc2626; color: #fca5a5; }
.lp-alert-medium { background: rgba(234,179,8,0.08); border-color: #ca8a04; color: #fde047; }
.lp-alert-low { background: rgba(0,200,170,0.08); border-color: #00d4b0; color: #a0d8cf; }

/* ── Stats row ── */
.lp-stats-section {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4,1fr);
  gap: 1px;
  border-top: 1px solid rgba(0,200,170,0.10);
  border-bottom: 1px solid rgba(0,200,170,0.10);
  background: rgba(0,200,170,0.06);
}
.lp-stat-box {
  padding: 2.5rem 2rem;
  text-align: center;
  background: rgba(1,11,15,0.85);
}
.lp-stat-box-value {
  font-size: 2.8rem;
  font-weight: 800;
  background: linear-gradient(135deg, #00d4b0, #06b6d4);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
}
.lp-stat-box-label {
  font-size: 0.8rem;
  color: #5a9e95;
  margin-top: 0.5rem;
  font-weight: 500;
  letter-spacing: 0.04em;
}

/* ── Features ── */
.lp-features {
  position: relative;
  z-index: 1;
  padding: 6rem 3rem;
  max-width: 1200px;
  margin: 0 auto;
}
.lp-section-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  color: #00d4b0;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  margin-bottom: 0.75rem;
}
.lp-section-title {
  font-size: clamp(1.8rem, 4vw, 2.8rem);
  font-weight: 700;
  line-height: 1.15;
  max-width: 520px;
  background: linear-gradient(135deg, #e2f0ef 0%, #00d4b0 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 3rem;
}
.lp-feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
}
.lp-feature-card {
  background: rgba(0,25,35,0.7);
  border: 1px solid rgba(0,200,170,0.10);
  border-radius: 12px;
  padding: 1.75rem;
  transition: all 0.3s;
  position: relative;
  overflow: hidden;
}
.lp-feature-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,212,176,0.4), transparent);
  transform: scaleX(0);
  transform-origin: center;
  transition: transform 0.35s;
}
.lp-feature-card:hover {
  border-color: rgba(0,200,170,0.25);
  background: rgba(0,35,50,0.8);
  transform: translateY(-3px);
  box-shadow: 0 12px 40px rgba(0,180,150,0.12);
}
.lp-feature-card:hover::before {
  transform: scaleX(1);
}
.lp-feature-icon {
  width: 44px; height: 44px;
  border-radius: 10px;
  background: rgba(0,180,150,0.12);
  border: 1px solid rgba(0,200,170,0.2);
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 1rem;
  font-size: 1.3rem;
}
.lp-feature-name {
  font-size: 1rem;
  font-weight: 600;
  color: #c8ede9;
  margin-bottom: 0.5rem;
}
.lp-feature-desc {
  font-size: 0.82rem;
  color: #5a9e95;
  line-height: 1.6;
}

/* ── CTA section ── */
.lp-cta-section {
  position: relative;
  z-index: 1;
  text-align: center;
  padding: 5rem 2rem 7rem;
}
.lp-cta-card {
  max-width: 700px;
  margin: 0 auto;
  background: rgba(0,30,42,0.6);
  border: 1px solid rgba(0,200,170,0.15);
  border-radius: 20px;
  padding: 3.5rem 2.5rem;
  position: relative;
  overflow: hidden;
}
.lp-cta-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at 50% 0%, rgba(0,180,150,0.12), transparent 65%);
  pointer-events: none;
}
.lp-cta-title {
  font-size: clamp(1.6rem, 4vw, 2.4rem);
  font-weight: 700;
  background: linear-gradient(135deg, #fff, #00d4b0);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 0.75rem;
}
.lp-cta-sub {
  color: #7ab8b0;
  font-size: 0.95rem;
  margin-bottom: 2rem;
  line-height: 1.6;
}
.lp-cta-btns {
  display: flex;
  gap: 1rem;
  justify-content: center;
  flex-wrap: wrap;
}

/* ── Footer ── */
.lp-footer {
  position: relative;
  z-index: 1;
  text-align: center;
  padding: 1.5rem;
  border-top: 1px solid rgba(0,200,170,0.08);
  font-size: 0.75rem;
  color: #2d5e57;
  font-family: 'JetBrains Mono', monospace;
}

@media (max-width: 768px) {
  .lp-nav { padding: 1rem 1.25rem; }
  .lp-features { padding: 4rem 1.5rem; }
  .lp-feature-grid { grid-template-columns: 1fr; }
  .lp-stats-section { grid-template-columns: 1fr 1fr; }
  .lp-hero-dashboard { grid-template-columns: 1fr 1fr; }
  .lp-feed-row { grid-template-columns: 1fr; }
  .lp-hud-cam-id { display: none; }
}
`;

const FEATURES = [
  { icon: '🎯', name: 'YOLOv8 Detection', desc: 'Real-time multi-class object detection with sub-100ms latency. Identifies persons, vehicles, and objects across all surveillance feeds.' },
  { icon: '🔍', name: 'AI Behavior Analysis', desc: 'Automated running, crawling, and throwing detection. Behavioral anomalies trigger instant priority alerts.' },
  { icon: '🏃', name: 'ByteTrack Tracking', desc: 'Multi-object tracking assigns persistent identity tags across frames. Every subject is monitored from entry to exit.' },
  { icon: '🚘', name: 'ANPR / Plate Recognition', desc: 'Automatic Number Plate Recognition with watchlist cross-check. Unauthorized vehicles flagged in real time.' },
  { icon: '🔐', name: 'Face Recognition (FRS)', desc: 'Authorized personnel verification with confidence scoring. Unknown faces trigger CRITICAL alerts automatically.' },
  { icon: '⚡', name: 'Restricted Zone Defense', desc: 'Draw custom restricted polygons and virtual fences per camera. Intrusion and loitering triggers timed-dwell alerts.' },
];

export default function LandingPage({ onLogin, onRegister }) {
  const styleRef = useRef(null);

  useEffect(() => {
    if (!document.getElementById('lp-styles')) {
      const el = document.createElement('style');
      el.id = 'lp-styles';
      el.textContent = LANDING_CSS;
      document.head.appendChild(el);
      styleRef.current = el;
    }
    return () => {
      // Keep styles while navigating — they'll be cleaned up when auth completes
    };
  }, []);

  return (
    <div className="lp-root">
      {/* Background Layers */}
      <div className="lp-bg-image" />
      <div className="lp-grid-bg" />
      <div className="lp-topo-bg" />
      <div className="lp-radar-layer" />

      <div className="lp-orb lp-orb-1" />
      <div className="lp-orb lp-orb-2" />
      <div className="lp-orb lp-orb-3" />

      {/* Decorative tactical coordinate watermarks */}
      <div className="lp-coord-tag lp-coord-tl">LAT: 34.5201° N · LON: 74.8820° E // SECTOR 04</div>
      <div className="lp-coord-tag lp-coord-tr">DEFENSE GRID // LEVEL 3 CLEARANCE</div>

      {/* Nav */}
      <nav className="lp-nav">
        <div className="lp-nav-logo">
          <div className="lp-nav-logo-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L2 7v10l10 5 10-5V7L12 2z" stroke="#00d4b0" strokeWidth="1.5" fill="none"/>
              <circle cx="12" cy="12" r="3" fill="#00d4b0" opacity="0.7"/>
            </svg>
          </div>
          <span className="lp-nav-logo-text">SENTINEL AI</span>
          <span className="lp-nav-badge">v2.0</span>
        </div>
        <div className="lp-nav-actions">
          <button id="nav-login-btn" className="lp-btn-ghost" onClick={onLogin}>Login</button>
          <button id="nav-register-btn" className="lp-btn-primary" onClick={onRegister}>Get Access</button>
        </div>
      </nav>

      {/* Hero */}
      <section className="lp-hero">
        <div className="lp-hero-tag">Operational Intelligence Platform</div>
        <h1 className="lp-hero-title">
          AI-Powered Border<br />Surveillance Command
        </h1>
        <p className="lp-hero-sub">
          Real-time threat detection, autonomous behavior analysis, and multi-camera
          command across critical border infrastructure — all in one classified platform.
        </p>
        <div className="lp-hero-cta">
          <button id="hero-get-access-btn" className="lp-btn-cta-primary" onClick={onRegister}>
            <span>⚡</span> Get Access
          </button>
          <button id="hero-sign-in-btn" className="lp-btn-cta-secondary" onClick={onLogin}>
            Sign In to Dashboard →
          </button>
        </div>

        {/* Dashboard Preview */}
        <div className="lp-hero-visual">
          <div className="lp-hero-visual-bar">
            <span className="lp-dot lp-dot-r" />
            <span className="lp-dot lp-dot-y" />
            <span className="lp-dot lp-dot-g" />
            <span className="lp-visual-url">sentinel-ai.ops / dashboard</span>
          </div>
          <div className="lp-hero-dashboard">
            {[
              { label: 'Active Feeds', value: '4', sub: 'All Online' },
              { label: 'Persons Detected', value: '17', sub: 'YOLO AI' },
              { label: 'Vehicles', value: '3', sub: 'ANPR Active' },
              { label: 'AI Detections', value: '142', sub: 'Session Total' },
            ].map(s => (
              <div key={s.label} className="lp-stat-mini">
                <div className="lp-stat-mini-label">{s.label}</div>
                <div className="lp-stat-mini-value">{s.value}</div>
                <div className="lp-stat-mini-sub">{s.sub}</div>
              </div>
            ))}
            <div className="lp-feed-row">
              <div className="lp-feed-cam">
              {/* Surveillance Video Placeholder with real video */}
              <div className="lp-cam-placeholder">
                {/* Real surveillance video — autoplay, loop, muted, decorative */}
                <video
                  aria-hidden="true"
                  className="lp-surv-video"
                  src="/surveillance_demo.mp4"
                  autoPlay
                  loop
                  muted
                  playsInline
                  onError={(e) => { e.currentTarget.style.display = 'none'; }}
                />

                {/* Teal tint / night-vision overlay */}
                <div className="lp-video-tint" aria-hidden="true" />

                {/* CSS scan line sweep */}
                <div className="lp-cam-scan-line" aria-hidden="true" />

                {/* HUD corner brackets */}
                <div className="lp-hud-corner lp-hud-corner-tl" aria-hidden="true" />
                <div className="lp-hud-corner lp-hud-corner-tr" aria-hidden="true" />
                <div className="lp-hud-corner lp-hud-corner-bl" aria-hidden="true" />
                <div className="lp-hud-corner lp-hud-corner-br" aria-hidden="true" />

                {/* HUD header */}
                <div className="lp-hud-header" aria-hidden="true">
                  <div className="lp-hud-live">
                    <div className="lp-hud-live-dot" />
                    LIVE
                  </div>
                  <span className="lp-hud-cam-id">CAM-01 · SECTOR 04 — NORTH PERIMETER</span>
                  <span className="lp-hud-timestamp">AI ANALYSIS: ACTIVE</span>
                </div>

                {/* Decorative AI detection boxes — purely presentational */}
                {/* Person #1 */}
                <div
                  aria-hidden="true"
                  className="lp-det-box lp-det-person"
                  style={{ top: '28%', left: '18%', width: '11%', height: '38%' }}
                >
                  <span className="lp-det-label">PERSON <span className="lp-det-conf">0.94</span></span>
                </div>

                {/* Person #2 */}
                <div
                  aria-hidden="true"
                  className="lp-det-box lp-det-person"
                  style={{ top: '32%', left: '48%', width: '10%', height: '34%' }}
                >
                  <span className="lp-det-label">PERSON <span className="lp-det-conf">0.87</span></span>
                </div>

                {/* Unknown subject */}
                <div
                  aria-hidden="true"
                  className="lp-det-box lp-det-unknown"
                  style={{ top: '25%', left: '70%', width: '12%', height: '40%' }}
                >
                  <span className="lp-det-label">UNKNOWN <span className="lp-det-conf">0.81</span></span>
                </div>

                {/* HUD footer */}
                <div className="lp-hud-footer" aria-hidden="true">
                  <div className="lp-hud-footer-left">
                    <span className="lp-hud-ai-badge">● SCANNING</span>
                    <span>OBJECT DETECTION · MULTI-OBJECT TRACKING</span>
                  </div>
                  <span>PERIMETER MONITORING · THREAT LEVEL: ELEVATED</span>
                </div>

                {/* Fallback shown only if video fails */}
                <div className="lp-video-fallback" style={{display:'none'}} aria-hidden="true">
                  <span>SURVEILLANCE FEED</span>
                  <span>INITIALIZING...</span>
                </div>
              </div>
                <div className="lp-cam-label">
                  <span className="lp-cam-live">● LIVE</span>
                  Sector 4 — Alpha · North Checkpoint
                </div>
              </div>
              <div className="lp-alert-list">
                <div style={{fontSize:'0.65rem', color:'#3a7068', fontFamily:"'JetBrains Mono',monospace", marginBottom:'0.25rem'}}>THREAT ALERTS</div>
                <div className="lp-alert-item lp-alert-critical">CRITICAL · Running Person #7</div>
                <div className="lp-alert-item lp-alert-medium">HIGH · Unknown Face</div>
                <div className="lp-alert-item lp-alert-low">INFO · Personnel Verified</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Row */}
      <div className="lp-stats-section">
        {[
          { value: '< 100ms', label: 'Detection Latency' },
          { value: '8+', label: 'AI Detection Modules' },
          { value: '4 Cam', label: 'Simultaneous Streams' },
          { value: '24 / 7', label: 'Autonomous Operation' },
        ].map(s => (
          <div key={s.label} className="lp-stat-box">
            <div className="lp-stat-box-value">{s.value}</div>
            <div className="lp-stat-box-label">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Features */}
      <section className="lp-features">
        <div className="lp-section-tag">// Capabilities</div>
        <h2 className="lp-section-title">Military-grade AI<br />surveillance modules</h2>
        <div className="lp-feature-grid">
          {FEATURES.map(f => (
            <div key={f.name} className="lp-feature-card">
              <div className="lp-feature-icon">{f.icon}</div>
              <div className="lp-feature-name">{f.name}</div>
              <div className="lp-feature-desc">{f.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA Section */}
      <section className="lp-cta-section">
        <div className="lp-cta-card">
          <h2 className="lp-cta-title">Ready to deploy?</h2>
          <p className="lp-cta-sub">
            Create your operator account to access the full Sentinel AI command dashboard.
            All AI modules, camera arrays, and threat analytics included.
          </p>
          <div className="lp-cta-btns">
            <button id="cta-create-account-btn" className="lp-btn-cta-primary" onClick={onRegister}>
              Create Account
            </button>
            <button id="cta-sign-in-btn" className="lp-btn-cta-secondary" onClick={onLogin}>
              Sign In →
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="lp-footer">
        © 2026 Sentinel AI Surveillance Platform · SIH Border Defense Initiative · All rights classified
      </footer>
    </div>
  );
}
