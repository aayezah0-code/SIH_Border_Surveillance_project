import React from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import defenceBg from '../../assets/defence_bg.png';

const Layout = ({ children, activeTab, onSelectTab, user, onLogout }) => {
  const TICKER_MSG = [
    'SYSTEM STATUS: OPERATIONAL',
    '·',
    'YOLOv8 GPU CORE: ACTIVE',
    '·',
    'AI INFERENCE LATENCY: 14ms',
    '·',
    'SECTOR 04 — PERIMETER ARMED',
    '·',
    'FACE RECOGNITION: STANDBY',
    '·',
    'ANPR ENGINE: SCANNING',
    '·',
    'BYTETRACK MULTI-OBJ: LIVE',
    '·',
    'ENCRYPTED CHANNEL: AES-256',
    '·',
    'THREAT LEVEL: ELEVATED',
    '·',
    'ALL FEEDS NOMINAL',
    '·',
  ].join('   ');

  return (
    <div className="flex h-screen bg-[#010b0f] text-[#e2f0ef] overflow-hidden font-sans relative">

      {/* ── Fixed atmospheric defence background ───────────────────── */}
      <div
        className="fixed inset-0 pointer-events-none z-0"
        style={{
          backgroundImage: `linear-gradient(180deg, rgba(1, 11, 15, 0.25) 0%, rgba(1, 18, 25, 0.12) 45%, rgba(1, 11, 15, 0.38) 100%), radial-gradient(circle at 60% 30%, rgba(0, 212, 176, 0.04) 0%, transparent 65%), url('${defenceBg}')`,
          backgroundSize: 'cover',
          backgroundPosition: 'center 30%',
          backgroundRepeat: 'no-repeat',
        }}
      />

      {/* Tactical crosshatch grid */}
      <div
        className="fixed inset-0 pointer-events-none z-0"
        style={{
          backgroundImage:
            'linear-gradient(rgba(0,210,180,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(0,210,180,0.02) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      {/* Ambient glow orb — top left */}
      <div
        className="fixed pointer-events-none z-0 animate-ambient-glow"
        style={{
          width: 500, height: 500,
          top: -150, left: -80,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(0,180,150,0.08) 0%, transparent 70%)',
          filter: 'blur(90px)',
        }}
      />

      {/* Ambient glow orb — bottom right */}
      <div
        className="fixed pointer-events-none z-0"
        style={{
          width: 380, height: 380,
          bottom: 40, right: -80,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(6,182,212,0.07) 0%, transparent 70%)',
          filter: 'blur(80px)',
          animation: 'ambient-glow 10s ease-in-out infinite 3s',
        }}
      />

      {/* ── Main layout ─────────────────────────────────────────────── */}
      <Sidebar activeTab={activeTab} onSelectTab={onSelectTab} />

      <div className="flex-1 flex flex-col min-w-0 relative z-10">
        <Header user={user} onLogout={onLogout} />

        <main className="flex-1 overflow-y-auto p-4 md:p-6 bg-transparent">
          {children}
        </main>

        {/* Bottom telemetry marquee bar */}
        <div className="shrink-0 h-6 bg-[#010e15]/90 border-t border-[#00d4b0]/10 flex items-center overflow-hidden">
          <div className="shrink-0 px-2.5 flex items-center gap-1.5 border-r border-[#00d4b0]/15 h-full bg-[#00d4b0]/8">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00d4b0] animate-pulse shadow-[0_0_6px_#00d4b0]" />
            <span className="font-mono text-[9px] text-[#00d4b0] font-bold tracking-widest">SENTINEL AI</span>
          </div>
          <div className="marquee-wrap flex-1">
            <div className="marquee-track font-mono text-[9px] text-[#3a7068] tracking-wider px-4">
              <span>{TICKER_MSG}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>
              <span>{TICKER_MSG}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>
            </div>
          </div>
          <div className="shrink-0 px-2.5 h-full flex items-center border-l border-[#00d4b0]/15">
            <span className="font-mono text-[9px] text-[#2d5e57] tracking-widest">
              LAT: 34.52°N · LON: 74.88°E
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Layout;
