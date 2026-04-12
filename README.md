# 🚀 Simple Download Manager (SDM)

A multi-threaded download manager built using distributed systems concepts, similar to IDM/XDM.

## 📌 Project Objective

The goal of this project is to design and implement a download manager that improves download speed and reliability using:

- Multi-threading
- HTTP Range Requests
- Fault tolerance
- Resume capability

---

## 🏗️ Architecture

This project follows a **Client–Server Layered Architecture**.

### 🔹 Layers:

1. **Frontend (Client)**
   - Simple web interface (HTML)
   - Sends requests to backend
   - Displays progress

2. **Backend API (FastAPI)**
   - Handles user requests
   - Exposes REST endpoints
   - Communicates with download manager

3. **Core Download Manager**
   - Manages downloads
   - Splits files into segments
   - Controls threads and queue

4. **Worker Threads**
   - Download file segments in parallel

5. **File System Layer**
   - Stores `.part` files
   - Merges into final file

6. **Persistence Layer**
   - Stores download history in JSON

---

## 🧩 System Components

- `main.py` → FastAPI server (API layer)
- `download_manager.py` → Core logic
- `segment_worker.py` → Segment downloading
- `file_assembler.py` → File merging
- `bandwidth_limiter.py` → Speed control
- `history_manager.py` → Persistent storage
- `history.json` → Saved downloads

---

## 🔗 Communication

- **REST API** → control downloads  
- **Threads** → parallel segment downloads  
- **File system** → persistence and resume  

---

## ⚙️ Features

### ✅ Core Features
- Download files from URL
- Multi-threaded segmented downloads
- HTTP Range requests
- File merging

### ✅ Reliability & Control
- Pause / Resume downloads
- True resume (continues from `.part` files)
- Retry mechanism (fault tolerance)

### ✅ Advanced Features
- Bandwidth limiting (Token Bucket)
- Download queue system
- Thread-safe progress tracking

### ✅ Progress Monitoring
- Download percentage
- Download speed
- Estimated remaining time (ETA)

### ✅ Persistence
- Download history stored in JSON
- Resume downloads after restart

---

## ▶️ How to Run

### 1. Clone the repository
```bash
git clone https://github.com/mayssgh/simple-download-manager.git
cd simple-download-manager/backend