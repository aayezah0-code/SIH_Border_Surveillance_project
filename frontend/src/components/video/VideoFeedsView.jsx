import React, { useState, useMemo } from 'react';
import { 
  Camera, 
  Video, 
  Radio, 
  Film, 
  Plus, 
  Trash2, 
  LayoutGrid, 
  Grid2X2, 
  Maximize2, 
  Activity, 
  AlertTriangle, 
  Tv, 
  CheckCircle2,
  X,
  Sparkles,
  Loader
} from 'lucide-react';
import { LiveVideoCard } from '../dashboard/CameraGrid';
import VideoUploadPanel from '../dashboard/VideoUploadPanel';
import AlertPanel from '../dashboard/AlertPanel';
import IntrusionPanel from '../dashboard/IntrusionPanel';

/**
 * VideoFeedsView
 * 
 * Dedicated Video Feeds management page.
 * - Displays ONLY currently active sources.
 * - Never auto-populates or fills empty slots with historical videos.
 * - When an uploaded video is active/analyzed, uses the consistent Defense Grid
 *   layout (Large video on left, AlertPanel + IntrusionPanel on right) without
 *   displaying standby camera connection slots beside it.
 * - When managing multi-feed RTSP streams, maintains the grid layout.
 */
export default function VideoFeedsView({
  activeSource,
  activeSources = [],
  detectionResults,
  isAnalyzing = false,
  analysisElapsed = 0,
  analysisSummary,
  analysisError = '',
  onAnalyze,
  onRemoveSource,
  onSourceAdded,
  onAnalysisComplete,
  alerts = [],
  intrusions = [],
  isConnected = false,
}) {
  // Feed ingestion drawer / active mode
  const [showIngestion, setShowIngestion] = useState(false);
  
  // Filter tab: 'all' | 'rtsp' | 'file'
  const [filterType, setFilterType] = useState('all');
  
  // Layout columns: 1 (Full width) | 2 (2x2 Grid) | 3 (3x3 Grid)
  const [layoutCols, setLayoutCols] = useState(2);

  // Merge unique sources strictly from current activeSources and activeSource
  const allSources = useMemo(() => {
    const map = new Map();
    (activeSources || []).forEach(s => {
      if (s && s.source_id) map.set(s.source_id, s);
    });
    if (activeSource && activeSource.source_id) {
      map.set(activeSource.source_id, { ...map.get(activeSource.source_id), ...activeSource });
    }
    return Array.from(map.values());
  }, [activeSources, activeSource]);

  // Check if an uploaded video is actively being viewed/analyzed
  const hasUploadedVideo = !!(activeSource && (activeSource.source_type === 'FILE' || !activeSource.source_type));

  // Status metrics calculated from real currently active sources ONLY
  const metrics = useMemo(() => {
    const total = allSources.length;
    const rtsp = allSources.filter(s => s.source_type === 'RTSP').length;
    const uploaded = allSources.filter(s => s.source_type === 'FILE' || !s.source_type).length;
    const online = allSources.filter(s => s.status !== 'ERROR' && s.status !== 'STOPPED').length;
    const offline = total - online;
    return { total, online, offline, rtsp, uploaded };
  }, [allSources]);

  // Filtered active source list
  const filteredSources = useMemo(() => {
    if (filterType === 'rtsp') {
      return allSources.filter(s => s.source_type === 'RTSP');
    }
    if (filterType === 'file') {
      return allSources.filter(s => s.source_type === 'FILE' || !s.source_type);
    }
    return allSources;
  }, [allSources, filterType]);

  const handleOpenIngestion = () => {
    setShowIngestion(true);
  };

  // Determine total slots for fixed grid layouts (2x2 = 4 slots, 3x3 = 9 slots)
  const totalSlots = layoutCols === 1 ? filteredSources.length : layoutCols === 2 ? Math.max(4, filteredSources.length) : Math.max(9, filteredSources.length);
  const emptySlotsCount = Math.max(0, totalSlots - filteredSources.length);

  return (
    <div className="flex flex-col gap-6 w-full min-w-0 pb-12">
      {/* ── 1. PAGE HEADER ────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-[#021822]/90 border border-[#00d4b0]/20 rounded-xl p-5 backdrop-blur-md shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#00d4b0]/10 border border-[#00d4b0]/30 shadow-[0_0_15px_rgba(0,212,176,0.15)]">
              <Video className="w-5 h-5 text-[#00d4b0]" />
            </div>
            <div>
              <h2 className="text-xl font-bold font-mono tracking-wider text-white flex items-center gap-2">
                VIDEO FEEDS
                <span className="text-[11px] font-sans px-2 py-0.5 rounded bg-[#00d4b0]/10 border border-[#00d4b0]/30 text-[#00d4b0] font-semibold uppercase tracking-normal">
                  SURVEILLANCE MANAGER
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Live camera feeds and uploaded surveillance sources
              </p>
            </div>
          </div>
        </div>

        {/* Quick action buttons */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={handleOpenIngestion}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-mono font-bold bg-[#02141d] hover:bg-[#032333] text-cyan-300 border border-cyan-500/30 transition-all hover:shadow-[0_0_15px_rgba(6,182,212,0.2)] cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5 text-cyan-400" />
            + ADD LIVE IP CAMERA (RTSP)
          </button>
          <button
            type="button"
            onClick={handleOpenIngestion}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-mono font-bold bg-gradient-to-r from-[#00d4b0] to-[#06b6d4] hover:from-[#00bfa0] hover:to-[#0891b2] text-slate-950 font-bold border border-[#00d4b0]/40 transition-all shadow-[0_0_15px_rgba(0,212,176,0.3)] cursor-pointer"
          >
            <Film className="w-3.5 h-3.5 text-slate-950" />
            + UPLOAD VIDEO
          </button>
        </div>
      </div>

      {/* ── 2. COMPACT STATUS SUMMARY ─────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Total Feeds</p>
            <p className="text-xl font-bold font-mono text-white mt-1">{metrics.total}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
            <Tv className="w-4 h-4 text-cyan-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Online</p>
            <p className="text-xl font-bold font-mono text-emerald-400 mt-1">{metrics.online}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Offline / Standby</p>
            <p className="text-xl font-bold font-mono text-slate-400 mt-1">{metrics.offline}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-slate-800/50 border border-slate-700/50 flex items-center justify-center">
            <AlertTriangle className="w-4 h-4 text-slate-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">RTSP Cameras</p>
            <p className="text-xl font-bold font-mono text-cyan-300 mt-1">{metrics.rtsp}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            <Radio className="w-4 h-4 text-cyan-400" />
          </div>
        </div>

        <div className="bg-[#02141d] border border-[#00d4b0]/15 rounded-xl p-3.5 flex items-center justify-between col-span-2 sm:col-span-1 shadow-sm">
          <div>
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Uploaded Videos</p>
            <p className="text-xl font-bold font-mono text-purple-300 mt-1">{metrics.uploaded}</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
            <Film className="w-4 h-4 text-purple-400" />
          </div>
        </div>
      </div>

      {/* ── 3. FEED MANAGEMENT / INGESTION AREA ────────────────────────── */}
      {showIngestion && (
        <div className="relative animate-fadeIn">
          <div className="flex justify-between items-center mb-2 px-1">
            <span className="text-xs font-mono font-bold text-cyan-400 tracking-wider">
              FEED REGISTRATION &amp; UPLOAD CONSOLE
            </span>
            <button
              onClick={() => setShowIngestion(false)}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
              <span>Close Console</span>
            </button>
          </div>
          <VideoUploadPanel
            activeSource={null}
            onSourceReady={(source) => {
              if (onSourceAdded) onSourceAdded(source);
              setShowIngestion(false);
            }}
            onRemove={() => {}}
            onAnalyze={onAnalyze}
            isAnalyzing={false}
            hasResults={false}
            elapsedSec={0}
          />
        </div>
      )}

      {/* ── 4. CONDITIONAL RENDER: UPLOADED VIDEO RESULT VIEW vs MULTI-FEED GRID ── */}
      {hasUploadedVideo ? (
        /* ══════════════════════════════════════════════════════════════════════
           UPLOADED VIDEO ANALYSIS VIEW (Consistent with Defense Grid Layout)
           Left: Large Video Feed with AI Overlays & Controls
           Right: Threat Alerts & Restricted Area Intrusions
           ══════════════════════════════════════════════════════════════════════ */
        <div className="flex flex-col xl:flex-row gap-6 items-start w-full">
          {/* Main Video Area */}
          <div className="flex-1 flex flex-col gap-4 min-w-0 w-full">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                <h3 className="text-sm font-bold font-mono text-white truncate">
                  {activeSource.original_name || activeSource.name || activeSource.source_id}
                </h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 border border-purple-500/30 text-purple-300">
                  RECORDED VIDEO
                </span>
                {detectionResults && detectionResults.length > 0 && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-300">
                    ✓ INFERENCE ACTIVE
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {onAnalyze && (
                  <button
                    type="button"
                    onClick={() => onAnalyze(activeSource)}
                    disabled={isAnalyzing}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer ${
                      isAnalyzing
                        ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 cursor-wait'
                        : detectionResults && detectionResults.length > 0
                        ? 'bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-400/40 shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                        : 'bg-gradient-to-r from-blue-600 via-cyan-600 to-teal-500 hover:from-blue-500 hover:to-cyan-400 text-white border border-cyan-400/50 shadow-[0_0_15px_rgba(6,182,212,0.4)] animate-pulse'
                    }`}
                  >
                    {isAnalyzing ? (
                      <>
                        <Loader className="w-3 h-3 animate-spin text-cyan-300" />
                        <span>ANALYZING {analysisElapsed}s…</span>
                      </>
                    ) : detectionResults && detectionResults.length > 0 ? (
                      <>
                        <CheckCircle2 className="w-3 h-3 text-emerald-200" />
                        <span>RE-ANALYZE YOLO</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-3 h-3 text-yellow-300 animate-spin" />
                        <span>⚡ ANALYZE YOLO AI</span>
                      </>
                    )}
                  </button>
                )}
                {onRemoveSource && (
                  <button
                    type="button"
                    onClick={() => onRemoveSource(activeSource)}
                    className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-mono text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer border border-slate-800 hover:border-red-500/30"
                    title="Remove uploaded video"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Remove</span>
                  </button>
                )}
              </div>
            </div>

            {/* Large LiveVideoCard with complete video playback and YOLO detection overlays */}
            <div className="w-full">
              <LiveVideoCard
                source={activeSource}
                onAnalysisComplete={onAnalysisComplete}
                detectionResults={detectionResults}
                isAnalyzing={isAnalyzing}
                analysisElapsed={analysisElapsed}
                analysisSummary={analysisSummary}
                analysisError={analysisError}
                onAnalyze={onAnalyze}
              />
            </div>
          </div>

          {/* Right Sidebar - Real-Time Threat Alerts & Restricted Area Intrusions */}
          <div className="w-full xl:w-80 shrink-0 flex flex-col gap-6 sticky top-6 h-[calc(100vh-3rem)]">
            <div className="flex-1 min-h-0">
              <AlertPanel alerts={alerts} isConnected={isConnected} />
            </div>
            <div className="flex-1 min-h-0">
              <IntrusionPanel intrusions={intrusions} />
            </div>
          </div>
        </div>
      ) : (
        /* ══════════════════════════════════════════════════════════════════════
           MULTI-FEED RTSP MANAGEMENT OR EMPTY STATE
           ══════════════════════════════════════════════════════════════════════ */
        <div className="flex flex-col gap-4 w-full">
          {/* Feeds Section Header & Controls */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
            {/* Filter buttons */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setFilterType('all')}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all cursor-pointer ${
                  filterType === 'all'
                    ? 'bg-blue-600/30 text-cyan-300 border border-blue-500/50 font-bold'
                    : 'text-slate-400 hover:text-slate-200 bg-slate-900/40 hover:bg-slate-800 border border-slate-800'
                }`}
              >
                ALL FEEDS ({allSources.length})
              </button>
              <button
                type="button"
                onClick={() => setFilterType('rtsp')}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all cursor-pointer ${
                  filterType === 'rtsp'
                    ? 'bg-[#00d4b0]/20 text-[#00d4b0] border border-[#00d4b0]/40 font-bold shadow-[0_0_12px_rgba(0,212,176,0.15)]'
                    : 'text-slate-400 hover:text-slate-200 bg-[#02141d] hover:bg-[#032333] border border-[#00d4b0]/15'
                }`}
              >
                RTSP STREAMS ({metrics.rtsp})
              </button>
              <button
                type="button"
                onClick={() => setFilterType('file')}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all cursor-pointer ${
                  filterType === 'file'
                    ? 'bg-purple-600/30 text-purple-300 border border-purple-500/50 font-bold'
                    : 'text-slate-400 hover:text-slate-200 bg-[#02141d] hover:bg-[#032333] border border-[#00d4b0]/15'
                }`}
              >
                UPLOADED ({metrics.uploaded})
              </button>
            </div>

            {/* Grid layout toggles */}
            <div className="flex items-center gap-1 bg-[#02141d] border border-[#00d4b0]/20 p-1 rounded-lg">
              <button
                type="button"
                onClick={() => setLayoutCols(1)}
                title="Single Large Feed"
                className={`p-1.5 rounded text-xs transition-colors cursor-pointer ${
                  layoutCols === 1 ? 'bg-[#00d4b0]/20 text-[#00d4b0]' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setLayoutCols(2)}
                title="2x2 Grid"
                className={`p-1.5 rounded text-xs transition-colors cursor-pointer ${
                  layoutCols === 2 ? 'bg-[#00d4b0]/20 text-[#00d4b0]' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Grid2X2 className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setLayoutCols(3)}
                title="Compact Grid (3x3 Matrix)"
                className={`p-1.5 rounded transition-all cursor-pointer ${
                  layoutCols === 3 ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <LayoutGrid className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Feeds Rendering */}
          {allSources.length === 0 ? (
            /* Empty State when 0 sources exist */
            <div className="flex flex-col items-center justify-center text-center p-12 my-6 bg-slate-900/40 border-2 border-dashed border-slate-800/90 rounded-2xl">
              <div className="w-16 h-16 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mb-4 shadow-[0_0_25px_rgba(6,182,212,0.15)]">
                <Camera className="w-8 h-8 text-cyan-400" />
              </div>
              <h3 className="text-base font-bold font-mono text-white tracking-wider mb-1">
                NO ACTIVE VIDEO FEEDS
              </h3>
              <p className="text-xs text-slate-400 max-w-md mb-6">
                Connect an RTSP camera or upload a surveillance video to begin.
              </p>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <button
                  type="button"
                  onClick={handleOpenIngestion}
                  className="px-4 py-2 rounded-lg text-xs font-mono font-bold bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-cyan-500/30 transition-all hover:shadow-[0_0_15px_rgba(6,182,212,0.2)] cursor-pointer flex items-center gap-2"
                >
                  <Radio className="w-3.5 h-3.5 text-cyan-400" />
                  ADD RTSP CAMERA
                </button>
                <button
                  type="button"
                  onClick={handleOpenIngestion}
                  className="px-4 py-2 rounded-lg text-xs font-mono font-bold bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white border border-cyan-400/40 transition-all shadow-[0_0_15px_rgba(6,182,212,0.3)] cursor-pointer flex items-center gap-2"
                >
                  <Film className="w-3.5 h-3.5 text-white" />
                  UPLOAD VIDEO
                </button>
              </div>
            </div>
          ) : (
            /* Multi-feed RTSP Grid */
            <div
              className={`grid gap-6 w-full ${
                layoutCols === 1
                  ? 'grid-cols-1'
                  : layoutCols === 3
                  ? 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3'
                  : 'grid-cols-1 lg:grid-cols-2'
              }`}
            >
              {/* Render each actual active source */}
              {filteredSources.map((source) => {
                const isRtsp = source.source_type === 'RTSP';

                return (
                  <div
                    key={source.source_id}
                    className="flex flex-col bg-[#050b14] border border-slate-800/90 hover:border-cyan-500/40 rounded-xl overflow-hidden shadow-lg transition-all duration-200 group"
                  >
                    {/* Source Top Meta Header */}
                    <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950/80 border-b border-slate-800/80">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        <span className="text-xs font-mono font-bold text-white truncate">
                          {source.original_name || source.name || source.source_id}
                        </span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/30 text-cyan-400 shrink-0">
                          {isRtsp ? 'RTSP LIVE' : 'RECORDED'}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {onRemoveSource && (
                          <button
                            type="button"
                            onClick={() => onRemoveSource(source)}
                            className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-mono text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer border border-transparent hover:border-red-500/30"
                            title="Remove/Delete feed"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Remove</span>
                          </button>
                        )}
                      </div>
                    </div>

                    {/* LiveVideoCard embedded with full playback & AI overlays */}
                    <div className="p-2">
                      <LiveVideoCard
                        source={source}
                        onAnalysisComplete={onAnalysisComplete}
                        detectionResults={null}
                        isAnalyzing={false}
                        analysisElapsed={0}
                        analysisSummary={null}
                        analysisError={''}
                        onAnalyze={onAnalyze}
                      />
                    </div>
                  </div>
                );
              })}

              {/* Render clean empty/standby slots if fixed grid layout (2x2 or 3x3) has empty slots */}
              {layoutCols > 1 && Array.from({ length: emptySlotsCount }).map((_, i) => {
                const slotIndex = filteredSources.length + i + 1;
                return (
                  <div
                    key={`empty-slot-${slotIndex}`}
                    className="flex flex-col items-center justify-center p-8 bg-[#030914]/60 border border-dashed border-slate-800/80 rounded-xl min-h-[340px] text-center"
                  >
                    <div className="w-12 h-12 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center mb-3">
                      <Radio className="w-5 h-5 text-slate-600" />
                    </div>
                    <p className="text-xs font-mono font-semibold text-slate-500 uppercase tracking-wider">
                      FEED SLOT #{slotIndex}
                    </p>
                    <p className="text-[11px] font-mono text-slate-600 mt-1">
                      [ STANDBY — NO ACTIVE FEED ]
                    </p>
                    <div className="flex items-center gap-2 mt-4">
                      <button
                        type="button"
                        onClick={handleOpenIngestion}
                        className="text-[11px] font-mono px-3 py-1.5 bg-slate-800/80 hover:bg-slate-700 text-cyan-300 rounded border border-cyan-500/20 hover:border-cyan-500/40 transition-colors cursor-pointer flex items-center gap-1.5"
                      >
                        <Plus className="w-3 h-3" />
                        Connect Feed
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
