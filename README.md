# AI-Based Intelligent Border Surveillance Platform

This is a modular, production-style prototype for an advanced border surveillance platform. It is designed to work with existing IP-based CCTV infrastructure, as well as RTSP streams and video files for development.

## High-Level Architecture

The system is composed of several loosely coupled modules to ensure scalability and ease of upgrading individual AI models:

1. **Camera Layer**: Handles video stream ingestion (RTSP, webcam, or video files) using OpenCV/FFmpeg.
2. **AI Engine (Python)**: A dedicated processing pipeline that runs object detection (YOLO), tracking (ByteTrack/BoT-SORT), recognition (ANPR, FRS), and behavior analysis on incoming frames.
3. **Backend API (FastAPI)**: The central hub managing data persistence, user authentication, and business logic.
4. **Real-time Communication**: WebSockets to push live alerts and events to the dashboard.
5. **Database (PostgreSQL)**: Stores configuration, known entities, and alert history.
6. **Frontend Dashboard (React + Tailwind)**: A modern web interface for operators to monitor cameras, receive real-time alerts, and manage the system.

## Planned Development Phases

1. **Phase 1 (Current)**: Project skeleton, architecture design, and basic setup.
2. **Phase 2**: Implement video ingestion and basic YOLO object detection in the AI Engine.
3. **Phase 3**: Add Multi-object tracking (ByteTrack/BoT-SORT).
4. **Phase 4**: Develop the backend REST API, database schemas, and WebSocket integration.
5. **Phase 5**: Develop the React frontend dashboard to display live data and alerts.
6. **Phase 6**: Integrate advanced AI modules (Intrusion/Line Crossing detection, Loitering, ANPR, FRS).
7. **Phase 7**: Implement Context-aware risk scoring and historical reporting.

## How to Run the Initial Skeletons

### Backend (FastAPI)
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
The backend API will be available at `http://localhost:8000`.

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
The frontend application will be available at `http://localhost:5173` (or port specified by Vite).
