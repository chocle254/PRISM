"""
PRISM - Ambient Intelligence Agent
Backend: FastAPI + Google ADK Multi-Agent Orchestrator
"""
from dotenv import load_dotenv
load_dotenv()

import os
os.environ["GOOGLE_API_KEY"] = os.environ.get("GEMINI_API_KEY", "")

import asyncio
import base64
import json
import logging

from typing import AsyncGenerator


import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.orchestrator import PRISMOrchestrator
from utils.session_manager import SessionManager


# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="PRISM API",
    description="Ambient Intelligence Agent — See, Hear, Create, Act",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_manager = SessionManager()

# ── Pydantic Models ─────────────────────────────────────────────────────────────
class SessionCreateRequest(BaseModel):
    user_id: str
    context: dict = {}

class SessionCreateResponse(BaseModel):
    session_id: str
    status: str

class CreativeRequest(BaseModel):
    session_id: str
    prompt: str
    screen_frame: str | None = None  # base64 encoded image


# ── REST Endpoints ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "PRISM Backend", "version": "1.0.0"}


@app.post("/session/create", response_model=SessionCreateResponse)
async def create_session(req: SessionCreateRequest):
    """Create a new PRISM agent session."""
    session_id = await session_manager.create_session(req.user_id, req.context)
    return SessionCreateResponse(session_id=session_id, status="created")


@app.delete("/session/{session_id}")
async def end_session(session_id: str):
    """End and clean up a PRISM session."""
    await session_manager.end_session(session_id)
    return {"status": "ended", "session_id": session_id}


@app.post("/creative/stream")
async def creative_stream(req: CreativeRequest):
    """
    Stream interleaved creative output (text + image descriptions + narration).
    Uses Gemini's interleaved/mixed output capability.
    """
    session = await session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    orchestrator: PRISMOrchestrator = session["orchestrator"]

    async def generate():
        async for chunk in orchestrator.creative_agent.stream_creative_output(
            prompt=req.prompt,
            screen_context=req.screen_frame,
        ):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── WebSocket: Main Real-Time Interaction ───────────────────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Main WebSocket endpoint for real-time PRISM interaction.
    
    Message types from client:
      - audio_chunk: base64 audio data
      - screen_frame: base64 screenshot
      - interrupt: user interruption signal
      - text_input: fallback text message
    
    Message types to client:
      - voice_response: text + audio for TTS
      - creative_chunk: interleaved creative content piece
      - action: UI navigation action to execute
      - status: agent status update
      - error: error message
    """
    await websocket.accept()
    logger.info(f"WebSocket connected: session {session_id}")

    # Wait up to 5 seconds for session to be created (race condition fix)
    session = None
    for _ in range(10):
        session = await session_manager.get_session(session_id)
        if session:
            break
    await asyncio.sleep(0.5)

    if not session:
        await websocket.close()
        return

    orchestrator: PRISMOrchestrator = session["orchestrator"]
    await orchestrator.on_connect(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")

            if msg_type == "audio_chunk":
                audio_bytes = base64.b64decode(message["data"])
                await orchestrator.handle_audio(audio_bytes)

            elif msg_type == "screen_frame":
                frame_bytes = base64.b64decode(message["data"])
                await orchestrator.handle_screen_frame(frame_bytes)

            elif msg_type == "interrupt":
                await orchestrator.handle_interrupt(message.get("text", ""))

            elif msg_type == "text_input":
                await orchestrator.handle_text(message["text"])

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                logger.warning(f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session {session_id}")
        await orchestrator.on_disconnect()
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        await websocket.send_json({"type": "error", "message": str(e)})
        await orchestrator.on_disconnect()


# ── WebSocket: Screen Action Executor ──────────────────────────────────────────
@app.websocket("/ws/actions/{session_id}")
async def actions_websocket(websocket: WebSocket, session_id: str):
    """
    Dedicated channel for receiving UI actions to execute on the client side.
    PRISM sends actions here; the frontend JS executes them in the browser.
    """
    await websocket.accept()
    session = None
    for _ in range(10):
        session = await session_manager.get_session(session_id)
        if session:
            break
    await asyncio.sleep(0.5)

    if not session:
        await websocket.close()
        return

    orchestrator: PRISMOrchestrator = session["orchestrator"]
    orchestrator.set_action_socket(websocket)

    try:
        while True:
            # Keep alive + receive action results
            raw = await websocket.receive_text()
            message = json.loads(raw)
            if message.get("type") == "action_result":
                await orchestrator.handle_action_result(message)
    except WebSocketDisconnect:
        pass


# ── Entry point ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
