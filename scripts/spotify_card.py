import base64
import html
import json
import os
import random
import re
import time
import urllib.request

PLAYLIST_ID = "37i9dQZF1EpwtGwNxZHUxC"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

# ── Layout constants for the animated progress / timer ────────────────────────
BAR_X, BAR_Y, BAR_W = 102, 92, 270   # progress bar geometry
TIME_X = 384                         # left edge of the "m:ss / m:ss" timer
CELL = 6.4                           # width of one monospace digit cell
LINE = 14                            # vertical pitch of a digit strip
BASE_Y = 96                          # text baseline of the timer
MAX_START_FRAC = 0.6                 # first play begins at a random point in 0..60% of the song


def fetch_url(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()

def get_playlist_tracks(playlist_id):
    embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
    page_html = fetch_url(embed_url).decode("utf-8", errors="ignore")
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page_html, re.DOTALL)
    if not match:
        raise RuntimeError("Could not locate __NEXT_DATA__ in Spotify embed page.")
    data = json.loads(match.group(1))
    return data["props"]["pageProps"]["state"]["data"]["entity"]["trackList"]

def get_cover_base64(track_id):
    try:
        oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
        oembed_data = json.loads(fetch_url(oembed_url).decode("utf-8"))
        img_bytes = fetch_url(oembed_data["thumbnail_url"])
        return "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode("ascii")
    except Exception:
        return ""

def truncate(text, limit):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def rolling_digit(idx, cx, digit_at, dur, start):
    """One digit of the ticking timer.

    The digits 0..n are stacked vertically inside a small clip window and the
    stack is shifted with a *discrete* SMIL animation, so exactly one digit is
    visible at a time and it flips on the exact second it should.
    `digit_at(t)` returns the digit to show `t` seconds into the track.
    """
    steps, prev = [], None
    for t in range(dur):
        v = digit_at(t)
        if v != prev:
            steps.append((t, v))
            prev = v

    # Digit never changes (e.g. the tens-of-minutes digit of a 3 min song)
    if len(steps) == 1:
        return f'<text x="{cx:.1f}" y="{BASE_Y}" text-anchor="middle">{steps[0][1]}</text>'

    top = max(v for _, v in steps)
    lines = "".join(
        f'<text x="{cx:.1f}" y="{BASE_Y + i * LINE}" text-anchor="middle">{i}</text>'
        for i in range(top + 1)
    )
    values = ";".join(f"0 {-v * LINE}" for _, v in steps)
    key_times = ";".join(f"{t / dur:.9f}" for t, _ in steps)
    rest = -digit_at(start) * LINE  # static frame if SMIL isn't supported

    return (
        f'<clipPath id="tick{idx}"><rect x="{cx - CELL / 2 - 0.6:.1f}" y="86.5" width="{CELL + 1.2:.1f}" height="13"/></clipPath>'
        f'<g clip-path="url(#tick{idx})"><g transform="translate(0 {rest})">{lines}'
        f'<animateTransform attributeName="transform" type="translate" calcMode="discrete" '
        f'values="{values}" keyTimes="{key_times}" begin="-{start}s" dur="{dur}s" repeatCount="indefinite"/>'
        f'</g></g>'
    )


