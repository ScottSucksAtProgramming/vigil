# Dashboard Frontend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `static/dashboard.js` and `static/dashboard.css` to make the grandma-watcher dashboard fully functional in a phone browser.

**Architecture:** Vanilla JS, zero dependencies, no build step. One `DOMContentLoaded` handler wires six narrow init functions (theme, gallery, silence, silence button, modal, report-missed). CSS custom properties drive theming with `prefers-color-scheme` default and a manual toggle persisted to `localStorage`.

**Tech Stack:** Vanilla JS (ES2020), CSS custom properties, Flask API endpoints already implemented in `web_server.py`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `templates/dashboard.html` | Modify | Add `#theme-toggle` button to header |
| `static/dashboard.css` | Create | All styles: theming, layout, gallery cards, modal, tap targets |
| `static/dashboard.js` | Create | Six init functions + DOMContentLoaded wiring |

**Spec:** `docs/superpowers/specs/2026-04-10-dashboard-frontend-design.md`

---

## Chunk 1: CSS + HTML

### Task 1: Add theme toggle button to dashboard.html

**Files:**
- Modify: `templates/dashboard.html:11-14`

- [ ] **Step 1: Read the current header section**

  Open `templates/dashboard.html` and locate the `<header>` block (lines ~11-14):
  ```html
  <header>
    <h1>Grandma Monitor</h1>
    <span id="silence-badge"></span>
  </header>
  ```

- [ ] **Step 2: Add theme toggle button after silence-badge**

  Replace the header block with:
  ```html
  <header>
    <h1>Grandma Monitor</h1>
    <div id="header-controls">
      <span id="silence-badge"></span>
      <button id="theme-toggle" type="button" aria-label="Toggle theme"></button>
    </div>
  </header>
  ```

  > **Note:** The `#header-controls` wrapper `<div>` is intentionally added here to allow the CSS flex layout to align the badge and toggle button as a group on the right side of the header. The spec says "no other changes to the existing HTML structure" referring to the overall page structure — this wrapper is a necessary implementation detail not explicitly mentioned in the spec. It does not affect any existing tests.

- [ ] **Step 3: Verify existing tests still pass**

  ```bash
  make check
  ```
  Expected: all tests pass (no Python changes; the test checks for `element_id` strings which are unchanged).

- [ ] **Step 4: Commit**

  ```bash
  git add templates/dashboard.html
  git commit -m "feat: add theme-toggle button to dashboard header"
  ```

---

### Task 2: Implement dashboard.css

**Files:**
- Create: `static/dashboard.css`

The CSS has four sections: theming variables, base layout, component styles (gallery, controls, modal), and the theme toggle button.

- [ ] **Step 1: Write the theming variables section**

  Open `static/dashboard.css` and write:

  ```css
  /* ── Theming ─────────────────────────────────────────────── */
  :root {
    --bg: #ffffff;
    --bg-card: #f5f5f5;
    --text: #111111;
    --text-muted: #666666;
    --accent-safe: #16a34a;
    --accent-alert: #dc2626;
    --accent-ui: #2563eb;
    --border: #e0e0e0;
    --tap-height: 48px;
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0f0f0f;
      --bg-card: #1a1a1a;
      --text: #f0f0f0;
      --text-muted: #999999;
      --border: #2a2a2a;
    }
  }

  [data-theme="light"] {
    --bg: #ffffff; --bg-card: #f5f5f5; --text: #111111;
    --text-muted: #666666; --border: #e0e0e0;
  }
  [data-theme="dark"] {
    --bg: #0f0f0f; --bg-card: #1a1a1a; --text: #f0f0f0;
    --text-muted: #999999; --border: #2a2a2a;
  }
  ```

- [ ] **Step 2: Write the base layout section**

  Append to `static/dashboard.css`:

  ```css
  /* ── Base layout ─────────────────────────────────────────── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 0 16px 32px;
    max-width: 480px;
    margin: 0 auto;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 0 10px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 14px;
  }

  header h1 { font-size: 1.1rem; font-weight: 600; }

  #header-controls {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  #silence-badge {
    font-size: 0.8rem;
    color: var(--text-muted);
  }

  #stream-img {
    width: 100%;
    border-radius: 8px;
    display: block;
    background: var(--border);
    margin-bottom: 14px;
  }
  ```

