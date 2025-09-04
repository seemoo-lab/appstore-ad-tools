#!/usr/bin/python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "requests==2.32.5",
# ]
# ///

"""
Glue code to perform experiments.
It combines the Kotlin-based UIAutomation and the C-based hid-setup.
"""

import argparse
import csv
import logging
import os
import subprocess as s
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from sys import exit
from threading import Barrier, Thread
from time import sleep
import traceback

from auth_secret import auth_token
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('ANDROID - %(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# add filehandler
fh = logging.FileHandler(f"logs/android_{datetime.now()}.log")
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)

# device_serial to type mapping (TODO: handle this more elegantly)
device_type = {"ANDROID_DEVICE_ID_5": "pixel_8",
               "ANDROID_DEVICE_ID_1": "g23", # treat this as g23, even though it's a g22+ (sufficiently similar)
               "ANDROID_DEVICE_ID_3": "g23", # treat this as g23, even though it's a g22 ultra (sufficiently similar)
               "ANDROID_DEVICE_ID_2": "g23",
               "ANDROID_DEVICE_ID_4": "g23",
               "ANDROID_DEVICE_ID_6": "g23"}

# define the retry behaviour for HTTP requests
retries = Retry(
            total=100,
            backoff_factor=0.1,
            status_forcelist=[500, 501, 502, 503, 504],
            allowed_methods={'GET', 'POST'},
)

FAILED_MEASUREMENT_THRESHOLD = 50
resume_targets = ["esim", "login", "signalling", "measurement", "post_personalization_measurement"]
NO_PERS_INDICATOR = "ACCOUNT_DOES_NOT_HAVE_PERSONALIZATION"

######################
## Helper functions ##
######################
def create_experiment(email, comment, device_serial, group_id, sub_group_id):
    # Create a new experiment
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))

        exp = s.post(f"https://harvester.seemoo.tu-darmstadt.de/experiment",
                      json={"platform": "android",
                            "device_serial": device_serial,
                            "group_id": group_id,
                            "sub_group_id": sub_group_id,
                            "comment": comment,
                            "account_email": email},
                      headers={"Authorization": auth_token}).json()
        experiment_id = exp["experiment_id"]
        logger.info(f"Created experiment with ID={experiment_id}.")
        return experiment_id

def get_account_details(email):
    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        account = s.get("https://harvester.seemoo.tu-darmstadt.de/account",
                        params={"email": email},
                        headers={"Authorization": auth_token})
        return account.json()

def release_sim(phonenumber):
    logger.info(f"Releasing SIM {phonenumber}.")

    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        s.get("https://harvester.seemoo.tu-darmstadt.de/sim/release",
              params={"phonenumber": phonenumber},
              headers={"Authorization": auth_token})

def log_esim_installation(phonenumber, serial):
    logger.info(f"Logging eSIM installation: {phonenumber=}, {serial=}.")

    with Session() as s:
        s.mount('https://', HTTPAdapter(max_retries=retries))
        s.get("https://harvester.seemoo.tu-darmstadt.de/sim/log",
              json={"phonenumber": phonenumber,
                    "serial": serial,
                    "time": datetime.now().isoformat()},
              headers={"Authorization": auth_token})

def install_instrumentation(serial: str):
    """Installs the instrumentation APKs to the given target device."""

    apk_paths = [
        "app/build/outputs/apk/debug/app-debug.apk",
        "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
    ]

    for i in range(10):
        try:
            logger.info(f"Installing instrumentation APKs on device={serial} in iteration {i}.")
            for apk_path in apk_paths:
                # ensure that the required files have been compiled
                if not Path(apk_path).is_file():
                    raise RuntimeError(f"Could not find {apk_path} from the current directory.\nHave you invoked both gradle tasks, i.e., `assembleDebug` and `assembleDebugAndroidTest`?\nAre you in the root directory of this repository?")

                s.check_output(["adb", "install", apk_path],
                               stderr=s.STDOUT,
                               env={"ANDROID_SERIAL": serial})
            # if both apps are installed successfully, we are done here.
            return
        except s.CalledProcessError as e:
            if f"adb: device '{serial}' not found".encode() in e.output:
                logger.warning(f"Installation of the instrumentation APK failed with '{e}', output: {e.output}, serial={serial}, iteration {i}. Trying hid-based reset.")
                sleep(15)
                try:
                    factory_reset_hid_based(serial)
                    initial_device_setup(serial)
                    continue
                except RuntimeError:
                    logger.warning(f"{serial}: Got RuntimeError During hid based factory reset / initial device setup. Continue with next iteration.")
                    continue
            else:
                raise RuntimeError(f"Installation of the instrumentation APK failed with unexpected exception: '{e}', output: {e.output}.")
    else:
        raise RuntimeError(f"Exceeded 10 iterations trying to install the instrumentation APKs on device {serial}.")

