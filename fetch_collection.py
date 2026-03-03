#!/usr/bin/env python3
"""
VinylVisualizer — Discogs Collection Dashboard Generator
=========================================================
Run this script to generate collection_dashboard.html from your Discogs collection.

Requirements:
    pip install requests python-dotenv

Setup:
    1. Copy .env.example to .env
    2. Paste your Discogs token into .env
    3. Run: python fetch_collection.py
"""

import argparse
import os
import json
import time
import sys
import re
import requests
from datetime import datetime
from urllib.parse import quote_plus
from dotenv import load_dotenv

# ── Configuration ──────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

TOKEN      = os.getenv("DISCOGS_TOKEN")
USERNAME   = "jack.warren"
BASE_URL   = "https://api.discogs.com"
OUTPUT     = os.path.join(SCRIPT_DIR, "collection_dashboard.html")
CACHE_FILE         = os.path.join(SCRIPT_DIR, "price_cache.json")
RELEASE_CACHE_FILE = os.path.join(SCRIPT_DIR, "release_cache.json")

if not TOKEN:
    print("ERROR: DISCOGS_TOKEN not found.")
    print("  1. Copy .env.example to a new file named .env")
    print("  2. Open .env and replace 'your_personal_access_token_here' with your real token")
    print("  3. Get a token at: discogs.com → Settings → Developers → Generate Token")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Discogs token={TOKEN}",
    "User-Agent":    "VinylVisualizer/1.0",
}

# ── Price cache ─────────────────────────────────────────────────────────────────

def load_price_cache():
    """Load the price cache from disk. Returns empty dict if not found."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_price_cache(cache):
    """Persist the price cache to disk."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def fetch_prices(records):
    """
    Fetch Discogs marketplace stats for each record and set record['price'].
    Uses a local cache (price_cache.json) to avoid redundant API calls.
    Modifies records in-place.
    """
    cache    = load_price_cache()
    uncached = [r for r in records if str(r["id"]) not in cache]

    if uncached:
        print(f"\nFetching prices for {len(uncached)} record(s) — this may take a minute...")
        for i, r in enumerate(uncached, 1):
            release_id = r["id"]
            print(f"  Fetching prices... {i}/{len(uncached)}", end="\r")
            url = f"{BASE_URL}/marketplace/stats/{release_id}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 429:
                    print(f"\n  Rate limit hit. Waiting 60 seconds...")
                    time.sleep(60)
                    resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 200:
                    stats      = resp.json()
                    median_obj = stats.get("median")
                    lowest_obj = stats.get("lowest_price")
                    median_val = median_obj["value"] if median_obj else None
                    lowest_val = lowest_obj["value"] if lowest_obj else None
                else:
                    median_val = None
                    lowest_val = None
            except Exception:
                median_val = None
                lowest_val = None

            cache[str(release_id)] = {
                "median":     median_val,
                "lowest":     lowest_val,
                "fetched_at": datetime.now().date().isoformat(),
            }
            time.sleep(0.5)

        print(f"\n  Done — {len(uncached)} price(s) fetched and cached.")
        save_price_cache(cache)
    else:
        print(f"Prices loaded from cache ({len(cache)} records cached).")

    # Apply cached prices to records
    for r in records:
        entry    = cache.get(str(r["id"]), {})
        price    = entry.get("median") or entry.get("lowest")
        r["price"] = price


# ── Release cache ───────────────────────────────────────────────────────────────

