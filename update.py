import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


# =========================================================
# PODEŠAVANJA
# =========================================================

SOURCE_URL = "https://turskeserije.tv/kalendar/"

OUTPUT_FILE = "tv-calendar.json"

TIMEOUT = 30

# Srbija
TIMEZONE = ZoneInfo("Europe/Belgrade")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": SOURCE_URL,
}


# =========================================================
# MESECI
# =========================================================

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


# =========================================================
# ČIŠĆENJE TEKSTA
# =========================================================

def clean_text(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


# =========================================================
# APSOLUTNI URL
# =========================================================

def absolute_url(url):

    if not url:
        return ""

    return urljoin(
        SOURCE_URL,
        url.strip()
    )


# =========================================================
# PARSIRANJE DATUMA
# =========================================================

def parse_calendar_date(text, year):

    """
    Primeri:

    Monday, Sep 21
    Tuesday, Sep 15
    Today (Tuesday, Sep 15)
    Wednesday, Sep 16
    """

    text = clean_text(text)

    match = re.search(
        r"\b("
        r"January|February|March|April|May|June|"
        r"July|August|September|October|November|December"
        r")\s+(\d{1,2})\b",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    month_name = match.group(1).lower()

    day = int(
        match.group(2)
    )

    month = MONTHS.get(
        month_name
    )

    if not month:
        return None

    try:

        return datetime(
            year,
            month,
            day
        ).date()

    except ValueError:

        return None


# =========================================================
# PARSIRANJE EPIZODE I SEZONE
# =========================================================

def parse_episode(text):

    """
    Primer:

    Epizoda 118, Sezone 2

    rezultat:

    episode = 118
    season = 2
    """

    text = clean_text(text)

    episode = None
    season = None

    episode_match = re.search(
        r"Epizoda\s*(\d+)",
        text,
        re.IGNORECASE
    )

    if episode_match:

        episode = int(
            episode_match.group(1)
        )

    season_match = re.search(
        r"Sezone?\s*(\d+)",
        text,
        re.IGNORECASE
    )

    if season_match:

        season = int(
            season_match.group(1)
        )

    return episode, season


# =========================================================
# POSTER
# =========================================================

def get_image_url(img):

    if not img:
        return ""

    candidates = [
        img.get("src"),
        img.get("data-src"),
        img.get("data-lazy-src"),
        img.get("data-original"),
    ]

    srcset = img.get("srcset")

    if srcset:

        parts = srcset.split(",")

        if parts:

            first = parts[0].strip()

            if first:

                first_parts = first.split()

                if first_parts:

                    candidates.append(
                        first_parts[0]
                    )

    for value in candidates:

        if value:

            return absolute_url(
                value
            )

    return ""


# =========================================================
# NORMALIZACIJA URL
# =========================================================

def normalize_url(url):

    if not url:
        return ""

    url = url.strip()

    url = url.split("?")[0]

    url = url.rstrip("/")

    return url.lower()


# =========================================================
# NORMALIZACIJA NASLOVA
# =========================================================

def normalize_title(title):

    title = clean_text(
        title
    ).lower()

    title = re.sub(
        r"[\(\)\[\]\-–—:.,']",
        " ",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


# =========================================================
# TEKUĆA NEDELJA
# =========================================================

def get_current_week():

    """
    Nedelja je:

    Ponedeljak -> Nedelja

    Primer:

    2026-09-15
    postaje:

    2026-09-14 -> 2026-09-20
    """

    now = datetime.now(
        TIMEZONE
    )

    today = now.date()

    monday = (
        today
        - timedelta(
            days=today.weekday()
        )
    )

    sunday = (
        monday
        + timedelta(
            days=6
        )
    )

    return monday, sunday


# =========================================================
# DATUMI NEDELJE
# =========================================================

def get_week_dates(monday):

    return [
        monday + timedelta(days=i)
        for i in range(7)
    ]


# =========================================================
# VREME
# =========================================================

def parse_time(text):

    text = clean_text(
        text
    )

    if not text:

        return "", ""

    time_value = ""

    timezone_value = ""

    # -----------------------------------------------------
    # SAT
    # -----------------------------------------------------

    time_match = re.search(
        r"\b(\d{1,2}:\d{2})\b",
        text
    )

    if time_match:

        time_value = (
            time_match.group(1)
        )

    # -----------------------------------------------------
    # TIMEZONE
    # -----------------------------------------------------

    timezone_match = re.search(
        r"\(([^)]+)\)",
        text
    )

    if timezone_match:

        timezone_value = (
            timezone_match.group(1)
        )

    return (
        time_value,
        timezone_value
    )


# =========================================================
# PRONALAŽENJE DATUMA ZA EPIZODU
# =========================================================

def find_date_for_episode(
    episode_box,
    headers_with_dates
):

    """
    Za svaki .primetime tražimo
    najbliži prethodni kalendarski h2.

    Ovo je bitno zato što stranica
    ponavlja kalendarske blokove.
    """

    current_position = (
        episode_box
    )

    while current_position:

        previous = (
            current_position.find_previous(
                "h2"
            )
        )

        if not previous:
            return None

        classes = previous.get(
            "class",
            []
        )

        # -------------------------------------------------
        # PROVERA DA LI JE OVO KALENDARSKI H2
        # -------------------------------------------------

        is_calendar_header = (
            "calendar-primary"
            in classes
        )

        # Nekad je calendar-primary na
        # roditeljskom elementu.
        if not is_calendar_header:

            parent = previous.parent

            if parent:

                parent_classes = parent.get(
                    "class",
                    []
                )

                is_calendar_header = (
                    "calendar-primary"
                    in parent_classes
                )

        if is_calendar_header:

            date_text = clean_text(
                previous.get_text(
                    " ",
                    strip=True
                )
            )

            return date_text

        current_position = previous

    return None


# =========================================================
# GLAVNI SCRAPER
# =========================================================

def scrape_calendar():

    print()
    print("=" * 70)
    print("TURSKA SERIJA TV - NEDELJNI KALENDAR")
    print("=" * 70)
    print()

    # =====================================================
    # TEKUĆA NEDELJA
    # =====================================================

    monday, sunday = get_current_week()

    print(
        f"Tekuća nedelja: "
        f"{monday} -> {sunday}"
    )

    week_dates = get_week_dates(
        monday
    )

    allowed_dates = {
        date.isoformat()
        for date in week_dates
    }

    # =====================================================
    # PRAZAN KALENDAR
    # =====================================================

    calendar = {
        date.isoformat(): []
        for date in week_dates
    }

    # =====================================================
    # UČITAVANJE STRANICE
    # =====================================================

    print()
    print(
        f"Učitavam:"
    )

    print(
        SOURCE_URL
    )

    print()

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    print(
        f"HTTP status: "
        f"{response.status_code}"
    )

    print(
        f"Veličina stranice: "
        f"{len(response.text):,} karaktera"
    )

    # =====================================================
    # BEAUTIFULSOUP
    # =====================================================

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # =====================================================
    # GODINA
    # =====================================================

    now = datetime.now(
        TIMEZONE
    )

    current_year = now.year

    # =====================================================
    # PRONAĐI SVE DATUMSKE HEADER-E
    # =====================================================

    date_headers = soup.select(
        ".calendar-primary h2"
    )

    print()
    print(
        f"Pronađeno datumskih zaglavlja: "
        f"{len(date_headers)}"
    )

    # =====================================================
    # PRONAĐI SVE EPIZODE
    # =====================================================

    episode_boxes = soup.select(
        ".primetime"
    )

    print(
        f"Pronađeno .primetime elemenata: "
        f"{len(episode_boxes)}"
    )

    print()

    # =====================================================
    # STATISTIKA
    # =====================================================

    found = 0

    added = 0

    skipped = 0

    outside_week = 0

    invalid_date = 0

    duplicate_count = 0

    # =====================================================
    # EPIZODE
    # =====================================================

    for episode_box in episode_boxes:

        found += 1

        # -------------------------------------------------
        # DATUM
        # -------------------------------------------------

        date_text = find_date_for_episode(
            episode_box,
            date_headers
        )

        if not date_text:

            invalid_date += 1

            print(
                "[DATUM ERROR] "
                "Nije pronađen datum za epizodu."
            )

            continue

        parsed_date = parse_calendar_date(
            date_text,
            current_year
        )

        if not parsed_date:

            invalid_date += 1

            print(
                f"[DATUM ERROR] "
                f"{date_text}"
            )

            continue

        date_key = (
            parsed_date.isoformat()
        )

        # -------------------------------------------------
        # SAMO TEKUĆA NEDELJA
        # -------------------------------------------------

        if date_key not in allowed_dates:

            outside_week += 1

            continue

        # -------------------------------------------------
        # LINK
        # -------------------------------------------------

        link = episode_box.select_one(
            "a"
        )

        if not link:

            skipped += 1

            continue

        url = absolute_url(
            link.get(
                "href",
                ""
            )
        )

        # -------------------------------------------------
        # POSTER
        # -------------------------------------------------

        img = episode_box.select_one(
            "img"
        )

        image = get_image_url(
            img
        )

        # -------------------------------------------------
        # NASLOV
        # -------------------------------------------------

        title_element = (
            episode_box.select_one(
                "h3"
            )
        )

        if title_element:

            title = clean_text(
                title_element.get_text(
                    " ",
                    strip=True
                )
            )

        else:

            title = ""

        # -------------------------------------------------
        # EPIZODA / SEZONA
        # -------------------------------------------------

        episode_element = (
            episode_box.select_one(
                "span.cl-text-primary"
            )
        )

        if episode_element:

            episode_text = clean_text(
                episode_element.get_text(
                    " ",
                    strip=True
                )
            )

        else:

            episode_text = ""

        episode, season = parse_episode(
            episode_text
        )

        # -------------------------------------------------
        # VREME
        # -------------------------------------------------

        time_element = (
            episode_box.select_one(
                "span.cl-mb-0"
            )
        )

        if time_element:

            time_text = clean_text(
                time_element.get_text(
                    " ",
                    strip=True
                )
            )

        else:

            time_text = ""

        (
            time_value,
            timezone_value
        ) = parse_time(
            time_text
        )

        # -------------------------------------------------
        # NASLOV OBAVEZAN
        # -------------------------------------------------

        if not title:

            skipped += 1

            continue

        # -------------------------------------------------
        # ITEM
        # -------------------------------------------------

        item = {
            "date": date_key,
            "title": title,
            "url": url,
            "image": image,
            "episode": episode,
            "season": season,
            "time": time_value,
            "timezone": timezone_value
        }

        # -------------------------------------------------
        # DODAVANJE
        # -------------------------------------------------

        calendar[date_key].append(
            item
        )

        added += 1

    # =====================================================
    # UKLANJANJE DUPLIKATA
    # =====================================================

    for date_key in calendar:

        unique = {}

        for item in calendar[date_key]:

            key = (
                normalize_url(
                    item.get("url")
                )
                + "|"
                + normalize_title(
                    item.get("title")
                )
                + "|"
                + str(
                    item.get("episode")
                )
                + "|"
                + str(
                    item.get("season")
                )
                + "|"
                + str(
                    item.get("time")
                )
            )

            if key in unique:

                duplicate_count += 1

                continue

            unique[key] = item

        calendar[date_key] = list(
            unique.values()
        )

    # =====================================================
    # SORTIRANJE
    # =====================================================

    for date_key in calendar:

        calendar[date_key].sort(
            key=lambda item: (
                item.get("time")
                or "99:99",

                normalize_title(
                    item.get("title")
                ),

                item.get("season")
                if item.get("season") is not None
                else 999,

                item.get("episode")
                if item.get("episode") is not None
                else 999
            )
        )

    # =====================================================
    # STATISTIKA
    # =====================================================

    total_items = sum(
        len(items)
        for items in calendar.values()
    )

    total_days = sum(
        1
        for items in calendar.values()
        if items
    )

    # =====================================================
    # VREME AŽURIRANJA
    # =====================================================

    updated_at = datetime.now(
        TIMEZONE
    ).isoformat()

    # =====================================================
    # FINALNI JSON
    # =====================================================

    output = {

        "updatedAt":
            updated_at,

        "source":
            SOURCE_URL,

        "week": {

            "start":
                monday.isoformat(),

            "end":
                sunday.isoformat(),

            "days":
                7

        },

        "calendar":
            calendar
    }

    # =====================================================
    # UPIS JSON-A
    # =====================================================

    output_path = Path(
        OUTPUT_FILE
    )

    output_path.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # =====================================================
    # ISPIS REZULTATA
    # =====================================================

    print()
    print("=" * 70)
    print("REZULTAT")
    print("=" * 70)
    print()

    print(
        f"Nedelja:"
    )

    print(
        f"{monday} -> {sunday}"
    )

    print()

    print(
        f"Pronađeno .primetime:"
        f" {found}"
    )

    print(
        f"Upisano:"
        f" {total_items}"
    )

    print(
        f"Preskočeno:"
        f" {skipped}"
    )

    print(
        f"Van tekuće nedelje:"
        f" {outside_week}"
    )

    print(
        f"Neispravnih datuma:"
        f" {invalid_date}"
    )

    print(
        f"Duplikata uklonjeno:"
        f" {duplicate_count}"
    )

    print(
        f"Dana sa epizodama:"
        f" {total_days}/7"
    )

    print()

    # =====================================================
    # ISPIS PO DANIMA
    # =====================================================

    print(
        "EPIZODE PO DANIMA:"
    )

    print()

    for date_key, items in calendar.items():

        print(
            f"{date_key}: "
            f"{len(items)} epizoda"
        )

        for item in items:

            episode_text = ""

            if item.get("episode") is not None:

                episode_text = (
                    f"Epizoda "
                    f"{item.get('episode')}"
                )

            if item.get("season") is not None:

                episode_text += (
                    f" | Sezona "
                    f"{item.get('season')}"
                )

            print(
                f"    - "
                f"{item.get('title')} "
                f"{episode_text} "
                f"{item.get('time')}"
            )

    print()

    print(
        f"JSON napravljen:"
    )

    print(
        str(
            output_path.resolve()
        )
    )

    print()

    print("=" * 70)
    print("GOTOVO")
    print("=" * 70)
    print()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    try:

        scrape_calendar()

    except requests.RequestException as error:

        print()
        print("=" * 70)
        print("HTTP GREŠKA")
        print("=" * 70)
        print()
        print(error)
        print()

        raise

    except Exception as error:

        print()
        print("=" * 70)
        print("GREŠKA")
        print("=" * 70)
        print()
        print(error)
        print()

        raise
