#!python3


"""Helper script to transfer a persona from iOS to Android.
"""

import sys
import psycopg
import os
from dotenv import load_dotenv
from appstore_api import fetch_app_details_android, look_up_app_id_android
import logging
import json
from subprocess import check_output

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
    return psycopg.connect(host="localhost", dbname=os.environ["DB_NAME"],
                           user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"])


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} persona_id_source persona_id_target")
        return 0

    per_id_src = int(sys.argv[1])
    per_id_dst = int(sys.argv[2])
    
    # get all the apps from src
    load_dotenv()

    # open db connection
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("select app.id, app.apple_id, app.app_detail_id, app.name from app join link_persona_app on link_persona_app.app_id = app.id where link_persona_app.persona_id = %s;", (per_id_src,))
    apps = cur.fetchall()

    for app in apps:
        if True:
            android_app_id = app
            # check if this app is already in the database
            cur.execute("SELECT id, google_id FROM app WHERE google_id = %s;", (android_app_id,))
            result = cur.fetchone()
            details = fetch_app_details_android(android_app_id, logger)
            if details["contentRating"] == "USK: Ages 18+":
                print(app, "ONLY USK 18!!")

            if result is None:
                # details for sanity checking.
                print(json.dumps(details, indent=4))
                # check_output(["xdg-open", details["url"]])
                if True or input("Add this app? (y/n): ").lower().strip() == "y":
                    cur.execute("INSERT INTO app (google_id, name) VALUES (%s, %s) RETURNING id;",
                                (android_app_id, details["name"]))
                    app_id = cur.fetchone()[0]
                    logger.info(f"Inserted {android_app_id} with new id {app_id}")
                else:
                    continue
            else:
                app_id = result[0]
                logger.info(f"{android_app_id} ({android_app_id}) is already in Database with id {app_id}.")

            # test if app is already associated with persona
            cur.execute("SELECT * FROM link_persona_app WHERE persona_id = %s AND app_id = %s;", (per_id_dst,
                                                                                                  app_id))
            result = cur.fetchone()

            if result is None:
                cur.execute("INSERT INTO link_persona_app (persona_id, app_id) VALUES (%s, %s);", (per_id_dst, app_id))
                logger.info(f"Added relation from {android_app_id} to {per_id_dst}")
            else:
                logger.info(f"App {android_app_id} - in db as {app_id} - is already associated with persona {per_id_dst}.")
        else:
            logger.warning(f"Could not find entry for {app}!!")
    #close db
    conn.commit()
    conn.close()

if __name__ == '__main__':
    sys.exit(main())
