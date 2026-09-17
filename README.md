Sentinel AI

AI-Powered Intelligent Video Analytics Platform for Border Surveillance

Transforming existing CCTV infrastructure into an intelligent, proactive and event-driven surveillance system.

Sentinel AI is an AI-powered intelligent video analytics platform designed for border and high-security surveillance environments. Instead of requiring organizations to replace their existing CCTV infrastructure, Sentinel AI adds an intelligent analytics layer over existing RTSP/IP camera streams and uploaded surveillance footage.

The platform continuously analyzes video, detects and tracks objects, recognizes authorized personnel, reads vehicle license plates, identifies suspicious human activities, monitors restricted areas, detects loitering, enhances low-light footage, captures important evidence, and generates real-time alerts and structured event logs.

The core philosophy behind Sentinel AI is simple:

“Don't just record what happened — understand what is happening.”

🚨 The Problem

Traditional CCTV surveillance mainly provides video feeds that must be continuously monitored by human operators.

In a border or high-security environment, this creates several challenges:

Multiple cameras generate huge amounts of video.
Human operators cannot continuously monitor every feed.
Suspicious activities can happen within seconds.
Unknown personnel may enter sensitive areas.
Vehicles and license plates need to be monitored.
Night-time and low-light conditions reduce visibility.
Important events may be difficult to trace later.
Manually reviewing recorded footage is time-consuming.
Existing CCTV infrastructure may already be expensive to replace.

Therefore, the problem is not simply capturing video.

The real problem is:

How can existing surveillance infrastructure become intelligent enough to detect, understand, prioritize and record important events automatically?

💡 Our Solution

Sentinel AI works as an intelligence layer over existing surveillance infrastructure.

Instead of asking security personnel to watch everything, the system continuously analyzes the incoming video and highlights events that require attention.

Core workflow
Camera / Uploaded Video
          ↓
     Frame Processing
          ↓
   Low-Light Enhancement
       (if required)
          ↓
     YOLOv8 Detection
          ↓
     ByteTrack Tracking
          ↓
  ┌───────┴────────┐
  ↓                ↓
Person           Vehicle
  ↓                ↓
FRS          ANPR Pipeline
  ↓
Behavior Analysis
  ↓
Running / Crawling /
Throwing / Loitering
          ↓
Restricted Area /
Virtual Fence Analysis
          ↓
    Event Confirmation
          ↓
 ┌────────┼──────────┐
 ↓        ↓          ↓
Alert   Evidence    Database
          ↓
       WebSocket
          ↓
       Dashboard
⭐ What Makes Sentinel AI Different?

Sentinel AI does not claim that technologies such as YOLO, OCR or facial recognition were invented by us. These are established technologies.

Our innovation lies in how multiple AI and computer-vision capabilities are engineered into one unified surveillance workflow.

Sentinel AI combines:
Object Detection
Multi-Object Tracking
Facial Recognition
Automatic Number Plate Recognition
Suspicious Activity Detection
Loitering Detection
Restricted Area Monitoring
Virtual Fence / Line Crossing
Low-Light Enhancement
Real-Time RTSP Analysis
Evidence Capture
Threat Alert Management
Event Audit Logging
Multi-Camera Monitoring
Personnel Registry
Secure Email Verification

all inside a single platform.

Our key idea:

“We are not replacing the surveillance infrastructure — we are adding intelligence to it.”

The system is also designed so that uploaded videos and live RTSP streams can use the same core AI processing architecture, reducing the need to maintain completely separate detection systems.

🧠 Key Features
1. 🎥 Existing CCTV / RTSP Integration

Sentinel AI can connect to existing IP/CCTV camera streams through RTSP.

This means organizations can use their existing camera infrastructure instead of replacing every camera with a new AI-enabled camera.

Working:
Existing IP Camera
       ↓
      RTSP
       ↓
 Stream Manager
       ↓
 Frame Processing
       ↓
 AI Detection Pipeline
       ↓
 Alerts + Events
       ↓
 Dashboard

The live feed can then be analyzed for:

Objects
Personnel
Vehicles
License plates
Suspicious activities
Restricted-area intrusion
Loitering
Other configured surveillance events
2. 🎯 YOLOv8 Object Detection

YOLOv8 acts as the primary object detection layer.