- [ ] **Step 3: Write the controls section**

  Append to `static/dashboard.css`:

  ```css
  /* ── Controls ────────────────────────────────────────────── */
  #controls {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
  }

  button, a.btn {
    min-height: var(--tap-height);
    min-width: var(--tap-height);
    font-size: 1rem;
    border-radius: 8px;
    padding: 0 20px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text);
    cursor: pointer;
    touch-action: manipulation;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  button:disabled, .btn--disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  #controls button,
  #controls a.btn { flex: 1; }

  #report-section { margin-top: 12px; }
  #report-btn { width: 100%; }
  ```

- [ ] **Step 4: Write the gallery section**

  Append to `static/dashboard.css`:

  ```css
  /* ── Gallery ─────────────────────────────────────────────── */
  #gallery-section h2 {
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 12px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .gallery-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 12px;
    overflow: hidden;
    cursor: pointer;
  }

  .gallery-card img {
    width: 100%;
    display: block;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    background: var(--border);
  }

  .gallery-card-body { padding: 10px 12px; }

  .gallery-card-status {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
    font-size: 0.9rem;
  }

  .badge-safe  { color: var(--accent-safe); font-weight: 600; }
  .badge-alert { color: var(--accent-alert); font-weight: 600; }
  .badge-conf  { color: var(--text-muted); font-size: 0.8rem; }
  .badge-time  { color: var(--text-muted); font-size: 0.8rem; margin-left: auto; }
  .badge-fired { color: var(--accent-alert); font-size: 0.8rem; }

  .gallery-card-reason {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-bottom: 4px;
  }

  .gallery-card-label {
    display: inline-block;
    font-size: 0.75rem;
    border-radius: 12px;
    padding: 2px 10px;
    margin-top: 4px;
  }
  .label-real  { background: #16a34a22; color: var(--accent-safe); }
  .label-false { background: #dc262622; color: var(--accent-alert); }

  .gallery-empty {
    color: var(--text-muted);
    font-size: 0.9rem;
    padding: 16px 0;
    text-align: center;
  }
  ```

- [ ] **Step 5: Write the modal section**

  Append to `static/dashboard.css`:

  ```css
  /* ── Modal ───────────────────────────────────────────────── */
  #modal {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: flex-end;
    z-index: 100;
  }

  #modal[hidden] { display: none; }

  #modal-sheet {
    background: var(--bg);
    border-radius: 16px 16px 0 0;
    padding: 20px;
    width: 100%;
    max-height: 85vh;
    overflow-y: auto;
  }

  #modal-close {
    float: right;
    border: none;
    background: none;
    font-size: 1.2rem;
    /* Explicit 48px tap target — overrides the global min-height reset */
    min-height: var(--tap-height);
    min-width: var(--tap-height);
    padding: 0;
  }

  #modal-img {
    width: 100%;
    border-radius: 8px;
    margin: 10px 0;
    display: block;
    background: var(--border);
  }

  #modal-reason {
    font-size: 0.9rem;
    color: var(--text-muted);
    margin-bottom: 16px;
  }

  #modal-actions {
    display: flex;
    gap: 12px;
  }

  #modal-actions button { flex: 1; }
  ```

- [ ] **Step 6: Write the theme toggle button section**

  Append to `static/dashboard.css`:

  ```css
  /* ── Theme toggle ────────────────────────────────────────── */
  #theme-toggle {
    background: none;
    border: none;
    font-size: 1.4rem;
    padding: 4px 8px;
    min-height: var(--tap-height);
    min-width: var(--tap-height);
    cursor: pointer;
    touch-action: manipulation;
  }
  ```

