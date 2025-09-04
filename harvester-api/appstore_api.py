#!python3

from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import json
import requests as r
import os
from time import sleep

def fetch_app_details_ios(search_term, logger):
    logger.info(f"iOS - Searching for '{search_term}'.")
    bearer_token = "Bearer %s" % (os.environ["APPLE_BEARER"])
    payload = {'platform' : 'iphone', 'term' : search_term, 'l' : 'en_GB'}
    headers = {'Authorization' : bearer_token}

    success = False
    while success == False:
        res = r.get("https://amp-api-search-edge.apps.apple.com/v1/catalog/de/search",
                params=payload, headers=headers)

        #check for valid response
        if res.status_code != 200:
            logger.warning(f"iOS - Http request unsuccessful for query '{search_term}'")
            logger.warning(f"iOS - Http Response: {res.status_code} {res.reason}")
            logger.info("Retrying...")
            sleep(3)
        else:
            success = True

    search_result_data = res.json()['results']['search-result']['data']

    #check if there are any results
    if len(search_result_data) < 1:
        logger.warning(f"iOS - no search results for iOS query '{search_term}'")
        return None

    #iterate through all results and choose first match
    first_result_index = -1

    for i, result in enumerate(search_result_data):
        if result["type"] == "apps" and "attributes" in result.keys():
            if search_term.casefold() in result["attributes"]["name"].casefold():
                logger.info(f"iOS - found match: '{result['attributes']['name']}'")
                if first_result_index != -1:
                    logger.warning(f"iOS - found more than one match for query '{search_term}', using first one.")
                    break
                else:
                    first_result_index = i

    #choose first match if available
    if first_result_index >= 0:
        #fetch details...
        first_result = res.json()['results']['search-result']['data'][first_result_index]
        logger.info(f"iOS - Fetching details for '{search_term}'.")
        detail_link = f"https://amp-api-search-edge.apps.apple.com{first_result['href']}"
        payload = {'platform' : 'iphone', 'l' : 'en_GB'}
        detail_res = r.get(detail_link, params=payload, headers=headers)
    else:
        #no match
        logger.info(f"iOS - found no match for iOS query '{search_term}'")
        return None

    return detail_res.json()["data"][0]


def look_up_app_id_android(name, logger):
    logger.info(f"Android - Looking up ID for '{name}'.")

    user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
    search_url = "https://play.google.com/store/search?q={}&c=apps"
    page = r.get(search_url.format(quote_plus(name)), headers={"User-Agent": user_agent})
    link_start = "/store/apps/details?id="

    def filter_fn(tag):
        return tag.name == "a" and link_start in tag.get("href", "")

    soup = BeautifulSoup(page.text, "lxml")
    matches = soup.find_all(filter_fn, limit=1)

    if len(matches) > 1:
        logger.warn(f"look_up_add_id({name}) found more than one match, using first one.")
        logger.warn([m["href"].split(link_start, 1)[-1] for m in matches])
    if len(matches) == 0:
        print(f"Warning: look_up_add_id({name}) found no match.")
        return None
    return matches[0]["href"].split(link_start, 1)[-1]


def fetch_app_details_android(app_id, logger):
    logger.info(f"Android - Fetching details for '{app_id}'.")

    user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
    details_url = "https://play.google.com/store/apps/details?id={}"
    doc = r.get(details_url.format(quote_plus(app_id)), headers={"User-Agent": user_agent}).text
    soup = BeautifulSoup(doc, "lxml")

    def filter_fn(tag):
        return tag.name == "script" and tag.get("type") == "application/ld+json"

    containers = soup.find_all(filter_fn)
    assert len(containers)== 1

    data = containers[0].contents
    assert len(data) == 1

    return json.loads(data[0])

def get_top_apps_ios(logger, genre_id, limit):
    """returns list tuples of (adamId, bundleId, name)"""

    logger.info(f"iOS - Fetching iOS Free App Charts for category '{genre_id}'. Limited to {limit} results.")

    headers = { 'X-Apple-Store-Front': '143443-2,26' }
    result =  r.get(f'https://itunes.apple.com/WebObjects/MZStore.woa/wa/viewTop?cc=de&genreId={genre_id}&l=de&popId=27',  headers=headers)
    if result.status_code != 200:
        logger.error(f"iOS - Http request unsuccessful '{result.url}'")
        logger.error(f"iOS - Http Response: {result.status_code} {result.reason}")
        return None
    
    con = result.json()

    adamIds = con["pageData"]["segmentedControl"]["segments"][0]["pageData"]["selectedChart"]["adamIds"]
    
    apps = []
    for i, adamId in enumerate(adamIds):
        if i > limit-1:
            break
        
        app_info = retrieve_app_api(logger, "http://itunes.apple.com/de/lookup", adamId)

        if app_info == None:
            logger.error(f"Could not retrieve App witch adamId {adamId}...")

        apps.append(app_info)

    return apps

def retrieve_app_api(logger, url, adamId):
    success = False
    params = {'id': adamId,
              'l' : 'en'}

    while success == False:
        app_resp = r.get(url, params=params)
        if app_resp.status_code == 200:
            app_json = app_resp.json()
            success = True

            if app_json["resultCount"] > 0:
                return (adamId, app_resp.json()["results"][0]["bundleId"], app_resp.json()["results"][0]["trackName"])
            else:
                logger.warning(f"iOS - Could not fetch App with adamId {adamId} from {url}.")
                return None

        else:
            logger.warning(f"iOS - No valid response for App with adamId {adamId} from {url}. Retrying...")