Its responsibility is to identify objects present in each frame.

For detected objects, the system obtains:

Object class
Bounding box
Confidence score
Position information
Example:
Video Frame
     ↓
   YOLOv8
     ↓
Person
Vehicle
Sports Ball
Other supported objects

YOLO provides the fundamental perception layer on which the rest of the surveillance intelligence is built.

3. 🔄 ByteTrack Multi-Object Tracking

Object detection alone only tells us what is present in a particular frame.

For surveillance, we also need to know:

“Is this the same person or vehicle that appeared in the previous frame?”

This is where ByteTrack is used.

ByteTrack associates detections across frames and maintains a persistent Track ID.

Simple explanation:

YOLO tells us WHAT is there.
ByteTrack tells us WHICH object is continuing across frames.

Tracking is especially important for:

Running
Crawling
Throwing
Loitering
Restricted-area monitoring
Virtual fence events
ANPR association

because these features require information across multiple frames.

4. 🏃 Suspicious Activity Detection

Sentinel AI includes a dedicated temporal suspicious-activity analysis layer.

Currently supported activities include:

🏃 Running

The system analyzes the movement of a tracked person over time.

It uses:

Track history
Object displacement
Movement speed
Body dimensions
Temporal confirmation
Posture-related geometric information

The system does not depend on a single frame.

Instead, the behavior is confirmed across multiple observations to reduce false alerts.

🧎 Crawling

Crawling detection uses the tracked person's spatial and temporal characteristics.

The system evaluates features such as:

Bounding-box geometry
Aspect ratio
Relative body height
Horizontal movement
Temporal persistence

The activity is confirmed through temporal analysis rather than a single-frame classification.

🤾 Throwing

Throwing detection analyzes the relationship between a person and a throwable object.

The system considers:

Person-object proximity
Object movement speed
Separation between person and object
Direction of movement
Trajectory consistency
Temporal continuity

The event is confirmed over multiple observations.

This helps distinguish a potential throwing event from simple object movement or dropping.

5. 🕒 Loitering Detection

Loitering detection identifies situations where an unknown person remains inside a monitored area for longer than the configured dwell time.

Working:
Person Detected
      ↓
Person Tracked
      ↓
Is Person Known?
   ↓          ↓
  Yes        No
   ↓          ↓
Normal      Monitor
             ↓
      Enter Monitored Zone
             ↓
      Start Dwell Timer
             ↓
    Remains Beyond Threshold?
             ↓
            YES
             ↓
      Loitering Alert

The system uses tracking history rather than simply detecting a person.

Short tracking interruptions are handled to avoid unnecessarily resetting the behavior state.

6. 🚧 Restricted Area Intrusion Detection

Security-sensitive areas can be configured as restricted zones.

The system monitors tracked objects against these zones.

When an object/person enters a restricted region, the system can generate an intrusion event.

Workflow:
Tracked Person
      ↓
Position Evaluation
      ↓
Restricted Zone Check
      ↓
Inside Zone?
   ↓       ↓
 No       Yes
 ↓         ↓
Continue   Intrusion Event
              ↓
           Alert

Restricted areas can be configured for individual surveillance contexts.

7. 📏 Virtual Fence / Line Crossing

Sentinel AI can monitor virtual boundaries within a camera view.

A virtual line can be configured across the surveillance scene.

The system tracks an object's movement relative to the line.

Example:
        Virtual Fence
------------------------------
            ↑
        Person crosses
            ↑
       Track Movement
            ↓
      Line Crossing Event

This allows security teams to monitor unauthorized movement across defined boundaries.

8. 👤 Facial Recognition System

Sentinel AI includes a dedicated personnel recognition pipeline.

It uses:

YuNet for face detection
SFace for face recognition
Personnel Registry for registered identities
Pipeline:
Video Frame
     ↓
   YuNet
     ↓
Face Detection
     ↓
   SFace
     ↓
Face Representation
     ↓
Personnel Registry
     ↓
Known / Unknown

The system can distinguish between:

Registered/known personnel
Unknown individuals
Important:

Unknown does not automatically mean threat.

An unknown person becomes relevant to the alert system when they also satisfy a configured surveillance condition such as loitering, restricted-area intrusion or suspicious behavior.

9. 🪪 Personnel Registry

