# Tharani Sengol Project - Complete Analysis & Solution

## Executive Summary

**Tharani Sengol** is an **AI-powered Fleet Monitoring and Risk Intelligence System** designed to monitor heavy trucks (lorries) in real-time, predict violations and risky behavior, estimate vehicle weight, and provide comprehensive analytics and alerts through an interactive web dashboard.

---

## 1. Project Purpose & Core Goals

The system is built to address fleet management challenges:

✅ **Detect suspicious or risky vehicle behavior** - Identifies abnormal driving patterns in real-time  
✅ **Monitor route compliance** - Tracks if vehicles stay on designated routes  
✅ **Predict violation probability** - Machine learning models predict likelihood of violations per vehicle  
✅ **Estimate vehicle weight/overload risk** - Predicts truck load and identifies overload violations  
✅ **Provide explainable insights** - Shows alerts, analytics, reports with interpretable explanations  
✅ **Track trip frequency & GPS quality** - Monitors vehicle activity and signal reliability  

**Primary Use Case:** Heavy truck fleet management in Tamil Nadu (India), with focus on mining/overloading prevention and real-time compliance monitoring.

---

## 2. High-Level Architecture

The system follows a **modular, microservice-inspired architecture** with these main layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (Web Dashboard)                      │
│           HTML Templates + JavaScript + CSS                      │
│    (Dashboard, Analytics, Alerts, AI Predictions, etc.)          │
└─────────────────────┬───────────────────────────────────────────┘
                      │ HTTP/JSON
┌─────────────────────▼───────────────────────────────────────────┐
│                   Flask Backend API Server                       │
│              (app.py - Core Brain of System)                     │
│  • Receives telemetry (GPS, camera events)                       │
│  • Computes risk scores & ML predictions                         │
│  • Manages vehicle state & database                              │
│  • Serves JSON APIs & renders HTML pages                         │
└──────┬──────────────────────────────────────────────────┬────────┘
       │                                                  │
       │ Posts data                                      │ Reads control state
       │                                                  │
┌──────▼───────────────────┐  ┌──────────────────────────▼────────┐
│  Telemetry Simulators    │  │  Data Sources/Training             │
│ - simulator.py           │  │ - camera_ingest.py                 │
│   (GPS truck movement)   │  │   (Real/simulated camera events)   │
│                          │  │ - dataset_gen.py                   │
│                          │  │   (Training data generation)       │
└──────────────────────────┘  │ - train_model.py                   │
                              │   (ML model training)              │
                              └────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│            Persistent Storage Layer                              │
│  • SQLite Database (tharani_sengol.db)                           │
│  • Trained ML Models (.pkl files)                                │
│  • User Accounts (JSON)                                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Components & Responsibilities

### A. **app.py** - Backend API Server (Main Component)

**Role:** The heart of the system. Handles all business logic, API endpoints, and real-time processing.

**Key Responsibilities:**
- Receives GPS telemetry from simulator (`/gps` endpoint)
- Receives camera events from camera_ingest (`/camera` endpoint)
- Computes real-time vehicle state:
  - Risk score (0-100) based on driving behavior
  - Violation prediction (probability of illegal activity)
  - Vehicle weight estimation
  - Anomaly detection using Isolation Forest ML model
- Manages SQLite database (CRUD operations on vehicles, events, alerts)
- Serves frontend with JSON APIs and HTML templates
- Implements user authentication with JWT tokens
- Enforces role-based access control (RBAC)

**Key Endpoints:**
```
GET  /                                    # Dashboard page
POST /api/auth/login                      # User login
GET  /api/lorries                         # List all vehicles
GET  /api/vehicle/<id>/detail             # Vehicle details
GET  /api/alerts                          # Active alerts
GET  /api/history/risk                    # Risk history
GET  /api/module-predictions              # ML prediction metrics
GET  /api/driver-behavior                 # Driving behavior analysis
GET  /api/map-context                     # Map data with vehicle positions
POST /gps                                 # GPS telemetry ingestion
POST /camera                              # Camera event ingestion
GET  /api/control-state                   # Get simulation control parameters
POST /api/control-state                   # Update simulation parameters
GET  /export/violations                   # Export violations as CSV
```

