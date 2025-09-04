#!python3

import sys, subprocess, logging, argparse, os, time, datetime, atexit, csv, random
from threading import Barrier, Thread, Lock
from uuid import uuid4
from urllib3.util import Retry
from requests import Session
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

cfgutil_lock = Lock()
IOS_DEVICE_UDID_1 = "IOS_DEVICE_UDID_1"
IOS_DEVICE_UDID_2 = "IOS_DEVICE_UDID_2"
API_ENDPOINT = ""

# define the retry behaviour for HTTP requests
retries = Retry(
            total=100,
            backoff_factor=0.1,
            status_forcelist=[500, 501, 502, 503, 504],
            allowed_methods={'GET', 'POST'},
)

def run_queued_parallel_experiments_from_file(logger, file_path, api_token):
    # load csv file
    logger.info(f"Reading file at {file_path} ...")
    with open(file_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)

        # loop 
        for i, row in enumerate(reader):
            # select devices randomly
            udids = [IOS_DEVICE_UDID_1, IOS_DEVICE_UDID_2]
            random.shuffle(udids)

            logger.warning(f"Starting parallel experiment #{i+1} for accounts: {row['email0']} and {row['email1']}")
            
            # check experiment tasks
            do_signal = (row["signal"] == "y")
            do_extract = (row["extract"] == "y")
            do_repeat_unpersonalized = (row["repeat_unpersonalized"] == "y")

             # start parallel experiment
            run_parallel_experiment(logger, udids[0], udids[1], 
                                       row["email0"], row["email1"], 
                                       api_token, int(row["number_of_ads"]), 
                                       int(row["number_of_repetitions"]), 
                                       int(row["repeat_every_minutes"]), 
                                       row["group_id"], do_signal, do_extract, do_repeat_unpersonalized, row["comment"])
            
            # wait after only signal expriment
            if do_signal and not do_extract and i > 0:
                logger.info(f"Signal stage only. Sleep for 30 minutes...")
                time.sleep(60 * 30)
    
   

def run_parallel_experiment(logger, udid0, udid1, email0, email1,api_token, number_of_ads, number_of_repetitions, repeat_every_minutes, group_id, do_signal, do_extract, do_repeat_unpersonalized, comment = ""):
    # probe if account is still active
    login_probe0 = probe_account_login(logger, email0, udid0, api_token)
    logger.info("Sleeping for 5 minutes...")
    time.sleep(60 * 5)
    login_probe1 = probe_account_login(logger, email1, udid1, api_token)

    if not login_probe0 or  not login_probe1:
        logger.error(f"Abort parallel experiment with account {email0} and {email1} because of probe login failure: {login_probe0=}, {login_probe1=}")
        logger.info("Sleeping for 20 minutes...")
        time.sleep(60 * 20)
        return False
    
    app_install_barrier = Barrier(2)
    sub_group_id = str(uuid4())

    t0 = Thread(target=run_experiment, args=[logger, udid0, email0, api_token, number_of_ads, number_of_repetitions, repeat_every_minutes, app_install_barrier, group_id, sub_group_id, do_signal, do_extract, do_repeat_unpersonalized, f"{comment}_CONTROL"])
    t1 = Thread(target=run_experiment, args=[logger, udid1, email1, api_token, number_of_ads, number_of_repetitions, repeat_every_minutes, app_install_barrier, group_id, sub_group_id, do_signal, do_extract, do_repeat_unpersonalized, f"{comment}_TREATMENT"])
    
    t0.start()
    t1.start()

    t0.join()
    t1.join()
    return True