The Personnel Registry provides a centralized place to manage authorized personnel.

Personnel profiles can contain:

Personnel details
Reference images
Identity information

These registered profiles are used by the facial-recognition pipeline.

Purpose:

Instead of treating every detected person as an unknown individual, Sentinel AI can compare detected faces against the registered personnel database.

This helps reduce unnecessary alerts and improves operator awareness.

10. 🚗 Automatic Number Plate Recognition — ANPR

Sentinel AI includes a dedicated ANPR pipeline for vehicle monitoring.

Pipeline:
Vehicle Detection
       ↓
    YOLOv8
       ↓
   ByteTrack
       ↓
Plate Localization
       ↓
Dedicated Plate Detector
       ↓
Plate Crop
       ↓
Image Preprocessing
       ↓
    EasyOCR
       ↓
Temporal Consensus
       ↓
Validation
       ↓
License Plate Result

The system does not blindly trust OCR from a single frame.

Instead, OCR observations can be accumulated across a vehicle track and resolved through temporal consensus.

This improves robustness when the plate is:

Small
Partially unclear
Slightly blurred
Difficult to read in a single frame
11. 🌙 Low-Light / Night Surveillance

Sentinel AI includes a dedicated low-light enhancement pipeline.

This is image enhancement, not thermal imaging.

The system first estimates whether the scene is sufficiently dark.

If required, an enhancement branch is activated.

Pipeline:
Raw Frame
    ↓
Luminance Estimation
    ↓
Is Scene Low-Light?
    ↓
   YES
    ↓
Gamma Enhancement
    +
CLAHE Enhancement
    ↓
Enhanced Detection Frame

The enhancement combines:

Gamma correction
CLAHE
Conservative blending
Important design decision:

The system preserves the original raw frame for tasks where original image information matters, such as:

Facial recognition
ANPR
Evidence capture

while the enhanced branch can be used for object detection.

12. 🚨 Threat Alert System

When a surveillance event is confirmed, Sentinel AI generates a structured alert.

Alerts can contain information such as:

Event type
Activity type
Object class
Track ID
Camera/source
Confidence
Severity
Timestamp
Description

Severity can be represented through levels such as:

Critical
High
Medium
Low

This allows the operator to focus attention on events requiring immediate review.

13. 📸 Evidence Capture

Important events can trigger evidence capture.

The system can preserve a relevant frame associated with an event.

Evidence is handled through a background/non-blocking writing mechanism so that disk operations do not unnecessarily block the core surveillance processing loop.

Workflow:
Confirmed Event
      ↓
Evidence Request
      ↓
Non-Blocking Queue
      ↓
Evidence Writer
      ↓
Evidence Snapshot
      ↓
Event Reference
14. 📖 Event Logbook

The Event Logbook provides a structured audit trail of surveillance activity.

It helps operators review:

What happened
When it happened
Which camera generated it
What type of event occurred
Which object/track was involved

The interface can focus on the current surveillance session/event context, while historical information remains persisted in the database.

15. 📊 CSV Event Reporting

Sentinel AI supports event-data export in CSV format.

The report can contain structured surveillance information rather than simply exporting video.

This is useful for:

Analysis
Documentation
Reporting
Investigation
Record keeping

The Event Logbook can work with the current session context for operational reporting.

16. 📹 Video Feeds

The Video Feeds section provides a dedicated environment for:

Uploaded video analysis
Active video feeds
RTSP sources
Feed management
Analysis results

The same underlying surveillance intelligence can be applied to uploaded footage and live sources.

17. 📡 Camera Array

The Camera Array provides centralized monitoring of multiple camera connections.

Each camera maintains its own surveillance context.

This helps prevent different camera events from becoming mixed together.

Each camera can have its own:

Feed
Threat Alerts
Restricted Area Intrusion information
Camera configuration
Monitoring context

This architecture is important for multi-camera border surveillance.

18. ⚡ Real-Time WebSocket Communication

For live surveillance, waiting for repeated frontend requests is inefficient.

Sentinel AI uses WebSocket communication for real-time event delivery.

Workflow:
AI Detection
     ↓
Confirmed Event
     ↓
Backend Event Layer
     ↓
WebSocket
     ↓
React Dashboard
     ↓
Real-Time Alert

