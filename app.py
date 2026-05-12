from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import re, requests, uvicorn
from bs4 import BeautifulSoup
from rapidfuzz import fuzz


app = FastAPI()


def mein_suchscript(letterboxd_username):
    import re, requests, json
    from bs4 import BeautifulSoup
    from rapidfuzz import fuzz

    WATCHLIST_URL = "https://letterboxd.com/" + letterboxd_username + "/watchlist/"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    filme = []

    page = 1

    while True:

        if page == 1:
            url = WATCHLIST_URL
        else:
            url = f"{WATCHLIST_URL}page/{page}/"

        print("Lade:", url)

        r = requests.get(url, headers=headers)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        items = soup.select("div.react-component[data-component-class='LazyPoster']")

        if not items:
            break

        for item in items:
            title = item.get("data-item-name")
            clean_title = re.sub(r"\s\(\d{4}\)$", "", title)

            poster_slug = item.get("data-item-slug")
            poster_url = "https://letterboxd.com/film/" + poster_slug + "/" if poster_slug else None

            filme.append({
                "title": clean_title,
                "poster_url": poster_url
            })

        next_button = soup.select_one("a.next")

        if not next_button:
            break

        page += 1

    BASE_URL = "https://katalog.stadtbibliothek-weimar.de"
    START_URL = BASE_URL + "/webOPACClient/start.do?Login=opextern&BaseURL=this"
    SEARCH_URL = BASE_URL + "/webOPACClient/search.do"

    def clean_title(title):
        title = title.replace("[Bildtonträger]", "")
        title = re.sub(r"\s+", " ", title)
        return title.strip()

    POSTER_CACHE = {}

    poster_session = requests.Session()
    poster_session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    def get_real_poster_url(letterboxd_film_url):

        if not letterboxd_film_url:
            return None

        if letterboxd_film_url in POSTER_CACHE:
            return POSTER_CACHE[letterboxd_film_url]

        try:
            r = poster_session.get(letterboxd_film_url, timeout=6)
            r.raise_for_status()

            html = r.text

            poster_url = None

            # 1. Schneller Weg: direkt im HTML suchen
            match = re.search(
                r'"image"\s*:\s*"(https://a\.ltrbxd\.com/resized/film-poster/[^"]+)"',
                html
            )

            if match:
                poster_url = match.group(1).replace("\\/", "/")

            # 2. Fallback: JSON-LD sauber auslesen
            if not poster_url:
                soup = BeautifulSoup(html, "html.parser")
                script = soup.select_one('script[type="application/ld+json"]')

                if script:
                    text = script.get_text()
                    text = text.replace("/* <![CDATA[ */", "")
                    text = text.replace("/* ]]> */", "")
                    text = text.strip()

                    data = json.loads(text)
                    poster_url = data.get("image")

            POSTER_CACHE[letterboxd_film_url] = poster_url
            return poster_url

        except Exception as e:
            print("Poster Fehler:", letterboxd_film_url, e)
            POSTER_CACHE[letterboxd_film_url] = None
            return None

    def search(filmliste):

        session = requests.Session()

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        session.get(START_URL, headers=headers)

        fertige_liste = []

        for film_data in filmliste:

            film = film_data["title"]
            letterboxd_film_url = film_data["poster_url"]

            params = {
                "methodToCall": "submit",
                "methodToCallParameter": "submitSearch",
                "searchCategories[0]": "-1",
                "searchString[0]": film,
                "submitSearch": "Suchen",
                "linguistic": "false",
                "selectedViewBranchlib": "0",
                "selectedSearchBranchlib": "0",
                "searchRestrictionID[0]": "3",
                "searchRestrictionValue1[0]": "",
                "searchRestrictionValue2[0]": "",
                "searchRestrictionID[1]": "2",
                "searchRestrictionValue1[1]": "",
                "searchRestrictionID[2]": "1",
                "searchRestrictionValue1[2]": "",
                "callingPage": "searchPreferences",
                "exemplarSorting": "1",
                "numberOfHits": "100",
                "rememberList": "-1",
                "timeOut": "10",
                "considerSearchRestriction": "2"
            }

            response = session.get(
                SEARCH_URL,
                params=params,
                headers=headers
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            treffer = soup.select("h2.recordtitle")

            bester_treffer = None
            bester_score = 0

            for treffer_element in treffer:

                link = treffer_element.find("a")

                if not link:
                    continue

                gefundener_titel_roh = link.get_text(strip=True)

                if "[Bildtonträger]" not in gefundener_titel_roh:
                    continue

                block_text = treffer_element.parent.get_text("\n", strip=True)

                zeilen = block_text.split("\n")

                kategorie = None
                status = None

                for zeile in zeilen:
                    if "Spielfilm" in zeile:
                        kategorie = zeile.replace("Spielfilm / ", "")

                    if "entliehen" in zeile.lower():
                        status = "entliehen"

                    if "ausleihbar" in zeile:
                        status = "ausleihbar"

                gefundener_titel = clean_title(gefundener_titel_roh)

                score = fuzz.token_sort_ratio(
                    film.lower(),
                    gefundener_titel.lower()
                )

                kandidat = {
                    "gesucht": film,
                    "gefunden": True,
                    "titel": gefundener_titel,
                    "score": score,
                    "kategorie": kategorie,
                    "status": status,
                    "url": response.url,
                    "poster_url": None
                }

                if score > bester_score:
                    bester_score = score
                    bester_treffer = kandidat

            if bester_treffer and bester_score > 50:
                bester_treffer["poster_url"] = get_real_poster_url(letterboxd_film_url)
                fertige_liste.append(bester_treffer)
                print(bester_treffer)
            else:
                fertige_liste.append({
                    "gesucht": film,
                    "gefunden": False,
                    "titel": None,
                    "score": 0,
                    "kategorie": None,
                    "status": None,
                    "url": None,
                    "poster_url": get_real_poster_url(letterboxd_film_url)
                })

        return fertige_liste

    ergebnisse = search(filme)

    return ergebnisse


@app.get("/", response_class=HTMLResponse)
def startseite():
    return """
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Letterboxd Bibliothek Suche</title>

        <style>
            * { box-sizing: border-box; }

            body {
                margin: 0;
                min-height: 100vh;
                background:
                    radial-gradient(circle at top, rgba(64,188,244,0.16), transparent 32%),
                    linear-gradient(180deg, #1f2933 0%, #14181c 62%);
                color: #9ab;
                font-family: Arial, Helvetica, sans-serif;
            }

            .topbar {
                background: #0f1419;
                border-bottom: 1px solid #26313b;
                padding: 18px 0;
            }

            .wrap {
                width: min(1200px, calc(100% - 32px));
                margin: 0 auto;
            }

            .brand {
                color: #fff;
                font-size: 26px;
                font-weight: 800;
                letter-spacing: -1px;
            }

            .center {
                min-height: calc(100vh - 66px);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 32px 0;
            }

            .card {
                width: min(620px, 100%);
                background: #1f2933;
                border: 1px solid #2c3946;
                border-radius: 14px;
                padding: 38px;
                box-shadow: 0 24px 70px rgba(0,0,0,0.42);
            }

            h1 {
                color: #fff;
                font-size: 34px;
                line-height: 1.1;
                margin: 0 0 12px;
            }

            p {
                font-size: 16px;
                line-height: 1.5;
                margin: 0 0 28px;
                color: #9ab;
            }

            label {
                display: block;
                color: #c8d4df;
                font-weight: bold;
                margin-bottom: 8px;
                text-transform: uppercase;
                font-size: 12px;
                letter-spacing: 0.08em;
            }

            input {
                width: 100%;
                padding: 15px 16px;
                border-radius: 8px;
                border: 1px solid #456;
                background: #2c3440;
                color: #fff;
                font-size: 18px;
                outline: none;
            }

            input:focus {
                border-color: #40bcf4;
                box-shadow: 0 0 0 3px rgba(64,188,244,0.18);
            }

            button {
                margin-top: 18px;
                width: 100%;
                border: 0;
                border-radius: 8px;
                padding: 15px 18px;
                background: #00ac1c;
                color: white;
                font-size: 16px;
                font-weight: 800;
                cursor: pointer;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            button:hover { background: #00c030; }

            @media (max-width: 600px) {
                .brand { font-size: 21px; }
                .card { padding: 24px; }
                h1 { font-size: 28px; }
            }
        </style>
    </head>

    <body>
        <div class="topbar">
            <div class="wrap">
                <div class="brand">Letterboxd Bibliothek</div>
            </div>
        </div>

        <main class="center">
            <section class="card">
                <h1>Watchlist suchen</h1>
                <p>
                    Gib deinen Letterboxd-Benutzernamen ein. Danach wird deine Watchlist
                    mit dem Katalog der Stadtbibliothek Weimar abgeglichen.
                </p>

                <form action="/suchen" method="get">
                    <label for="username">Letterboxd Benutzername</label>
                    <input type="text" id="username" name="username" placeholder="username" required>
                    <button type="submit">Watchlist prüfen</button>
                </form>
            </section>
        </main>
    </body>
    </html>
    """


@app.get("/suchen", response_class=HTMLResponse)
def suchen(username: str):

    ergebnisse = mein_suchscript(username)

    html = baue_ergebnis_html(
        titel=f"Ergebnisse für {username}",
        untertitel="Watchlist-Abgleich mit dem Katalog der Stadtbibliothek Weimar",
        ergebnisse=ergebnisse
    )

    return html


def make_bib_search_url(title):
    return (
        "https://katalog.stadtbibliothek-weimar.de/webOPACClient/search.do"
        "?methodToCall=submit"
        "&methodToCallParameter=submitSearch"
        "&searchCategories%5B0%5D=-1"
        "&searchString%5B0%5D=" + requests.utils.quote(title)
        + "&submitSearch=Suchen"
        "&linguistic=false"
        "&selectedViewBranchlib=0"
        "&selectedSearchBranchlib=0"
        "&numberOfHits=100"
    )


def baue_ergebnis_html(titel, untertitel, ergebnisse):

    gefundene = [e for e in ergebnisse if e.get("gefunden")]
    nicht_gefundene = [e for e in ergebnisse if not e.get("gefunden")]

    html = f"""
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Ergebnisse</title>

        <style>
            * {{ box-sizing: border-box; }}

            body {{
                margin: 0;
                background: #14181c;
                color: #9ab;
                font-family: Arial, Helvetica, sans-serif;
            }}

            .topbar {{
                background: #0f1419;
                border-bottom: 1px solid #26313b;
                padding: 18px 0;
            }}

            .wrap {{
                width: min(1200px, calc(100% - 32px));
                margin: 0 auto;
            }}

            .brand {{
                color: #fff;
                font-size: 26px;
                font-weight: 800;
                letter-spacing: -1px;
            }}

            .headline {{
                padding: 26px 0 24px;
                border-bottom: 1px solid #26313b;
            }}

            .topline {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                margin-bottom: 18px;
            }}

            .new-search {{
                color: #40bcf4;
                text-decoration: none;
                font-weight: bold;
                white-space: nowrap;
            }}

            .new-search:hover {{ color: #fff; }}

            h1 {{
                color: #fff;
                margin: 0 0 8px;
                font-size: 34px;
            }}

            .sub {{
                margin: 0;
                color: #789;
                font-size: 15px;
            }}

            .section-title {{
                margin: 34px 0 18px;
                color: #fff;
                font-size: 22px;
                font-weight: 800;
                border-bottom: 1px solid #2c3946;
                padding-bottom: 12px;
            }}

            .section-title span {{
                color: #789;
                font-size: 15px;
                font-weight: normal;
                margin-left: 8px;
            }}

            .result-list {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
                gap: 18px;
                padding-bottom: 20px;
            }}

            .result-card {{
                background: #1f2933;
                border: 1px solid #2c3946;
                border-radius: 12px;
                padding: 14px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.22);
                transition: transform 0.15s ease, border-color 0.15s ease;
            }}

            .result-card:hover {{
                transform: translateY(-3px);
                border-color: #40bcf4;
            }}

            .poster {{
                width: 100%;
                aspect-ratio: 2 / 3;
                object-fit: cover;
                border-radius: 8px;
                margin-bottom: 14px;
                background: #111820;
                border: 1px solid #33414f;
                display: block;
            }}

            .poster-placeholder {{
                width: 100%;
                aspect-ratio: 2 / 3;
                border-radius: 8px;
                margin-bottom: 14px;
                background: linear-gradient(135deg, #202a34, #111820);
                border: 1px solid #33414f;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #567;
                font-size: 42px;
            }}

            .original-title {{
                display: block;
                color: #fff;
                font-size: 19px;
                font-weight: bold;
                line-height: 1.25;
                text-decoration: none;
                margin-bottom: 8px;
            }}

            .original-title:hover {{ color: #40bcf4; }}

            .matched-title {{
                color: #789;
                font-size: 14px;
                line-height: 1.35;
                margin-bottom: 12px;
            }}

            .matched-title a {{
                color: #9ab;
                text-decoration: none;
            }}

            .matched-title a:hover {{ color: #40bcf4; }}

            .info {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 12px;
            }}

            .info-pill {{
                border: 1px solid #33414f;
                background: #141c24;
                border-radius: 999px;
                padding: 7px 10px;
                font-size: 13px;
                color: #c8d4df;
                line-height: 1.2;
            }}

            .info-pill strong {{
                color: #678;
                text-transform: uppercase;
                font-size: 10px;
                letter-spacing: 0.06em;
                margin-right: 5px;
            }}

            .missing-section {{
                margin-top: 34px;
                padding-top: 10px;
                border-top: 1px solid #33414f;
            }}

            .missing-card {{ opacity: 0.78; }}

            @media (max-width: 600px) {{
                .wrap {{ width: min(100% - 20px, 1200px); }}
                .brand {{ font-size: 21px; }}

                .topline {{
                    align-items: flex-start;
                    flex-direction: column;
                    gap: 10px;
                }}

                h1 {{
                    font-size: 26px;
                    line-height: 1.15;
                }}

                .result-list {{
                    grid-template-columns: 1fr;
                    gap: 12px;
                }}

                .result-card {{
                    display: grid;
                    grid-template-columns: 92px 1fr;
                    gap: 14px;
                    padding: 12px;
                    align-items: start;
                }}

                .poster,
                .poster-placeholder {{
                    margin-bottom: 0;
                    border-radius: 7px;
                }}

                .mobile-content {{ min-width: 0; }}
                .original-title {{ font-size: 17px; }}
                .matched-title {{ font-size: 13px; }}

                .info {{
                    gap: 6px;
                }}

                .info-pill {{
                    font-size: 12px;
                    padding: 6px 8px;
                }}
            }}
        </style>
    </head>

    <body>
        <div class="topbar">
            <div class="wrap">
                <div class="brand">Letterboxd Bibliothek</div>
            </div>
        </div>

        <section class="headline">
            <div class="wrap">
                <div class="topline">
                    <div>
                        <h1>{titel}</h1>
                        <p class="sub">{untertitel} · {len(gefundene)} gefunden · {len(nicht_gefundene)} nicht gefunden</p>
                    </div>

                    <a class="new-search" href="/">Neue Suche</a>
                </div>
            </div>
        </section>

        <main class="wrap">
            <h2 class="section-title">Gefunden <span>{len(gefundene)} Filme</span></h2>
            <div class="result-list">
    """

    for eintrag in gefundene:

        bib_url = make_bib_search_url(eintrag.get("gesucht", ""))

        if eintrag.get("poster_url"):
            poster_html = f"""
                    <a href="{bib_url}" target="_blank">
                        <img class="poster" src="{eintrag.get("poster_url")}" alt="{eintrag.get("gesucht", "")}">
                    </a>
            """
        else:
            poster_html = '<div class="poster-placeholder">🎬</div>'

        html += f"""
                <article class="result-card">
                    {poster_html}

                    <div class="mobile-content">
                        <a class="original-title" href="{bib_url}" target="_blank">
                            {eintrag.get("gesucht", "")}
                        </a>

                        <div class="matched-title">
                            Gefundener Titel:
                            <a href="{bib_url}" target="_blank">
                                {eintrag.get("titel") or ""}
                            </a>
                        </div>

                        <div class="info">
                            <div class="info-pill"><strong>Kategorie</strong>{eintrag.get("kategorie") or "-"}</div>
                            <div class="info-pill"><strong>Status</strong>{eintrag.get("status") or "-"}</div>
                        </div>
                    </div>
                </article>
        """

    html += """
            </div>

            <section class="missing-section">
    """

    html += f"""
                <h2 class="section-title">Nicht gefunden <span>{len(nicht_gefundene)} Filme</span></h2>
                <div class="result-list">
    """

    for eintrag in nicht_gefundene:

        bib_url = make_bib_search_url(eintrag.get("gesucht", ""))

        if eintrag.get("poster_url"):
            poster_html = f"""
                    <a href="{bib_url}" target="_blank">
                        <img class="poster" src="{eintrag.get("poster_url")}" alt="{eintrag.get("gesucht", "")}">
                    </a>
            """
        else:
            poster_html = '<div class="poster-placeholder">🎬</div>'

        html += f"""
                    <article class="result-card missing-card">
                        {poster_html}

                        <div class="mobile-content">
                            <a class="original-title" href="{bib_url}" target="_blank">
                                {eintrag.get("gesucht", "")}
                            </a>

                            <div class="matched-title">Kein passender Bildtonträger gefunden</div>
                        </div>
                    </article>
        """

    html += """
                </div>
            </section>
        </main>
    </body>
    </html>
    """

    return html


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000
    )
