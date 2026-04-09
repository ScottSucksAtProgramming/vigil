---
title: "grandma-watcher Dev Environment"
summary: "Local development strategy — what runs on Mac, what runs on Pi, and how to test without hardware"
created: 2026-04-09
updated: 2026-04-09
---

# grandma-watcher Dev Environment

## The Split

Development happens on Mac. Deployment target is Raspberry Pi 5 (ARM64, Pi OS Lite 64-bit, headless).

| Activity | Where |
|---|---|
| Write code, run tests | Mac |
| Linting / formatting | Mac (`make check`) |
| Smoke test (live camera + real API) | Pi via SSH |
| Permanent deployment | Pi |

All unit and integration tests must pass on Mac without Pi hardware. If a test requires the Pi, it belongs in `smoke_test.py`.

## Mac Setup

```bash
# Clone and install deps
cd grandma-watcher
pip install -r requirements.txt

# Copy example config — edit with real API keys for smoke tests only
cp config.yaml.example config.yaml

# Run the full pre-merge gate
make check   # black + ruff + pytest
```

`config.yaml` with real keys is `.gitignore`d. Never commit it.

## Running Tests Locally

```bash
pytest           # all tests
pytest tests/test_alert.py        # one file
pytest -k "decision_matrix"       # by name
pytest --tb=long                  # full tracebacks
```

Tests are designed to run with no camera, no internet, no Pi. External boundaries are mocked:

| Boundary | How it's mocked |
|---|---|
| go2rtc camera frame | `tests/fixtures/frame.jpeg` returned by `responses` mock on `GET http://localhost:1984/api/frame.jpeg?src=grandma` |
| OpenRouter / VLM API | `unittest.mock.patch` or `responses` library on the HTTP POST |
| Pushover API | `unittest.mock.patch` on the send call |
| Config | `tests/fixtures/config_valid.yaml` or `tmp_path` + `yaml.dump` for edge cases |

Shared pytest fixtures live in `tests/conftest.py`:
- `fixture_frame_bytes` / `fixture_frame_path` — fixture JPEG bytes and path
- `safe_assessment` / `unsafe_assessment` — pre-built `AssessmentResult` instances
- `phase1_sensor_snapshot` — `SensorSnapshot` with both sensors disabled

## Pi Access

The Pi is on the same Tailscale network as the builder's Mac. SSH by Tailscale IP or hostname:

```bash
ssh pi@<tailscale-ip>
# or if mDNS is configured:
ssh pi@grandma-pi.local
```

Check service status:
```bash
systemctl status monitor web_server go2rtc cloudflared
```

View live logs:
```bash
journalctl -u monitor -f
journalctl -u web_server -f
```

## Deploying to Pi

No automated deploy pipeline yet. Sync changed files with `rsync`:

```bash
rsync -av --exclude='.git' --exclude='dataset/' --exclude='config.yaml' \
  /path/to/grandma-watcher/ pi@<tailscale-ip>:~/grandma-watcher/
```

Then restart the affected service:
```bash
ssh pi@<tailscale-ip> "sudo systemctl restart monitor"
```

`dataset/` is excluded — it lives on the Pi only. `config.yaml` is excluded — the Pi has its own copy with real keys.

## Smoke Testing on Pi

`smoke_test.py` is hardware-in-loop only. Run it manually after deploying changes to the Pi:

```bash
ssh pi@<tailscale-ip>
cd ~/grandma-watcher
python smoke_test.py
```

It fetches a real frame from go2rtc, calls the real OpenRouter API, and verifies an `AssessmentResult` is returned. Does not fire a real Pushover alert.

## Key Constraints

- **Never import `picamera2`** in application code — go2rtc owns the camera. Fetch frames via HTTP only.
- **`config.yaml` with real keys stays on the Pi** — use fixture configs for all tests.
- **All tests must pass offline** — no test should make real network requests.
- **`smoke_test.py` requires live Pi + real API keys** — not part of `make check`.

## Lessons Learned

<!-- Append dated one-liners below. -->
