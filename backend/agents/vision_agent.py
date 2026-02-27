"""
Vision Agent
────────────
Interprets screenshots and screen recordings using Gemini multimodal.
Extracts UI elements, text, context, and generates executable action plans.
"""

import json
import logging
import os
from typing import TYPE_CHECKING

from google import genai
from google.genai import types as genai_types

if TYPE_CHECKING:
    from agents.orchestrator import PRISMOrchestrator

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"

SCREEN_ANALYSIS_PROMPT = """
You are a precise screen analysis AI. Analyze this screenshot and return a JSON object with:

{
  "app_detected": "name of the app/website visible",
  "page_type": "what kind of page this is (e.g. email composer, spreadsheet, form, browser)",
  "key_elements": [
    {
      "type": "button|input|text|image|link|dropdown",
      "label": "visible text or description",
      "position": "top-left|top-right|center|bottom etc.",
      "actionable": true/false
    }
  ],
  "current_content": "brief summary of what content is visible",
  "user_likely_doing": "inferred task the user is performing",
  "suggested_next_actions": ["action1", "action2"],
  "warnings": ["any issues noticed, e.g. unsaved changes, error messages"]
}

Return ONLY valid JSON, no markdown.
"""

ACTION_PLAN_PROMPT = """
You are a UI automation expert. Given:
- User intent: {intent}
- Current screen analysis: {screen_analysis}
- App detected: {app}

Generate a step-by-step action plan as JSON:
{{
  "plan_summary": "one sentence description of what will happen",
  "confidence": 0.0-1.0,
  "steps": [
    {{
      "step": 1,
      "action": "click|type|navigate|scroll|select|press_key",
      "target_description": "describe what to click/interact with visually",
      "value": "text to type or key to press (if applicable)",
      "wait_for": "what to wait for after this action",
      "verification": "how to verify this step succeeded"
    }}
  ],
  "fallback": "what to do if the plan fails"
}}

Return ONLY valid JSON, no markdown.
"""


