import re
import requests
from selenium import webdriver
from bs4 import BeautifulSoup

from src.custom_logging import setup_logger
from src.logic.language import ProviderError, get_href_by_language
from src.constants import (provider_priority)

logger = setup_logger(__name__)

# ------------------------------------------------------- #
#                   definitions
# ------------------------------------------------------- #
cache_url_attempts = 0

# ------------------------------------------------------- #
#                   global variables
# ------------------------------------------------------- #
VOE_PATTERNS = [re.compile(r"'hls': '(?P<url>.+)'"),
                re.compile(r'prompt\("Node",\s*"(?P<url>[^"]+)"')]
STREAMTAPE_PATTERN = re.compile(r'get_video\?id=[^&\'\s]+&expires=[^&\'\s]+&ip=[^&\'\s]+&token=[^&\'\s]+\'')

# ------------------------------------------------------- #
#                      functions
# ------------------------------------------------------- #

def get_year(url):
    """
    Get the year of the show.

    Parameters:
        url (String): url of the show.

    Returns:
        year (String): year of the show.
    """
    try:
        html_page = requests.get(url, allow_redirects=True)
        html_page.raise_for_status()
        logger.debug("Opened URL: " + url)
        soup = BeautifulSoup(html_page.text, features="html.parser")
        logger.debug("Soup is ready.")
        year = soup.find("span", {"itemprop": "startDate"}).text
        logger.debug("Year is: " + year)
        return year
    except AttributeError:
        logger.error("Could not find year of the show.")
        return 0

def get_redirect_link_by_provider(site_url, internal_link, language, provider):
    """
    Sets the priority in which downloads are attempted.
    First -> VOE download, if not available...
    Second -> Streamtape download, if not available...
    Third -> Vidoza download

    Parameters:
        site_url (String): serie or anime site.
        internal_link (String): link of the html page of the episode.
        language (String): desired language to download the video file in.
        provider (String): define the provider to use.

    Returns:
        get_redirect_link(): returns link_to_redirect and provider.
    """
    local_provider_priority = provider_priority.copy()
    local_provider_priority.remove(provider)
    try:
        return get_redirect_link(site_url, internal_link, language, provider)
    except ProviderError:
        logger.info(f"Provider {provider} failed. Trying {local_provider_priority[0]} next.")
        try:
            return get_redirect_link(site_url, internal_link, language, local_provider_priority[0])
        except ProviderError:
            logger.info(f"Provider {local_provider_priority[0]} failed. Trying {local_provider_priority[1]} next.")
            return get_redirect_link(site_url, internal_link, language, local_provider_priority[1])

def get_redirect_link(site_url, html_link, language, provider):
    # if you encounter issues with captchas use this line below
    # html_link = open_captcha_window(html_link)
    html_response = requests.get(html_link, allow_redirects=True)
    html_response.raise_for_status()
    href_value = get_href_by_language(html_response.text, language, provider)
    link_to_redirect = site_url + href_value
    logger.debug("Link to redirect is: " + link_to_redirect)
    return link_to_redirect, provider

def find_cache_url(url, provider):
    global cache_url_attempts
    logger.debug("Entered {} to cache".format(provider))

    try:
        # Set up Selenium with headless option
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)

        # Open the URL and handle redirects
        driver.get(url)
        redirected_url = driver.current_url

        # If redirected, fetch the page source
        if redirected_url != url:
            logger.debug(f"Redirected to: {redirected_url}")
            html_page = driver.page_source
        else:
            response = requests.get(url, allow_redirects=True)
            response.raise_for_status()
            html_page = response.text

        driver.quit()

    except requests.RequestException as e:
        logger.warning(f"{e}")
        logger.info("Trying again to read HTML Element...")
        if cache_url_attempts < 5:
            cache_url_attempts += 1
            return find_cache_url(url, provider)
        else:
            logger.error("Could not find cache url HTML for {}.".format(provider))
            return 0

    try:
        if provider == "Vidoza":
            soup = BeautifulSoup(html_page, features="html.parser")
            cache_link = soup.find("source").get("src")
        elif provider == "VOE":
            for voe_pattern in VOE_PATTERNS:
                match = voe_pattern.search(html_page)
                if match:
                    cache_link = match.group("url")
                    if cache_link and cache_link.startswith("https://"):
                        return cache_link
            logger.error("Could not find cache url for {}.".format(provider))
            return 0
        elif provider == "Streamtape":
            match = STREAMTAPE_PATTERN.search(html_page)
            if match:
                cache_link = "https://" + provider + ".com/" + match.group()[:-1]
                logger.debug(f"This is the found video link of {provider}: {cache_link}")
                return cache_link
            else:
                return find_cache_url(url, provider)
    except AttributeError as e:
        logger.error(f"ERROR: {e}")
        logger.info("Trying again...")
        if cache_url_attempts < 5:
            cache_url_attempts += 1
            return find_cache_url(url, provider)
        else:
            logger.error("Could not find cache url for {}.".format(provider))
            return 0

    logger.debug("Exiting {} to Cache".format(provider))
    return cache_link

# ------------------------------------------------------- #
#                      classes
# ------------------------------------------------------- #


# ------------------------------------------------------- #
#                       main
# ------------------------------------------------------- #
