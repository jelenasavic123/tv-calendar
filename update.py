# update.py

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# =========================================================
# PODEŠAVANJA
# =========================================================

SOURCE_URL = "https://turskeserije.tv/kalendar/"

OUTPUT_FILE = "tv-calendar.json"

TIMEOUT = 30


# =========================================================
# HTTP
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
    "Referer": "https://turskeserije.tv/",
}


# =========================================================
# POMOĆNE FUNKCIJE
# =========================================================

def clean_text(value):
    """
    Čisti višak razmaka i newline karaktera.
    """

    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def absolute_url(url):
    """
    Pretvara relativan URL u apsolutan.
    """

    if not url:
        return ""

    if url.startswith("//"):
        return "https:" + url

    if url.startswith("/"):
        return "https://turskeserije.tv" + url

    return url


def parse_episode(text):
    """
    Primer:

    Epizoda 19, Sezone 2

    vraća:

    episode = 19
    season = 2
    """

    if not text:
        return None, None

    episode_match = re.search(
        r"Epizoda\s+(\d+)",
        text,
        re.IGNORECASE
    )

    season_match = re.search(
        r"Sezone\s+(\d+)",
        text,
        re.IGNORECASE
    )

    episode = (
        int(episode_match.group(1))
        if episode_match
        else None
    )

    season = (
        int(season_match.group(1))
        if season_match
        else None
    )

    return episode, season


# =========================================================
# DATUM
# =========================================================

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def parse_calendar_date(text):
    """
    Primer:

        Monday, Sep 21

    Godina se uzima iz trenutne godine.
    """

    text = clean_text(text)

    match = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    month_name = match.group(1).title()
    day = int(match.group(2))

    month = MONTHS.get(month_name)

    if not month:
        return None

    year = datetime.now().year

    return (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )


# =========================================================
# POSTER
# =========================================================

def get_image_url(img):
    """
    Uzima poster iz src atributa.

    Ako je lazy-load slika, proverava i:

    data-src
    data-lazy-src
    data-original
    """

    if not img:
        return ""

    attributes = [
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
    ]

    for attribute in attributes:

        value = img.get(attribute)

        if value:
            return absolute_url(
                value.strip()
            )

    return ""


# =========================================================
# GLAVNO
# =========================================================

def main():

    print()
    print("=" * 60)
    print(" TV KALENDAR UPDATE")
    print("=" * 60)
    print()

    print(
        f"[INFO] Preuzimam:\n{SOURCE_URL}"
    )

    try:

        response = requests.get(
            SOURCE_URL,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

    except Exception as error:

        print()
        print(
            f"[ERROR] Ne mogu da otvorim stranicu:"
        )

        print(error)

        raise SystemExit(1)


    print(
        f"[OK] HTTP {response.status_code}"
    )

    print(
        f"[INFO] Veličina HTML-a: "
        f"{len(response.text):,} karaktera"
    )


    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    # =====================================================
    # PRONAĐI SVE DANE
    # =====================================================

    calendar = {}

    day_blocks = soup.select(
        ".swiper-slide"
    )


    print(
        f"[INFO] Pronađeno blokova dana: "
        f"{len(day_blocks)}"
    )


    total_items = 0

    skipped_items = 0


    # =====================================================
    # OBRADA DANA
    # =====================================================

    for day_block in day_blocks:

        day_header = day_block.select_one(
            ".calendar-primary h2"
        )

        if not day_header:
            continue


        date_key = parse_calendar_date(
            day_header.get_text(
                " ",
                strip=True
            )
        )


        if not date_key:
            print(
                "[WARN] Ne mogu da pročitam datum:"
            )

            print(
                day_header.get_text(
                    " ",
                    strip=True
                )
            )

            continue


        if date_key not in calendar:

            calendar[date_key] = []


        # =================================================
        # EPIZODE
        # =================================================

        items = day_block.select(
            ".primetime"
        )


        for item in items:

            link = item.select_one(
                "a"
            )

            if not link:
                skipped_items += 1
                continue


            # ---------------------------------------------
            # URL
            # ---------------------------------------------

            url = absolute_url(
                link.get("href", "")
            )


            # ---------------------------------------------
            # POSTER
            # ---------------------------------------------

            img = item.select_one(
                "img"
            )

            image = get_image_url(
                img
            )


            # ---------------------------------------------
            # NASLOV
            # ---------------------------------------------

            title_element = item.select_one(
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

            episode_element = item.select_one(
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

            time_element = item.select_one(
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


            # ---------------------------------------------
            # TIMEZONE
            # ---------------------------------------------

            timezone_match = re.search(
                r"\(([^)]+)\)",
                time_text
            )

            timezone_text = ""

            if timezone_match:

                timezone_text = clean_text(
                    timezone_match.group(1)
                )

                time_text = clean_text(
                    re.sub(
                        r"\s*\([^)]+\)",
                        "",
                        time_text
                    )
                )


            # ---------------------------------------------
            # VALIDACIJA
            # ---------------------------------------------

            if not title:

                print(
                    "[WARN] Preskačem stavku "
                    "bez naslova."
                )

                skipped_items += 1

                continue


            if not url:

                print(
                    f"[WARN] {title} nema URL."
                )


            if episode is None:

                print(
                    f"[WARN] {title} nema broj epizode."
                )


            # ---------------------------------------------
            # REZULTAT
            # ---------------------------------------------

            episode_data = {

                "title": title,

                "url": url,

                "image": image,

                "episode": episode,

                "season": season,

                "time": time_text,

                "timezone": timezone_text,

            }


            calendar[date_key].append(
                episode_data
            )


            total_items += 1


    # =====================================================
    # SORTIRANJE
    # =====================================================

    sorted_calendar = {}


    for date_key in sorted(
        calendar.keys()
    ):

        items = calendar[date_key]


        # prvo vreme
        # pa sezona
        # pa epizoda

        items.sort(
            key=lambda item: (
                item.get("time", ""),
                item.get("season") or 0,
                item.get("episode") or 0
            )
        )


        sorted_calendar[
            date_key
        ] = items


    # =====================================================
    # VREME AŽURIRANJA
    # =====================================================

    serbia_tz = timezone(
        timedelta(hours=2)
    )

    updated_at = datetime.now(
        serbia_tz
    ).isoformat()


    # =====================================================
    # FINALNI JSON
    # =====================================================

    output = {

        "updatedAt":
            updated_at,

        "source":
            SOURCE_URL,

        "calendar":
            sorted_calendar

    }


    # =====================================================
    # SNIMANJE
    # =====================================================

    output_path =
        Path(OUTPUT_FILE)


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

    total_days = len(
        sorted_calendar
    )


    total_series_links = 0


    for items in sorted_calendar.values():

        total_series_links += len(
            items
        )


    print()
    print("=" * 60)
    print(" GOTOVO")
    print("=" * 60)

    print(
        f"[OK] Dana: {total_days}"
    )

    print(
        f"[OK] Epizoda: {total_series_links}"
    )

    print(
        f"[OK] Preskočeno: {skipped_items}"
    )

    print(
        f"[OK] JSON: {output_path.resolve()}"
    )

    print(
        f"[OK] Ažurirano: {updated_at}"
    )

    print()
    print("=" * 60)


if __name__ == "__main__":

    main()