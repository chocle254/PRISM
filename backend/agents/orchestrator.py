"""
PRISM Orchestrator
──────────────────
Master ADK agent that coordinates Voice, Vision, and Creative sub-agents.
Built on Google Agent Development Kit (ADK).
"""

import asyncio
import os
import logging

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from fastapi import WebSocket

from agents.voice_agent import VoiceAgent
from agents.vision_agent import VisionAgent
from agents.creative_agent import CreativeAgent
from agents.desktop_agent import desktop
from utils.memory import ConversationMemory

logger = logging.getLogger(__name__)


class PRISMOrchestrator:

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.websocket: WebSocket | None = None
        self.action_socket: WebSocket | None = None
        self.memory = ConversationMemory(session_id)

        # Sub-agents
        self.voice_agent = VoiceAgent(session_id=session_id, orchestrator=self)
        self.vision_agent = VisionAgent(session_id=session_id, orchestrator=self)
        self.creative_agent = CreativeAgent(session_id=session_id, orchestrator=self)

        # State
        self.current_screen_context: bytes | None = None
        self.is_executing: bool = False
        self.pending_actions: asyncio.Queue = asyncio.Queue()
        self._recently_sent: set = set()

        # ADK runner
        self._adk_agent = self._build_adk_agent()
        self._runner = InMemoryRunner(agent=self._adk_agent, app_name="PRISM")

        logger.info(f"PRISM Orchestrator initialized: {session_id}")

    # ── ADK Agent Definition ────────────────────────────────────────────────────
    def _build_adk_agent(self) -> Agent:
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

        from google.adk.tools import FunctionTool

        async def analyze_screen(description: str) -> dict:
            """Analyze the current screen and extract actionable information."""
            return await self.vision_agent.analyze_current_screen(description)

        async def generate_creative_brief(prompt: str, context: str) -> dict:
            """Generate a multimodal creative brief with text, image prompts, and actions."""
            return await self.creative_agent.generate_brief(prompt, context)

        async def execute_ui_action(action_type: str, target: str, value: str = "") -> dict:
            """
            Execute a UI action on the user's screen using desktop automation.

            action_type options:
            - click: click at coordinates or named position e.g. "960,540" or "search bar"
            - type: type text into the currently focused element (set value=text to type)
            - find_and_click: find UI element by description and click it
            - find_and_type: find element by description, click it, then type value into it
            - hotkey: press keyboard shortcut e.g. target="ctrl+t" for new tab
            - navigate: open a URL in the browser e.g. target="https://gemini.google.com"
            - scroll: scroll at a position
            - screenshot: take a screenshot

            Examples:
            - Open Gemini: action_type="navigate", target="https://gemini.google.com"
            - Click chat input: action_type="find_and_click", target="chat input box"
            - Type message: action_type="type", value="What is the weather today?"
            - Send message: action_type="hotkey", target="enter"
            - Do it all at once: action_type="find_and_type", target="chat input", value="Hello Gemini"
            """
            result = await desktop.execute(action_type, target, value)
            # Also notify frontend of the action taken
            await self._send({
                "type": "action_executed",
                "action_type": action_type,
                "target": target,
                "value": value,
                "result": result,
            })
            return result

        async def speak_to_user(message: str, emotion: str = "neutral") -> dict:
            """Send a spoken response to the user."""
            return await self.voice_agent.speak(message, emotion)

        async def recall_context(query: str) -> dict:
            """Recall relevant past context from this session."""
            return await self.memory.recall(query)

        return Agent(
            name="PRISM",
            model="gemini-2.5-flash",
            description=(
                "PRISM is an ambient intelligence agent. It sees the user's screen, "
                "hears their voice, creates rich multimedia content, and takes actions "
                "on their behalf. It operates in a continuous loop: SEE → UNDERSTAND → CREATE → ACT."
            ),
            instruction="""
You are PRISM, an ambient AI agent. You have four superpowers:

1. HEAR: You listen to the user in real-time and understand their intent.
2. SEE: You can see the user's screen — their open apps, browser tabs, documents.
3. CREATE: You generate rich interleaved output — narration, images, plans.
4. ACT: You control the user's screen directly using desktop automation.

When the user asks you to interact with something on screen:
- First use analyze_screen to understand what is visible
- Then use execute_ui_action to perform the action

Common action patterns:
- "Open Google Gemini" → execute_ui_action(action_type="navigate", target="https://gemini.google.com")
- "Type X in the chat" → execute_ui_action(action_type="find_and_type", target="chat input", value="X")
- "Press Enter" → execute_ui_action(action_type="hotkey", target="enter")
- "Open a new tab" → execute_ui_action(action_type="hotkey", target="ctrl+t")
- "Click the search bar" → execute_ui_action(action_type="find_and_click", target="search bar")

Always narrate what you are doing. If the user interrupts, STOP immediately and re-plan.
Be warm, efficient, and always explain before you execute.
            """,
            tools=[
                FunctionTool(analyze_screen),
                FunctionTool(generate_creative_brief),
                FunctionTool(execute_ui_action),
                FunctionTool(speak_to_user),
                FunctionTool(recall_context),
            ],
        )

    # ── Connection Management ───────────────────────────────────────────────────
    async def on_connect(self, websocket: WebSocket):
        self.websocket = websocket
        await self.voice_agent.initialize()

        await self._runner.session_service.create_session(
            app_name="PRISM",
            user_id=self.session_id,
            session_id=self.session_id,
        )

        desktop_status = "Desktop control enabled ✅" if desktop.is_available() \
            else "Desktop control unavailable — run: pip install pyautogui"

        await self._send({
            "type": "status",
            "status": "connected",
            "message": f"PRISM is ready. {desktop_status}",
        })

    async def on_disconnect(self):
        await self.voice_agent.cleanup()
        self.websocket = None

    def set_action_socket(self, websocket: WebSocket):
        self.action_socket = websocket

    # ── Input Handlers ──────────────────────────────────────────────────────────
    async def handle_audio(self, audio_bytes: bytes):
        transcript = await self.voice_agent.process_audio_chunk(audio_bytes)
        if transcript:
            self._recently_sent.clear()
            await self.memory.add_user_message(transcript)
            await self._run_agent_loop(transcript)

    async def handle_screen_frame(self, frame_bytes: bytes):
        self.current_screen_context = frame_bytes
        await self.vision_agent.update_frame(frame_bytes)

    async def handle_interrupt(self, text: str = ""):
        logger.info(f"Interrupt received: {text}")
        self.is_executing = False
        while not self.pending_actions.empty():
            self.pending_actions.get_nowait()
        await self._send({"type": "status", "status": "interrupted"})
        if text:
            await self.handle_text(text)

    async def handle_text(self, text: str):
        self._recently_sent.clear()
        await self.memory.add_user_message(text)
        await self._run_agent_loop(text)

    async def handle_action_result(self, result: dict):
        action_id = result.get("action_id")
        logger.info(f"Action {action_id} result: {result.get('success')}")
        self.pending_actions.put_nowait(result)

    # ── Core Agent Loop ─────────────────────────────────────────────────────────
    async def _run_agent_loop(self, user_input: str):
        try:
            from google.genai import types as genai_types

            context_text = user_input
            if self.current_screen_context:
                screen_summary = await self.vision_agent.get_screen_summary()
                context_text = f"{user_input}\n\n[Screen Context: {screen_summary}]"

            new_message = genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=context_text)]
            )

            async for event in self._runner.run_async(
                user_id=self.session_id,
                session_id=self.session_id,
                new_message=new_message,
            ):
                await self._handle_adk_event(event)

        except Exception as e:
            logger.error(f"Agent loop error: {e}", exc_info=True)
            await self._send({"type": "error", "message": f"Agent error: {str(e)}"})

    async def _handle_adk_event(self, event):
        if hasattr(event, "is_final_response") and not event.is_final_response():
            return
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    await self._send({"type": "voice_response", "text": part.text})
                    await self.memory.add_assistant_message(part.text)

    # ── Action Dispatcher (browser-side fallback) ───────────────────────────────
    async def _dispatch_action(self, action_type: str, target: str, value: str = "") -> dict:
        """Fallback browser-side action dispatcher via WebSocket."""
        if not self.action_socket:
            return {"success": False, "error": "No action socket connected"}

        import uuid
        action_id = str(uuid.uuid4())[:8]
        await self.action_socket.send_json({
            "type": "action",
            "action_id": action_id,
            "action_type": action_type,
            "target": target,
            "value": value,
        })
        self.is_executing = True
        try:
            result = await asyncio.wait_for(self.pending_actions.get(), timeout=10.0)
            return result
        except asyncio.TimeoutError:
            return {"success": False, "error": "Action timed out"}
        finally:
            self.is_executing = False

    # ── Utility ─────────────────────────────────────────────────────────────────
    async def _send(self, message: dict):
        if self.websocket:
            try:
                if message.get("type") == "voice_response":
                    text = message.get("text", "")
                    if text in self._recently_sent:
                        return
                    self._recently_sent.add(text)
                    if len(self._recently_sent) > 10:
                        self._recently_sent.pop()
                await self.websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")