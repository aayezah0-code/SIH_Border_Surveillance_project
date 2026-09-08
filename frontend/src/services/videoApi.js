/**
 * videoApi.js — Video Ingestion API Service Layer
 * ------------------------------------------------
 * Centralises all communication with the backend video endpoints.
 * Import individual functions wherever needed in the UI.
 *
 * Base URL is intentionally relative ("/api/...") so it works with the
 * Vite dev proxy (localhost:5173 → localhost:8000) and in production
 * without any environment-variable wiring.
 */

const BASE = '/api/v1/video';

// ── Upload ──────────────────────────────────────────────────────────────────

/**
 * Upload a video file to the backend.
 *
 * @param {File}     file        - The File object from the input element.
 * @param {Function} onProgress  - Callback (0–100) for upload progress.
 * @returns {Promise<Object>}    - Resolved source object from the server.
 */
export function uploadVideo(file, onProgress) {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener('load', () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error(data.detail || `Upload failed (${xhr.status})`));
        }
      } catch {
        reject(new Error('Invalid response from server.'));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error during upload.')));
    xhr.addEventListener('abort', () => reject(new Error('Upload cancelled.')));

    xhr.open('POST', `${BASE}/upload`);
    xhr.send(formData);
  });
}

// ── Sources ──────────────────────────────────────────────────────────────────

/**
 * Fetch all registered video sources.
 * @returns {Promise<Array>}
 */
export async function getSources() {
  const res = await fetch(`${BASE}/sources`);
  if (!res.ok) throw new Error(`Failed to list sources (${res.status})`);
  const data = await res.json();
  return data.sources ?? [];
}

/**
 * Register an RTSP camera stream.
 * @param {Object} config - { name, location, url, source_id? }
 * @returns {Promise<Object>}
 */
export async function addRtspCamera(config) {
  const res = await fetch(`${BASE}/sources/rtsp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to add RTSP camera (${res.status})`);
  }
  return res.json();
}

/**
 * Fetch a single source by ID.
 * @param {string} sourceId
 * @returns {Promise<Object>}
 */
export async function getSource(sourceId) {
  const res = await fetch(`${BASE}/sources/${sourceId}`);
  if (!res.ok) throw new Error(`Source not found (${res.status})`);
  return res.json();
}

/**
 * Update the playback status of a source.
 * @param {string} sourceId
 * @param {'PLAYING'|'STOPPED'|'ERROR'|'CONNECTED'} newStatus
 * @param {string} [errorMessage]
 * @returns {Promise<Object>}
 */
export async function updateSourceStatus(sourceId, newStatus, errorMessage) {
  const body = { status: newStatus };
  if (errorMessage) body.error_message = errorMessage;

  const res = await fetch(`${BASE}/sources/${sourceId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Status update failed (${res.status})`);
  }
  return res.json();
}

/**
 * Delete / deregister a source.
 * @param {string} sourceId
 * @returns {Promise<Object>}
 */
export async function deleteSource(sourceId) {
  const res = await fetch(`${BASE}/sources/${sourceId}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Delete failed (${res.status})`);
  }
  return res.json();
}

// ── Detection (Phase 4) ──────────────────────────────────────────────────────

/**
 * Trigger YOLO object detection on a source's video.
 * @param {string} sourceId
 * @param {Object} params - optional { max_frames, sample_rate, confidence }
 * @param {number} timeoutMs - request timeout in milliseconds (default 10 min)
 * @returns {Promise<Object>}
 */
