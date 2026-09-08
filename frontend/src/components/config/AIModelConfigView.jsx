import React, { useState, useEffect } from 'react';
import {
  Cpu,
  Sliders,
  Moon,
  UserCheck,
  CreditCard,
  Flame,
  Activity,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  Save,
  Shield,
  Layers,
  Sparkles,
  Info,
  Server,
  Eye,
  Check
} from 'lucide-react';
import { getAIConfig, updateAIConfig } from '../../services/videoApi';

const DEFAULT_FORM = {
  confidence: 0.40,
  iou: 0.45,
  low_light_mode: 'auto',
  frs_match_threshold: 0.65,
  anpr_consensus_threshold: 2,
  running_enabled: true,
  crawling_enabled: true,
  throwing_enabled: true,
};

export default function AIModelConfigView() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [serverConfig, setServerConfig] = useState(DEFAULT_FORM);
  const [systemStatus, setSystemStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  // Fetch current backend configuration
  const fetchConfig = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const data = await getAIConfig();
      const currentValues = {
        confidence: data.confidence ?? 0.40,
        iou: data.iou ?? 0.45,
        low_light_mode: data.low_light_mode || 'auto',
        frs_match_threshold: data.frs_match_threshold ?? 0.65,
        anpr_consensus_threshold: data.anpr_consensus_threshold ?? 2,
        running_enabled: data.running_enabled ?? true,
        crawling_enabled: data.crawling_enabled ?? true,
        throwing_enabled: data.throwing_enabled ?? true,
      };
      setForm(currentValues);
      setServerConfig(currentValues);
      setSystemStatus(data.system_status || null);
    } catch (err) {
      console.error('Failed to load AI config:', err);
      setErrorMessage('Could not load active AI configuration from server. Please check backend connection.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const isDirty = JSON.stringify(form) !== JSON.stringify(serverConfig);

  const handleApply = async () => {
    setSaving(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const res = await updateAIConfig({
        confidence: Number(form.confidence),
        iou: Number(form.iou),
        low_light_mode: form.low_light_mode,
        frs_match_threshold: Number(form.frs_match_threshold),
        anpr_consensus_threshold: Number(form.anpr_consensus_threshold),
        running_enabled: Boolean(form.running_enabled),
        crawling_enabled: Boolean(form.crawling_enabled),
        throwing_enabled: Boolean(form.throwing_enabled),
      });

      const updated = res.config || {};
      const appliedValues = {
        confidence: updated.confidence ?? form.confidence,
        iou: updated.iou ?? form.iou,
        low_light_mode: updated.low_light_mode || form.low_light_mode,
        frs_match_threshold: updated.frs_match_threshold ?? form.frs_match_threshold,
        anpr_consensus_threshold: updated.anpr_consensus_threshold ?? form.anpr_consensus_threshold,
        running_enabled: updated.running_enabled ?? form.running_enabled,
        crawling_enabled: updated.crawling_enabled ?? form.crawling_enabled,
        throwing_enabled: updated.throwing_enabled ?? form.throwing_enabled,
      };

      setForm(appliedValues);
      setServerConfig(appliedValues);
      if (updated.system_status) {
        setSystemStatus(updated.system_status);
      }
      setStatusMessage('AI Model Configuration successfully applied across all active sources.');
      setTimeout(() => setStatusMessage(null), 5000);
    } catch (err) {
      console.error('Failed to apply AI config:', err);
      setErrorMessage(err.message || 'Failed to update AI model configuration.');
    } finally {
      setSaving(false);
    }
  };

  const handleResetToDefaults = () => {
    setForm({ ...DEFAULT_FORM });
  };

  if (loading) {
    return (
      <div className="flex-1 p-8 flex items-center justify-center bg-gray-950 text-gray-400">
        <div className="flex flex-col items-center gap-3">
          <Cpu className="w-8 h-8 text-emerald-500 animate-spin" />
          <p className="text-sm font-medium tracking-wide">Loading AI Model Configuration...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 w-full max-w-7xl mx-auto pb-12">
      {/* ── Page Header ────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-[#021822]/90 border border-[#00d4b0]/20 rounded-2xl p-6 shadow-[0_4px_25px_rgba(0,0,0,0.5)] backdrop-blur-md">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-[#00d4b0]/10 border border-[#00d4b0]/30 text-[#00d4b0]">
              <Cpu className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-wide flex items-center gap-2 font-mono">
                AI Model Configuration
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-[#00d4b0]/15 text-[#00d4b0] border border-[#00d4b0]/30 font-medium">
                  Global Scope
                </span>
              </h1>
              <p className="text-sm text-slate-400 mt-0.5">
                Manage safe runtime parameters across all active surveillance sources (RTSP &amp; Video Uploads).
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleResetToDefaults}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#02141d] hover:bg-[#032333] text-slate-300 border border-[#00d4b0]/20 text-sm font-medium transition-all shadow-sm active:scale-95 disabled:opacity-50 cursor-pointer"
            title="Reset form fields to standard safe defaults"
          >
            <RotateCcw className="w-4 h-4 text-slate-400" />
            Reset Defaults
          </button>

          <button
            onClick={handleApply}
            disabled={saving || !isDirty}
            className={`flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold transition-all shadow-lg active:scale-95 cursor-pointer ${
              isDirty
                ? 'bg-gradient-to-r from-[#00d4b0] to-[#06b6d4] hover:from-[#00bfa0] hover:to-[#0891b2] text-slate-950 shadow-[0_0_15px_rgba(0,212,176,0.3)]'
                : 'bg-[#010e15] text-slate-600 border border-[#00d4b0]/10 cursor-not-allowed'
            } disabled:opacity-50`}
          >
            {saving ? (
              <>
                <Cpu className="w-4 h-4 animate-spin" />
                Applying...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Apply Changes
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── Status / Feedback Banners ────────────────────────────── */}
      {statusMessage && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-sm animate-fadeIn">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
          <span>{statusMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-red-950/40 border border-red-500/40 text-red-300 text-sm animate-fadeIn">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* ── Scope & Safety Notice ─────────────────────────────────── */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-[#021822]/80 border border-[#00d4b0]/20 text-[#00d4b0] text-xs md:text-sm">
        <Info className="w-5 h-5 text-[#00d4b0] flex-shrink-0 mt-0.5" />
        <div className="text-slate-300">
          <span className="font-semibold text-[#00d4b0]">Global Configuration Active: </span>
          Settings configured on this page apply process-wide to all live RTSP feeds and video analyses without interrupting stream connections or reloading neural weights. Camera-specific Virtual Fence geometries remain managed independently inside the Camera Array.
        </div>
      </div>

      {/* ── System Status & Telemetry Bar (Read-Only) ─────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-[#02141d] border border-[#00d4b0]/15 flex flex-col gap-1 shadow-sm">
          <span className="text-xs text-slate-400 font-medium">Active Detection Model</span>
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-[#00d4b0]" />
            <span className="text-sm font-semibold text-slate-100">
              {systemStatus?.active_model || 'YOLOv8 Nano (yolov8n.pt)'}
            </span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-[#02141d] border border-[#00d4b0]/15 flex flex-col gap-1 shadow-sm">
          <span className="text-xs text-slate-400 font-medium">Detection Engine</span>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-sm font-semibold text-emerald-400">
              {systemStatus?.detection_engine || 'ACTIVE'}
            </span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-[#02141d] border border-[#00d4b0]/15 flex flex-col gap-1 shadow-sm">
          <span className="text-xs text-slate-400 font-medium">Inference Device</span>
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-cyan-400" />
            <span className="text-sm font-semibold text-slate-100">
              {systemStatus?.inference_device || 'CPU (Optimized)'}
            </span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-[#02141d] border border-[#00d4b0]/15 flex flex-col gap-1 shadow-sm">
          <span className="text-xs text-slate-400 font-medium">Multi-Source Pool</span>
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-purple-400" />
            <span className="text-sm font-semibold text-slate-100">
              {systemStatus?.active_sources_count ?? 0} Active Source(s)
            </span>
          </div>
        </div>
      </div>

      {/* ── Main Configuration Grid ───────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* 1. Object Detection (YOLOv8 & Tracking) */}
        <div className="p-5 rounded-2xl bg-[#02141d] border border-[#00d4b0]/15 flex flex-col gap-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-[#00d4b0]/15 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-[#00d4b0]/10 text-[#00d4b0]">
                <Sliders className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-white">Object Detection (YOLOv8)</h2>
                <p className="text-xs text-slate-400">Perimeter detection sensitivity and bounding-box suppression</p>
              </div>
            </div>
            <span className="text-xs font-medium px-2 py-0.5 rounded bg-[#010e15] text-[#00d4b0] border border-[#00d4b0]/20 font-mono">
              Real-Time
            </span>
          </div>

          {/* Confidence Slider */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-slate-200">
                Detection Confidence Threshold
              </label>
              <span className="text-sm font-bold text-[#00d4b0] px-2 py-0.5 rounded bg-[#00d4b0]/10 border border-[#00d4b0]/20 font-mono">
                {Math.round(form.confidence * 100)}%
              </span>
            </div>
            <input
              type="range"
              min="0.25"
              max="0.70"
              step="0.01"
              value={form.confidence}
              onChange={(e) => setForm({ ...form, confidence: parseFloat(e.target.value) })}
              className="w-full accent-[#00d4b0] cursor-pointer h-2 bg-[#010e15] rounded-lg appearance-none"
            />
            <div className="flex justify-between text-xs text-slate-400 font-mono">
              <span>25% (High Recall)</span>
              <span className="text-slate-400 font-medium">Default: 40%</span>
              <span>70% (High Precision)</span>
            </div>
          </div>

          {/* IoU Slider */}
          <div className="flex flex-col gap-2 pt-2 border-t border-[#00d4b0]/15">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-slate-200">
                IoU / NMS Overlap Threshold
              </label>
              <span className="text-sm font-bold text-[#00d4b0] px-2 py-0.5 rounded bg-[#00d4b0]/10 border border-[#00d4b0]/20 font-mono">
                {Math.round(form.iou * 100)}%
              </span>
            </div>
            <input
              type="range"
              min="0.30"
              max="0.60"
              step="0.01"
              value={form.iou}
              onChange={(e) => setForm({ ...form, iou: parseFloat(e.target.value) })}
              className="w-full accent-[#00d4b0] cursor-pointer h-2 bg-[#010e15] rounded-lg appearance-none"
            />
            <div className="flex justify-between text-xs text-slate-400 font-mono">
              <span>30% (Strict Deduplication)</span>
              <span className="text-slate-400 font-medium">Default: 45%</span>
              <span>60% (Loose)</span>
            </div>
          </div>
        </div>

        {/* 2. Night Vision & Low-Light Enhancement */}
        <div className="p-5 rounded-2xl bg-[#02141d] border border-[#00d4b0]/15 flex flex-col gap-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-[#00d4b0]/15 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-blue-500/10 text-cyan-400">
                <Moon className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-white">Night Vision &amp; Low-Light</h2>
                <p className="text-xs text-slate-400">Adaptive LAB lightness enhancement with dynamic gamma LUTs</p>
              </div>
            </div>
            <span className="text-xs font-medium px-2 py-0.5 rounded bg-blue-500/10 text-cyan-300 border border-blue-500/20 font-mono">
              Adaptive
            </span>
          </div>

          <div className="flex flex-col gap-3">
            <label className="text-sm font-medium text-slate-200">
              Enhancement Operating Mode
            </label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { id: 'auto', label: 'Auto (Recommended)', desc: 'Hysteresis luma trigger' },
                { id: 'on', label: 'Always On', desc: 'Enforce CLAHE on all frames' },
                { id: 'off', label: 'Disabled', desc: 'Bypass enhancement' },
              ].map((m) => {
                const active = form.low_light_mode === m.id;
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setForm({ ...form, low_light_mode: m.id })}
                    className={`p-3 rounded-xl border flex flex-col text-left transition-all cursor-pointer ${
                      active
                        ? 'bg-[#00d4b0]/20 border-[#00d4b0]/50 text-white shadow-sm ring-1 ring-[#00d4b0]/50'
                        : 'bg-[#010e15] border-[#00d4b0]/15 text-slate-400 hover:bg-[#032333] hover:text-slate-200'
                    }`}
                  >
                    <span className="text-xs font-bold tracking-wide flex items-center justify-between">
                      {m.label}
                      {active && <Check className="w-3.5 h-3.5 text-[#00d4b0]" />}
                    </span>
                    <span className="text-[11px] text-slate-400 mt-1">{m.desc}</span>
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              In Auto mode, frames with mean luminance &lt; 60 are gently enhanced in LAB color space without modifying original stored evidence.
            </p>
          </div>
        </div>

        {/* 3. Face Recognition (FRS) */}
        <div className="p-5 rounded-2xl bg-[#02141d] border border-[#00d4b0]/15 flex flex-col gap-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-[#00d4b0]/15 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
                <UserCheck className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-white">Face Recognition (FRS)</h2>
                <p className="text-xs text-slate-400">YuNet alignment + SFace 128-D biometric matching</p>
              </div>
            </div>
            <span className="text-xs font-medium px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20 font-mono">
              {systemStatus?.registered_personnel_count ?? 0} In Gallery
            </span>
          </div>

          {/* Personnel Match Threshold Slider */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-slate-200">
                Personnel Match Similarity Threshold
              </label>
              <span className="text-sm font-bold text-purple-400 px-2 py-0.5 rounded bg-purple-500/10 border border-purple-500/20 font-mono">
                {Math.round(form.frs_match_threshold * 100)}%
              </span>
            </div>
            <input
              type="range"
              min="0.50"
              max="0.80"
              step="0.01"
              value={form.frs_match_threshold}
              onChange={(e) => setForm({ ...form, frs_match_threshold: parseFloat(e.target.value) })}
              className="w-full accent-purple-500 cursor-pointer h-2 bg-[#010e15] rounded-lg appearance-none"
            />
            <div className="flex justify-between text-xs text-slate-400 font-mono">
              <span>50% (Lenient)</span>
              <span className="text-slate-400 font-medium">Default: 65% (Cosine Match)</span>
              <span>80% (Strict)</span>
            </div>
          </div>
          <p className="text-xs text-slate-400">
            Cosine similarity threshold used to match query faces against authorized personnel embeddings in the frozen Personnel Registry.
          </p>
        </div>

        {/* 4. License Plate Recognition (ANPR) */}
        <div className="p-5 rounded-2xl bg-[#02141d] border border-[#00d4b0]/15 flex flex-col gap-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-[#00d4b0]/15 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400">
                <CreditCard className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-white">License Plate Recognition (ANPR)</h2>
                <p className="text-xs text-slate-400">Fair multi-vehicle scheduler &amp; temporal voting consensus</p>
              </div>
            </div>
            <span className="text-xs font-medium px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 font-mono">
              Indian MoRTH
            </span>
          </div>

          <div className="flex flex-col gap-3">
            <label className="text-sm font-medium text-slate-200">
              Consensus Verification Frames
            </label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { val: 1, label: '1 Frame', desc: 'Fastest single detection' },
                { val: 2, label: '2 Frames (Recommended)', desc: 'Standard multi-frame consensus' },
                { val: 3, label: '3 Frames', desc: 'High validation certainty' },
              ].map((opt) => {
                const active = form.anpr_consensus_threshold === opt.val;
                return (
                  <button
                    key={opt.val}
                    type="button"
                    onClick={() => setForm({ ...form, anpr_consensus_threshold: opt.val })}
                    className={`p-3 rounded-xl border flex flex-col text-left transition-all cursor-pointer ${
                      active
                        ? 'bg-amber-600/20 border-amber-500 text-white shadow-sm ring-1 ring-amber-500/50'
                        : 'bg-[#010e15] border-[#00d4b0]/15 text-slate-400 hover:bg-[#032333] hover:text-slate-200'
                    }`}
                  >
                    <span className="text-xs font-bold tracking-wide flex items-center justify-between">
                      {opt.label}
                      {active && <Check className="w-3.5 h-3.5 text-amber-400" />}
                    </span>
                    <span className="text-[11px] text-slate-400 mt-1">{opt.desc}</span>
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Number of consistent OCR observations required before resolving and confirming a vehicle license plate. Standard Indian state codes &amp; BH-series formats are verified.
            </p>
          </div>
        </div>

        {/* 5. Suspicious Behavior Detection Modules */}
        <div className="p-5 rounded-2xl bg-[#02141d] border border-[#00d4b0]/15 flex flex-col gap-5 shadow-sm lg:col-span-2">
          <div className="flex items-center justify-between border-b border-[#00d4b0]/15 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-red-500/10 text-red-400">
                <Flame className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-white">Suspicious Activity Behavior Modules</h2>
                <p className="text-xs text-slate-400">Enable or disable specific heuristic behavioral detectors</p>
              </div>
            </div>
            <span className="text-xs font-medium px-2 py-0.5 rounded bg-red-500/10 text-red-300 border border-red-500/20 font-mono">
              Heuristic Engine
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            
            {/* Running Detection Toggle */}
            <div className="p-4 rounded-xl bg-[#010e15] border border-[#00d4b0]/15 flex flex-col justify-between gap-4">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-100">Running Detection</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-bold font-mono ${
                      form.running_enabled
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {form.running_enabled ? 'ENABLED' : 'DISABLED'}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                  Monitors sudden kinematic velocity spikes &amp; upright posture displacement across consecutive frames.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setForm({ ...form, running_enabled: !form.running_enabled })}
                className={`w-full py-2 rounded-lg text-xs font-semibold font-mono transition-all cursor-pointer ${
                  form.running_enabled
                    ? 'bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/30'
                    : 'bg-[#00d4b0]/20 text-[#00d4b0] hover:bg-[#00d4b0]/30 border border-[#00d4b0]/30'
                }`}
              >
                {form.running_enabled ? 'Disable Running Detection' : 'Enable Running Detection'}
              </button>
            </div>

            {/* Crawling Detection Toggle */}
            <div className="p-4 rounded-xl bg-[#010e15] border border-[#00d4b0]/15 flex flex-col justify-between gap-4">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-100">Crawling Detection</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-bold font-mono ${
                      form.crawling_enabled
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {form.crawling_enabled ? 'ENABLED' : 'DISABLED'}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                  Identifies horizontal aspect ratios, low relative height profiles, and continuous ground infiltration.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setForm({ ...form, crawling_enabled: !form.crawling_enabled })}
                className={`w-full py-2 rounded-lg text-xs font-semibold font-mono transition-all cursor-pointer ${
                  form.crawling_enabled
                    ? 'bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/30'
                    : 'bg-[#00d4b0]/20 text-[#00d4b0] hover:bg-[#00d4b0]/30 border border-[#00d4b0]/30'
                }`}
              >
                {form.crawling_enabled ? 'Disable Crawling Detection' : 'Enable Crawling Detection'}
              </button>
            </div>

            {/* Throwing Detection Toggle */}
            <div className="p-4 rounded-xl bg-[#010e15] border border-[#00d4b0]/15 flex flex-col justify-between gap-4">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-100">Throwing Detection</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-bold font-mono ${
                      form.throwing_enabled
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {form.throwing_enabled ? 'ENABLED' : 'DISABLED'}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                  Analyzes object separation from subject, projectile trajectory consistency, and rapid release velocity.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setForm({ ...form, throwing_enabled: !form.throwing_enabled })}
                className={`w-full py-2 rounded-lg text-xs font-semibold font-mono transition-all cursor-pointer ${
                  form.throwing_enabled
                    ? 'bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/30'
                    : 'bg-[#00d4b0]/20 text-[#00d4b0] hover:bg-[#00d4b0]/30 border border-[#00d4b0]/30'
                }`}
              >
                {form.throwing_enabled ? 'Disable Throwing Detection' : 'Enable Throwing Detection'}
              </button>
            </div>

          </div>
        </div>

      </div>

      {/* ── Footer Information / Security Standards ──────────────── */}
      <div className="p-4 rounded-xl bg-[#021822]/70 border border-[#00d4b0]/15 text-slate-400 text-xs flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-[#00d4b0]" />
          <span>Sentinel AI Border Surveillance Platform — System Configuration Module</span>
        </div>
        <div className="flex items-center gap-4 text-slate-500 font-mono">
          <span>YOLOv8 + ByteTrack</span>
          <span>•</span>
          <span>YuNet / SFace</span>
          <span>•</span>
          <span>EasyOCR</span>
        </div>
      </div>
    </div>
  );
}
