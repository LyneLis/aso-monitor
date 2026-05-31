import re
from typing import List, Tuple
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from google_play_scraper import app as gp_app

from core.app_ids import normalize_app_id
from core.subtitle import clean_subtitle_candidate, decode_apple_subtitle, is_valid_subtitle_candidate

APPLE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
SUBTITLE_JSON_RE = re.compile(r'"subtitle"\s*:\s*"((?:[^"\\]|\\.)*)"')
SUBTITLE_CLASS_RE = re.compile(r"^subtitle")
SCREENSHOT_SIZE_RE = re.compile(r"/(\d+)x(\d+)")
SKIP_IMAGE_KEYWORDS = ("icon", "logo", "artwork", "brand")


def _locale_codes(locale: str) -> Tuple[str, str]:
    if locale == "es-419":
        return "es-419", "MX"
    if "-" in locale:
        return locale, locale.split("-")[1].upper()
    return locale.lower(), locale.upper()


def _screenshot_url_to_jpg(img_url: str) -> str:
    return (
        img_url.replace(".webp", ".jpg")
        .replace("w.webp", "bb.jpg")
        .replace("w.png", "bb.png")
    )


def _collect_screenshots_from_soup(soup: BeautifulSoup) -> List[str]:
    clean_screens: List[str] = []
    all_imgs = soup.find_all("picture")

    for pic in all_imgs:
        source = pic.find("source", type="image/jpeg") or pic.find("source", type="image/webp")
        if not source or not source.has_attr("srcset"):
            continue
        img_url = source["srcset"].split()[0]
        s_lower = img_url.lower()
        if any(x in s_lower for x in SKIP_IMAGE_KEYWORDS):
            continue
        res_match = SCREENSHOT_SIZE_RE.search(s_lower)
        if not res_match:
            continue
        w, h = int(res_match.group(1)), int(res_match.group(2))
        if (w == 300 or h == 300) and w != h:
            s_jpg = _screenshot_url_to_jpg(img_url)
            if s_jpg not in clean_screens:
                clean_screens.append(s_jpg)

    if clean_screens:
        return clean_screens

    for pic in all_imgs:
        source = pic.find("source", type="image/jpeg") or pic.find("source", type="image/webp")
        if not source or not source.has_attr("srcset"):
            continue
        img_url = source["srcset"].split()[0]
        s_lower = img_url.lower()
        if any(x in s_lower for x in ("icon", "logo", "artwork")):
            continue
        res_match = SCREENSHOT_SIZE_RE.search(s_lower)
        if not res_match:
            continue
        w, h = int(res_match.group(1)), int(res_match.group(2))
        if w != h and (w >= 300 or h >= 300):
            s_jpg = img_url.replace(".webp", ".jpg").replace("w.webp", "bb.jpg")
            if s_jpg not in clean_screens:
                clean_screens.append(s_jpg)

    return clean_screens


def _parse_ios_page_html(html_content: str, screens: List[str]) -> Tuple[str, List[str]]:
    soup = BeautifulSoup(html_content, "html.parser")

    subtitle = ""
    for tag in soup.find_all(["p", "h2", "div"], class_=SUBTITLE_CLASS_RE):
        candidate = clean_subtitle_candidate(tag.get_text(" ", strip=True))
        if is_valid_subtitle_candidate(candidate):
            subtitle = candidate
            break

    if not subtitle:
        for sub_match in SUBTITLE_JSON_RE.finditer(html_content):
            candidate = clean_subtitle_candidate(decode_apple_subtitle(sub_match.group(1)))
            if is_valid_subtitle_candidate(candidate):
                subtitle = candidate
                break

    clean_screens = _collect_screenshots_from_soup(soup)
    if clean_screens:
        screens = clean_screens

    return subtitle, screens


def _apple_web_lang(locale: str) -> str:
    if locale.lower().startswith("iw"):
        return locale.replace("iw", "he", 1)
    return locale


