"""
Vision Agent
────────────
Interprets screenshots and screen recordings using Gemini multimodal.
Extracts UI elements, text, context, and generates executable action plans.
"""

import base64
import json
import logging
import os
from typing import TYPE_CHECKING

import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory

if TYPE_CHECKING:
    from agents.orchestrator import PRISMOrchestrator

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


SCREEN_ANALYSIS_PROMPT = """
You are a precise screen analysis AI. Analyze this screenshot and return a JSON object with:

{
  "app_detected": "name of the app/website visible",
  "page_type": "what kind of page this is (e.g. email composer, spreadsheet, form, browser, etc.)",
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
{
  "plan_summary": "one sentence description of what will happen",
  "confidence": 0.0-1.0,
  "steps": [
    {
      "step": 1,
      "action": "click|type|navigate|scroll|select|press_key",
      "target_description": "describe what to click/interact with visually",
      "value": "text to type or key to press (if applicable)",
      "wait_for": "what to wait for after this action",
      "verification": "how to verify this step succeeded"
    }
  ],
  "fallback": "what to do if the plan fails"
}

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
        self._model = None
        self._initialize_model()

    def _initialize_model(self):
        """Initialize Gemini vision model."""
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self._model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                },
            )
            logger.info("Vision model initialized")
        except Exception as e:
            logger.error(f"Vision model init error: {e}")

    async def update_frame(self, frame_bytes: bytes):
        """Update the current screen frame."""
        self.previous_frame = self.current_frame
        self.current_frame = frame_bytes
        # Invalidate cached analysis
        self.current_analysis = None

    async def analyze_current_screen(self, user_intent: str = "") -> dict:
        """
        Analyze the current screen frame with Gemini vision.
        Returns structured screen analysis.
        """
        if not self.current_frame:
            return {"error": "No screen frame available", "app_detected": "unknown"}

        if self.current_analysis and not user_intent:
            return self.current_analysis

        if not self._model:
            return {"error": "Vision model not initialized"}

        try:
            image_part = {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(self.current_frame).decode(),
            }

            prompt = SCREEN_ANALYSIS_PROMPT
            if user_intent:
                prompt += f"\n\nUser's current intent: {user_intent}"

            response = await self._model.generate_content_async(
                [prompt, image_part],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            analysis = json.loads(response.text)
            self.current_analysis = analysis

            # Notify orchestrator of screen update
            await self.orchestrator._send({
                "type": "screen_analysis",
                "analysis": analysis,
            })

            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in screen analysis: {e}")
            return {"error": "Analysis parse failed", "raw": response.text[:200]}
        except Exception as e:
            logger.error(f"Screen analysis error: {e}")
            return {"error": str(e)}

    async def generate_action_plan(self, user_intent: str) -> dict:
        """
        Generate a UI automation action plan based on screen + user intent.
        """
        if not self._model:
            return {"error": "Vision model not initialized"}

        screen_analysis = await self.analyze_current_screen(user_intent)
        app = screen_analysis.get("app_detected", "unknown app")

        prompt = ACTION_PLAN_PROMPT.format(
            intent=user_intent,
            screen_analysis=json.dumps(screen_analysis, indent=2),
            app=app,
        )

        try:
            response = await self._model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
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

    async def detect_changes(self) -> dict:
        """
        Compare current and previous frames to detect what changed on screen.
        Useful for verifying action success.
        """
        if not self.current_frame or not self.previous_frame:
            return {"changed": False, "description": "Insufficient frames"}

        if not self._model:
            return {"changed": False}

        try:
            prev_part = {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(self.previous_frame).decode(),
            }
            curr_part = {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(self.current_frame).decode(),
            }

            prompt = """Compare these two screenshots (before and after).
Return JSON: {"changed": bool, "changes": ["list of what changed"], "success_indicators": ["any success messages or new content"]}
Only return valid JSON."""

            response = await self._model.generate_content_async(
                [prompt, "BEFORE:", prev_part, "AFTER:", curr_part],
                generation_config=genai.types.GenerationConfig(temperature=0.1),
            )

            return json.loads(response.text)

        except Exception as e:
            logger.error(f"Change detection error: {e}")
            return {"changed": False, "error": str(e)}

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

    async def locate_element(self, description: str) -> dict:
        """
        Find a specific UI element on screen by description.
        Returns position info for automation.
        """
        if not self.current_frame or not self._model:
            return {"found": False}

        try:
            image_part = {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(self.current_frame).decode(),
            }

            prompt = f"""Find the UI element described as: "{description}"
Return JSON: {{
  "found": bool,
  "element_type": "button/input/link/etc",
  "visible_text": "text on the element",
  "relative_position": "describe position (e.g. top-center, left sidebar)",
  "css_selector_hint": "if detectable",
  "confidence": 0.0-1.0
}}
Only return valid JSON."""

            response = await self._model.generate_content_async(
                [prompt, image_part],
                generation_config=genai.types.GenerationConfig(temperature=0.1),
            )

            return json.loads(response.text)

        except Exception as e:
            logger.error(f"Element location error: {e}")
            return {"found": False, "error": str(e)}