def run_instrumentation(task: str, serial: str, args: dict, restartable=False):
    """Helper function to run the given task by invoking the instrumentation directly using `am`.
    Also handles errors."""

    arguments = sum([['-e', k, v] for k,v in args.items()], [])
    cmd = (["adb", "shell", "am", "instrument"] +
           arguments +
           ["-e", "task", task,
            "-e", "deviceType", device_type[serial],
            "-w", "com.example.adextractauto.test/androidx.test.runner.AndroidJUnitRunner"])

    # we perform up to then retries
    failed_measurement_counter = 0
    for i in range(10):
        try:
            # for installESIM, we want to unlock the eSIM before retrying an attempt to install it. Else, it might be in a locked state from before.
            if task == 'installESIM' and i > 0:
                release_sim(args["phonenumber"])

            # run the instrumentation
            logger.debug("Running instrumentation task on device %s (attempt %d): %s", serial, i, cmd)
            output = s.check_output(cmd,
                                    stderr=s.STDOUT,
                                    env={"ANDROID_SERIAL": serial})
            # am instrument does not return non-zero on failure, so we have to check that ourselves.
            if "FAILURES!!!" in output.decode():
                raise s.CalledProcessError(-1, cmd, output)

            # reset counter after successful measurement
            if task == 'measurement':
                failed_measurement_counter = 0

            # prevent retries if successful
            return

        # error handling code below
        except s.CalledProcessError as e:
            error_msg = e.output.decode()

            # if we encountered a captcha, we need manual intervention to solve that.
            if "CAPTCHA" in error_msg:
                logger.error(f"Found Captcha, please intervene manually on device {serial}.")
                input("Please hit enter after finishing the task.")
                logger.info("Supervisor hit enter, starting guided captcha task.")

                # call semi-automatic captcha task
                login_account(args["accountEmail"], serial, True)

                # continue with the next task
                logger.info("Finished guided captcha task successfully.")
                return

            # handle accounts that do not get personalization by logging these events.
            if (task == 'enablePersonalization' or task == 'disablePersonalization') and "ACCOUNT_DOES_NOT_HAVE_PERSONALIZATION" in error_msg:
                logger.error(f"Account {args['accountEmail']} does not get personalized ads. Related measurements will be invalid.")
                return NO_PERS_INDICATOR


            # if measuring ads, we can just ignore the crash and continue. The logic in `extract_ads` calls the corresponding task until enough ads have been extracted.
            if task == 'measurement':
                if failed_measurement_counter > FAILED_MEASUREMENT_THRESHOLD:
                    logger.error(f"Measurement task crashed on device {serial} for {FAILED_MEASUREMENT_THRESHOLD} times in a row, aborting the experiment.")
                    raise RuntimeError(f"Measurement task crashed on device {serial} for {FAILED_MEASUREMENT_THRESHOLD} times in a row, aborting the experiment.")

                logger.warning(f"Measurement task crashed on device {serial}, continuing with next run in this iteration.")
                failed_measurement_counter += 1
                return

            # reset might just fail after it succeeded because the device goes down.
            if task == 'factoryReset':
                if f"adb: device '{serial}' not found" in error_msg or "com.example.adextractauto.AutomationTest:" == error_msg.strip():
                    logger.info(f"Ignoring factoryReset error: '{error_msg}'.")
                    return

            # One of our devices has a quirk where it loses connection during eSIM install/removal, ignore that.
            if (task == 'installESIM' or task == 'removeESIM') and serial in ["ANDROID_DEVICE_ID_2"]:
                if f"adb: device '{serial}' not found" in error_msg or "com.example.adextractauto.AutomationTest:" == error_msg.strip():
                    logger.info(f"Ignoring device {serial} gone missing after esimInstall.")

                    if task == 'installESIM':
                        log_esim_installation(args["phonenumber"], serial)

                    # wait a short amount of time for it to be back up to prevent subsequent failures
                    sleep(10)
                    return

            # since the last update, the initial setup sometimes fails to set the correct language
            # this means that the subsequent sound setup fails
            # try to fix this by performing another reset.
            if task == 'disableSound' and i > 7:
                logger.warning(f"{serial} - Failed to disableSound multiple times, trying to reset and perform the initial setup again.")

                # Step 1.) Reset the device
                factory_reset_device(serial)
                # Step 1.a) Initial Device Setup
                initial_device_setup(serial)
                # Step 1.b) install instrumentation APK
                install_instrumentation(serial)

            if restartable:
                # prevent logging spam on warning level
                if i > 5:
                    logger.warning(f"Restarting task {task} on {serial} in iteration {i} due to restartable=true.")
                else:
                    logger.info(f"Restarting task {task} on {serial} in iteration {i} due to restartable=true.")
                logger.info(f"Instrumentation error was: {error_msg}")
                # wait a few seconds to avoid spam and handle devices going down for a short time
                sleep(10)
                continue

            logger.error("Caught error in instrumentation task: %s", error_msg)

            # enable a experiment supervisor to fix the state manually and continue the experiment.
            option = input(f"Task {task} failed on device {serial}. Enter 'c' to continue with next task, 'r' to retry, anything else to abort: ").lower()
            if option == 'c':
                return
            elif option == 'r':
                continue
            else:
                raise RuntimeError("Instrumentation Task failed due to supervisor input.")

    # after leaving for loop
    raise RuntimeError("Instrumentation task failed after reaching the maximum number of retries.")