def build_timer(dur, total_str, start):
    """Returns SVG for an 'm:ss / total' timer that counts up once per second."""
    n_min = len(str((dur - 1) // 60))  # number of minute digits needed
    parts, idx, x = [], 0, TIME_X

    for k in range(n_min):
        div = 10 ** (n_min - 1 - k)
        parts.append(rolling_digit(idx, x + CELL / 2, lambda t, d=div: (t // 60 // d) % 10, dur, start))
        idx += 1
        x += CELL

    parts.append(f'<text x="{x + 2:.1f}" y="{BASE_Y}" text-anchor="middle">:</text>')
    x += 4

    parts.append(rolling_digit(idx, x + CELL / 2, lambda t: (t % 60) // 10, dur, start))
    idx += 1
    x += CELL
    parts.append(rolling_digit(idx, x + CELL / 2, lambda t: t % 10, dur, start))
    x += CELL

    return (
        f'<g class="mono" font-size="10.5" fill="#a6adc8">{"".join(parts)}</g>'
        f'<text x="{x + 3:.1f}" y="{BASE_Y}" class="mono" font-size="10.5" fill="#6c7086">/ {total_str}</text>'
    )


def generate_svg(track):
    uri = track.get("uri", "spotify:track:0")
    track_id = uri.split(":")[-1]
    title = html.escape(truncate(track.get("title", "Unknown Track"), 32))
    artist = html.escape(truncate(track.get("subtitle", "Unknown Artist"), 38))

    duration_ms = track.get("duration") or 180000
    dur = max(1, int(duration_ms // 1000))   # whole seconds, drives every animation
    mins, secs = divmod(dur, 60)
    duration_str = f"{mins}:{secs:02d}"

    cover_data = get_cover_base64(track_id)
    cover_element = (
        f'<image x="18" y="36" width="68" height="68" rx="8" clip-path="url(#art-clip)" href="{cover_data}"/>'
        if cover_data
        else '<rect x="18" y="36" width="68" height="68" rx="8" fill="#313244"/>'
    )

    # First play starts part-way through so it doesn't look like the song began at page load.
    # Negative `begin` = "this animation started N seconds ago"; later loops run from 0:00.
    start = random.randint(0, int(dur * MAX_START_FRAC))
    timer = build_timer(dur, duration_str, start)
    fb_w = BAR_W * start / dur
    fb_x = BAR_X + fb_w
    bar_end = BAR_X + BAR_W

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 120" width="480" height="120">
  <defs>
    <clipPath id="art-clip">
      <rect x="18" y="36" width="68" height="68" rx="8"/>
    </clipPath>
    <linearGradient id="bar-grad" gradientUnits="userSpaceOnUse" x1="{BAR_X}" y1="0" x2="{bar_end}" y2="0">
      <stop offset="0" stop-color="#cba6f7"/>
      <stop offset="1" stop-color="#89b4fa"/>
    </linearGradient>
    <style>
      .card {{ fill: #1e1e2e; stroke: #313244; stroke-width: 2; }}
      .top {{ fill: #181825; }}
      .mono {{ font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace; }}
      .sans {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    </style>
  </defs>

  <rect class="card" x="1" y="1" width="478" height="118" rx="10"/>
  <path class="top" d="M 11 2 H 469 A 9 9 0 0 1 478 11 V 26 H 2 V 11 A 9 9 0 0 1 11 2 Z"/>
  <line x1="2" y1="26" x2="478" y2="26" stroke="#313244" stroke-width="1"/>

  <!-- Header Prompt: pulsing status dot + blinking cursor -->
  <circle cx="16" cy="14" r="4" fill="#a6e3a1">
    <animate attributeName="opacity" values="1;0.35;1" dur="2s" repeatCount="indefinite"/>
  </circle>
  <text x="28" y="18" class="mono" font-size="10.5" fill="#a6adc8">
    spotifyd --playlist <tspan fill="#cba6f7">{PLAYLIST_ID[:10]}…</tspan> <tspan fill="#6c7086">[rotates 3h]</tspan><tspan fill="#a6e3a1">_<animate attributeName="fill-opacity" values="1;0" keyTimes="0;0.5" calcMode="discrete" dur="1.1s" repeatCount="indefinite"/></tspan>
  </text>

  <!-- Album Cover -->
  {cover_element}

  <!-- Track Metadata -->
  <text x="102" y="55" class="sans" font-size="15" font-weight="700" fill="#cdd6f4">{title}</text>
  <text x="102" y="75" class="sans" font-size="12.5" fill="#a6adc8">{artist}</text>

  <!-- Progress Bar: fills over the track's real duration, then restarts from 0:00 -->
  <rect x="{BAR_X}" y="{BAR_Y}" width="{BAR_W}" height="4" rx="2" fill="#313244"/>
  <rect x="{BAR_X}" y="{BAR_Y}" width="{fb_w:.1f}" height="4" rx="2" fill="url(#bar-grad)">
    <animate attributeName="width" from="0" to="{BAR_W}" begin="-{start}s" dur="{dur}s" repeatCount="indefinite"/>
  </rect>
  <!-- Playhead -->
  <circle cx="{fb_x:.1f}" cy="{BAR_Y + 2}" r="3.5" fill="#cdd6f4">
    <animate attributeName="cx" from="{BAR_X}" to="{bar_end}" begin="-{start}s" dur="{dur}s" repeatCount="indefinite"/>
  </circle>

  <!-- Ticking timer: elapsed counts up every second / total -->
  {timer}

  <!-- Baseline-Locked Equalizer Bars (Bottom locked at y=58) -->
  <g fill="#a6e3a1">
    <rect x="438" y="48" width="3" height="10" rx="1.5">
      <animate attributeName="y" values="52;45;50;43;52" dur="1.3s" repeatCount="indefinite"/>
      <animate attributeName="height" values="6;13;8;15;6" dur="1.3s" repeatCount="indefinite"/>
    </rect>
    <rect x="444" y="44" width="3" height="14" rx="1.5">
      <animate attributeName="y" values="45;53;44;51;45" dur="1.1s" repeatCount="indefinite"/>
      <animate attributeName="height" values="13;5;14;7;13" dur="1.1s" repeatCount="indefinite"/>
    </rect>
    <rect x="450" y="50" width="3" height="8" rx="1.5">
      <animate attributeName="y" values="51;43;52;46;51" dur="1.5s" repeatCount="indefinite"/>
      <animate attributeName="height" values="7;15;6;12;7" dur="1.5s" repeatCount="indefinite"/>
    </rect>
    <rect x="456" y="47" width="3" height="11" rx="1.5">
      <animate attributeName="y" values="46;53;48;54;46" dur="1.2s" repeatCount="indefinite"/>
      <animate attributeName="height" values="12;5;10;4;12" dur="1.2s" repeatCount="indefinite"/>
    </rect>
  </g>
</svg>'''

def main():
    tracks = get_playlist_tracks(PLAYLIST_ID)
    if not tracks:
        raise RuntimeError("No tracks returned from playlist.")

    slot = int(time.time() // 10800)
    rng = random.Random(slot)
    chosen = rng.choice(tracks)

    os.makedirs("dist", exist_ok=True)
    svg_content = generate_svg(chosen)
    with open("dist/spotify.svg", "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Rendered: {chosen.get('title')} - {chosen.get('subtitle')}")

if __name__ == "__main__":
    main()
        
