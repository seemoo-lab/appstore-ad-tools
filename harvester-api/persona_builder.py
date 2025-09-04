#!python3

from appstore_api import fetch_app_details_ios, look_up_app_id_android, get_top_apps_ios
from appbrain_fetcher import get_top_apps_android
from dotenv import load_dotenv
import os, sys, argparse, psycopg
import logging

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


def insert_android_apps_into_db(conn, logger, category, limit, persona_id):
    cur = conn.cursor()
    apps = get_top_apps_android(logger, category, limit)

    for app in apps:
        app_name, google_id = app

        # check if this app is already in the database
        cur.execute("SELECT id, google_id, apple_id FROM app WHERE google_id = %s;", (google_id,))
        result = cur.fetchone()
        if result is None:
            # insert entry into db
            cur.execute("INSERT INTO app (name, google_id) VALUES (%s, %s) RETURNING id;",
                        (app_name, google_id))
            app_id = cur.fetchone()[0]
            logger.info(f"Inserted {app_name} with new id {app_id}")
        else:
            app_id = result[0]
            logger.info(f"{app_name} ({google_id}) is already in Database with id {app_id}.")
            
        # test if app is already associated with persona
        cur.execute("SELECT * FROM link_persona_app WHERE persona_id = %s AND app_id = %s;", (persona_id, app_id))
        result = cur.fetchone()

        if result is None:
            cur.execute("INSERT INTO link_persona_app (persona_id, app_id) VALUES (%s, %s);", (persona_id, app_id))
            logger.info(f"Added relation from {app_name} to {persona_id}")
        else:
            logger.info(f"App {app_name} is already associated with persona {persona_id}.")
    conn.commit()

            
def insert_ios_apps_into_db(db_conn, logger, genre_id, limit, persona_id):
    cur = db_conn.cursor()

    apps = get_top_apps_ios(logger, genre_id, limit)

    for app in apps:
        app_name = app[2]
        apple_id = app[1]
        cur.execute("SELECT id, google_id, apple_id FROM app WHERE apple_id = %s;", (apple_id,))
        result = cur.fetchone()

        if result is None:
            # insert entry into db
            cur.execute("INSERT INTO app (name, apple_id) VALUES (%s, %s) RETURNING id;",
                        (app_name, apple_id))
            app_id = cur.fetchone()[0]
            logger.info(f"Inserted {app_name} with new id {app_id}")
        else:
            app_id = result[0]
            logger.info(f"{app_name} ({apple_id}) is already in Database with id {app_id}.")

        #test if app is already associated with persona
        cur.execute("SELECT * FROM link_persona_app WHERE persona_id = %s AND app_id = %s;", (persona_id, app_id))
        result = cur.fetchone()

        if result is None:
            cur.execute("INSERT INTO link_persona_app (persona_id, app_id) VALUES (%s, %s);", (persona_id, app_id))
            logger.info(f"Added relation from {app_name} to {persona_id}")
        else:
            logger.info(f"App {app_name} is already associated with persona {persona_id}.")

    db_conn.commit()

def insert_ios_app_by_name_into_db(db_conn, logger, search_term, persona_id):
    cur = db_conn.cursor()

    details = fetch_app_details_ios(search_term, logger)
    app_name = details["attributes"]["name"]
    bundle_id = details["attributes"]["platformAttributes"]["ios"]["bundleId"]

    cur.execute("INSERT INTO app (name, apple_id) VALUES (%s, %s) RETURNING id;",
                        (app_name, bundle_id))
    app_id = cur.fetchone()[0]
    logger.info(f"Inserted {app_name} with new id {app_id}")

    #test if app is already associated with persona
    cur.execute("SELECT * FROM link_persona_app WHERE persona_id = %s AND app_id = %s;", (persona_id, app_id))
    result = cur.fetchone()

    if result == None:
        cur.execute("INSERT INTO link_persona_app (persona_id, app_id) VALUES (%s, %s);", (persona_id, app_id))
        logger.info(f"Added relation from {app_name} to {persona_id}")
    else:
        logger.info(f"App {app_name} is already associated with persona {persona_id}.")

    db_conn.commit()

def main():
    load_dotenv()
    #argument parsing...
    parser = argparse.ArgumentParser(description="Utility to fetch and insert app ids for a given persona_id.")
    parser.add_argument('persona_id')
    parser.add_argument('--ios', action='store_true')
    parser.add_argument('--android', action='store_true')
    parser.add_argument('--appbrain_category')
    parser.add_argument('--ios_genre_id')
    parser.add_argument('--limit', default=50)
    parser.add_argument('--from_file', default="")
    args=parser.parse_args()
    persona_id = args.persona_id

    # open db connection
    conn = get_db_connection()
    #ios approach
    if args.ios:
        if args.from_file != "":
            with open(args.from_file) as f:
                for line in f.readlines():
                    insert_ios_app_by_name_into_db(conn, logger, line.strip("\n"), persona_id)
        else:
            insert_ios_apps_into_db(conn, logger, args.ios_genre_id, int(args.limit), persona_id)
    elif args.android:
        if args.from_file:
            raise NotImplementedError("Inserting personas from a file is not yet supported on Android.")
        else:
            insert_android_apps_into_db(conn, logger, args.appbrain_category, int(args.limit), persona_id)

    #close db
    conn.close()

if __name__ == '__main__':
    sys.exit(main())