- [ ] **Step 7: Run make check**

  ```bash
  make check
  ```
  Expected: all tests pass (CSS changes don't affect Python tests; lint only covers `.py` files).

- [ ] **Step 8: Commit**

  ```bash
  git add static/dashboard.css
  git commit -m "feat: implement dashboard.css — theming, layout, gallery, modal"
  ```

---

## Chunk 2: JavaScript

### Task 3: Implement initTheme()

**Files:**
- Create (start): `static/dashboard.js`

Note: tasks 3–7 build `dashboard.js` incrementally. Each task appends to the file; the final task adds the `DOMContentLoaded` wiring that calls all the init functions.

- [ ] **Step 1: Write the file header and initTheme()**

  Write `static/dashboard.js`:

  ```js
  /* dashboard.js — grandma-watcher caregiver dashboard */
  'use strict';

  // ── Theme ──────────────────────────────────────────────────

  function getEffectiveTheme() {
    const stored = localStorage.getItem('theme');
    if (stored) return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀' : '🌙';
  }

  function toggleTheme() {
    const next = getEffectiveTheme() === 'dark' ? 'light' : 'dark';
    localStorage.setItem('theme', next);
    applyTheme(next);
  }

  function initTheme() {
    applyTheme(getEffectiveTheme());
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.addEventListener('click', toggleTheme);
  }
  ```

- [ ] **Step 2: Verify manually**

  Open the dashboard in a browser (`flask run` or `python web_server.py`). Confirm:
  - Theme toggle button shows ☀ or 🌙 depending on system preference.
  - Clicking it flips the icon and the page colours change.
  - Refreshing preserves the manual choice.

  (Automated test: none for JS — see spec Testing section.)

- [ ] **Step 3: Run make check**

  ```bash
  make check
  ```
  Expected: passes.

- [ ] **Step 4: Commit**

  ```bash
  git add static/dashboard.js
  git commit -m "feat: add initTheme() to dashboard.js"
  ```

---

### Task 4: Implement initGallery()

**Files:**
- Modify: `static/dashboard.js`

Gallery entry shape from `/gallery`:
```json
{
  "timestamp": "2026-04-09T03:00:00Z",
  "image_path": "images/2026-04-09_03-00-00.jpg",
  "assessment": { "safe": true, "confidence": "high", "reason": "Patient resting in bed." },
  "alert_fired": false,
  "label": ""
}
```
Image URL: `src="/${entry.image_path}"` — no leading slash in `image_path`, prefix with `/`.

- [ ] **Step 1: Append initGallery() and helpers**

  Append to `static/dashboard.js`:

  ```js
  // ── Gallery ────────────────────────────────────────────────

  // Module-level store: maps timestamp → entry object (used by modal for in-place label update)
  const galleryEntries = {};

  function formatTimestamp(iso) {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }

  function renderLabelTag(label) {
    if (!label) return '';
    const cls = label === 'real_issue' ? 'label-real' : 'label-false';
    const text = label === 'real_issue' ? '✓ Real Issue' : '✗ False Alarm';
    return `<span class="gallery-card-label ${cls}">${text}</span>`;
  }

  function buildCard(entry) {
    const safeClass = entry.assessment.safe ? 'badge-safe' : 'badge-alert';
    const safeText  = entry.assessment.safe ? '✓ Safe' : '✗ Unsafe';
    const alertBadge = entry.alert_fired
      ? '<span class="badge-fired">🔔 Alert fired</span>'
      : '';
    return `
      <div class="gallery-card" data-id="${entry.timestamp}">
        <img src="/${entry.image_path}" alt="Frame ${formatTimestamp(entry.timestamp)}" loading="lazy">
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
    const container = document.getElementById('gallery');
    fetch('/gallery')
      .then(r => r.json())
      .then(entries => {
        if (entries.length === 0) {
          container.innerHTML = '<p class="gallery-empty">No recent activity yet</p>';
          return;
        }
        entries.forEach(e => { galleryEntries[e.timestamp] = e; });
        container.innerHTML = entries.map(buildCard).join('');
        // wire card clicks to open modal
        container.querySelectorAll('.gallery-card').forEach(card => {
          card.addEventListener('click', () => openModal(galleryEntries[card.dataset.id]));
        });
      })
      .catch(() => {
        container.innerHTML = '<p class="gallery-empty">Unable to load recent activity</p>';
      });
  }
  ```

- [ ] **Step 2: Add stub for openModal() so the file is runnable**

  Append to `static/dashboard.js` (temporary — will be replaced in Task 6):

  ```js
  // stub — replaced by initModal() in Task 6
  function openModal(entry) { console.log('openModal stub', entry); }
  ```

- [ ] **Step 3: Verify manually**

  Open the dashboard. Confirm gallery cards render with image, status, reason, and timestamp. Confirm empty-state text appears when gallery is empty (temporarily rename `dataset/log.jsonl` to test, then restore).

- [ ] **Step 4: Run make check**

  ```bash
  make check
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add static/dashboard.js
  git commit -m "feat: add initGallery() to dashboard.js"
  ```

---

### Task 5: Implement initSilence() and initSilenceButton()

**Files:**
- Modify: `static/dashboard.js`

`GET /silence` response: `{ "active": true, "remaining_seconds": 1234 }`.
Badge text: `Math.ceil(remaining_seconds / 60)` minutes.

- [ ] **Step 1: Append updateSilenceBadge(), initSilence(), initSilenceButton()**

  Append to `static/dashboard.js`:

  ```js
  // ── Silence ────────────────────────────────────────────────

  function updateSilenceBadge() {
    fetch('/silence')
      .then(r => r.json())
      .then(data => {
        const badge = document.getElementById('silence-badge');
        if (!badge) return;
        if (data.active) {
          const mins = Math.ceil(data.remaining_seconds / 60);
          badge.textContent = `🔕 Silenced — ${mins} min remaining`;
        } else {
          badge.textContent = '';
        }
      })
      .catch(() => { /* silent — don't disrupt page */ });
  }

  function initSilence() {
    updateSilenceBadge();
    setInterval(updateSilenceBadge, 15000);
  }

  function initSilenceButton() {
    const btn = document.getElementById('silence-btn');
    if (!btn) return;
    btn.addEventListener('click', () => {
      btn.disabled = true;
      fetch('/silence', { method: 'POST' })
        .then(() => updateSilenceBadge())
        .catch(() => {})
        .finally(() => {
          setTimeout(() => { btn.disabled = false; }, 2000);
        });
    });
  }
  ```

- [ ] **Step 2: Verify manually**

  Open dashboard. Confirm silence badge is empty when not silenced. Click "Silence 30 min" button — confirm badge updates to show remaining time, and button is briefly disabled after click.

- [ ] **Step 3: Run make check**

  ```bash
  make check
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add static/dashboard.js
  git commit -m "feat: add initSilence() and initSilenceButton() to dashboard.js"
  ```

---

### Task 6: Implement initModal()

**Files:**
- Modify: `static/dashboard.js`

Modal elements (already in `dashboard.html`): `#modal`, `#modal-sheet`, `#modal-img`, `#modal-reason`, `#modal-real`, `#modal-false`, `#modal-close`.

