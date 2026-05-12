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

    WATCHLIST_URL = "https://letterboxd.com/ludwiglehmann/watchlist/"

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

    def get_real_poster_url(letterboxd_film_url):

        if not letterboxd_film_url:
            return None

        try:
            r = requests.get(letterboxd_film_url, headers=headers, timeout=10)
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")

            script = soup.select_one('script[type="application/ld+json"]')

            if not script:
                return None

            text = script.text
            text = text.replace("/* <![CDATA[ */", "")
            text = text.replace("/* ]]> */", "")
            text = text.strip()

            data = json.loads(text)

            return data.get("image")

        except Exception as e:
            print("Poster Fehler:", letterboxd_film_url, e)
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
                "selectedSearchBranchlib": "",
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
                    "url": response.url,
                    "poster_url": None
                }

                if score > bester_score:
                    bester_score = score
                    bester_treffer = kandidat

            if bester_treffer and bester_score > 50:
                bester_treffer["poster_url"] = get_real_poster_url(letterboxd_film_url)
                fertige_liste.append(bester_treffer)
            else:
                fertige_liste.append({
                    "gesucht": film,
                    "gefunden": False,
                    "titel": None,
                    "score": 0,
                    "url": None,
                    "poster_url": None
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
        <title>Letterboxd Bibliothek Suche</title>

        <style>
            * {
                box-sizing: border-box;
            }

            body {
                margin: 0;
                min-height: 100vh;
                background:
                    radial-gradient(circle at top, rgba(64,188,244,0.16), transparent 32%),
                    linear-gradient(180deg, #1f2933 0%, #14181c 62%);
                color: #9ab;
                font-family: Arial, Helvetica, sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .card {
                width: min(620px, calc(100% - 40px));
                background: #1f2933;
                border: 1px solid #2c3946;
                border-radius: 14px;
                padding: 38px;
                box-shadow: 0 24px 70px rgba(0,0,0,0.42);
            }

            h1 {
                color: #fff;
                font-size: 38px;
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

            input::placeholder {
                color: #6f7f8d;
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

            button:hover {
                background: #00c030;
            }
        </style>
    </head>

    <body>
        <main class="card">
            <h1>Watchlist in der Bibliothek suchen</h1>
            <p>
                Gib deinen Letterboxd-Benutzernamen ein. Danach wird deine Watchlist
                mit dem Katalog der Stadtbibliothek Weimar abgeglichen.
            </p>

            <form action="/suchen" method="get">
                <label for="username">Letterboxd Benutzername</label>
                <input type="text" id="username" name="username" placeholder="username" required>
                <button type="submit">Suchen</button>
            </form>
        </main>
    </body>
    </html>
    """


@app.get("/suchen", response_class=HTMLResponse)
def suchen(username: str):

    ergebnisse = mein_suchscript(username)

    gefundene = [e for e in ergebnisse if e.get("gefunden")]
    nicht_gefundene = [e for e in ergebnisse if not e.get("gefunden")]

    html = f"""
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <title>Ergebnisse</title>

        <style>
            * {{
                box-sizing: border-box;
            }}

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
                width: min(1200px, calc(100% - 40px));
                margin: 0 auto;
            }}

            .brand {{
                color: #fff;
                font-size: 26px;
                font-weight: 800;
                letter-spacing: -1px;
            }}

            .headline {{
                padding: 44px 0 26px;
                border-bottom: 1px solid #26313b;
            }}

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
                margin: 34px 0 14px;
                color: #c8d4df;
                font-size: 15px;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                border-bottom: 1px solid #2c3946;
                padding-bottom: 10px;
            }}

            .result-list {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
                gap: 18px;
                padding-bottom: 20px;
            }}

            .result-card {{
                background: #1f2933;
                border: 1px solid #2c3946;
                border-radius: 12px;
                padding: 14px;
                min-height: 145px;
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

            .original-title {{
                display: block;
                color: #fff;
                font-size: 19px;
                font-weight: bold;
                line-height: 1.25;
                text-decoration: none;
                margin-bottom: 8px;
            }}

            .original-title:hover {{
                color: #40bcf4;
            }}

            .matched-title {{
                color: #789;
                font-size: 14px;
                line-height: 1.35;
                margin-bottom: 14px;
            }}

            .matched-title a {{
                color: #9ab;
                text-decoration: none;
            }}

            .matched-title a:hover {{
                color: #40bcf4;
            }}

            .badge {{
                display: inline-block;
                border-radius: 999px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}

            .badge-ok {{
                background: rgba(0, 224, 84, 0.15);
                color: #00e054;
            }}

            .badge-no {{
                background: rgba(255, 128, 0, 0.16);
                color: #ffb36b;
            }}

            .score {{
                margin-top: 10px;
                font-size: 13px;
                color: #789;
            }}

            .missing-section {{
                margin-top: 28px;
                padding-top: 10px;
                border-top: 1px solid #33414f;
            }}

            .missing-card {{
                opacity: 0.72;
            }}

            .back {{
                display: inline-block;
                margin: 34px 0 46px;
                color: #40bcf4;
                text-decoration: none;
                font-weight: bold;
            }}

            .back:hover {{
                color: #fff;
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
                <h1>Ergebnisse für {username}</h1>
                <p class="sub">{len(gefundene)} gefunden · {len(nicht_gefundene)} nicht gefunden</p>
            </div>
        </section>

        <main class="wrap">
            <h2 class="section-title">Gefunden</h2>
            <div class="result-list">
    """

    for eintrag in gefundene:
        poster_html = ""

        if eintrag.get("poster_url"):
            poster_html = f"""
                    <a href="{eintrag.get("url")}" target="_blank">
                        <img class="poster" src="{eintrag.get("poster_url")}" alt="{eintrag.get("gesucht", "")}">
                    </a>
            """

        html += f"""
                <article class="result-card">
                    {poster_html}

                    <a class="original-title" href="{eintrag.get("url")}" target="_blank">
                        {eintrag.get("gesucht", "")}
                    </a>

                    <div class="matched-title">
                        Gefundener Titel:
                        <a href="{eintrag.get("url")}" target="_blank">
                            {eintrag.get("titel") or ""}
                        </a>
                    </div>

                    <span class="badge badge-ok">Gefunden</span>
                    <div class="score">Trefferqualität: {eintrag.get("score", 0)}</div>
                </article>
        """

    html += """
            </div>

            <section class="missing-section">
                <h2 class="section-title">Nicht gefunden</h2>
                <div class="result-list">
    """

    for eintrag in nicht_gefundene:
        poster_html = ""

        if eintrag.get("poster_url"):
            poster_html = f"""
                        <img class="poster" src="{eintrag.get("poster_url")}" alt="{eintrag.get("gesucht", "")}">
            """

        html += f"""
                    <article class="result-card missing-card">
                        {poster_html}

                        <div class="original-title">{eintrag.get("gesucht", "")}</div>
                        <div class="matched-title">Kein passender Bildtonträger gefunden</div>
                        <span class="badge badge-no">Nicht gefunden</span>
                    </article>
        """

    html += """
                </div>
            </section>

            <a class="back" href="/">← Neue Suche</a>
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
