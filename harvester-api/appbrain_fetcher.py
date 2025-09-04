import requests as r
from bs4 import BeautifulSoup
from random import shuffle
from time import sleep

def get_top_apps_android(logger, category, limit):
    """Returns a shuffled list of the top <limit> apps in Germany within a category, as fetched from appbrain.
    """


    url = f"https://www.appbrain.com/stats/google-play-rankings/top_free/{category}/de"
    google_url = "https://play.google.com/store/apps/details?id="
    rankings = r.get(url).text
    soup = BeautifulSoup(rankings, "lxml")

    app_list = []
    for td in soup.find("table").find_all("td"):
        for tag in td.find_all("a"):
            if tag.text and tag['href'] and tag['href'].startswith("/app/"):
                app_name = tag.text
                app_id = tag['href'].replace("/app/", "").split("/")[1]


                # normalize name -> sometimes, google localised names differ from appbrain's.
                while True:
                    try:
                        resp = r.get(google_url + app_id,
                                 headers = {"Accept-Language": "en-US,en;q=0.5",
                                            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"}
                                 ).text
                        break
                    except r.exceptions.ConnectionError:
                        logger.info("Caught ConnectionError, retrying.")
                        sleep(2)

                soup = BeautifulSoup(resp, "lxml")
                google_name = soup.find("title").text.replace(" - Apps on Google Play", "")

                # if an app is usk 18, we cannot install it without providing proof of age
                content_rating  = soup.find("span", itemprop="contentRating").find("span").text
                if content_rating in ["USK: Ages 18+"]:
                    logger.warning(f"App {app_name} has content rating {content_rating}, skipping.")
                    continue

                if app_name != google_name:
                    logger.info(f"App {app_name} has different Google Name: {google_name}, using Google name instead.")
                    app_name = google_name


                logger.info(f"Found {(app_name, app_id)}.")
                app_list.append((app_name, app_id))

    # cut off below limit
    app_list = app_list[:limit]

    # shuffle apps
    shuffle(app_list)

    if len(app_list) < limit:
        logger.warning(f"Only found {len(app_list)} apps instead of {limit}.")

    return app_list
