// State machine: empty -> working -> results | error. No framework, no build step.

const API_BASE = window.API_BASE;
const SAMPLE_NOTICE_URL = "sample-notice.jpg";

const els = {
  empty: document.getElementById("state-empty"),
  working: document.getElementById("state-working"),
  results: document.getElementById("state-results"),
  error: document.getElementById("state-error"),
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  trySample: document.getElementById("try-sample"),
  workingThumb: document.getElementById("working-thumb"),
  workingText: document.getElementById("working-text"),
  eventCount: document.getElementById("event-count"),
  eventCountPlural: document.getElementById("event-count-plural"),
  warnings: document.getElementById("warnings"),
  eventList: document.getElementById("event-list"),
  addAll: document.getElementById("add-all"),
  another: document.getElementById("another"),
  errorText: document.getElementById("error-text"),
  retry: document.getElementById("retry"),
};

let currentEvents = [];
let lastFile = null;

function showState(name) {
  for (const key of ["empty", "working", "results", "error"]) {
    els[key].hidden = key !== name;
  }
}

function showError(message) {
  els.errorText.textContent = message;
  showState("error");
}

// --- Upload + extract flow -------------------------------------------------

async function processFile(file) {
  lastFile = file;
  els.workingThumb.src = URL.createObjectURL(file);
  els.workingText.textContent = "Reading the notice…";
  showState("working");

  try {
    const { uploadUrl, key } = await requestUploadUrl(file);
    await putToS3(uploadUrl, file);
    els.workingText.textContent = "Finding the dates…";
    const { events, warnings } = await requestExtraction(key);
    renderResults(events, warnings);
  } catch (err) {
    console.error(err);
    showError(err.message || "Something went wrong reading that notice.");
  }
}

async function requestUploadUrl(file) {
  const res = await fetch(`${API_BASE}/upload-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, contentType: file.type || "image/jpeg" }),
  });
  if (!res.ok) throw new Error("Could not start the upload. Try again.");
  return res.json();
}

async function putToS3(uploadUrl, file) {
  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type || "image/jpeg" },
    body: file,
  });
  if (!res.ok) throw new Error("Upload failed. Try again.");
}

async function requestExtraction(key) {
  const res = await fetch(`${API_BASE}/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  if (!res.ok) throw new Error("Could not read that notice. Try again.");
  return res.json();
}

// --- Rendering ---------------------------------------------------------

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function formatTime(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  const period = h >= 12 ? "pm" : "am";
  const hour12 = ((h + 11) % 12) + 1;
  return m === 0 ? `${hour12}${period}` : `${hour12}:${String(m).padStart(2, "0")}${period}`;
}

function eventMetaLine(event) {
  const parts = [];
  if (event.startTime) {
    parts.push(event.endTime ? `${formatTime(event.startTime)}–${formatTime(event.endTime)}` : formatTime(event.startTime));
  }
  if (event.venue) parts.push(event.venue);
  if (event.action) parts.push(event.action);
  return parts.join(" · ");
}

function renderResults(events, warnings) {
  currentEvents = events;
  els.eventCount.textContent = events.length;
  els.eventCountPlural.textContent = events.length === 1 ? "" : "s";

  if (warnings && warnings.length) {
    els.warnings.textContent = warnings.join(" · ");
    els.warnings.hidden = false;
  } else {
    els.warnings.hidden = true;
  }

  els.eventList.innerHTML = "";
  events.forEach((event, index) => {
    const [, month, day] = event.date.split("-").map(Number);
    const li = document.createElement("li");
    li.className = "event-card";
    li.innerHTML = `
      <div class="event-date">
        <span class="day">${day}</span>
        <span class="month">${MONTHS[month - 1]}</span>
      </div>
      <div class="event-body">
        <p class="event-title">${escapeHtml(event.title)}${event.confidence === "low" ? '<span class="event-low-confidence">unsure</span>' : ""}</p>
        <p class="event-meta">${escapeHtml(eventMetaLine(event))}</p>
      </div>
      <button class="event-add" type="button" data-index="${index}">Add</button>
    `;
    els.eventList.appendChild(li);
  });

  showState("results");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

// --- .ics generation -----------------------------------------------------

function icsEscape(text) {
  return String(text || "").replace(/\\/g, "\\\\").replace(/,/g, "\\,").replace(/;/g, "\\;").replace(/\n/g, "\\n");
}

function icsDateTime(date, time) {
  return `${date.replace(/-/g, "")}T${time.replace(":", "")}00`;
}

function addDays(dateStr, days) {
  // Do the arithmetic in UTC and read it back in UTC — mixing local-time
  // construction with toISOString() (always UTC) rolls the date back a day
  // for any positive UTC offset, which includes IST.
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10).replace(/-/g, "");
}

function buildVEvent(event, uid) {
  const lines = ["BEGIN:VEVENT", `UID:${uid}`];
  if (event.startTime) {
    lines.push(`DTSTART;TZID=Asia/Kolkata:${icsDateTime(event.date, event.startTime)}`);
    const end = event.endTime || event.startTime;
    lines.push(`DTEND;TZID=Asia/Kolkata:${icsDateTime(event.date, end)}`);
  } else {
    lines.push(`DTSTART;VALUE=DATE:${event.date.replace(/-/g, "")}`);
    lines.push(`DTEND;VALUE=DATE:${addDays(event.date, 1)}`);
  }
  lines.push(`SUMMARY:${icsEscape(event.title)}`);
  if (event.venue) lines.push(`LOCATION:${icsEscape(event.venue)}`);
  if (event.action) lines.push(`DESCRIPTION:${icsEscape(event.action)}`);
  lines.push("END:VEVENT");
  return lines;
}

function buildIcs(events) {
  const stamp = Date.now();
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Notice-to-Calendar//EN"];
  events.forEach((event, index) => {
    lines.push(...buildVEvent(event, `${stamp}-${index}@notice-to-calendar`));
  });
  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}

function downloadIcs(content, filename) {
  const blob = new Blob([content], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// --- Wiring ----------------------------------------------------------------

els.dropzone.addEventListener("click", () => els.fileInput.click());
els.dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.fileInput.click(); }
});
els.fileInput.addEventListener("change", () => {
  if (els.fileInput.files[0]) processFile(els.fileInput.files[0]);
});

["dragover", "dragenter"].forEach((evt) =>
  els.dropzone.addEventListener(evt, (e) => { e.preventDefault(); els.dropzone.classList.add("drag-over"); })
);
["dragleave", "drop"].forEach((evt) =>
  els.dropzone.addEventListener(evt, (e) => { e.preventDefault(); els.dropzone.classList.remove("drag-over"); })
);
els.dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) processFile(file);
});

els.trySample.addEventListener("click", async () => {
  try {
    const res = await fetch(SAMPLE_NOTICE_URL);
    const blob = await res.blob();
    const file = new File([blob], "sample-notice.jpg", { type: blob.type || "image/jpeg" });
    processFile(file);
  } catch {
    showError("Could not load the sample notice.");
  }
});

els.eventList.addEventListener("click", (e) => {
  const btn = e.target.closest(".event-add");
  if (!btn) return;
  const event = currentEvents[Number(btn.dataset.index)];
  downloadIcs(buildIcs([event]), `${event.title.slice(0, 40)}.ics`);
});

els.addAll.addEventListener("click", () => {
  downloadIcs(buildIcs(currentEvents), "notice-events.ics");
});

els.another.addEventListener("click", () => showState("empty"));
els.retry.addEventListener("click", () => {
  if (lastFile) processFile(lastFile);
  else showState("empty");
});