####################
## Task functions ##
####################
def factory_reset_hid_based(device_serial):
    logger.info(f"Starting hid-based factory reset process on device={device_serial}.")
    try:
        s.check_output(["build-auto/hid-setup/hid-setup",
                        device_serial,
                        device_type[device_serial],
                        "reset"],
                       stderr=s.STDOUT)

        logger.info(f"Waiting for device={device_serial} to finish hid-based resetting.")

        # detect if the device is up again
        # we use hid-setup for that, because it reports the proper serial number
        # wait up to half an hour before raising an error
        for _ in range(30 * 30):
            ret = s.run(["build-auto/hid-setup/hid-setup"],
                        capture_output=True)
            if device_serial in ret.stderr.decode():
                logger.info(f"Found device {device_serial}, finished reset.")
                return
            sleep(30) # wait so that the device is really ready and not in some startup animation
        raise RuntimeError(f"Failed to wait for the device {device_serial} to come up again!")

    except s.CalledProcessError as e:
        logger.error("Caught error in hid-setup: %s", e.output.decode())
        raise RuntimeError("hid-setup failed.")

def factory_reset_device(device_serial):
    logger.info(f"Starting factory reset process on device={device_serial}.")
    run_instrumentation("factoryReset", device_serial, {}, True)

    logger.info(f"Waiting for device={device_serial} to finish resetting.")

    # detect if the device is up again
    # we use hid-setup for that, because it reports the proper serial number
    # wait up to half an hour before raising an error
    for _ in range(30 * 30):
        ret = s.run(["build-auto/hid-setup/hid-setup"],
                    capture_output=True)
        if device_serial in ret.stderr.decode():
            logger.info(f"Found device {device_serial}, finished reset.")
            return
        sleep(30) # wait so that the device is really ready and not in some startup animation
    raise RuntimeError(f"Failed to wait for the device {device_serial} to come up again!")

