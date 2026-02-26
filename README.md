# 🌈 PRISM — Ambient Intelligence Agent

> **"You think it. PRISM builds it and does it."**

PRISM is a next-generation multi-modal AI agent that combines **real-time voice interaction**, **visual screen understanding**, and **interleaved creative output** into one seamless ambient intelligence experience. It sees your screen, hears your voice, creates rich multimedia content, and takes actions on your behalf — all in one continuous, intelligent loop.

---

## 🏆 Hackathon: Gemini Live Agent Challenge

**Categories Targeted:**
- 🗣️ **Live Agents** — Real-time voice with Gemini Live API
- ✍️ **Creative Storyteller** — Interleaved multimodal output
- ☸️ **UI Navigator** — Visual screen understanding & automation

---

## ✨ What Makes PRISM Different

Most AI tools do one thing. PRISM's three capabilities are **architecturally dependent on each other**:

| Without Voice | No intent → no action |
|---|---|
| Without Vision | No context → generic output |
| Without Creative | No plan → blind execution |

Remove any one capability and the experience collapses. That interdependence is what makes PRISM genuinely innovative.

---

## 🎯 Demo Scenario

**A small business owner in Nairobi launches a new honey brand:**

1. Says: *"PRISM, help me launch my honey brand online"*
2. PRISM **hears** the intent via Gemini Live API
3. PRISM **sees** the open spreadsheet and product photos on screen
4. PRISM **creates** a full brand package: narration + logo concept + social posts + launch email — all interleaved in one stream
5. PRISM **executes**: opens Canva, creates the post, drafts the Gmail, scaffolds the landing page
6. User interrupts: *"Change the brand color to green"* — PRISM **stops, adjusts, continues**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER'S BROWSER                           │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │  🎙️ Voice   │  │  🖥️ Screen Share  │  │  ✨ Creative     │   │
│  │  Interface  │  │  (WebRTC)        │  │  Output Stream  │   │
│  └──────┬──────┘  └────────┬─────────┘  └────────▲─────────┘   │
│         │  WebSocket        │  JPEG frames         │             │
└─────────┼───────────────────┼──────────────────────┼─────────────┘
          │                   │                      │
