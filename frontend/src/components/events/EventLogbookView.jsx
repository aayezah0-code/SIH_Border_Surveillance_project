import React, { useState, useMemo } from 'react';
import { 
  Database, 
  Search, 
  Download, 
  History, 
  Filter, 
  ShieldAlert, 
  AlertTriangle, 
  AlertCircle, 
  ShieldCheck, 
  Clock, 
  Layers, 
  Activity, 
  Radio, 
  Tv, 
  CheckCircle2,
  FileSpreadsheet
} from 'lucide-react';

/**
 * EventLogbookView
 * 
 * Dedicated full-page Event Logbook view.
 * Displays and exports ONLY events belonging to the current active source/analysis.
 * Historical records in SQLite remain intact.
 */
export default function EventLogbookView({
  events = [],
  activeSource = null,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterRisk, setFilterRisk] = useState('ALL');

  const currentSourceId = activeSource?.source_id ?? null;

  // Filter events strictly to current active source
  const currentEvents = useMemo(() => {
    if (!currentSourceId) return [];
    return events.filter(e => !e.sourceId || e.sourceId === currentSourceId);
  }, [events, currentSourceId]);

  // Metrics calculated from current active source events ONLY
  const metrics = useMemo(() => {
    const total = currentEvents.length;
    const priority = currentEvents.filter(e => 
      e.risk === 'CRITICAL' || 
      e.risk === 'HIGH' || 
      e.type?.toLowerCase().includes('breach') || 
      e.type?.toLowerCase().includes('intrusion')
    ).length;
    const suspicious = currentEvents.filter(e => 
      e.type?.toLowerCase().includes('suspicious') ||
      e.type?.toLowerCase().includes('running') ||
      e.type?.toLowerCase().includes('crawling') ||
      e.type?.toLowerCase().includes('throwing')
    ).length;
    const vehicleOrObj = currentEvents.filter(e => 
      e.type?.toLowerCase().includes('vehicle') ||
      e.object?.toLowerCase().includes('car') ||
      e.object?.toLowerCase().includes('truck') ||
      e.object?.toLowerCase().includes('bus') ||
      e.object?.toLowerCase().includes('obj')
    ).length;
    return { total, priority, suspicious, vehicleOrObj };
  }, [currentEvents]);

  // Search and risk filtering
  const filteredEvents = useMemo(() => {
    return currentEvents.filter((ev) => {
      // 1. Risk / severity filter
      if (filterRisk !== 'ALL') {
        const r = (ev.risk || '').toUpperCase();
        if (filterRisk === 'LOW') {
          if (r !== 'LOW' && r !== 'SAFE') return false;
        } else if (r !== filterRisk) {
          return false;
        }
      }

      // 2. Search query filter
      if (searchTerm.trim()) {
        const q = searchTerm.toLowerCase().trim();
        const matchesType   = (ev.type || '').toLowerCase().includes(q);
        const matchesCamera = (ev.camera || '').toLowerCase().includes(q);
        const matchesObject = (ev.object || '').toLowerCase().includes(q);
        const matchesRisk   = (ev.risk || '').toLowerCase().includes(q);
        const matchesTrack  = ev.trackId != null && String(ev.trackId).toLowerCase().includes(q);
        const matchesTime   = (ev.timestamp || '').toLowerCase().includes(q);
        if (!matchesType && !matchesCamera && !matchesObject && !matchesRisk && !matchesTrack && !matchesTime) {
          return false;
        }
      }

      return true;
    });
  }, [currentEvents, filterRisk, searchTerm]);

  // CSV Export strictly scoped to current active source
  const handleExportCSV = () => {
    if (!currentSourceId) return;

    try {
      const sourceParam = `?source_id=${encodeURIComponent(currentSourceId)}`;
      const link = document.createElement("a");
      link.href = `/api/v1/events/export/csv${sourceParam}`;
      link.download = `sentinel_events_${currentSourceId}_${Date.now()}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (e) {
      // Client-side fallback with complete column schema for current session events
      if (!currentEvents.length) return;
      const headers = [
        'Event ID',
        'Date',
        'Time',
        'Camera / Source',
        'Session',
        'Event Type',
        'Detected Object',
        'Track ID',
        'Person Name',
        'Person Status',
        'Threat Level',
        'Severity',
        'Confidence',
        'Evidence Reference',
        'Status'
      ];
      const today = new Date().toISOString().split('T')[0];
      const rows = currentEvents.map((ev, idx) => [
        `evt_${Date.now()}_${idx}`,
        today,
        `"${ev.timestamp || ''}"`,
        `"${ev.camera || activeSource?.original_name || 'Active Feed'}"`,
        `"${currentSourceId}"`,
        `"${ev.type || 'Object Detection'}"`,
        `"${(ev.object || '').replace(/"/g, '""')}"`,
        `"${ev.trackId != null ? ev.trackId : 'N/A'}"`,
        `"${ev.personName || (ev.risk === 'SAFE' ? 'Authorized Personnel' : 'N/A')}"`,
        `"${ev.risk === 'SAFE' ? 'KNOWN_PERSON' : 'UNKNOWN_PERSON'}"`,
        `"${ev.risk || 'LOW'}"`,
        `"${ev.risk === 'CRITICAL' ? 'Critical' : ev.risk === 'HIGH' ? 'High' : 'Info'}"`,
        `"${ev.confidence || '90%'}"`,
        'N/A',
        `"${ev.status || 'Logged'}"`
      ]);
      const csvContent = "data:text/csv;charset=utf-8," + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", `sentinel_events_${currentSourceId}_${Date.now()}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  return (
    <div className="flex flex-col gap-6 w-full min-w-0 pb-12">
      {/* ── 1. PAGE HEADER ────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-[#021822]/90 border border-[#00d4b0]/20 rounded-xl p-5 backdrop-blur-md shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#00d4b0]/10 border border-[#00d4b0]/30 shadow-[0_0_15px_rgba(0,212,176,0.15)]">
              <Database className="w-5 h-5 text-[#00d4b0]" />
            </div>
            <div>
              <h2 className="text-xl font-bold font-mono tracking-wider text-white flex items-center gap-2">
                EVENT LOGBOOK
                <span className="text-[11px] font-sans px-2 py-0.5 rounded bg-[#00d4b0]/10 border border-[#00d4b0]/30 text-[#00d4b0] font-semibold uppercase tracking-normal">
                  TELEMETRY AUDIT
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Surveillance telemetry &amp; object detection audit log for current active session
              </p>
            </div>
          </div>
        </div>

        {/* Current Active Source Info & Export Action */}
        <div className="flex flex-wrap items-center gap-3">
          {activeSource ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#010e15] border border-[#00d4b0]/20 text-xs font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-slate-400">ACTIVE SOURCE:</span>
              <span className="text-white font-bold truncate max-w-[200px]">
                {activeSource.original_name || activeSource.name || activeSource.source_id}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#010e15] border border-[#00d4b0]/15 text-xs font-mono text-slate-500">
              <span className="w-2 h-2 rounded-full bg-slate-600" />
              <span>NO ACTIVE SOURCE</span>
            </div>
          )}

          <button
            type="button"
            onClick={handleExportCSV}
            disabled={!currentSourceId || currentEvents.length === 0}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-mono font-bold transition-all ${
              currentSourceId && currentEvents.length > 0
                ? 'bg-[#02141d] hover:bg-[#032333] text-[#00d4b0] border border-[#00d4b0]/30 hover:shadow-[0_0_12px_rgba(0,212,176,0.2)] cursor-pointer'
                : 'bg-[#010e15] border border-[#00d4b0]/10 text-slate-600 cursor-not-allowed opacity-60'
            }`}
            title={currentSourceId ? "Export current session events to CSV" : "No active session to export"}
          >
            <Download className="w-3.5 h-3.5" />
            <span>EXPORT CURRENT CSV</span>
          </button>
        </div>
      </div>

      {/* ── 2. SUMMARY METRICS ROW ────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Total Events</p>
            <p className="text-xl font-bold font-mono text-white mt-1">{metrics.total}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
            <Layers className="w-4 h-4 text-cyan-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Priority Breaches</p>
            <p className="text-xl font-bold font-mono text-red-400 mt-1">{metrics.priority}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <ShieldAlert className="w-4 h-4 text-red-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Suspicious Activity</p>
            <p className="text-xl font-bold font-mono text-amber-400 mt-1">{metrics.suspicious}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <Activity className="w-4 h-4 text-amber-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Vehicles &amp; Objects</p>
            <p className="text-xl font-bold font-mono text-purple-300 mt-1">{metrics.vehicleOrObj}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
            <Radio className="w-4 h-4 text-purple-400" />
          </div>
        </div>
      </div>

      {/* ── 3. FILTER & SEARCH TOOLBAR ────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-[#021822]/80 border border-[#00d4b0]/20 rounded-xl p-3">
        {/* Risk / Severity Filter Tabs */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {[
            { id: 'ALL', label: 'ALL EVENTS' },
            { id: 'CRITICAL', label: 'CRITICAL' },
            { id: 'HIGH', label: 'HIGH' },
            { id: 'MEDIUM', label: 'MEDIUM' },
            { id: 'LOW', label: 'LOW / SAFE' },
          ].map(tab => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setFilterRisk(tab.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all cursor-pointer ${
                filterRisk === tab.id
                  ? 'bg-[#00d4b0]/20 text-[#00d4b0] border border-[#00d4b0]/40 font-bold shadow-[0_0_10px_rgba(0,212,176,0.15)]'
                  : 'text-slate-400 hover:text-slate-200 bg-[#02141d] hover:bg-[#032333] border border-[#00d4b0]/15'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Search Field */}
        <div className="relative min-w-[240px] sm:w-72">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search events, objects, cameras…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#010e15] border border-[#00d4b0]/20 focus:border-[#00d4b0]/60 rounded-lg pl-9 pr-3 py-1.5 text-xs font-mono text-slate-200 placeholder:text-slate-600 outline-none transition-colors"
          />
          {searchTerm && (
            <button
              type="button"
              onClick={() => setSearchTerm('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 text-xs font-mono"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* ── 4. EVENT TABLE / LIST ─────────────────────────────────────── */}
      {!activeSource ? (
        /* Empty State: No active source */
        <div className="flex flex-col items-center justify-center text-center p-16 my-4 bg-[#02141d]/70 border-2 border-dashed border-[#00d4b0]/20 rounded-2xl">
          <div className="w-16 h-16 rounded-full bg-[#010e15] border border-[#00d4b0]/30 flex items-center justify-center mb-4">
            <History className="w-8 h-8 text-[#00d4b0] opacity-60" />
          </div>
          <h3 className="text-base font-bold font-mono text-white tracking-wider mb-1">
            NO ACTIVE SURVEILLANCE SOURCE
          </h3>
          <p className="text-xs text-slate-400 max-w-md">
            Connect an RTSP camera or upload a surveillance video to begin logging telemetry events for the active session.
          </p>
        </div>
      ) : currentEvents.length === 0 ? (
        /* Empty State: Active source has 0 events */
        <div className="flex flex-col items-center justify-center text-center p-16 my-4 bg-[#02141d]/70 border-2 border-dashed border-[#00d4b0]/20 rounded-2xl">
          <div className="w-16 h-16 rounded-full bg-[#00d4b0]/10 border border-[#00d4b0]/30 flex items-center justify-center mb-4">
            <Activity className="w-8 h-8 text-[#00d4b0]" />
          </div>
          <h3 className="text-base font-bold font-mono text-white tracking-wider mb-1">
            NO EVENTS RECORDED FOR CURRENT SOURCE
          </h3>
          <p className="text-xs text-slate-400 max-w-md">
            Surveillance session active. Trigger YOLO video analysis or stream telemetry to populate the Event Logbook.
          </p>
        </div>
      ) : filteredEvents.length === 0 ? (
        /* Empty State: Search / filter yielded 0 results */
        <div className="flex flex-col items-center justify-center text-center p-12 my-4 bg-[#02141d]/50 border border-[#00d4b0]/20 rounded-xl">
          <Filter className="w-8 h-8 text-slate-600 mb-3" />
          <h4 className="text-sm font-bold font-mono text-slate-300">NO MATCHING EVENTS</h4>
          <p className="text-xs text-slate-500 mt-1">
            No events match your current filter ({filterRisk}) or search criteria.
          </p>
          <button
            type="button"
            onClick={() => { setFilterRisk('ALL'); setSearchTerm(''); }}
            className="mt-4 px-3 py-1.5 bg-[#02141d] hover:bg-[#032333] text-[#00d4b0] border border-[#00d4b0]/30 rounded text-xs font-mono transition-colors cursor-pointer"
          >
            Reset Filters
          </button>
        </div>
      ) : (
        /* Event Table */
        <div className="bg-[#021822]/90 backdrop-blur-md border border-[#00d4b0]/20 rounded-xl overflow-hidden shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-400 font-mono">
              <thead className="text-[11px] text-slate-400 uppercase bg-slate-950/80 border-b border-slate-800/80">
                <tr>
                  <th className="px-4 py-3 font-semibold">Time Offset</th>
                  <th className="px-4 py-3 font-semibold">Feed / Sector</th>
                  <th className="px-4 py-3 font-semibold">Event Type</th>
                  <th className="px-4 py-3 font-semibold">Detected Objects &amp; Telemetry</th>
                  <th className="px-4 py-3 font-semibold">Threat Level</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredEvents.map((event, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3 text-cyan-300 font-bold whitespace-nowrap">
                      {event.timestamp}
                    </td>
                    <td className="px-4 py-3 text-slate-300 font-medium">
                      {event.camera || activeSource?.original_name || 'Active Feed'}
                    </td>
                    <td className="px-4 py-3 text-white font-semibold">
                      {event.type}
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-md">
                      {event.object}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                        event.risk === 'CRITICAL' ? 'bg-red-500/20 text-red-400 border-red-500/40' :
                        event.risk === 'HIGH' ? 'bg-orange-500/20 text-orange-400 border-orange-500/40' :
                        event.risk === 'MEDIUM' ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40' :
                        'bg-emerald-500/20 text-emerald-400 border-emerald-500/40'
                      }`}>
                        {event.risk || 'LOW'}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className="text-slate-400 bg-slate-950/60 border border-slate-800 px-2 py-0.5 rounded text-[10px]">
                        {event.status || 'Logged'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
