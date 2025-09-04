"""Helper script to check that the names associated with a persona have not changed since its creation."""

import logging
from dotenv import load_dotenv
import psycopg
import sys
import os
import requests as r
from time import sleep
from bs4 import BeautifulSoup

# logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
# create formatter (time is part of journal anyways)
formatter = logging.Formatter('%(levelname)s - %(message)s')
# add formatter to ch
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)

def get_db_connection():
    return psycopg.connect(host="localhost",
                           dbname=os.environ["DB_NAME"],
                           user=os.environ["DB_USER"],
                           password=os.environ["DB_PASSWORD"])

google_url = "https://play.google.com/store/apps/details?id="


### ENTRY POINT
load_dotenv()
conn = get_db_connection()


if len(sys.argv) < 2:
    print(f"usage: {sys.argv[0]} <persona_id>")
    sys.exit(0)

persona_id = int(sys.argv[1])

# get all persona apps
cur = conn.cursor()
cur.execute("""select app.google_id, name from app join link_persona_app on link_persona_app.app_id = app.id where link_persona_app.persona_id = %s;""",
            (persona_id, ))
app_ids = cur.fetchall()


for app_id, name in app_ids:
    # print(app_id, name)

    # retrieve current google name
    while True:
        try:
            resp = r.get(
                google_url + app_id,
                headers={
                    "Accept-Language": "en-US,en;q=0.5",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
                },
            ).text
            break
        except r.exceptions.ConnectionError:
            logger.info("Caught ConnectionError, retrying.")
            sleep(2)

    # extract name and age restriction
    soup = BeautifulSoup(resp, "lxml")
    google_name = soup.find("title").text.replace(" - Apps on Google Play", "")

    # if an app is usk 18, we cannot install it without providing proof of age
    cr_container = soup.find("span", itemprop="contentRating")
    if cr_container is None:
        print(f"Failed to find age container for: {app_id}, {name}. App might no longer exist?")
        continue
    content_rating = cr_container.find("span").text
    if content_rating in ["USK: Ages 18+"]:
        logger.warning(f"App {name} has content rating {content_rating}!!")

    if name != google_name:
        logger.warning(f"App {app_id} '{name}' has different Google Name: '{google_name}'!!!")

conn.close()