def run_experiment(logger, udid, email, api_token, number_of_ads, number_of_repetitions, repeat_every_minutes, barrier, group_id, sub_group_id, do_signal, do_extract, do_repeat_unpersonalized, comment = ""):
    logger.info(f"Starting Experiment with account {email} on device {udid}. ({number_of_ads=}, {number_of_repetitions=}, {repeat_every_minutes=}, {comment=}, {group_id=}, {sub_group_id=}, {do_extract=}, {do_signal=})")
    if not _run_experiment(logger, udid, email, api_token, number_of_ads, number_of_repetitions, repeat_every_minutes, barrier, group_id, sub_group_id, do_signal, do_extract, do_repeat_unpersonalized, comment):
        # graceful ending of experiment
        if is_logged_in(logger, udid, email, api_token):
            logout_account(logger, udid, email, api_token)
        if is_esim_present(logger, udid):
            remove_sim(logger, udid, email, api_token)
        logger.error(f"Aborted Experiment with account {email} on device {udid}. ({number_of_ads=}, {number_of_repetitions=}, {repeat_every_minutes=}, {comment=}, {group_id=}, {sub_group_id=}, {do_extract=}, {do_repeat_unpersonalized=}, {do_signal=})")
    else:
        logger.warning(f"Finished Experiment with account {email} on device {udid}. ({number_of_ads=}, {number_of_repetitions=}, {repeat_every_minutes=}, {comment=}, {group_id=}, {sub_group_id=}, {do_extract=}, {do_repeat_unpersonalized=}, {do_signal=})")


def _run_experiment(logger, udid, email, api_token, number_of_ads, number_of_repetitions, repeat_every_minutes, barrier, group_id, sub_group_id, do_signal, do_extract, do_repeat_unpersonalized, comment):    
    #reset device
    counter = 0
    while (setup_status := initial_setup(logger, udid)) == False:
        if not setup_status:
            counter += 1
            logger.warning(f"Device setup failed on device {udid}. Retrying attempt #{counter}...")
            time.sleep(20)
            if counter > 2:
                logger.error(f"Device setup failed on device {udid} after {counter} attempts. Aborting...")
                return False

        
    time.sleep(20)

    # set display to always on
    if not set_display_to_always_on(logger, udid, api_token, True):
        return False
    
    #insert sim
    if not insert_sim(logger, udid, email, api_token):
        return False

    #login
    counter = 0
    while (login_status := login_account(logger, udid, email, api_token)) == False:
        if not login_status:
            counter += 1
            logger.warning(f"Account login failed on device {udid} with account {email}. Retrying attempt #{counter}...")
            time.sleep(20)
            if counter > 10:
                logger.error(f"Account login failed on device {udid} after {counter} attempts. Aborting...")
                return False

    
    #set privacy settings
    if not set_privacy_settings_all_on(logger, udid, api_token):
        return False
    
    # activate personalized ads
    if not activate_personalized_ads(logger, udid, api_token):
        return False
    

    device_serial = get_serial(logger, udid)
    if do_signal:
        #inject persona
        app_install_status = False
        counter = 0
        while app_install_status == False:
            install_apps(logger, udid, email, api_token)
            time.sleep(30) #wait for last app to be installed...
            app_install_status = verify_app_installs(logger, udid, email, api_token)
            if app_install_status == False:
                counter += 1
                logger.warning(f"App install failed on device {udid} with account {email}. Retrying attempt #{counter}...")
                time.sleep(20)
            if counter > 2:
                logger.error(f"App install failed on device {udid} after {counter} attempts. Aborting...")
                return False
        post_account_log(email, device_serial, datetime.datetime.now().isoformat(), "signal", api_token)
        
    # set display to auto off    
    if not set_display_to_always_on(logger, udid, api_token, False):
        return False
    
    barrier.wait()

    if do_extract:
        #extraction
        if not run_ad_extraction_experiment(logger, udid, email, number_of_ads, f"{comment}", api_token, number_of_repetitions, repeat_every_minutes, group_id, sub_group_id):
            return False
        post_account_log(email, device_serial, datetime.datetime.now().isoformat(), "extract", api_token)
    
    if do_repeat_unpersonalized:
        # deactivate personalized ads
        if not deactivate_personalized_ads(logger, udid, api_token):
            return False
        
        # extract again
        if not run_ad_extraction_experiment(logger, udid, email, number_of_ads, f"{comment}_UNPERSONALIZED", api_token, number_of_repetitions, repeat_every_minutes, group_id, f"{sub_group_id}_UNPERSONALIZED"):
            return False
        post_account_log(email, device_serial, datetime.datetime.now().isoformat(), "extract_unpersonalized", api_token)
        
    #logout
    if not logout_account(logger, udid, email, api_token):
        return False
    
    #eject sim
    if not remove_sim(logger, udid, email, api_token):
        return False

    return True