┌─────────▼───────────────────▼──────────────────────┼─────────────┐
│                   PRISM BACKEND (Cloud Run)         │             │
│  ┌─────────────────────────────────────────────┐   │             │
│  │          PRISM Orchestrator (ADK)           │   │             │
│  │  ┌─────────────────────────────────────┐   │   │             │
│  │  │  ADK Root Agent (gemini-2.0-flash)  │   │   │             │
│  │  │  Tools: analyze_screen,             │   │   │             │
│  │  │         generate_creative_brief,    │   │   │             │
│  │  │         execute_ui_action,          │   │   │             │
│  │  │         speak_to_user,              │   │   │             │
│  │  │         recall_context              │   │   │             │
│  │  └─────────────────────────────────────┘   │   │             │
│  └───────────┬──────────────────────┬──────────┘   │             │
│              │                      │              │             │
│  ┌───────────▼──────┐  ┌────────────▼──┐  ┌───────▼──────────┐  │
│  │   Voice Agent    │  │ Vision Agent  │  │ Creative Agent   │  │
│  │ Gemini Live API  │  │ Gemini Vision │  │ Gemini Flash +   │  │
│  │ (audio in/out)   │  │ (screenshot   │  │ Imagen 3         │  │
│  │ STT + TTS        │  │  analysis)    │  │ (interleaved     │  │
│  └──────────────────┘  └───────────────┘  │  output)         │  │
│                                            └──────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  Google Cloud Services                     │  │
│  │  Firestore (sessions) │ Cloud Storage (assets) │ Pub/Sub   │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| AI Brain | Google ADK (Agent Development Kit) |
| Voice | Gemini Live API (`gemini-2.0-flash-live-001`) |
| Vision | Gemini Multimodal (`gemini-2.0-flash`) |
| Image Generation | Imagen 3 on Vertex AI |
| Backend | FastAPI + Python 3.12 |
| Frontend | React 18 + WebRTC |
| Hosting | Google Cloud Run |
| Database | Google Cloud Firestore |
| Storage | Google Cloud Storage |
| IaC | Terraform |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Node.js 20+
- Google Cloud account
- Gemini API key ([get one here](https://aistudio.google.com))

### Local Development

**1. Clone and set up environment**
```bash
git clone https://github.com/YOUR_USERNAME/prism-agent
cd prism-agent

# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
GEMINI_API_KEY=your_gemini_api_key_here
GCP_PROJECT_ID=your_gcp_project_id
GCP_REGION=us-central1
USE_FIRESTORE=false
EOF
```

**2. Start the backend**
```bash
cd backend
uvicorn main:app --reload --port 8080
# API docs at http://localhost:8080/docs
```

**3. Start the frontend**
```bash
cd frontend
npm install
REACT_APP_BACKEND_URL=http://localhost:8080 \
REACT_APP_WS_URL=ws://localhost:8080 \
npm start
# App at http://localhost:3000
```

### Deploy to Google Cloud

**Option A: Automated Script**
```bash
export GCP_PROJECT_ID="your-project-id"
export GEMINI_API_KEY="your-api-key"

chmod +x infrastructure/deploy.sh
./infrastructure/deploy.sh
```

**Option B: Terraform**
```bash
cd infrastructure
terraform init
terraform apply \
  -var="project_id=your-project-id" \
  -var="gemini_api_key=your-api-key"
```

---

## 📁 Project Structure

```
prism/
├── backend/
│   ├── main.py                    # FastAPI app + WebSocket endpoints
│   ├── agents/
│   │   ├── orchestrator.py        # ADK master orchestrator
│   │   ├── voice_agent.py         # Gemini Live API voice
│   │   ├── vision_agent.py        # Screen analysis + action planning
│   │   └── creative_agent.py      # Interleaved multimodal output
│   ├── utils/
│   │   ├── session_manager.py     # Session lifecycle
│   │   └── memory.py              # Conversation memory
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   └── src/
│       ├── App.jsx                # Main app + layout
│       ├── components/
│       │   ├── VoiceInterface.jsx # Real-time audio UI
│       │   ├── ScreenShare.jsx    # WebRTC screen capture
│       │   ├── CreativeOutput.jsx # Interleaved content renderer
│       │   ├── ActionFeed.jsx     # UI action execution queue
│       │   └── PRISMHeader.jsx    # App header
│       └── hooks/
│           └── index.js           # WebSocket + Session hooks
│
├── infrastructure/
│   ├── main.tf                    # Terraform GCP infrastructure
│   └── deploy.sh                  # Automated deployment script
│
└── README.md
```

---

## 🎥 Key Features

### 🗣️ Live Voice Interaction
- Real-time speech-to-text via Gemini Live API
- Natural interruption handling — say "stop" mid-execution
- Emotional tone-aware responses (calm, excited, authoritative)
- Audio visualization feedback

### 🖥️ Screen Understanding
- Continuous screen frame analysis via WebRTC + Gemini Vision
- App detection, UI element recognition, content understanding
- Action plan generation from visual context
- Change detection for action verification

### ✨ Interleaved Creative Output
- Mixed-media stream: narration + images + structured data + actions
- Imagen 3 image generation inline with text
- Social post, email, and landing page generation
- Storyboard and brand package creation

### ⚡ UI Automation
- Cross-application navigation without API access
- Form filling and content creation
- Real-time action queue with status tracking
- Interrupt-and-resume execution flow

---

## 🌍 Impact

PRISM democratizes access to sophisticated AI assistance. A small business owner in Nairobi, a student in Lagos, a craftsperson in Kampala — anyone who can speak can now have an intelligent collaborator that sees their screen, understands their context, and helps them achieve professional outcomes.

**No technical knowledge required. Just speak.**

---

## 👥 Team

Built for the **Gemini Live Agent Challenge** hackathon.

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

*Built with ❤️ using Google Gemini, ADK, and Google Cloud*
#   P R I S M  
 