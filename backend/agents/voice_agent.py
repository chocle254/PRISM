"""
Voice Agent
───────────
Real-time voice interaction using Gemini Live API.
Handles speech-to-text, text-to-speech, interruptions, and emotional tone.
"""

import asyncio
import base64
import io
import logging
import os
from typing import TYPE_CHECKING, AsyncGenerator

import google.generativeai as genai
from google.genai import types as genai_types

if TYPE_CHECKING:
    from agents.orchestrator import PRISMOrchestrator

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


class VoiceAgent:
    """
    Manages all real-time audio I/O for PRISM.
    
    - Streams audio to Gemini Live API
    - Receives transcriptions in real-time
    - Generates spoken responses with emotional tone
    - Handles turn-taking and interruptions
    """

    VOICE_MAP = {
        "neutral": "Aoede",
        "excited": "Charon",
        "calm": "Kore",
        "authoritative": "Fenrir",
    }

    def __init__(self, session_id: str, orchestrator: "PRISMOrchestrator"):
        self.session_id = session_id
        self.orchestrator = orchestrator
        self.live_session = None
        self.audio_buffer = io.BytesIO()
        self.is_speaking = False
        self.current_transcript = ""
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._client = None

    async def initialize(self):
        """Set up Gemini Live API session."""
        try:
            self._client = genai.Client(api_key=GEMINI_API_KEY)
            logger.info("Voice agent initialized")
        except Exception as e:
            logger.error(f"Voice agent init error: {e}")

    async def cleanup(self):
        """Clean up resources."""
        if self.live_session:
            try:
                await self.live_session.close()
            except Exception:
                pass
        logger.info(f"Voice agent cleaned up: {self.session_id}")

    async def process_audio_chunk(self, audio_bytes: bytes) -> str | None:
        """
        Process an incoming audio chunk.
        Returns transcript if a complete utterance is detected.
        """
        try:
            # In a real implementation this streams to Gemini Live API
            # and returns partial/final transcripts
            transcript = await self._transcribe_audio(audio_bytes)
            if transcript:
                self.current_transcript += " " + transcript
                return transcript
        except Exception as e:
            logger.error(f"Audio processing error: {e}")
        return None

    async def _transcribe_audio(self, audio_bytes: bytes) -> str | None:
        """Send audio to Gemini Live API and get transcription."""
        if not self._client:
            return None

        try:
            # Use Gemini's audio understanding capability
            audio_part = genai_types.Part(
                inline_data=genai_types.Blob(
                    mime_type="audio/webm",
                    data=audio_bytes,
                )
            )

            # For streaming transcription with Live API
            config = genai_types.LiveConnectConfig(
                response_modalities=["TEXT"],
                speech_config=genai_types.SpeechConfig(
                    voice_config=genai_types.VoiceConfig(
                        prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                            voice_name=self.VOICE_MAP["neutral"]
                        )
                    )
                ),
                system_instruction="Transcribe the audio accurately. Return only the transcription text.",
            )

            # Stream transcription (simplified — real impl uses async context manager)
            async with self._client.aio.live.connect(
                model="gemini-2.0-flash-live-001",
                config=config,
            ) as session:
                await session.send(audio=audio_bytes, end_of_turn=True)
                full_text = ""
                async for response in session.receive():
                    if response.text:
                        full_text += response.text
                return full_text.strip() or None

        except Exception as e:
            logger.debug(f"Transcription error (expected in dev): {e}")
            return None

    async def speak(self, message: str, emotion: str = "neutral") -> dict:
        """
        Convert text to speech and send audio to client.
        Returns success status.
        """
        if not self._client:
            # Fallback: send text for client-side TTS
            await self.orchestrator._send({
                "type": "voice_response",
                "text": message,
                "emotion": emotion,
                "audio": None,
            })
            return {"success": True, "method": "client_tts"}

        try:
            voice_name = self.VOICE_MAP.get(emotion, self.VOICE_MAP["neutral"])
            config = genai_types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                speech_config=genai_types.SpeechConfig(
                    voice_config=genai_types.VoiceConfig(
                        prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
            )

            audio_chunks = []
            async with self._client.aio.live.connect(
                model="gemini-2.0-flash-live-001",
                config=config,
            ) as session:
                await session.send(message, end_of_turn=True)
                async for response in session.receive():
                    if response.data:
                        audio_chunks.append(response.data)

            if audio_chunks:
                combined_audio = b"".join(audio_chunks)
                audio_b64 = base64.b64encode(combined_audio).decode()
                await self.orchestrator._send({
                    "type": "voice_response",
                    "text": message,
                    "emotion": emotion,
                    "audio": audio_b64,
                    "audio_format": "pcm_16000",
                })
                return {"success": True, "method": "live_api"}

        except Exception as e:
            logger.error(f"TTS error: {e}")
            # Fallback to text
            await self.orchestrator._send({
                "type": "voice_response",
                "text": message,
                "emotion": emotion,
                "audio": None,
            })
            return {"success": True, "method": "fallback_text"}

        return {"success": False}

    async def stream_live_response(
        self, prompt: str, screen_context: str | None = None
    ) -> AsyncGenerator[dict, None]:
        """
        Run a full live conversation turn with Gemini Live API.
        Yields chunks suitable for the frontend.
        """
        if not self._client:
            yield {"type": "voice_response", "text": "Voice API not initialized"}
            return

        system = (
            "You are PRISM, a warm and capable AI assistant. "
            "You see the user's screen and help them accomplish tasks. "
            "Be concise and natural in speech."
        )
        if screen_context:
            system += f"\n\nCurrent screen context: {screen_context}"

        config = genai_types.LiveConnectConfig(
            response_modalities=["AUDIO", "TEXT"],
            system_instruction=system,
            speech_config=genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                        voice_name=self.VOICE_MAP["neutral"]
                    )
                )
            ),
        )

        try:
            async with self._client.aio.live.connect(
                model="gemini-2.0-flash-live-001",
                config=config,
            ) as session:
                await session.send(prompt, end_of_turn=True)
                async for response in session.receive():
                    if response.text:
                        yield {"type": "voice_response", "text": response.text}
                    if response.data:
                        yield {
                            "type": "audio_chunk",
                            "audio": base64.b64encode(response.data).decode(),
                        }
        except Exception as e:
            logger.error(f"Live stream error: {e}")
            yield {"type": "error", "message": str(e)}
