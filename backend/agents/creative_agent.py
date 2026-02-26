"""
Creative Agent
──────────────
Generates rich interleaved multimodal output using Gemini's mixed-output capability.
Weaves together narration, images, diagrams, action plans, and structured content
in one cohesive stream — like a creative director thinking out loud.
"""

import asyncio
import base64
import json
import logging
import os
from typing import TYPE_CHECKING, AsyncGenerator

import google.generativeai as genai
from google.cloud import aiplatform
from vertexai.preview.vision_models import ImageGenerationModel

if TYPE_CHECKING:
    from agents.orchestrator import PRISMOrchestrator

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")


CREATIVE_BRIEF_SYSTEM = """
You are PRISM's Creative Director — a brilliant mind that thinks in multiple formats simultaneously.

When given a task, you produce a rich, interleaved creative brief that combines:
- 🗣️ Narrated explanations (conversational, warm)
- 🖼️ Image generation prompts (for Imagen, marked with [IMAGE: ...])
- 📊 Structured data (JSON blocks for UI rendering, marked with [DATA: ...])
- ✅ Action steps (executable steps, marked with [ACTION: ...])
- 💡 Insights and recommendations (marked with [INSIGHT: ...])

Format your output as a flowing stream where these elements are naturally interwoven.
Think like you're explaining AND creating AND planning simultaneously.

Example format:
"Let me build your brand story. I'm envisioning a warm, earthy aesthetic for your honey brand...

[IMAGE: A rustic honey jar with golden liquid, warm sunlight, wildflower background, photorealistic, luxury product photography]

Your brand voice should feel artisanal and authentic. Here's your Instagram caption:

[DATA: {"type": "social_post", "caption": "...", "hashtags": [...], "platform": "instagram"}]

Now let me plan the execution steps:

[ACTION: {"step": 1, "action": "navigate", "target": "https://canva.com", "description": "Open Canva to create your first post"}]"
"""