def extract_ads(logger, udid, email, minimum_amount_of_ads, api_token, experiment_id, new_ad_data_id, run_id = 0):
    #set test parameters
    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token
    subprocess_env["TEST_RUNNER_ACCOUNT_EMAIL"] = email
    subprocess_env["TEST_RUNNER_DEVICE_SERIAL"] = get_serial(logger, udid)
    subprocess_env["TEST_RUNNER_MINIMUM_AMOUNT_OF_ADS"] = str(minimum_amount_of_ads)
    subprocess_env["TEST_RUNNER_EXPERIMENT_ID"] = str(experiment_id)
    subprocess_env["TEST_RUNNER_AD_DATA_ID"] = str(new_ad_data_id)

    logger.info("Start ad extraction ... ")
    #run test
    return execute_ui_test(logger, "test_extract_ads", udid, subprocess_env) == 0

def run_ad_extraction_experiment(logger, udid, email, minimum_amount_of_ads, comment, api_token, number_of_repetitions, repeat_every_minutes, group_id, sub_group_id):
    logger.info("Start new repeated experiment...")
    exp_id = retrieve_new_experiment_id(logger, udid, comment, email, api_token, group_id, sub_group_id)
    counter = 0
    while counter < number_of_repetitions:
        logger.info(f"Start extraction #{counter} of experiment #{exp_id}.")
        next_exp = datetime.datetime.now() + datetime.timedelta(minutes=repeat_every_minutes)

        start_ad_id = get_new_ad_data_id(logger, exp_id, api_token)
        extracted_ads = 0
        success = False
        #run ad extraction (repeat until everything is extracted...)
        while (not success) or (extracted_ads < minimum_amount_of_ads):
            success = extract_ads(logger, udid, email, minimum_amount_of_ads - extracted_ads, api_token, exp_id, get_new_ad_data_id(logger, exp_id, api_token), counter)
            extracted_ads = get_new_ad_data_id(logger, exp_id, api_token) - start_ad_id


        counter += 1
        if repeat_every_minutes > 0 and counter < number_of_repetitions:
            sleep_until(logger, next_exp)       

        
    return True


def retrieve_new_experiment_id(logger, udid, comment, email, api_token, group_id, sub_group_id):
    logger.info("Retrieving new experiment id...")
    serial = get_serial(logger, udid)

    headers = {"Authorization" : api_token}
    payload = {"platform" : "ios",
               "device_serial" : serial,
               "comment" : comment,
               "account_email" : email,
               "group_id" : group_id,
               "sub_group_id" : sub_group_id}
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        res = s.post(f"{API_ENDPOINT}/experiment", headers=headers, json=payload)
        new_id = res.json()["experiment_id"]
        logger.info(f"Retrieved new experiment id: {new_id}")

    return new_id

def get_new_ad_data_id(logger, experiment_id, api_token):
    logger.info(f"Retrieving new ad_data id for experiment #{experiment_id}.")
    headers = {"Authorization" : api_token}
    payload = {"experiment_id" : experiment_id}
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        res = s.get(f"{API_ENDPOINT}/ad_data/new_id", headers=headers, params=payload)
        if res.status_code == 400:
            logger.error(f"Experiment #{experiment_id} is not in the database.")
            return None
        new_id = res.json()["id"]
    logger.info(f"New ad_data id is {new_id}")
    return new_id

def install_apps(logger, udid, email, api_token):
    #set test parameters
    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token
    subprocess_env["TEST_RUNNER_ACCOUNT_EMAIL"] = email

    logger.info("Start installing Apps...")
    #run test
    execute_ui_test(logger, "test_install_apps", udid, subprocess_env)
    logger.info("Finished installing apps...")
    

def get_account_json(logger, email, api_token):
    headers = {"Authorization" : api_token}
    payload = {"email" : email}
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        res = s.get(f"{API_ENDPOINT}/account", headers=headers, params=payload)
    return res.json()

def get_sim_json(logger, email, api_token):
    headers = {"Authorization" : api_token}
    payload = {"email" : email}
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        res = s.get(f"{API_ENDPOINT}/sim", headers=headers, params=payload)
    return res.json()