def initial_device_setup(device_serial):
    logger.info(f"Performing initial setup on device={device_serial}.")
    try:
        s.check_output(["build-auto/hid-setup/hid-setup", device_serial, device_type[device_serial]],
                       stderr=s.STDOUT)
    except s.CalledProcessError as e:
        logger.error("Caught error in hid-setup: %s", e.output.decode())
        raise RuntimeError("hid-setup failed.")

def mute_device(device_serial):
    logger.info(f"Muting sounds on device={device_serial}.")
    s.check_output(["adb", "-s", device_serial, "shell", "input", "keyevent", "164"],
                   stderr=s.STDOUT, env={"ANDROID_SERIAL": device_serial})
    run_instrumentation("disableSound", device_serial, {}, True)

def disable_screen_timeout(device_serial):
    logger.info(f"Disabling screen timeout on device={device_serial}.")
    run_instrumentation("disableScreenTimeout", device_serial, {}, True)

def disable_updates(device_serial):
    logger.info(f"Disabling updates on device={device_serial}.")
    run_instrumentation("disableUpdates", device_serial, {}, True)

def setup_wifi(device_serial):
    logger.info(f"Setting up WIFI on device={device_serial}.")
    run_instrumentation("setupWifi", device_serial, {}, True)

def install_esim(phonenumber, device_serial):
    try:
        logger.info(f"Installing eSIM ({phonenumber}) on device={device_serial}.")
        run_instrumentation("installESIM", device_serial, {"phonenumber" : phonenumber}, True)
    except:
        pass
    finally:
        # sometimes, task dies after registering eSIM (might have to do something with a USB issue?)
        # try to avoid cellular cost by disabling connectivity here
        output = s.check_output(["adb", "-s", device_serial, "shell", "svc", "data", "disable"],
                                stderr=s.STDOUT, env={"ANDROID_SERIAL": device_serial})
        if output != b"":
            logger.warning(f"adb svc data disable returned unexpected value: {output}")

def disable_cellular_data(phonenumber, device_serial):
    """Confirm that cellular is really disabled, disable it if not."""

    logger.info(f"Disabling cellular data for {phonenumber} on device={device_serial}.")
    run_instrumentation("disableCellular", device_serial,
               {"phonenumber" : phonenumber},
               True)

def login_account(email, device_serial, handle_captcha=False):
    logger.info(f"Logging in account {email} on device={device_serial}.")
    run_instrumentation("loginAccount", device_serial,
               {"accountEmail" : email,
                "handleCaptcha": str(handle_captcha)},
               True)

def enable_personalization(email, device_serial):
    logger.info(f"Enabling personalization on device={device_serial}.")
    return run_instrumentation("enablePersonalization", device_serial, {"accountEmail": email}, True)

def disable_personalization(email, device_serial):
    logger.info(f"Disabling personalization on device={device_serial}.")
    return run_instrumentation("disablePersonalization", device_serial, {"accountEmail": email}, True)


def signal_persona(email, device_serial):
    logger.info(f"Signalling persona for {email} on device={device_serial}.")
    run_instrumentation("signalPersona", device_serial, {"accountEmail" : email}, True)

def get_installed_apps(device_serial):
    output = s.check_output(["adb", "-s", device_serial, "shell", "pm", "list", "packages"],
                                stderr=s.STDOUT, env={"ANDROID_SERIAL": device_serial})
    return output

def remove_esim(phonenumber, device_serial):
    logger.info(f"Removing eSIM from device={device_serial}.")
    run_instrumentation("removeESIM", device_serial, {"phonenumber" : phonenumber}, True)

def logout_account(email, device_serial):
    logger.info(f"Logging out account {email} from device={device_serial}.")
    run_instrumentation("logoutAccount", device_serial, {"accountEmail": email}, True)