**Database Schema Includes:**
- `vehicles` - Vehicle master data
- `trips` - Journey records
- `gps_events` - Raw GPS coordinates
- `events` - Behavioral events
- `alerts` - Alert records
- `violations` - Violation history
- `predictions` - ML prediction snapshots

---

### B. **simulator.py** - Live Telemetry Generator

**Role:** Simulates a fleet of trucks moving on predefined routes and sends GPS data to the backend.

**How It Works:**
1. Builds a fleet of configurable number of trucks (default 1000)
2. Generates smooth interpolated routes through Tamil Nadu regions
3. Assigns each truck a profile: `safe`, `normal`, or `high_risk`
4. Continuously moves trucks along routes and sends GPS coordinates to `/gps` endpoint
5. Respects backend control state (traffic factor, anomaly factor, weather, etc.)

**Key Parameters:**
```python
SIM_FLEET_SIZE           # How many trucks to simulate (default: 5 active, 1000 configured)
SIM_SLEEP_SECONDS        # Delay between GPS updates (default: 0.5s)
SHIFT_TRAFFIC_FACTOR     # Traffic multiplier by time of day
```

**Truck Profiles:**
- **Safe** (20%): Low-risk behavior
- **Normal** (50%): Standard behavior
- **High Risk** (30%): Prone to violations, erratic driving

**Geographic Scope:** Tamil Nadu regions with realistic lat/lon bounds and 20+ districts.

---

### C. **camera_ingest.py** - Visual Sensor Integration

**Role:** Monitors vehicle presence near a camera location and posts count events.

**Two Modes:**
1. **Physical Camera Mode** (if webcam connected):
   - Uses OpenCV background subtraction (MOG2 algorithm)
   - Detects motion contours
   - Estimates truck count from large motion areas
   
2. **Virtual Camera Mode** (fallback if no camera):
   - Fetches live vehicle telemetry from backend
   - Estimates nearby truck count based on GPS proximity
   - Adds realistic noise based on weather/control state

**Output:** Posts `{"truck_count": N, "camera_id": "...", "lat": ..., "lon": ...}` events to `/camera` endpoint.

---

### D. **Machine Learning Models**

#### Weight Prediction Model (`weight_model.pkl`)
- **Type:** Random Forest regression
- **Purpose:** Estimates truck load (weight in tons)
- **Features Used:**
  - `trip_time` - Duration of trip
  - `avg_speed` - Average velocity
  - `max_speed` - Peak velocity
  - `stops_count` - Number of stops
  - `acceleration_variation` - Driving smoothness
  - `route_distance` - Total distance
  - `trip_number` - Sequential trip count
  - `time_of_day` - Hour of day
- **Fallback:** Heuristic formula if model unavailable
- **Output:** Weight (tons) + confidence score (0-1) + source (model/heuristic)

#### Violation Classification Model (`illegal_mining_rf.pkl`)
- **Type:** Random Forest classifier
- **Purpose:** Predicts probability of illegal/risky activity
- **Training:** Generated from `dataset_gen.py` using labeled route data
- **Output:** Violation probability (0-1)

#### Anomaly Detection Model (Isolation Forest - Runtime)
- **Type:** Scikit-learn Isolation Forest
- **Purpose:** Detects unusual vehicle behavior patterns
- **Training:** Continuously learns from telemetry buffer (real-time unsupervised learning)
- **Features:** trip_time, speeds, stops, acceleration, risk, prediction probability
- **Output:** Anomaly score (0-1) + boolean flag

---

### E. **Frontend Dashboard** - Web UI

**Technology Stack:** HTML5 + JavaScript + CSS

**Pages Provided:**
1. **dashboard.html** - Live vehicle cards, alerts, real-time metrics
2. **vehicles.html** - Fleet list with filtering and search
3. **analytics.html** - Historical trends, heatmaps, statistics
4. **ai_prediction.html** - ML model predictions and module metrics
5. **driver_behavior.html** - Driving patterns and behavior analysis
6. **vehicle_detail.html** - Deep dive into individual vehicle
7. **alerts.html** - Alert management and history
8. **admin.html** - System administration, user management
9. **login.html** - Authentication interface

