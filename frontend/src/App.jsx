import React, { useState, useCallback, useEffect, useRef } from 'react';
import Layout from './components/layout/Layout';
import StatCard from './components/dashboard/StatCard';
import { CameraGrid } from './components/dashboard/CameraGrid';
import AlertPanel from './components/dashboard/AlertPanel';
import IntrusionPanel from './components/dashboard/IntrusionPanel';
import RecentEventsTable from './components/dashboard/RecentEventsTable';
import VideoUploadPanel from './components/dashboard/VideoUploadPanel';
import PersonnelRegistry from './components/personnel/PersonnelRegistry';
import VideoFeedsView from './components/video/VideoFeedsView';
import ThreatAlertsView from './components/alerts/ThreatAlertsView';
import EventLogbookView from './components/events/EventLogbookView';
import CameraArrayView from './components/camera/CameraArrayView';
import AIModelConfigView from './components/config/AIModelConfigView';
import { deleteSource, getSources, analyzeVideo, getDetectionResults } from './services/videoApi';
import { useWebSocket } from './hooks/useWebSocket';
import { Camera, Users, Car, AlertTriangle } from 'lucide-react';
import { useAuth } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import VerifyOTPPage from './pages/VerifyOTPPage';

// ── WebSocket URL ─────────────────────────────────────────────────────────────
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/v1/ws`;


// ── Web Audio API Tactical Alarm Synthesizer ──────────────────────────────
let _sharedAudioCtx = null;

const getAudioContext = () => {
  if (!_sharedAudioCtx && typeof window !== 'undefined') {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (AudioCtx) {
      _sharedAudioCtx = new AudioCtx();
    }
  }
  return _sharedAudioCtx;
};

// Automatically unlock and resume AudioContext on first user interaction
if (typeof window !== 'undefined') {
  const unlockAudio = () => {
    const ctx = getAudioContext();
    if (ctx && ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }
    window.removeEventListener('click', unlockAudio);
    window.removeEventListener('keydown', unlockAudio);
    window.removeEventListener('touchstart', unlockAudio);
  };
  window.addEventListener('click', unlockAudio);
  window.addEventListener('keydown', unlockAudio);
  window.addEventListener('touchstart', unlockAudio);
}

const playAlarmSound = (type = 'default') => {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;

    const playTone = () => {
      try {
        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        if (type === 'loitering') {
          // Urgent tactical dual-tone pulse for Loitering Detection
          osc.type = 'sawtooth';
          osc.frequency.setValueAtTime(880, now);
          osc.frequency.exponentialRampToValueAtTime(440, now + 0.15);
          osc.frequency.setValueAtTime(880, now + 0.20);
          osc.frequency.exponentialRampToValueAtTime(440, now + 0.35);
          gain.gain.setValueAtTime(0.25, now);
          gain.gain.exponentialRampToValueAtTime(0.01, now + 0.40);
          osc.start(now);
          osc.stop(now + 0.40);
        } else {
          // Standard perimeter breach chime
          osc.type = 'sine';
          osc.frequency.setValueAtTime(587.33, now);
          gain.gain.setValueAtTime(0.18, now);
          gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
          osc.start(now);
          osc.stop(now + 0.25);
        }

        osc.onended = () => {
          try {
            osc.disconnect();
            gain.disconnect();
          } catch (_) {}
        };
      } catch (err) {
        console.warn('[Audio] Synth play error:', err);
      }
    };

    if (ctx.state === 'suspended') {
      ctx.resume().then(playTone).catch(() => {});
    } else {
      playTone();
    }
  } catch (e) {
    // Autoplay policy or unsupported audio
  }
};


// ── Vehicle Classes Set ───────────────────────────────────────────────────
const VEHICLE_CLASSES = new Set(['car', 'truck', 'bus', 'motorcycle', 'bicycle']);

function App() {
  // ── Auth State ────────────────────────────────────────────────────────────
  const { isAuthenticated, isLoading: authLoading, user, logout } = useAuth();
  const [publicPage, setPublicPage] = useState('landing'); // 'landing'|'login'|'register'|'verify-otp'
  // OTP verification state — populated when /register returns pending_id
  const [otpPendingId, setOtpPendingId]     = useState('');
  const [otpPendingEmail, setOtpPendingEmail] = useState('');

  // ── Navigation Tab State ──────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState('defense-grid');

  // ── Video Ingestion State ─────────────────────────────────────────────────
  const [activeSource, setActiveSource] = useState(null); // Used for single file uploads
  const [activeSources, setActiveSources] = useState([]); // Used for multiple RTSP streams

  // ── Real Detection Metrics ────────────────────────────────────────────────
  const [metrics, setMetrics] = useState({
    personCount: 0,
    vehicleCount: 0,
    totalDetections: 0,
    framesProcessed: 0,
  });

  // ── Analysis State ────────────────────────────────────────────────────────
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisElapsed, setAnalysisElapsed] = useState(0);
  const [detectionResults, setDetectionResults] = useState(null);
  const [analysisSummary, setAnalysisSummary] = useState(null);
  const [analysisError, setAnalysisError] = useState('');

  // ── Real Events State ─────────────────────────────────────────────────────
  const [events, setEvents] = useState([]);

  // ── Live Alerts State ─────────────────────────────────────────────────────
  const [alerts, setAlerts] = useState([]);

  // ── Phase 7: Intrusion Events State ───────────────────────────────────────
  const [intrusions, setIntrusions] = useState([]);

  // Phase 6: Persistent recognized track identities { [source_id_track_id]: { isKnown, name, confPct } }
  const recognizedTracksRef = useRef(new Map());
  const isAnalyzingRef = useRef(false);

  // Initial fetch of registered sources on load: only activate live RTSP streams
  useEffect(() => {
    getSources()
      .then((sources) => {
        // Only active RTSP cameras are persisted streams on initial load.
        // Historical files in backend storage must NOT be auto-activated as feeds.
        const liveRtsp = (sources || []).filter(s => s.source_type === 'RTSP');
        setActiveSources(liveRtsp);
      })
      .catch(() => {});
  }, []);

  const handleSourceReady = useCallback((source) => {
    setActiveSources((prev) => {
      const exists = prev.find(s => s.source_id === source.source_id);
      return exists ? prev.map(s => s.source_id === source.source_id ? source : s) : [...prev, source];
    });
    if (source.source_type !== 'RTSP') {
      setActiveSource((curr) => {
        if (curr?.source_id !== source.source_id) {
          setEvents([]); // Reset events state when switching to new source
        }
        return source;
      });
      setDetectionResults(null);
      setAnalysisSummary(null);
      setAnalysisError('');
    }
  }, []);

  const handleRemoveSource = useCallback(async (sourceToRemove = activeSource) => {
    if (!sourceToRemove) return;
    const targetId = typeof sourceToRemove === 'string' ? sourceToRemove : sourceToRemove.source_id;
    if (!targetId) return;

    try {
      await deleteSource(targetId);
    } catch {
      // Source may already be gone on server
    }
    setActiveSources((prev) => prev.filter(s => s.source_id !== targetId));
    setActiveSource((curr) => {
      if (curr?.source_id === targetId) {
        setEvents([]); // Reset events state when active source removed
        setDetectionResults(null);
        setAnalysisSummary(null);
        setAnalysisError('');
        return null;
      }
      return curr;
    });
  }, []);

  // Handler called when YOLO video analysis finishes (or cached data loads)
  const handleAnalysisComplete = useCallback((data, source) => {
    if (!data || !data.frame_results) return;

    let persons = 0;
    let vehicles = 0;
    let totalDets = data.total_detections || 0;
    const generatedEvents = [];
    const generatedAlerts = [];
    // Phase 6: deduplicate alerts per track_id so the same tracked object
    // doesn't flood the panel (e.g. the same person #1 in 60 frames → 1 alert)
    const seenTrackIds = new Set();

    data.frame_results.forEach((frame) => {
      if (!frame.detections || frame.detections.length === 0) return;

      const mins = Math.floor(frame.timestamp_sec / 60).toString().padStart(2, '0');
      const secs = (frame.timestamp_sec % 60).toFixed(1).padStart(4, '0');
      const timeStr = `${mins}:${secs}s`;

      let hasPerson = false;
      let hasVehicle = false;
      let hasPriority = false;

      const objSummary = frame.detections
        .slice(0, 3)
        .map((d) => {
          const cName = d.class_name.toLowerCase();
          const trkId = d.track_id;
          const knownInfo = trkId != null ? (recognizedTracksRef.current.get(`${source?.source_id}_${trkId}`) || recognizedTracksRef.current.get(`${trkId}`)) : null;

          if (cName === 'person') {
            persons += 1;
            hasPerson = true;
            if (knownInfo?.isKnown) {
              return `${knownInfo.name} #${trkId} (Authorized: ${knownInfo.confPct || Math.round(d.confidence * 100)}%)`;
            }
          } else if (VEHICLE_CLASSES.has(cName)) {
            vehicles += 1;
            hasVehicle = true;
          }
          if (d.is_priority) hasPriority = true;
          const trackPart = trkId != null ? ` #${trkId}` : '';
          return `${d.class_name}${trackPart} (${Math.round(d.confidence * 100)}%)`;
        })
        .join(', ');

      const personDets = frame.detections.filter(d => d.class_name.toLowerCase() === 'person');
      const allPersonsKnown = personDets.length > 0 && personDets.every(d => {
        const knownInfo = d.track_id != null ? (recognizedTracksRef.current.get(`${source?.source_id}_${d.track_id}`) || recognizedTracksRef.current.get(`${d.track_id}`)) : null;
        return knownInfo?.isKnown;
      });

      const risk = allPersonsKnown
        ? 'SAFE'
        : hasPriority
        ? 'HIGH'
        : hasPerson
        ? 'MEDIUM'
        : hasVehicle
        ? 'MEDIUM'
        : 'LOW';

      const eventType = allPersonsKnown
        ? 'Authorized Personnel Detected'
        : hasPriority
        ? 'Priority Perimeter Breach'
        : hasPerson
        ? 'Person Movement Detected'
        : hasVehicle
        ? 'Vehicle Incursion'
        : 'Object Detection';

      generatedEvents.push({
        timestamp: timeStr,
        camera: source?.original_name || source?.name || 'Feed 1',
        type: eventType,
        object: objSummary,
        risk: risk,
        status: 'Logged',
        trackId: personDets[0]?.track_id ?? null,
        sourceId: source?.source_id ?? null,
      });

      // Find top priority or highest confidence detection for this frame
      const priorityDets = frame.detections.filter((d) => d.is_priority || d.class_name.toLowerCase() === 'person');
      const topDet = (priorityDets.length > 0 ? priorityDets : frame.detections).reduce((best, curr) => 
        (curr.confidence > (best?.confidence || 0) ? curr : best), null);

      if (topDet && (hasPriority || hasPerson || hasVehicle) && generatedAlerts.length < 50) {
        const topClass = topDet.class_name.toUpperCase();
        const topConf = Math.round(topDet.confidence * 100);
        const trackId = topDet.track_id ?? null;
        const knownInfo = trackId != null ? (recognizedTracksRef.current.get(`${source?.source_id}_${trackId}`) || recognizedTracksRef.current.get(`${trackId}`)) : null;

        // Phase 6: Deduplicate by track_id — only one alert card per tracked object
        if (trackId != null) {
          if (seenTrackIds.has(trackId)) return; // skip this frame's alert
          seenTrackIds.add(trackId);
        }

        const isKnownTopPerson = topClass === 'PERSON' && knownInfo?.isKnown;
        const trackLabel = isKnownTopPerson
          ? `Authorized Personnel — ${knownInfo.name} #${trackId}`
          : trackId != null
          ? `${topClass} #${trackId}`
          : topClass;
        
        generatedAlerts.push({
          id: `det-${frame.frame_index}-${frame.timestamp_sec}`,
          type: isKnownTopPerson ? trackLabel : `Priority Object Detected — ${trackLabel}`,
          objectClass: isKnownTopPerson ? 'AUTHORIZED' : topClass,
          trackId: trackId,          // Phase 6: persisted track ID
          sourceId: source?.source_id ?? null,  // Evidence lookup key
          confidence: isKnownTopPerson ? (knownInfo.confPct || topConf) : topConf,
          severity: isKnownTopPerson ? 'Safe' : (topDet.is_priority ? 'High' : 'Medium'),
          time: timeStr,
          camera: source?.original_name || 'Surveillance Feed',
          description: isKnownTopPerson
            ? `${knownInfo.name} (${knownInfo.confPct || topConf}% match) verified. Authorized personnel on site.`
            : `${trackLabel} detected (${topConf}% confidence) at ${timeStr}`,
        });
      }
    });

    const suspiciousAlerts = [];
    const suspiciousEvents = [];

    if (Array.isArray(data.suspicious_events)) {
      data.suspicious_events.forEach((sEv) => {
        const actUpper = String(sEv.activity || 'SUSPICIOUS').toUpperCase();
        const confPct = Math.round((sEv.confidence || 0.8) * (sEv.confidence <= 1 ? 100 : 1));
        const trkId = sEv.track_id;
        const trackLabel = trkId != null ? `PERSON #${trkId}` : 'PERSON';
        const tsSec = typeof sEv.timestamp_sec === 'number' ? sEv.timestamp_sec : 0;
        const mins = Math.floor(tsSec / 60).toString().padStart(2, '0');
        const secs = (tsSec % 60).toFixed(1).padStart(4, '0');
        const timeStr = `${mins}:${secs}s`;
        const cameraLabel = source?.original_name || source?.name || 'Surveillance Feed';

        const desc = sEv.object_track_id != null
          ? `Suspicious activity (${actUpper}) confirmed for ${trackLabel} throwing OBJECT #${sEv.object_track_id} at ${tsSec.toFixed(1)}s.`
          : `Suspicious activity (${actUpper}) confirmed for ${trackLabel} at ${tsSec.toFixed(1)}s.`;

        suspiciousAlerts.push({
          id: `susp-${actUpper}-${trkId}-${tsSec.toFixed(2)}`,
          type: `SUSPICIOUS ACTIVITY — ${actUpper}`,
          event_type: 'SUSPICIOUS_ACTIVITY',
          activity_subtype: actUpper,
          objectClass: 'PERSON',
          trackId: trkId,
          sourceId: source?.source_id ?? null,
          confidence: confPct,
          severity: actUpper === 'THROWING' || actUpper === 'CRAWLING' ? 'Critical' : 'High',
          time: timeStr,
          camera: cameraLabel,
          description: desc,
          isIntrusion: false,
          object_track_id: sEv.object_track_id ?? null,
          metadata: sEv.metadata || {},
        });

        const subFormatted = actUpper === 'RUNNING' ? 'Running' : actUpper === 'CRAWLING' ? 'Crawling' : actUpper === 'THROWING' ? 'Throwing' : actUpper;
        const objDesc = sEv.object_track_id != null
          ? `PERSON #${trkId} (Throwing Obj #${sEv.object_track_id}, ${confPct}%)`
          : `PERSON #${trkId} (${subFormatted}, ${confPct}%)`;

        suspiciousEvents.push({
          timestamp: timeStr,
          camera: cameraLabel,
          type: `SUSPICIOUS ACTIVITY — ${actUpper}`,
          object: objDesc,
          risk: 'HIGH',
          status: 'Logged',
          trackId: trkId,
          sourceId: source?.source_id ?? null,
        });
      });
    }

    setMetrics({
      personCount: persons,
      vehicleCount: vehicles,
      totalDetections: totalDets,
      framesProcessed: data.frames_processed || 0,
    });

    setEvents((prev) => {
      const srcId = source?.source_id;
      const wsEvents = prev.filter(e => 
        (!srcId || e.sourceId === srcId) && (
          e.type === 'RESTRICTED ZONE INTRUSION' || 
          e.type === 'LINE CROSSING' ||
          e.type === 'LOITERING DETECTED' ||
          e.type === 'Authorized Personnel Detected' ||
          (e.type && e.type.startsWith('SUSPICIOUS ACTIVITY'))
        )
      );
      const existingEvKeys = new Set(wsEvents.map(e => `${e.type}_${e.trackId}`));
      const uniqueSuspEvents = suspiciousEvents.filter(e => !existingEvKeys.has(`${e.type}_${e.trackId}`));
      return [...uniqueSuspEvents, ...wsEvents, ...generatedEvents].slice(0, 100);
    });
    setAlerts((prev) => {
      // Keep real-time websocket alerts + new detection alerts
      const wsAlerts = prev.filter((a) => a.id?.startsWith('ws-') || a.id?.startsWith('face-'));
      const existingAlertKeys = new Set(wsAlerts.map(a => `${a.event_type}_${a.activity_subtype}_${a.trackId}`));
      const uniqueSuspAlerts = suspiciousAlerts.filter(a => !existingAlertKeys.has(`${a.event_type}_${a.activity_subtype}_${a.trackId}`));
      return [...uniqueSuspAlerts, ...wsAlerts, ...generatedAlerts].slice(0, 50);
    });
  }, []);

  // Trigger analysis function callable from both VideoUploadPanel and CameraGrid
  const handleTriggerAnalysis = useCallback(async (sourceToAnalyze = activeSource) => {
    const src = sourceToAnalyze || activeSource;
    if (!src?.source_id) return;
    if (isAnalyzingRef.current) {
      console.warn('[ANALYZE] Analysis already running, ignoring duplicate trigger.');
      return;
    }

    isAnalyzingRef.current = true;
    setIsAnalyzing(true);
    setAnalysisError('');
    setAnalysisSummary(null);
    setAnalysisElapsed(0);

    const startTs = Date.now();
    const ticker = setInterval(() => {
      setAnalysisElapsed(Math.floor((Date.now() - startTs) / 1000));
    }, 1000);

    try {
      console.log(`[RTSP_ANALYZE_TRACE][REQUEST_SENT] analyzeVideo called for ${src.source_id} (${src.source_type})`);
      const data = await analyzeVideo(src.source_id);
      console.log(`[RTSP_ANALYZE_TRACE][BACKEND_RECEIVED] Response for ${src.source_id}:`, data);
      if (src.source_type !== 'RTSP') {
        setDetectionResults(data.frame_results);
        setAnalysisSummary({
          frames: data.frames_processed,
          detections: data.total_detections,
          classes: (data.unique_classes || []).join(', ') || 'none',
        });
        handleAnalysisComplete(data, src);
      }
    } catch (err) {
      console.error('[ANALYZE] Error:', err.message, err);
      setAnalysisError(err.message || 'Analysis failed. Please try again.');
    } finally {
      clearInterval(ticker);
      isAnalyzingRef.current = false;
      setIsAnalyzing(false);
    }
  }, [activeSource, handleAnalysisComplete]);

  // Check for cached detection results whenever activeSource changes
  useEffect(() => {
    if (activeSource?.source_id) {
      getDetectionResults(activeSource.source_id)
        .then((data) => {
          if (data && data.frame_results) {
            setDetectionResults(data.frame_results);
            setAnalysisSummary({
              frames: data.frames_processed,
              detections: data.total_detections,
              classes: (data.unique_classes || []).join(', ') || 'none',
            });
            handleAnalysisComplete(data, activeSource);
          }
        })
        .catch(() => {});
    }
  }, [activeSource?.source_id, handleAnalysisComplete]);

  // Handler called by the WebSocket hook for every incoming message
  const handleWsMessage = useCallback((parsed) => {
    // ── RTSP live frame updates ───────────────────────────────────────────────
    // Detection state (detectionResults, analysisSummary) for RTSP sectors is
    // now managed per-card inside LiveVideoCard. App.jsx only needs to generate
    // Event Log entries from these frames.
    if (parsed?.type === 'frame_update') {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('sentinel-ws-frame', { detail: parsed }));
      }
      const frame = parsed.data;
      if (frame?.detections?.length > 0) {
        const timeStr = new Date().toLocaleTimeString('en-US', { hour12: false });
        let hasPerson = false, hasVehicle = false, hasPriority = false;
        const objSummary = frame.detections
          .slice(0, 3)
          .map((d) => {
            const cName = d.class_name.toLowerCase();
            const trkId = d.track_id;
            const knownInfo = trkId != null ? (recognizedTracksRef.current.get(`${parsed.source_id}_${trkId}`) || recognizedTracksRef.current.get(`${trkId}`)) : null;
            if (cName === 'person') {
              hasPerson = true;
              if (knownInfo?.isKnown) {
                return `${knownInfo.name} #${trkId} (Authorized: ${knownInfo.confPct || Math.round(d.confidence * 100)}%)`;
              }
            } else if (VEHICLE_CLASSES.has(cName)) {
              hasVehicle = true;
            }
            if (d.is_priority) hasPriority = true;
            const trackPart = trkId != null ? ` #${trkId}` : '';
            return `${d.class_name}${trackPart} (${Math.round(d.confidence * 100)}%)`;
          })
          .join(', ');

        const personDets = frame.detections.filter(d => d.class_name.toLowerCase() === 'person');
        const allPersonsKnown = personDets.length > 0 && personDets.every(d => {
          const knownInfo = d.track_id != null ? (recognizedTracksRef.current.get(`${parsed.source_id}_${d.track_id}`) || recognizedTracksRef.current.get(`${d.track_id}`)) : null;
          return knownInfo?.isKnown;
        });

        const risk = allPersonsKnown ? 'SAFE' : hasPriority ? 'HIGH' : hasPerson ? 'MEDIUM' : hasVehicle ? 'MEDIUM' : 'LOW';
        const eventType = allPersonsKnown ? 'Authorized Personnel Detected'
          : hasPriority ? 'Priority Perimeter Breach'
          : hasPerson ? 'Person Movement Detected'
          : hasVehicle ? 'Vehicle Incursion'
          : 'Object Detection';
        const cameraLabel = parsed.source_id || 'Live Feed';
        setEvents(prev => [{
          timestamp: timeStr,
          camera: cameraLabel,
          type: eventType,
          object: objSummary,
          risk: risk,
          status: 'Logged',
          trackId: personDets[0]?.track_id ?? null,
        }, ...prev].slice(0, 100));
      }
      return;
    }

    if (parsed?.type === 'face_recognition') {
      const data = parsed.data || parsed;
      const srcId = parsed.source_id || data.source_id || 'default';
      const trkId = data.track_id ?? parsed.track_id;
      const isKnown = data.status === 'KNOWN_PERSON';
      const name = isKnown && data.name && data.name !== 'Unknown Person' ? data.name : 'Unknown Person';
      const rawConf = data.confidence != null ? data.confidence : 0;
      const confPct = Math.round(rawConf * (rawConf <= 1 ? 100 : 1));
      const trackPart = trkId != null ? ` #${trkId}` : '';
      const cameraLabel = parsed.source_id || data.source_id || activeSource?.original_name || 'Live Feed';
      const timeStr = data.time || new Date().toLocaleTimeString('en-US', { hour12: false });

      if (trkId != null) {
        recognizedTracksRef.current.set(`${srcId}_${trkId}`, { isKnown, name, confPct, timeStr });
        recognizedTracksRef.current.set(`${trkId}`, { isKnown, name, confPct, timeStr });
      }

      if (isKnown) {
        // 1. Audit Log: Log as Safe / Authorized Personnel & update ALL matching existing events for this track
        setEvents(prev => {
          const updated = prev.map(ev => {
            // NEVER downgrade genuine intrusion/virtual fence alerts
            if (ev.type?.includes('INTRUSION') || ev.type?.includes('CROSSING') || (ev.risk === 'CRITICAL' && (ev.type?.includes('ZONE') || ev.type?.includes('LINE')))) {
              return ev;
            }

            // Case-insensitive match for track_id or explicit track match
            const trackMatch = trkId != null && (
              ev.trackId === trkId ||
              (typeof ev.object === 'string' && (
                ev.object.includes(`#${trkId}`) ||
                ev.object.toLowerCase().includes(`person #${trkId}`) ||
                ev.object.toLowerCase().includes(`person#${trkId}`)
              ))
            );

            if (trackMatch) {
              return {
                ...ev,
                type: 'Authorized Personnel Detected',
                object: `${name} #${trkId} (Authorized: ${confPct}%)`,
                risk: 'SAFE',
              };
            }
            return ev;
          });

          return [{
            timestamp: timeStr,
            camera: cameraLabel,
            type: 'Authorized Personnel Detected',
            object: `${name}${trackPart} (Authorized: ${confPct}%)`,
            risk: 'SAFE',
            status: 'Logged',
            trackId: trkId,
            sourceId: srcId,
          }, ...updated].slice(0, 100);
        });

        // 2. Threat Alerts Panel: Update existing alert for this track to Safe (do NOT downgrade genuine intrusion alerts)
        setAlerts(prev => {
          let matched = false;
          const updatedAlerts = prev.map(al => {
            if (al.isIntrusion || al.event_type === 'SUSPICIOUS_ACTIVITY') return al; // Preserve genuine security fence/zone intrusions & suspicious activity
            if (trkId != null && al.trackId === trkId) {
              matched = true;
              return {
                ...al,
                type: `Authorized Personnel — ${name}${trackPart}`,
                objectClass: 'AUTHORIZED',
                severity: 'Safe',
                confidence: confPct,
                description: `${name} (${confPct}% match) verified. Authorized personnel on site.`,
              };
            }
            return al;
          });

          if (!matched) {
            return [{
              id: `face-${trkId ?? Date.now()}`,
              type: `Authorized Personnel — ${name}${trackPart}`,
              objectClass: 'AUTHORIZED',
              trackId: trkId,
              confidence: confPct,
              severity: 'Safe',
              time: timeStr,
              camera: cameraLabel,
              description: `${name} (${confPct}% match) verified. Authorized personnel on site.`,
            }, ...updatedAlerts].slice(0, 50);
          }

          return updatedAlerts;
        });
      } else {
        // Unrecognized face -> High risk
        setEvents(prev => [{
          timestamp: timeStr,
          camera: cameraLabel,
          type: 'Unrecognized Face Detected',
          object: `Unknown Person${trackPart} (Face: ${confPct}%)`,
          risk: 'HIGH',
          status: 'Logged',
          trackId: trkId,
          sourceId: srcId,
        }, ...prev].slice(0, 100));

        setAlerts(prev => {
          let matched = false;
          const updatedAlerts = prev.map(al => {
            if (al.isIntrusion || al.event_type === 'SUSPICIOUS_ACTIVITY') return al;
            if (trkId != null && al.trackId === trkId) {
              matched = true;
              return {
                ...al,
                type: `Unrecognized Person — #${trkId}`,
                objectClass: 'UNKNOWN',
                severity: 'High',
                confidence: confPct,
                description: `Unrecognized face detected (${confPct}% conf) at ${timeStr}.`,
              };
            }
            return al;
          });
          return updatedAlerts;
        });
      }
      return;
    }

    if (parsed?.type === 'anpr_recognition') {
      console.log('[ANPR_TRACE][FRONTEND_RECEIVED]', parsed);
      const data = parsed.data || parsed;
      const srcId = parsed.source_id || data.source_id || 'default';
      const trkId = data.track_id ?? parsed.track_id;
      const plateNum = data.plate_number;
      const vClass = data.vehicle_class || 'CAR';
      const confPct = data.confidence_pct ?? Math.round((data.ocr_confidence || 0.9) * 100);
      const isWatchlist = !!data.is_watchlist_match;
      const cameraLabel = parsed.source_id || data.source_id || activeSource?.original_name || 'Live Feed';
      const timeStr = data.time || new Date().toLocaleTimeString('en-US', { hour12: false });
      const trackPart = trkId != null ? ` #${trkId}` : '';

      // Log in Real-Time Event Audit Log (Normal recognized plates do NOT trigger threat alerts or alarms)
      setEvents(prev => [{
        timestamp: timeStr,
        camera: cameraLabel,
        type: 'Vehicle Plate Recognized',
        object: `${vClass}${trackPart} [${plateNum}] (${confPct}%)`,
        risk: isWatchlist ? 'HIGH' : 'LOW',
        status: 'Logged',
        trackId: trkId,
        sourceId: srcId,
      }, ...prev].slice(0, 100));
      return;
    }

    if (parsed?.type !== 'alert') return;

    const data = parsed.data ?? {};
    const wsObjectClass = data.object_class ? data.object_class.toUpperCase() : null;
    const wsConfidence = data.confidence != null
      ? Math.round(data.confidence * (data.confidence <= 1 ? 100 : 1))
      : null;
    const wsTrackId = data.track_id ?? null;
    const wsTrackLabel = data.track_label ?? wsObjectClass;

    const baseType = data.alert_type ?? 'Live Perimeter Alert';

    const newAlert = {
      id:               `ws-${Date.now()}-${Math.random()}`,
      type:             baseType,
      objectClass:      wsObjectClass,
      trackId:          wsTrackId,
      sourceId:         parsed.source_id ?? data.source_id ?? null,  // Evidence lookup key
      confidence:       wsConfidence,
      severity:         data.severity     ?? 'Critical',
      time:             data.time         ?? new Date().toLocaleTimeString('en-US', { hour12: false }),
      camera:           data.camera       ?? (activeSource?.original_name || 'Live Feed'),
      description:      data.description  ?? 'A new detection event was received via WebSocket.',
      isIntrusion:      !!data.is_intrusion,
      event_type:       data.event_type   ?? null,
      activity_subtype: data.activity_subtype ?? null,
      object_track_id:  data.object_track_id  ?? null,
    };

    setAlerts((prev) => [newAlert, ...prev].slice(0, 50));

    // Play tactical alarm chime when LOITERING DETECTED, perimeter intrusion, or SUSPICIOUS ACTIVITY is received
    if (data.event_type === 'loitering') {
      playAlarmSound('loitering');
    } else if (data.event_type === 'zone_intrusion' || data.event_type === 'line_crossing' || data.event_type === 'SUSPICIOUS_ACTIVITY') {
      playAlarmSound('default');
    }


    // Phase 7 + Phase 9: Add high-priority WebSocket alerts to Restricted Area Intrusions & Event Log
    // STRICT FILTER: Only genuine virtual-fence and loitering events are classified as intrusions/restricted events.
    const isIntrusionAlert = data.event_type === 'zone_intrusion' || data.event_type === 'line_crossing' || data.event_type === 'loitering';

    if (isIntrusionAlert) {
      const isLine = data.event_type === 'line_crossing';
      const isLoiter = data.event_type === 'loitering';
      const intrusionType = isLine ? 'LINE CROSSING' : isLoiter ? 'LOITERING DETECTED' : 'ZONE ENTRY';

      const newIntrusion = {
        id: `int-${newAlert.id}`,
        objectClass: wsObjectClass || 'UNKNOWN',
        trackId: wsTrackId,
        confidence: wsConfidence,
        camera: newAlert.camera,
        time: newAlert.time,
        type: intrusionType,
        status: isLoiter ? 'LOITERING' : 'ACTIVE',
        duration_sec: data.duration_sec,
        threshold_sec: data.threshold_sec,
        description: data.description,
        sourceId: newAlert.sourceId,
      };

      setIntrusions((prev) => [newIntrusion, ...prev].slice(0, 50));

      setEvents((prev) => [{
        timestamp: newAlert.time,
        camera: newAlert.camera,
        type: baseType,
        object: `${newAlert.objectClass} ${newAlert.trackId ? '#' + newAlert.trackId : ''} (${newAlert.confidence}%)`,
        risk: newAlert.severity.toUpperCase(),
        status: 'Logged',
      }, ...prev].slice(0, 100));
    } else if (data.event_type === 'SUSPICIOUS_ACTIVITY') {
      // Step 6C: Suspicious Activity Real-Time Event Audit Log entry
      const sub = data.activity_subtype || 'SUSPICIOUS';
      const subFormatted = sub === 'RUNNING' ? 'Running' : sub === 'CRAWLING' ? 'Crawling' : sub === 'THROWING' ? 'Throwing' : sub;
      const trackStr = wsTrackId != null ? `#${wsTrackId}` : 'N/A';
      const objDesc = data.object_track_id != null
        ? `${newAlert.objectClass || 'PERSON'} ${trackStr} (Throwing Obj #${data.object_track_id}, ${newAlert.confidence ?? 0}%)`
        : `${newAlert.objectClass || 'PERSON'} ${trackStr} (${subFormatted}, ${newAlert.confidence ?? 0}%)`;

      setEvents((prev) => [{
        timestamp: newAlert.time,
        camera:    newAlert.camera,
        type:      baseType,
        object:    objDesc,
        risk:      newAlert.severity.toUpperCase(),
        status:    'Logged',
        trackId:   wsTrackId,
        sourceId:  newAlert.sourceId,
      }, ...prev].slice(0, 100));
    }
  }, [activeSource?.original_name]);

  // ── WebSocket connection (only when authenticated) ─────────────────────────
  const { isConnected } = useWebSocket({
    url:       WS_URL,
    onMessage: handleWsMessage,
    enabled:   isAuthenticated,
  });

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.__injectSentinelWsMessage = handleWsMessage;
    }
    return () => {
      if (typeof window !== 'undefined') {
        delete window.__injectSentinelWsMessage;
      }
    };
  }, [handleWsMessage]);

  // ── Real Dynamic Stats Cards ──────────────────────────────────────────────
  const stats = [
    {
      title: "Active Feeds",
      value: activeSource ? "1/1 Online" : "0/0 Feeds",
      icon: Camera,
      trend: activeSource ? "Connected" : "Idle",
      trendLabel: activeSource ? (activeSource.original_name || "Active") : "No Stream",
      colorClass: activeSource ? "bg-blue-500" : "bg-slate-700",
    },
    {
      title: "Persons Detected",
      value: metrics.personCount.toLocaleString(),
      icon: Users,
      trend: metrics.framesProcessed > 0 ? `${metrics.framesProcessed} Frames` : "Ready",
      trendLabel: "from YOLO AI",
      colorClass: "bg-emerald-500",
    },
    {
      title: "Vehicles Detected",
      value: metrics.vehicleCount.toLocaleString(),
      icon: Car,
      trend: metrics.vehicleCount > 0 ? "Tracked" : "0",
      trendLabel: "Cars & Transport",
      colorClass: "bg-purple-500",
    },
    {
      title: "Total AI Detections",
      value: metrics.totalDetections.toLocaleString(),
      icon: AlertTriangle,
      trend: metrics.totalDetections > 0 ? `${events.length} Events` : "0",
      trendLabel: "Total detections",
      colorClass: "bg-red-500",
    },
  ];

  const placeholderCameras = [
    { name: "Sector 4 - Alpha",   location: "North Checkpoint",   isOnline: true,  detectionStatus: "ONLINE",          hasAlert: false },
    { name: "Sector 4 - Bravo",   location: "Perimeter Fence 1",  isOnline: true,  detectionStatus: "CLEAR",           hasAlert: false },
    { name: "Sector 7 - Charlie", location: "Main Gate Entry",    isOnline: true,  detectionStatus: "STANDBY",         hasAlert: false },
  ];


  // ── Auth Loading Splash ───────────────────────────────────────────────────
  if (authLoading) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#010b0f', color: '#00d4b0', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85rem',
        letterSpacing: '0.1em'
      }}>
        SENTINEL AI · INITIALIZING...
      </div>
    );
  }

  // ── Public Pages (unauthenticated) ────────────────────────────────────────
  if (!isAuthenticated) {
    if (publicPage === 'login') {
      return (
        <LoginPage
          onSuccess={() => setPublicPage('landing')}
          onRegister={() => setPublicPage('register')}
          onBack={() => setPublicPage('landing')}
        />
      );
    }
    if (publicPage === 'register') {
      return (
        <RegisterPage
          onVerify={(pendingId, email) => {
            setOtpPendingId(pendingId);
            setOtpPendingEmail(email);
            setPublicPage('verify-otp');
          }}
          onLogin={() => setPublicPage('login')}
          onBack={() => setPublicPage('landing')}
        />
      );
    }
    if (publicPage === 'verify-otp') {
      return (
        <VerifyOTPPage
          pendingId={otpPendingId}
          email={otpPendingEmail}
          onSuccess={() => {
            /* login() is called inside VerifyOTPPage via useAuth;
               isAuthenticated flips true automatically — no extra action needed */
          }}
          onBack={() => setPublicPage('register')}
        />
      );
    }
    // Default: landing
    return (
      <LandingPage
        onLogin={() => setPublicPage('login')}
        onRegister={() => setPublicPage('register')}
      />
    );
  }

  // ── Authenticated Dashboard ───────────────────────────────────────────────
  return (
    <Layout activeTab={activeTab} onSelectTab={setActiveTab} user={user} onLogout={logout}>
      {activeTab === 'personnel-registry' ? (
        <PersonnelRegistry />
      ) : activeTab === 'video-feeds' ? (
        <VideoFeedsView
          activeSource={activeSource}
          activeSources={activeSources}
          detectionResults={detectionResults}
          isAnalyzing={isAnalyzing}
          analysisElapsed={analysisElapsed}
          analysisSummary={analysisSummary}
          analysisError={analysisError}
          onAnalyze={handleTriggerAnalysis}
          onRemoveSource={handleRemoveSource}
          onSourceAdded={handleSourceReady}
          onAnalysisComplete={handleAnalysisComplete}
          alerts={alerts}
          intrusions={intrusions}
          isConnected={isConnected}
        />
      ) : activeTab === 'threat-alerts' ? (
        <ThreatAlertsView
          alerts={alerts}
          isConnected={isConnected}
          onClearAlerts={() => setAlerts([])}
        />
      ) : activeTab === 'event-logbook' ? (
        <EventLogbookView
          events={events}
          activeSource={activeSource}
        />
      ) : activeTab === 'camera-array' ? (
        <CameraArrayView
          activeSources={activeSources}
          alerts={alerts}
          intrusions={intrusions}
          isConnected={isConnected}
          onSourceAdded={handleSourceReady}
          onRemoveSource={handleRemoveSource}
        />
      ) : activeTab === 'model-config' ? (
        <AIModelConfigView />
      ) : (
        <div className="flex flex-col xl:flex-row gap-5 items-start">
          {/* Main Content Area */}
          <div className="flex-1 flex flex-col gap-5 min-w-0">

            {/* ── Mission Status Banner ─────────────────────────── */}
            <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 rounded-xl bg-[#021822]/80 border border-[#00d4b0]/14 backdrop-blur-sm">
              <div className="flex items-center gap-2 text-[10px] font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#10b981]" />
                <span className="text-emerald-400 font-bold tracking-wider">MISSION: ACTIVE</span>
              </div>
              <div className="w-px h-4 bg-[#00d4b0]/15 hidden sm:block" />
              <span className="text-[9px] font-mono text-[#4a8a80] tracking-widest">SECTOR 04 — NORTH PERIMETER</span>
              <div className="w-px h-4 bg-[#00d4b0]/15 hidden md:block" />
              <span className="text-[9px] font-mono text-[#3a7068] tracking-wider hidden md:block">AI MODULES: YOLOv8 · BYTETRACK · FRS · ANPR</span>
              <div className="ml-auto flex items-center gap-2">
                {isConnected ? (
                  <span className="flex items-center gap-1 text-[9px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                    <span className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" />
                    WS LIVE
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[9px] font-mono text-slate-500 bg-slate-800/60 border border-slate-700/40 px-2 py-0.5 rounded">
                    WS OFFLINE
                  </span>
                )}
              </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {stats.map((stat, idx) => (
                <StatCard key={idx} {...stat} />
              ))}
            </div>

            {/* Camera Grid Section */}
            <div className="flex flex-col gap-4">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2.5">
                  <div className="w-1 h-5 bg-gradient-to-b from-[#00d4b0] to-[#06b6d4] rounded-full shadow-[0_0_8px_rgba(0,212,176,0.5)]" />
                  <h3 className="text-sm font-bold text-white font-mono tracking-wider">LIVE SURVEILLANCE FEEDS</h3>
                  <span className="flex items-center gap-1 text-[9px] font-mono font-bold text-red-400 bg-red-500/10 border border-red-500/25 px-1.5 py-0.5 rounded">
                    <span className="w-1 h-1 rounded-full bg-red-400 animate-threat-blink" />
                    LIVE
                  </span>
                </div>
                <div className="flex gap-1.5">
                  <button className="text-[10px] font-mono px-2.5 py-1 bg-[#021822]/80 text-[#6aa89f] rounded-lg border border-[#00d4b0]/18 hover:border-[#00d4b0]/35 hover:text-cyan-300 transition-all">GRID: 2×2</button>
                  <button className="text-[10px] font-mono px-2.5 py-1 bg-[#021822]/80 text-[#6aa89f] rounded-lg border border-[#00d4b0]/18 hover:border-[#00d4b0]/35 hover:text-cyan-300 transition-all">FILTER: ALERTS</button>
                </div>
              </div>

              {/* Video Ingestion & Upload with prominent Analyze button */}
              <VideoUploadPanel
                activeSource={activeSource}
                onSourceReady={(source) => {
                  handleSourceReady(source);
                  // Force activeSource to update for the ingestion panel even if it's RTSP
                  setActiveSource(source);
                }}
                onRemove={handleRemoveSource}
                onAnalyze={handleTriggerAnalysis}
                isAnalyzing={isAnalyzing}
                hasResults={!!(detectionResults && detectionResults.length > 0)}
                elapsedSec={analysisElapsed}
              />

              <CameraGrid
                cameras={placeholderCameras}
                activeSources={activeSources}
                uploadedSource={activeSource}
                onAnalysisComplete={handleAnalysisComplete}
                detectionResults={detectionResults}
                isAnalyzing={isAnalyzing}
                analysisElapsed={analysisElapsed}
                analysisSummary={analysisSummary}
                analysisError={analysisError}
                onAnalyze={handleTriggerAnalysis}
                onRemoveSource={handleRemoveSource}
                onSourceAdded={handleSourceReady}
              />
            </div>

            {/* Recent Real Events Table */}
            <div className="pt-2">
              <RecentEventsTable events={events} activeSource={activeSource} />
            </div>
          </div>

          {/* Right Sidebar - Real-Time Alerts & Intrusions */}
          <div className="w-full xl:w-80 shrink-0 flex flex-col gap-6 sticky top-6 h-[calc(100vh-3rem)]">
            <div className="flex-1 min-h-0">
              <AlertPanel alerts={alerts} isConnected={isConnected} />
            </div>
            <div className="flex-1 min-h-0">
              <IntrusionPanel intrusions={intrusions} />
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}


export default App;
