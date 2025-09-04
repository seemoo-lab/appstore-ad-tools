#!python3

"""HTTP REST API for easier access control to backend database and service to fetch app details from Google / Apple."""

from appstore_api import fetch_app_details_android, fetch_app_details_ios, look_up_app_id_android
from flask import Flask, Response, jsonify, request
from dotenv import load_dotenv
import os, psycopg, datetime
from multiprocessing import Queue, Process
import os
from time import sleep
import logging
from psycopg.types.json import Json
from psycopg.rows import dict_row
from functools import wraps

TIMEOUT = 2 # how long to wait between detail fetching iterations
app = Flask(__name__)

load_dotenv()
queue = Queue()

def get_db_connection():
    return psycopg.connect(host="localhost", dbname=os.environ["DB_NAME"],
                           user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"])

def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'Authorization' in request.headers:
            if request.headers['Authorization'] == os.environ['API_TOKEN']:
                return f(*args, **kwargs)

        return Response(status=401)

    return decorated_function


@app.post("/experiment")
@token_required
def experiment_new_post():
    content = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO experiment (platform, device_serial, comment, account_email, group_id, sub_group_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;',
                (content['platform'], content['device_serial'], content['comment'], content['account_email'], content['group_id'], content['sub_group_id']))
    new_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return jsonify(experiment_id=new_id)

@app.post("/ad_data")
@token_required
def data_post():
    content = request.json
    conn = get_db_connection()
    cur = conn.cursor()


    if "from_search_page" in content:
        from_search_page = content["from_search_page"]
    else:
        from_search_page = False


    cur.execute('INSERT INTO ad_data (id, experiment_id, time, label, sub_label, from_search_page, type) VALUES (%s, %s, %s, %s, %s, %s, %s);',
                (content['id'], content['experiment_id'], content['time'], content['label'], content['sub_label'], from_search_page, content["type"]))
    conn.commit()
    conn.close()

    # notify the "detail fetching" process that there is a new ad.
    queue.put((content['id'], content['experiment_id'], content['label']))
    return Response(status=200)

@app.post("/ad_data/refetch")
@token_required
def data_refetch_post():
    content = request.json
    conn = get_db_connection()
    conn.row_factory = dict_row
    cur = conn.cursor()

    # fetch all ad_data entries without a valid app_detail entry related to the experiment
    #cur.execute('SELECT ad_data.* FROM ad_data LEFT OUTER JOIN app_detail ON ad_data.app_id = app_detail.id WHERE experiment_id = %s AND data = \'null\'::jsonb;', (content['experiment_id'],))
    # fetch all ad_data entries without an app_id
    cur.execute('SELECT * FROM ad_data WHERE experiment_id = %s AND app_id is Null;', (content['experiment_id'],))
    result = cur.fetchall()

    # add entries to queue
    for ad in result:
        queue.put((ad['id'], ad['experiment_id'], ad['label']))

    return Response(status=200)

@app.get("/ad_data/new_id")
@token_required
def ad_data_new_id_get():
    exp_id = request.args.get("experiment_id")

    conn = get_db_connection()
    cur = conn.cursor()
    # test if experiment is valid
    cur.execute("SELECT count(*) FROM experiment WHERE id = %s", (exp_id,))

    exp_count = cur.fetchone()[0]

    if exp_count == 1:
        cur.execute("SELECT id from ad_data WHERE experiment_id = %s ORDER BY id DESC LIMIT 1;", (exp_id,))

        cur_id = cur.fetchone()
        if cur_id is None:
            new_id = 0
        else:
            new_id = cur_id[0] + 1
    else:
        conn.commit()
        conn.close()
        return Response(status=400)

    conn.commit()
    conn.close()

    return jsonify(id=new_id)

@app.get("/ad_data/count")
@token_required
def ad_data_number_of_ads_get():
    """Route to return the number of ads and suggestions that are linked to the given experiment_id.
    This is semantically different from /ad_data/new_id, which does not distinguish between ads and suggestions.
    In addition, id ranges might have holes."""

    exp_id = request.args.get("experiment_id")

    conn = get_db_connection()
    cur = conn.cursor()
    # test if experiment is valid
    cur.execute("SELECT count(*) FROM experiment WHERE id = %s", (exp_id,))
    exp_count = cur.fetchone()[0]

    result = {}
    if exp_count == 1:
        for t in ["suggestion", "ad"]:
            cur.execute("SELECT COUNT(*) from ad_data WHERE experiment_id = %s AND type = %s;", (exp_id, t))
            cur_id = cur.fetchone()[0]
            result[t + "s"] = cur_id if cur_id is not None else 0
        conn.commit()
        conn.close()
        return jsonify(result)

    else:
        conn.commit()
        conn.close()
        return Response(status=400)

@app.post("/account")
@token_required
def account_post():
    content = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('INSERT INTO account (email, sur_name, first_name, password, birth, gender, phonenumber, postalcode, city, street, street_number, country, persona_id) VALUES (%s,%s, %s, %s, %s, %s, %s,%s, %s, %s, %s, %s, %s);',
                (content["email"], content["sur_name"], content["first_name"], content["password"], content["birth"], content["gender"], content["phonenumber"], content["postalcode"], content["city"], content["street"], content["street_number"], content["country"], content["persona_id"]))

    conn.commit()
    conn.close()
    return Response(status=200)

@app.get("/account")
@token_required
def account_get():
    persona_email = request.args.get('email')

    conn = get_db_connection()
    conn.row_factory = dict_row
    cur = conn.cursor()

    cur.execute("SELECT * FROM account WHERE email = %s;", (persona_email,))

    account_data = cur.fetchone()
    conn.close()
    return jsonify(account_data)

@app.get("/sim")
@token_required
def sim_get():
    conn = get_db_connection()
    conn.row_factory = dict_row
    cur = conn.cursor()
    sql_query_select = ""
    sql_query_update = ""
    query_param = ""

    #can be accessed by phonenumber OR account email
    if 'phonenumber' in request.args:
        query_param = request.args.get('phonenumber')
        sql_query_select = "SELECT * FROM sim WHERE phonenumber = %s;"
        sql_query_update = "UPDATE sim SET locked = true WHERE phonenumber = %s;"

    elif 'email' in request.args:
        query_param = request.args.get('email')
        sql_query_select = "SELECT sim.* FROM sim, account WHERE account.email = %s AND account.phonenumber = sim.phonenumber;"
        sql_query_update = "UPDATE sim SET locked = true FROM account WHERE account.email = %s AND account.phonenumber = sim.phonenumber;"
    else:
        return Response(status=400)

    with conn.transaction():
        cur.execute(sql_query_select, (query_param,))
        sim_data = cur.fetchone()
        if sim_data["locked"] == False:
            cur.execute(sql_query_update, (query_param,))
        else:
            return jsonify(locked=True)

    conn.close()
    return jsonify(sim_data)

@app.post("/sim/log")
@token_required
def sim_log_post():
    content : dict = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    if 'phonenumber' in content.keys():
        phonenumber = content['phonenumber']
    elif 'email' in content.keys():
        sql_query_email = "SELECT account.phonenumber FROM account WHERE email = %s;"
        cur.execute(sql_query_email, (content['email'],))
        phonenumber = cur.fetchone()[0]
    else:
        return Response(status=400)
    
    sql_query_insert = "INSERT INTO sim_insertion_log (phonenumber, device_serial, time) VALUES (%s, %s, %s);"
    cur.execute(sql_query_insert, (phonenumber, content['device_serial'], content['time']))
    conn.commit()
    conn.close()
    return Response(status=200)


@app.get("/sim/release")
@token_required
def sim_release():
    conn = get_db_connection()
    cur = conn.cursor()
    sql_query_update = ""

    #can be accessed by phonenumber OR account email
    if 'phonenumber' in request.args:
        query_param = request.args.get('phonenumber')
        sql_query_update = "UPDATE sim SET locked = false WHERE phonenumber = %s;"

    elif 'email' in request.args:
        query_param = request.args.get('email')
        sql_query_update = "UPDATE sim SET locked = false FROM account WHERE account.email = %s AND account.phonenumber = sim.phonenumber;"
    else:
        return Response(status=400)

    cur.execute(sql_query_update, (query_param,))
    conn.commit()
    conn.close()
    return Response(status=200)

@app.post("/account/log")
@token_required
def account_log_post():
    content = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("INSERT INTO account_log (account_email, time, device_serial, action) VALUES (%s,%s,%s,%s);",
                (content["email"], content["time"], content["device_serial"], content["action"]))
    conn.commit()
    conn.close()
    return Response(status=200)

@app.post("/account/app")
@token_required
def account_app_post():
    content = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("INSERT INTO app_install_log (account_email, app_id, time) VALUES (%s, %s, %s);",
                (content["email"], content["app_id"], content["time"]))

    conn.commit()
    conn.close()
    return Response(status=200)


@app.post("/persona")
@token_required
def persona_post():
    content = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("INSERT INTO persona (comment) VALUES (%s) RETURNING id;",
                (content["comment"],))
    new_id = cur.fetchone()[0]

    conn.commit()
    conn.close()
    return jsonify(persona_id=new_id)

@app.get("/persona/apps")
@token_required
def persona_apps_get():
    persona_id = request.args.get('id')

    conn = get_db_connection()
    conn.row_factory = dict_row
    cur = conn.cursor()

    cur.execute("SELECT app.* FROM app, link_persona_app WHERE link_persona_app.persona_id = %s AND app.id = link_persona_app.app_id;", (persona_id,))

    data = cur.fetchall()
    conn.close()

    return jsonify(data)


@app.get('/alive')
@token_required
def alive():
    return Response(status=200)


def detail_fetcher_fn(queue):
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

    logger.info("Started process for fetching app details.")
    while True:
        # FIXME: We probably should think about catching some exceptions here to prevent this process from crashing?

        ad_id, experiment_id, app_name = queue.get()
        logger.info(f"Checking app details for {ad_id=}, {experiment_id=}, {app_name=}.")

        # get the platform of this experiment
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT platform FROM experiment WHERE id = %s;", (experiment_id,))
        if cur.rowcount > 0:
            platform = cur.fetchone()[0]

        # test if entry is already in database
        cur.execute("SELECT id from app_detail WHERE platform = %s AND label = %s;", (platform, app_name))
        if cur.rowcount > 0:
            app_detail_id = cur.fetchone()[0]
        else:
            # retrieve new app details
            match platform:
                case "android":
                    app_id = look_up_app_id_android(app_name, logger)
                    if app_id:
                        details = fetch_app_details_android(app_id, logger)
                    else:
                        logger.warning(f"Failed to look-up app_id for '{app_name}'.")
                        continue
                case "ios":
                    details = fetch_app_details_ios(app_name, logger)
                case _:
                    logger.error(f"Unknown platform value: `{platform}`.")
                    continue

            # handle empty details
            if details is not None:
                cur.execute("INSERT INTO app_detail (data, label, platform, updated_on) VALUES (%s, %s, %s, %s) RETURNING id;", (Json(details), app_name, platform, datetime.datetime.now().isoformat()))
                app_detail_id = cur.fetchone()[0]
            else:
                app_detail_id = 0

            sleep(TIMEOUT)

        cur.execute("UPDATE ad_data SET app_id = %s WHERE id = %s AND experiment_id = %s;",
                    (app_detail_id, ad_id, experiment_id))
        conn.commit()
        conn.close()

# Setup second process to handle the fetching of app details
if __name__ == "server":
    proc = Process(target=detail_fetcher_fn, args=(queue,))
    proc.start()
