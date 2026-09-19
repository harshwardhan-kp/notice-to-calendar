"""Strands agent that extracts calendar events from a college notice image.

One vision-capable Bedrock call per notice, no OCR layer: the model reads the
image directly and returns structured events as JSON.
"""
import datetime
import json
import re

from strands import Agent
from strands.models import BedrockModel

SYSTEM_PROMPT = """You read photos of Indian college notices and extract every dated \
commitment as a calendar event.

Today's date is {today}. Use it to resolve relative dates like "next Friday" or \
"within 3 days of this notice" into an absolute YYYY-MM-DD date.

Indian date convention: DD/MM/YYYY and DD-MM-YYYY are day-first, never month-first. \
04/10/2026 means 4 October 2026, not April 10.

A notice may contain zero, one, or several dated commitments (exam dates, fee \
deadlines, submission deadlines, event dates, meeting times). Extract each as its \
own event. Ignore the notice's own issue date and any reference/circular number — \
those are not events.

Return a JSON array only. No prose, no markdown, no code fences, just the array \
(an empty array [] if there are no dates). Each element has exactly these fields:

{{
  "title": string, short and specific (e.g. "Mid-semester exam: Data Structures"),
  "date": "YYYY-MM-DD",
  "startTime": "HH:MM" in 24-hour time, or null if no time is given,
  "endTime": "HH:MM" in 24-hour time, or null if no end time is given,
  "venue": string or null,
  "action": string or null, a short note on what to bring or do,
  "confidence": "high" or "low"
}}

Mark "confidence": "low" on anything you are guessing at — a smudged date, an \
ambiguous year, handwriting you are inferring rather than reading clearly.
"""

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _build_agent(model_id: str, region: str, today: str) -> Agent:
    model = BedrockModel(model_id=model_id, region_name=region)
    return Agent(model=model, system_prompt=SYSTEM_PROMPT.format(today=today))


def _extract_json_array(text: str) -> list:
    text = text.strip()
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        raise ValueError("No JSON array found in model output")
    return json.loads(match.group(0))


def extract_events(image_bytes: bytes, image_format: str, model_id: str, region: str) -> list:
    """Run the extraction agent once, with one retry on unparseable output.

    Returns a list of raw event dicts (not yet validated — see schema.py).
    Raises only if both attempts fail to produce parseable JSON.
    """
    today = datetime.date.today().isoformat()
    agent = _build_agent(model_id, region, today)

    prompt = [
        {"text": "Extract every dated commitment from this notice as a JSON array."},
        {"image": {"format": image_format, "source": {"bytes": image_bytes}}},
    ]

    last_error: Exception | None = None
    for attempt in range(2):
        result = agent(prompt if attempt == 0 else "That was not valid JSON. Reply with the JSON array only.")
        try:
            return _extract_json_array(str(result))
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            continue

    raise last_error or ValueError("Model did not return parseable JSON")
