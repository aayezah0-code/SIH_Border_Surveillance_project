import React, { useState } from 'react';
import { Database, Search, Shield, Filter, Download } from 'lucide-react';

const RecentEventsTable = ({ events = [], activeSource = null }) => {
  const [searchTerm, setSearchTerm] = useState('');

  // Scope events to current active source if specified
  const currentSourceId = activeSource?.source_id ?? null;
  const currentEvents = React.useMemo(() => {
    if (!currentSourceId) return events;
    return events.filter((ev) => !ev.sourceId || ev.sourceId === currentSourceId);
  }, [events, currentSourceId]);

  const filteredEvents = currentEvents.filter((ev) => {
    if (!searchTerm) return true;
    const query = searchTerm.toLowerCase();
    return (
      ev.type?.toLowerCase().includes(query) ||
      ev.camera?.toLowerCase().includes(query) ||
      ev.object?.toLowerCase().includes(query) ||
      ev.risk?.toLowerCase().includes(query)
    );
  });

  const exportCSV = () => {
    if (!currentEvents.length && !currentSourceId) return;

    // 1. Direct backend database CSV download filtered strictly by current source_id
    try {
      const sourceParam = currentSourceId ? `?source_id=${encodeURIComponent(currentSourceId)}` : '';
      const link = document.createElement("a");
      link.href = `/api/v1/events/export/csv${sourceParam}`;
      link.download = `surveillance_events_${currentSourceId || 'current'}_${Date.now()}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (e) {
      // 2. Client-side fallback with complete column schema for current session events
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
      const rows = currentEvents.map((e, idx) => [
        `evt_${Date.now()}_${idx}`,
        today,
        `"${e.timestamp || ''}"`,
        `"${e.camera || activeSource?.original_name || 'Feed 1'}"`,
        `"${currentSourceId || 'Active Session'}"`,
        `"${e.type || 'Object Detection'}"`,
        `"${(e.object || '').replace(/"/g, '""')}"`,
        `"${e.trackId != null ? e.trackId : 'N/A'}"`,
        `"${e.personName || (e.risk === 'SAFE' ? 'Authorized Personnel' : 'N/A')}"`,
        `"${e.risk === 'SAFE' ? 'KNOWN_PERSON' : 'UNKNOWN_PERSON'}"`,
        `"${e.risk || 'LOW'}"`,
        `"${e.risk === 'CRITICAL' ? 'Critical' : e.risk === 'HIGH' ? 'High' : 'Info'}"`,
        `"${e.confidence || '90%'}"`,
        'N/A',
        `"${e.status || 'Logged'}"`
      ]);
      const csvContent = "data:text/csv;charset=utf-8," + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", `surveillance_events_${currentSourceId || 'current'}_${Date.now()}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };


  return (
    <div className="bg-[#021822]/85 backdrop-blur-md border border-[#00d4b0]/16 rounded-xl overflow-hidden shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
      {/* Table Header Controls */}
      <div className="p-4 border-b border-[#00d4b0]/15 bg-[#01121a]/60 flex flex-col sm:flex-row justify-between sm:items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-[#00d4b0]/10 border border-[#00d4b0]/25 shadow-[0_0_10px_rgba(0,212,176,0.15)]">
            <Database className="w-4 h-4 text-[#00d4b0]" />
          </div>
          <div>
            <h3 className="font-mono font-bold text-xs text-white uppercase tracking-wider">
              REAL-TIME EVENT AUDIT LOG
            </h3>
            <p className="text-[10px] font-mono text-[#6aa89f]">
              YOLO OBJECT INTRUSION & TELEMETRY STREAM
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Filter log..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-[#010e14]/90 border border-[#00d4b0]/20 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-[#3d6e67] focus:outline-none focus:border-[#00d4b0]/50 font-mono w-40 sm:w-48"
            />
          </div>

          {/* Export CSV */}
          {events.length > 0 && (
            <button
              onClick={exportCSV}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#021f2b] hover:bg-[#032e40] text-cyan-200 hover:text-white border border-[#00d4b0]/30 text-xs font-mono font-medium transition-colors cursor-pointer shadow-[0_0_10px_rgba(0,212,176,0.1)]"
              title="Download Log as CSV"
            >
              <Download className="w-3.5 h-3.5 text-[#00d4b0]" />
              <span>CSV</span>
            </button>
          )}
        </div>
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-400 font-mono">
          <thead className="text-[11px] text-[#6aa89f] uppercase bg-[#01121a]/80 border-b border-[#00d4b0]/15">
            <tr>
              <th className="px-4 py-3 font-semibold">Time Offset</th>
              <th className="px-4 py-3 font-semibold">Feed / Sector</th>
              <th className="px-4 py-3 font-semibold">Event Type</th>
              <th className="px-4 py-3 font-semibold">Detected Objects</th>
              <th className="px-4 py-3 font-semibold">Threat Level</th>
              <th className="px-4 py-3 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#00d4b0]/10">
            {filteredEvents && filteredEvents.length > 0 ? (
              filteredEvents.map((event, idx) => (
                <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3 text-cyan-300 font-bold whitespace-nowrap">
                    {event.timestamp}
                  </td>
                  <td className="px-4 py-3 text-slate-300 font-medium">{event.camera}</td>
                  <td className="px-4 py-3 text-slate-200">{event.type}</td>
                  <td className="px-4 py-3 text-slate-300 max-w-xs truncate">{event.object}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border
                      ${event.risk === 'CRITICAL' ? 'bg-red-500/20 text-red-400 border-red-500/40' : ''}
                      ${event.risk === 'HIGH' ? 'bg-orange-500/20 text-orange-400 border-orange-500/40' : ''}
                      ${event.risk === 'MEDIUM' ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40' : ''}
                      ${event.risk === 'SAFE' || event.risk === 'LOW' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' : ''}
                      ${event.risk === 'N/A' || !event.risk ? 'bg-slate-800 text-slate-400 border-slate-700' : ''}
                    `}>
                      <span className={`w-1.5 h-1.5 rounded-full ${
                        event.risk === 'CRITICAL' ? 'bg-red-400 animate-pulse' :
                        event.risk === 'HIGH' ? 'bg-orange-400' :
                        event.risk === 'MEDIUM' ? 'bg-yellow-400' :
                        event.risk === 'SAFE' || event.risk === 'LOW' ? 'bg-emerald-400' : 'bg-slate-400'
                      }`} />
                      {event.risk || 'N/A'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                      {event.status}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="6" className="px-4 py-10 text-center text-slate-500 text-xs font-mono">
                  <div className="flex flex-col items-center gap-1">
                    <Database className="w-5 h-5 text-slate-600 mb-1" />
                    <span>No matching events logged in this session.</span>
                    <span className="text-[10px] text-slate-600">Upload and analyze a video feed to view AI detections.</span>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default RecentEventsTable;