def extract_ads(email, comment, number_of_ads_per_repetition, number_of_repetitions, repeat_every_minutes, device_serial, group_id, sub_group_id):
    extracted_ads_overall = 0
    time_delta = timedelta(minutes=repeat_every_minutes)

    # Create a database entry for this experiment run
    experiment_id = str(
        create_experiment(email, comment, device_serial, group_id, sub_group_id)
    )

    # execute requested number of repetitions (spaced by repeat_every_minutes)
    for repetition in range(number_of_repetitions):
        time_start = datetime.now()
        logger.info(f"- {device_serial} - Starting repetition {repetition} for {email} / {comment} at {time_start.isoformat()}")

        # in a single repetition, extract until we have extracted at least the target number of ads
        extracted_ads_this_repetition = 0
        while extracted_ads_this_repetition < number_of_ads_per_repetition:
            logger.info(f"- {device_serial} - Extracting ads in repetition {repetition}, {extracted_ads_this_repetition=}, {extracted_ads_overall=}")

            # perform ad extraction
            perform_measurement(experiment_id, device_serial)

            # update the number of extracted ads
            with Session() as s:
                s.mount('https://', HTTPAdapter(max_retries=retries))
                count = s.get("https://harvester.seemoo.tu-darmstadt.de/ad_data/count",
                              params={"experiment_id": experiment_id},
                              headers={"Authorization": auth_token}).json()
            new_number_ads = count["ads"] - extracted_ads_overall
            # calculate how many ads were new
            extracted_ads_this_repetition += new_number_ads
            # update how many ads we have extracted overall
            extracted_ads_overall += new_number_ads

            logger.info(f"- {device_serial} - Rep[{repetition}]: Got {new_number_ads} new ads, overall {extracted_ads_this_repetition} in this repetition. "
                        f"- {device_serial} - Remaining: {number_of_ads_per_repetition - extracted_ads_this_repetition} ads.")

        # wait until next repetition (if there is one!)
        if repetition < number_of_repetitions - 1:
            next_repetition_time = time_start + time_delta
            logger.info(f"- {device_serial} - Got enough ads. Waiting for next iteration at {next_repetition_time.isoformat()}")
            while datetime.now() < next_repetition_time:
                sleep(1)
    logger.info(f"- {device_serial} - Finished all {number_of_repetitions} repetitions, extracted {extracted_ads_overall} ads.")

def perform_measurement(experiment_id, device_serial):
    """Performs a single measurement run as part of an experiment."""

    logger.info(f"- {device_serial} - Starting measurement procedure.")
    run_instrumentation("measurement", device_serial, {"experimentID": experiment_id})
    logger.info(f"- {device_serial} - Finished measurement procedure.")

