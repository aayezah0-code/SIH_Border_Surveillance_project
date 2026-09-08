# Phase 3: Video Ingestion — Implementation Plan

## Background & Summary

The project already has a skeleton for video ingestion:
- `backend/app/api/video_router.py` — has upload, list, status, delete, and stream endpoints
- `backend/app/services/video_service.py` — has in-memory source registry with `SourceType`/`SourceStatus` enums

**What's missing / broken:**

1. **Backend**: `python-multipart` is NOT in `requirements.txt` — FastAPI cannot process `UploadFile` without it. This will cause a 422/500 error on upload.
2. **Backend**: `FileResponse` doesn't support HTTP Range requests by default in all scenarios — need to add a proper streaming endpoint using `StreamingResponse` with range support for reliable video seek in the browser.
3. **Frontend**: No UI for uploading a video file or showing the real video stream — `CameraGrid` only shows static placeholder cards.
4. **Frontend**: No API layer / service file — raw `fetch` calls would be scattered.
5. **Frontend**: No `VideoPlayer` component that connects to the backend stream URL.
6. **Frontend**: No proxy config — browser will hit CORS issues when fetching from `localhost:8000` during dev.

## Proposed Changes

---

### Backend

#### [MODIFY] [`video_router.py`](file:///c:/Users/HP/Desktop/SIH_Border_Surveillance_project/backend/app/api/video_router.py)
- Replace `FileResponse` stream endpoint with a `StreamingResponse` that reads the file in chunks and correctly handles the `Range` header (required for `<video>` seek to work in Chrome/Firefox).
- Add a `PATCH /api/v1/video/sources/{id}/status` endpoint to let the frontend update source state (PLAYING → STOPPED, etc.).

#### [MODIFY] [`video_service.py`](file:///c:/Users/HP/Desktop/SIH_Border_Surveillance_project/backend/app/services/video_service.py)
- Add `stream_url` and `original_name` fields to `VideoSource` so `to_dict()` returns everything the frontend needs in one call.

#### [MODIFY] [`requirements.txt`](file:///c:/Users/HP/Desktop/SIH_Border_Surveillance_project/backend/requirements.txt)
- Add `python-multipart` (required for `UploadFile` to work in FastAPI).

---

### Frontend

#### [MODIFY] [`vite.config.js`](file:///c:/Users/HP/Desktop/SIH_Border_Surveillance_project/frontend/vite.config.js)
- Add a dev proxy so that `/api` calls from the Vite dev server are forwarded to `http://localhost:8000` — eliminates CORS issues during development.

#### [NEW] `src/services/videoApi.js`
- Thin API service layer with functions: `uploadVideo()`, `getSources()`, `getSource()`, `deleteSource()`, `updateStatus()`.
- All functions use `fetch` against the backend. Centralizes the base URL.

#### [NEW] `src/components/dashboard/VideoUploadPanel.jsx`
- A compact upload panel with:
  - Drag-and-drop or click-to-browse file input (accepts `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`).
  - Upload progress bar (using `XMLHttpRequest` for progress events).
  - Status badge showing current source state (CONNECTED / PLAYING / STOPPED / ERROR).
  - "Remove source" button to call DELETE endpoint.

#### [MODIFY] [`CameraGrid.jsx`](file:///c:/Users/HP/Desktop/SIH_Border_Surveillance_project/frontend/src/components/dashboard/CameraGrid.jsx)
- Add a new `LiveVideoCard` component (alongside the existing `CameraCard`) that:
  - Renders a `<video>` tag pointing to the backend's `/api/v1/video/stream/{filename}` URL.
  - Shows a status badge (CONNECTED / PLAYING / STOPPED / ERROR) in the control bar.
  - Falls back to the existing static placeholder if no source is active.

#### [MODIFY] [`App.jsx`](file:///c:/Users/HP/Desktop/SIH_Border_Surveillance_project/frontend/src/App.jsx)
- Add state for `activeSource` (null or the source object from the backend).
- Import and render `VideoUploadPanel` above the camera grid section.
- When a source is active, replace the first static camera card with `LiveVideoCard`.
- No changes to layout structure, stat cards, alert panel, or events table.

---

## Verification Plan

### Automated
- Start the backend: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- Check `/health` returns `{"status": "healthy"}`
- `curl -F "file=@test.mp4" http://localhost:8000/api/v1/video/upload` returns 201 with `source_id` and `stream_url`
- `curl http://localhost:8000/api/v1/video/sources` lists the source
- `curl http://localhost:8000/api/v1/video/stream/<filename>` serves the file (200 or 206)

### Manual / Frontend
- Start frontend: `npm run dev` in `frontend/`
- Open browser → upload panel visible → click Browse → pick an `.mp4`
- Upload progress bar advances → status becomes PLAYING
- First camera slot shows `<video>` element playing the uploaded file
- Seek bar in the video player works (requires Range header support)
- "Remove" button → source disappears, slot reverts to placeholder
