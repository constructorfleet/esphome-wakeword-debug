type Clip = {
  id: string;
  filename: string;
  timestamp: string;
  duration_seconds: number | null;
  assistant_id: string | null;
  sample_rate: number | null;
  audio_url: string;
};

type ClipResponse = {
  clips: Clip[];
};

const listEl = document.getElementById("list") as HTMLDivElement;
const emptyEl = document.getElementById("empty") as HTMLDivElement;
const countEl = document.getElementById("clip-count") as HTMLSpanElement;
const rangeEl = document.getElementById("range-label") as HTMLSpanElement;

const startInput = document.getElementById("start") as HTMLInputElement;
const endInput = document.getElementById("end") as HTMLInputElement;
const applyBtn = document.getElementById("apply") as HTMLButtonElement;
const clearBtn = document.getElementById("clear") as HTMLButtonElement;
const refreshBtn = document.getElementById("refresh") as HTMLButtonElement;

const formatDate = (value: string) => {
  const date = new Date(value);
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
};

const formatDuration = (value: number | null) => {
  if (value === null || Number.isNaN(value)) return "Unknown";
  return `${value.toFixed(2)}s`;
};

const setRangeLabel = () => {
  if (!startInput.value && !endInput.value) {
    rangeEl.textContent = "All time";
    return;
  }
  const start = startInput.value ? new Date(startInput.value) : null;
  const end = endInput.value ? new Date(endInput.value) : null;
  if (start && end) {
    rangeEl.textContent = `${start.toLocaleString()} → ${end.toLocaleString()}`;
  } else if (start) {
    rangeEl.textContent = `From ${start.toLocaleString()}`;
  } else if (end) {
    rangeEl.textContent = `Until ${end.toLocaleString()}`;
  }
};

const buildQuery = () => {
  const params = new URLSearchParams();
  if (startInput.value) {
    params.set("start", new Date(startInput.value).toISOString());
  }
  if (endInput.value) {
    params.set("end", new Date(endInput.value).toISOString());
  }
  const query = params.toString();
  return query ? `?${query}` : "";
};

const render = (clips: Clip[]) => {
  listEl.innerHTML = "";
  countEl.textContent = clips.length.toString();
  if (clips.length === 0) {
    emptyEl.classList.remove("hidden");
    return;
  }
  emptyEl.classList.add("hidden");

  for (const clip of clips) {
    const card = document.createElement("div");
    card.className = "clip-card";

    const header = document.createElement("div");
    header.className = "clip-header";

    const title = document.createElement("div");
    title.className = "clip-title";
    title.textContent = clip.filename;

    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = clip.assistant_id ?? "assistant";

    header.appendChild(title);
    header.appendChild(badge);

    const meta = document.createElement("div");
    meta.className = "clip-meta";
    meta.innerHTML = `
      <div>Captured: ${formatDate(clip.timestamp)}</div>
      <div>Duration: ${formatDuration(clip.duration_seconds)}</div>
      <div>Sample Rate: ${clip.sample_rate ?? "Unknown"} Hz</div>
    `;

    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = clip.audio_url;

    const actions = document.createElement("div");
    actions.className = "actions";

    const trueBtn = document.createElement("button");
    trueBtn.className = "true";
    trueBtn.textContent = "True Positive";

    const falseBtn = document.createElement("button");
    falseBtn.className = "false";
    falseBtn.textContent = "False Positive";

    const lockButtons = (locked: boolean) => {
      trueBtn.disabled = locked;
      falseBtn.disabled = locked;
    };

    const labelClip = async (label: "true_positive" | "false_positive") => {
      lockButtons(true);
      try {
        const response = await fetch(`/api/clips/${encodeURIComponent(clip.filename)}/label`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ label }),
        });
        if (!response.ok) {
          throw new Error("Failed to label clip");
        }
        card.remove();
        const remaining = listEl.querySelectorAll(".clip-card").length;
        countEl.textContent = remaining.toString();
        if (remaining === 0) {
          emptyEl.classList.remove("hidden");
        }
      } catch (error) {
        console.error(error);
        lockButtons(false);
      }
    };

    trueBtn.addEventListener("click", () => labelClip("true_positive"));
    falseBtn.addEventListener("click", () => labelClip("false_positive"));

    actions.appendChild(trueBtn);
    actions.appendChild(falseBtn);

    card.appendChild(header);
    card.appendChild(meta);
    card.appendChild(audio);
    card.appendChild(actions);

    listEl.appendChild(card);
  }
};

const load = async () => {
  setRangeLabel();
  const response = await fetch(`/api/clips${buildQuery()}`);
  if (!response.ok) {
    render([]);
    return;
  }
  const data = (await response.json()) as ClipResponse;
  render(data.clips);
};

applyBtn.addEventListener("click", () => {
  load();
});

clearBtn.addEventListener("click", () => {
  startInput.value = "";
  endInput.value = "";
  load();
});

refreshBtn.addEventListener("click", () => {
  load();
});

load();