#####################
## Entry functions ##
#####################
def perform_full_experiment(email: str,
                            device_serial: str,
                            phonenumber: str,
                            group_id: str,
                            sub_group_id: str,
                            signal_step: bool,
                            extract_post_personalization: bool,
                            number_of_ads: int,
                            number_of_repetitions: int,
                            repeat_every_minutes: int,
                            pre_measurement_timeout: int,
                            comment: str,
                            pre_signalling_barrier: Barrier | None,
                            app_install_barrier: Barrier,
                            personalization_barrier: Barrier | None,
                            resume_at: str | None):
    """Function that performs a full experiment run (including baseline and subsequent ad extraction)."""

    try:
        if not resume_at:
            # Step 1.) Reset the device
            factory_reset_device(device_serial)

            # Step 1.a) Initial Device Setup
            initial_device_setup(device_serial)

            # Step 1.b) install instrumentation APK
            install_instrumentation(device_serial)

            # Step 1.c) Mute sounds
            mute_device(device_serial)

            # Step 1.d) Disable screen timeout
            disable_screen_timeout(device_serial)

            # Step 1.e) Disable system updates
            disable_updates(device_serial)

            # Step 1.f) Setup Wifi
            setup_wifi(device_serial)

        # Step 2.) Insert eSIM
        if not resume_at or resume_at == 'esim':
            install_esim(phonenumber, device_serial)

            # Step 2.1) Check that cellular is disabled
            disable_cellular_data(phonenumber, device_serial)

        # Step 3.) Login Google Account
        if not resume_at or resume_at in ["esim", "login"]:
            login_account(email, device_serial)

        # Step 4.) Set Privacy Settings
        # Should by default enable all the relevant telemetry

        # Step 5.) Signal Persona (can be empty for control groups)
        if signal_step and (not resume_at or resume_at in ["esim", "login", "signalling"]):
            pre_signalling_barrier.wait() # wait for the other thread to arrive here
            signal_persona(email, device_serial)

            logger.info(f"{device_serial} - Starting to sleep after successful signalling.")
            # in signal step, we want to wait 3 minutes to prevent rate limiting from impacting the next login
            sleep(60 *3)
            logger.info(f"{device_serial} - Finished sleeping after successful signalling.")

            # extract the installed apps. this might be useful to verify that everything worked as intended
            logger.info(f"{device_serial} - Installed apps are: {get_installed_apps(device_serial)}")

        # wait for all other threads to arrive at this barrier
        # usually, the control group should arrive here first.
        app_install_barrier.wait()

        # extraction step
        if not signal_step and (not resume_at or resume_at in ["esim", "login", "signalling", "measurement"]):
            # wait pre_measurement timeout (per default 0)
            sleep(pre_measurement_timeout * 60)

            # re-enable personalization (mostly necessary for re-extraction)
            if enable_personalization(email, device_serial) != NO_PERS_INDICATOR:
                # Step 6.) AdExtraction only if there are ads to extract
                extract_ads(email, comment, number_of_ads, number_of_repetitions,
                            repeat_every_minutes, device_serial, group_id, sub_group_id)
            else:
                logger.info(f"- {device_serial} - {email} does not get any ads, skipping the extraction process.")

        # Optional: disable personalization and extract again
        if (not signal_step) and extract_post_personalization:
            # sleep 10 minutes
            logger.info(f"{device_serial} - Sleeping after extraction before disabling personalization.")
            sleep(10 * 60)

            logger.info(f"{device_serial} - Starting to disable personalization to extract again.")
            if disable_personalization(email, device_serial) != NO_PERS_INDICATOR:

                # wait for the other to arrive here. sometimes, disabling the personalization might fail
                personalization_barrier.wait()

                extract_ads(email, comment + "_no_personalization", number_of_ads, number_of_repetitions,
                        repeat_every_minutes, device_serial, group_id, sub_group_id)
            else:
                # wait for the other to arrive here. sometimes, disabling the personalization might fail
                personalization_barrier.wait()
                logger.info(f"- {device_serial} - {email} does not get any ads, skipping the extraction process.")

        # Step 7.) Account logout (this is already part of the reset process, so we do not do it here to avoid mistakes)
        # logout_account(email, device_serial)

        # Step 9.) Remove eSIm
        remove_esim(phonenumber, device_serial)

    except RuntimeError as e:
        logger.critical(f"`perform_experiment` failed due to '{e}' on {device_serial}, bailing out.")
        os._exit(-1) # we want to take the second thread with us
    except Exception as e:
        logger.critical(f"Unexpected exception occurred: '{e}' on {device_serial}, bailing out. Full backtrace: {traceback.format_exc()}")
        os._exit(-1) # we want to take the second thread with us


