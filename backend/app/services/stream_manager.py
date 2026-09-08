"""
Stream Manager Service
----------------------
Manages live RTSP/IP camera streams in the background.
Reads frames using OpenCV and makes the latest frame available
for both MJPEG streaming to the frontend and YOLO inference.
"""

import cv2
import os
import time
import threading
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class CameraStream:
    def __init__(self, source_id: str, rtsp_url: str):
        self.source_id = source_id
        self.rtsp_url = rtsp_url
        
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self.latest_frame = None
        self.latest_jpeg = None
        
        self.is_connected = False
        self.error = None
        
        # Lock to protect reading the latest frame while it's being written
        self._lock = threading.Lock()

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._update_loop,
            name=f"CameraStream-{self.source_id}",
            daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        # Release is now handled by the background thread to prevent OpenCV deadlocks
        self.is_connected = False

    def _update_loop(self):
        logger.info(f"Connecting to RTSP stream: {self.rtsp_url}")
        
        # Prevent indefinite blocking in FFmpeg
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;5000"
        
        # We can set environment variables or use FFmpeg options if needed,
        # but basic VideoCapture is often sufficient for most RTSP streams.
        self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        
        if not self._cap.isOpened():
            self.error = "Failed to open RTSP stream"
            self.is_connected = False
            logger.error(self.error)
            
            from app.services.video_service import set_source_status, SourceStatus
            set_source_status(self.source_id, SourceStatus.ERROR, self.error)
            return
            
        try:
            while not self._stop_event.is_set():
                ret, frame = self._cap.read()
                if not ret:
                    # Connection dropped, try to reconnect
                    logger.warning(f"RTSP stream dropped: {self.source_id}. Attempting reconnect...")
                    self.is_connected = False
                    from app.services.video_service import set_source_status, SourceStatus
                    set_source_status(self.source_id, SourceStatus.ERROR, "Connection dropped. Reconnecting...")
                    if self._cap:
                        self._cap.release()
                    time.sleep(2)
                    if self._stop_event.is_set():
                        break
                    self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                    if self._cap.isOpened():
                        self.is_connected = True
                        set_source_status(self.source_id, SourceStatus.CONNECTED, None)
                        logger.info(f"Reconnected to RTSP stream: {self.source_id}")
                    continue

                # Encode to JPEG for the MJPEG stream
                # Using quality 70 to keep bandwidth reasonable
                ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ret:
                    with self._lock:
                        self.latest_frame = frame
                        self.latest_jpeg = jpeg.tobytes()
                        
                    # Mark as fully connected only after obtaining and encoding the first frame
                    if not self.is_connected:
                        self.is_connected = True
                        from app.services.video_service import set_source_status, SourceStatus
                        set_source_status(self.source_id, SourceStatus.CONNECTED, None)
                        logger.info(f"Connected to RTSP stream and receiving frames: {self.source_id}")
                        
                # cap.read() blocks until a frame is available, so no sleep needed unless it's a file
        finally:
            if self._cap:
                self._cap.release()
                self._cap = None
            logger.info(f"CameraStream thread stopped and resources released: {self.source_id}")
            
    def get_latest_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self.latest_jpeg
            
    def get_latest_frame(self):
        with self._lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
            return None


class StreamManager:
    def __init__(self):
        self._streams: Dict[str, CameraStream] = {}
        
    def add_stream(self, source_id: str, rtsp_url: str) -> CameraStream:
        if source_id in self._streams:
            self._streams[source_id].stop()
            
        stream = CameraStream(source_id, rtsp_url)
        self._streams[source_id] = stream
        stream.start()
        return stream
        
    def get_stream(self, source_id: str) -> Optional[CameraStream]:
        return self._streams.get(source_id)
        
    def remove_stream(self, source_id: str):
        stream = self._streams.pop(source_id, None)
        if stream:
            stream.stop()

stream_manager = StreamManager()