def get_release_sim(logger, email, api_token):
    headers = {"Authorization" : api_token}
    payload = {"email" : email}
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        res = s.get(f"{API_ENDPOINT}/sim/release", headers=headers, params=payload)
    return res.status_code

def post_sim_log(email, device_serial, time, api_token):
    headers = {"Authorization" : api_token}
    payload = {"email" : email,
               "device_serial" : device_serial,
               "time": time}
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        res = s.post(f"{API_ENDPOINT}/sim/log", headers=headers, json=payload)
    return res.status_code

def post_account_log(email, device_serial, time, action, api_token):
    headers = {"Authorization" : api_token}
    payload = {"email" : email,
               "device_serial" : device_serial,
               "time": time,
               "action" : action}
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        res = s.post(f"{API_ENDPOINT}/account/log", headers=headers, json=payload)
    return res.status_code


def verify_app_installs(logger, udid, email, api_token):
    logger.info("Verify App installs...")
    headers = {"Authorization" : api_token}
    payload = {"email" : email}
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        res = s.get(f"{API_ENDPOINT}/account", headers=headers, params=payload)
        persona_id = res.json()["persona_id"]

        payload = {"id" : persona_id}

        res = s.get(f"{API_ENDPOINT}/persona/apps", headers=headers, params=payload)
        apps = res.json()

    device_apps = get_app_list_from_device(logger, udid)

    all_installed = True

    for app in apps:
        if any(app["apple_id"] in x for x in device_apps.splitlines()):
            logger.info(f"App {app['name']} with bundle id {app['apple_id']} is installed.")
        else:
            logger.info(f"App {app['name']} with bundle id {app['apple_id']} not installed!")
            all_installed = False
    
    if all_installed:
        logger.info("All Apps are installed.")
    else:
        logger.warning("Not all Apps are installed.")
    return all_installed
            

def get_app_list_from_device(logger, udid):
    logger.info(f"Fetching app list from device {udid}")
    process_info = subprocess.run(["ideviceinstaller", "-l", "-u", udid], capture_output=True, text=True)
    if process_info.returncode != 0:
        logger.error(process_info.stdout.strip())
        return None
    
    return process_info.stdout.strip()

def get_serial(logger, udid):
    logger.info("Start reading Serial from device...")
    process_info = subprocess.run(["ideviceinfo", "-k", "SerialNumber", "-u", udid], capture_output=True, text=True)
    serial = process_info.stdout.strip()

    if process_info.returncode != 0:
        logger.error(serial)
        return None
    logger.info(f"Connected to device with Serial: {serial}")

    return serial

def is_esim_present(logger, udid):
    logger.info(f"Start probing for eSIM on device {udid}...")
    process_info = subprocess.run(["ideviceinfo", "-k", "IntegratedCircuitCardIdentity", "-u", udid], capture_output=True, text=True)
    value= process_info.stdout.strip()

    if value == "":
        logger.info(f"eSIM not found on device with udid: {udid}")
        return False
    
    logger.info(f"eSIM is present on device with udid {udid}. Probe return value: {value}.")
    return True

def has_active_icloud_account(logger, udid):
    logger.info(f"Start probing for active iCloud account on device {udid}...")
    process_info = subprocess.run(["ideviceinfo", "-k", "NonVolatileRAM", "-u", udid], capture_output=True, text=True)
    if "fm-account-masked: \n" not in process_info.stdout.strip():
        logger.info(f"Active iCloud account on device with udid: {udid}")
        return True
    
    logger.info(f"No active iCloud account on device with udid: {udid}")
    return False

def is_logged_in(logger, udid, email, api_token):
    logger.info(f"Start probing for account {email} on device {udid}...")
    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token
    subprocess_env["TEST_RUNNER_ACCOUNT_EMAIL"] = email

    #run test
    ret = execute_ui_test(logger, "test_is_logged_in", udid, subprocess_env, skip_error=True)
    if ret == 0:
        logger.info(f"Account {email} is logged in on device {udid}.")
        return True
    else:
        logger.info(f"Account {email} is not logged in on device {udid}.")
        return False