def perform_cross_account_experiment(
    email: str,
    email_successor: str,
    phonenumber: str,
    phonenumber_successor: str,
    device_serial: str,
    group_id: str,
    sub_group_id: str,
    number_of_ads: int,
    number_of_repetitions: int,
    repeat_every_minutes: int,
    comment: str,
    pre_signalling_barrier: Barrier,
    app_install_barrier: Barrier,
    app_install_barrier_extraction: Barrier,
    app_install_barrier_second_acc: Barrier,
    resume_at: str | None,
):
    """Function that performs a cross account experiment run. This includes signalling + waiting 14 days, extracting,
    then logging in the successor account and signalling again."""

    # perform signalling step
    if not resume_at or resume_at in ['esim', 'login', 'signalling']: # esim / login do not have any meaning for this experiment
        logger.info(f"{device_serial} - Starting signalling sub-experiment.")
        perform_full_experiment(
            email=email,
            device_serial=device_serial,
            phonenumber=phonenumber,
            group_id=group_id,
            sub_group_id=sub_group_id,
            signal_step=True,
            extract_post_personalization=False,
            number_of_ads=0,
            number_of_repetitions=0,
            repeat_every_minutes=0,
            pre_measurement_timeout=0,
            comment=comment,
            pre_signalling_barrier=pre_signalling_barrier,
            app_install_barrier=app_install_barrier,
            personalization_barrier=None,
            resume_at=resume_at if resume_at in ["esim", "login"] else None
        )

        # sleep 2 weeks (staying logged in)
        logger.info(f"{device_serial} - Going to sleep for 2 weeks.")
        for week in range(2):
            for days in range(7):
                for hours in range(24):
                    logger.info(f"{device_serial} - Sleeping {week=}, {days=}, {hours=}")
                    # sleep hour
                    sleep(60 * 60)

    # perform extraction step
    if not resume_at or resume_at in ['esim', 'login', 'signalling', 'measurement']:
        logger.info(f"{device_serial} - {email} - Starting extraction step sub-experiment.")
        perform_full_experiment(
            email=email,
            device_serial=device_serial,
            phonenumber=phonenumber,
            group_id=group_id,
            sub_group_id=sub_group_id,
            signal_step=False,
            extract_post_personalization=False,
            number_of_ads=number_of_ads,
            number_of_repetitions=number_of_repetitions,
            repeat_every_minutes=repeat_every_minutes,
            pre_measurement_timeout=0,
            comment=comment,
            pre_signalling_barrier=None, # unused for extraction step
            app_install_barrier=app_install_barrier_extraction,
            personalization_barrier=None, # we do not want to extract post personalization!
            resume_at='measurement' # this account is already logged-in.
        )


    # switch to new account and perform extraction
    logger.info(f"{device_serial} - {email_successor} - Starting extraction of the successor sub-experiment.")
    perform_full_experiment(
        email=email_successor,
        device_serial=device_serial,
        phonenumber=phonenumber_successor,
        group_id=group_id,
        sub_group_id=sub_group_id,
        signal_step=False,
        extract_post_personalization=False,
        number_of_ads=number_of_ads,
        number_of_repetitions=number_of_repetitions,
        repeat_every_minutes=repeat_every_minutes,
        pre_measurement_timeout=0,
        comment=comment+"_SUCCESSOR",
        pre_signalling_barrier=None, # we do not want to signal
        app_install_barrier=app_install_barrier_second_acc,
        personalization_barrier=None,
        resume_at=None
    )