- [ ] **Step 1: Remove the openModal() stub**

  Delete the stub line added in Task 4:
  ```js
  // stub — replaced by initModal() in Task 6
  function openModal(entry) { console.log('openModal stub', entry); }
  ```

- [ ] **Step 2: Append openModal(), closeModal(), flashButton(), submitLabel(), initModal()**

  Append to `static/dashboard.js`:

  ```js
  // ── Modal ──────────────────────────────────────────────────

  let currentEntryId = null;

  function openModal(entry) {
    currentEntryId = entry.timestamp;
    document.getElementById('modal-img').src = `/${entry.image_path}`;
    document.getElementById('modal-reason').textContent = entry.assessment.reason;
    document.getElementById('modal').removeAttribute('hidden');
  }

  function closeModal() {
    document.getElementById('modal').setAttribute('hidden', '');
    currentEntryId = null;
  }

  function flashButton(btn, text, durationMs) {
    const original = btn.textContent;
    btn.textContent = text;
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = original;
      btn.disabled = false;
    }, durationMs);
  }

  function submitLabel(labelValue, btn) {
    if (!currentEntryId) return;
    const id = currentEntryId;
    fetch(`/label/${encodeURIComponent(id)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: labelValue }),
    })
      .then(r => {
        if (!r.ok) throw new Error('label failed');
        flashButton(btn, '✓ Saved', 1000);
        // Update entry in memory and re-render card label in place
        if (galleryEntries[id]) {
          galleryEntries[id].label = labelValue;
          const card = document.querySelector(`.gallery-card[data-id="${id}"]`);
          if (card) {
            const existing = card.querySelector('.gallery-card-label');
            if (existing) existing.remove();
            const body = card.querySelector('.gallery-card-body');
            if (body) body.insertAdjacentHTML('beforeend', renderLabelTag(labelValue));
          }
        }
        setTimeout(closeModal, 1000);
      })
      .catch(() => {
        flashButton(btn, 'Error', 1000);
        // leave modal open
      });
  }

  function initModal() {
    document.getElementById('modal-close').addEventListener('click', closeModal);
    // Close on backdrop click (outside modal-sheet)
    document.getElementById('modal').addEventListener('click', e => {
      if (e.target === document.getElementById('modal')) closeModal();
    });
    document.getElementById('modal-real').addEventListener('click', function () {
      submitLabel('real_issue', this);
    });
    document.getElementById('modal-false').addEventListener('click', function () {
      submitLabel('false_alarm', this);
    });
  }
  ```

- [ ] **Step 3: Verify manually**

  Open dashboard. Click a gallery card — modal should appear with the correct image and reason. Click ✕ or outside the sheet — modal should close. Click "Real Issue" or "False Alarm" — should flash "✓ Saved" then close, and the card should show the label tag.

- [ ] **Step 4: Run make check**

  ```bash
  make check
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add static/dashboard.js
  git commit -m "feat: add initModal() to dashboard.js"
  ```

---

### Task 7: Implement initReportMissed() and wire DOMContentLoaded

**Files:**
- Modify: `static/dashboard.js`

- [ ] **Step 1: Append initReportMissed()**

  Append to `static/dashboard.js`:

  ```js
  // ── Report missed alert ────────────────────────────────────

  function initReportMissed() {
    const btn = document.getElementById('report-btn');
    if (!btn) return;
    btn.addEventListener('click', () => {
      btn.disabled = true;
      fetch('/report-missed', { method: 'POST' })
        .then(r => {
          if (!r.ok) throw new Error('report failed');
          flashButton(btn, '✓ Sent', 1500);
        })
        .catch(() => {
          flashButton(btn, 'Error — try again', 1500);
        });
      // Note: no finally{} needed — flashButton() re-enables the button after the delay.
    });
  }
  ```

- [ ] **Step 2: Append DOMContentLoaded wiring**

  Append to `static/dashboard.js`:

  ```js
  // ── Init ───────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initGallery();
    initSilence();
    initSilenceButton();
    initModal();
    initReportMissed();
  });
  ```

- [ ] **Step 3: Run make check**

  ```bash
  make check
  ```
  Expected: all tests pass.

- [ ] **Step 4: Full manual verification**

  Open dashboard. Walk through every interaction:
  - [ ] Theme toggle flips colours and persists on reload
  - [ ] Gallery cards render with image, status, reason, timestamp
  - [ ] Empty gallery shows "No recent activity yet"
  - [ ] Silence button disables briefly, badge updates
  - [ ] Silence badge polls every 15 s (check DevTools network tab)
  - [ ] Card click opens modal with correct image + reason
  - [ ] Modal closes on ✕ or backdrop click
  - [ ] Label buttons flash "✓ Saved" then close modal; card shows label tag
  - [ ] "Report Missed Alert" button flashes "✓ Sent"

- [ ] **Step 5: Final commit**

  ```bash
  git add static/dashboard.js
  git commit -m "feat: add initReportMissed() and DOMContentLoaded wiring — dashboard.js complete"
  ```

- [ ] **Step 6: Mark tasks @done in todo.taskpaper**

  In `todo.taskpaper`, mark the following tasks `@done`:
  - `Build dashboard.js (fetch gallery, poll silence state, update UI without full reload)`
  - `Build dashboard.css (mobile-first, large tap targets, readable on phone)`

  ```bash
  git add todo.taskpaper
  git commit -m "chore: mark dashboard.js and dashboard.css tasks @done"
  ```
