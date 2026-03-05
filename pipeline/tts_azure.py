"""
pipeline/tts_azure.py
=====================
Azure Speech Service TTS with voice cloning.
Reuses the voice profiles from video-language-update-cn-en project.
Generates audio with YOUR cloned voice (not generic TTS).
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

from .config import OUTPUT_DIR, AUDIO_DIR

# Load .env from current project (or fallback to video-language-update project)
_env_paths = [
    Path(__file__).resolve().parent.parent / ".env",  # 当前项目的 .env
    Path(__file__).resolve().parent.parent.parent / "video-language-update-cn-en" / ".env",  # 旧项目备用
]
for _env_path in _env_paths:
    if _env_path.exists():
        try:
            for line in open(_env_path, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass
        break  # 找到一个就够了

# ── Voice Profiles (from env or defaults) ───────
VOICE_PROFILES = {
    "zh": {
        "speaker_profile_id": os.environ.get("TTS_SPEAKER_ZH", ""),
        "carrier_voice": "zh-CN-Yunqi:DragonHDOmniLatestNeural",
    },
    "en": {
        "speaker_profile_id": os.environ.get("TTS_SPEAKER_EN", ""),
        "carrier_voice": "en-US-Andrew:DragonHDLatestNeural",
    },
}

# Azure Speech config
SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY", "")
SPEECH_REGION = os.environ.get("AZURE_SPEECH_REGION", "eastus")
SPEECH_RESOURCE_ID = os.environ.get("AZURE_SPEECH_RESOURCE_ID", "")


def _get_aad_token(resource="https://cognitiveservices.azure.com"):
    """Get AAD token via az CLI with caching."""
    cache = getattr(_get_aad_token, "_cache", None)
    if cache:
        token, expires = cache
        if time.time() < expires - 60:
            return token
    result = subprocess.run(
        ["az", "account", "get-access-token",
         "--resource", resource,
         "--query", "{accessToken:accessToken,expiresOn:expiresOn}",
         "-o", "json"],
        capture_output=True, text=True, check=True, shell=True,
    )
    data = json.loads(result.stdout)
    token = data["accessToken"]
    try:
        from datetime import datetime, timezone
        exp_str = data["expiresOn"]
        dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
        expires = dt.timestamp()
    except Exception:
        expires = time.time() + 3000
    _get_aad_token._cache = (token, expires)
    return token


def _make_speech_config():
    """Create SpeechConfig with AAD or key auth."""
    import azure.cognitiveservices.speech as speechsdk

    use_aad = not SPEECH_KEY
    if not use_aad:
        # Test if key works
        try:
            import httpx
            url = f"https://{SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
            resp = httpx.post(url, headers={"Ocp-Apim-Subscription-Key": SPEECH_KEY, "Content-Length": "0"}, timeout=5)
            if resp.status_code in (401, 403):
                use_aad = True
        except Exception:
            use_aad = True

    if use_aad:
        token = _get_aad_token()
        sc = speechsdk.SpeechConfig(
            auth_token=f"aad#{SPEECH_RESOURCE_ID}#{token}",
            region=SPEECH_REGION,
        )
    else:
        sc = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    return sc


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _detect_language(text: str) -> str:
    cn_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total = len(text.strip())
    if total == 0:
        return "en"
    return "zh" if cn_chars / total > 0.3 else "en"


def tts_clone_voice(text: str, output_path: str, language: str = "auto") -> str | None:
    """
    Generate TTS audio using YOUR cloned voice via Azure Speech Service.

    Args:
        text: Text to speak
        output_path: Where to save the audio file (.wav or .mp3)
        language: "zh", "en", or "auto" (auto-detect)

    Returns:
        output_path if successful, None if failed
    """
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        print("  ⚠️ azure-cognitiveservices-speech 未安装")
        print("     请运行: pip install azure-cognitiveservices-speech")
        return None

    # Auto-detect language
    if language == "auto":
        language = _detect_language(text)

    profile = VOICE_PROFILES.get(language, VOICE_PROFILES["zh"])
    speaker_id = profile["speaker_profile_id"]
    carrier = profile["carrier_voice"]

    # Build SSML with voice cloning
    escaped = _escape_xml(text)
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">'
        f'<voice name="{carrier}">'
        f'<mstts:ttsembedding speakerProfileId="{speaker_id}">'
        f'{escaped}'
        '</mstts:ttsembedding>'
        '</voice></speak>'
    )

    try:
        print(f"  🎤 Azure TTS (你的声音): lang={language}, text={text[:40]}...")
        sc = _make_speech_config()
        sc.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
        )
        synth = speechsdk.SpeechSynthesizer(speech_config=sc, audio_config=None)
        result = synth.speak_ssml_async(ssml).get()

        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            detail = result.cancellation_details
            print(f"  ❌ TTS 失败: {detail.reason} – {detail.error_details}")
            return None

        # Save
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        if output_path.endswith(".wav"):
            with open(output_path, "wb") as f:
                f.write(result.audio_data)
        else:
            # Save as wav first, then convert to mp3 via ffmpeg
            wav_tmp = output_path.rsplit(".", 1)[0] + "_tmp.wav"
            with open(wav_tmp, "wb") as f:
                f.write(result.audio_data)
            # Convert to mp3
            from .config import FFMPEG_BIN
            subprocess.run(
                [FFMPEG_BIN, "-y", "-i", wav_tmp, "-b:a", "128k", output_path],
                capture_output=True, timeout=30,
            )
            os.remove(wav_tmp)

        print(f"  ✅ TTS (你的声音): {output_path}")
        return output_path

    except Exception as e:
        print(f"  ❌ Azure TTS 失败: {e}")
        return None
