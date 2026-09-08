import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertTriangle, Info, AlertCircle, ShieldAlert, ShieldCheck,
  WifiOff, Camera, X, ChevronLeft, ChevronRight, ImageOff,
  Clock, Tag, Crosshair, BarChart2, FileImage, Loader2
} from 'lucide-react';
import { getEvidenceList, getEvidenceImageUrl } from '../../services/videoApi';

// ─────────────────────────────────────────────────────────────────────────────
// Evidence Viewer Modal — fully opaque, professional surveillance UI
// ─────────────────────────────────────────────────────────────────────────────
export const EvidenceModal = ({ alert, onClose }) => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [imgStatus, setImgStatus] = useState('loading'); // 'loading' | 'ok' | 'error'

  // Determine the event_type scope for retrieval based on alert type
  const inferEventType = useCallback((alert) => {
    if (!alert) return null;
    const t = (alert.type || '').toLowerCase();
    const isLoitering  = alert.event_type === 'loitering' || t.includes('loiter');
    const isIntrusion  = alert.isIntrusion || t.includes('intrusion') || t.includes('zone');
    const isCrossing   = t.includes('crossing') || t.includes('line');
    const isUnknown    = t.includes('unrecognized') || t.includes('unknown');
    const isSuspicious = alert.event_type === 'SUSPICIOUS_ACTIVITY' || t.includes('suspicious');
    if (isLoitering)  return 'loitering';
    if (isIntrusion)  return 'zone_intrusion';
    if (isCrossing)   return 'line_crossing';
    if (isUnknown)    return 'unknown_person_face';
    if (isSuspicious) return 'suspicious_activity';
    return null; // priority_person_alert or other — no event_type filter
  }, []);

  useEffect(() => {
    if (!alert) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setRecords([]);
    setSelectedIdx(0);
    setImgStatus('loading');

    const eventType = inferEventType(alert);

    // Primary query: by source_id + optional track_id
    getEvidenceList(alert.sourceId, 50, alert.trackId, eventType)
      .then(({ evidence }) => {
        if (cancelled) return;
        let list = evidence || [];
        // If nothing found with exact track_id filter, broaden to source only
        if (list.length === 0 && alert.sourceId) {
          return getEvidenceList(alert.sourceId, 20, null, eventType)
            .then(({ evidence: ev2 }) => {
              if (!cancelled) {
                setRecords(ev2 || []);
                setLoading(false);
              }
            });
        }
        setRecords(list);
        setLoading(false);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || 'Failed to load evidence');
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [alert?.sourceId, alert?.trackId, alert?.type, inferEventType]);

  const selected = records[selectedIdx] ?? null;

  const handlePrev = () => setSelectedIdx(i => Math.max(0, i - 1));
  const handleNext = () => setSelectedIdx(i => Math.min(records.length - 1, i + 1));

  // Severity color for the event badge
  const sevColor = (() => {
    const s = (alert?.severity || '').toLowerCase();
    if (s === 'critical') return 'text-red-400 bg-red-500/15 border-red-500/40';
    if (s === 'high')     return 'text-orange-400 bg-orange-500/15 border-orange-500/40';
    if (s === 'medium')   return 'text-yellow-400 bg-yellow-500/15 border-yellow-500/40';
    if (s === 'safe')     return 'text-emerald-400 bg-emerald-500/15 border-emerald-500/40';
    return 'text-cyan-400 bg-cyan-500/15 border-cyan-500/40';
  })();

  return createPortal(
    /* ── Backdrop: fully opaque dark overlay ── */
    <div
      style={{ backgroundColor: 'rgba(0,0,0,0.88)', zIndex: 999999 }}
      className="fixed inset-0 flex items-center justify-center p-4"
      onClick={onClose}
    >
      {/* ── Modal shell: fully opaque slate-950 ── */}
      <div
        style={{ backgroundColor: '#0f172a' }}
        className="relative w-full max-w-3xl rounded-2xl border border-slate-700/80
                   shadow-[0_30px_80px_rgba(0,0,0,0.7)] overflow-hidden flex flex-col
                   max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >

        {/* ═══════════ HEADER ═══════════ */}
        <div
          style={{ backgroundColor: '#020617' }}
          className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/25">
              <Camera className="w-4 h-4 text-cyan-400" />
            </div>
            <div>
              <h2 className="font-mono font-bold text-sm text-white uppercase tracking-widest">
                Evidence Capture
              </h2>
              <p className="text-[10px] font-mono text-slate-500 mt-0.5">
                Security Event Forensic Record
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-500 hover:text-white
                       transition-colors border border-transparent hover:border-slate-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* ═══════════ EVENT SUMMARY STRIP ═══════════ */}
        <div
          style={{ backgroundColor: '#0f172a' }}
          className="px-5 py-3 border-b border-slate-800/70 flex flex-wrap gap-x-5 gap-y-2"
        >
          {[
            { Icon: Tag,       label: 'Event',    value: alert?.type || '—' },
            { Icon: ShieldAlert, label: 'Severity', value: alert?.severity || '—', colored: true },
            { Icon: Camera,    label: 'Camera',   value: alert?.camera || '—' },
            { Icon: Crosshair, label: 'Track ID', value: alert?.trackId != null ? `#${alert.trackId}` : '—' },
            ...(alert?.object_track_id != null ? [{ Icon: Crosshair, label: 'Object ID', value: `#${alert.object_track_id}` }] : []),
            { Icon: Clock,     label: 'Time',     value: alert?.time || '—' },
          ].map(({ Icon, label, value, colored }) => (
            <div key={label} className="flex items-center gap-1.5 min-w-0">
              <Icon className="w-3 h-3 text-slate-500 shrink-0" />
              <span className="text-[10px] font-mono text-slate-500 uppercase shrink-0">{label}:</span>
              <span className={`text-[11px] font-mono font-semibold truncate max-w-[180px] ${colored ? sevColor.split(' ')[0] : 'text-slate-200'}`}>
                {value}
              </span>
            </div>
          ))}
        </div>

        {/* ═══════════ MAIN BODY ═══════════ */}
        <div className="flex flex-1 overflow-hidden min-h-0" style={{ backgroundColor: '#0f172a' }}>

          {/* ── Thumbnail strip (left) ── */}
          <div
            style={{ backgroundColor: '#020617', width: '100px', minWidth: '100px' }}
            className="flex flex-col border-r border-slate-800 overflow-y-auto"
          >
            <div className="px-2 py-2 border-b border-slate-800/70">
              <p className="text-[9px] font-mono text-slate-500 uppercase tracking-wider text-center">
                {records.length} Snapshot{records.length !== 1 ? 's' : ''}
              </p>
            </div>

            {loading ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
              </div>
            ) : records.length === 0 ? (
              <div className="flex-1 flex items-center justify-center p-2 text-center">
                <p className="text-[9px] font-mono text-slate-600">No snapshots</p>
              </div>
            ) : (
              records.map((rec, i) => (
                <button
                  key={rec.filename}
                  onClick={() => { setSelectedIdx(i); setImgStatus('loading'); }}
                  className={`w-full p-1.5 border-b border-slate-800/50 transition-all
                    ${selectedIdx === i
                      ? 'bg-cyan-950/50 border-l-2 border-l-cyan-400'
                      : 'hover:bg-slate-800/60 border-l-2 border-l-transparent'
                    }`}
                >
                  <div className="relative">
                    <img
                      src={getEvidenceImageUrl(rec.filename)}
                      alt={`Snapshot ${i + 1}`}
                      className="w-full h-14 object-cover rounded"
                      onError={e => { e.target.style.opacity = '0.2'; }}
                    />
                    {selectedIdx === i && (
                      <div className="absolute inset-0 border border-cyan-400/60 rounded pointer-events-none" />
                    )}
                  </div>
                  <p className="text-[8px] font-mono text-slate-500 mt-1 truncate text-center">
                    {rec.captured_at
                      ? new Date(rec.captured_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                      : `#${i + 1}`}
                  </p>
                </button>
              ))
            )}
          </div>

          {/* ── Main content area (right) ── */}
          <div className="flex-1 flex flex-col overflow-hidden min-w-0">

            {/* Image viewer */}
            <div className="flex-1 flex items-center justify-center bg-black overflow-hidden relative">
              {loading ? (
                <div className="flex flex-col items-center gap-3 text-slate-600">
                  <Loader2 className="w-8 h-8 animate-spin" />
                  <span className="text-xs font-mono">Loading evidence…</span>
                </div>
              ) : error ? (
                <div className="flex flex-col items-center gap-2 text-slate-600 p-6 text-center">
                  <ImageOff className="w-10 h-10 opacity-30" />
                  <p className="text-xs font-mono text-red-400/70">Evidence fetch failed</p>
                  <p className="text-[10px] font-mono text-slate-600">{error}</p>
                </div>
              ) : records.length === 0 ? (
                <div className="flex flex-col items-center gap-3 text-center p-8">
                  <div className="w-16 h-16 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center">
                    <FileImage className="w-7 h-7 text-slate-700" />
                  </div>
                  <div>
                    <p className="text-sm font-mono font-bold text-slate-400">
                      No Evidence Snapshot Available
                    </p>
                    <p className="text-[11px] font-mono text-slate-600 mt-1 max-w-xs">
                      Snapshots are captured automatically on security events.
                      {alert?.sourceId
                        ? ' The source may not have a snapshot saved yet for this specific event.'
                        : ' No source ID is linked to this alert.'}
                    </p>
                  </div>
                </div>
              ) : selected ? (
                <>
                  {imgStatus === 'error' ? (
                    <div className="flex flex-col items-center gap-2 text-slate-600">
                      <ImageOff className="w-10 h-10 opacity-30" />
                      <p className="text-xs font-mono">Image file unavailable</p>
                    </div>
                  ) : (
                    <img
                      key={selected.filename}
                      src={getEvidenceImageUrl(selected.filename)}
                      alt="Evidence snapshot"
                      className="max-w-full max-h-full object-contain"
                      style={{ display: imgStatus === 'ok' ? 'block' : 'block' }}
                      onLoad={() => setImgStatus('ok')}
                      onError={() => setImgStatus('error')}
                    />
                  )}

                  {/* Navigation arrows */}
                  {records.length > 1 && (
                    <>
                      <button
                        onClick={handlePrev}
                        disabled={selectedIdx === 0}
                        className="absolute left-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg
                                   bg-black/60 border border-slate-700 text-slate-400
                                   hover:text-white hover:bg-slate-800 transition-colors
                                   disabled:opacity-20 disabled:cursor-not-allowed"
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </button>
                      <button
                        onClick={handleNext}
                        disabled={selectedIdx === records.length - 1}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg
                                   bg-black/60 border border-slate-700 text-slate-400
                                   hover:text-white hover:bg-slate-800 transition-colors
                                   disabled:opacity-20 disabled:cursor-not-allowed"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                      {/* Position counter */}
                      <div className="absolute bottom-2 left-1/2 -translate-x-1/2
                                      bg-black/70 border border-slate-700/60 rounded-full
                                      px-3 py-0.5 text-[10px] font-mono text-slate-400">
                        {selectedIdx + 1} / {records.length}
                      </div>
                    </>
                  )}
                </>
              ) : null}
            </div>

            {/* Metadata footer */}
            {selected && (
              <div
                style={{ backgroundColor: '#020617' }}
                className="border-t border-slate-800 px-4 py-3 grid grid-cols-3 gap-x-4 gap-y-1.5"
              >
                {[
                  ['Event Type', selected.event_type?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())],
                  ['Source ID', selected.source_id ? selected.source_id.slice(0, 18) + '…' : '—'],
                  ['Track', selected.track_id != null ? `#${selected.track_id}` : '—'],
                  ['Confidence', selected.confidence != null ? `${Math.round(selected.confidence * 100)}%` : '—'],
                  ['Captured', selected.captured_at ? new Date(selected.captured_at).toLocaleString() : '—'],
                  ['Object', selected.object_class || '—'],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-start gap-1.5">
                    <span className="text-[9px] font-mono text-slate-600 uppercase tracking-wide shrink-0 w-14">
                      {label}
                    </span>
                    <span className="text-[10px] font-mono text-slate-300 truncate">
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ═══════════ FOOTER STATUS BAR ═══════════ */}
        <div
          style={{ backgroundColor: '#020617' }}
          className="px-5 py-2 border-t border-slate-800/80 flex items-center justify-between"
        >
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${records.length > 0 ? 'bg-emerald-400' : 'bg-slate-600'}`} />
            <span className="text-[10px] font-mono text-slate-500">
              {records.length > 0
                ? `${records.length} evidence record${records.length > 1 ? 's' : ''} found`
                : 'No evidence records for this event'}
            </span>
          </div>
          <span className="text-[9px] font-mono text-slate-700 uppercase tracking-wider">
            Sentinel AI · Evidence Archive
          </span>
        </div>
      </div>
    </div>,
    document.body
  );
};


// ─────────────────────────────────────────────────────────────────────────────
// Main AlertPanel
// ─────────────────────────────────────────────────────────────────────────────
const AlertPanel = ({ alerts = [], isConnected = false }) => {
  const [filterSeverity, setFilterSeverity] = useState('ALL');
  const [evidenceAlert, setEvidenceAlert]   = useState(null);

  const getSeverityConfig = (severity = '') => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return { icon: ShieldAlert,   color: 'text-red-400',     bg: 'bg-red-950/40',     border: 'border-red-500/40',    badge: 'bg-red-500/20 text-red-400' };
      case 'high':
        return { icon: AlertTriangle, color: 'text-orange-400',  bg: 'bg-orange-950/40',  border: 'border-orange-500/40', badge: 'bg-orange-500/20 text-orange-400' };
      case 'medium':
        return { icon: AlertCircle,   color: 'text-yellow-400',  bg: 'bg-yellow-950/40',  border: 'border-yellow-500/40', badge: 'bg-yellow-500/20 text-yellow-400' };
      case 'safe':
      case 'authorized':
        return { icon: ShieldCheck,   color: 'text-emerald-400', bg: 'bg-emerald-950/40', border: 'border-emerald-500/40', badge: 'bg-emerald-500/20 text-emerald-400' };
      case 'low':
      default:
        return { icon: Info,          color: 'text-cyan-400',    bg: 'bg-cyan-950/40',    border: 'border-cyan-500/40',   badge: 'bg-cyan-500/20 text-cyan-400' };
    }
  };

  const filteredAlerts = alerts.filter((a) => {
    if (filterSeverity === 'ALL') return true;
    return a.severity?.toUpperCase() === filterSeverity;
  });

  // Only threat-level alerts get an evidence button
  const isEvidenceEligible = (alert) => {
    const sev = (alert.severity || '').toLowerCase();
    return sev === 'critical' || sev === 'high' || sev === 'medium';
  };

  return (
    <>
      {/* Evidence Modal — rendered at top level to ensure no clipping */}
      {evidenceAlert && (
        <EvidenceModal
          alert={evidenceAlert}
          onClose={() => setEvidenceAlert(null)}
        />
      )}

      <div className="bg-[#021822]/85 backdrop-blur-md border border-[#00d4b0]/16 rounded-xl flex flex-col h-full overflow-hidden shadow-[0_4px_25px_rgba(0,0,0,0.5)]">

        {/* Header */}
        <div className="p-4 border-b border-[#00d4b0]/15 bg-[#01121a]/60 flex justify-between items-center gap-2">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded bg-red-500/10 border border-red-500/20 shadow-[0_0_10px_rgba(239,68,68,0.15)]">
              <ShieldAlert className="w-4 h-4 text-red-400" />
            </div>
            <div>
              <h3 className="font-mono font-bold text-xs text-white uppercase tracking-wider">THREAT ALERTS</h3>
              <p className="text-[10px] font-mono text-[#6aa89f]">REAL-TIME INTRUSION FEED</p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {isConnected ? (
              <span className="flex items-center gap-1 text-[10px] font-mono font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#10b981]" />
                WS LIVE
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[10px] font-mono text-slate-500 bg-[#01121a] px-2 py-0.5 rounded-full border border-slate-700">
                <WifiOff className="w-3 h-3" />
                WS OFF
              </span>
            )}
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="px-3 py-2 bg-[#01121a]/40 border-b border-[#00d4b0]/12 flex items-center justify-between gap-1 text-[10px] font-mono">
          <div className="flex items-center gap-1">
            {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM'].map((tab) => (
              <button
                key={tab}
                onClick={() => setFilterSeverity(tab)}
                className={`px-2 py-1 rounded transition-colors cursor-pointer ${
                  filterSeverity === tab
                    ? 'bg-[#00d4b0]/25 text-cyan-200 border border-[#00d4b0]/40 font-bold shadow-[0_0_10px_rgba(0,212,176,0.15)]'
                    : 'text-slate-400 hover:text-white hover:bg-[#032230]/50'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
          <span className="text-[#4a8a80] font-mono">{filteredAlerts.length} ALERTS</span>
        </div>

        {/* Alert list */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2.5 max-h-[600px]">
          {filteredAlerts.length === 0 ? (
            <div className="py-12 px-4 text-center">
              <div className="w-10 h-10 rounded-full bg-slate-800/60 border border-slate-700 flex items-center justify-center mx-auto mb-2 text-slate-500">
                <ShieldAlert className="w-5 h-5 opacity-40" />
              </div>
              <p className="text-xs font-mono text-slate-400 font-semibold">NO ACTIVE ALERTS</p>
              <p className="text-[10px] text-slate-500 mt-1">
                Perimeter scan in progress. Alerts will appear upon target detection.
              </p>
            </div>
          ) : (
            filteredAlerts.map((alert) => {
              const { icon: Icon, color, bg, border, badge } = getSeverityConfig(alert.severity);
              return (
                <div
                  key={alert.id ?? `${alert.time}-${alert.type}`}
                  className={`p-3 rounded-lg border ${border} ${bg} backdrop-blur-sm flex gap-3 items-start transition-all hover:translate-x-0.5`}
                >
                  <div className={`p-1.5 rounded ${badge} shrink-0 mt-0.5`}>
                    <Icon className={`w-4 h-4 ${color}`} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start mb-0.5">
                      <h4 className={`text-xs font-bold font-mono ${color} truncate`}>
                        {alert.type}
                      </h4>
                      <div className="flex items-center gap-1 ml-2 shrink-0">
                        <span className="text-[10px] font-mono text-slate-400 whitespace-nowrap bg-black/40 px-1.5 py-0.5 rounded">
                          {alert.time}
                        </span>
                        {/* Evidence button — only for threat-level alerts */}
                        {isEvidenceEligible(alert) && (
                          <button
                            title="View Evidence Snapshot"
                            onClick={() => setEvidenceAlert(alert)}
                            className="p-1 rounded hover:bg-slate-700/60 text-slate-500 hover:text-cyan-400 transition-colors"
                          >
                            <Camera className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Object Class + Track ID + Confidence + Activity badges */}
                    {(alert.objectClass || alert.activity_subtype) && (
                      <div className="flex items-center gap-1.5 mt-1 mb-1 flex-wrap">
                        {alert.objectClass && (
                          <span className={`inline-flex items-center gap-1 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${badge} border ${border} uppercase tracking-wide`}>
                            <svg className="w-2.5 h-2.5 shrink-0" viewBox="0 0 10 10" fill="currentColor">
                              <circle cx="5" cy="5" r="4" />
                            </svg>
                            {alert.objectClass}
                          </span>
                        )}
                        {alert.trackId != null && (
                          <span className="text-[10px] font-mono font-bold text-cyan-300 bg-cyan-950/60 border border-cyan-500/40 px-1.5 py-0.5 rounded">
                            #{alert.trackId}
                          </span>
                        )}
                        {alert.confidence != null && (
                          <span className="text-[10px] font-mono text-slate-300 bg-slate-800/80 border border-slate-700/60 px-1.5 py-0.5 rounded">
                            {alert.confidence}% conf
                          </span>
                        )}
                        {alert.activity_subtype && (
                          <span className="text-[10px] font-mono font-bold text-amber-300 bg-amber-950/60 border border-amber-500/40 px-1.5 py-0.5 rounded uppercase">
                            {alert.activity_subtype === 'RUNNING' ? 'Running' :
                             alert.activity_subtype === 'CRAWLING' ? 'Crawling' :
                             alert.activity_subtype === 'THROWING' ? 'Throwing' :
                             alert.activity_subtype}
                          </span>
                        )}
                        {alert.object_track_id != null && (
                          <span className="text-[10px] font-mono font-bold text-purple-300 bg-purple-950/60 border border-purple-500/40 px-1.5 py-0.5 rounded">
                            Obj #{alert.object_track_id}
                          </span>
                        )}
                      </div>
                    )}

                    <p className="text-[11px] font-mono text-slate-300 truncate">{alert.camera}</p>
                    <p className="text-[11px] text-slate-400 mt-1 leading-snug">{alert.description}</p>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </>
  );
};

export default AlertPanel;