class CreativeAgent:
    """
    Generates rich interleaved multimodal content.
    
    Output stream contains mixed content types:
    - text: narrative explanations
    - image_prompt: trigger Imagen generation
    - data: structured JSON for UI components
    - action: UI automation step
    - insight: recommendations
    """

    def __init__(self, session_id: str, orchestrator: "PRISMOrchestrator"):
        self.session_id = session_id
        self.orchestrator = orchestrator
        self._model = None
        self._imagen_model = None
        self._initialize_models()

    def _initialize_models(self):
        """Initialize Gemini and Imagen models."""
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self._model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                system_instruction=CREATIVE_BRIEF_SYSTEM,
            )
            logger.info("Creative agent: Gemini model initialized")
        except Exception as e:
            logger.error(f"Gemini init error: {e}")

        try:
            if GCP_PROJECT:
                aiplatform.init(project=GCP_PROJECT, location=GCP_REGION)
                self._imagen_model = ImageGenerationModel.from_pretrained(
                    "imagen-3.0-generate-001"
                )
                logger.info("Creative agent: Imagen model initialized")
        except Exception as e:
            logger.warning(f"Imagen init (non-critical): {e}")

    async def stream_creative_output(
        self, prompt: str, screen_context: str | None = None
    ) -> AsyncGenerator[dict, None]:
        """
        Stream interleaved creative content.
        Parses special markers and yields typed chunks.
        """
        if not self._model:
            yield {"type": "text", "content": "Creative model not initialized"}
            return

        full_prompt = prompt
        if screen_context:
            full_prompt = f"Current screen context: {screen_context}\n\nUser request: {prompt}"

        try:
            response_stream = await self._model.generate_content_async(
                full_prompt,
                stream=True,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.8,
                    max_output_tokens=4096,
                ),
            )

            buffer = ""
            async for chunk in response_stream:
                if chunk.text:
                    buffer += chunk.text
                    # Parse and yield complete segments
                    async for parsed_chunk in self._parse_stream_buffer(buffer):
                        buffer = ""  # Clear processed buffer
                        yield parsed_chunk
                        # Also send to WebSocket
                        await self.orchestrator._send({
                            "type": "creative_chunk",
                            **parsed_chunk,
                        })

            # Flush remaining buffer
            if buffer.strip():
                yield {"type": "text", "content": buffer}
                await self.orchestrator._send({
                    "type": "creative_chunk",
                    "type_content": "text",
                    "content": buffer,
                })

        except Exception as e:
            logger.error(f"Creative stream error: {e}")
            yield {"type": "error", "content": str(e)}

    async def _parse_stream_buffer(self, buffer: str) -> AsyncGenerator[dict, None]:
        """
        Parse the streaming buffer for special markers and yield typed chunks.
        """
        import re

        # Look for complete special blocks
        patterns = {
            "image_prompt": r"\[IMAGE:\s*(.*?)\]",
            "data": r"\[DATA:\s*(\{.*?\})\]",
            "action": r"\[ACTION:\s*(\{.*?\})\]",
            "insight": r"\[INSIGHT:\s*(.*?)\]",
        }

        last_end = 0
        all_matches = []

        for chunk_type, pattern in patterns.items():
            for match in re.finditer(pattern, buffer, re.DOTALL):
                all_matches.append((match.start(), match.end(), chunk_type, match.group(1)))

        all_matches.sort(key=lambda x: x[0])

        for start, end, chunk_type, content in all_matches:
            # Yield any text before this marker
            if start > last_end:
                text_before = buffer[last_end:start].strip()
                if text_before:
                    yield {"type": "text", "content": text_before}

            # Yield the typed chunk
            if chunk_type == "image_prompt":
                image_data = await self._generate_image(content.strip())
                yield {
                    "type": "image",
                    "prompt": content.strip(),
                    "image_data": image_data,
                }
            elif chunk_type == "data":
                try:
                    yield {"type": "data", "content": json.loads(content.strip())}
                except json.JSONDecodeError:
                    yield {"type": "data", "content": content.strip()}
            elif chunk_type == "action":
                try:
                    yield {"type": "action", "content": json.loads(content.strip())}
                except json.JSONDecodeError:
                    yield {"type": "action", "content": content.strip()}
            elif chunk_type == "insight":
                yield {"type": "insight", "content": content.strip()}

            last_end = end

    async def generate_brief(self, prompt: str, context: str = "") -> dict:
        """
        Generate a complete creative brief (non-streaming).
        Returns a structured dict with all content types.
        """
        chunks = []
        async for chunk in self.stream_creative_output(prompt, context):
            chunks.append(chunk)

        return {
            "session_id": self.session_id,
            "prompt": prompt,
            "chunks": chunks,
            "text_summary": " ".join(
                c["content"] for c in chunks if c["type"] == "text"
            ),
            "actions": [c["content"] for c in chunks if c["type"] == "action"],
            "images": [c for c in chunks if c["type"] == "image"],
            "insights": [c["content"] for c in chunks if c["type"] == "insight"],
        }

    async def _generate_image(self, prompt: str) -> str | None:
        """
        Generate an image using Imagen 3 on Vertex AI.
        Returns base64-encoded image or None.
        """
        if not self._imagen_model:
            logger.warning("Imagen not available, skipping image generation")
            return None

        try:
            images = self._imagen_model.generate_images(
                prompt=prompt,
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_some",
            )

            if images and images[0]:
                image_bytes = images[0]._image_bytes
                return base64.b64encode(image_bytes).decode()

        except Exception as e:
            logger.error(f"Image generation error: {e}")

        return None

    async def generate_storyboard(self, project_description: str) -> list[dict]:
        """
        Generate a visual storyboard for a project.
        Returns a list of scenes with narration + image.
        """
        if not self._model:
            return []

        prompt = f"""
Create a 4-scene visual storyboard for this project: {project_description}

For each scene, provide:
[DATA: {{"scene": 1, "title": "...", "narration": "...", "image_prompt": "..."}}]

Generate exactly 4 scenes.
"""

        scenes = []
        async for chunk in self.stream_creative_output(prompt):
            if chunk["type"] == "data" and isinstance(chunk["content"], dict):
                scene = chunk["content"]
                if "image_prompt" in scene:
                    scene["image_data"] = await self._generate_image(scene["image_prompt"])
                scenes.append(scene)

        return scenes

    async def generate_launch_package(self, business_info: dict) -> dict:
        """
        Generate a complete product launch package:
        brand story + social posts + email + landing page copy.
        """
        prompt = f"""
Create a complete product launch package for:
Business: {business_info.get('name', 'Unknown')}
Product: {business_info.get('product', 'Unknown')}
Target audience: {business_info.get('audience', 'General')}
Brand values: {business_info.get('values', 'Quality, authenticity')}

Generate:
1. Brand story narrative
2. [IMAGE: Professional product photography style for {business_info.get('product', 'the product')}]
3. [DATA: {{"type": "instagram_post", "caption": "...", "hashtags": [...]}}]
4. [DATA: {{"type": "launch_email", "subject": "...", "body": "...", "cta": "..."}}]
5. [DATA: {{"type": "landing_page", "headline": "...", "subheadline": "...", "features": [...], "cta": "..."}}]
6. [ACTION: {{"step": 1, "action": "navigate", "target": "canva.com", "description": "Create social post"}}]
"""

        return await self.generate_brief(prompt)
