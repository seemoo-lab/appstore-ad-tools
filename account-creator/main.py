#!/usr/bin/env python3

"""
Tool to aid the creation of Apple/Google accounts.
"""

import argparse
from random import shuffle
import sys
from google_acc import create_google_account
from apple import create_apple_account, handle_sim_only
import psycopg
import os
from datetime import datetime
import subprocess as s
from dotenv import load_dotenv
from time import sleep

def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        prog='main',
        description='Tool to aid the creation of Apple/Google accounts.')
    parser.add_argument("-p", "--platform", help="Restrict account creation to given platform.",
                        required=True, choices=["android", "ios"])
    parser.add_argument("-l", "--limit", help="Limits the number of created accounts.", required=False)
    args = parser.parse_args()

    # fetch accounts that require creation
    conn = psycopg.connect(dbname=os.environ.get('DB_NAME'),
                        user=os.environ.get('DB_USER'),
                        host='localhost',
                        password=os.environ.get('DB_PASSWORD'),
                        port=os.environ.get('DB_PORT'))
    cur = conn.cursor()

    serial = "ANDROID_DEVICE_ID_7"

    if args.limit:
        cur.execute("SELECT email,sur_name,first_name,password,birth,gender,phonenumber,street,city,postalcode,street_number,country,platform FROM account WHERE created_at IS NULL AND platform = %s ORDER BY email DESC LIMIT %s;", (args.platform, args.limit))
    else:
        cur.execute("SELECT email,sur_name,first_name,password,birth,gender,phonenumber,street,city,postalcode,street_number,country,platform FROM account WHERE created_at IS NULL AND platform = %s ORDER BY email DESC;", (args.platform,))
    
    accounts = cur.fetchall()
    shuffle(accounts) # debug only
    conn.commit()
    conn.close()

    for account in accounts:

        print(f"Creating account: {account}")
        # unpack data from database
        args.email, args.sur_name, args.first_name, args.password, args.birth, args.gender, args.phonenumber, args.street, args.city, args.postalcode, args.street_number, args.country, args.platform = account

        # preprocess birthdate
        args.birthdate_day = str(args.birth.day)
        args.birthdate_month = str(args.birth.month)
        args.birthdate_year = str(args.birth.year)

        if args.platform == "ios":
            handle_sim_only(args)
        else:
            # retry until successful
            try:
                result = create_google_account(args)
            except Exception as e:
                input(f"Got exception {e}, hit enter to continue.")
                result = None
            while not result:
                print(f"Failed to create account {args.email}, retrying in 60s.")
                sleep(60)
                # set retry = True so we do not re-install the sim
                result = create_google_account(args, True)

        # connection dies after a time, trying to avoid that by opening a new connection when necessary
        conn = psycopg.connect(dbname=os.environ.get('DB_NAME'),
                        user=os.environ.get('DB_USER'),
                        host='localhost',
                        password=os.environ.get('DB_PASSWORD'),
                        port=os.environ.get('DB_PORT'))
        cur = conn.cursor()

        # update that this account has been created
        cur.execute("UPDATE account SET created_at = %s WHERE email = %s;",
                    (datetime.now().isoformat(), args.email))

        conn.commit()
        conn.close()

        print("Sleeping 10 min after account creation.")
        sleep(60 * 10)

if __name__ == "__main__":
    sys.exit(main())