This allows important events to appear on the dashboard without requiring the frontend to continuously refresh the page.

19. 🗄️ Database & Persistence

Sentinel AI uses:

SQLite
SQLAlchemy
SQLite WAL mode

The database stores structured surveillance and application information such as:

Cameras
Surveillance sessions
Detection events
Threat alerts
Intrusion events
Evidence references
Personnel
Personnel images
Authentication-related records

The application does not need to treat the database as a continuous video recorder.

Instead, it focuses on structured event-driven surveillance data.

20. 🔐 Secure Authentication

Sentinel AI includes an authentication layer using:

Password Security

Bcrypt

Passwords are never stored as plaintext.

Session Authentication

JWT

Authenticated users receive a JWT after successful authentication.

Email Verification

New users must verify their email before receiving authenticated dashboard access.

Verification Flow:
Registration
     ↓
Pending Registration
     ↓
Generate 6-Digit OTP
     ↓
Send Email
     ↓
User Enters OTP
     ↓
OTP Validation
     ↓
Email Verified
     ↓
JWT Issued
     ↓
Dashboard Access

The OTP:

Contains 6 digits
Expires after a limited period
Is not stored as plaintext
Cannot be reused after successful verification

Email delivery uses SMTP, with configuration kept outside source code.

21. 🖥️ Frontend Architecture

The frontend is built using React.

The application follows a component-based architecture.

Major interfaces include:

Landing Page
Login
Registration
Email Verification
Defense Grid
Video Feeds
Threat Alerts
Event Logbook
Camera Array
Personnel Registry
AI Model Config

The dashboard receives real-time surveillance updates through WebSocket and communicates with backend services through REST APIs.

22. ⚙️ Backend Architecture

The backend is built using Python + FastAPI.

FastAPI provides:

REST APIs
Authentication APIs
Video-analysis endpoints
Event APIs
Alert APIs
Evidence APIs
Camera-related services
WebSocket integration

The backend keeps AI processing and application logic modular.

23. 🔬 Technology Stack
Frontend
Technology	Purpose
React.js	User interface and dashboard
HTML	Structure
CSS	Styling and responsive UI
WebSocket	Real-time event updates
Backend
Technology	Purpose
Python	Core backend + AI ecosystem
FastAPI	REST API backend
SQLAlchemy	Database ORM
SQLite	Persistent data storage
SQLite WAL	Improved concurrent database behavior
Computer Vision & AI
Technology	Purpose
YOLOv8	Object detection
ByteTrack	Multi-object tracking
OpenCV	Image/video processing
YuNet	Face detection
SFace	Face recognition
EasyOCR	License plate OCR
Dedicated Plate Detector	License plate localization
Authentication
Technology	Purpose
Bcrypt	Password hashing
JWT	Authentication/session token
SMTP	Email delivery
6-digit OTP	Email verification
🔄 Complete Technical Pipeline

The overall Sentinel AI pipeline can be understood in six major stages.

Stage 1 — Video Ingestion

Input can come from:

RTSP Camera
     OR
Uploaded Video
Stage 2 — Frame Processing

Frames are extracted and prepared for AI processing.

If the scene is sufficiently dark:

Low-Light Detection
        ↓
Gamma + CLAHE Enhancement
Stage 3 — Perception
YOLOv8
   ↓
Object Detection
   ↓
ByteTrack
   ↓
Persistent Track IDs
Stage 4 — Specialized Intelligence

Based on the detected object and context:

Person
Person
 ↓
FRS
 ↓
Known / Unknown

AND

Behavior Analysis
 ↓
Running
Crawling
Throwing
Loitering
Vehicle
Vehicle
 ↓
ANPR
 ↓
Plate Detection
 ↓
OCR
 ↓
Temporal Consensus
 ↓
Plate Result
Spatial Analysis
Object Track
 ↓
Restricted Area
Virtual Fence
 ↓
Spatial Event
Stage 5 — Event Confirmation

The system does not treat every raw detection as a threat.

Depending on the event, it uses:

Confidence
Tracking
Persistence
Temporal history
Movement
Spatial conditions
Behavior-specific rules
Multi-frame confirmation

This helps reduce unnecessary alerts.

Detection ≠ Alert

A raw detection becomes an actionable event only after the relevant event logic confirms it.