def get_ecid(logger, udid):
    logger.info("Start reading ecid from device...")
    process_info = subprocess.run(["ideviceinfo", "-k", "UniqueChipID", "-u", udid], capture_output=True, text=True)
    ecid = process_info.stdout.strip()

    if process_info.returncode != 0:
        logger.error(ecid)
        return None
    logger.info(f"Connected to device with ecid / Unique Chip ID: {ecid}")

    return ecid

def initial_setup(logger, udid):
    logger.info(f"Start initial setup for device {udid}...")
    if is_esim_present(logger, udid):
        logger.error(f"eSIM is still present on device {udid}...")
        return False

    if has_active_icloud_account(logger, udid):
        logger.error(f"Account is still active on device {udid}...")
        return False
    #retrieve ecid
    ecid = get_ecid(logger, udid)
    
    #erase device
    with cfgutil_lock:
        logger.info("Erasing device...")
        cfgutil_process = subprocess.run(["cfgutil", "-e" ,ecid, "erase"], text=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        logger.info(f"CFGUTIL - {cfgutil_process.stdout}")
        logger.info("Waiting until device is rebooted...")
    time.sleep(180)

    #todo wait until rest is finished...
    wait_for_device(logger, udid)

    #install profile
    with cfgutil_lock:
        logger.info("Install profile on device...")
        cfgutil_process = subprocess.run(["cfgutil", "-e", ecid, "install-profile","test_device.mobileconfig"], text=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        logger.info(f"CFGUTIL - {cfgutil_process.stdout}")
    time.sleep(20)
    
    #prepare device
    with cfgutil_lock:
        logger.info("Prepare device...")
        cfgutil_process = subprocess.run(["cfgutil/bin/cfgutil_PATCHED", "-e", ecid, "prepare", "--skip-all", "--skip-tos"], text=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        logger.info(f"CFGUTIL_PATCHED - {cfgutil_process.stdout}")
    time.sleep(40)

    #activate dev mode
    logger.info("Activate developer mode on device...")
    devmode_process = subprocess.run(["devmodectl", "single", udid], text=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    logger.info(f"DEVMODECTL - returncode: {devmode_process.returncode}")
    logger.info(f"DEVMODECTL - {devmode_process.stdout}")
    

    if devmode_process.returncode != 0:
        logger.warning(f"devmode returncode is {devmode_process.returncode} -> Device setup failed.")
        return False
    time.sleep(5)
    #check for success TODO is this check valid?
    process_info = subprocess.run(["ideviceinfo", "-k", "UntrustedHostBUID", "-u", udid], capture_output=True, text=True)
    if process_info.stdout.strip() != "":
        logger.warning("Device setup failed.")
        return False
    else:
        logger.info("Device setup successful.")
        return True




def is_device_available(logger, udid):
    process_info = subprocess.run(["ideviceinfo", "-u", udid], capture_output=True)
    if process_info.returncode == 0:
        logger.info(f"Device {udid} is available")
        return True
    else:
        logger.warning(f"Device {udid} is unavailable")
        return False

def wait_for_device(logger, udid):
    logger.info(f"Waiting for device {udid}...")
    while True:
        if is_device_available(logger, udid):
            return True
        else:
           time.sleep(10)

def sleep_until(logger, until_time):
    now = datetime.datetime.now()
    if until_time < now:
        logger.warning("Sleeping time is negative. Skip sleeping...")
        return

    seconds_until_time = (until_time - now).total_seconds()
    logger.info(f"Sleeping until {until_time} for a total of {seconds_until_time} seconds...")
    time.sleep(seconds_until_time)
    logger.info(f"Ended napping...")

def login_account(logger, udid, email, api_token):
    logger.info(f"Start login process for account {email} on device {udid}...")
    # retrieve account data
    account_data = get_account_json(logger, email, api_token)

    #set test parameters
    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token
    subprocess_env["TEST_RUNNER_ACCOUNT_EMAIL"] = account_data["email"]
    subprocess_env["TEST_RUNNER_ACCOUNT_PASSWORD"] = account_data["password"]

    #run test
    execute_ui_test(logger, "test_app_store_login", udid, subprocess_env)
    #probe if account is active
    is_active = is_logged_in(logger, udid, email, api_token)
    if is_active:
        logger.info(f"Login process successful for account {email} on device {udid}.")
        post_account_log(email, get_serial(logger, udid), datetime.datetime.now().isoformat(), "login", api_token)
    else:
        logger.error(f"Login process failed for account {email} on device {udid}.")
    # returns true if login was successful
    return is_active

def logout_account(logger, udid, email, api_token):
    logger.info(f"Start logout process on device {udid}...")
    # retrieve account data
    account_data = get_account_json(logger, email, api_token)

    #set test parameters
    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token
    subprocess_env["TEST_RUNNER_ACCOUNT_PASSWORD"] = account_data["password"]


    #run test
    execute_ui_test(logger, "test_app_store_logout", udid, subprocess_env)

    #probe if account is removed
    is_active = is_logged_in(logger, udid, email, api_token)
    if is_active:
        logger.error(f"Logout process failed on device {udid}.")
        return False
    else:
        post_account_log(email, get_serial(logger, udid), datetime.datetime.now().isoformat(), "logout", api_token)
        logger.info(f"Logout process successful on device {udid}.")
        return True
    # returns true is logout was successful


def insert_sim(logger, udid, email, api_token):
    logger.info(f"Start inserting sim for account {email} on device {udid}...")
    #probe for eSIM
    is_present = is_esim_present(logger, udid)
    if is_present:
        logger.error(f"eSIM is already present on device {udid}. eSIM insertion aborted...")
        return False
    # retrieve info
    sim_info = get_sim_json(logger, email, api_token)

    # check if sim is currently in use
    if sim_info["locked"] == True:
        logger.warning(f"eSIM is currently locked. eSIM insertion aborted...")
        return False

    #set test parameters
    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token
    subprocess_env["TEST_RUNNER_ADDRESS"] = sim_info["address"]
    subprocess_env["TEST_RUNNER_ACTIVATION_CODE"] = sim_info["activation_code"]
    subprocess_env["TEST_RUNNER_CONFIRMATION_CODE"] = sim_info["confirmation_code"]
    subprocess_env["TEST_RUNNER_SKIP_CELLULAR_WARNING"] = "1"

    #run test
    execute_ui_test(logger, "test_install_sim", udid, subprocess_env)

    #probe for eSIM
    is_present = is_esim_present(logger, udid)
    if is_present:
        device_serial = get_serial(logger, udid)
        post_sim_log(email, device_serial, datetime.datetime.now().isoformat(), api_token)
        logger.info(f"eSIM insertion successful for account {email} on device {udid}.")
    else:
        logger.error(f"eSIM insertion failed for account {email} on device {udid}.")
        get_release_sim(logger, email, api_token)
    #return true if eSIM is present
    return is_present

def execute_ui_test(logger, testcase, udid, subprocess_env, skip_error = False):
    logger.info("Running XCUITest...")
    subprocess_env["TEST_RUNNER_API_ENDPOINT"] = API_ENDPOINT

    logFileName = f"{datetime.datetime.now()}"
    process_info = subprocess.run(["xcodebuild", "test-without-building", "-project", "app_store_ad_extraction.xcodeproj", "-scheme", "app_store_ad_extraction", "-destination" ,"platform=iOS,id="+udid, f"-only-testing:app_store_ad_extractionUITests/ui_testUITests/{testcase}", "-resultBundlePath", f"logs/resultBundles/{logFileName}"], capture_output=True, text=True, env=subprocess_env)
    logger.info(f"XCUITest finished. Exit Code: {process_info.returncode}")
    logger.info(f"XCUITest - {process_info.stdout}")
    if process_info.returncode != 0:
        if skip_error:
            logger.info(f"XCUITest - {process_info.stderr}")
        else:
            logger.error(f"XCUITest - {process_info.stderr}")
        
        #analyze error
        graph_process = subprocess.run(["xcrun", "xcresulttool", "graph", "--path", f"logs/resultBundles/{logFileName}"], capture_output=True, text=True)
        for i, line in enumerate(graph_process.stdout.splitlines()):
            if "Session-app_store_ad_extractionUITests" in line:
                log_id = graph_process.stdout.splitlines()[i+3].split("Id: ")[1]
                subprocess.run(["xcrun", "xcresulttool", "export", "--path", f"logs/resultBundles/{logFileName}", "--type", "file", "--output-path", ".log_tmp", "--id", log_id])
                with open('.log_tmp') as log:
                    log_content = log.read()
                    if "SEEMOO_connection_cellular" in log_content:
                        logger.error(f"Cellular data is active on device {udid} ! Detailed information: logs/resultBundles/{logFileName}")
                    if "SEEMOO_connection_bad" in log_content:
                        logger.error(f"Device {udid} has no internet connection! Detailed information: logs/resultBundles/{logFileName}")   
                
                if os.path.exists(".log_tmp"):
                    os.remove(".log_tmp")

    else:
        logger.info(f"XCUITest - {process_info.stderr}")

    logger.info("XCUITest finished.")
    
    return process_info.returncode

    
def remove_sim(logger, udid, email, api_token):
    logger.info(f"Start ejecting eSIM on device {udid}...")
    #probe for eSIM
    is_present = is_esim_present(logger, udid)
    if not is_present:
        logger.error(f"There is no eSIM on device {udid}. eSIM extraction aborted...")
        return False
    
    # run test
    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token

    execute_ui_test(logger, "test_remove_current_sim", udid, subprocess_env)

    #probe for eSIM
    is_present = is_esim_present(logger, udid)
    if is_present:
        logger.error(f"eSIM ejection on device {udid} failed.")
        return False
    else:
        logger.info(f"eSIM ejection on device {udid} successful")
        get_release_sim(logger, email, api_token)
        return True
    #return true if eSIM is not present

def set_privacy_settings_all_on(logger, udid, api_token):
    logger.info(f"Start setting privacy settings to all on on device {udid}...")

    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token

    ret = execute_ui_test(logger, "test_privacy_settings_all_on", udid, subprocess_env)
    if ret == 0:
        logger.info(f"Privacy settings are all set to on.")
        return True
    else:
        logger.error(f"Error setting privacy settings on device {udid}.")
        return False

def set_display_to_always_on(logger, udid, api_token, always_on):
    logger.info(f"Start setting always-on-status of device {udid} to {always_on}...")

    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token
    if always_on:
        ret = execute_ui_test(logger, "test_display_always_on", udid, subprocess_env)
    else:
        ret = execute_ui_test(logger, "test_display_auto_off", udid, subprocess_env)

    if ret == 0:
        logger.info(f"Always-on-status of device {udid} is set to {always_on}.")
        return True
    else:
        logger.error(f"Error setting always-on-status of device {udid}.")
        return False

def deactivate_personalized_ads(logger, udid, api_token):
    logger.info(f"Start deactivating personalized ads of device {udid}...")

    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token

    ret = execute_ui_test(logger, "test_deactivate_personalized_ads", udid, subprocess_env)

    if ret == 0:
        logger.info(f"Deactivating personalized ads of device {udid} succesful.")
        return True
    else:
        logger.error(f"Error deactivating personalized ads of device {udid}.")
        return False
    
def activate_personalized_ads(logger, udid, api_token):
    logger.info(f"Start activating personalized ads of device {udid}...")

    subprocess_env = os.environ.copy()
    subprocess_env["TEST_RUNNER_API_TOKEN"] = api_token

    ret = execute_ui_test(logger, "test_activate_personalized_ads", udid, subprocess_env)

    if ret == 0:
        logger.info(f"Activating personalized ads of device {udid} succesful.")
        return True
    else:
        logger.error(f"Error activating personalized ads of device {udid}.")
        return False

def test_login_apple_account_browser(logger, email, api_token):
    account_data = get_account_json(logger, email, api_token)

    options = webdriver.FirefoxOptions()
    options.add_argument("--headless")
    driver = webdriver.Firefox(options=options)
    driver.get("https://account.apple.com/sign-in")

    time.sleep(10)

    driver.switch_to.active_element.send_keys(account_data['email'])
    time.sleep(2)
    driver.switch_to.active_element.send_keys(Keys.RETURN)
    time.sleep(5)
    driver.switch_to.active_element.send_keys(account_data['password'])
    time.sleep(2)
    driver.switch_to.active_element.send_keys(Keys.RETURN)   
    time.sleep(5)

    iframe = driver.find_element(By.ID, "aid-auth-widget-iFrame")

    # switch to selected iframe
    driver.switch_to.frame(iframe)
    try:
        success = driver.find_element(By.ID, "cannot-use-number").is_displayed()
    except:
        success = False
    
    driver.close()
    return success

def probe_account_login(logger, email, udid, api_token):
    logger.info(f"Starting probe login for account {email}...")
    if test_login_apple_account_browser(logger, email, api_token):
        post_account_log(email, get_serial(logger, udid), datetime.datetime.now().isoformat(), "probe_login_success", api_token )
        logger.info(f"Probe login for account {email} successful.")
        return True
    else:
        post_account_log(email, get_serial(logger, udid), datetime.datetime.now().isoformat(), "probe_login_error", api_token )
        post_account_log(email, get_serial(logger, udid), datetime.datetime.now().isoformat(), "inactive", api_token )
        logger.error(f"Probe login for account {email} failed.")
        return False

def main():
    logger = logging.getLogger(__name__)

    atexit.register(handle_exit, logger)

    logger.setLevel(logging.DEBUG)
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter('iOS - %(asctime)s %(module)s %(levelname)s - %(message)s')
    # add formatter to ch
    ch.setFormatter(formatter)
    # add ch to logger
    logger.addHandler(ch)

    # add filehandler
    fh = logging.FileHandler(f"logs/ios_{datetime.datetime.now()}.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)


    #Set up argument parsing
    parser = argparse.ArgumentParser(description="todo")
    parser.add_argument("--email0")
    parser.add_argument("--udid0")
    parser.add_argument("--email1", default="")
    parser.add_argument("--udid1", default="")
    parser.add_argument("--number_of_ads", type=int)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--repeat_minutes", type=int)
    parser.add_argument("--group_id", default=str(uuid4()))
    parser.add_argument("--install", action='store_true')
    parser.add_argument("--setup", action='store_true')
    parser.add_argument("--insert_sim", action='store_true')
    parser.add_argument("--remove_sim", action='store_true')
    parser.add_argument("--login", action='store_true')
    parser.add_argument("--logout", action='store_true')
    parser.add_argument("--extract", action='store_true')
    parser.add_argument("--comment", default="")
    parser.add_argument("--repeat", action='store_true')
    parser.add_argument("--privacy", action='store_true')
    parser.add_argument("--test", action='store_true')
    parser.add_argument("--from_file", type=str)

    args=parser.parse_args()

    load_dotenv()
    API_ENDPOINT = os.environ["API_ENDPOINT"]
    if args.setup:
        initial_setup(logger, args.udid0)
    elif args.email1 != "" and args.udid1 != "":
        run_parallel_experiment(logger, args.udid0, args.udid1, args.email0, args.email1, os.environ["API_TOKEN"], args.number_of_ads, args.repetitions, args.repeat_minutes, args.group_id, args.comment)
    elif args.insert_sim:
        insert_sim(logger, args.udid0, args.email0, os.environ["API_TOKEN"])
    elif args.remove_sim:
        remove_sim(logger, args.udid0, args.email0, os.environ["API_TOKEN"])
    elif args.login:
        login_account(logger, args.udid0, args.email0, os.environ["API_TOKEN"])
    elif args.privacy:
        set_privacy_settings_all_on(logger, args.udid0, os.environ["API_TOKEN"])
    elif args.logout:
        logout_account(logger, args.udid0, args.email0, os.environ["API_TOKEN"])
    elif args.install:
        install_apps(logger, args.udid0, args.email0, os.environ["API_TOKEN"])
        verify_app_installs(logger, args.udid0, args.email0, os.environ["API_TOKEN"])
    elif args.extract:
        run_ad_extraction_experiment(logger, args.udid0, args.email0, args.number_of_ads, args.comment, os.environ["API_TOKEN"], args.repetitions, args.repeat_minutes, "TEST123", "TESTSUB123")
    elif args.from_file != "":
        run_queued_parallel_experiments_from_file(logger, args.from_file, os.environ["API_TOKEN"])
    
    else:
        logger.warning("Please provide a valid argument!")
    
    handle_exit(logger)
    
def handle_exit(logger):
    # unregister logging handlers
    for handler in logger.handlers:
        logger.removeHandler(handler)
        handler.close()

if __name__ == '__main__':
    sys.exit(main())