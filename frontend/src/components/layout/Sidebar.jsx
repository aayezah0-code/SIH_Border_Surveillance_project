import React from 'react';
import {
  LayoutDashboard,
  Video,
  Bell,
  History,
  Camera,
  Users,
  Settings,
  Radar,
  Cpu,
  Wifi,
  ShieldAlert,
} from 'lucide-react';

const Sidebar = ({ activeTab = 'defense-grid', onSelectTab = () => {} }) => {
  const menuItems = [
    { id: 'defense-grid',       icon: LayoutDashboard, label: 'Defense Grid',       badge: 'LIVE' },
    { id: 'video-feeds',        icon: Video,           label: 'Video Feeds',         count: '1 Online' },
    { id: 'threat-alerts',      icon: Bell,            label: 'Threat Alerts',       count: 'REAL-TIME' },
    { id: 'event-logbook',      icon: History,         label: 'Event Logbook' },
    { id: 'camera-array',       icon: Camera,          label: 'Camera Array',        count: '4 Sectors' },
    { id: 'personnel-registry', icon: Users,           label: 'Personnel Registry' },
    { id: 'model-config',       icon: Settings,        label: 'AI Model Config' },
  ];

  return (
    <div className="w-64 bg-[#010f17]/95 backdrop-blur-md text-slate-300 flex flex-col h-screen border-r border-[#00d4b0]/15 shrink-0 select-none shadow-[4px_0_30px_rgba(0,0,0,0.5)] relative overflow-hidden">

      {/* Subtle inner grid */}
      <div
        className="absolute inset-0 pointer-events-none z-0"
        style={{
          backgroundImage:
            'linear-gradient(rgba(0,212,176,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,176,0.025) 1px, transparent 1px)',
          backgroundSize: '32px 32px',
        }}
      />

      {/* Ambient side glow */}
      <div
        className="absolute pointer-events-none z-0"
        style={{
          width: 220, height: 220,
          bottom: 60, right: -80,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(0,180,150,0.14) 0%, transparent 70%)',
          filter: 'blur(50px)',
        }}
      />

      {/* ── Brand header ─────────────────────────────────────────── */}
      <div className="relative z-10 p-4 border-b border-[#00d4b0]/15 bg-[#010e15]/80">
        {/* Tactical top-left corner marker */}
        <div className="absolute top-1.5 left-1.5 w-2 h-2 border-t border-l border-[#00d4b0]/40 pointer-events-none" />
        <div className="absolute top-1.5 right-1.5 w-2 h-2 border-t border-r border-[#00d4b0]/40 pointer-events-none" />

        <div className="flex items-center gap-3">
          <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4b0]/15 to-[#06b6d4]/10 border border-[#00d4b0]/40 flex items-center justify-center shadow-[0_0_18px_rgba(0,212,176,0.22)] animate-glow-breathe">
            <Radar className="w-5 h-5 text-[#00d4b0] animate-radar" />
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-[#010f17] shadow-[0_0_8px_#10b981]" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-widest flex items-center gap-1.5 font-mono text-glow-teal">
              SENTINEL<span className="text-[#00d4b0]">AI</span>
            </h1>
            <p className="text-[9px] font-mono text-[#4a8a80] tracking-widest uppercase">
              BORDER DEFENSE OS <span className="text-[#00d4b0]">v2.0</span>
            </p>
          </div>
        </div>

        {/* System status row */}
        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[9px] font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#10b981]" />
            <span className="text-emerald-400 font-bold">OPERATIONAL</span>
          </div>
          <div className="flex items-center gap-1 text-[9px] font-mono text-slate-500">
            <Wifi className="w-2.5 h-2.5 text-[#00d4b0]" />
            <span className="text-[#3a7068]">SEC-LINK-04</span>
          </div>
        </div>
      </div>

      {/* ── Navigation List ───────────────────────────────────────── */}
      <nav className="relative z-10 flex-1 overflow-y-auto py-3 px-2.5 space-y-1">
        <div className="px-3 pb-2 pt-1 text-[9px] font-mono font-semibold text-[#4a8a80] uppercase tracking-widest flex items-center justify-between">
          <span>CORE MODULES</span>
          <span className="text-[8px] text-slate-600 font-mono">// SEC-04</span>
        </div>

        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <div key={item.id} className="relative">
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 bg-[#00d4b0] rounded-r shadow-[0_0_8px_#00d4b0]" />
              )}
              <button
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-[11px] font-medium transition-all duration-200 cursor-pointer ${
                  isActive
                    ? 'bg-gradient-to-r from-[#00d4b0]/18 to-[#06b6d4]/8 text-cyan-200 border border-[#00d4b0]/35 shadow-[0_0_12px_rgba(0,212,176,0.1)] font-semibold'
                    : 'text-slate-400 hover:bg-[#042432]/50 hover:text-slate-200 border border-transparent hover:border-[#00d4b0]/12'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-[#00d4b0]' : 'text-slate-500'}`} />
                  <span className="font-mono tracking-wide">{item.label}</span>
                </div>
                {item.badge && (
                  <span className="px-1.5 py-0.5 rounded text-[8px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    {item.badge}
                  </span>
                )}
                {item.count && (
                  <span className="text-[9px] font-mono text-slate-500">{item.count}</span>
                )}
              </button>
            </div>
          );
        })}

        {/* Divider */}
        <div className="my-3 mx-2 h-px bg-gradient-to-r from-transparent via-[#00d4b0]/15 to-transparent" />

        {/* Threat Level Status Card */}
        <div className="mx-1 p-2.5 rounded-lg bg-[#0a0a1a]/60 border border-[#00d4b0]/12">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <ShieldAlert className="w-3 h-3 text-amber-400" />
              <span className="font-mono text-[9px] text-slate-400 uppercase tracking-wider">Threat Level</span>
            </div>
            <span className="font-mono text-[9px] font-bold text-amber-400 bg-amber-500/10 border border-amber-500/25 px-1.5 py-0.5 rounded">ELEVATED</span>
          </div>
          <div className="w-full bg-slate-900/80 h-1 rounded-full overflow-hidden">
            <div className="bg-gradient-to-r from-amber-500 to-orange-500 h-full w-[60%] rounded-full shadow-[0_0_8px_rgba(234,179,8,0.4)]" />
          </div>
        </div>
      </nav>

      {/* ── System Telemetry Footer ───────────────────────────────── */}
      <div className="relative z-10 p-3 border-t border-[#00d4b0]/12 bg-[#010e15]/90 space-y-2">
        {/* YOLOv8 status */}
        <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
          <span className="flex items-center gap-1.5 text-slate-300">
            <Cpu className="w-3 h-3 text-[#00d4b0]" />
            YOLOv8n GPU
          </span>
          <span className="text-emerald-400 font-bold tracking-wide text-[9px]">● ACTIVE</span>
        </div>

        {/* GPU utilization bar */}
        <div className="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden border border-white/5">
          <div className="bg-gradient-to-r from-[#00d4b0] to-[#06b6d4] h-full w-[42%] rounded-full animate-pulse shadow-[0_0_8px_rgba(0,212,176,0.45)]" />
        </div>

        {/* Telemetry row */}
        <div className="flex items-center justify-between text-[9px] font-mono text-slate-500 pt-0.5">
          <span>LATENCY: <span className="text-[#00d4b0]">14ms</span></span>
          <span>FPS: <span className="text-[#00d4b0] font-semibold">25.0</span></span>
          <span>GPU: <span className="text-amber-400">42%</span></span>
        </div>

        {/* Bottom coord tag */}
        <div className="pt-1 border-t border-[#00d4b0]/08 font-mono text-[8px] text-[#2d5e57] flex justify-between">
          <span>LAT: 34.52°N</span>
          <span>LON: 74.88°E</span>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
