import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Camera, 
  ShieldAlert, 
  Crosshair, 
  Radio, 
  Play, 
  Square, 
  Trash2, 
  Plus, 
  Wifi, 
  WifiOff, 
  AlertTriangle, 
  CheckCircle2, 
  Eye, 
  Activity,
  Layers,
  Info,
  Clock,
  ShieldCheck,
  Check
} from 'lucide-react';
import { 
  analyzeVideo, 
  updateSourceStatus, 
  getDetectionResults,
  setVirtualFence,
  clearVirtualFence,
  getVirtualFence
} from '../../services/videoApi';

const DEFAULT_SECTOR_NAMES = [
  'SECTOR 01 — NORTH PERIMETER',
  'SECTOR 02 — EAST CHECKPOINT',
  'SECTOR 03 — SOUTH GATE ENTRY',
  'SECTOR 04 — WEST RIDGE WATCH'
];

export const CameraArrayCard = ({
  slotIndex = 0,
  source = null,
  alerts = [],
  intrusions = [],
  isConnected = false,
  onConnect = () => {},
  onDisconnect = () => {},
  onOpenEvidence = () => {},
}) => {
  const slotNumber = slotIndex + 1;
  const defaultSector = DEFAULT_SECTOR_NAMES[slotIndex] || `SECTOR 0${slotNumber}`;
  const isRtsp = source?.source_type === 'RTSP';

  // Analysis & Detection State
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState('');
  const [frameDetections, setFrameDetections] = useState(null);
  const [streamError, setStreamError] = useState(false);

  // Virtual Fence State (Local to this camera card)
  const [fenceMode, setFenceMode] = useState('none'); // 'none' | 'zone' | 'line'
  const [fencePoints, setFencePoints] = useState([]);  // Normalized [[nx, ny], ...]
  const [isFenceActive, setIsFenceActive] = useState(false);
  const [loiteringDuration, setLoiteringDuration] = useState(0); // 0 (Off), 10, 20, 30, 60, 300
  const [fenceFeedback, setFenceFeedback] = useState(null); // { type: 'success' | 'error', msg: string }

  // Connection Dialog State for empty slots
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [rtspUrl, setRtspUrl] = useState('');
  const [camName, setCamName] = useState(`Camera ${slotNumber}`);
  const [camLocation, setCamLocation] = useState(defaultSector);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const animRef = useRef(null);

  // Filter alerts & intrusions strictly to THIS camera's source_id
  const scopedAlerts = source?.source_id
    ? alerts.filter((a) => a.sourceId === source.source_id)
    : [];

  const scopedIntrusions = source?.source_id
    ? intrusions.filter((i) => i.sourceId === source.source_id)
    : [];

  // Reset states and fetch existing virtual fence configuration when source changes
  useEffect(() => {
    setStreamError(false);
    setFrameDetections(null);
    setAnalysisError('');
    setFencePoints([]);
    setIsFenceActive(false);
    setFenceMode('none');
    setLoiteringDuration(0);
    setFenceFeedback(null);

    if (source?.source_id) {
      // 1. Fetch cached detection results
      getDetectionResults(source.source_id)
        .then((data) => {
          if (data && data.frame_results && data.frame_results.length > 0) {
            setFrameDetections(data.frame_results[data.frame_results.length - 1]);
          }
        })
        .catch(() => {});

      // 2. Restore active virtual fence configuration for this source
      getVirtualFence(source.source_id)
        .then((res) => {
          if (res && res.status === 'active' && res.config?.points?.length > 0) {
            setFencePoints(res.config.points);
            setIsFenceActive(true);
            setLoiteringDuration(res.config.loitering_duration || 0);
          }
        })
        .catch(() => {});
    }
  }, [source?.source_id]);

  // Handle WebSocket frame updates for canvas bounding boxes
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleFrameBroadcast = (e) => {
      const msg = e.detail;
      if (msg?.type === 'frame_update') {
        const srcId = msg.source_id || msg.data?.source_id;
        if (srcId && source?.source_id && srcId === source.source_id) {
          setFrameDetections(msg.data);
          setIsAnalyzing(true);
        }
      }
    };

    window.addEventListener('sentinel-ws-frame', handleFrameBroadcast);
    return () => {
      window.removeEventListener('sentinel-ws-frame', handleFrameBroadcast);
    };
  }, [source?.source_id]);

  // Canvas click handler for plotting normalized fence points
  const handleCanvasClick = (e) => {
    if (fenceMode === 'none') return;
    const img = imgRef.current;
    if (!img) return;

    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mediaWidth = img.naturalWidth || 1280;
    const mediaHeight = img.naturalHeight || 720;
    if (!mediaWidth || !mediaHeight) return;

    // Calculate letterboxing/pillarboxing offsets to map click accurately
    const videoRatio = mediaWidth / mediaHeight;
    const canvasRatio = rect.width / rect.height;

    let renderWidth = rect.width;
    let renderHeight = rect.height;
    let offsetX = 0;
    let offsetY = 0;

    if (videoRatio > canvasRatio) {
      renderHeight = rect.width / videoRatio;
      offsetY = (rect.height - renderHeight) / 2;
    } else {
      renderWidth = rect.height * videoRatio;
      offsetX = (rect.width - renderWidth) / 2;
    }

    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    // Prevent clicks outside video frame
    if (clickX < offsetX || clickX > offsetX + renderWidth || clickY < offsetY || clickY > offsetY + renderHeight) {
      return;
    }

    const nx = Math.max(0.0, Math.min(1.0, (clickX - offsetX) / renderWidth));
    const ny = Math.max(0.0, Math.min(1.0, (clickY - offsetY) / renderHeight));

    setFencePoints((prev) => [...prev, [nx, ny]]);
  };

  // Canvas drawing loop for live bounding boxes AND virtual fence polygons
  const drawDetections = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (canvas.width !== img.clientWidth || canvas.height !== img.clientHeight) {
      canvas.width = img.clientWidth || 320;
      canvas.height = img.clientHeight || 180;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const mediaW = img.naturalWidth || 1280;
    const mediaH = img.naturalHeight || 720;

    if (mediaW > 0 && mediaH > 0 && canvas.width > 0 && canvas.height > 0) {
      const videoRatio = mediaW / mediaH;
      const canvasRatio = canvas.width / canvas.height;

      let renderWidth = canvas.width;
      let renderHeight = canvas.height;
      let offsetX = 0;
      let offsetY = 0;

      if (videoRatio > canvasRatio) {
        renderHeight = canvas.width / videoRatio;
        offsetY = (canvas.height - renderHeight) / 2;
      } else {
        renderWidth = canvas.height * videoRatio;
        offsetX = (canvas.width - renderWidth) / 2;
      }

      const scaleX = renderWidth / mediaW;
      const scaleY = renderHeight / mediaH;

      // ── 1. Draw Virtual Fence (Restricted Zone / Virtual Line) ──
      if (fencePoints.length > 0) {
        ctx.save();
        ctx.lineWidth = 2.5;
        const isZone = fenceMode === 'zone' || (fenceMode === 'none' && isFenceActive && fencePoints.length > 2);
        
        ctx.strokeStyle = isZone ? '#f59e0b' : '#3b82f6'; // Amber for Zone, Blue for Line
        ctx.fillStyle = isZone ? 'rgba(245, 158, 11, 0.22)' : 'rgba(59, 130, 246, 0.22)';

        ctx.beginPath();
        fencePoints.forEach((pt, idx) => {
          const px = pt[0] * renderWidth + offsetX;
          const py = pt[1] * renderHeight + offsetY;
          if (idx === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });

        if (isZone && fencePoints.length > 2) {
          ctx.closePath();
          ctx.fill();
        }
        ctx.stroke();

        // Draw vertex anchor points
        fencePoints.forEach((pt) => {
          const px = pt[0] * renderWidth + offsetX;
          const py = pt[1] * renderHeight + offsetY;
          ctx.beginPath();
          ctx.arc(px, py, 3.5, 0, 2 * Math.PI);
          ctx.fillStyle = '#ffffff';
          ctx.fill();
          ctx.strokeStyle = isZone ? '#f59e0b' : '#3b82f6';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        });
        ctx.restore();
      }

      // ── 2. Draw YOLO Bounding Boxes ──
      if (frameDetections && frameDetections.detections && frameDetections.detections.length > 0) {
        frameDetections.detections.forEach((det) => {
          let x1 = det.x1 != null ? det.x1 : (det.bbox ? det.bbox[0] : 0);
          let y1 = det.y1 != null ? det.y1 : (det.bbox ? det.bbox[1] : 0);
          let x2 = det.x2 != null ? det.x2 : (det.bbox ? det.bbox[2] : 0);
          let y2 = det.y2 != null ? det.y2 : (det.bbox ? det.bbox[3] : 0);

          if (x2 <= 1.0 && y2 <= 1.0 && mediaW > 1) {
            x1 *= mediaW;
            y1 *= mediaH;
            x2 *= mediaW;
            y2 *= mediaH;
          }

          const bx = x1 * scaleX + offsetX;
          const by = y1 * scaleY + offsetY;
          const bw = (x2 - x1) * scaleX;
          const bh = (y2 - y1) * scaleY;

          const cName = (det.class_name || 'OBJECT').toUpperCase();
          const conf = Math.round((det.confidence || 0.8) * 100);
          const isPerson = cName === 'PERSON';

          ctx.strokeStyle = isPerson ? '#ef4444' : '#06b6d4';
          ctx.lineWidth = 2;
          ctx.strokeRect(bx, by, bw, bh);

          // Label tag
          const tagText = det.track_id != null ? `${cName} #${det.track_id} ${conf}%` : `${cName} ${conf}%`;
          ctx.font = 'bold 10px monospace';
          const textWidth = ctx.measureText(tagText).width;
          ctx.fillStyle = isPerson ? 'rgba(239, 68, 68, 0.85)' : 'rgba(6, 182, 212, 0.85)';
          ctx.fillRect(bx, Math.max(0, by - 16), textWidth + 6, 16);
          ctx.fillStyle = '#ffffff';
          ctx.fillText(tagText, bx + 3, Math.max(12, by - 4));
        });
      }
    }

    animRef.current = requestAnimationFrame(drawDetections);
  }, [frameDetections, fencePoints, fenceMode, isFenceActive]);

  useEffect(() => {
    animRef.current = requestAnimationFrame(drawDetections);
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [drawDetections]);

  // Start analysis for this specific camera
  const handleStartAnalysis = async () => {
    if (!source?.source_id) return;
    setIsAnalyzing(true);
    setAnalysisError('');
    try {
      await analyzeVideo(source.source_id);
    } catch (err) {
      setAnalysisError(err.message || 'Failed to start AI analysis');
      setIsAnalyzing(false);
    }
  };

  // Stop analysis for this specific camera
  const handleStopAnalysis = async () => {
    if (!source?.source_id) return;
    try {
      await updateSourceStatus(source.source_id, 'STOPPED');
      setIsAnalyzing(false);
    } catch (err) {
      setAnalysisError(err.message || 'Failed to stop stream');
    }
  };

  // Save Virtual Fence / Restricted Area
  const handleSaveFence = async () => {
    if (!source?.source_id) return;

    if (fenceMode === 'zone' && fencePoints.length < 3) {
      setFenceFeedback({ type: 'error', msg: 'Restricted Zone requires at least 3 points.' });
      return;
    }
    if (fenceMode === 'line' && fencePoints.length < 2) {
      setFenceFeedback({ type: 'error', msg: 'Virtual Fence Line requires at least 2 points.' });
      return;
    }

    try {
      const payload = {
        type: fenceMode,
        points: fencePoints,
        loitering_duration: (fenceMode === 'zone' && loiteringDuration > 0) ? loiteringDuration : null,
      };

      await setVirtualFence(source.source_id, payload);
      setIsFenceActive(true);
      setFenceMode('none');
      setFenceFeedback({ type: 'success', msg: `${payload.type === 'zone' ? 'Restricted Zone' : 'Virtual Line'} saved!` });
      setTimeout(() => setFenceFeedback(null), 3000);

      // Trigger/ensure continuous stream processing is active
      if (source?.source_id) {
        analyzeVideo(source.source_id).catch(() => {});
      }
    } catch (err) {
      setFenceFeedback({ type: 'error', msg: err.message || 'Failed to save virtual fence' });
    }
  };

  // Clear Virtual Fence from this specific camera
  const handleClearFence = async () => {
    if (!source?.source_id) return;
    try {
      await clearVirtualFence(source.source_id);
    } catch (e) {}
    setFencePoints([]);
    setIsFenceActive(false);
    setFenceMode('none');
    setFenceFeedback({ type: 'success', msg: 'Virtual fence cleared.' });
    setTimeout(() => setFenceFeedback(null), 3000);
  };

  // Cancel drawing and revert to previous active fence
  const handleCancelDrawing = async () => {
    setFenceMode('none');
    setFenceFeedback(null);
    if (source?.source_id) {
      try {
        const res = await getVirtualFence(source.source_id);
        if (res && res.status === 'active' && res.config?.points?.length > 0) {
          setFencePoints(res.config.points);
          setIsFenceActive(true);
          return;
        }
      } catch (e) {}
    }
    setFencePoints([]);
    setIsFenceActive(false);
  };

  // Connect submission handler
  const handleConnectSubmit = async (e) => {
    e.preventDefault();
    if (!rtspUrl.trim()) {
      setFormError('RTSP Stream URL is required.');
      return;
    }
    setFormError('');
    setIsSubmitting(true);
    try {
      await onConnect({
        name: camName.trim() || `Camera ${slotNumber}`,
        location: camLocation.trim() || defaultSector,
        url: rtspUrl.trim(),
      }, slotIndex);
      setShowConnectModal(false);
      setRtspUrl('');
    } catch (err) {
      setFormError(err.message || 'Failed to connect RTSP stream');
    } finally {
      setIsSubmitting(false);
    }
  };

  // ───────────────────────────────────────────────────────────────────────────
  // EMPTY STATE CARD
  // ───────────────────────────────────────────────────────────────────────────
  if (!source) {
    return (
      <div className="bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-xl p-4 flex flex-col justify-between h-full min-h-[460px] shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
        {/* Header */}
        <div className="flex justify-between items-center pb-3 border-b border-slate-800/80">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-800 text-slate-400 border border-slate-700">
              CAM 0{slotNumber}
            </span>
            <span className="text-xs font-mono font-semibold text-slate-300">
              {defaultSector}
            </span>
          </div>
          <span className="flex items-center gap-1.5 text-[10px] font-mono text-slate-500">
            <span className="w-2 h-2 rounded-full bg-slate-700" />
            DISCONNECTED
          </span>
        </div>

        {/* Empty Slot Placeholder */}
        <div className="flex-1 flex flex-col items-center justify-center my-6 py-8 border-2 border-dashed border-slate-800/80 rounded-lg bg-slate-950/40 text-center px-4">
          <div className="w-12 h-12 rounded-full bg-slate-800/50 border border-slate-700 flex items-center justify-center text-slate-500 mb-3">
            <Camera className="w-6 h-6 opacity-60" />
          </div>
          <h4 className="text-sm font-bold text-white font-mono mb-1">
            CAMERA 0{slotNumber} AVAILABLE
          </h4>
          <p className="text-[11px] text-slate-400 max-w-xs mb-4">
            Connect an RTSP stream or live IP camera feed to start real-time surveillance & AI detection.
          </p>
          <button
            onClick={() => setShowConnectModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold font-mono rounded-lg transition-all shadow-[0_0_15px_rgba(37,99,235,0.3)]"
          >
            <Plus className="w-4 h-4" />
            CONNECT RTSP CAMERA
          </button>
        </div>

        {/* Footer info */}
        <div className="text-[10px] font-mono text-slate-500 text-center pt-2 border-t border-slate-800/60">
          QUAD ARRAY SLOT #{slotNumber} • READY FOR INGESTION
        </div>

        {/* Connect RTSP Modal */}
        {showConnectModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl">
              <div className="flex justify-between items-center mb-4 pb-2 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <Radio className="w-5 h-5 text-cyan-400" />
                  <h3 className="text-sm font-bold font-mono text-white">
                    CONNECT CAMERA 0{slotNumber}
                  </h3>
                </div>
                <button 
                  onClick={() => setShowConnectModal(false)}
                  className="text-slate-400 hover:text-white"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleConnectSubmit} className="space-y-3">
                {formError && (
                  <div className="p-2.5 rounded bg-red-950/60 border border-red-500/40 text-red-300 text-xs font-mono">
                    {formError}
                  </div>
                )}
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">
                    CAMERA NAME
                  </label>
                  <input
                    type="text"
                    value={camName}
                    onChange={(e) => setCamName(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded text-xs text-white focus:border-cyan-500 outline-none font-mono"
                    placeholder="e.g. North Gate Camera"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">
                    SECTOR / LOCATION
                  </label>
                  <input
                    type="text"
                    value={camLocation}
                    onChange={(e) => setCamLocation(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded text-xs text-white focus:border-cyan-500 outline-none font-mono"
                    placeholder="e.g. Sector 01 — North Perimeter"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">
                    RTSP STREAM URL <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={rtspUrl}
                    onChange={(e) => setRtspUrl(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded text-xs text-white focus:border-cyan-500 outline-none font-mono"
                    placeholder="rtsp://192.168.1.100:554/stream"
                  />
                  <p className="text-[10px] text-slate-500 mt-1">
                    Direct RTSP/H.264 video feed endpoint.
                  </p>
                </div>

                <div className="flex justify-end gap-2 pt-3 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setShowConnectModal(false)}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-mono rounded"
                  >
                    CANCEL
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono font-bold rounded flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {isSubmitting ? 'CONNECTING...' : 'INITIALIZE FEED'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ───────────────────────────────────────────────────────────────────────────
  // ACTIVE CAMERA CARD (CONNECTED FEED)
  // ───────────────────────────────────────────────────────────────────────────
  const mjpegUrl = `/api/v1/video/mjpeg/${encodeURIComponent(source.source_id)}`;

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-xl flex flex-col h-full overflow-hidden shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
      {/* ── 1. Header ── */}
      <div className="p-3 border-b border-slate-800/80 bg-slate-950/60 flex justify-between items-center gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shrink-0">
            CAM 0{slotNumber}
          </span>
          <div className="min-w-0">
            <h4 className="text-xs font-bold font-mono text-white truncate">
              {source.original_name || source.name || `Camera 0${slotNumber}`}
            </h4>
            <p className="text-[10px] font-mono text-slate-400 truncate">
              {source.location || defaultSector}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* Virtual Fence Active Indicator */}
          {isFenceActive && (
            <span className="flex items-center gap-1 text-[9px] font-mono font-bold text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/30">
              <ShieldAlert className="w-3 h-3 text-amber-400" />
              FENCE
            </span>
          )}

          {/* Live Status Badge */}
          {isAnalyzing ? (
            <span className="flex items-center gap-1 text-[9px] font-mono font-bold text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/30">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              AI ACTIVE
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[9px] font-mono font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              LIVE
            </span>
          )}

          {/* Disconnect / Unbind button */}
          <button
            title="Disconnect Camera"
            onClick={() => onDisconnect(source.source_id)}
            className="p-1 rounded hover:bg-red-500/20 text-slate-400 hover:text-red-400 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* ── 2. Live Stream & Canvas Area ── */}
      <div className="relative bg-black w-full aspect-video flex items-center justify-center overflow-hidden border-b border-slate-800">
        {streamError ? (
          <div className="p-4 text-center">
            <AlertTriangle className="w-6 h-6 text-amber-400 mx-auto mb-1" />
            <p className="text-xs font-mono text-slate-400">Stream signal lost or reconnecting...</p>
          </div>
        ) : (
          <img
            ref={imgRef}
            src={mjpegUrl}
            alt={source.name}
            onError={() => setStreamError(true)}
            className="w-full h-full object-contain"
          />
        )}

        {/* AI Overlay Canvas + Fence Interaction */}
        <canvas
          ref={canvasRef}
          onClick={handleCanvasClick}
          className={`absolute inset-0 w-full h-full z-10 ${
            fenceMode !== 'none' ? 'cursor-crosshair pointer-events-auto' : 'pointer-events-none'
          }`}
        />

        {/* Stream Tag Overlay */}
        <div className="absolute top-2 left-2 pointer-events-none flex items-center gap-1 z-20">
          <span className="px-1.5 py-0.5 rounded bg-black/70 backdrop-blur-sm border border-slate-700/60 text-[9px] font-mono font-bold text-cyan-300">
            CAM-{slotNumber < 10 ? `0${slotNumber}` : slotNumber} [RTSP]
          </span>
          {fenceMode !== 'none' && (
            <span className="px-1.5 py-0.5 rounded bg-amber-500 text-black text-[9px] font-mono font-bold animate-pulse">
              CLICK TO DRAW {fenceMode.toUpperCase()} ({fencePoints.length} PTS)
            </span>
          )}
        </div>

        {/* Controls Overlay Button (Bottom-Right) */}
        <div className="absolute bottom-2 right-2 flex gap-1 z-20">
          {isAnalyzing ? (
            <button
              onClick={handleStopAnalysis}
              className="px-2 py-1 bg-red-600/90 hover:bg-red-500 text-white rounded text-[10px] font-mono font-bold flex items-center gap-1 shadow"
            >
              <Square className="w-3 h-3" /> STOP AI
            </button>
          ) : (
            <button
              onClick={handleStartAnalysis}
              className="px-2.5 py-1 bg-cyan-600/90 hover:bg-cyan-500 text-white rounded text-[10px] font-mono font-bold flex items-center gap-1 shadow"
            >
              <Play className="w-3 h-3" /> START AI
            </button>
          )}
        </div>
      </div>

      {/* ── 3. Virtual Fence Editor Control Toolbar ── */}
      <div className="px-3 py-2 bg-slate-950/80 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
        {fenceMode !== 'none' ? (
          /* Active Drawing Controls */
          <div className="flex flex-wrap items-center gap-2 w-full justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/40 text-[10px] font-bold">
                {fenceMode === 'zone' ? 'DRAWING ZONE' : 'DRAWING LINE'}: {fencePoints.length} PTS
              </span>

              {/* Loiter Limit Selector for Zones */}
              {fenceMode === 'zone' && (
                <div className="flex items-center gap-1 text-[10px] bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5">
                  <Clock className="w-3 h-3 text-amber-400" />
                  <span className="text-slate-400">LOITER:</span>
                  <select
                    value={loiteringDuration}
                    onChange={(e) => setLoiteringDuration(Number(e.target.value))}
                    className="bg-transparent text-cyan-300 text-[10px] font-mono font-bold focus:outline-none cursor-pointer"
                  >
                    <option value={0} className="bg-slate-900 text-white">Disabled</option>
                    <option value={10} className="bg-slate-900 text-white">10 sec</option>
                    <option value={20} className="bg-slate-900 text-white">20 sec</option>
                    <option value={30} className="bg-slate-900 text-white">30 sec</option>
                    <option value={60} className="bg-slate-900 text-white">1 min</option>
                    <option value={300} className="bg-slate-900 text-white">5 min</option>
                  </select>
                </div>
              )}

              <button
                onClick={() => setFencePoints([])}
                className="text-[10px] text-red-400 hover:text-red-300 px-1.5 py-0.5 hover:bg-red-950/40 rounded transition-colors"
              >
                Clear Points
              </button>
            </div>

            <div className="flex items-center gap-1.5">
              <button
                onClick={handleCancelDrawing}
                className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[10px] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveFence}
                className="px-3 py-1 bg-amber-600 hover:bg-amber-500 text-white font-bold rounded text-[10px] flex items-center gap-1 shadow shadow-amber-900/50 transition-colors"
              >
                <Check className="w-3 h-3" /> Save {fenceMode === 'zone' ? 'Zone' : 'Line'}
              </button>
            </div>
          </div>
        ) : (
          /* Normal State: Add Zone / Line / Clear buttons */
          <div className="flex flex-wrap items-center gap-2 w-full justify-between">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-slate-400 flex items-center gap-1 font-bold">
                <ShieldAlert className={`w-3.5 h-3.5 ${isFenceActive ? 'text-amber-400' : 'text-slate-500'}`} />
                RESTRICTED AREA:
              </span>
              <button
                onClick={() => {
                  setFenceMode('zone');
                  setFencePoints([]);
                }}
                className="px-2 py-1 bg-slate-900 hover:bg-slate-800 text-amber-300 hover:text-amber-200 border border-amber-500/30 rounded text-[10px] flex items-center gap-1 transition-colors"
              >
                + Draw Zone
              </button>
              <button
                onClick={() => {
                  setFenceMode('line');
                  setFencePoints([]);
                }}
                className="px-2 py-1 bg-slate-900 hover:bg-slate-800 text-cyan-300 hover:text-cyan-200 border border-cyan-500/30 rounded text-[10px] flex items-center gap-1 transition-colors"
              >
                + Draw Line
              </button>
            </div>

            {isFenceActive && (
              <button
                onClick={handleClearFence}
                className="text-[10px] text-red-400 hover:text-red-300 px-2 py-0.5 hover:bg-red-950/40 rounded border border-red-500/20 transition-colors"
              >
                Clear Fence
              </button>
            )}
          </div>
        )}
      </div>

      {/* Feedback banner */}
      {fenceFeedback && (
        <div className={`px-3 py-1 text-[10px] font-mono border-b ${
          fenceFeedback.type === 'success' 
            ? 'bg-emerald-950/70 border-emerald-500/40 text-emerald-300' 
            : 'bg-red-950/70 border-red-500/40 text-red-300'
        }`}>
          {fenceFeedback.msg}
        </div>
      )}

      {/* Error notification if any */}
      {analysisError && (
        <div className="px-3 py-1.5 bg-red-950/60 border-b border-red-500/40 text-red-300 text-[10px] font-mono">
          {analysisError}
        </div>
      )}

      {/* ── 4. Split Scoped Telemetry (Threat Alerts & Restricted Intrusions) ── */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-800/80 min-h-[180px] max-h-[220px]">
        {/* 4A. Threat Alerts Box (Scoped to this source) */}
        <div className="flex flex-col min-h-0 bg-slate-950/30">
          <div className="px-3 py-1.5 bg-slate-950/70 border-b border-slate-800/60 flex justify-between items-center">
            <div className="flex items-center gap-1.5 text-[10px] font-mono font-bold text-red-400">
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>THREAT ALERTS ({scopedAlerts.length})</span>
            </div>
            <span className="text-[9px] font-mono text-slate-500">SCOPED</span>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {scopedAlerts.length === 0 ? (
              <div className="py-6 text-center text-slate-500 font-mono text-[10px]">
                No threat alerts for Cam 0{slotNumber}
              </div>
            ) : (
              scopedAlerts.slice(0, 15).map((al, i) => (
                <div
                  key={al.id || i}
                  className="p-1.5 rounded border border-slate-800 bg-slate-900/60 flex items-start justify-between gap-1 text-[10px] font-mono"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1">
                      <span className={`px-1 rounded text-[8px] font-bold ${
                        al.severity === 'Critical' ? 'bg-red-500/20 text-red-400 border border-red-500/40' :
                        al.severity === 'High' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/40' :
                        'bg-yellow-500/20 text-yellow-400 border border-yellow-500/40'
                      }`}>
                        {al.severity || 'ALERT'}
                      </span>
                      <span className="text-white font-semibold truncate">{al.type}</span>
                    </div>
                    <p className="text-slate-400 text-[9px] truncate mt-0.5">{al.description}</p>
                  </div>
                  <div className="flex flex-col items-end shrink-0 gap-1">
                    <span className="text-slate-500 text-[8px]">{al.time}</span>
                    <button
                      title="View Evidence Snapshot"
                      onClick={() => onOpenEvidence(al)}
                      className="p-0.5 rounded hover:bg-slate-700 text-slate-400 hover:text-cyan-400"
                    >
                      <Camera className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 4B. Restricted Intrusions Box (Scoped to this source) */}
        <div className="flex flex-col min-h-0 bg-slate-950/30">
          <div className="px-3 py-1.5 bg-slate-950/70 border-b border-slate-800/60 flex justify-between items-center">
            <div className="flex items-center gap-1.5 text-[10px] font-mono font-bold text-amber-400">
              <Crosshair className="w-3.5 h-3.5" />
              <span>INTRUSIONS ({scopedIntrusions.length})</span>
            </div>
            <span className="text-[9px] font-mono text-slate-500">SCOPED</span>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {scopedIntrusions.length === 0 ? (
              <div className="py-6 text-center text-slate-500 font-mono text-[10px]">
                No intrusions for Cam 0{slotNumber}
              </div>
            ) : (
              scopedIntrusions.slice(0, 15).map((intr, i) => (
                <div
                  key={intr.id || i}
                  className="p-1.5 rounded border border-red-500/30 bg-red-950/30 flex items-start justify-between gap-1 text-[10px] font-mono"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1">
                      <span className="px-1 rounded text-[8px] font-bold bg-red-500/20 text-red-400 border border-red-500/40">
                        {intr.type || 'INTRUSION'}
                      </span>
                      <span className="text-white font-semibold truncate">
                        {intr.objectClass} {intr.trackId ? `#${intr.trackId}` : ''}
                      </span>
                    </div>
                    <p className="text-amber-400 text-[9px] truncate mt-0.5">{intr.description || intr.status}</p>
                  </div>
                  <span className="text-slate-500 text-[8px] shrink-0">{intr.time}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CameraArrayCard;