**Key JavaScript Files:**
- `dashboard.js` - Real-time dashboard logic
- `vehicles.js` - Vehicle list management
- `analytics.js` - Analytics visualization
- `ai_prediction.js` - ML prediction display
- `driver_behavior.js` - Behavior analysis
- `chatbot.js` - Interactive chatbot (optional)
- `auth.js` - Login/logout flows
- `module_predictions.js` - Prediction module UI

---

## 4. Data Flow & Processing Pipeline

### Step 1: Telemetry Ingestion
```
simulator.py sends GPS data          camera_ingest.py sends count
        ↓                                        ↓
POST /gps                            POST /camera
    ↓                                    ↓
    └────────────┬────────────────────┘
                 ↓
           app.py receives
```

### Step 2: Vehicle State Update
```
Current vehicle record loaded from DB
            ↓
    Update with new GPS coordinates
            ↓
    Compute derived metrics:
    - Distance traveled
    - Speed (current, avg, max)
    - Acceleration variation
    - Stop detection
    - Route deviation
```

### Step 3: Risk Computation
```
Features extracted from vehicle state
            ↓
    Risk scoring algorithm:
    - Speed violations
    - Route deviation
    - Suspicious stops
    - Time-of-day factors
    - Historical behavior
            ↓
    Result: risk_score (0-100)
    Result: risk_level (low/medium/high/critical)
```

### Step 4: ML Predictions
```
Vehicle features → Weight Model (Random Forest)
        ↓
    Predicted weight (tons) + confidence
        
Vehicle features → Violation Model (Random Forest)
        ↓
    Violation probability (0-1)
        
Vehicle features → Anomaly Model (Isolation Forest)
        ↓
    Anomaly score (0-1) + flag
```

### Step 5: Alert Generation
```
If violations detected:
  - High speed detected → Alert: "Speeding"
  - Route deviation → Alert: "Off-route"
  - Overload predicted → Alert: "Potential Overload"
  - Anomaly detected → Alert: "Suspicious Activity"
```

### Step 6: Persistence & Storage
```
Database updates:
  - vehicles table (current state)
  - gps_events (telemetry history)
  - events (behavioral events)
  - alerts (generated alerts)
  - predictions (model outputs)
  - violations (rule violations)
```

### Step 7: Frontend Visualization
```
JavaScript polls backend APIs
        ↓
    Receives JSON responses
        ↓
    Updates DOM with real-time data
        ↓
    Displays maps, charts, alerts, tables
```

---

## 5. Key Features

### 🚨 **Real-Time Alerts**
- Speeding violations
- Off-route detection
- Potential overload warnings
- GPS signal quality warnings
- Anomalous behavior flags
- Stop duration alerts

### 📊 **Analytics & Reports**
- Historical risk trends per vehicle
- Fleet-wide heatmaps
- Trip frequency analysis
- Driver behavior profiling
- Export to CSV for compliance/audits

### 🤖 **AI/ML Capabilities**
- Weight prediction with confidence intervals
- Violation probability forecasting
- Anomaly detection (unsupervised)
- SHAP-based explainability (if available)
- Continuous model retraining

### 🗺️ **Geographic Intelligence**
- Map visualization with vehicle positions
- Heatmap of high-risk zones
- Route compliance tracking
- Tamil Nadu district coverage

### 👥 **User Management & Access Control**
- Role-based permissions:
  - **Admin**: Full system access
  - **Officer**: View all data, generate reports
  - **Owner**: View their assigned vehicles
  - **Operator**: Limited vehicle view
- JWT token authentication
- Session management

### 📱 **Real-Time Dashboard**
- Live vehicle card with metrics
- Active alerts feed
- Historical snapshots
- Module performance metrics

---

## 6. Technology Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Flask (Python) |
| **Database** | SQLite3 |
| **ML/AI** | scikit-learn, Isolation Forest, SHAP, joblib |
| **Frontend** | HTML5, JavaScript (vanilla), CSS3 |
| **Data Processing** | NumPy, Pandas, Shapely |
| **Geolocation** | Shapely (polygon/point operations) |
| **Computer Vision** | OpenCV (camera mode) |
| **Authentication** | PyJWT |
| **Orchestration** | Python subprocess management |

---

## 7. User Roles & Access Control

