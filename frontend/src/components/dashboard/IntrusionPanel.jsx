import React from 'react';
import { ShieldAlert, Crosshair } from 'lucide-react';

const IntrusionPanel = ({ intrusions = [] }) => {
  return (
    <div className="bg-[#021822]/85 backdrop-blur-md border border-[#00d4b0]/16 rounded-xl flex flex-col h-full overflow-hidden shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
      {/* Header */}
      <div className="p-4 border-b border-[#00d4b0]/15 bg-[#01121a]/60 flex justify-between items-center gap-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-amber-500/10 border border-amber-500/20 shadow-[0_0_10px_rgba(245,158,11,0.15)]">
            <Crosshair className="w-4 h-4 text-amber-400" />
          </div>
          <div>
            <h3 className="font-mono font-bold text-xs text-white uppercase tracking-wider">RESTRICTED AREA INTRUSIONS</h3>
            <p className="text-[10px] font-mono text-[#6aa89f]">REAL-TIME ZONE / LINE BREACH FEED</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="flex items-center gap-1 text-[10px] font-mono font-bold text-red-400 bg-red-500/10 px-2 py-0.5 rounded-full border border-red-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse shadow-[0_0_6px_#ef4444]" />
            LIVE
          </span>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {intrusions.length === 0 ? (
          <div className="py-12 px-4 text-center">
            <div className="w-10 h-10 rounded-full bg-slate-800/60 border border-slate-700 flex items-center justify-center mx-auto mb-2 text-slate-500">
              <ShieldAlert className="w-5 h-5 opacity-40" />
            </div>
            <p className="text-xs font-mono text-slate-400 font-semibold">NO ACTIVE RESTRICTED AREAS</p>
            <p className="text-[10px] text-slate-500 mt-1">Draw and save a zone or line to monitor intrusions.</p>
          </div>
        ) : (
          intrusions.map((intrusion) => (
            <div
              key={intrusion.id}
              className="p-3 rounded-lg border border-red-500/40 bg-red-950/40 backdrop-blur-sm flex flex-col gap-1 transition-all hover:translate-x-0.5"
            >
              <h4 className={`text-xs font-bold font-mono tracking-wide ${intrusion.type === 'LOITERING DETECTED' ? 'text-amber-400' : 'text-white'}`}>
                {intrusion.type === 'LOITERING DETECTED' ? '🚨 LOITERING DETECTED' : 'RESTRICTED AREA INTRUSION'}
              </h4>
              <div className="flex items-center gap-1.5 flex-wrap my-1">
                <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/40 uppercase">
                  {intrusion.objectClass}
                </span>
                {intrusion.trackId != null && (
                  <span className="text-[10px] font-mono font-bold text-cyan-300 bg-cyan-950/60 border border-cyan-500/40 px-1.5 py-0.5 rounded">
                    #{intrusion.trackId}
                  </span>
                )}
                {intrusion.confidence != null && (
                  <span className="text-[10px] font-mono text-slate-300 bg-slate-800/80 border border-slate-700/60 px-1.5 py-0.5 rounded">
                    {intrusion.confidence}% CONF
                  </span>
                )}
                {intrusion.duration_sec != null && (
                  <span className="text-[10px] font-mono font-bold text-amber-300 bg-amber-950/60 border border-amber-500/40 px-1.5 py-0.5 rounded">
                    {intrusion.duration_sec}s DWELL
                  </span>
                )}
              </div>
              <p className="text-[11px] font-mono text-slate-300 truncate">Source: {intrusion.camera}</p>
              <p className="text-[11px] font-mono font-bold text-amber-400 mt-1">
                {intrusion.description || intrusion.type}
              </p>
              <div className="flex justify-between items-center mt-1">
                <span className="text-[10px] font-mono text-slate-400">
                  Detected at {intrusion.time}
                </span>
                <span className="flex items-center gap-1 text-[10px] font-mono font-bold text-red-400">
                  <span className="w-1 h-1 rounded-full bg-red-400" />
                  {intrusion.status}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default IntrusionPanel;
