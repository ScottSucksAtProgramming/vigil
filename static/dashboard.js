/* dashboard.js — grandma-watcher caregiver dashboard */
"use strict";

// ── Theme ──────────────────────────────────────────────────

function getEffectiveTheme() {
  const stored = localStorage.getItem("theme");
  if (stored) return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = theme === "dark" ? "☀" : "🌙";
}

function toggleTheme() {
  const next = getEffectiveTheme() === "dark" ? "light" : "dark";
  localStorage.setItem("theme", next);
  applyTheme(next);
}

function initTheme() {
  applyTheme(getEffectiveTheme());
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.addEventListener("click", toggleTheme);
}

// ── Gallery ────────────────────────────────────────────────

// Module-level store: maps timestamp → entry object (used by modal for in-place label update)
const galleryEntries = {};

function formatTimestamp(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderLabelTag(label) {
  if (!label) return "";
  const cls = label === "real_issue" ? "label-real" : "label-false";
  const text = label === "real_issue" ? "✓ Real Issue" : "✗ False Alarm";
  return `<span class="gallery-card-label ${cls}">${text}</span>`;
}

function buildCard(entry) {
  const safeClass = entry.assessment.safe ? "badge-safe" : "badge-alert";
  const safeText = entry.assessment.safe ? "✓ Safe" : "✗ Unsafe";
  const alertBadge = entry.alert_fired
    ? '<span class="badge-fired">🔔 Alert fired</span>'
    : "";
  return `
    <div class="gallery-card" data-id="${entry.timestamp}">
      <img src="/${entry.image_path}" alt="Frame ${formatTimestamp(
        entry.timestamp,
      )}" loading="lazy">
      <div class="gallery-card-body">
        <div class="gallery-card-status">
          <span class="${safeClass}">${safeText}</span>
          <span class="badge-conf">${entry.assessment.confidence}</span>
          ${alertBadge}
          <span class="badge-time">${formatTimestamp(entry.timestamp)}</span>
        </div>
        <p class="gallery-card-reason">${entry.assessment.reason}</p>
        ${renderLabelTag(entry.label)}
      </div>
    </div>`;
}

function initGallery() {
  const container = document.getElementById("gallery");
  fetch("/gallery")
    .then((r) => r.json())
    .then((entries) => {
      if (entries.length === 0) {
        container.innerHTML =
          '<p class="gallery-empty">No recent activity yet</p>';
        return;
      }
      entries.forEach((e) => {
        galleryEntries[e.timestamp] = e;
      });
      container.innerHTML = entries.map(buildCard).join("");
      container.querySelectorAll(".gallery-card").forEach((card) => {
        card.addEventListener("click", () =>
          openModal(galleryEntries[card.dataset.id]),
        );
      });
    })
    .catch(() => {
      container.innerHTML =
        '<p class="gallery-empty">Unable to load recent activity</p>';
    });
}

// stub — replaced by initModal() in Task 6
function openModal(entry) {
  console.log("openModal stub", entry);
}