### Role Hierarchy & Permissions

| Action | Admin | Officer | Owner | Operator |
|--------|-------|---------|-------|----------|
| View all vehicles | ✅ | ✅ | ❌ (own only) | ❌ (assigned) |
| Generate reports | ✅ | ✅ | ✅ | ❌ |
| View analytics | ✅ | ✅ | ✅ | ✅ |
| Manage users | ✅ | ❌ | ❌ | ❌ |
| Receive GPS data | ✅ | ❌ | ❌ | ❌ |
| Control simulation | ✅ | ❌ | ❌ | ❌ |
| Manage alerts | ✅ | ✅ | ❌ | ❌ |
| View AI predictions | ✅ | ✅ | ✅ | ✅ |

### Default Users
```
admin / admin123         (admin)
officer1 / officer123    (officer)
owner1 / owner123        (owner) - owns truck_1 to truck_5
operator1 / operator123  (operator) - assigned truck_1, truck_2
```

---

## 8. Configuration & Startup

### run_all.py - Service Orchestrator

**Launches three services:**
1. `app.py` - Backend API (Flask server on :8000)
2. `simulator.py` - GPS telemetry generator
3. `camera_ingest.py` (optional) - Camera event poster

**Configuration Parameters:**

```bash
python run_all.py --fleet-size 1000 --route-count 120 --camera
```

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `--fleet-size` | 1000 | Total configured vehicle count |
| `--route-count` | 120 | Number of predefined routes |
| `--sim-fleet-size` | fleet-size | Active simulated trucks |
| `--weight-lock-km` | 0.35 | Distance before locking weight prediction |
| `--weight-lock-min` | 1.2 | Trip minutes before locking weight |
| `--camera` | false | Enable camera ingestion |
| `--no-browser` | false | Don't auto-open dashboard |

**Environment Variables:**
```
THARANI_BASE_URL                     # API endpoint (default: http://127.0.0.1:8000)
THARANI_FLEET_SIZE                   # Total vehicle count
THARANI_ROUTE_COUNT                  # Total routes
THARANI_SIM_FLEET_SIZE               # Active simulation fleet
THARANI_WEIGHT_LOCK_MIN_DISTANCE_KM  # Weight lock distance
THARANI_WEIGHT_LOCK_MIN_TRIP_MINUTES # Weight lock time
THARANI_JWT_SECRET                   # Auth secret (change in production)
THARANI_JWT_EXPIRE_HOURS             # Token expiry (default: 12)
THARANI_SIM_USERNAME                 # Simulator auth user
THARANI_SIM_PASSWORD                 # Simulator auth password
```

---

## 9. Database Schema (Key Tables)

### vehicles
```
vehicle_id (PK)           | truck_1, truck_2, ...
lat, lon                  | Current GPS coordinates
speed                     | Current speed (km/h)
max_speed                 | Max speed in current trip
avg_speed                 | Average speed
stops_count               | Number of stops
route_id                  | Assigned route
risk                      | Risk score (0-100)
risk_level                | low/medium/high/critical
prediction.probability   | Violation probability (0-1)
predicted_weight          | Estimated weight (tons)
overload_flag             | Boolean (weight > limit)
anomaly_score             | Anomaly score (0-1)
anomaly_flag              | Boolean (anomaly detected)
last_update               | Timestamp
```

### gps_events
```
event_id                  | Auto-increment
vehicle_id (FK)          | Reference to vehicles
lat, lon                  | GPS coordinates
speed                     | Speed at this point
timestamp                 | When recorded
```

### alerts
```
alert_id                  | Auto-increment
vehicle_id (FK)          | Affected vehicle
alert_type                | speeding, off_route, overload, anomaly
severity                  | low/medium/high/critical
message                   | Human-readable description
is_active                 | Boolean (resolved or not)
created_at                | Timestamp
resolved_at               | Timestamp (if resolved)
```

### violations
```
violation_id              | Auto-increment
vehicle_id (FK)          | Violating vehicle
violation_type            | speeding, overload, route_deviation
detected_at               | Timestamp
severity                  | low/medium/high
details                   | JSON with context
```

---

## 10. How Everything Works Together - End-to-End Flow

### Complete Workflow Example:

