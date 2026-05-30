"""
PRISM Orchestrator
──────────────────
Master ADK agent that coordinates Voice, Vision, and Creative sub-agents.
Built on Google Agent Development Kit (ADK).
"""

import asyncio
import os
import logging
import json

from fastapi import WebSocket
from groq import AsyncGroq

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
        self._groq = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))
        self._tools = self._build_tools()
        self._conversation: list = []

        logger.info(f"PRISM Orchestrator initialized: {session_id}")

    # ── ADK Agent Definition ────────────────────────────────────────────────────
    # ── Groq Tools Definition ───────────────────────────────────────────────────
    def _build_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "analyze_screen",
                    "description": "Analyze the current screen and extract actionable information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string", "description": "What to look for on screen"}
                        },
                        "required": ["description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_ui_action",
                    "description": "Execute a UI action on the user's screen. Always open a new tab before navigating anywhere.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action_type": {
                                "type": "string",
                                "enum": ["click", "type", "hotkey", "navigate", "scroll"],
                                "description": "Type of action to perform"
                            },
                            "target": {"type": "string", "description": "Target element or URL"},
                            "value": {"type": "string", "description": "Text to type (only for type and find_and_type actions)"}
                        },
                        "required": ["action_type", "target"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "recall_context",
                    "description": "Recall relevant past context from this session.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "What to recall"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    # ── Connection Management ───────────────────────────────────────────────────
    # ── Connection Management ───────────────────────────────────────────────────
    async def on_connect(self, websocket: WebSocket):
        self.websocket = websocket
        await self.voice_agent.initialize()

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
    # ── Core Agent Loop ─────────────────────────────────────────────────────────
    async def _run_agent_loop(self, user_input: str):
        try:
            screen_summary = await self.vision_agent.get_screen_summary()

            system_prompt = """You are PRISM, a powerful AI agent that controls the user's computer completely.

You MUST call execute_ui_action multiple times to complete any task. Never respond with just text — always take action.

For ANY search or browse task follow these EXACT steps by calling execute_ui_action each time:
STEP 1: action_type="hotkey", target="ctrl+t" → open new tab
STEP 2: action_type="navigate", target="https://www.google.com" → go to google
STEP 3: action_type="find_and_type", target="search box", value="<search terms>" → type the search
STEP 4: action_type="hotkey", target="enter" → submit search
STEP 5: action_type="find_and_click", target="first result" → click the best result
STEP 6: Tell the user what you found

For news: use "https://news.google.com" in STEP 2
For videos: use "https://www.youtube.com" in STEP 2

NEVER stop after just one action. ALWAYS complete all steps.
NEVER say "I'll search for that" and stop — actually do it.

Current screen: """ + screen_summary

            self._conversation.append({"role": "user", "content": user_input})

            messages = [{"role": "system", "content": system_prompt}] + self._conversation

            while True:
                response = await self._groq.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    tools=self._tools,
                    tool_choice="auto",
                    max_tokens=2048,
                )

                msg = response.choices[0].message

                if msg.tool_calls:
                    messages.append(msg)
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)

                        # Narrate what we're doing
                        action_type = tool_args.get("action_type", "")
                        target = tool_args.get("target", "")
                        value = tool_args.get("value", "")
                        narration = self._narrate_action(action_type, target, value)
                        if narration:
                            await self._send({"type": "voice_response", "text": narration})

                        result = await self._execute_tool(tool_name, tool_args)

                        # Wait for page to load after navigation
                        if action_type in ["navigate", "hotkey"] and target in ["enter", "ctrl+t"]:
                            import asyncio
                            await asyncio.sleep(2)

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result),
                        })
                else:
                    final_text = msg.content
                    if final_text:
                        self._conversation.append({"role": "assistant", "content": final_text})
                        await self._send({"type": "voice_response", "text": final_text})
                        await self.memory.add_assistant_message(final_text)
                    break

        except Exception as e:
            logger.error(f"Agent loop error: {e}", exc_info=True)
            await self._send({"type": "error", "message": f"Agent error: {str(e)}"})

    async def _execute_tool(self, name: str, args: dict) -> dict:
        """Execute a tool call from Groq."""
        try:
            if name == "analyze_screen":
                return await self.vision_agent.analyze_current_screen(args.get("description", ""))

            elif name == "execute_ui_action":
                action_type = args.get("action_type")
                target = args.get("target", "")
                value = args.get("value") or ""

                # Always open new tab before navigating
                if action_type == "navigate":
                    await desktop.execute("hotkey", "ctrl+t")
                    import asyncio
                    await asyncio.sleep(0.5)

                result = await desktop.execute(action_type, target, value)
                await self._send({
                    "type": "action_executed",
                    "action_type": action_type,
                    "target": target,
                    "value": value,
                    "result": result,
                })
                return result

            elif name == "recall_context":
                return await self.memory.recall(args.get("query", ""))

            return {"error": f"Unknown tool: {name}"}

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"error": str(e)}

    # ── Action Dispatcher (browser-side fallback) ───────────────────────────────
    def _narrate_action(self, action_type: str, target: str, value: str) -> str | None:
        """Generate a narration for each action so user knows what's happening."""
        if action_type == "hotkey" and target == "ctrl+t":
            return "Opening a new tab..."
        if action_type == "navigate":
            return f"Navigating to {target}..."
        if action_type == "find_and_type":
            return f"Searching for {value}..."
        if action_type == "hotkey" and target == "enter":
            return "Searching..."
        if action_type == "find_and_click":
            return "Opening the best result..."
        return None

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