def _itunes_lookup(pkg_id: str, c_code: str, apple_lang: str, *, allow_country_fallback: bool = False) -> dict:
    url = f"https://itunes.apple.com/lookup?id={pkg_id}&country={c_code}&lang={apple_lang}"
    res = requests.get(url, timeout=10).json()

    if res.get("resultCount", 0) == 0 and allow_country_fallback:
        url_fallback = f"https://itunes.apple.com/lookup?id={pkg_id}&country={c_code}"
        res = requests.get(url_fallback, timeout=10).json()

    if res.get("resultCount", 0) == 0:
        raise Exception(f"Приложение {pkg_id} не найдено в App Store ({c_code})")
    return res["results"][0]


def _lookup_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _lookup_matches_english(local_data: dict, english_data: dict) -> bool:
    if not english_data:
        return False
    local_title = _lookup_text(local_data.get("trackName", ""))
    english_title = _lookup_text(english_data.get("trackName", ""))
    local_description = _lookup_text(local_data.get("description", ""))
    english_description = _lookup_text(english_data.get("description", ""))
    return bool(local_title or local_description) and local_title == english_title and local_description == english_description


def _fetch_ios_web_page(pkg_id: str, c_code: str, locale: str, l_code: str, screens: List[str]) -> Tuple[str, List[str]]:
    web_lang = _apple_web_lang(locale)
    app_url = f"https://apps.apple.com/{c_code.lower()}/app/id{pkg_id}?{urlencode({'l': web_lang})}"
    headers = {
        "User-Agent": APPLE_USER_AGENT,
        "Accept-Language": f"{web_lang},{l_code};q=0.9,en-US;q=0.6",
    }
    response = requests.get(app_url, headers=headers, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    response.encoding = "utf-8"
    return _parse_ios_page_html(response.text, screens)


def _fetch_ios_app_data(pkg_id: str, locale: str, l_code: str, c_code: str) -> dict:
    apple_lang = locale.replace("-", "_").lower()
    data = _itunes_lookup(pkg_id, c_code, apple_lang, allow_country_fallback=True)
    screens = data.get("screenshotUrls", []) or data.get("ipadScreenshotUrls", [])
    icon_url = data.get("artworkUrl512", data.get("artworkUrl100", "")).replace(".webp", ".jpg")
    subtitle = ""
    subtitle_unavailable = False
    screenshots_unavailable = False
    web_locale = locale
    web_l_code = l_code

    if locale.lower() not in ("en", "en-us", "en_us"):
        try:
            english_data = _itunes_lookup(pkg_id, c_code, "en_us")
            if _lookup_matches_english(data, english_data):
                web_locale = "en-US"
                web_l_code = "en-US"
        except Exception as e:
            print(f"⚠️ Ошибка проверки английской локализации App Store: {e}")

    try:
        subtitle, screens = _fetch_ios_web_page(pkg_id, c_code, web_locale, web_l_code, screens)
    except Exception as e:
        subtitle_unavailable = True
        screenshots_unavailable = True
        print(f"⚠️ Ошибка парсера App Store HTML: {e}")
    else:
        if not subtitle and web_locale.lower() != "en-us":
            try:
                fallback_subtitle, _ = _fetch_ios_web_page(pkg_id, c_code, "en-US", "en-US", screens)
                subtitle = fallback_subtitle
            except Exception as e:
                print(f"⚠️ Ошибка fallback App Store HTML en-US: {e}")
        if not subtitle:
            subtitle_unavailable = True

    return {
        "title": data.get("trackName", ""),
        "summary": subtitle or "",
        "summary_unavailable": subtitle_unavailable,
        "screenshots_unavailable": screenshots_unavailable,
        "description": data.get("description", ""),
        "publisher": data.get("artistName") or data.get("sellerName", ""),
        "icon": icon_url or "",
        "headerImage": "",
        "screenshots": [s.replace(".webp", ".jpg") for s in screens],
    }


def fetch_app_data(pkg_id, locale: str) -> dict:
    clean_pkg_id = normalize_app_id(pkg_id)
    if not clean_pkg_id:
        raise ValueError("Package ID / App ID пустой или некорректный")

    l_code, c_code = _locale_codes(locale)
    if l_code == "iw":
        l_code = "iw"

    if clean_pkg_id.isdigit():
        return _fetch_ios_app_data(clean_pkg_id, locale, l_code, c_code)
    return gp_app(clean_pkg_id, lang=l_code, country=c_code)