export async function analyzeVideo(sourceId, params = {}, timeoutMs = 600_000) {
  const query = new URLSearchParams(params).toString();
  const url = `/api/v1/detection/analyze/${sourceId}${query ? '?' + query : ''}`;

  // Use AbortController so the browser doesn't hang indefinitely.
  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeoutMs);

  let res;
  try {
    res = await fetch(url, { method: 'POST', signal: controller.signal });
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Analysis timed out — the server took too long to respond.');
    }
    throw err;
  } finally {
    clearTimeout(timerId);
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Analysis failed (${res.status})`);
  }
  return res.json();
}

/**
 * Fetch cached detection results for a source.
 * @param {string} sourceId
 * @returns {Promise<Object>}
 */
export async function getDetectionResults(sourceId) {
  const res = await fetch(`/api/v1/detection/results/${sourceId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Results not found (${res.status})`);
  }
  return res.json();
}

// ── Virtual Fence (Phase 7) ──────────────────────────────────────────────────

/**
 * Set the virtual fence configuration for a source.
 * @param {string} sourceId
 * @param {Object} config - { type: 'zone'|'line', points: [[x,y],...] }
 * @returns {Promise<Object>}
 */
export async function setVirtualFence(sourceId, config) {
  const res = await fetch(`/api/v1/fence/${sourceId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to set virtual fence (${res.status})`);
  }
  return res.json();
}

/**
 * Get the active virtual fence configuration for a source.
 * @param {string} sourceId
 * @returns {Promise<Object>}
 */
export async function getVirtualFence(sourceId) {
  try {
    const res = await fetch(`/api/v1/fence/${sourceId}`);
    if (!res.ok) return { status: 'none', config: null };
    return res.json();
  } catch {
    return { status: 'none', config: null };
  }
}

/**
 * Clear the virtual fence configuration for a source.
 * @param {string} sourceId
 * @returns {Promise<Object>}
 */
export async function clearVirtualFence(sourceId) {
  const res = await fetch(`/api/v1/fence/${sourceId}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to clear virtual fence (${res.status})`);
  }
  return res.json();
}

// ── Evidence Capture (Phase 8) ───────────────────────────────────────────────

/**
 * Fetch the list of evidence snapshots from the backend.
 * @param {string} [sourceId]    - Filter by camera/source UUID (extension-tolerant).
 * @param {number} [limit]       - Maximum number of records (default 100).
 * @param {number} [trackId]     - Optional filter by ByteTrack track ID.
 * @param {string} [eventType]   - Optional filter by event_type string.
 * @returns {Promise<Object>}
 */
export async function getEvidenceList(sourceId, limit = 100, trackId = null, eventType = null) {
  const params = new URLSearchParams({ limit });
  if (sourceId) {
    // Strip .mp4/.avi extension before sending — backend source_id is a bare UUID
    const cleanId = sourceId.replace(/\.[^.]+$/, '');
    params.append('source_id', cleanId);
  }
  if (trackId != null) params.append('track_id', trackId);
  if (eventType)       params.append('event_type', eventType);
  const res = await fetch(`/api/v1/evidence?${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch evidence (${res.status})`);
  }
  return res.json();
}

/**
 * Build the URL to view an evidence image by filename.
 * @param {string} filename
 * @returns {string}
 */
export function getEvidenceImageUrl(filename) {
  return `/api/v1/evidence/image/${encodeURIComponent(filename)}`;
}

// ── Events & Persistence (Phase 10) ──────────────────────────────────────────

/**
 * Query persisted detection events from the backend database.
 */
export async function getEvents(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== '') {
      params.append(key, val);
    }
  });
  const res = await fetch(`/api/v1/events?${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch events (${res.status})`);
  }
  return res.json();
}

/**
 * Trigger download of full CSV surveillance log.
 */
export function getCsvExportUrl(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== '') {
      params.append(key, val);
    }
  });
  return `/api/v1/events/export/csv?${params.toString()}`;
}

/**
 * List surveillance sessions.
 */
export async function getSessions(limit = 50, offset = 0) {
  const res = await fetch(`/api/v1/sessions?limit=${limit}&offset=${offset}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch sessions (${res.status})`);
  }
  return res.json();
}

// ── Personnel Registry ───────────────────────────────────────────────────────

/**
 * List all registered personnel from the gallery.
 */
export async function getPersonnelList() {
  const res = await fetch('/api/v1/faces');
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to list personnel (${res.status})`);
  }
  return res.json();
}

/**
 * Register a new person with name, role, and 1 to 5 face photos.
 */
export async function registerPersonnel(name, role, photoFiles) {
  const formData = new FormData();
  formData.append('name', name);
  formData.append('role', role || 'Authorized Personnel');

  for (const file of photoFiles) {
    formData.append('photos', file);
  }

  const res = await fetch('/api/v1/faces/register', {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Personnel registration failed (${res.status})`);
  }
  return res.json();
}

/**
 * Delete a person from the registry and gallery.
 */
export async function deletePersonnel(personId) {
  const res = await fetch(`/api/v1/faces/${personId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to delete personnel (${res.status})`);
  }
  return res.json();
}

// ── ANPR (Automatic Number Plate Recognition) ───────────────────────────────

/**
 * Fetch list of recognized vehicle license plates.
 */
export async function getAnprRecords(params = {}) {
  const query = new URLSearchParams();
  if (params.source_id) query.set('source_id', params.source_id);
  if (params.plate_number) query.set('plate_number', params.plate_number);
  if (params.vehicle_class) query.set('vehicle_class', params.vehicle_class);
  if (params.limit) query.set('limit', params.limit);
  if (params.offset) query.set('offset', params.offset);

  const res = await fetch(`/api/v1/anpr/records?${query.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch ANPR records (${res.status})`);
  return res.json();
}

/**
 * Fetch single ANPR record by anpr_id.
 */
export async function getAnprRecordById(anprId) {
  const res = await fetch(`/api/v1/anpr/records/${anprId}`);
  if (!res.ok) throw new Error(`Failed to fetch ANPR record (${res.status})`);
  return res.json();
}

/**
 * Fetch current global AI model configuration and telemetry.
 */
export async function getAIConfig() {
  const res = await fetch('/api/v1/config/ai');
  if (!res.ok) throw new Error(`Failed to fetch AI configuration (${res.status})`);
  return res.json();
}

/**
 * Update global AI model configuration safely.
 */
export async function updateAIConfig(payload) {
  const res = await fetch('/api/v1/config/ai', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Failed to update AI configuration (${res.status})`);
  }
  return res.json();
}

