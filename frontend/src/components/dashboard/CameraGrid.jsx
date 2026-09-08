import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Camera, AlertCircle, Settings, Maximize2, Radio, Activity, Loader, ShieldAlert } from 'lucide-react';
import { analyzeVideo, getDetectionResults, setVirtualFence, clearVirtualFence, getVirtualFence } from '../../services/videoApi';
import { useWebSocket } from '../../hooks/useWebSocket';

// ── Status helpers ───────────────────────────────────────────────────────────

const STATUS_BADGE = {
  PLAYING:   { cls: 'border-emerald-500/50 text-emerald-400 bg-emerald-500/10', label: 'PLAYING',   pulse: true },
  CONNECTED: { cls: 'border-blue-500/50    text-blue-400    bg-blue-500/10',    label: 'CONNECTED', pulse: false },
  STOPPED:   { cls: 'border-amber-500/50   text-amber-400   bg-amber-500/10',   label: 'STOPPED',   pulse: false },
  ERROR:     { cls: 'border-red-500/50     text-red-400     bg-red-500/10',     label: 'ERROR',     pulse: false },
  IDLE:      { cls: 'border-slate-700      text-slate-500   bg-transparent',    label: 'IDLE',      pulse: false },
};

// ── LiveVideoCard — renders a <video> element from the backend stream URL ────

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/v1/ws`;

export const LiveVideoCard = ({
  source,
  onAnalysisComplete,
  detectionResults: externalDetectionResults,
  isAnalyzing: externalIsAnalyzing,
  analysisElapsed: externalElapsed,
  analysisSummary: externalSummary,
  analysisError: externalError,
  onAnalyze: externalOnAnalyze,
}) => {
  const isRtsp = source?.source_type === 'RTSP';
  const videoRef = useRef(null);
  const imgRef = useRef(null);
  const canvasRef = useRef(null);
  const requestRef = useRef(null);
  const badge = STATUS_BADGE[source.status] ?? STATUS_BADGE.IDLE;

  const [internalAnalyzing, setInternalAnalyzing] = useState(false);
  const [internalDetectionResults, setInternalDetectionResults] = useState(null);
  const [internalAnalysisError, setInternalAnalysisError] = useState('');
  const [internalAnalysisSummary, setInternalAnalysisSummary] = useState(null);
  const [internalElapsedSec, setInternalElapsedSec] = useState(0);

  // Phase 7: Virtual Fence State
  const [fenceMode, setFenceMode] = useState('none'); // 'none', 'zone', 'line'
  const [fencePoints, setFencePoints] = useState([]);
  const [isFenceActive, setIsFenceActive] = useState(false);
  // Phase 9: Loitering Detection Duration in seconds (0 = Disabled, 10, 20, 30, 60, 300)
  const [loiteringDuration, setLoiteringDuration] = useState(0);

  // Presentational UI Inputs (No backend effect)
  const [uiSector, setUiSector] = useState(source.location || 'PRIMARY SURVEILLANCE FEED');
  const [uiName, setUiName] = useState(source.original_name || source.name || 'FEED 01');

  // Phase 6: Frontend Face Recognition State { [track_id]: { status, name, role, confidence, time } }
  const [faceRecognitions, setFaceRecognitions] = useState({});
  // Phase 8 / ANPR: Frontend License Plate State { [track_id]: { plate_number, ocr_confidence, is_watchlist_match, ... } }
  const [anprRecognitions, setAnprRecognitions] = useState({});

  // ── Per-card WebSocket subscription for frame updates, face recognition, and ANPR ──
  // Subscribes to the shared WebSocket and filters frame_update (for RTSP),
  // face_recognition, and anpr_recognition messages by source_id.
  const handleWsMessage = useCallback((parsed) => {
    const srcId = parsed?.source_id || parsed?.data?.source_id;
    const sourceNameStem = source?.name ? source.name.replace(/\.[^/.]+$/, '') : null;
    const matchesSource = !srcId || srcId === source?.source_id || srcId === source?.name || srcId === sourceNameStem;

    if (parsed?.type === 'frame_update' && matchesSource) {
      const frame = parsed.data;
      if (isRtsp) {
        console.log('[RTSP_ANALYZE_TRACE][UI_RECEIVED] Frame update for RTSP:', frame.frame_index, 'dets:', frame.detections?.length);
        setInternalDetectionResults((prev) => {
          const next = [...(prev || []), frame];
          return next.length > 15 ? next.slice(next.length - 15) : next;
        });
        setInternalAnalysisSummary((prev) => ({
          frames: (prev?.frames || 0) + 1,
          detections: (prev?.detections || 0) + (frame.detections?.length || 0),
          classes: 'Live',
        }));
      } else {
        setInternalDetectionResults((prev) => [...(prev || []), frame]);
        setInternalAnalysisSummary((prev) => ({
          frames: (prev?.frames || 0) + 1,
          detections: (prev?.detections || 0) + (frame.detections?.length || 0),
          classes: (frame.detections || []).map(d => d.class_name).filter(Boolean).slice(0, 3).join(', ') || 'Processing...',
        }));
      }
    } else if (parsed?.type === 'face_recognition') {
      const data = parsed.data || parsed;
      const srcId = parsed.source_id || data.source_id;
      const trkId = data.track_id ?? parsed.track_id;
      const sourceNameStem = source?.name ? source.name.replace(/\.[^/.]+$/, '') : null;
      const matchesSource = !srcId || srcId === source?.source_id || srcId === source?.name || srcId === sourceNameStem;
      if (trkId != null && matchesSource) {
        setFaceRecognitions((prev) => ({
          ...prev,
          [trkId]: {
            status: data.status || parsed.status,
            name: data.name || parsed.name,
            role: data.role || parsed.role,
            confidence: data.confidence ?? parsed.confidence,
            time: data.time || parsed.time,
          },
        }));
      }
    } else if (parsed?.type === 'anpr_recognition') {
      console.log('[ANPR_TRACE][FRONTEND_RECEIVED][CANVAS_BADGE]', parsed);
      const data = parsed.data || parsed;
      const srcId = parsed.source_id || data.source_id;
      const trkId = data.track_id ?? parsed.track_id;
      const sourceNameStem = source?.name ? source.name.replace(/\.[^/.]+$/, '') : null;
      const matchesSource = !srcId || srcId === source?.source_id || srcId === source?.name || srcId === sourceNameStem;
      if (trkId != null && matchesSource) {
        setAnprRecognitions((prev) => {
          const next = { ...prev };
          if (data.plate_number) {
            for (const [existingTid, existingRec] of Object.entries(next)) {
              if (String(existingTid) !== String(trkId) && existingRec?.plate_number === data.plate_number) {
                delete next[existingTid];
              }
            }
          }
          next[trkId] = {
            plate_number: data.plate_number,
            ocr_confidence: data.ocr_confidence,
            plate_confidence: data.plate_confidence,
            confidence_pct: data.confidence_pct ?? Math.round((data.ocr_confidence || 0) * 100),
            vehicle_class: data.vehicle_class,
            is_watchlist_match: data.is_watchlist_match,
            watchlist_category: data.watchlist_category,
            time: data.time,
          };
          return next;
        });
      }
    }
  }, [isRtsp, source?.source_id, source?.name]);

  useWebSocket({
    url: WS_URL,
    onMessage: handleWsMessage,
    enabled: true,
  });

  // For RTSP cards, always use internal state (fed by WS). For file sources,
  // allow external props from App.jsx to override (uploaded video flow).
  const isAnalyzing = !isRtsp && externalIsAnalyzing !== undefined ? externalIsAnalyzing : internalAnalyzing;
  const detectionResults = isRtsp
    ? internalDetectionResults
    : (externalDetectionResults !== undefined ? externalDetectionResults : internalDetectionResults);
  const analysisError = !isRtsp && externalError !== undefined ? externalError : internalAnalysisError;
  const analysisSummary = isRtsp
    ? internalAnalysisSummary
    : (externalSummary !== undefined ? externalSummary : internalAnalysisSummary);
  const elapsedSec = !isRtsp && externalElapsed !== undefined ? externalElapsed : internalElapsedSec;

  const autoStartedRef = useRef(new Set());

  // When the stream URL changes, force a reload of the video element & check for cached results
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.load();
    }

    // Auto-start continuous YOLO detection once for RTSP stream
    if (isRtsp && source?.source_id) {
      if (!autoStartedRef.current.has(source.source_id)) {
        autoStartedRef.current.add(source.source_id);
        analyzeVideo(source.source_id).catch(() => {});
      }
    }

    if (externalDetectionResults === undefined) {
      setInternalDetectionResults(null);
      setInternalAnalysisError('');
      setInternalAnalysisSummary(null);
      setInternalElapsedSec(0);

      // Check if this source already has cached detection results
      if (source?.source_id) {
        getDetectionResults(source.source_id)
          .then((data) => {
            if (data && data.frame_results) {
              setInternalDetectionResults(data.frame_results);
              setInternalAnalysisSummary({
                frames: data.frames_processed,
                detections: data.total_detections,
                classes: (data.unique_classes || []).join(', ') || 'none',
              });
              if (onAnalysisComplete) {
                onAnalysisComplete(data, source);
              }
            }
          })
          .catch(() => {});

        // Sync active virtual fence configuration from backend
        getVirtualFence(source.source_id)
          .then((res) => {
            if (res && res.status === 'active' && res.config?.points?.length > 0) {
              setFencePoints(res.config.points);
              setFenceMode('none');
              setIsFenceActive(true);
              if (res.config.loitering_duration) {
                setLoiteringDuration(res.config.loitering_duration);
              }
            } else {
              setFencePoints([]);
              setIsFenceActive(false);
              setFenceMode('none');
            }
          })
          .catch(() => {});
      }
    }
  }, [source.stream_url, source.source_id, isRtsp]);

  const handleAnalyze = async () => {
    if (!isRtsp && externalOnAnalyze) {
      return externalOnAnalyze(source);
    }

    setInternalAnalyzing(true);
    setInternalAnalysisError('');
    setInternalElapsedSec(0);

    // Show live elapsed time so the user can see progress
    const startTs = Date.now();
    const ticker = setInterval(() => {
      setInternalElapsedSec(Math.floor((Date.now() - startTs) / 1000));
    }, 1000);

    try {
      console.log(`[RTSP_ANALYZE_TRACE][UI_ANALYZE_CLICK] Starting analysis for ${source.source_id}`);
      const data = await analyzeVideo(source.source_id);

      if (!isRtsp) {
        setInternalDetectionResults(data.frame_results);
        setInternalAnalysisSummary({
          frames: data.frames_processed,
          detections: data.total_detections,
          classes: (data.unique_classes || []).join(', ') || 'none',
        });

        if (onAnalysisComplete) {
          onAnalysisComplete(data, source);
        }
      } else {
        console.log(`[RTSP_ANALYZE_TRACE][SESSION_STARTED] Real-time detection active for ${source.source_id}`);
        if (externalOnAnalyze) {
          externalOnAnalyze(source).catch(() => {});
        }
      }
    } catch (err) {
      console.error('[ANALYZE] ❌ Error:', err.message, err);
      setInternalAnalysisError(err.message);
    } finally {
      clearInterval(ticker);
      setInternalAnalyzing(false);
    }
  };

  // Canvas drawing loop
  const drawDetections = useCallback(() => {
    const MATCH_THRESHOLD = 1.5;

    // Sync canvas size to video/image element size
    const mediaEl = isRtsp ? imgRef.current : videoRef.current;
    if (!mediaEl || !canvasRef.current) {
      requestRef.current = requestAnimationFrame(drawDetections);
      return;
    }

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    if (canvas.width !== mediaEl.clientWidth || canvas.height !== mediaEl.clientHeight) {
      canvas.width = mediaEl.clientWidth;
      canvas.height = mediaEl.clientHeight;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // For RTSP, we might not have a reliable currentTime. We'll use latest frame if recent, or simply the last frame.
    // To match bounding boxes, we just use the most recent detection result for RTSP.
    let closestFrame = null;
    let minDiff = Infinity;
    
    if (detectionResults && detectionResults.length > 0) {
      if (isRtsp) {
        // Just use the latest result for RTSP live stream
        closestFrame = detectionResults[detectionResults.length - 1];
        minDiff = 0; // force draw
      } else {
        const currentTime = mediaEl.currentTime || 0;
        for (let i = 0; i < detectionResults.length; i++) {
          const frame = detectionResults[i];
          const diff = Math.abs(frame.timestamp_sec - currentTime);
          if (diff < minDiff) {
            minDiff = diff;
            closestFrame = frame;
          }
        }
        // Fallback: If video is paused, at start, or during analysis, display closest or latest frame
        if (minDiff > MATCH_THRESHOLD && (isAnalyzing || currentTime < 0.1 || mediaEl.paused)) {
          closestFrame = detectionResults[detectionResults.length - 1] || detectionResults[0];
          minDiff = 0;
        }
      }
    }

    const mediaWidth = isRtsp ? (mediaEl.naturalWidth || 1280) : (mediaEl.videoWidth || mediaEl.clientWidth || 1280);
    const mediaHeight = isRtsp ? (mediaEl.naturalHeight || 720) : (mediaEl.videoHeight || mediaEl.clientHeight || 720);

    if (mediaWidth > 0 && mediaHeight > 0) {
      const videoRatio = mediaWidth / mediaHeight;
      const canvasRatio = canvas.width / canvas.height;
      
      let renderWidth = canvas.width;
      let renderHeight = canvas.height;
      let offsetX = 0;
      let offsetY = 0;
      
      if (videoRatio > canvasRatio) {
        // Letterboxed top and bottom
        renderHeight = canvas.width / videoRatio;
        offsetY = (canvas.height - renderHeight) / 2;
      } else {
        // Pillarboxed sides
        renderWidth = canvas.height * videoRatio;
        offsetX = (canvas.width - renderWidth) / 2;
      }
      
      const drawScaleX = renderWidth / mediaWidth;
      const drawScaleY = renderHeight / mediaHeight;

      // Phase 7: Draw Virtual Fence
      if (fencePoints.length > 0) {
        ctx.save();
        ctx.lineWidth = 2.5;
        const isZone = fenceMode === 'zone' || (fenceMode === 'none' && isFenceActive && fencePoints.length > 2);
        ctx.strokeStyle = isZone ? '#f59e0b' : '#3b82f6'; // Amber for zone, Blue for line
        ctx.fillStyle = isZone ? 'rgba(245, 158, 11, 0.2)' : 'rgba(59, 130, 246, 0.2)';
        
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
        
        // Draw points
        fencePoints.forEach((pt) => {
          const px = pt[0] * renderWidth + offsetX;
          const py = pt[1] * renderHeight + offsetY;
          ctx.beginPath();
          ctx.arc(px, py, 4, 0, 2 * Math.PI);
          ctx.fillStyle = '#fff';
          ctx.fill();
        });
        ctx.restore();
      }

      // Draw detections if we're within range of sampled frame
      if (closestFrame && minDiff <= MATCH_THRESHOLD && closestFrame.detections) {
        closestFrame.detections.forEach((det) => {
          let detX1 = det.x1 != null ? det.x1 : (det.bbox ? det.bbox[0] : 0);
          let detY1 = det.y1 != null ? det.y1 : (det.bbox ? det.bbox[1] : 0);
          let detX2 = det.x2 != null ? det.x2 : (det.bbox ? det.bbox[2] : 0);
          let detY2 = det.y2 != null ? det.y2 : (det.bbox ? det.bbox[3] : 0);

          // If normalized coords (0..1), scale to native media dimensions
          if (detX2 <= 1.0 && detY2 <= 1.0 && mediaWidth > 1) {
            detX1 = detX1 * mediaWidth;
            detY1 = detY1 * mediaHeight;
            detX2 = detX2 * mediaWidth;
            detY2 = detY2 * mediaHeight;
          }

          const x = detX1 * drawScaleX + offsetX;
          const y = detY1 * drawScaleY + offsetY;
          const w = (detX2 - detX1) * drawScaleX;
          const h = (detY2 - detY1) * drawScaleY;

        const isPriority = det.is_priority || det.class_name.toLowerCase() === 'person';
        const primaryColor = isPriority ? '#ef4444' : '#06b6d4';
        const fillColor = isPriority ? 'rgba(239, 68, 68, 0.12)' : 'rgba(6, 182, 212, 0.10)';

        // 1. Semi-transparent target area fill
        ctx.fillStyle = fillColor;
        ctx.fillRect(x, y, w, h);

        // 2. Main Bounding Box
        ctx.strokeStyle = primaryColor;
        ctx.lineWidth = 2.5;
        ctx.strokeRect(x, y, w, h);

        // 3. Tactical Corner Reticles (surveillance look)
        const cornerLen = Math.min(16, w / 4, h / 4);
        ctx.lineWidth = 4;
        ctx.strokeStyle = primaryColor;

        // Top-Left
        ctx.beginPath();
        ctx.moveTo(x, y + cornerLen);
        ctx.lineTo(x, y);
        ctx.lineTo(x + cornerLen, y);
        ctx.stroke();

        // Top-Right
        ctx.beginPath();
        ctx.moveTo(x + w - cornerLen, y);
        ctx.lineTo(x + w, y);
        ctx.lineTo(x + w, y + cornerLen);
        ctx.stroke();

        // Bottom-Left
        ctx.beginPath();
        ctx.moveTo(x, y + h - cornerLen);
        ctx.lineTo(x, y + h);
        ctx.lineTo(x + cornerLen, y + h);
        ctx.stroke();

        // Bottom-Right
        ctx.beginPath();
        ctx.moveTo(x + w - cornerLen, y + h);
        ctx.lineTo(x + w, y + h);
        ctx.lineTo(x + w, y + h - cornerLen);
        ctx.stroke();

        // 4. Label Badge at Top-Left of Box
        // YOLO detection confidence
        const trackSuffix = det.track_id != null ? ` #${det.track_id}` : '';
        const yoloConf = Math.round(det.confidence * 100);
        const labelText = `${det.class_name.toUpperCase()}${trackSuffix} ${yoloConf}%`;
        ctx.font = 'bold 13px system-ui, -apple-system, sans-serif';
        const textWidth = ctx.measureText(labelText).width;
        const badgeHeight = 22;
        const badgeWidth = textWidth + 14;
        const badgeY = y - badgeHeight > 0 ? y - badgeHeight : y;

        // Badge background
        ctx.fillStyle = primaryColor;
        ctx.fillRect(x, badgeY, badgeWidth, badgeHeight);

        // Badge text
        ctx.fillStyle = '#ffffff';
        ctx.fillText(labelText, x + 7, badgeY + 15);

        // Phase 6: Face Recognition Badge (rendered separately below or alongside)
        const isPerson = det.class_name.toLowerCase() === 'person';
        const faceInfo = (isPerson && det.track_id != null) ? faceRecognitions[det.track_id] : null;

        if (faceInfo) {
          const isKnown = faceInfo.status === 'KNOWN_PERSON';
          const faceColor = isKnown ? '#10b981' : '#f59e0b'; // Emerald Green for Known, Amber for Unknown
          const faceIcon = isKnown ? '✓ ' : '? ';
          const displayName = isKnown && faceInfo.name && faceInfo.name !== 'Unknown Person'
            ? faceInfo.name
            : 'UNKNOWN';

          const rawConf = faceInfo.confidence != null ? faceInfo.confidence : null;
          const faceConfPct = rawConf != null ? Math.round(rawConf * (rawConf <= 1 ? 100 : 1)) : null;
          const faceConfStr = faceConfPct != null ? ` • ${faceConfPct}%` : '';
          const faceLabel = `${faceIcon}${displayName}${faceConfStr}`;

          ctx.font = 'bold 12px system-ui, -apple-system, sans-serif';
          const faceTextWidth = ctx.measureText(faceLabel).width;
          const faceBadgeHeight = 20;
          const faceBadgeWidth = faceTextWidth + 12;

          // Place face recognition badge cleanly below the box (or under top badge if at bottom edge)
          let faceBadgeX = x;
          let faceBadgeY = y + h + 4;
          if (faceBadgeY + faceBadgeHeight > canvas.height) {
            faceBadgeY = badgeY + badgeHeight + 2;
          }

          // Face Badge Background
          ctx.fillStyle = faceColor;
          ctx.fillRect(faceBadgeX, faceBadgeY, faceBadgeWidth, faceBadgeHeight);

          // Face Badge Text
          ctx.fillStyle = '#ffffff';
          ctx.fillText(faceLabel, faceBadgeX + 6, faceBadgeY + 14);
        }

        // Phase 8: License Plate Recognition Badge (rendered beneath vehicle bounding box)
        const isVehicle = ['car', 'truck', 'bus', 'motorcycle'].includes(det.class_name.toLowerCase());
        const anprInfo = (isVehicle && det.track_id != null) ? anprRecognitions[det.track_id] : null;

        if (anprInfo && anprInfo.plate_number) {
          const plateText = anprInfo.plate_number;
          const confPct = anprInfo.confidence_pct != null ? anprInfo.confidence_pct : Math.round((anprInfo.ocr_confidence || 0.9) * 100);
          const isMatch = !!anprInfo.is_watchlist_match;
          const plateBadgeLabel = `${plateText}  |  ${confPct}%`;

          ctx.font = 'bold 11px system-ui, -apple-system, sans-serif';
          const plateTextWidth = ctx.measureText(plateBadgeLabel).width;
          const plateBadgeHeight = 20;
          const plateBadgeWidth = plateTextWidth + 14;

          // Place ANPR badge cleanly below the box (or under top badge if at bottom edge)
          let plateBadgeX = x;
          let plateBadgeY = y + h + 4;
          if (plateBadgeY + plateBadgeHeight > canvas.height) {
            plateBadgeY = badgeY + badgeHeight + 2;
          }

          // Tactical Sentinel AI styling
          ctx.fillStyle = isMatch ? '#7f1d1d' : '#0f172a';
          ctx.fillRect(plateBadgeX, plateBadgeY, plateBadgeWidth, plateBadgeHeight);

          ctx.strokeStyle = isMatch ? '#ef4444' : '#06b6d4';
          ctx.lineWidth = 1.5;
          ctx.strokeRect(plateBadgeX, plateBadgeY, plateBadgeWidth, plateBadgeHeight);

          ctx.fillStyle = isMatch ? '#fca5a5' : '#38bdf8';
          ctx.fillText(plateBadgeLabel, plateBadgeX + 7, plateBadgeY + 14);
        }
      });
    }
  }

  requestRef.current = requestAnimationFrame(drawDetections);
}, [detectionResults, fencePoints, fenceMode, isFenceActive, faceRecognitions, anprRecognitions]);

  useEffect(() => {
    requestRef.current = requestAnimationFrame(drawDetections);
    return () => {
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
    };
  }, [drawDetections]);

  // Phase 7: Canvas click handler for drawing
  const handleCanvasClick = (e) => {
    if (fenceMode === 'none') return;
    
    const mediaEl = isRtsp ? imgRef.current : videoRef.current;
    if (!mediaEl) return;
    
    const rect = canvasRef.current.getBoundingClientRect();
    
    const mediaWidth = isRtsp ? mediaEl.naturalWidth : mediaEl.videoWidth;
    const mediaHeight = isRtsp ? mediaEl.naturalHeight : mediaEl.videoHeight;
    if (!mediaWidth || !mediaHeight) return;
    
    // Recalculate letterboxing/pillarboxing offsets to map click correctly
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

    // Prevent drawing outside the actual video frame
    if (clickX < offsetX || clickX > offsetX + renderWidth || clickY < offsetY || clickY > offsetY + renderHeight) {
      return;
    }

    const nx = (clickX - offsetX) / renderWidth;
    const ny = (clickY - offsetY) / renderHeight;
    
    setFencePoints((prev) => [...prev, [nx, ny]]);
  };

  return (
    <div className="relative flex flex-col bg-[#030914] border-2 border-[#00f3ff]/40 shadow-[0_0_30px_rgba(0,243,255,0.15)] rounded-xl overflow-hidden group mb-4">
      {/* Video area */}
      <div className="relative aspect-video bg-black overflow-hidden flex items-center justify-center">
        {isRtsp ? (
          <img 
            ref={imgRef}
            src={source.stream_url}
            className="w-full h-full object-contain"
            alt="RTSP MJPEG Stream"
            onError={(e) => {
               // Prevent infinite loops on error, just log
               console.error("MJPEG stream error");
            }}
          />
        ) : (
          <video
            ref={videoRef}
            src={source.stream_url}
            className="w-full h-full object-contain"
            controls
            autoPlay
            loop
            muted
            playsInline
            onError={() => {}}
          >
            Your browser does not support the video tag.
          </video>
        )}

        <canvas
          ref={canvasRef}
          onClick={handleCanvasClick}
          className={`absolute inset-0 w-full h-full z-10 ${fenceMode !== 'none' ? 'cursor-crosshair pointer-events-auto' : 'pointer-events-none'}`}
        />

        {/* OSD overlay — top-left: source label */}
        <div className="absolute top-3 left-3 pointer-events-none flex flex-col gap-1 z-10">
          <span className="font-mono text-xs text-black bg-[#00f3ff] px-3 py-1 rounded border border-[#00f3ff] shadow-[0_0_15px_rgba(0,243,255,0.6)] font-extrabold tracking-wider">
            {uiName}
          </span>
          {isAnalyzing && (
            <span className="font-mono text-[10px] text-blue-300 bg-blue-950/90 px-2 py-0.5 rounded backdrop-blur-sm w-fit border border-blue-500/40 animate-pulse font-semibold">
              AI INFERENCE IN PROGRESS… {elapsedSec}s
            </span>
          )}
          {analysisSummary && !isAnalyzing && (
            <span className="font-mono text-[10px] text-emerald-300 bg-emerald-950/90 px-2 py-0.5 rounded backdrop-blur-sm w-fit border border-emerald-500/40 font-semibold">
              ✓ {analysisSummary.frames} FRAMES • {analysisSummary.detections} TARGETS DETECTED
            </span>
          )}
          {analysisError && (
            <span className="font-mono text-[10px] text-red-400 bg-red-950/90 px-2 py-0.5 rounded backdrop-blur-sm w-fit border border-red-500/40 font-semibold">
              ERR: {analysisError}
            </span>
          )}
        </div>

        {/* OSD overlay — top-right: live indicator + Quick AI Action */}
        <div className="absolute top-2.5 right-2.5 flex items-center gap-2 z-20 pointer-events-auto">
          {source.status === 'PLAYING' && (
            <div className="flex items-center gap-1.5 bg-black/75 px-2 py-1 rounded border border-emerald-500/30 backdrop-blur-sm">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="font-mono text-[10px] font-bold text-emerald-400">
                STREAM LIVE
              </span>
            </div>
          )}
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md font-mono text-xs font-bold transition-all shadow-lg cursor-pointer backdrop-blur-md ${
              detectionResults && !isAnalyzing
                ? 'bg-emerald-600/90 hover:bg-emerald-500 text-white border border-emerald-400/50 shadow-[0_0_15px_rgba(16,185,129,0.3)]'
                : isAnalyzing
                  ? 'bg-blue-600/90 text-blue-100 border border-blue-400/50 cursor-wait'
                  : 'bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white border border-cyan-400/50 shadow-[0_0_18px_rgba(6,182,212,0.4)]'
            }`}
            title={detectionResults ? 'Re-run YOLO AI detection' : 'Analyze Video with YOLO AI'}
          >
            {isAnalyzing ? (
              <>
                <Loader className="w-3.5 h-3.5 animate-spin text-cyan-200" />
                <span>ANALYZING {elapsedSec}s…</span>
              </>
            ) : detectionResults ? (
              <>
                <Activity className="w-3.5 h-3.5" />
                <span>RE-ANALYZE</span>
              </>
            ) : (
              <>
                <Activity className="w-3.5 h-3.5" />
                <span>⚡ ANALYZE AI</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Control bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-[#0a1220] border-t-2 border-[#06b6d4]/40">
        <div className="flex flex-col gap-3 min-w-[300px]">
          <div className="flex flex-col">
            <label className="text-[10px] text-[#06b6d4] font-bold font-mono uppercase tracking-widest mb-1">Camera Name</label>
            <input 
              className="bg-[#030914] border border-[#06b6d4]/50 text-[#00f3ff] text-sm font-bold font-mono px-3 py-1.5 rounded focus:outline-none focus:border-[#00f3ff] focus:shadow-[0_0_10px_rgba(0,243,255,0.3)] transition-all"
              value={uiName} 
              onChange={e => setUiName(e.target.value)} 
            />
          </div>
          <div className="flex flex-col">
            <label className="text-[10px] text-[#4d7c0f] font-bold font-mono uppercase tracking-widest mb-1">Sector Assignment</label>
            <div className="flex items-center gap-2 font-mono">
              <Radio className="w-4 h-4 text-[#4d7c0f] animate-pulse" />
              <input 
                className="bg-[#030914] border border-[#4d7c0f]/50 text-[#4d7c0f] text-xs font-bold font-mono px-3 py-1.5 rounded focus:outline-none focus:border-[#4d7c0f] focus:shadow-[0_0_10px_rgba(77,124,15,0.3)] transition-all flex-1 uppercase"
                value={uiSector} 
                onChange={e => setUiSector(e.target.value)} 
              />
            </div>
          </div>
        </div>

        {/* Phase 7: Virtual Fence Controls */}
        <div className="flex flex-wrap items-center gap-2 border-l border-slate-700 pl-4 ml-2">
          <ShieldAlert className={`w-4 h-4 ${isFenceActive ? 'text-amber-500' : 'text-slate-600'}`} />
          {fenceMode !== 'none' ? (
            <>
              {fenceMode === 'zone' && (
                <div className="flex items-center gap-1.5 bg-[#030914] border border-amber-500/50 shadow-[0_0_10px_rgba(245,158,11,0.2)] rounded px-2 py-1">
                  <label className="text-[11px] text-amber-400 font-bold font-mono uppercase tracking-wider whitespace-nowrap">
                    Loiter Limit:
                  </label>
                  <select
                    value={loiteringDuration}
                    onChange={(e) => setLoiteringDuration(Number(e.target.value))}
                    className="bg-[#0f172a] text-[#00f3ff] text-xs font-mono font-bold border border-slate-700 rounded px-2 py-0.5 focus:outline-none focus:border-cyan-400 cursor-pointer"
                  >
                    <option value={0}>Off (Disabled)</option>
                    <option value={10}>10 sec</option>
                    <option value={20}>20 sec</option>
                    <option value={30}>30 sec</option>
                    <option value={60}>1 min</option>
                    <option value={300}>5 min</option>
                  </select>
                </div>
              )}
              <button onClick={() => setFencePoints([])} className="text-xs text-red-400 px-2 py-1 hover:bg-red-950/50 rounded font-mono transition-colors">
                Clear Points
              </button>
              <button 
                onClick={async () => {
                  setFenceMode('none');
                  setFencePoints([]);
                  if (source?.source_id) {
                    try {
                      await clearVirtualFence(source.source_id);
                    } catch (e) {}
                  }
                  setIsFenceActive(false);
                }} 
                className="text-xs text-slate-400 px-2 py-1 hover:bg-slate-800 rounded font-mono transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={async () => {
                  if (fencePoints.length < 2 || (fenceMode === 'zone' && fencePoints.length < 3)) return;
                  try {
                    const payload = {
                      type: fenceMode,
                      points: fencePoints,
                      loitering_duration: (fenceMode === 'zone' && loiteringDuration > 0) ? loiteringDuration : null,
                    };
                    await setVirtualFence(source.source_id, payload);
                    setIsFenceActive(true);
                    setFenceMode('none');
                    if (isRtsp && source?.source_id) {
                      analyzeVideo(source.source_id).catch(() => {});
                    }
                  } catch (e) {
                    console.error("Failed to save fence", e);
                  }
                }} 
                className="text-xs bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 rounded shadow shadow-amber-900/50 font-bold font-mono transition-colors"
              >
                Save {fenceMode === 'zone' ? 'Zone' : 'Line'}
              </button>
            </>
          ) : (
            <>
              <button 
                onClick={async () => {
                  setFenceMode('zone');
                  setFencePoints([]);
                  if (source?.source_id) {
                    try {
                      await clearVirtualFence(source.source_id);
                    } catch (e) {}
                  }
                  setIsFenceActive(false);
                }} 
                className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded font-mono border border-slate-700 transition-colors"
              >
                + Draw Zone
              </button>
              <button 
                onClick={async () => {
                  setFenceMode('line');
                  setFencePoints([]);
                  if (source?.source_id) {
                    try {
                      await clearVirtualFence(source.source_id);
                    } catch (e) {}
                  }
                  setIsFenceActive(false);
                }} 
                className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded font-mono border border-slate-700 transition-colors"
              >
                + Draw Line
              </button>
              {(isFenceActive || fencePoints.length > 0) && (
                <button 
                  onClick={async () => {
                    if (source?.source_id) {
                      try {
                        await clearVirtualFence(source.source_id);
                      } catch (e) {}
                    }
                    setFencePoints([]);
                    setIsFenceActive(false);
                    setFenceMode('none');
                  }} 
                  className="text-xs text-red-400 px-2 py-1 hover:bg-red-950/50 rounded font-mono transition-colors"
                >
                  Clear All
                </button>
              )}
            </>
          )}
        </div>

        <div className="flex items-center gap-2 text-slate-400 ml-auto">
          <button 
            type="button"
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className={`flex items-center gap-1.5 text-xs font-mono font-bold px-3.5 py-1.5 rounded-lg transition-all ${
              detectionResults && !isAnalyzing
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30 cursor-pointer shadow-[0_0_15px_rgba(16,185,129,0.15)]'
                : isAnalyzing
                  ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 cursor-wait'
                  : 'bg-gradient-to-r from-[var(--peacock-blue)] to-[var(--neon-teal)] hover:from-cyan-500 hover:to-blue-500 text-black shadow-[0_0_18px_rgba(0,243,255,0.3)] border border-[var(--neon-teal)]/40 cursor-pointer'
            }`}
            title={detectionResults ? 'Re-run YOLO analysis' : 'Analyze Video with YOLO AI'}
          >
            {isAnalyzing ? (
              <Loader className="w-3.5 h-3.5 animate-spin text-cyan-300" />
            ) : (
              <Activity className="w-3.5 h-3.5" />
            )}
            {isAnalyzing
              ? `ANALYZING ${elapsedSec}s…`
              : detectionResults
                ? 'RE-ANALYZE'
                : '⚡ ANALYZE WITH AI'
            }
          </button>
        </div>
      </div>
    </div>
  );
};

// ── CameraCard — static placeholder card ─────────────────────────────────────
import { addRtspCamera } from '../../services/videoApi';

// Derive a stable, URL-safe source_id from a sector name.
// e.g. "Sector 4 - Alpha" → "sector_4_alpha"
const sectorSlug = (name) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');

export const CameraCard = ({ name, location, isOnline, detectionStatus, hasAlert, onSourceAdded }) => {
  const [url, setUrl] = useState('');
  const [connecting, setConnecting] = useState(false);
  
  // Presentational Inputs (No backend effect)
  const [uiSector, setUiSector] = useState(location || 'Sector');
  const [uiName, setUiName] = useState(name || 'Camera');
  
  const handleConnect = async (e) => {
      e.preventDefault();
      if (!url) return;
      setConnecting(true);
      try {
          // Pass a stable source_id so reconnect always reuses the same slot.
          const stableId = sectorSlug(name);
          const newSrc = await addRtspCamera({
            name: `Feed - ${name}`,
            location: name,        // original_name stored as sector name for display
            url,
            source_id: stableId,  // stable ID for sector-based mapping
          });
          if (onSourceAdded) onSourceAdded(newSrc);
      } catch (err) {
          console.error("Failed to connect RTSP:", err);
          alert(err.message || "Failed to connect RTSP stream");
      } finally {
          setConnecting(false);
      }
  };

  return (
    <div className={`relative flex flex-col bg-[#02141d] border-2 ${hasAlert ? 'border-red-500 shadow-[0_0_30px_rgba(239,68,68,0.3)]' : 'border-[#00d4b0]/30 shadow-[0_0_20px_rgba(0,212,176,0.1)]'} rounded-xl overflow-hidden group mb-4`}>
      {/* Video Placeholder Area */}
      <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
        {/* Fake video feed noise/gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#010e14] via-[#021622] to-black opacity-85"></div>

        {!isOnline ? (
          <div className="flex flex-col items-center text-slate-600 z-10">
            <AlertCircle className="w-8 h-8 mb-2 text-slate-600" />
            <span className="font-mono text-xs font-bold tracking-widest text-slate-500">FEED STANDBY</span>
          </div>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center z-10">
             <form onSubmit={handleConnect} className="flex flex-col gap-2 p-4 bg-[#01121a]/90 rounded-lg border border-[#00d4b0]/30 backdrop-blur-sm">
                 <span className="text-xs text-[#00d4b0] font-bold font-mono text-center mb-2 tracking-widest">CONNECT RTSP STREAM</span>
                 <input 
                     type="text" 
                     placeholder="rtsp://..." 
                     value={url}
                     onChange={(e) => setUrl(e.target.value)}
                     className="bg-[#010e14] text-[#00d4b0] text-sm font-mono px-4 py-2 rounded border border-[#00d4b0]/40 outline-none focus:border-[#00d4b0] focus:shadow-[0_0_15px_rgba(0,212,176,0.3)] w-64 text-center transition-all"
                 />
                 <button 
                     type="submit" 
                     disabled={connecting || !url}
                     className="bg-gradient-to-r from-[#00b896] to-[#06b6d4] hover:brightness-110 disabled:bg-slate-800 text-[#011218] font-mono text-xs font-bold px-3 py-1.5 rounded transition-colors cursor-pointer shadow-[0_0_12px_rgba(0,212,176,0.3)]"
                 >
                     {connecting ? 'Connecting...' : 'CONNECT'}
                 </button>
             </form>
             <div className="absolute inset-0 border border-white/5 m-3 flex flex-col justify-between pointer-events-none p-2">
               {/* OSD (On-Screen Display) */}
               <div className="flex justify-between items-center text-white/80 font-mono text-[10px]">
                 <span className="bg-black/60 px-1.5 py-0.5 rounded border border-white/10">{name}</span>
                 <span className="flex items-center gap-1 bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded border border-red-500/30">
                   <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                   REC
                 </span>
               </div>
               <div className="text-right text-white/50 font-mono text-[9px]">
                 SECTOR GRID • {location}
               </div>
             </div>
          </div>
        )}
      </div>

      {/* Camera Controls & Status Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-[#01141f] border-t-2 border-[#00d4b0]/30">
        <div className="flex flex-col gap-3 min-w-[300px]">
          <div className="flex flex-col">
            <label className="text-[10px] text-[#00d4b0] font-bold font-mono uppercase tracking-widest mb-1">Camera Name</label>
            <div className="flex items-center gap-3">
              <input 
                className="bg-[#010e14] border border-[#00d4b0]/40 text-[#00d4b0] text-sm font-bold font-mono px-3 py-1.5 rounded focus:outline-none focus:border-[#00d4b0] focus:shadow-[0_0_10px_rgba(0,212,176,0.3)] transition-all flex-1"
                value={uiName}
                onChange={e => setUiName(e.target.value)}
              />
              {isOnline ? (
                <div className="flex items-center gap-1.5 px-2 py-1 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-400 text-[10px] font-bold tracking-widest">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#10b981] animate-pulse" />
                  ONLINE
                </div>
              ) : (
                <div className="flex items-center gap-1.5 px-2 py-1 bg-slate-800/50 border border-slate-600 rounded text-slate-400 text-[10px] font-bold tracking-widest">
                  <span className="w-2 h-2 rounded-full bg-slate-500" />
                  STANDBY
                </div>
              )}
            </div>
          </div>
          <div className="flex flex-col">
            <label className="text-[10px] text-[#4a8a80] font-bold font-mono uppercase tracking-widest mb-1">Sector Assignment</label>
            <input 
              className="bg-[#010e14] border border-[#00d4b0]/30 text-[#4a8a80] text-xs font-bold font-mono px-3 py-1.5 rounded focus:outline-none focus:border-[#00d4b0] focus:shadow-[0_0_10px_rgba(0,212,176,0.2)] transition-all uppercase w-full"
              value={uiSector}
              onChange={e => setUiSector(e.target.value)}
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${hasAlert ? 'border-red-500/50 text-red-400 bg-red-500/10 font-bold' : 'border-[#00d4b0]/20 text-[#6aa89f] bg-[#011218]'}`}>
            {detectionStatus}
          </span>
        </div>
      </div>
    </div>
  );
};

// ── CameraGrid ───────────────────────────────────────────────────────────────

/**
 * CameraGrid
 *
 * Props:
 *   cameras          {Array}       — Static camera placeholder data
 *   activeSources    {Array}       — Array of active RTSP sources
 *   uploadedSource   {Object|null} — Uploaded video source
 *   onAnalysisComplete {Function}  — Callback when analysis completes
 *   detectionResults {Array|null}  — Detection results data for uploaded video
 *   isAnalyzing      {boolean}     — Whether analysis is currently in progress
 *   analysisElapsed  {number}      — Elapsed seconds
 *   analysisSummary  {Object|null} — Summary data
 *   analysisError    {string}      — Error message
 *   onAnalyze        {Function}    — Trigger analysis handler
 *   onSourceAdded    {Function}    — Triggered when RTSP source is added
 *   onRemoveSource   {Function}    — Triggered when a source is removed
 */
export const CameraGrid = ({
  cameras,
  activeSources,
  uploadedSource,
  onAnalysisComplete,
  detectionResults,
  isAnalyzing,
  analysisElapsed,
  analysisSummary,
  analysisError,
  onAnalyze,
  onSourceAdded,
  onRemoveSource,
}) => {
  // Build a fast lookup: source_id → source object
  const sourceById = Object.fromEntries((activeSources || []).map(s => [s.source_id, s]));

  return (
    <div className="flex flex-col gap-6 w-full">
      {/* Uploaded Video rendering full width if present */}
      {uploadedSource && (
        <div className="w-full">
          <div className="flex justify-between items-center mb-2">
            <h4 className="text-sm font-bold text-white">Uploaded Video Analysis</h4>
            <button onClick={() => onRemoveSource(uploadedSource)} className="text-xs text-red-400 hover:text-red-300">Close Upload</button>
          </div>
          <LiveVideoCard
            source={uploadedSource}
            onAnalysisComplete={onAnalysisComplete}
            detectionResults={detectionResults}
            isAnalyzing={isAnalyzing}
            analysisElapsed={analysisElapsed}
            analysisSummary={analysisSummary}
            analysisError={analysisError}
            onAnalyze={onAnalyze}
          />
        </div>
      )}

      {/* Full-width Sector Camera Cards */}
      <div className="flex flex-col gap-8 w-full">
        {cameras.map((cam, idx) => {
          // Map by stable sector slug source_id — no fragile display-name matching
          const stableId = sectorSlug(cam.name);
          const src = sourceById[stableId];
          
          if (src) {
             return (
               <div key={idx} className="relative group">
                 {/* Each RTSP LiveVideoCard manages its own WS-driven detection state */}
                 <LiveVideoCard 
                   source={src} 
                   onAnalysisComplete={onAnalysisComplete}
                   onAnalyze={onAnalyze}
                 />
                 {/* Disconnect button */}
                 <button 
                    onClick={() => onRemoveSource(src)}
                    className="absolute top-3 right-3 z-30 bg-red-600 hover:bg-red-500 text-white text-xs px-2 py-1 rounded shadow opacity-0 group-hover:opacity-100 transition-opacity"
                 >
                    Disconnect
                 </button>
               </div>
             );
          }

          return <CameraCard key={idx} {...cam} onSourceAdded={onSourceAdded} />;
        })}
      </div>
    </div>
  );
};