Stage 6 — Event Response

Once an event is confirmed:

Confirmed Event
      ↓
 ┌────┼───────────┐
 ↓    ↓           ↓
Alert Evidence   Database
 ↓                ↓
WebSocket        CSV/Event Log
 ↓
React Dashboard

The operator receives a structured representation of what happened.

🧩 Hybrid AI Architecture

One of the important architectural decisions in Sentinel AI is that not every problem is solved using a separate neural network.

The platform uses a hybrid approach.

AI models handle perception:
YOLOv8 → object detection
YuNet → face detection
SFace → face recognition
Plate detector → plate localization
EasyOCR → text recognition
Temporal/spatial intelligence handles event reasoning:
Loitering → dwell time
Running → movement analysis
Crawling → body geometry + movement
Throwing → person-object kinematics
Restricted area → spatial rules
Virtual fence → line-crossing logic

This approach makes the system:

More modular
More explainable
More configurable
Less dependent on heavy models for every feature
🎯 Why Sentinel AI is Practical

Sentinel AI is designed around the reality of existing surveillance infrastructure.

Instead of:

Replace Existing Cameras
        ↓
Buy New AI Cameras
        ↓
Deploy New Infrastructure

our approach is:

Existing CCTV/IP Cameras
        ↓
RTSP
        ↓
Sentinel AI Intelligence Layer
        ↓
Detection + Recognition + Behavior Analysis
        ↓
Actionable Surveillance Events

This makes the platform suitable as an intelligent software layer over existing video infrastructure.

🛡️ Event-Driven Surveillance

A key design principle of Sentinel AI is event-driven monitoring.

Instead of making the operator watch everything:

Thousands of Frames
       ↓
AI Analysis
       ↓
Meaningful Events
       ↓
Prioritized Alerts
       ↓
Human Attention

The goal is not to remove humans from the surveillance loop.

The goal is to help security personnel focus their attention where it matters most.

🚀 Performance & Optimization

Sentinel AI also includes performance-oriented processing decisions.

Low-Light Optimization

High-resolution footage can make image enhancement expensive.

Therefore, low-light processing is performed at an appropriate inference resolution rather than unnecessarily enhancing the complete original resolution.

Asynchronous Operations

Operations such as:

Database writes
Evidence writing
Event handling

are separated where appropriate so they do not unnecessarily block the core surveillance processing loop.

Tracking-Based Intelligence

Instead of repeatedly performing expensive analysis without context, the system maintains tracking history and uses temporal information for behavior analysis.

🔍 Important Design Principles
1. Detection is not automatically a threat

The system separates:

Detection
   ↓
Tracking
   ↓
Analysis
   ↓
Confirmation
   ↓
Event
   ↓
Alert
2. Known does not automatically mean safe everywhere

Recognition status and spatial security policies are treated as separate concepts.

3. Unknown does not automatically mean dangerous

An unknown individual becomes relevant when they satisfy an event or configured surveillance condition.

4. Raw evidence matters

Enhanced frames may help detection, but original frames are preserved for important downstream tasks such as recognition, ANPR and evidence.

🧪 Testing & Validation

The platform has been tested across multiple parts of the system, including:

Object detection
Multi-object tracking
ANPR
Facial recognition
Low-light processing
Loitering
Running detection
Crawling detection
Throwing detection
Restricted area monitoring
RTSP analysis
Database persistence
WebSocket event delivery
Frontend integration
Authentication
Email OTP verification

Both automated testing and manual browser/video testing were used during development.

📁 High-Level Project Structure
Sentinel-AI/
│
├── ai_engine/
│   └── AI and computer-vision modules
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   ├── schemas/
│   │   ├── db/
│   │   └── main.py
│   │
│   ├── data/
│   ├── tests/
│   ├── uploads/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── context/
│   │   └── App.jsx
│   │
│   └── package.json
│
└── README.md
🚀 How Sentinel AI Works — In One Example

Imagine a person enters a monitored border area.

Step 1

The CCTV camera sends its live feed through RTSP.

Step 2

Sentinel AI receives the frames.

Step 3

YOLOv8 detects the person.

Step 4

ByteTrack assigns a Track ID and follows that person across frames.

Step 5

The system checks the person's face against the Personnel Registry.

Step 6

