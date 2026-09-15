import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# =========================================================
# PODEŠAVANJA
# =========================================================

SOURCE_URL = "https://turskeserije.tv/kalendar/"

OUTPUT_FILE = "tv-calendar.json"

TIMEOUT = 30

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
# POMOĆNE FUNKCIJE
# =========================================================

def clean_text(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def absolute_url(url):
    if not url:
        return ""

    return urljoin(
        SOURCE_URL,
        url
    )


# =========================================================
# EPIZODA
# =========================================================

def parse_episode(text):
    """
    Primer:

    Epizoda 2, Sezone 1

    vraća:

    episode = 2
    season = 1
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
# DATUM
# =========================================================

def parse_calendar_date(text, reference_year):
    """
    Primer:

    Monday, Sep 21

    Tuesday, Sep 15
    """

    text = clean_text(text)

    match = re.search(
        r"(January|February|March|April|May|June|"
        r"July|August|September|October|November|December)"
        r"\s+(\d{1,2})",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    month_name = (
        match.group(1)
        .lower()
    )

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
            reference_year,
            month,
            day
        ).date()

    except ValueError:

        return None


# =========================================================
# SLIKA
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
        first = srcset.split(",")[0].strip()

        if first:
            parts = first.split()

            if parts:
                candidates.append(
                    parts[0]
                )

    for value in candidates:

        if value:
            return absolute_url(
                value
            )

    return ""


# =========================================================
# NORMALIZACIJA URL-a
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
    Vraća:

    ponedeljak
    nedelja

    Tekuće nedelje.
    """

    today = datetime.now().date()

    monday = (
        today
        - timedelta(
            days=today.weekday()
        )
    )

    sunday = (
        monday
        + timedelta(days=6)
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
# GLAVNI SCRAPER
# =========================================================

def scrape_calendar():

    print("=" * 60)
    print("TV KALENDAR")
    print("=" * 60)

    # -----------------------------------------------------
    # TEKUĆA NEDELJA
    # -----------------------------------------------------

    monday, sunday = get_current_week()

    print(
        f"Tekuća nedelja: "
        f"{monday} -> {sunday}"
    )

    week_dates = get_week_dates(
        monday
    )

    allowed_dates = {
        d.isoformat()
        for d in week_dates
    }

    # -----------------------------------------------------
    # PRAZAN KALENDAR
    # -----------------------------------------------------

    calendar = {
        d.isoformat(): []
        for d in week_dates
    }

    # -----------------------------------------------------
    # HTTP
    # -----------------------------------------------------

    print(
        f"Učitavam: {SOURCE_URL}"
    )

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    print(
        f"HTTP: {response.status_code}"
    )

    # -----------------------------------------------------
    # PARSIRANJE
    # -----------------------------------------------------

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # -----------------------------------------------------
    # GODINA
    # -----------------------------------------------------

    current_year = datetime.now().year

    # -----------------------------------------------------
    # SVI SWIPER BLOKOVI
    # -----------------------------------------------------

    slides = soup.select(
        ".swiper-slide"
    )

    print(
        f"Pronađeno blokova: {len(slides)}"
    )

    # -----------------------------------------------------
    # STATISTIKA
    # -----------------------------------------------------

    found = 0

    added = 0

    skipped = 0

    outside_week = 0

    invalid_date = 0

    # -----------------------------------------------------
    # PROLAZ KROZ BLOKOVE
    # -----------------------------------------------------

    for slide in slides:

        date_element = slide.select_one(
            ".calendar-primary h2"
        )

        if not date_element:
            continue

        date_text = clean_text(
            date_element.get_text(
                " ",
                strip=True
            )
        )

        parsed_date = parse_calendar_date(
            date_text,
            current_year
        )

        if not parsed_date:

            invalid_date += 1

            print(
                f"[DATUM ERROR] {date_text}"
            )

            continue

        date_key = parsed_date.isoformat()

        # -------------------------------------------------
        # SAMO TEKUĆA NEDELJA
        # -------------------------------------------------

        if date_key not in allowed_dates:

            outside_week += 1

            continue

        # -------------------------------------------------
        # EPIZODE
        # -------------------------------------------------

        episode_elements = slide.select(
            ".primetime"
        )

        for episode_box in episode_elements:

            found += 1

            # ---------------------------------------------
            # LINK
            # ---------------------------------------------

            link = episode_box.select_one(
                "a"
            )

            if not link:

                skipped += 1

                continue

            url = absolute_url(
                link.get("href", "")
            )

            # ---------------------------------------------
            # POSTER
            # ---------------------------------------------

            img = episode_box.select_one(
                "img"
            )

            image = get_image_url(
                img
            )

            # ---------------------------------------------
            # NASLOV
            # ---------------------------------------------

            title_element = episode_box.select_one(
                "h3"
            )

            title = clean_text(
                title_element.get_text(
                    " ",
                    strip=True
                )
                if title_element
                else ""
            )

            # ---------------------------------------------
            # EPIZODA / SEZONA
            # ---------------------------------------------

            episode_element = episode_box.select_one(
                "span.cl-text-primary"
            )

            episode_text = clean_text(
                episode_element.get_text(
                    " ",
                    strip=True
                )
                if episode_element
                else ""
            )

            episode, season = parse_episode(
                episode_text
            )

            # ---------------------------------------------
            # VREME
            # ---------------------------------------------

            time_element = episode_box.select_one(
                "span.cl-mb-0"
            )

            time_text = clean_text(
                time_element.get_text(
                    " ",
                    strip=True
                )
                if time_element
                else ""
            )

            time_value = ""

            timezone_value = ""

            if time_text:

                time_match = re.search(
                    r"(\d{1,2}:\d{2})",
                    time_text
                )

                if time_match:

                    time_value = (
                        time_match.group(1)
                    )

                timezone_match = re.search(
                    r"\(([^)]+)\)",
                    time_text
                )

                if timezone_match:

                    timezone_value = (
                        timezone_match.group(1)
                    )

            # ---------------------------------------------
            # PROVERA
            # ---------------------------------------------

            if not title:

                skipped += 1

                continue

            # ---------------------------------------------
            # ITEM
            # ---------------------------------------------

            item = {
                "date": date_key,
                "title": title,
                "url": url,
                "image": image,
                "episode": episode,
                "season": season,
                "time": time_value,
                "timezone": timezone_value,
            }

            calendar[date_key].append(
                item
            )

            added += 1

    # =====================================================
    # UKLANJANJE DUPLIKATA
    # =====================================================

    """
    Na source stranici isti blok može biti ponovljen.

    Na primer:

    Haysiyet epizoda 1
    Haysiyet epizoda 2
    Haysiyet epizoda 3

    To NIJE duplikat.

    Ali ako se potpuno isti zapis pojavi dva puta:

    Haysiyet + datum + epizoda 1

    onda ga uklanjamo.
    """

    duplicate_count = 0

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
                item.get("time") or "99:99",
                item.get("title") or "",
                item.get("season")
                if item.get("season") is not None
                else 999,
                item.get("episode")
                if item.get("episode") is not None
                else 999,
            )
        )

    # =====================================================
    # UKUPAN BROJ
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

    serbia_timezone = timezone(
        timedelta(hours=2)
    )

    updated_at = datetime.now(
        serbia_timezone
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
    # UPIS
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
    # STATISTIKA
    # =====================================================

    print()
    print("=" * 60)
    print("ZAVRŠENO")
    print("=" * 60)

    print(
        f"Nedelja: "
        f"{monday} -> {sunday}"
    )

    print(
        f"Dana sa epizodama: "
        f"{total_days}/7"
    )

    print(
        f"Pronađeno epizoda: "
        f"{found}"
    )

    print(
        f"Upisano epizoda: "
        f"{total_items}"
    )

    print(
        f"Preskočeno: "
        f"{skipped}"
    )

    print(
        f"Van nedelje: "
        f"{outside_week}"
    )

    print(
        f"Duplikata uklonjeno: "
        f"{duplicate_count}"
    )

    print(
        f"Neispravnih datuma: "
        f"{invalid_date}"
    )

    print(
        f"JSON: "
        f"{output_path.resolve()}"
    )

    print()

    for date_key, items in calendar.items():

        print(
            f"{date_key}: "
            f"{len(items)} epizoda"
        )

    print()
    print("=" * 60)


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    try:

        scrape_calendar()

    except requests.RequestException as error:

        print()
        print(
            "HTTP GREŠKA:"
        )

        print(error)

        raise

    except Exception as error:

        print()
        print(
            "GREŠKA:"
        )

        print(error)

        raise
