type Clip = {
  id: number;
  filename: string;
  timestamp: string;
  duration_seconds: number | null;
  assistant_id: string | null;
  sample_rate: number | null;
  label: string | null;
  deleted: boolean;
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
const labelFilter = document.getElementById("label-filter") as HTMLSelectElement;
const showDeletedCheckbox = document.getElementById("show-deleted") as HTMLInputElement;
const applyBtn = document.getElementById("apply") as HTMLButtonElement;
const clearBtn = document.getElementById("clear") as HTMLButtonElement;
const downloadBtn = document.getElementById("download") as HTMLButtonElement;
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
  if (labelFilter.value !== "all") {
    params.set("label", labelFilter.value);
  }
  if (showDeletedCheckbox.checked) {
    params.set("include_deleted", "true");
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
    if (clip.deleted) {
      card.classList.add("deleted");
    }

    const header = document.createElement("div");
    header.className = "clip-header";

    const title = document.createElement("div");
    title.className = "clip-title";
    title.textContent = clip.filename;

    const badges = document.createElement("div");
    badges.className = "badges";

    const assistantBadge = document.createElement("span");
    assistantBadge.className = "badge";
    assistantBadge.textContent = clip.assistant_id ?? "assistant";
    badges.appendChild(assistantBadge);

    const labelBadge = document.createElement("span");
    labelBadge.className = "badge label-badge";
    labelBadge.textContent = clip.label ?? "Unknown";
    labelBadge.setAttribute("data-label", clip.label ?? "Unknown");
    badges.appendChild(labelBadge);

    if (clip.deleted) {
      const deletedBadge = document.createElement("span");
      deletedBadge.className = "badge deleted-badge";
      deletedBadge.textContent = "Deleted";
      badges.appendChild(deletedBadge);
    }

    header.appendChild(title);
    header.appendChild(badges);

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

    const positiveBtn = document.createElement("button");
    positiveBtn.className = "positive";
    positiveBtn.textContent = "✓ True Positive";

    const falsePositiveBtn = document.createElement("button");
    falsePositiveBtn.className = "false-positive";
    falsePositiveBtn.textContent = "✗ False Positive";

    const falseNegativeBtn = document.createElement("button");
    falseNegativeBtn.className = "false-negative";
    falseNegativeBtn.textContent = "⊘ False Negative";

    const backgroundNoiseBtn = document.createElement("button");
    backgroundNoiseBtn.className = "background-noise";
    backgroundNoiseBtn.textContent = "♪ Background Noise";

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete";
    deleteBtn.textContent = clip.deleted ? "↺ Undelete" : "🗑 Delete";

    const lockButtons = (locked: boolean) => {
      positiveBtn.disabled = locked;
      falsePositiveBtn.disabled = locked;
      falseNegativeBtn.disabled = locked;
      backgroundNoiseBtn.disabled = locked;
      deleteBtn.disabled = locked;
    };

    const labelClip = async (
      label: "Positive" | "False Positive" | "False Negative" | "Background Noise",
    ) => {
      lockButtons(true);
      try {
        const response = await fetch(`/api/clips/${clip.id}/label`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ label }),
        });
        if (!response.ok) {
          throw new Error("Failed to label clip");
        }
        // Update the label badge
        labelBadge.textContent = label;
        labelBadge.setAttribute("data-label", label);
        lockButtons(false);
      } catch (error) {
        console.error(error);
        lockButtons(false);
      }
    };

    const toggleDelete = async () => {
      lockButtons(true);
      try {
        const endpoint = clip.deleted ? "undelete" : "delete";
        const response = await fetch(`/api/clips/${clip.id}/${endpoint}`, {
          method: "POST",
        });
        if (!response.ok) {
          throw new Error(`Failed to ${endpoint} clip`);
        }
        // Reload the list to reflect changes
        load();
      } catch (error) {
        console.error(error);
        lockButtons(false);
      }
    };

    positiveBtn.addEventListener("click", () => labelClip("Positive"));
    falsePositiveBtn.addEventListener("click", () => labelClip("False Positive"));
    falseNegativeBtn.addEventListener("click", () => labelClip("False Negative"));
    backgroundNoiseBtn.addEventListener("click", () => labelClip("Background Noise"));
    deleteBtn.addEventListener("click", toggleDelete);

    actions.appendChild(positiveBtn);
    actions.appendChild(falsePositiveBtn);
    actions.appendChild(falseNegativeBtn);
    actions.appendChild(backgroundNoiseBtn);
    actions.appendChild(deleteBtn);

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

downloadBtn.addEventListener("click", () => {
  const query = buildQuery();
  window.location.href = `/api/clips/download${query}`;
});

refreshBtn.addEventListener("click", () => {
  load();
});

load();
