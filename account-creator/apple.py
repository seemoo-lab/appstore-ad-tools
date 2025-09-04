"""Apple specific account creation logic.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from time import sleep
from random import randint
from sim_factor import install_esim, remove_esim, retrieve_code_apple, SSH_CONFIG
from fabric import Config, Connection
from fabric.config import SSHConfig

TIMEOUT = 5
APPLE_ACCOUNT_CREATION_PAGE = "https://appleid.apple.com/account"
DELAY_CLICK_MIN = 1000
DELAY_CLICK_MAX = 4000
DELAY_TYPE_MIN = 200
DELAY_TYPE_MAX = 1000

safari = True

def create_apple_account(args):
    global safari
    # insert sim card
    conf = Config(ssh_config=SSHConfig.from_text(SSH_CONFIG))
    with Connection("mac", config=conf) as con:
        print(f"Installing eSim for number {args.phonenumber}")
        install_task = install_esim(con, args.phonenumber)

        # Create driver and open google login page
        print("Loading web driver...")
        if safari:
            options = webdriver.SafariOptions()
            driver = webdriver.Safari(options=options)
            safari = False
        else:
            options = webdriver.FirefoxOptions()
            driver = webdriver.Firefox(options=options)
            safari = True

        driver.get(APPLE_ACCOUNT_CREATION_PAGE)

        sleep(3)

        # apple randomizes their IDs, so we do it by order
        inputs = driver.find_elements(By.TAG_NAME, "input")
        selects = driver.find_elements(By.TAG_NAME, "select")

        # for developing: print ids of fields
        # print([i.get_attribute('id') for i in inputs])

        # set firstname
        #inputs[3].send_keys(args.first_name)
        type_keys(inputs[3], args.first_name)

        # set lastname
        #inputs[4].send_keys(args.sur_name)
        type_keys(inputs[4], args.sur_name)

        # set country DE
        Select(selects[0]).select_by_value("DEU")
        sleep(randint(DELAY_CLICK_MIN, DELAY_CLICK_MAX) / 1000)


        # set birthday (need to click it first)
        inputs[5].click()
        sleep(randint(DELAY_CLICK_MIN, DELAY_CLICK_MAX) / 1000)
        #inputs[5].send_keys(
        #    f"{args.birthdate_month.zfill(2)}{args.birthdate_day.zfill(2)}{args.birthdate_year}"
        #)
        type_keys(inputs[5], f"{args.birthdate_month.zfill(2)}{args.birthdate_day.zfill(2)}{args.birthdate_year}")

        # set email
        #inputs[6].send_keys(args.email)
        type_keys(inputs[6], args.email)

        # set passwords
        #inputs[7].send_keys(args.password)
        type_keys(inputs[7], args.password)
        #inputs[8].send_keys(args.password)
        type_keys(inputs[8], args.password)

        # set phone number prefix
        Select(selects[1]).select_by_value("DE")
        sleep(randint(DELAY_CLICK_MIN, DELAY_CLICK_MAX) / 1000)

        # set phone number
        #inputs[9].send_keys(args.phonenumber)
        type_keys(inputs[9], args.phonenumber)

        # scroll down
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        sleep(randint(DELAY_CLICK_MIN, DELAY_CLICK_MAX) / 1000)

        install_task.join()
        print("eSIM installed.")
        # focus captcha field
        inputs[14].click()

        #input("sms factor sent?")
        #second_factor = retrieve_code_apple(con)
        #print(f"Second Factor is {second_factor}")
        input("Finished creation?")
        print("Ejecting eSim...")
        remove_esim(con, args.phonenumber).join()
        print("eSIM ejected.")
        input("Browser window closed?")

def handle_sim_only(args):
    conf = Config(ssh_config=SSHConfig.from_text(SSH_CONFIG))
    with Connection("mac", config=conf) as con:
        print(f"Installing eSim for number {args.phonenumber}")
        install_task = install_esim(con, args.phonenumber)
        install_task.join()
        print("eSIM installed.")
        input("Finished creation?")
        print("Ejecting eSim...")
        remove_esim(con, args.phonenumber).join()
        print("eSIM ejected.")


def type_keys(input, value):
    for c in value:
        sleep(randint(DELAY_TYPE_MIN, DELAY_TYPE_MAX)/1000)
        input.send_keys(c)
        
    sleep(randint(DELAY_TYPE_MIN, DELAY_TYPE_MAX)/1000)