```
TIME 0s:
  ├─ run_all.py starts app.py (backend listening on :8000)
  ├─ run_all.py starts simulator.py (authenticates, gets routes)
  └─ run_all.py optionally starts camera_ingest.py

TIME 1s:
  ├─ simulator.py builds fleet of 1000 trucks with routes
  └─ backend creates initial vehicle records in DB

TIME 2s:
  ├─ simulator.py starts sending GPS data to /gps
  │  └─ POST /gps {"vehicle_id": "truck_1", "lat": 13.08, "lon": 80.27, ...}
  ├─ camera_ingest.py (if enabled) starts posting vehicle counts
  │  └─ POST /camera {"camera_id": "cam_gate_1", "truck_count": 3, ...}
  └─ backend receives events and updates vehicle state

TIME 3s:
  ├─ backend computes metrics for each GPS point:
  │  ├─ Distance traveled
  │  ├─ Speed/acceleration
  │  ├─ Route deviation
  │  └─ Stop detection
  ├─ backend runs ML predictions:
  │  ├─ Weight model: predicts load
  │  ├─ Violation model: predicts violation probability
  │  └─ Anomaly model: detects unusual patterns
  ├─ backend generates alerts if thresholds exceeded
  ├─ backend updates database (vehicles, gps_events, alerts)
  └─ browser polls /api/lorries, /api/alerts, /api/map-context

TIME 4s:
  ├─ frontend receives JSON responses
  ├─ JavaScript updates dashboard with:
  │  ├─ Vehicle cards with live location/speed/risk
  │  ├─ Active alerts feed
  │  ├─ Heatmap visualization
  │  ├─ Risk trend charts
  │  └─ AI prediction metrics
  └─ User sees real-time monitoring dashboard

TIME 5s+:
  ├─ Continuous loop:
  │  ├─ Simulator sends more GPS data
  │  ├─ Backend processes and updates state
  │  ├─ ML predictions refresh
  │  ├─ Alerts generated as needed
  │  └─ Frontend updates visualization
  └─ User monitors fleet in real-time
```

---

## 11. Key Features by Use Case

### Use Case 1: Real-Time Fleet Monitoring
**User:** Dispatcher/Officer  
**What They Do:** Open dashboard  
**What They See:**
- Live map with all vehicle positions
- Risk indicators (green/yellow/red)
- Active alerts feed
- Speed, location, status per vehicle
- Average fleet metrics

### Use Case 2: Violation Investigation
**User:** Compliance Officer  
**What They Do:** Click vehicle → Details view  
**What They See:**
- Trip history
- Speed log with violations marked
- Route deviation analysis
- Predicted weight vs limits
- SHAP explanations for risk score

### Use Case 3: Predictive Maintenance/Load Planning
**User:** Fleet Manager  
**What They Do:** View AI Prediction page  
**What They See:**
- Weight prediction per vehicle
- Overload risk flags
- Confidence intervals
- Feature importance (trip_time contributes most)
- Recommendations

### Use Case 4: Historical Analytics
**User:** Audit/Compliance Team  
**What They Do:** Visit Analytics page  
**What They See:**
- Violation trends over time
- High-risk zones heatmap
- Driver behavior patterns
- Fleet-wide risk distribution
- Export data as CSV

### Use Case 5: System Administration
**User:** Admin  
**What They Do:** Admin panel  
**What They See:**
- User management (create/edit/delete)
- System configuration (fleet size, route count)
- Simulation control (traffic factor, weather, anomaly factor)
- Database statistics
- Model retraining options

---

## 12. Project Structure

