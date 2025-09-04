#!python

from dotenv import load_dotenv
import psycopg
import os, sys

load_dotenv()

conn = psycopg.connect(
        dbname=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        host="localhost",
        password=os.environ.get("DB_PASSWORD"),
        port=os.environ.get("DB_PORT"),
    )
cur = conn.cursor()


cur.execute('SELECT (SELECT COUNT(*) = 4644875 FROM ad_data), (SELECT COUNT(*) =26 FROM persona), (SELECT COUNT(*) = 729 FROM experiment), (SELECT COUNT(*) = 4324 FROM app_detail);')
result = cur.fetchall()
for check in result[0]:
    if not check:
        print('Error...')
        sys.exit()

print("Everything is set up :)")