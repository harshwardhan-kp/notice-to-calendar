"""Event schema: validation and normalisation for model output.

The model returns a JSON array of event-like objects. This module enforces the
contract the frontend and .ics generation depend on, dropping anything that
doesn't meet it rather than failing the whole request.
"""
import re

REQUIRED_FIELDS = ("title", "date")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def normalise_event(raw: dict) -> tuple[dict | None, str | None]:
    """Validate and normalise one raw event dict.

    Returns (event, None) if valid, or (None, warning) if dropped.
    """
    if not isinstance(raw, dict):
        return None, "Dropped a malformed event (not an object)"

    title = raw.get("title")
    date = raw.get("date")

    if not title or not isinstance(title, str):
        return None, "Dropped an event with no title"
    if not date or not isinstance(date, str) or not DATE_RE.match(date):
        return None, f"Dropped '{title}': missing or invalid date"

    start_time = raw.get("startTime")
    if start_time is not None and not TIME_RE.match(str(start_time)):
        start_time = None

    end_time = raw.get("endTime")
    if end_time is not None and not TIME_RE.match(str(end_time)):
        end_time = None

    venue = raw.get("venue")
    venue = venue if isinstance(venue, str) and venue.strip() else None

    action = raw.get("action")
    action = action if isinstance(action, str) and action.strip() else None

    confidence = raw.get("confidence")
    confidence = "low" if confidence not in ("high", "low") else confidence

    return {
        "title": title.strip(),
        "date": date,
        "startTime": start_time,
        "endTime": end_time,
        "venue": venue,
        "action": action,
        "confidence": confidence,
    }, None


def validate_events(raw_events: list) -> tuple[list[dict], list[str]]:
    """Validate a list of raw event dicts. Never raises on bad input."""
    events: list[dict] = []
    warnings: list[str] = []

    if not isinstance(raw_events, list):
        return [], ["Model did not return a list of events"]

    for raw in raw_events:
        event, warning = normalise_event(raw)
        if event is not None:
            events.append(event)
        if warning is not None:
            warnings.append(warning)

    if not events and not warnings:
        warnings.append("No dates found in this image")

    return events, warnings