def main():
    # parse args
    parser = argparse.ArgumentParser(
        prog='main',
        description='Glue script between the hid-setup and the AdExtractAuto UI automation tests to run experiments.')
    parser.add_argument("experiment_file", help="A CSV file containing the parameters for one or more experiments.")
    args = parser.parse_args()

    # iterate through the experiments configured in the given CSV file
    with open(args.experiment_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        used_serials = set()
        for experiment_params in reader:
            logger.info(f"Beginning experiment {experiment_params}.")

            assert(experiment_params["control_account_email"] != experiment_params["treatment_account_email"])
            assert(experiment_params["control_device_serial"] != experiment_params["treatment_device_serial"])

            # save these serials for later cleanup
            used_serials.add(experiment_params["control_device_serial"])
            used_serials.add(experiment_params["treatment_device_serial"])

            # fetch account details
            control_account = get_account_details(experiment_params["control_account_email"])
            treatment_account = get_account_details(experiment_params["treatment_account_email"])

            # create barriers
            app_install_barrier = Barrier(parties=2,
                                          action=lambda: logger.info("Both threads finished app installation, continuing after barrier."))
            pre_signalling_barrier = Barrier(parties=2,
                                          action=lambda: logger.info("Both threads arrived at signalling step, continuing after barrier."))
            personalization_barrier = Barrier(parties=2,
                                          action=lambda: logger.info("Both threads finished disabling the personalization, continuing after barrier."))
            # create uuid for the this subgroup
            sub_group_id = str(uuid.uuid4())

            # if we have successor accounts, this is a cross account pollution experiment
            if not ("control_account_email_successor" in experiment_params or "control_account_email_successor" in experiment_params):
                logger.info("Performing a full_experiment run.")

                # create threads for full experiment
                control_thread = Thread(target=perform_full_experiment,
                                        args=(experiment_params["control_account_email"],
                                              experiment_params["control_device_serial"],
                                              control_account['phonenumber'],
                                              experiment_params["group_id"],
                                              sub_group_id,
                                              bool(int(experiment_params["signal_step"])),
                                              bool(int(experiment_params.get("extract_post_personalization", "0"))),
                                              int(experiment_params["number_of_ads"]),
                                              int(experiment_params["number_of_repetitions"]),
                                              int(experiment_params["repeat_every_minutes"]),
                                              int(experiment_params["pre_measurement_timeout"]),
                                              experiment_params["comment"] + 'control_group',
                                              pre_signalling_barrier,
                                              app_install_barrier,
                                              personalization_barrier,
                                              experiment_params["resume_at"]))

                treatment_thread = Thread(target=perform_full_experiment,
                                        args=(experiment_params["treatment_account_email"],
                                              experiment_params["treatment_device_serial"],
                                              treatment_account['phonenumber'],
                                              experiment_params["group_id"],
                                              sub_group_id,
                                              bool(int(experiment_params["signal_step"])),
                                              bool(int(experiment_params.get("extract_post_personalization", "0"))),
                                              int(experiment_params["number_of_ads"]),
                                              int(experiment_params["number_of_repetitions"]),
                                              int(experiment_params["repeat_every_minutes"]),
                                              int(experiment_params["pre_measurement_timeout"]),
                                              experiment_params["comment"] + 'treatment_group',
                                              pre_signalling_barrier,
                                              app_install_barrier,
                                              personalization_barrier,
                                              experiment_params["resume_at"]))
            else:
                logger.info("Running cross-account pollution experiment.")

                # Fetch additional account data
                control_account_successor = get_account_details(experiment_params["control_account_email_successor"])
                treatment_account_successor = get_account_details(experiment_params["treatment_account_email_successor"])

                # create additional barriers
                app_install_barrier_extraction = Barrier(parties=2,
                                                         action=lambda: logger.info("Both threads finished signalling, continuing after barrier."))
                app_install_barrier_second_acc = Barrier(parties=2,
                                                            action=lambda: logger.info("Both threads finished signalling, continuing after barrier."))

                control_thread = Thread(
                    target=perform_cross_account_experiment,
                    args=(
                        experiment_params["control_account_email"],
                        experiment_params["control_account_email_successor"],
                        control_account["phonenumber"],
                        control_account_successor["phonenumber"],
                        experiment_params["control_device_serial"],
                        experiment_params["group_id"],
                        sub_group_id,
                        int(experiment_params["number_of_ads"]),
                        int(experiment_params["number_of_repetitions"]),
                        int(experiment_params["repeat_every_minutes"]),
                        experiment_params["comment"] + "control_group",
                        pre_signalling_barrier,
                        app_install_barrier,
                        app_install_barrier_extraction,
                        app_install_barrier_second_acc,
                        experiment_params["resume_at"]))

                treatment_thread = Thread(
                    target=perform_cross_account_experiment,
                    args=(
                        experiment_params["treatment_account_email"],
                        experiment_params["treatment_account_email_successor"],
                        treatment_account["phonenumber"],
                        treatment_account_successor["phonenumber"],
                        experiment_params["treatment_device_serial"],
                        experiment_params["group_id"],
                        sub_group_id,
                        int(experiment_params["number_of_ads"]),
                        int(experiment_params["number_of_repetitions"]),
                        int(experiment_params["repeat_every_minutes"]),
                        experiment_params["comment"] + "treatment_group",
                        pre_signalling_barrier,
                        app_install_barrier,
                        app_install_barrier_extraction,
                        app_install_barrier_second_acc,
                        experiment_params["resume_at"]))

            control_thread.start()
            treatment_thread.start()

            control_thread.join()
            treatment_thread.join()

        # we want to reset the devices again to prevent accounts from being logged in longer than intended
        logger.info('Starting cleanup procedure.')
        for serial in used_serials:
            factory_reset_device(serial)

            # perform initial device setup to prevent the device from powering off
            initial_device_setup(serial)
            install_instrumentation(serial)

        # log success
        logger.warning(f"Finished all experiments in '{args.experiment_file}'.")

if __name__ == "__main__":
    exit(main())
