import React, { useState, useEffect } from 'react';
import {
  Shield,
  Bell,
  Activity,
  Wifi,
  Radio,
  Lock,
  Volume2,
  VolumeX,
  Maximize2,
  RotateCw,
  LogOut,
  MapPin,
  Zap,
} from 'lucide-react';

const Header = ({ user, onLogout }) => {
  const [time, setTime] = useState(new Date());
  const [isMuted, setIsMuted] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  };

  const handleRefresh = () => {
    setIsRefreshing(true);
    window.location.reload();
  };

  const zulu = time.toUTCString().slice(17, 25); // HH:MM:SS UTC

  return (
    <header className="h-14 bg-[#01121a]/96 backdrop-blur-md border-b border-[#00d4b0]/14 flex items-center justify-between px-5 text-slate-300 sticky top-0 z-50 shadow-[0_4px_24px_rgba(0,0,0,0.4)] relative overflow-hidden">

      {/* Decorative scan line at bottom of header */}
      <div
        className="absolute bottom-0 left-0 right-0 h-px pointer-events-none"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(0,212,176,0.35), rgba(6,182,212,0.25), transparent)' }}
      />

      {/* ── Left: Sector & Mission Status ─────────────────── */}
      <div className="flex items-center gap-3">
        {/* Sector ID badge */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-[#00d4b0]/10 border border-[#00d4b0]/30 rounded-md">
          <Shield className="w-3.5 h-3.5 text-[#00d4b0]" />
          <span className="font-mono text-[11px] font-bold text-cyan-200 tracking-widest">
            DEFENSE GRID // ALPHA-7
          </span>
        </div>

        {/* System Armed indicator */}
        <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-emerald-500/10 text-emerald-400 rounded-full border border-emerald-500/20 text-[10px] font-mono font-bold">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#10b981]" />
          ARMED
        </div>

        {/* AI Core badge */}
        <div className="hidden md:flex items-center gap-1.5 font-mono text-[10px] text-slate-400 bg-[#021f2b]/60 px-2.5 py-1 rounded border border-[#00d4b0]/18">
          <Radio className="w-3 h-3 text-[#00d4b0] animate-pulse" />
          <span>YOLOv8 ACTIVE</span>
        </div>

        {/* GPS / Location */}
        <div className="hidden lg:flex items-center gap-1.5 font-mono text-[9px] text-[#3a7068] bg-[#010e15]/80 px-2 py-1 rounded border border-[#00d4b0]/10">
          <MapPin className="w-2.5 h-2.5 text-[#2d8a7e]" />
          <span>34.52°N · 74.88°E</span>
        </div>
      </div>

      {/* ── Right: Clock, Controls, Operator Profile ──────── */}
      <div className="flex items-center gap-3 sm:gap-4">

        {/* Zulu / local dual clock */}
        <div className="hidden md:flex flex-col items-end font-mono">
          <div className="flex items-baseline gap-1.5">
            <span className="text-[13px] font-bold text-slate-100 tracking-wider">
              {time.toLocaleTimeString('en-GB', { hour12: false })}
            </span>
            <span className="text-[9px] text-[#00d4b0] font-semibold">IST</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] text-slate-500">{zulu}</span>
            <span className="text-[8px] text-[#3a7068] border border-[#00d4b0]/15 px-1 rounded">ZULU</span>
          </div>
        </div>

        {/* Vertical separator */}
        <div className="hidden md:block w-px h-8 bg-[#00d4b0]/12" />

        {/* Alert indicator */}
        <div className="relative">
          <Bell className="w-4 h-4 text-slate-400 hover:text-[#00d4b0] transition-colors cursor-pointer" />
          <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-red-500 animate-threat-blink shadow-[0_0_6px_#ef4444]" />
        </div>

        {/* Signal indicator */}
        <div className="flex items-center gap-1 text-[9px] font-mono text-emerald-400 bg-emerald-500/8 border border-emerald-500/18 px-2 py-1 rounded">
          <Wifi className="w-3 h-3" />
          <span className="hidden sm:inline">LINK ON</span>
        </div>

        {/* Quick toggles group */}
        <div className="flex items-center gap-0.5 bg-[#021f2b]/80 p-1 rounded-lg border border-[#00d4b0]/18 shadow-[0_0_12px_rgba(0,0,0,0.2)]">
          <button
            id="header-refresh-btn"
            onClick={handleRefresh}
            className={`p-1.5 rounded hover:bg-[#00d4b0]/15 text-slate-400 hover:text-[#00d4b0] active:scale-95 transition-all cursor-pointer ${
              isRefreshing ? 'text-[#00d4b0] bg-[#00d4b0]/15' : ''
            }`}
            title="Refresh Application"
            aria-label="Refresh Application"
          >
            <RotateCw className={`w-3.5 h-3.5 transition-transform duration-300 ${isRefreshing ? 'animate-spin text-[#00d4b0]' : ''}`} />
          </button>
          <button
            onClick={() => setIsMuted(!isMuted)}
            className="p-1.5 rounded hover:bg-[#00d4b0]/12 text-slate-400 hover:text-white transition-colors cursor-pointer"
            title={isMuted ? 'Unmute Alarm Chime' : 'Mute Alarm Chime'}
            aria-label={isMuted ? 'Unmute Alarm Chime' : 'Mute Alarm Chime'}
          >
            {isMuted
              ? <VolumeX className="w-3.5 h-3.5 text-red-400" />
              : <Volume2 className="w-3.5 h-3.5 text-emerald-400" />
            }
          </button>
          <button
            onClick={toggleFullscreen}
            className="p-1.5 rounded hover:bg-[#00d4b0]/12 text-slate-400 hover:text-white transition-colors cursor-pointer"
            title="Toggle Command Fullscreen"
            aria-label="Toggle Command Fullscreen"
          >
            <Maximize2 className="w-3.5 h-3.5 text-slate-300" />
          </button>
        </div>

        {/* Vertical separator */}
        <div className="w-px h-8 bg-[#00d4b0]/12" />

        {/* Operator profile chip */}
        <div className="flex items-center gap-2.5">
          <div className="text-right hidden sm:block">
            <div className="flex items-center justify-end gap-1">
              <p className="text-[11px] font-bold text-white tracking-wide font-mono">
                {user?.full_name || user?.username?.toUpperCase() || 'OPERATOR'}
              </p>
              <Lock className="w-2.5 h-2.5 text-amber-400" />
            </div>
            <p className="text-[9px] font-mono text-[#00d4b0] tracking-wider">
              {user?.role?.toUpperCase() || 'OPERATOR'} · CLEARANCE L3
            </p>
          </div>

          {/* Avatar */}
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#00b896] to-[#06b6d4] flex items-center justify-center border border-[#00d4b0]/45 shadow-[0_0_12px_rgba(0,212,176,0.3)]">
            <span className="font-mono text-xs font-bold text-[#010e14]">
              {(user?.username?.[0] || 'O').toUpperCase()}
            </span>
          </div>

          {/* Logout */}
          {onLogout && (
            <button
              id="header-logout-btn"
              onClick={onLogout}
              title="Sign Out"
              className="p-1.5 rounded hover:bg-red-900/35 text-slate-500 hover:text-red-400 transition-colors border border-transparent hover:border-red-500/28 cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
