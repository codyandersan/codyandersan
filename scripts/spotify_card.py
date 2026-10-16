import base64
import html
import json
import os
import random
import re
import time
import urllib.request

PLAYLIST_ID = "3QIalaAOvvSPAQ9GT967nL"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

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

def generate_svg(track):
    uri = track.get("uri", "spotify:track:0")
    track_id = uri.split(":")[-1]
    title = html.escape(truncate(track.get("title", "Unknown Track"), 32))
    artist = html.escape(truncate(track.get("subtitle", "Unknown Artist"), 38))
    
    duration_ms = track.get("duration", 180000)
    mins, secs = divmod(duration_ms // 1000, 60)
    duration_str = f"{mins}:{secs:02d}"
    
    cover_data = get_cover_base64(track_id)
    cover_element = (
        f'<image x="18" y="36" width="68" height="68" rx="8" clip-path="url(#art-clip)" href="{cover_data}"/>'
        if cover_data
        else '<rect x="18" y="36" width="68" height="68" rx="8" fill="#313244"/>'
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 120" width="480" height="120">
  <defs>
    <clipPath id="art-clip">
      <rect x="18" y="36" width="68" height="68" rx="8"/>
    </clipPath>
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

  <!-- Header Prompt -->
  <circle cx="16" cy="14" r="4" fill="#a6e3a1"/>
  <text x="28" y="18" class="mono" font-size="10.5" fill="#a6adc8">
    spotifyd --playlist <tspan fill="#cba6f7">{PLAYLIST_ID[:10]}…</tspan> <tspan fill="#6c7086">[rotates 3h]</tspan>
  </text>

  <!-- Album Cover -->
  {cover_element}

  <!-- Track Metadata -->
  <text x="102" y="55" class="sans" font-size="15" font-weight="700" fill="#cdd6f4">{title}</text>
  <text x="102" y="75" class="sans" font-size="12.5" fill="#a6adc8">{artist}</text>

  <!-- Progress Bar -->
  <rect x="102" y="92" width="290" height="4" rx="2" fill="#313244"/>
  <rect x="102" y="92" width="165" height="4" rx="2" fill="#cba6f7"/>
  <text x="402" y="96" class="mono" font-size="10.5" fill="#6c7086">{duration_str}</text>

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