def load_release_cache():
    """Load the release cache from disk. Returns empty dict if not found."""
    if os.path.exists(RELEASE_CACHE_FILE):
        try:
            with open(RELEASE_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_release_cache(cache):
    """Persist the release cache to disk."""
    with open(RELEASE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def fetch_tracklists(records):
    """Fetch full release info (tracklist, country, notes) for each record. Cached."""
    cache    = load_release_cache()
    uncached = [r for r in records if str(r["id"]) not in cache]

    if uncached:
        print(f"\nFetching tracklists for {len(uncached)} record(s)...")
        for i, r in enumerate(uncached, 1):
            print(f"  {i}/{len(uncached)}", end="\r")
            url = f"{BASE_URL}/releases/{r['id']}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 429:
                    print(f"\n  Rate limit hit. Waiting 60 seconds...")
                    time.sleep(60)
                    resp = requests.get(url, headers=HEADERS, timeout=15)
                d = resp.json() if resp.status_code == 200 else {}
                fmt_parts = []
                for f in d.get("formats", []):
                    parts = [f.get("name", "")]
                    parts += f.get("descriptions", [])
                    fmt_parts.append(", ".join(p for p in parts if p))
                formats_str = " / ".join(fmt_parts) or ""
                cache[str(r["id"])] = {
                    "tracklist":  [{"pos": t.get("position", ""), "title": t.get("title", ""),
                                    "dur": t.get("duration", "")}
                                   for t in d.get("tracklist", []) if t.get("type_", "track") == "track"],
                    "country":    d.get("country", ""),
                    "notes":      (d.get("notes", "") or "")[:400],
                    "formats":    formats_str,
                    "released":   d.get("released", ""),
                    "fetched_at": datetime.now().date().isoformat(),
                }
            except Exception:
                cache[str(r["id"])] = {"tracklist": [], "country": "", "notes": "",
                                       "formats": "", "released": "", "fetched_at": ""}
            time.sleep(0.5)
        save_release_cache(cache)
        print(f"\n  Done.")
    else:
        print(f"Release data loaded from cache ({len(cache)} records).")

    for r in records:
        entry = cache.get(str(r["id"]), {})
        r["tracklist"] = entry.get("tracklist", [])
        r["country"]   = entry.get("country", "")
        r["notes"]     = entry.get("notes", "")
        r["formats"]   = entry.get("formats", "")
        r["released"]  = entry.get("released", "")


# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch_collection():
    """Fetch every release in the Discogs collection, handling pagination."""
    releases    = []
    page        = 1
    total_pages = None

    print(f"\nConnecting to Discogs for user '{USERNAME}'...")

    while True:
        url    = f"{BASE_URL}/users/{USERNAME}/collection/folders/0/releases"
        params = {"page": page, "per_page": 100, "sort": "added", "sort_order": "desc"}

        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            resp.raise_for_status()

        except requests.HTTPError:
            code = resp.status_code
            print(f"\nHTTP {code} error from Discogs.")
            if code == 401:
                print("  Your token is invalid or expired. Check your .env file.")
            elif code == 404:
                print(f"  User '{USERNAME}' not found, or their collection is private.")
            elif code == 429:
                print("  Rate limit hit. Waiting 60 seconds and retrying...")
                time.sleep(60)
                continue
            else:
                print(f"  Response: {resp.text[:200]}")
            sys.exit(1)

        except requests.ConnectionError:
            print("\nCannot reach Discogs. Check your internet connection.")
            sys.exit(1)

        data       = resp.json()
        pagination = data["pagination"]

        if total_pages is None:
            total_pages = pagination["pages"]
            total_items = pagination["items"]
            print(f"Found {total_items} records across {total_pages} page(s).\n")

        releases.extend(data["releases"])
        print(f"  Page {page}/{total_pages} loaded  ({len(releases)} records so far)")

        if page >= total_pages:
            break

        page += 1
        time.sleep(0.5)   # Stay well within Discogs' 60 req/min rate limit

    print(f"\nAll done — {len(releases)} records fetched.\n")
    return releases


# ── Process ────────────────────────────────────────────────────────────────────

def clean_artist(name):
    """Strip Discogs disambiguation suffixes like 'The Beatles (2)'."""
    return re.sub(r"\s*\(\d+\)$", "", name).strip()


def process_collection(releases):
    """Aggregate raw release data into dashboard-ready structures."""
    genres  = {}
    decades = {}
    records = []

    for r in releases:
        info = r["basic_information"]

        raw    = info["artists"][0]["name"] if info.get("artists") else "Unknown Artist"
        artist = clean_artist(raw)

        year   = info.get("year") or 0

        # Genre tallies — count only the first genre tag per record
        genre_list    = info.get("genres") or ["Unknown"]
        primary_genre = genre_list[0]
        genres[primary_genre] = genres.get(primary_genre, 0) + 1

        # Decade tallies (ignore garbage years)
        if 1900 < year <= 2030:
            decade = f"{(year // 10) * 10}s"
            decades[decade] = decades.get(decade, 0) + 1

        # eBay search URL as price fallback (pre-built, no API key needed)
        ebay_query = quote_plus(f"{info.get('title', '')} {artist} vinyl")
        ebay_url   = f"https://www.ebay.com/sch/i.html?_nkw={ebay_query}&LH_Sold=1&LH_Complete=1"

        records.append({
            "id":          info.get("id"),
            "title":       info.get("title", "Untitled"),
            "artist":      artist,
            "year":        year if year else None,
            "genres":      info.get("genres", []),
            "styles":      info.get("styles", []),
            "labels":      [l["name"] for l in info.get("labels", [])][:2],
            "price":       None,       # populated later by fetch_prices()
            "ebay_url":    ebay_url,
            "date_added":  r.get("date_added", ""),
            "thumb":       info.get("thumb", ""),
            "cover_image": info.get("cover_image", ""),
        })

    sorted_decades = dict(sorted(decades.items(), key=lambda x: int(x[0][:-1])))
    genres = dict(sorted(genres.items(), key=lambda x: x[1], reverse=True))

    top_genre  = max(genres, key=genres.get) if genres else "Unknown"
    years      = [r["year"] for r in records if r["year"]]
    year_range = f"{min(years)}\u2013{max(years)}" if years else "Unknown"

    current_year    = datetime.now().year
    added_this_year = [r for r in records
                       if r.get("date_added", "").startswith(str(current_year))]

    return {
        "username":            USERNAME,
        "total":               len(releases),
        "top_genre":           top_genre,
        "year_range":          year_range,
        "genres":              genres,
        "decades":             sorted_decades,
        "all_records":         records,
        "recent_20":           records[:20],
        "generated_at":        datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        "current_year":        current_year,
        "added_this_year_count": len(added_this_year),
        "added_this_year":     added_this_year,
        # Price-dependent fields — computed in main() after fetch_prices()
        "total_value":         0.0,
        "priced_count":        0,
        "unpriced_count":      len(releases),
        "top_10":              [],
    }


# ── HTML generation ────────────────────────────────────────────────────────────

def generate_html(data):
    """Build and return the complete self-contained HTML dashboard string."""

    json_blob = json.dumps(data)

    # ── Stats block (Python values interpolated here) ──────────────────────
    total_label  = f"{data['total']:,}"
    added_label  = f"{data['added_this_year_count']:,}"
    current_year = data['current_year']
    stats_html = f"""
        <div class="stat-card accent-amber clickable-card"
             onclick="openCollectionModal()"
             title="Click to browse all records">
          <div class="stat-label">Total Records</div>
          <div class="stat-value">{data['total']:,}</div>
          <div class="stat-sub">{data['year_range']}</div>
        </div>
        <div class="stat-card accent-green clickable-card"
             onclick="openValueModal()"
             title="Click to view collection by value">
          <div class="stat-label">Estimated Value</div>
          <div class="stat-value">${data['total_value']:,.0f}</div>
          <div class="stat-sub">{data['priced_count']} of {data['total']} records priced (Discogs median)</div>
        </div>
        <div class="stat-card accent-indigo">
          <div class="stat-label">Top Genre</div>
          <div class="stat-value genre-val">{data['top_genre']}</div>
          <div class="stat-sub">{data['genres'].get(data['top_genre'], 0)} records</div>
        </div>
        <div class="stat-card accent-red clickable-card"
             onclick="openModal('Added in {current_year} \u2014 {added_label} records', DATA.added_this_year)"
             title="Click to view records added in {current_year}">
          <div class="stat-label">Added This Year</div>
          <div class="stat-value">{added_label}</div>
          <div class="stat-sub">Records added in {current_year}</div>
        </div>
    """

    meta_html = f"""
        <div>Generated {data['generated_at']}</div>
        <div style="margin-top:4px">{data['total']:,} records &middot; {data['priced_count']} priced</div>
    """

    footer_html = (
        f"VinylVisualizer &middot; Data from "
        f"<a href='https://www.discogs.com' style='color:var(--amber)'>Discogs</a> &middot; "
        f"Prices = Discogs marketplace median &middot; "
        f"Generated {data['generated_at']}"
    )

    # ── JavaScript (plain string — no f-string brace conflicts) ───────────
    js = (
        "const DATA = " + json_blob + ";\n"
        """
const PALETTE = [
  '#f59e0b','#6366f1','#10b981','#ef4444','#3b82f6',
  '#ec4899','#14b8a6','#f97316','#8b5cf6','#22c55e','#facc15','#06b6d4',
];

// ── Escape HTML to prevent XSS ─────────────────────────────────────────────
function esc(s) {
  return String(s || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Record card builder (shared by Recent + Modal) ────────────────────────
function makeCard(r) {
  const art        = r.cover_image || r.thumb;
  const discogsUrl = r.id ? 'https://www.discogs.com/release/' + r.id : '';
  const date = r.date_added
    ? new Date(r.date_added).toLocaleDateString('en-US',
        { month: 'short', day: 'numeric', year: 'numeric' })
    : '';
  const imgTag = art
    ? `<img class="card-art" src="${esc(art)}" alt=""
           onerror="this.outerHTML='<div class=\\'card-art no-art\\'>&#9835;</div>'">`
    : `<div class="card-art no-art">&#9835;</div>`;
  const artHtml = discogsUrl
    ? `<a href="${esc(discogsUrl)}" target="_blank" rel="noopener" class="art-link">${imgTag}</a>`
    : imgTag;
  const genre = r.genres[0]
    ? `<span class="badge small-badge">${esc(r.genres[0])}</span>` : '';
  let priceHtml = '';
  if (r.price != null) {
    priceHtml = `<div class="card-price">$${r.price.toFixed(2)}</div>`;
  } else if (r.ebay_url) {
    priceHtml = `<a href="${esc(r.ebay_url)}" target="_blank" rel="noopener" class="ebay-link">Search eBay \u2197</a>`;
  }
  const ytQ   = encodeURIComponent(r.artist + ' ' + r.title + ' full album');
  const ytUrl = 'https://www.youtube.com/results?search_query=' + ytQ;
  const ytBtn = `<a href="${esc(ytUrl)}" target="_blank" rel="noopener" class="yt-card-btn"
    title="Search YouTube for this album">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
      <path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.5a3 3 0 0 0-2.1 2.1C0 8.1 0 12 0 12s0 3.9.5 5.8a3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1C24 15.9 24 12 24 12s0-3.9-.5-5.8zM9.75 15.5V8.5l6.25 3.5-6.25 3.5z"/>
    </svg>
    YouTube
  </a>`;
  return `
    <div class="recent-card">
      ${artHtml}
      <div class="card-info">
        <div class="rec-title ellipsis" title="${esc(r.title)}"
          style="cursor:pointer" onclick="openDetailModal(DATA.all_records.find(x=>x.id===${r.id}))">${esc(r.title)}</div>
        <div class="rec-artist ellipsis">${esc(r.artist)}</div>
        ${genre}
        ${priceHtml}
        ${ytBtn}
        <div class="card-date">${date ? 'Added ' + date : ''}</div>
      </div>
    </div>`;
}

// ── Modal ──────────────────────────────────────────────────────────────────
function openModal(title, records) {
  document.getElementById('modalTitle').textContent = title;
  const grid = document.getElementById('modalGrid');
  grid.innerHTML = records.map(makeCard).join('');
  const modal = document.getElementById('modal');
  modal.classList.add('open');
  modal.scrollTop = 0;
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  document.getElementById('modal').classList.remove('open');
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeModal(); closeDetail(); } });

// ── Search ─────────────────────────────────────────────────────────────────
const searchInput    = document.getElementById('searchInput');
const searchDropdown = document.getElementById('searchDropdown');

searchInput.addEventListener('input', function() {
  const q = this.value.trim().toLowerCase();
  if (q.length < 2) { searchDropdown.classList.remove('open'); return; }
  const hits = DATA.all_records.filter(r =>
    r.title.toLowerCase().includes(q) || r.artist.toLowerCase().includes(q)
  ).slice(0, 8);
  if (!hits.length) {
    searchDropdown.innerHTML = '<div class="search-no-results">No records found</div>';
  } else {
    searchDropdown.innerHTML = hits.map(r => {
      const art = r.thumb || r.cover_image;
      const img = art
        ? `<img src="${esc(art)}" alt="" onerror="this.style.display='none'">`
        : `<div class="search-result-noimg">&#9835;</div>`;
      return `<div class="search-result" onclick="openDetailModal(DATA.all_records.find(x=>x.id===${r.id})); clearSearch();">
        ${img}
        <div class="search-result-info">
          <div class="sr-title">${esc(r.title)}</div>
          <div class="sr-artist">${esc(r.artist)}</div>
        </div>
      </div>`;
    }).join('');
  }
  searchDropdown.classList.add('open');
});

document.addEventListener('click', e => {
  if (!document.getElementById('searchWrap').contains(e.target)) {
    searchDropdown.classList.remove('open');
  }
});

function clearSearch() {
  searchInput.value = '';
  searchDropdown.classList.remove('open');
}

// ── Album Detail Modal ─────────────────────────────────────────────────────
function openDetailModal(r) {
  if (!r) return;
  document.getElementById('detailTitle').textContent = r.title;
  const art = r.cover_image || r.thumb;
  const ytQuery = encodeURIComponent(r.artist + ' ' + r.title + ' full album');
  const ytUrl   = 'https://www.youtube.com/results?search_query=' + ytQuery;
  const discogsUrl = r.id ? 'https://www.discogs.com/release/' + r.id : '';

  const artHtml = art
    ? `<img class="detail-art" src="${esc(art)}" alt="">`
    : `<div class="detail-no-art">&#9835;</div>`;

  const badges = [...(r.genres||[]), ...(r.styles||[])].map(
    g => `<span class="badge">${esc(g)}</span>`).join('');

  const fields = [
    r.year     ? `<div class="detail-field">Year: <span>${r.year}</span></div>` : '',
    r.released ? `<div class="detail-field">Released: <span>${esc(r.released)}</span></div>` : '',
    r.country  ? `<div class="detail-field">Country: <span>${esc(r.country)}</span></div>` : '',
    r.formats  ? `<div class="detail-field">Format: <span>${esc(r.formats)}</span></div>` : '',
    r.labels && r.labels.length
               ? `<div class="detail-field">Label: <span>${esc(r.labels.join(', '))}</span></div>` : '',
    r.price != null
               ? `<div class="detail-field">Est. Value: <span style="color:var(--green)">$${r.price.toFixed(2)}</span></div>` : '',
  ].join('');

  const actions = [
    discogsUrl ? `<a href="${esc(discogsUrl)}" target="_blank" rel="noopener" class="detail-btn">
      Discogs &#8599;</a>` : '',
    `<a href="${esc(ytUrl)}" target="_blank" rel="noopener" class="detail-btn yt">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.5a3 3 0 0 0-2.1 2.1C0 8.1 0 12 0 12s0 3.9.5 5.8a3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1C24 15.9 24 12 24 12s0-3.9-.5-5.8zM9.75 15.5V8.5l6.25 3.5-6.25 3.5z"/>
      </svg>
      YouTube</a>`,
    r.ebay_url ? `<a href="${esc(r.ebay_url)}" target="_blank" rel="noopener" class="detail-btn">
      Search eBay &#8599;</a>` : '',
  ].join('');

  let tracklistHtml = '';
  if (r.tracklist && r.tracklist.length) {
    const rows = r.tracklist.map(t =>
      `<tr><td class="tl-pos">${esc(t.pos)}</td><td>${esc(t.title)}</td><td class="tl-dur">${esc(t.dur)}</td></tr>`
    ).join('');
    tracklistHtml = `
      <div class="tracklist-title">Tracklist</div>
      <table class="tracklist"><tbody>${rows}</tbody></table>`;
  }

  document.getElementById('detailBody').innerHTML = `
    <div class="detail-hero">
      ${artHtml}
      <div class="detail-meta">
        <div class="detail-title">${esc(r.title)}</div>
        <div class="detail-artist">${esc(r.artist)}</div>
        <div class="detail-badges">${badges}</div>
        ${fields}
        <div class="detail-actions">${actions}</div>
      </div>
    </div>
    ${tracklistHtml}`;

  const dm = document.getElementById('detailModal');
  dm.classList.add('open');
  dm.scrollTop = 0;
  document.body.style.overflow = 'hidden';
}

function closeDetail() {
  document.getElementById('detailModal').classList.remove('open');
  document.body.style.overflow = '';
}

// ── Random Record ──────────────────────────────────────────────────────────
function openRandomRecord() {
  const r = DATA.all_records[Math.floor(Math.random() * DATA.all_records.length)];
  openDetailModal(r);
}

// ── Last-name extractor for alphabetical sort ──────────────────────────────
function lastName(artist) {
  const cleaned = artist.replace(/^the\\s+/i, '').trim();
  const parts   = cleaned.split(/\\s+/);
  return parts[parts.length - 1].toLowerCase();
}

// ── Named modal openers ────────────────────────────────────────────────────
function openCollectionModal() {
  const sorted = [...DATA.all_records].sort((a, b) => {
    const la = lastName(a.artist), lb = lastName(b.artist);
    if (la !== lb) return la < lb ? -1 : 1;
    return (a.year || 9999) - (b.year || 9999);
  });
  openModal('Full Collection \u2014 ' + DATA.all_records.length + ' records', sorted);
}

function openValueModal() {
  const priced = DATA.all_records
    .filter(r => r.price != null)
    .sort((a, b) => b.price - a.price);
  openModal('Collection by Value \u2014 ' + priced.length + ' priced records', priced);
}

// ── Top 10 Table ───────────────────────────────────────────────────────────
(function() {
  const tbody  = document.getElementById('top10Body');
  const medals = { 1: '🥇', 2: '🥈', 3: '🥉' };
  DATA.top_10.forEach((r, i) => {
    const rank  = i + 1;
    const label = medals[rank] || '#' + rank;
    const art        = r.cover_image || r.thumb;
    const discogsUrl = r.id ? 'https://www.discogs.com/release/' + r.id : '';
    const imgTag  = art
      ? `<img src="${esc(art)}" class="thumb" alt=""
             onerror="this.outerHTML='<div class=\\'no-thumb\\'>&#9835;</div>'">`
      : `<div class="no-thumb">&#9835;</div>`;
    const artHtml = discogsUrl
      ? `<a href="${esc(discogsUrl)}" target="_blank" rel="noopener">${imgTag}</a>`
      : imgTag;
    const genre = r.genres[0] ? `<span class="badge">${esc(r.genres[0])}</span>` : '';
    const priceCell = r.price != null
      ? `<span class="price">$${r.price.toFixed(2)}</span>`
      : (r.ebay_url
          ? `<a href="${esc(r.ebay_url)}" target="_blank" rel="noopener" class="ebay-link">Search eBay \u2197</a>`
          : `<span class="muted small">Not listed</span>`);
    const ytQ10   = encodeURIComponent(r.artist + ' ' + r.title + ' full album');
    const ytUrl10 = 'https://www.youtube.com/results?search_query=' + ytQ10;
    const ytCell  = `<a href="${esc(ytUrl10)}" target="_blank" rel="noopener"
      style="display:inline-flex;align-items:center;gap:4px;font-size:0.75rem;color:#ff0000;text-decoration:none;"
      title="Search YouTube">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
        <path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.5a3 3 0 0 0-2.1 2.1C0 8.1 0 12 0 12s0 3.9.5 5.8a3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1C24 15.9 24 12 24 12s0-3.9-.5-5.8zM9.75 15.5V8.5l6.25 3.5-6.25 3.5z"/>
      </svg> YouTube</a>`;
    tbody.innerHTML += `
      <tr>
        <td class="rank rank-${rank}">${label}</td>
        <td>${artHtml}</td>
        <td>
          <div class="rec-title">${esc(r.title)}</div>
          <div class="rec-artist">${esc(r.artist)}</div>
        </td>
        <td class="muted small">${r.year || '&mdash;'}</td>
        <td>${genre}</td>
        <td>${priceCell}</td>
        <td>${ytCell}</td>
      </tr>`;
  });
}());

// ── Recent Cards ───────────────────────────────────────────────────────────
(function() {
  const grid = document.getElementById('recentGrid');
  DATA.recent_20.forEach(r => { grid.innerHTML += makeCard(r); });
}());

// ── Charts (guarded — Chart.js loaded from CDN, may be blocked) ────────────
if (typeof Chart !== 'undefined') {

// ── Genre Donut ────────────────────────────────────────────────────────────
(function() {
  const labels = Object.keys(DATA.genres);
  const values = Object.values(DATA.genres);
  new Chart(document.getElementById('genreChart'), {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: PALETTE,
        borderWidth: 2,
        borderColor: '#1c1c1c',
        hoverOffset: 8,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: (evt, elements) => {
        if (!elements.length) return;
        const genre    = labels[elements[0].index];
        const filtered = DATA.all_records.filter(r => r.genres[0] === genre);
        openModal('"' + genre + '" \u2014 ' + filtered.length + ' records', filtered);
      },
      plugins: {
        legend: {
          position: 'right',
          labels: { color: '#d0d0d0', boxWidth: 12, padding: 14, font: { size: 12 } }
        },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed} records`
          }
        }
      }
    }
  });
}());

// ── Decade Bar ─────────────────────────────────────────────────────────────
(function() {
  const labels = Object.keys(DATA.decades);
  const values = Object.values(DATA.decades);
  new Chart(document.getElementById('decadeChart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Records',
        data: values,
        backgroundColor: labels.map((_, i) => PALETTE[i % PALETTE.length] + 'bb'),
        borderColor:      labels.map((_, i) => PALETTE[i % PALETTE.length]),
        borderWidth: 1,
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: (evt, elements) => {
        if (!elements.length) return;
        const decade      = labels[elements[0].index];
        const decadeStart = parseInt(decade);
        const filtered    = DATA.all_records.filter(r =>
          r.year && Math.floor(r.year / 10) * 10 === decadeStart
        );
        openModal('"The ' + decade + '" \u2014 ' + filtered.length + ' records', filtered);
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y} records` } }
      },
      scales: {
        x: { ticks: { color: '#777' }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y: { ticks: { color: '#777', precision: 0 }, grid: { color: 'rgba(255,255,255,0.04)' } }
      }
    }
  });
}());

} else {
  // Chart.js CDN failed (e.g. content blocker) — show a message in each chart area
  document.querySelectorAll('.chart-card').forEach(function(card) {
    var wrap = card.querySelector('.chart-wrap');
    if (wrap) wrap.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#777;font-size:0.85rem;text-align:center;padding:20px;">Charts unavailable\u2014enable external scripts\u00a0(jsDelivr CDN)</div>';
  });
}
"""
    )

    # ── Full HTML document ─────────────────────────────────────────────────
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>VinylVisualizer &mdash; """ + data["username"] + """'s Collection</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:       #111111;
      --surface:  #1c1c1c;
      --surface2: #242424;
      --border:   #2e2e2e;
      --text:     #f0f0f0;
      --muted:    #777777;
      --amber:    #f59e0b;
      --indigo:   #6366f1;
      --green:    #10b981;
      --red:      #ef4444;
      --radius:   14px;
      --shadow:   0 8px 40px rgba(0,0,0,0.6);
    }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      line-height: 1.6;
      min-height: 100vh;
      padding-left: env(safe-area-inset-left);
      padding-right: env(safe-area-inset-right);
      -webkit-tap-highlight-color: transparent;
    }

    a { color: var(--amber); }

    /* ── Layout ──────────────────────────────────────────────────────────── */
    .wrap  { max-width: 1380px; margin: 0 auto; padding: 0 28px; }
    main   { padding: 44px 0 60px; }
    section { margin-bottom: 52px; }

    /* ── Header ──────────────────────────────────────────────────────────── */
    header {
      background: linear-gradient(170deg, #1a0d00 0%, #111 55%);
      border-bottom: 1px solid var(--border);
      padding: 36px 0 28px;
    }
    header .wrap {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    .logo { display: flex; align-items: center; gap: 18px; }

    /* Spinning vinyl disc */
    .vinyl {
      width: 58px; height: 58px; flex-shrink: 0;
      border-radius: 50%;
      background: repeating-conic-gradient(#222 0deg 20deg, #2a2a2a 20deg 40deg);
      box-shadow: 0 0 0 6px #1a1a1a, 0 0 0 8px #2e2e2e, 0 0 20px rgba(0,0,0,0.8);
      position: relative;
      animation: spin 5s linear infinite;
    }
    .vinyl::after {
      content: '';
      position: absolute; top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      width: 16px; height: 16px;
      border-radius: 50%;
      background: var(--amber);
      box-shadow: 0 0 6px rgba(245,158,11,0.5);
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    header h1 {
      font-size: 1.9rem; font-weight: 800;
      letter-spacing: -0.5px;
      color: var(--amber);
    }
    .subtitle { color: var(--muted); font-size: 0.9rem; margin-top: 3px; }
    .header-meta { text-align: right; color: var(--muted); font-size: 0.82rem; }

    /* ── Section headings ────────────────────────────────────────────────── */
    .section-title {
      font-size: 1.1rem; font-weight: 700;
      margin-bottom: 18px;
      display: flex; align-items: center; gap: 10px;
    }
    .section-title::before {
      content: ''; display: inline-block;
      width: 4px; height: 18px;
      background: var(--amber); border-radius: 2px;
    }

    /* ── Stat cards ──────────────────────────────────────────────────────── */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 16px;
    }
    .stat-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 22px 24px;
      position: relative; overflow: hidden;
    }
    .stat-card::before {
      content: ''; position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      border-radius: var(--radius) var(--radius) 0 0;
    }
    .accent-amber::before { background: var(--amber); }
    .accent-green::before  { background: var(--green); }
    .accent-indigo::before { background: var(--indigo); }
    .accent-red::before    { background: var(--red); }

    .stat-label {
      font-size: 0.72rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.1em;
      color: var(--muted); margin-bottom: 8px;
    }
    .stat-value {
      font-size: 2.4rem; font-weight: 800; line-height: 1;
      color: var(--text);
    }
    .genre-val { font-size: 1.4rem; line-height: 1.2; }
    .stat-sub  { font-size: 0.78rem; color: var(--muted); margin-top: 7px; }

    /* ── Clickable stat card ─────────────────────────────────────────────── */
    .clickable-card {
      cursor: pointer;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .clickable-card:hover {
      transform: translateY(-3px);
      box-shadow: var(--shadow);
    }

    /* ── Charts ──────────────────────────────────────────────────────────── */
    .charts-grid {
      display: grid;
      grid-template-columns: 1fr 1.7fr;
      gap: 18px;
    }
    @media (max-width: 800px) { .charts-grid { grid-template-columns: 1fr; } }

    @media (max-width: 480px) {
      /* Layout */
      .wrap        { padding: 0 14px; }
      main         { padding: 24px 0 40px; }
      section      { margin-bottom: 36px; }

      /* Header */
      header       { padding: 20px 0 16px; }
      header .wrap { gap: 10px; }
      header h1    { font-size: 1.3rem; }
      .subtitle    { font-size: 0.78rem; }

      /* Stat cards */
      .stats-grid  { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
      .stat-card   { padding: 16px 14px; }
      .stat-value  { font-size: 1.8rem; }

      /* Charts */
      .chart-wrap  { height: 220px; }

      /* Top 10 table — horizontal scroll */
      .table-wrap  { overflow-x: auto; -webkit-overflow-scrolling: touch; }

      /* Modals */
      .modal-overlay { padding: 12px 10px; }
      .modal-box   { padding: 16px; border-radius: 10px; }
      .modal-header { margin-bottom: 14px; }

      /* Action buttons — 44px tap targets */
      .detail-btn  { min-height: 44px; display: inline-flex; align-items: center; justify-content: center; }
      .modal-close { min-width: 44px; min-height: 44px; }

      /* Recent cards — 2 columns on phone */
      .recent-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }

      /* Modal record grid */
      .modal-grid  { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
    }

    .chart-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
    }
    .chart-label {
      font-size: 0.75rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--muted); margin-bottom: 20px;
    }
    .chart-wrap { position: relative; height: 300px; cursor: pointer; }
    .chart-wrap canvas { display: block; width: 100% !important; height: 100% !important; }

    /* ── Top 10 table ────────────────────────────────────────────────────── */
    .table-wrap {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
    }
    table { width: 100%; border-collapse: collapse; }
    thead th {
      text-align: left; font-size: 0.72rem;
      text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--muted);
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
    }
    tbody td {
      padding: 12px 16px;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      vertical-align: middle;
    }
    tbody tr:last-child td { border-bottom: none; }
    tbody tr:hover td { background: var(--surface2); }

    .rank       { font-size: 1rem; font-weight: 700; color: var(--muted); width: 44px; }
    .rank-1     { color: #FFD700; }
    .rank-2     { color: #C0C0C0; }
    .rank-3     { color: #CD7F32; }

    .thumb {
      width: 52px; height: 52px;
      border-radius: 8px; object-fit: cover;
      display: block;
    }
    .no-thumb {
      width: 52px; height: 52px;
      border-radius: 8px;
      background: var(--surface2);
      display: flex; align-items: center; justify-content: center;
      color: var(--muted); font-size: 1.3rem;
    }

    .rec-title  { font-weight: 600; font-size: 0.92rem; color: var(--text); }
    .rec-artist { font-size: 0.8rem; color: var(--muted); margin-top: 2px; }

    .badge {
      display: inline-block;
      padding: 2px 9px; border-radius: 20px;
      font-size: 0.72rem; font-weight: 600;
      background: rgba(245,158,11,0.12);
      color: var(--amber);
      border: 1px solid rgba(245,158,11,0.25);
    }
    .price { font-weight: 700; font-size: 0.98rem; color: var(--green); white-space: nowrap; }
    .muted { color: var(--muted); }
    .small { font-size: 0.84rem; }

    /* ── eBay link ───────────────────────────────────────────────────────── */
    .ebay-link {
      font-size: 0.75rem; color: var(--amber);
      text-decoration: none; display: inline-block; margin-top: 4px;
    }
    .ebay-link:hover { text-decoration: underline; }

    /* ── Recent cards grid ───────────────────────────────────────────────── */
    .recent-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
      gap: 16px;
    }
    .recent-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      transition: transform 0.18s ease, box-shadow 0.18s ease;
      cursor: default;
    }
    .recent-card:hover {
      transform: translateY(-5px);
      box-shadow: var(--shadow);
    }
    .art-link { display: block; }
    .art-link:hover .card-art { opacity: 0.85; }

    .card-art {
      width: 100%; aspect-ratio: 1;
      object-fit: cover; display: block;
    }
    .no-art {
      width: 100%; aspect-ratio: 1;
      background: var(--surface2);
      display: flex; align-items: center;
      justify-content: center;
      font-size: 2.8rem; color: var(--muted);
    }
    .card-info  { padding: 12px; }
    .ellipsis   { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .small-badge { font-size: 0.68rem; padding: 1px 7px; margin-top: 6px; display: inline-block; }
    .card-date  { font-size: 0.7rem; color: var(--muted); margin-top: 6px; opacity: 0.75; }
    .card-price { font-size: 0.8rem; font-weight: 700; color: var(--green); margin-top: 4px; }

    /* ── Modal ───────────────────────────────────────────────────────────── */
    .modal-overlay {
      display: none;
      position: fixed; top: 0; right: 0; bottom: 0; left: 0;
      background: rgba(0,0,0,0.78);
      z-index: 1000;
      padding: 40px 16px;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
      padding-bottom: env(safe-area-inset-bottom, 24px);
    }
    #detailModal { z-index: 1001; }
    .modal-overlay.open { display: block; }
    .modal-box {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      max-width: 1200px;
      margin: 0 auto;
      padding: 28px;
    }
    .modal-header {
      display: flex; align-items: center;
      justify-content: space-between;
      margin-bottom: 24px; gap: 16px;
    }
    .modal-title { font-size: 1.15rem; font-weight: 700; color: var(--text); }
    .modal-close {
      background: none; border: none;
      color: var(--muted); font-size: 2rem;
      cursor: pointer; line-height: 1;
      padding: 0 4px; flex-shrink: 0;
    }
    .modal-close:hover { color: var(--text); }
    .modal-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
      gap: 16px;
    }

    /* ── Random Record button ────────────────────────────────────────────── */
    .random-btn {
      display: flex; align-items: center; gap: 8px;
      background: var(--surface); border: 1px solid var(--border);
      color: var(--text); border-radius: 10px;
      padding: 10px 18px; font-size: 0.88rem; font-weight: 600;
      cursor: pointer; transition: background 0.15s, border-color 0.15s;
    }
    .random-btn:hover { background: var(--surface2); border-color: var(--amber); color: var(--amber); }
    .header-right { display: flex; flex-direction: column; align-items: flex-end; gap: 12px; }

    /* ── Search ──────────────────────────────────────────────────────────── */
    .search-section { margin-bottom: 32px; }
    .search-wrap { position: relative; max-width: 560px; }
    .search-icon {
      position: absolute; left: 14px; top: 50%; transform: translateY(-50%);
      color: var(--muted); pointer-events: none;
    }
    .search-input {
      width: 100%; padding: 13px 16px 13px 42px;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); color: var(--text);
      font-size: 0.95rem; outline: none;
      transition: border-color 0.15s;
    }
    .search-input:focus { border-color: var(--amber); }
    .search-dropdown {
      display: none; position: absolute; top: calc(100% + 6px); left: 0; right: 0;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); z-index: 200; overflow: hidden;
      box-shadow: var(--shadow);
    }
    .search-dropdown.open { display: block; }
    .search-result {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 14px; cursor: pointer; border-bottom: 1px solid var(--border);
    }
    .search-result:last-child { border-bottom: none; }
    .search-result:hover { background: var(--surface2); }
    .search-result img { width: 40px; height: 40px; object-fit: cover; border-radius: 6px; flex-shrink: 0; }
    .search-result-noimg {
      width: 40px; height: 40px; background: var(--surface2);
      border-radius: 6px; display: flex; align-items: center; justify-content: center;
      color: var(--muted); font-size: 1.1rem; flex-shrink: 0;
    }
    .search-result-info .sr-title { font-size: 0.88rem; font-weight: 600; color: var(--text); }
    .search-result-info .sr-artist { font-size: 0.78rem; color: var(--muted); }
    .search-no-results { padding: 14px; color: var(--muted); font-size: 0.88rem; }

    /* ── Album detail modal ──────────────────────────────────────────────── */
    .detail-box { max-width: 860px; }
    .detail-hero {
      display: grid; grid-template-columns: 220px 1fr; gap: 28px;
      margin-bottom: 28px;
    }
    @media (max-width: 600px) { .detail-hero { grid-template-columns: 1fr; } }
    .detail-art {
      width: 100%; aspect-ratio: 1; object-fit: cover;
      border-radius: var(--radius);
    }
    .detail-no-art {
      width: 100%; aspect-ratio: 1; background: var(--surface2);
      border-radius: var(--radius); display: flex; align-items: center;
      justify-content: center; font-size: 4rem; color: var(--muted);
    }
    .detail-meta { display: flex; flex-direction: column; gap: 10px; }
    .detail-title { font-size: 1.5rem; font-weight: 800; line-height: 1.2; }
    .detail-artist { font-size: 1rem; color: var(--muted); }
    .detail-badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
    .detail-field { font-size: 0.83rem; color: var(--muted); }
    .detail-field span { color: var(--text); }
    .detail-actions { display: flex; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
    .detail-btn {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 8px 14px; border-radius: 8px; font-size: 0.82rem; font-weight: 600;
      text-decoration: none; border: 1px solid var(--border);
      color: var(--text); background: var(--surface2);
      cursor: pointer; transition: border-color 0.15s;
    }
    .detail-btn:hover { border-color: var(--amber); color: var(--amber); }
    .detail-btn.yt { border-color: #ff0000; color: #ff0000; }
    .detail-btn.yt:hover { background: rgba(255,0,0,0.08); }
    .detail-notes {
      font-size: 0.82rem; color: var(--muted); line-height: 1.6;
      background: var(--surface2); border-radius: 8px; padding: 12px; margin-bottom: 20px;
    }
    .tracklist-title {
      font-size: 0.85rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--muted); margin-bottom: 12px;
    }
    .tracklist { width: 100%; border-collapse: collapse; }
    .tracklist td {
      padding: 7px 8px; border-bottom: 1px solid rgba(255,255,255,0.05);
      font-size: 0.85rem; vertical-align: top;
    }
    .tracklist tr:last-child td { border-bottom: none; }
    .tracklist .tl-pos { color: var(--muted); width: 36px; }
    .tracklist .tl-dur { color: var(--muted); text-align: right; white-space: nowrap; }

    /* ── YouTube card button ─────────────────────────────────────────────── */
    .yt-card-btn {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 0.68rem; font-weight: 600;
      color: #ff0000; text-decoration: none;
      margin-top: 4px; opacity: 0.85;
    }
    .yt-card-btn:hover { opacity: 1; text-decoration: underline; }

    /* ── Footer ──────────────────────────────────────────────────────────── */
    footer {
      border-top: 1px solid var(--border);
      padding: 22px 0;
      text-align: center;
      color: var(--muted);
      font-size: 0.78rem;
    }

    /* ── aspect-ratio fallback for iOS < 15 / Safari < 15 ───────────────── */
    @supports not (aspect-ratio: 1) {
      .card-art, .no-art           { height: 160px; }
      .detail-art, .detail-no-art  { height: 260px; }
    }
  </style>
</head>
<body>

<!-- Album detail modal -->
<div id="detailModal" class="modal-overlay" onclick="if(event.target===this)closeDetail()">
  <div class="modal-box detail-box">
    <div class="modal-header">
      <span class="modal-title" id="detailTitle"></span>
      <button class="modal-close" onclick="closeDetail()" aria-label="Close">&times;</button>
    </div>
    <div id="detailBody"></div>
  </div>
</div>

<!-- Modal overlay -->
<div id="modal" class="modal-overlay" onclick="if(event.target===this)closeModal()">
  <div class="modal-box">
    <div class="modal-header">
      <span class="modal-title" id="modalTitle"></span>
      <button class="modal-close" onclick="closeModal()" aria-label="Close">&times;</button>
    </div>
    <div class="modal-grid" id="modalGrid"></div>
  </div>
</div>

<header>
  <div class="wrap">
    <div class="logo">
      <div class="vinyl"></div>
      <div>
        <h1>VinylVisualizer</h1>
        <div class="subtitle">Jack Warren's Record Collection as of """ + data["generated_at"] + """</div>
      </div>
    </div>
    <div class="header-right">
      <button class="random-btn" onclick="openRandomRecord()" title="Show a random record">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="16 3 21 3 21 8"/><polyline points="4 20 21 3"/>
          <polyline points="21 16 21 21 16 21"/><line x1="4" y1="4" x2="9" y2="9"/>
          <line x1="15" y1="15" x2="20" y2="20"/>
        </svg>
        Random Record
      </button>
      <div class="header-meta">""" + meta_html + """</div>
    </div>
  </div>
</header>

<main>
  <div class="wrap">

    <!-- Search -->
    <section class="search-section">
      <div class="search-wrap" id="searchWrap">
        <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input id="searchInput" type="search" class="search-input"
               placeholder="Search by title or artist\u2026" autocomplete="off">
        <div id="searchDropdown" class="search-dropdown"></div>
      </div>
    </section>

    <!-- Stats row -->
    <section>
      <div class="stats-grid">""" + stats_html + """</div>
    </section>

    <!-- Charts -->
    <section>
      <div class="section-title">Collection Analysis</div>
      <div class="charts-grid">
        <div class="chart-card">
          <div class="chart-label">Genre Breakdown &mdash; click a slice to filter</div>
          <div class="chart-wrap"><canvas id="genreChart"></canvas></div>
        </div>
        <div class="chart-card">
          <div class="chart-label">Records by Decade &mdash; click a bar to filter</div>
          <div class="chart-wrap"><canvas id="decadeChart"></canvas></div>
        </div>
      </div>
    </section>

    <!-- Top 10 Most Valuable -->
    <section>
      <div class="section-title">Top 10 Most Valuable Records</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th></th>
              <th>Title / Artist</th>
              <th>Year</th>
              <th>Genre</th>
              <th>Est. Value</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="top10Body"></tbody>
        </table>
      </div>
    </section>

    <!-- Recently Added -->
    <section>
      <div class="section-title">Recently Added</div>
      <div class="recent-grid" id="recentGrid"></div>
    </section>

  </div>
</main>

<footer>
  <div class="wrap">""" + footer_html + """</div>
</footer>

<script>
""" + js + """
</script>
</body>
</html>"""

    return html


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VinylVisualizer dashboard generator")
    parser.add_argument(
        "--silent", action="store_true",
        help="Skip all prompts and auto-write output (for scheduled/unattended runs)"
    )
    args = parser.parse_args()

    releases = fetch_collection()

    print("Processing data...")
    data = process_collection(releases)

    fetch_prices(data["all_records"])
    fetch_tracklists(data["all_records"])

    # Recalculate price-dependent stats now that prices are populated
    priced                 = [r for r in data["all_records"] if r["price"] is not None]
    data["total_value"]    = round(sum(r["price"] for r in priced), 2)
    data["priced_count"]   = len(priced)
    data["unpriced_count"] = len(data["all_records"]) - len(priced)
    data["top_10"]         = sorted(priced, key=lambda x: x["price"], reverse=True)[:10]

    print("\n--- Collection Summary ---")
    print(f"  Records total   : {data['total']:,}")
    print(f"  Records priced  : {data['priced_count']} / {data['total']}")
    print(f"  Estimated value : ${data['total_value']:,.2f}")
    print(f"  Year range      : {data['year_range']}")
    print(f"  Top genre       : {data['top_genre']}")
    print(f"  Decades covered : {len(data['decades'])}")
    print("--------------------------\n")

    print("Building HTML dashboard...")
    html = generate_html(data)

    if not args.silent:
        print("\n--- HTML Preview (first 600 chars) ---")
        print(html[:600])
        print("...\n")
        answer = input(f"Write to '{OUTPUT}'? (y/n): ").strip().lower()
    else:
        answer = "y"

    if answer == "y":
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(html)
        size_kb = os.path.getsize(OUTPUT) / 1024
        print(f"\nSaved: {OUTPUT}  ({size_kb:.1f} KB)")
        if not args.silent:
            print("Open that file in any browser to view your dashboard.")
            print(f"\nFull path: {os.path.abspath(OUTPUT)}")
    else:
        print("Cancelled — no file written.")


if __name__ == "__main__":
    main()
    if "--silent" not in sys.argv:
        input("\nPress Enter to close this window...")
