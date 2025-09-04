"""Google specific account creation logic."""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from time import sleep
from random import randint
from sim_factor import install_esim, remove_esim, SSH_CONFIG, retrieve_code_google
from fabric import Connection, Config
from fabric.config import SSHConfig
import atexit


TIMEOUT = 10
GOOGLE_ACCOUNT_CREATION_PAGE = "https://accounts.google.com/ServiceLogin?hl=de&passive=true&continue=https://www.google.com/&ec=GAZAmgQ"
DELAY_CLICK_MIN = 1000
DELAY_CLICK_MAX = 4000
DELAY_TYPE_MIN = 200
DELAY_TYPE_MAX = 1000
ATTEMPTS = 5
USE_CHROMIUM = True

# Helper method for just clicking on a span with text.
def click(text, driver, elem_type="span"):
    for i in range(ATTEMPTS):
        try:
            WebDriverWait(driver, TIMEOUT).until(
                expected_conditions.element_to_be_clickable(
                    (By.XPATH,
                     f"//{elem_type}[text()='{text}']"))
            ).click()
            sleep(randint(DELAY_CLICK_MIN, DELAY_CLICK_MAX) / 1000)
            return
        except StaleElementReferenceException:
            print(f"Caught StaleElementReferencException, retrying {i} / {ATTEMPTS}")
            sleep(2)


# Helper to fill a form field. allows custom xpath, then field is ignored.
def fill_form(field, value, driver, xpath=None):
    for i in range(ATTEMPTS):
        try:
            elem = WebDriverWait(driver, TIMEOUT).until(
            expected_conditions.element_to_be_clickable(
                (By.XPATH,
                 (f"//input[@id ='{field}' and @name='{field}']" if not xpath else xpath)
                 )
            ))
            elem.clear()
            # simulate slow typing
            for c in value:
                elem.send_keys(c)
                sleep(randint(DELAY_TYPE_MIN, DELAY_TYPE_MAX) / 1000)
            return
        except StaleElementReferenceException:
            print(f"Caught StaleElementReferencException, retrying {i} / {ATTEMPTS}")
            sleep(2)


# Select given value from a dropdown given an ID
def select_dropdown(field, value, driver):
    for i in range(ATTEMPTS):
        try:
            elem = WebDriverWait(driver, TIMEOUT).until(
                expected_conditions.visibility_of_element_located(
                    (By.XPATH,
                     f"//select[@id ='{field}']"))
            )
            Select(elem).select_by_value(value)
            sleep(randint(DELAY_CLICK_MIN, DELAY_CLICK_MAX) / 1000)
            return
        except StaleElementReferenceException as e:
            print(f"Caught StaleElementReferencException, retrying {i} / {ATTEMPTS}")
            sleep(2)


def login_account(args):
    if USE_CHROMIUM:
        option = webdriver.ChromeOptions()

        #Removes navigator.webdriver flag
        # For older ChromeDriver under version 79.0.3945.16
        option.add_experimental_option("excludeSwitches", ["enable-automation"])
        option.add_experimental_option('useAutomationExtension', False)

        #For ChromeDriver version 79.0.3945.16 or over
        option.add_argument('--disable-blink-features=AutomationControlled')
        #Open Browser
        driver = webdriver.Chrome(options=option)

    else:
        # Create driver and open google login page
        options = webdriver.FirefoxOptions()
        driver = webdriver.Firefox(options=options)

    
    driver.get("https://www.google.com/")
    click("Alle ablehnen", driver, elem_type='div')

    # click sign in
    WebDriverWait(driver, TIMEOUT).until(
        expected_conditions.element_to_be_clickable((By.XPATH, "//a[@aria-label='Anmelden']"))).click()
    sleep(randint(DELAY_CLICK_MIN, DELAY_CLICK_MAX) / 1000)

    # fill email field
    fill_form(None, args.email, driver, f"//input[@id ='identifierId']")

    # click next
    click("Weiter", driver)

    # fill password
    fill_form(None, args.password, driver, f"//input[@name='Passwd']")

    # click next
    click("Weiter", driver)

    if input("Perform phone entry? (y/N): ") == 'y':
        # fill telephone
        fill_form(None, "+49" + args.phonenumber, driver, "//input[@type='tel' and @id='phoneNumberId']")
        click('Weiter', driver)

        input("Press enter after filling code")

        # click next
        click("Nicht jetzt", driver)

    link_services(driver, args)

def link_services(driver, args):
    print("Waiting a few seconds before navigating...")
    sleep(5)
    driver.get("https://myactivity.google.com/linked-services?hl=en")

    # click select all
    driver.find_elements(By.XPATH, "//input")[0].click()

    click("Next", driver)

    click("Confirm", driver)

    click("Done", driver)

    sleep(2)