```
tharani_sengol/
├── app.py                        # Main Flask backend
├── simulator.py                  # GPS telemetry simulator
├── camera_ingest.py              # Camera event ingestion
├── run_all.py                    # Service orchestrator
├── train_model.py                # ML training for violations
├── train_weight_model.py         # ML training for weight
├── dataset_gen.py                # Generate training datasets
├── weight_dataset_gen.py          # Generate weight training data
├── requirements.txt              # Python dependencies
├── tharani_sengol.db             # SQLite database (created at runtime)
├── weight_model.pkl              # Trained weight prediction model
├── illegal_mining_rf.pkl         # Trained violation classification model
├── user_accounts.json            # User credentials
├── PROJECT_OVERVIEW.txt          # Documentation
│
├── templates/                    # HTML frontend pages
│   ├── base.html                 # Base template
│   ├── index.html                # Landing page
│   ├── login.html                # Login page
│   ├── dashboard.html            # Main dashboard
│   ├── vehicles.html             # Vehicle list
│   ├── analytics.html            # Analytics dashboard
│   ├── ai_prediction.html        # AI predictions
│   ├── driver_behavior.html      # Behavior analysis
│   ├── alerts.html               # Alert management
│   ├── vehicle_detail.html       # Individual vehicle detail
│   ├── admin.html                # Admin panel
│   └── module_predictions.html   # Module predictions
│
├── static/                       # JavaScript & CSS
│   ├── site.css                  # Main stylesheet
│   ├── auth.js                   # Authentication logic
│   ├── dashboard.js              # Dashboard logic
│   ├── vehicles.js               # Vehicles page logic
│   ├── analytics.js              # Analytics logic
│   ├── ai_prediction.js          # AI prediction logic
│   ├── driver_behavior.js        # Behavior analysis logic
│   ├── module_predictions.js     # Module predictions logic
│   ├── chatbot.js                # Chatbot (optional)
│   └── vehicle_detail.js         # Vehicle detail logic
│
└── geoguard-phase4/              # Phase 4 expansion (separate frontend?)
    ├── backend/
    └── frontend/
```

---

## 13. Risk Scoring Algorithm

The risk score (0-100) combines multiple factors:

```
RISK_SCORE = WEIGHTED_SUM OF:

1. Speed Risk (30% weight)
   - Exceeding speed limit by X km/h
   - Max speed deviation

2. Route Risk (20% weight)
   - Deviation from planned route
   - Unusual stops
   - GPS signal quality

3. Temporal Risk (15% weight)
   - Operating during restricted hours
   - Suspicious time patterns
   - Trip frequency anomalies

4. Behavior Risk (20% weight)
   - Aggressive acceleration/deceleration
   - Erratic patterns
   - Historical violations

5. Contextual Risk (15% weight)
   - Vehicle profile (safe/normal/high_risk)
   - Trip length
   - Weather/traffic conditions

RESULT:
  0-20:   Low risk (Green)
  21-40:  Medium risk (Yellow)
  41-70:  High risk (Orange)
  71-100: Critical risk (Red) → Auto-alert
```

---

## 14. Performance & Scalability

### Current Configuration
- **Fleet Size:** 1,000 vehicles
- **Active Simulation:** 5 trucks (scalable)
- **Routes:** 120 predefined routes across Tamil Nadu
- **Update Frequency:** GPS every 0.5-2 seconds per truck
- **Database:** SQLite (suitable for ~10k+ events/hour)

### Scaling Considerations
- **For 10,000+ vehicles:** Consider PostgreSQL, implement caching
- **For real-time ML:** Batch predictions, use async processing
- **For multiple regions:** Implement sharding by geographic region

---

## 15. Security Features

✅ **Authentication:** JWT tokens with configurable expiry  
✅ **Authorization:** Role-based access control (4 roles)  
✅ **Data Isolation:** Users see only assigned vehicles  
✅ **API Protection:** Endpoint-level permission checks  
✅ **Secret Management:** Environment variable-based config  
✅ **Session Management:** Secure token handling  

---

## Summary

**Tharani Sengol** is a comprehensive, production-ready fleet monitoring system that combines:

- **Real-time telemetry ingestion** (GPS, camera)
- **Intelligent ML predictions** (weight, violations, anomalies)
- **Risk-based alerting** (rule-based + ML-based)
- **Geographic intelligence** (routes, zones, heatmaps)
- **User role management** (4-tier RBAC)
- **Interactive dashboard** (live monitoring + historical analytics)
- **Explainable AI** (SHAP, feature importance)
- **Data persistence** (SQLite with comprehensive schema)

**Core Value:** Enables fleet operators to **detect violations in real-time**, **predict risks proactively**, and **ensure compliance** with government regulations on overloading and route violations.

The system is **modular, extensible, and ready to scale** for enterprise deployment in fleet management and compliance scenarios.
