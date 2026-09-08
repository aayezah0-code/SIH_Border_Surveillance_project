import React, { useState, useEffect, useCallback } from 'react';
import { 
  Camera, 
  Grid, 
  Layers, 
  ShieldAlert, 
  Crosshair, 
  Activity, 
  Radio, 
  Cpu, 
  RefreshCw, 
  Wifi, 
  WifiOff 
} from 'lucide-react';
import CameraArrayCard from './CameraArrayCard';
import { EvidenceModal } from '../dashboard/AlertPanel';
import { addRtspCamera, deleteSource, getSources } from '../../services/videoApi';

export const CameraArrayView = ({
  activeSources = [],
  alerts = [],
  intrusions = [],
  isConnected = false,
  onSourceAdded = () => {},
  onRemoveSource = () => {},
}) => {
  // 4 Slot Array State: holds source objects or null for empty slots
  const [slotSources, setSlotSources] = useState([null, null, null, null]);
  const [evidenceAlert, setEvidenceAlert] = useState(null);

  // Sync active RTSP streams into slots
  useEffect(() => {
    const rtspSources = (activeSources || []).filter(s => s.source_type === 'RTSP');
    setSlotSources((prev) => {
      const next = [null, null, null, null];
      rtspSources.slice(0, 4).forEach((src, idx) => {
        next[idx] = src;
      });
      return next;
    });
  }, [activeSources]);

  // Connect new RTSP camera to a specific slot
  const handleConnectCamera = async (config, slotIndex) => {
    const newSource = await addRtspCamera(config);
    if (onSourceAdded) {
      onSourceAdded(newSource);
    }
    setSlotSources((prev) => {
      const next = [...prev];
      next[slotIndex] = newSource;
      return next;
    });
    return newSource;
  };

  // Disconnect camera from a specific slot
  const handleDisconnectCamera = async (sourceId) => {
    if (!sourceId) return;
    try {
      await deleteSource(sourceId);
    } catch {
      // Ignored if already removed
    }
    if (onRemoveSource) {
      onRemoveSource(sourceId);
    }
    setSlotSources((prev) => prev.map(s => s?.source_id === sourceId ? null : s));
  };

  // Calculate active feeds
  const activeCount = slotSources.filter(Boolean).length;
  
  // Total alerts & intrusions across all 4 cameras
  const totalQuadAlerts = alerts.filter(a => 
    slotSources.some(s => s && s.source_id === a.sourceId)
  ).length;

  const totalQuadIntrusions = intrusions.filter(i => 
    slotSources.some(s => s && s.source_id === i.sourceId)
  ).length;

  return (
    <div className="flex flex-col gap-6 w-full">
      {/* Evidence Modal if an evidence snapshot is selected */}
      {evidenceAlert && (
        <EvidenceModal
          alert={evidenceAlert}
          onClose={() => setEvidenceAlert(null)}
        />
      )}

      {/* ── Page Header ── */}
      <div className="bg-[#021822]/90 backdrop-blur-md border border-[#00d4b0]/20 rounded-xl p-5 shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className="p-1.5 rounded-lg bg-[#00d4b0]/10 border border-[#00d4b0]/30 text-[#00d4b0]">
                <Grid className="w-5 h-5" />
              </div>
              <h2 className="text-lg font-bold text-white font-mono tracking-wider">
                CAMERA ARRAY <span className="text-[#00d4b0]">— 4-SECTOR SURVEILLANCE</span>
              </h2>
            </div>
            <p className="text-xs text-slate-400 font-mono">
              Simultaneous 4-camera real-time surveillance, automated threat alerts & intrusion detection.
            </p>
          </div>

          {/* Telemetry Chips */}
          <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
            {/* Active Feeds Chip */}
            <div className="px-3 py-1.5 rounded-lg bg-[#010e15] border border-[#00d4b0]/20 flex items-center gap-2">
              <Camera className="w-4 h-4 text-cyan-400" />
              <span className="text-slate-400">FEEDS:</span>
              <span className="text-white font-bold">{activeCount}/4 ONLINE</span>
            </div>

            {/* Total Threat Alerts Chip */}
            <div className="px-3 py-1.5 rounded-lg bg-[#010e15] border border-[#00d4b0]/20 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-red-400" />
              <span className="text-slate-400">ALERTS:</span>
              <span className="text-red-400 font-bold">{totalQuadAlerts}</span>
            </div>

            {/* Total Intrusions Chip */}
            <div className="px-3 py-1.5 rounded-lg bg-[#010e15] border border-[#00d4b0]/20 flex items-center gap-2">
              <Crosshair className="w-4 h-4 text-amber-400" />
              <span className="text-slate-400">INTRUSIONS:</span>
              <span className="text-amber-400 font-bold">{totalQuadIntrusions}</span>
            </div>

            {/* WS Status */}
            <div className="px-3 py-1.5 rounded-lg bg-[#010e15] border border-[#00d4b0]/20 flex items-center gap-2">
              {isConnected ? (
                <span className="flex items-center gap-1.5 text-emerald-400 font-bold">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  WS ACTIVE
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-slate-500 font-bold">
                  <WifiOff className="w-3.5 h-3.5" />
                  OFFLINE
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── 2x2 Camera Array Grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[0, 1, 2, 3].map((slotIndex) => (
          <CameraArrayCard
            key={slotIndex}
            slotIndex={slotIndex}
            source={slotSources[slotIndex]}
            alerts={alerts}
            intrusions={intrusions}
            isConnected={isConnected}
            onConnect={handleConnectCamera}
            onDisconnect={handleDisconnectCamera}
            onOpenEvidence={(al) => setEvidenceAlert(al)}
          />
        ))}
      </div>
    </div>
  );
};

export default CameraArrayView;
