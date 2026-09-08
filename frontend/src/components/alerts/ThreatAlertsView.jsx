import React, { useState, useMemo } from 'react';
import { 
  ShieldAlert, 
  AlertTriangle, 
  AlertCircle, 
  ShieldCheck, 
  Info, 
  WifiOff, 
  Camera, 
  Search, 
  Filter, 
  Trash2, 
  Clock, 
  Activity, 
  Crosshair, 
  Tag, 
  Layers,
  Radio
} from 'lucide-react';
import { EvidenceModal } from '../dashboard/AlertPanel';

/**
 * ThreatAlertsView
 * 
 * Dedicated full-screen Threat Alerts management & analysis page.
 * Reuses the existing alert data flow, WebSocket connection state, and EvidenceModal.
 */
export default function ThreatAlertsView({
  alerts = [],
  isConnected = false,
  onClearAlerts,
}) {
  const [filterSeverity, setFilterSeverity] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [evidenceAlert, setEvidenceAlert] = useState(null);

  // Helper to map severity to styling tokens
  const getSeverityConfig = (severity = '') => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return { 
          icon: ShieldAlert,   
          color: 'text-red-400',     
          bg: 'bg-red-950/40',     
          border: 'border-red-500/40',    
          badge: 'bg-red-500/20 text-red-400 border border-red-500/30',
          indicator: 'bg-red-500'
        };
      case 'high':
        return { 
          icon: AlertTriangle, 
          color: 'text-orange-400',  
          bg: 'bg-orange-950/40',  
          border: 'border-orange-500/40', 
          badge: 'bg-orange-500/20 text-orange-400 border border-orange-500/30',
          indicator: 'bg-orange-500'
        };
      case 'medium':
        return { 
          icon: AlertCircle,   
          color: 'text-yellow-400',  
          bg: 'bg-yellow-950/40',  
          border: 'border-yellow-500/40', 
          badge: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
          indicator: 'bg-yellow-500'
        };
      case 'safe':
      case 'authorized':
        return { 
          icon: ShieldCheck,   
          color: 'text-emerald-400', 
          bg: 'bg-emerald-950/40', 
          border: 'border-emerald-500/40', 
          badge: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
          indicator: 'bg-emerald-500'
        };
      case 'low':
      default:
        return { 
          icon: Info,          
          color: 'text-cyan-400',    
          bg: 'bg-cyan-950/40',    
          border: 'border-cyan-500/40',   
          badge: 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30',
          indicator: 'bg-cyan-500'
        };
    }
  };

  // Summary Metrics calculated from real alerts array
  const metrics = useMemo(() => {
    const total = alerts.length;
    const critical = alerts.filter(a => a.severity?.toLowerCase() === 'critical').length;
    const high = alerts.filter(a => a.severity?.toLowerCase() === 'high').length;
    const medium = alerts.filter(a => a.severity?.toLowerCase() === 'medium').length;
    const lowOrSafe = alerts.filter(a => {
      const s = a.severity?.toLowerCase();
      return s === 'low' || s === 'safe' || s === 'authorized' || !s;
    }).length;
    return { total, critical, high, medium, lowOrSafe };
  }, [alerts]);

  // Filter and search execution
  const filteredAlerts = useMemo(() => {
    return alerts.filter(a => {
      // 1. Severity filter
      if (filterSeverity !== 'ALL') {
        const s = (a.severity || '').toUpperCase();
        if (filterSeverity === 'LOW') {
          if (s !== 'LOW' && s !== 'SAFE' && s !== 'AUTHORIZED') return false;
        } else if (s !== filterSeverity) {
          return false;
        }
      }

      // 2. Search query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesType = (a.type || '').toLowerCase().includes(q);
        const matchesDesc = (a.description || '').toLowerCase().includes(q);
        const matchesCam  = (a.camera || '').toLowerCase().includes(q);
        const matchesObj  = (a.objectClass || '').toLowerCase().includes(q);
        const matchesTrk  = a.trackId != null && String(a.trackId).toLowerCase().includes(q);
        const matchesObjTrk = a.object_track_id != null && String(a.object_track_id).toLowerCase().includes(q);
        const matchesSub  = (a.activity_subtype || '').toLowerCase().includes(q);
        if (!matchesType && !matchesDesc && !matchesCam && !matchesObj && !matchesTrk && !matchesObjTrk && !matchesSub) {
          return false;
        }
      }

      return true;
    });
  }, [alerts, filterSeverity, searchQuery]);

  // Check if an alert is eligible for forensic evidence snapshots
  const isEvidenceEligible = (alert) => {
    const sev = (alert.severity || '').toLowerCase();
    return sev === 'critical' || sev === 'high' || sev === 'medium';
  };

  return (
    <div className="flex flex-col gap-6 w-full min-w-0 pb-12">
      {/* Evidence Viewer Modal */}
      {evidenceAlert && (
        <EvidenceModal
          alert={evidenceAlert}
          onClose={() => setEvidenceAlert(null)}
        />
      )}

      {/* ── 1. PAGE HEADER ────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-[#021822]/90 border border-[#00d4b0]/20 rounded-xl p-5 backdrop-blur-md shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/30 shadow-[0_0_15px_rgba(239,68,68,0.15)]">
              <ShieldAlert className="w-5 h-5 text-red-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold font-mono tracking-wider text-white flex items-center gap-2">
                THREAT ALERTS
                <span className="text-[11px] font-sans px-2 py-0.5 rounded bg-red-500/10 border border-red-500/30 text-red-400 font-semibold uppercase tracking-normal">
                  REAL-TIME INCIDENT MONITOR
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Real-time security event monitoring &amp; forensic analysis
              </p>
            </div>
          </div>
        </div>

        {/* Live WebSocket Status & Optional UI Clear */}
        <div className="flex items-center gap-3">
          {isConnected ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono text-xs font-bold shadow-[0_0_12px_rgba(16,185,129,0.15)]">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>WS LIVE</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#02141d] border border-[#00d4b0]/20 text-slate-400 font-mono text-xs font-bold">
              <WifiOff className="w-3.5 h-3.5" />
              <span>WS OFF</span>
            </div>
          )}

          {onClearAlerts && alerts.length > 0 && (
            <button
              type="button"
              onClick={onClearAlerts}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium text-slate-400 hover:text-red-400 bg-[#02141d] hover:bg-red-500/10 border border-[#00d4b0]/15 hover:border-red-500/30 transition-colors cursor-pointer"
              title="Clear current local session alerts"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Clear Session</span>
            </button>
          )}
        </div>
      </div>

      {/* ── 2. SUMMARY METRICS ROW ────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Total Alerts</p>
            <p className="text-xl font-bold font-mono text-white mt-1">{metrics.total}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
            <Layers className="w-4 h-4 text-cyan-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Critical</p>
            <p className="text-xl font-bold font-mono text-red-400 mt-1">{metrics.critical}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <ShieldAlert className="w-4 h-4 text-red-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">High</p>
            <p className="text-xl font-bold font-mono text-orange-400 mt-1">{metrics.high}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-orange-500/10 border border-orange-500/20 flex items-center justify-center">
            <AlertTriangle className="w-4 h-4 text-orange-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Medium</p>
            <p className="text-xl font-bold font-mono text-yellow-400 mt-1">{metrics.medium}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-yellow-500/10 border border-yellow-500/20 flex items-center justify-center">
            <AlertCircle className="w-4 h-4 text-yellow-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between col-span-2 sm:col-span-1 shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Low / Safe</p>
            <p className="text-xl font-bold font-mono text-cyan-300 mt-1">{metrics.lowOrSafe}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
          </div>
        </div>
      </div>

      {/* ── 3. FILTER & SEARCH TOOLBAR ────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-[#021822]/80 border border-[#00d4b0]/20 rounded-xl p-3">
        {/* Severity Filter Tabs */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {[
            { id: 'ALL', label: 'ALL', count: metrics.total },
            { id: 'CRITICAL', label: 'CRITICAL', count: metrics.critical },
            { id: 'HIGH', label: 'HIGH', count: metrics.high },
            { id: 'MEDIUM', label: 'MEDIUM', count: metrics.medium },
            { id: 'LOW', label: 'LOW / SAFE', count: metrics.lowOrSafe },
          ].map(tab => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setFilterSeverity(tab.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all cursor-pointer flex items-center gap-1.5 ${
                filterSeverity === tab.id
                  ? 'bg-[#00d4b0]/20 text-[#00d4b0] border border-[#00d4b0]/40 font-bold shadow-[0_0_10px_rgba(0,212,176,0.15)]'
                  : 'text-slate-400 hover:text-slate-200 bg-[#02141d] hover:bg-[#032333] border border-[#00d4b0]/15'
              }`}
            >
              <span>{tab.label}</span>
              <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                filterSeverity === tab.id ? 'bg-[#00d4b0]/20 text-[#00d4b0]' : 'bg-[#010e14] text-slate-500'
              }`}>
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        {/* Search Field */}
        <div className="relative min-w-[240px] sm:w-72">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search alerts, tracks, cameras…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#010e15] border border-[#00d4b0]/20 focus:border-[#00d4b0]/60 rounded-lg pl-9 pr-3 py-1.5 text-xs font-mono text-slate-200 placeholder:text-slate-600 outline-none transition-colors"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 text-xs font-mono"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* ── 4. ALERT LIST ─────────────────────────────────────────────── */}
      {alerts.length === 0 ? (
        /* Empty State: No alerts overall */
        <div className="flex flex-col items-center justify-center text-center p-16 my-4 bg-slate-900/30 border-2 border-dashed border-slate-800/80 rounded-2xl">
          <div className="w-16 h-16 rounded-full bg-slate-800/60 border border-slate-700 flex items-center justify-center mb-4">
            <ShieldAlert className="w-8 h-8 text-slate-500 opacity-50" />
          </div>
          <h3 className="text-base font-bold font-mono text-white tracking-wider mb-1">
            NO ACTIVE THREAT ALERTS
          </h3>
          <p className="text-xs text-slate-400 max-w-md">
            Perimeter scan in progress. Real-time alerts will appear automatically upon target detection or suspicious activity.
          </p>
        </div>
      ) : filteredAlerts.length === 0 ? (
        /* Empty State: Filter/search yielded 0 results */
        <div className="flex flex-col items-center justify-center text-center p-12 my-4 bg-slate-900/20 border border-slate-800/80 rounded-xl">
          <Filter className="w-8 h-8 text-slate-600 mb-3" />
          <h4 className="text-sm font-bold font-mono text-slate-300">NO MATCHING ALERTS</h4>
          <p className="text-xs text-slate-500 mt-1">
            No threat alerts match your current filter ({filterSeverity}) or search criteria.
          </p>
          <button
            type="button"
            onClick={() => { setFilterSeverity('ALL'); setSearchQuery(''); }}
            className="mt-4 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-300 rounded text-xs font-mono transition-colors"
          >
            Reset Filters
          </button>
        </div>
      ) : (
        /* Active Alert Cards */
        <div className="flex flex-col gap-3 w-full">
          {filteredAlerts.map((alert) => {
            const { icon: Icon, color, bg, border, badge, indicator } = getSeverityConfig(alert.severity);

            return (
              <div
                key={alert.id ?? `${alert.time}-${alert.type}`}
                className={`p-4 rounded-xl border ${border} ${bg} backdrop-blur-md flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all duration-200 hover:translate-x-1 shadow-md group`}
              >
                {/* Left Info Column */}
                <div className="flex items-start gap-3.5 min-w-0 flex-1">
                  <div className={`p-2.5 rounded-lg ${badge} shrink-0 mt-0.5 shadow-sm`}>
                    <Icon className={`w-5 h-5 ${color}`} />
                  </div>

                  <div className="flex flex-col gap-1.5 min-w-0 flex-1">
                    {/* Top Row: Title, Severity Badge, Activity Badge */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded ${badge}`}>
                        {alert.severity || 'ALERT'}
                      </span>
                      <h4 className={`text-sm font-bold font-mono ${color} truncate`}>
                        {alert.type}
                      </h4>

                      {/* Suspicious Activity Subtype Badge */}
                      {alert.activity_subtype && (
                        <span className="text-[10px] font-mono font-bold text-amber-300 bg-amber-950/70 border border-amber-500/40 px-2 py-0.5 rounded uppercase">
                          ⚡ {alert.activity_subtype === 'RUNNING' ? 'Running' :
                              alert.activity_subtype === 'CRAWLING' ? 'Crawling' :
                              alert.activity_subtype === 'THROWING' ? 'Throwing' :
                              alert.activity_subtype}
                        </span>
                      )}
                    </div>

                    {/* Metadata Badges Row */}
                    <div className="flex items-center gap-2 flex-wrap text-[11px] font-mono text-slate-400">
                      {alert.objectClass && (
                        <span className="inline-flex items-center gap-1 bg-slate-950/60 border border-slate-800 px-2 py-0.5 rounded text-slate-300 font-semibold uppercase">
                          <span className={`w-1.5 h-1.5 rounded-full ${indicator}`} />
                          {alert.objectClass}
                        </span>
                      )}
                      {alert.trackId != null && (
                        <span className="bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 font-bold px-2 py-0.5 rounded">
                          Track #{alert.trackId}
                        </span>
                      )}
                      {alert.object_track_id != null && (
                        <span className="bg-purple-950/60 border border-purple-500/40 text-purple-300 font-bold px-2 py-0.5 rounded">
                          Obj #{alert.object_track_id}
                        </span>
                      )}
                      {alert.confidence != null && (
                        <span className="bg-slate-900 border border-slate-700/60 text-slate-300 px-2 py-0.5 rounded">
                          {alert.confidence}% conf
                        </span>
                      )}
                      <span className="text-slate-500">•</span>
                      <span className="text-slate-300 font-semibold truncate max-w-[200px]">
                        {alert.camera}
                      </span>
                    </div>

                    {/* Description */}
                    <p className="text-xs text-slate-300 mt-0.5 leading-relaxed">
                      {alert.description}
                    </p>
                  </div>
                </div>

                {/* Right Action & Timestamp Column */}
                <div className="flex items-center md:flex-col md:items-end justify-between md:justify-center gap-2 shrink-0 border-t md:border-t-0 pt-2 md:pt-0 border-slate-800">
                  <div className="flex items-center gap-1.5 text-xs font-mono text-slate-400 bg-black/40 px-2.5 py-1 rounded-md border border-slate-800">
                    <Clock className="w-3.5 h-3.5 text-slate-500" />
                    <span>{alert.time}</span>
                  </div>

                  {/* Forensic Evidence Snapshot Button */}
                  {isEvidenceEligible(alert) && (
                    <button
                      type="button"
                      title="Inspect Forensic Evidence Snapshot"
                      onClick={() => setEvidenceAlert(alert)}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono font-medium text-cyan-300 bg-cyan-950/40 hover:bg-cyan-900/60 border border-cyan-500/30 hover:border-cyan-500/60 transition-all cursor-pointer shadow-sm"
                    >
                      <Camera className="w-3.5 h-3.5 text-cyan-400" />
                      <span>Evidence</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
