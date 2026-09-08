import React, { useRef, useState, useCallback } from 'react';
import { Upload, X, Film, CheckCircle, AlertCircle, Loader, Radio, Sparkles, Video } from 'lucide-react';
import { uploadVideo, addRtspCamera } from '../../services/videoApi';

const ACCEPTED = '.mp4,.avi,.mov,.mkv,.webm,.m4v';
const ACCEPTED_DISPLAY = 'MP4, AVI, MOV, MKV, WEBM';

const STATUS_STYLES = {
  PLAYING:   { dot: 'bg-emerald-400', text: 'text-emerald-400', badge: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400', label: 'FEED ACTIVE' },
  CONNECTED: { dot: 'bg-cyan-400',    text: 'text-cyan-400',    badge: 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400',       label: 'CONNECTED' },
  STOPPED:   { dot: 'bg-amber-400',   text: 'text-amber-400',   badge: 'bg-amber-500/10 border-amber-500/30 text-amber-400',    label: 'PAUSED' },
  ERROR:     { dot: 'bg-red-500',     text: 'text-red-400',     badge: 'bg-red-500/10 border-red-500/30 text-red-400',          label: 'ERROR' },
  IDLE:      { dot: 'bg-slate-500',   text: 'text-slate-400',   badge: 'bg-slate-800 border-slate-700 text-slate-400',          label: 'IDLE' },
};

export default function VideoUploadPanel({
  activeSource,
  onSourceReady,
  onRemove,
  onAnalyze,
  isAnalyzing = false,
  hasResults = false,
  elapsedSec = 0,
}) {
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  
  const [mode, setMode] = useState('upload'); // 'upload' or 'rtsp'
  const [rtspConfig, setRtspConfig] = useState({ name: '', location: '', url: '' });

  const statusStyle = activeSource
    ? (STATUS_STYLES[activeSource.status] ?? STATUS_STYLES.IDLE)
    : null;

  const handleFile = useCallback(async (file) => {
    if (!file) return;

    const ext = file.name.split('.').pop().toLowerCase();
    const validExts = ['mp4', 'avi', 'mov', 'mkv', 'webm', 'm4v'];
    if (!validExts.includes(ext)) {
      setError(`Unsupported format ".${ext}". Accepted: ${ACCEPTED_DISPLAY}`);
      return;
    }

    setError('');
    setProgress(0);
    setUploading(true);

    try {
      const source = await uploadVideo(file, setProgress);
      onSourceReady(source);
    } catch (err) {
      setError(err.message || 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [onSourceReady]);

  const onDragOver  = (e) => { e.preventDefault(); setIsDragging(true); };
  const onDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };
  const onDrop      = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleRtspSubmit = async (e) => {
    e.preventDefault();
    if (!rtspConfig.url) return;
    setUploading(true);
    setError('');
    
    // Slugify the name to match sector placeholders
    const sectorSlug = (name) => name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
    
    try {
      const payload = { ...rtspConfig, source_id: sectorSlug(rtspConfig.name) };
      const source = await addRtspCamera(payload);
      onSourceReady(source);
      setRtspConfig({ name: '', location: '', url: '' });
    } catch (err) {
      setError(err.message || 'Failed to add RTSP camera.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="bg-[#021822]/85 backdrop-blur-md border border-[#00d4b0]/16 rounded-xl p-4 mb-5 shadow-[0_4px_25px_rgba(0,0,0,0.5)]">
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-[#00d4b0]/10 border border-[#00d4b0]/25 shadow-[0_0_10px_rgba(0,212,176,0.15)]">
            <Film className="w-4 h-4 text-[#00d4b0]" />
          </div>
          <div>
            <h4 className="text-xs font-mono font-bold tracking-wider text-slate-200 uppercase">
              SURVEILLANCE VIDEO INGESTION
            </h4>
          </div>
        </div>

        {/* Status badge */}
        {activeSource && statusStyle && (
          <div className={`flex items-center gap-2 px-2.5 py-1 rounded-full border text-[11px] font-mono font-semibold ${statusStyle.badge}`}>
            <span className={`w-2 h-2 rounded-full ${statusStyle.dot} ${activeSource.status === 'PLAYING' ? 'animate-pulse' : ''}`} />
            <span>{statusStyle.label}</span>
          </div>
        )}
      </div>

      {/* Active source info */}
      {activeSource && !uploading ? (
        <div className="flex flex-wrap sm:flex-nowrap items-center justify-between gap-3 bg-[#01121a]/80 border border-[#00d4b0]/20 rounded-lg p-3">
          <div className="flex items-center gap-3 min-w-0 mr-2">
            <div className="w-9 h-9 rounded-lg bg-[#00d4b0]/10 border border-[#00d4b0]/30 flex items-center justify-center shrink-0">
              <Radio className="w-4 h-4 text-[#00d4b0]" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-white truncate font-mono">
                {activeSource.original_name || activeSource.filename}
              </p>
              <div className="flex items-center gap-2 mt-0.5 text-[10px] font-mono text-slate-400">
                {activeSource.size_mb != null && <span>{activeSource.size_mb} MB</span>}
                <span>•</span>
                <span className={hasResults ? "text-[#00d4b0] font-semibold" : "text-emerald-400"}>
                  {hasResults ? "✓ YOLO Inference Complete" : "Ready for YOLO Inference"}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {onAnalyze && (
              <button
                type="button"
                onClick={() => onAnalyze(activeSource)}
                disabled={isAnalyzing}
                className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold transition-all shadow-md cursor-pointer ${
                  isAnalyzing
                    ? 'bg-[#00d4b0]/20 text-cyan-200 border border-[#00d4b0]/40 cursor-wait'
                    : hasResults
                      ? 'bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-400/40 shadow-[0_0_15px_rgba(16,185,129,0.35)]'
                      : 'bg-gradient-to-r from-[#00b896] via-[#00d4b0] to-[#06b6d4] hover:brightness-110 text-[#011218] border border-[#00d4b0]/50 shadow-[0_0_18px_rgba(0,212,176,0.4)] animate-pulse'
                }`}
                title={hasResults ? "Re-run YOLO Object Detection" : "Start YOLO AI Video Analysis"}
              >
                {isAnalyzing ? (
                  <>
                    <Loader className="w-3.5 h-3.5 animate-spin text-cyan-300" />
                    <span>ANALYZING {elapsedSec}s…</span>
                  </>
                ) : hasResults ? (
                  <>
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-200" />
                    <span>RE-ANALYZE YOLO</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5 text-amber-950 animate-spin" />
                    <span>⚡ ANALYZE WITH YOLO AI</span>
                  </>
                )}
              </button>
            )}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-2.5 py-1.5 rounded text-[11px] font-mono text-[#00d4b0] hover:text-white bg-[#00d4b0]/10 hover:bg-[#00d4b0]/20 border border-[#00d4b0]/30 transition-colors cursor-pointer"
            >
              Change Video
            </button>
            <button
              onClick={onRemove}
              title="Remove source"
              className="p-1.5 rounded text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      ) : mode === 'upload' ? (
        /* Drop zone */
        <div
          onClick={() => !uploading && fileInputRef.current?.click()}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          className={`
            relative border-2 border-dashed rounded-xl px-4 py-5
            flex flex-col items-center justify-center gap-2 cursor-pointer
            transition-all duration-200 select-none group
            ${isDragging
              ? 'border-[#00d4b0] bg-[#00d4b0]/10 shadow-[0_0_20px_rgba(0,212,176,0.2)]'
              : 'border-[#00d4b0]/20 hover:border-[#00d4b0]/50 bg-[#01121a]/60 hover:bg-[#021f2b]/60'
            }
            ${uploading ? 'pointer-events-none opacity-80' : ''}
          `}
        >
          {uploading ? (
            <Loader className="w-7 h-7 text-[#00d4b0] animate-spin" />
          ) : (
            <div className="p-3 rounded-full bg-[#00d4b0]/10 border border-[#00d4b0]/30 group-hover:scale-110 transition-transform shadow-[0_0_12px_rgba(0,212,176,0.15)]">
              <Upload className="w-5 h-5 text-[#00d4b0]" />
            </div>
          )}
          <div className="text-center">
            {uploading ? (
              <p className="text-xs font-mono text-cyan-200 font-semibold">UPLOADING FEED… {progress}%</p>
            ) : (
              <>
                <p className="text-xs font-medium text-slate-300">
                  <span className="text-[#00d4b0] font-semibold underline underline-offset-2">Click to select video</span> or drag &amp; drop file here
                </p>
                <p className="text-[10px] font-mono text-[#6aa89f] mt-1">{ACCEPTED_DISPLAY} • Up to 500 MB</p>
              </>
            )}
          </div>

          {/* Progress bar */}
          {uploading && (
            <div className="w-full max-w-xs bg-slate-900 rounded-full h-1.5 mt-2 overflow-hidden border border-white/5">
              <div
                className="bg-gradient-to-r from-[#00d4b0] to-[#06b6d4] h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>
      ) : (
        /* RTSP Form */
        <form onSubmit={handleRtspSubmit} className="bg-slate-950/40 border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
           <div className="grid grid-cols-2 gap-3">
             <input
               type="text"
               placeholder="Camera Name (e.g. Gate Cam 1)"
               value={rtspConfig.name}
               onChange={(e) => setRtspConfig({...rtspConfig, name: e.target.value})}
               className="bg-slate-900 border border-slate-700 rounded text-xs px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
               required
             />
             <input
               type="text"
               placeholder="Location/Sector"
               value={rtspConfig.location}
               onChange={(e) => setRtspConfig({...rtspConfig, location: e.target.value})}
               className="bg-slate-900 border border-slate-700 rounded text-xs px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
             />
           </div>
           <input
             type="text"
             placeholder="RTSP URL (e.g. rtsp://192.168.1.100:554/stream)"
             value={rtspConfig.url}
             onChange={(e) => setRtspConfig({...rtspConfig, url: e.target.value})}
             className="bg-slate-900 border border-slate-700 rounded text-xs px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
             required
           />
           <button
             type="submit"
             disabled={uploading}
             className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-mono text-xs font-bold py-2 rounded transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
           >
             {uploading ? <Loader className="w-3.5 h-3.5 animate-spin" /> : <Video className="w-3.5 h-3.5" />}
             CONNECT RTSP STREAM
           </button>
        </form>
      )}

      {/* Mode toggles if idle */}
      {!activeSource && (
        <div className="flex items-center justify-center gap-4 mt-3">
          <button 
            type="button"
            onClick={() => setMode('upload')}
            className={`text-xs font-mono font-medium ${mode === 'upload' ? 'text-cyan-400' : 'text-slate-500 hover:text-slate-300'}`}
          >
            UPLOAD VIDEO
          </button>
          <span className="text-slate-700">•</span>
          <button 
            type="button"
            onClick={() => setMode('rtsp')}
            className={`text-xs font-mono font-medium ${mode === 'rtsp' ? 'text-cyan-400' : 'text-slate-500 hover:text-slate-300'}`}
          >
            ADD LIVE IP CAMERA (RTSP)
          </button>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="flex items-start gap-2 mt-2 p-2 rounded bg-red-950/60 border border-red-500/30 text-red-400 text-xs">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED}
        onChange={onFileChange}
        className="hidden"
      />
    </div>
  );
}