If the person is unknown, behavior and spatial rules continue to evaluate the track.

Step 7

Suppose the person remains inside a monitored area longer than the configured threshold.

Step 8

Loitering logic confirms the behavior.

Step 9

Sentinel AI generates a structured threat event.

Step 10

The event can:

Generate an alert
Capture evidence
Enter the Event Logbook
Be stored in the database
Be sent to the frontend through WebSocket
Step 11

The operator immediately sees the event on the dashboard.

This is the core idea of Sentinel AI:

From raw video → to understanding → to actionable information.

🔮 Future Scope

Although the current platform provides a broad surveillance intelligence layer, future versions can expand toward:

Advanced pose-based behavior recognition
Larger-scale multi-camera deployment
GPU-based distributed inference
More robust ANPR under extreme conditions
Camera health monitoring
Additional sensor integration
Edge-device deployment
Advanced analytics and reporting
Role-based access control
Large-scale production databases such as PostgreSQL

These are future enhancements rather than dependencies of the current system.

⚠️ Current Limitations

Like any computer-vision system, performance can depend on:

Camera quality
Camera angle
Lighting
Object size
Occlusion
Motion blur
Computational resources
Video quality

Behavior detection based on geometric and temporal analysis can also face ambiguity in complex real-world situations.

ANPR performance may decrease when license plates are:

Very small
Blurred
Occluded
Captured at difficult angles

These limitations provide opportunities for future improvements.

🔐 Security Considerations

Sentinel AI follows several security-oriented practices:

Passwords are hashed using Bcrypt.
JWT is used for authenticated sessions.
New users require email verification.
OTPs have limited validity.
Verification codes are not stored as plaintext.
SMTP credentials are kept outside source code.
Sensitive credentials should not be committed to Git repositories.
Surveillance event data is stored separately from authentication data.
🌐 Application Modules

Sentinel AI provides a centralized interface containing:

🏠 Landing Page
      ↓
🔐 Authentication
      ↓
📧 Email Verification
      ↓
🛡️ Defense Grid
      ↓
🎥 Video Feeds
      ↓
🚨 Threat Alerts
      ↓
📖 Event Logbook
      ↓
📡 Camera Array
      ↓
👤 Personnel Registry
      ↓
⚙️ AI Model Config

Each module has a specific responsibility while sharing the same underlying surveillance architecture.

🏆 Core USP
Sentinel AI brings together:

Existing Camera Infrastructure

AI-Based Detection

Multi-Object Tracking

Face Recognition

ANPR

Behavior Analysis

Restricted Area Intelligence

Real-Time Alerts

Evidence Capture

Event Audit Trail

into one unified surveillance platform.

💭 The Idea Behind Sentinel AI

Surveillance should not be about storing more footage.

It should be about extracting more intelligence from the footage that already exists.

Sentinel AI aims to move surveillance from:

“Someone has to watch every camera.”

to:

“AI continuously analyzes every camera and brings important events to the operator.”

👥 Intended Use Cases

Sentinel AI can be adapted for environments where continuous video monitoring and rapid event awareness are important, such as:

Border surveillance
Restricted zones
Critical infrastructure
Industrial facilities
Large campuses
High-security premises
Strategic facilities
Controlled access areas

The exact detection rules and deployment configuration can be adapted to the operational environment.

📌 Project Summary

Sentinel AI is an intelligent video analytics platform that combines computer vision, AI-based perception, temporal behavior analysis, real-time communication and event-driven monitoring into a unified surveillance system.

Its central objective is to make existing surveillance infrastructure more intelligent without requiring the entire camera ecosystem to be replaced.

The platform follows a simple but powerful pipeline:

SEE
 ↓
DETECT
 ↓
TRACK
 ↓
UNDERSTAND
 ↓
CONFIRM
 ↓
ALERT
 ↓
RECORD
 ↓
RESPOND
In one sentence:

Sentinel AI transforms existing CCTV infrastructure into an intelligent, event-driven surveillance system that can detect, track, recognize and analyze critical events in real time.

🛠️ Built With

Python • FastAPI • React.js • YOLOv8 • ByteTrack • OpenCV • YuNet • SFace • EasyOCR • SQLite • SQLAlchemy • WebSocket • JWT • Bcrypt • SMTP
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