class VisionAgent:
    """
    Sees and interprets the user's screen using Gemini multimodal.

    Capabilities:
    - Screenshot analysis (UI elements, text, app detection)
    - Action plan generation from visual context
    - Change detection between frames
    - Element localization for automation
    """

    def __init__(self, session_id: str, orchestrator: "PRISMOrchestrator"):
        self.session_id = session_id
        self.orchestrator = orchestrator
        self.current_frame: bytes | None = None
        self.previous_frame: bytes | None = None
        self.current_analysis: dict | None = None
        self._client: genai.Client | None = None
        self._initialize_model()

    def _initialize_model(self):
        try:
            self._client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
            logger.info("Vision model initialized")
        except Exception as e:
            logger.error(f"Vision model init error: {e}")

    # ── Frame Management ────────────────────────────────────────────────────────
    async def update_frame(self, frame_bytes: bytes):
        """Update the current screen frame and invalidate cached analysis."""
        self.previous_frame = self.current_frame
        self.current_frame = frame_bytes
        self.current_analysis = None

    # ── Screen Analysis ─────────────────────────────────────────────────────────
    async def analyze_current_screen(self, user_intent: str = "") -> dict:
        """
        Analyze the current screen frame with Gemini vision.
        Returns structured screen analysis as a dict.
        """
        if not self.current_frame:
            return {"error": "No screen frame available", "app_detected": "unknown"}

        # Return cached analysis if no new intent
        if self.current_analysis and not user_intent:
            return self.current_analysis

        if not self._client:
            return {"error": "Vision model not initialized"}

        try:
            prompt = SCREEN_ANALYSIS_PROMPT
            if user_intent:
                prompt += f"\n\nUser's current intent: {user_intent}"

            response = await self._client.aio.models.generate_content(
                model=MODEL,
                contents=[
                    genai_types.Part.from_bytes(
                        data=self.current_frame,
                        mime_type="image/jpeg",
                    ),
                    genai_types.Part.from_text(text=prompt),
                ],
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            analysis = json.loads(response.text)
            self.current_analysis = analysis

            await self.orchestrator._send({
                "type": "screen_analysis",
                "analysis": analysis,
            })

            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in screen analysis: {e}")
            return {"error": "Analysis parse failed"}
        except Exception as e:
            logger.error(f"Screen analysis error: {e}")
            return {"error": str(e)}

    # ── Action Plan ─────────────────────────────────────────────────────────────
    async def generate_action_plan(self, user_intent: str) -> dict:
        """
        Generate a UI automation action plan based on screen + user intent.
        """
        if not self._client:
            return {"error": "Vision model not initialized"}

        screen_analysis = await self.analyze_current_screen(user_intent)
        app = screen_analysis.get("app_detected", "unknown app")

        prompt = ACTION_PLAN_PROMPT.format(
            intent=user_intent,
            screen_analysis=json.dumps(screen_analysis, indent=2),
            app=app,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=MODEL,
                contents=[genai_types.Part.from_text(text=prompt)],
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )

            plan = json.loads(response.text)

            await self.orchestrator._send({
                "type": "action_plan",
                "plan": plan,
            })

            return plan

        except Exception as e:
            logger.error(f"Action plan generation error: {e}")
            return {"error": str(e), "steps": []}

    # ── Change Detection ────────────────────────────────────────────────────────
    async def detect_changes(self) -> dict:
        """
        Compare current and previous frames to detect what changed on screen.
        Useful for verifying that an action succeeded.
        """
        if not self.current_frame or not self.previous_frame:
            return {"changed": False, "description": "Insufficient frames"}

        if not self._client:
            return {"changed": False}

        try:
            prompt = """Compare these two screenshots (BEFORE and AFTER an action).
Return JSON only:
{
  "changed": true/false,
  "changes": ["list of what changed"],
  "success_indicators": ["any success messages or new content visible"]
}"""

            response = await self._client.aio.models.generate_content(
                model=MODEL,
                contents=[
                    genai_types.Part.from_text(text=prompt),
                    genai_types.Part.from_text(text="BEFORE:"),
                    genai_types.Part.from_bytes(
                        data=self.previous_frame,
                        mime_type="image/jpeg",
                    ),
                    genai_types.Part.from_text(text="AFTER:"),
                    genai_types.Part.from_bytes(
                        data=self.current_frame,
                        mime_type="image/jpeg",
                    ),
                ],
                config=genai_types.GenerateContentConfig(temperature=0.1),
            )

            return json.loads(response.text)

        except Exception as e:
            logger.error(f"Change detection error: {e}")
            return {"changed": False, "error": str(e)}

    # ── Screen Summary ──────────────────────────────────────────────────────────
    async def get_screen_summary(self) -> str:
        """Get a brief text summary of the current screen state."""
        if not self.current_frame:
            return "No screen visible"

        analysis = await self.analyze_current_screen()
        if "error" in analysis:
            return "Screen analysis unavailable"

        app = analysis.get("app_detected", "unknown app")
        page = analysis.get("page_type", "unknown page")
        content = analysis.get("current_content", "")
        doing = analysis.get("user_likely_doing", "")

        return f"User is on {app} ({page}). {content}. They appear to be {doing}."

    # ── Element Locator ─────────────────────────────────────────────────────────
    async def locate_element(self, description: str) -> dict:
        """
        Find a specific UI element on screen by description.
        Returns position info for automation.
        """
        if not self.current_frame or not self._client:
            return {"found": False}

        try:
            prompt = f"""Find the UI element described as: "{description}"
Return JSON only:
{{
  "found": true/false,
  "element_type": "button/input/link/etc",
  "visible_text": "text on the element",
  "relative_position": "describe position e.g. top-center, left sidebar",
  "confidence": 0.0-1.0
}}"""

            response = await self._client.aio.models.generate_content(
                model=MODEL,
                contents=[
                    genai_types.Part.from_bytes(
                        data=self.current_frame,
                        mime_type="image/jpeg",
                    ),
                    genai_types.Part.from_text(text=prompt),
                ],
                config=genai_types.GenerateContentConfig(temperature=0.1),
            )

            return json.loads(response.text)

        except Exception as e:
            logger.error(f"Element location error: {e}")
            return {"found": False, "error": str(e)}