def create_google_account(args, retry=False):
    conf = Config(ssh_config=SSHConfig.from_text(SSH_CONFIG))
    with Connection("mac", config=conf) as con:

        sim_install_promise = None
        def cleanup():
            if sim_install_promise is not None:
                # wait for install to cleanup. because if install fails, we can't remove the sim
                print(sim_install_promise.join())
            print(remove_esim(con, args.phonenumber).join())

        sim_install_promise = install_esim(con, args.phonenumber)
        atexit.register(cleanup)

        # if this is a retry, we don't need to install the esim
        if not retry:
            # we can start the sim insertion simultaneously
            sim_install_promise = install_esim(con, args.phonenumber)
            atexit.register(cleanup)

        # Create driver and open google login page
        if USE_CHROMIUM:
            option = webdriver.ChromeOptions()

            #Removes navigator.webdriver flag
            # For older ChromeDriver under version 79.0.3945.16
            option.add_experimental_option("excludeSwitches", ["enable-automation"])
            option.add_experimental_option('useAutomationExtension', False)

            #For ChromeDriver version 79.0.3945.16 or over
            option.add_argument('--disable-blink-features=AutomationControlled')
            #Open Browser
            driver = webdriver.Chrome(options=option)
        else:
            # Create driver and open google login page
            options = webdriver.FirefoxOptions()
            driver = webdriver.Firefox(options=options)

        driver.get(GOOGLE_ACCOUNT_CREATION_PAGE)

        # click on "Account erstellen" (FIXME: Language detection?)
        click('Konto erstellen', driver)

        # select "Für meine private Nutzung"
        click('Für meine private Nutzung', driver)

        # fill "Vorname" field
        fill_form('firstName', args.first_name, driver)

        # fill "Nachname" field
        fill_form('lastName', args.sur_name, driver)

        # click "Weiter"
        click('Weiter', driver)

        # fill "Tag" field
        fill_form('day', args.birthdate_day, driver)

        # select "month" in dropdown
        select_dropdown("month", args.birthdate_month, driver)

        # fill "Year" field
        fill_form('year', args.birthdate_year, driver)

        # fill "geschlecht"
        select = Select(driver.find_element(By.XPATH, f"//select[@id ='gender']"))
         # order is male=1, female=2, prefer_not_to_say=3, custom=4
        select.select_by_value(str(['male', 'female', 'prefer_not_to_say', 'custom'].index(args.gender) + 1))
        sleep(randint(DELAY_CLICK_MIN, DELAY_CLICK_MAX) / 1000)

        # click "Weiter"
        click('Weiter', driver)

        # select create gmail address
        click('Gmail-Adresse erstellen', driver, 'div')

        # click "Weiter"
        click('Weiter', driver)

        # TODO: this seems not always be required? Maybe we need to detect this state
        # # select create gmail address again, to enter a custom address
        try:
            click('Gmail-Adresse erstellen', driver, 'div')
        except TimeoutException as e:
            print("Caught timeout when trying to click 'create address', this might be fine, continuing.")

        # fill "gmail address" field
        fill_form(None, args.email.replace("@gmail.com", ""), driver, "//input[@name='Username']")

        # click "Weiter"
        click('Weiter', driver)

        # fill "password" field and passwd confirm field
        fill_form(None, args.password, driver, "//input[@type='password' and @name='Passwd']")
        fill_form(None, args.password, driver, "//input[@type='password' and @name='PasswdAgain']")

        # click "Weiter"
        click('Weiter', driver)

        # here usually the 'rate limit' error happens ("account could not be created")
        try:
            fill_form(None, args.phonenumber, driver, "//input[@type='tel' and @id='phoneNumberId']")
            click('Weiter', driver)
        except TimeoutException:
            driver.close()
            return False

        if not retry:
            # we need to wait for the phonenumber here
            print(sim_install_promise.join())
            sleep(1)

        for _ in range(10):
            try:
                code = retrieve_code_google(con)
                print("code is:", code)
                break
            except RuntimeError:
                print("Failed to fetch code, retry")
                sleep(1)
        # no code was found
        else:
            input("Press enter to exit.")
            raise RuntimeError("Failed to get a code, aborting.")

        # enter code
        try:
            fill_form("code", code.replace("G-", ""), driver)
            click('Weiter', driver)

            click('Überspringen', driver)
        except TimeoutException:
            if input("Failed to enter code, manually fixed this? (enter y after hitting 'skip').").strip().lower() != "y":
                raise RuntimeError("Failed to get a valid code, aborting.")

        import subprocess
        subprocess.Popen(["chromium", "--incognito"])

        # # after we got the code (and it worked), we can remove the esim again
        input("Hit enter after getting the code!")
        atexit.unregister(cleanup) # we do not need to start the sim promise
        esim_removal_promise = remove_esim(con, args.phonenumber)

        # however, we need to wait for it in case we don't reach the end
        def cleanup_second_stage():
            print(esim_removal_promise.join())
        atexit.register(cleanup_second_stage)

        # # debugging only
        # # input("Hit enter after entering code.")

        click('Weiter', driver)

        # here is a new dialogue asking to use the number?
        # only happens sometimes though.
        try:
            click('Ja, ich stimme zu', driver)
        except TimeoutException:
            pass

        try:
            click('Weiter', driver)
        except TimeoutException:
            print("Expected Weiter, but not found.")

        # select express
        # this is a weird radio button selection thingy
        WebDriverWait(driver, TIMEOUT).until(
            expected_conditions.element_to_be_clickable(
                (By.XPATH, "//div[text()='Express (1 Schritt)']"))
        ).click()
        sleep(randint(DELAY_CLICK_MIN, DELAY_CLICK_MAX) / 1000)

        click('Weiter', driver)

        click('Alle akzeptieren', driver)

        click('Bestätigen', driver)

        click('Ich stimme zu', driver)

        link_services(driver, args)

        # here we should wait for esim removal
        atexit.unregister(cleanup_second_stage)
        print(esim_removal_promise.join())

        input("Finished creation?")
        # driver.close()
        return True
