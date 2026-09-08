import React from 'react';

const StatCard = ({ title, value, icon: Icon, trend, trendLabel, colorClass }) => {
  return (
    <div className="relative group bg-[#021822]/85 backdrop-blur-md border border-[#00d4b0]/16 hover:border-[#00d4b0]/35 rounded-xl p-4.5 flex flex-col justify-between transition-all duration-300 hover:shadow-[0_4px_25px_rgba(0,0,0,0.5)] overflow-hidden">
      {/* Top subtle ambient glow line */}
      <div className={`absolute top-0 left-0 right-0 h-[2px] ${colorClass} opacity-85`} />

      <div className="flex justify-between items-start mb-3">
        <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-[#6aa89f]">
          {title}
        </span>
        <div className={`p-2.5 rounded-lg ${colorClass} bg-opacity-15 border border-white/5 group-hover:scale-105 transition-transform shadow-[0_0_12px_rgba(0,212,176,0.1)]`}>
          <Icon className={`w-4 h-4 ${colorClass.replace('bg-', 'text-')}`} />
        </div>
      </div>

      <div>
        <h3 className="text-2xl font-extrabold text-white tracking-tight mb-1.5 font-mono">
          {value}
        </h3>
        {trend && (
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <span className="font-mono font-bold text-[11px] px-1.5 py-0.5 rounded bg-[#011218] text-[#00d4b0] border border-[#00d4b0]/30">
              {trend}
            </span>
            <span className="truncate text-[11px] text-slate-400">{trendLabel}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default StatCard;
