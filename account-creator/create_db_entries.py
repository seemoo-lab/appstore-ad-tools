#!/usr/bin/env python3

"""Helper script to create a large number of accounts from csv.
Expected CVS format example:
sur_name,first_name,birth,gender,platform,fresh_phonenumber,number_accs
mustermann,max,1.1.1990,male,ios,1,5
mustermann,max,1.1.1990,male,android,0,5
"""

from typing_extensions import ParamSpecArgs
import psycopg
import os
import csv
import sys
import random
import string
from dotenv import load_dotenv

defaults = {'first_name': 'Alex',
            'sur_name': 'Mueller',
            'gender': 'prefer_not_to_say',
            'country': 'germany'}

def populate_apple_account(row, cur):
    # get next free id for this combination (technically speaking, this should be sanitized I guess, but who cares)
    prefix = f'{row["first_name"]}-{row["sur_name"]}'.replace("ü", "ue")
    pattern = f'{prefix}%@seemoo.de'
    cur.execute(f'SELECT email FROM account WHERE email like \'{pattern}\' ORDER BY email DESC LIMIT 1;')
    email = cur.fetchone()

    # no email found, start by 0
    if not email:
        email_id = '0'
    else:
        offset = len(prefix)
        email_id = str(int(email[0][offset:offset+6]) + 1)
    row['email'] = f'{prefix}{email_id.zfill(6)}@seemoo.de'

    # use defaults
    row['street'] = 'Pankratiusstrasse'
    row['city'] = 'Darmstadt'
    row['street_number'] = 2
    row['postalcode'] = 64289

def populate_google_account(row, cur):
    email_id = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    row['email'] = f'{row["first_name"]}.{row["sur_name"]}{email_id}@gmail.com'.replace("ü", "ue")

    # no location necessary for Google
    row['street'] = row['city'] = ''
    row['postalcode'] = row['street_number'] = 0

    # check if this email already exists
    cur.execute(f'SELECT email FROM account WHERE email = %s;', (row['email'],))
    email = cur.fetchone()
    if email:
        # retry again
        return populate_google_account(row, cur)

def find_phonenumber(fresh, cur, platform):
    """Selects a phonenumber from the database. If fresh is true, makes sure that this phone number is not yet taken.
    """

    if fresh:
        # we exceeded the fresh sim cards, so now we have to re-use apple sims for google accounts and vice versa
        # cur.execute("""SELECT sim.phonenumber FROM sim WHERE (SELECT count(*) FROM account WHERE account.phonenumber = sim.phonenumber) = 0 AND address = 'man-gto.prod.ondemandconnectivity.com' AND broken = false;""")
        opposed_platform = "ios" if platform == 'android' else 'android'
        cur.execute("""SELECT sim.phonenumber FROM sim WHERE sim.phonenumber in (SELECT DISTINCT account.phonenumber FROM account join experiment on account.email = experiment.account_email where experiment.platform = %s) AND sim.phonenumber not in (SELECT DISTINCT account.phonenumber FROM account where platform = %s AND account.phonenumber is not null) AND address = 'man-gto.prod.ondemandconnectivity.com' AND broken = false;""", (opposed_platform, platform))
        print(f"No more fresh sims, falling back to using numbers on opposite platform of {platform}.")
        number = cur.fetchone()
        if not number:
            print("ERROR: Could not find a fresh phone number to create account with!!")
            sys.exit(-1)
        else:
            return number
    else:
        # prefer used sim, but ones that haven't been used much
        cur.execute("""
        SELECT sim.phonenumber
        FROM sim
        JOIN (SELECT account.phonenumber, COUNT(*) FROM account GROUP BY account.phonenumber) AS usage
        ON sim.phonenumber = usage.phonenumber
        WHERE count > 0
        AND sim.address = 'man-gto.prod.ondemandconnectivity.com'
        AND broken = false
        ORDER by count ASC;
        """)
        number = cur.fetchone()
        if not number:
            # There are no numbers that already have been used, fall back to fresh number
            return find_phonenumber(True, cur, platform)
        else:
            return number

def main():
    load_dotenv()

    if len(sys.argv) < 2:
        print(f'Usage: python3 {sys.argv[0]} <csv_filename>')
        return 0

    conn = psycopg.connect(dbname=os.environ.get('DB_NAME'),
                        user=os.environ.get('DB_USER'),
                        host='localhost',
                        password=os.environ.get('DB_PASSWORD'),
                        port=os.environ.get('DB_PORT'))
    cur = conn.cursor()

    with open(sys.argv[1], newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # apply defaults
            for k in defaults.keys():
                if not row.get(k):
                    row[k] = defaults[k]

            # sanity checks
            if not row['birth']:
                raise NotImplementedError('neutral age not yet determined.')
            if not row['platform']:
                raise ValueError('platform value missing.')

            # email changes for repeated accounts, so we start the loop here
            for _ in range(int(row['number_accs'])):
                if row['platform'] == 'android':
                    populate_google_account(row, cur)
                elif row['platform'] == 'ios':
                    populate_apple_account(row, cur)
                else:
                    raise ValueError(f"platform should be either ios or android, found '{row['platform']}'.")

                # create random password
                row['password'] = ''.join(random.choices(string.ascii_letters + string.digits, k=19))+'$'

                # obtain phonenumber
                row['phonenumber'] = find_phonenumber(bool(row['fresh_phonenumber']), cur, row['platform'])

                cur.execute("""INSERT INTO account
                (email, sur_name, first_name, password, birth, gender, phonenumber, street, city, postalcode, street_number, country, platform)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);""",
                (
                    row['email'], row['sur_name'], row['first_name'], row['password'], row['birth'], row['gender'], row['phonenumber'],
                    row['street'], row['city'], row['postalcode'], row['street_number'], row['country'], row['platform']
                ))
                conn.commit()

        conn.close()

if __name__ == '__main__':
    sys.exit(main())
