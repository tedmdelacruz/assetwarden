import difflib
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from urllib.parse import urljoin, urlparse

import click
import jsbeautifier
import requests
import yaml
from bs4 import BeautifulSoup
from discord_notify import Notifier
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_RETRY_ATTEMPTS = 5
API_ENDPOINTS_REGEX = r"(?<=['\"`])\/[\w\/\.-]+(?=['\"`])"
SCRIPT_BASE_PATH = os.path.dirname(os.path.realpath(__file__))
DEFAULT_SAVE_PATH = os.path.join(SCRIPT_BASE_PATH, "./monitored_assets")

# The main configuration dictionary
config = None

# Config file to use
config_filepath = "./config.yaml"


def load_config_file():
    """Loads the defined config file if config is not defined yet"""
    global config
    global config_filepath

    # Do not load config file if config has already been set
    if config:
        return

    config_filepath = open(os.path.join(SCRIPT_BASE_PATH, config_filepath), "r")
    config = yaml.safe_load(config_filepath)
    config_filepath.close()


def get_config(key, default=None):
    """Fetches a config item from the defined config.yaml file"""
    load_config_file()

    try:
        return config[key]
    except KeyError:
        return default


def generate_source(url, source_basepath):
    """Attempts to generate source from sourcemap from a resource URL"""
    response = requests.get(url.split("?")[0])
    sourcemap_split = response.content.decode().split("//# sourceMappingURL=")
    if len(sourcemap_split) == 1:
        return

    sourcemap = sourcemap_split[1]
    if not sourcemap:
        return

    if not os.path.exists(source_basepath):
        os.mkdir(source_basepath)

    datetime_now = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
    sourcemap_url = (
        sourcemap if sourcemap.startswith("http") else urljoin(url, sourcemap)
    )
    log(f"Attempting to regenerate source {sourcemap_url}...")
    source_dir = os.path.join(source_basepath, datetime_now)
    subprocess.run(
        ["sourcemapper", "-output", source_dir, "-url", sourcemap_url],
        capture_output=True,
    )


def download_file(url, download_filepath):
    """Downloads a resource from a URL into the local file system. Opted for requests
    instead of urllib library due to its better handling of encodings.
    Removes query parameters to mitigate caching issues.
    """
    response = requests.get(url.split("?")[0])
    with open(download_filepath, "wb") as f:
        f.write(response.content)


def notify(message):
    """Sends a notification via Discord"""
    notifier = Notifier(config["discord_webhook_url"])
    notifier.send(message, print_message=False)


def get_optional_config(key, config, default=None):
    return config[key] if key in config else default


def log(message):
    if get_config("verbose", True):
        print(message)


def fetch_resource_url(
    url,
    selector,
    asset_base_path,
    headers={},
    url_attribute="src",
    dynamic=False,
    timeout=DEFAULT_TIMEOUT_SECONDS,
):
    """Fetches a resource URL from a webpage element given a CSS selector. Useful for
    retrieving URLs from <script src="{resource_url}"></script> or <link href="{resource_url}/>.

    Uses plain requests for static JS files, otherwise use Selenium for dynamic JS files.
    """
    log(f"Fetching resource from {url}...")

    if not dynamic:
        response = requests.get(url, headers=headers)
        html = BeautifulSoup(response.content, "html.parser")
        asset_element = html.select_one(selector)
        if not asset_element:
            return
        asset_url = asset_element.get(url_attribute)
        if not asset_url.startswith("http"):
            return urljoin(asset_base_path, asset_url)

    try:
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-dev-shm-usage")
        ignored_exceptions = (StaleElementReferenceException,)
        browser = webdriver.Chrome(options=chrome_options)
        browser.get(url)

        asset_url = (
            WebDriverWait(browser, timeout, ignored_exceptions=ignored_exceptions)
            .until(ec.presence_of_element_located((By.CSS_SELECTOR, selector)))
            .get_attribute(url_attribute)
        )
        if not asset_url.startswith("http"):
            return urljoin(asset_base_path, asset_url)
        return asset_url

    except (TimeoutException, StaleElementReferenceException, NoSuchElementException):
        log("Timed out. Retrying...")
    except WebDriverException as e:
        log(e)


def get_new_endpoints(js_filepath, known_endpoints_filepath):
    """Finds API endpoints in a JS filepath and adds them into known_endpoints.txt"""
    pattern = re.compile(API_ENDPOINTS_REGEX)
    with open(js_filepath, "r") as js_file:
        detected_endpoints = set(pattern.findall(js_file.read()))

    if not os.path.isfile(known_endpoints_filepath):
        with open(known_endpoints_filepath, "w") as f:
            f.writelines(
                [endpoint + "\n" for endpoint in sorted(detected_endpoints) if endpoint]
            )
        return set()

    with open(known_endpoints_filepath, "r") as f:
        contents = f.read()
        known_endpoints = set(filter(None, contents.split("\n")))
        new_endpoints = detected_endpoints.symmetric_difference(known_endpoints)

    with open(known_endpoints_filepath, "w") as f:
        f.writelines(
            [
                endpoint + "\n"
                for endpoint in sorted(detected_endpoints | known_endpoints)
                if endpoint
            ]
        )
        f.close()

    return new_endpoints


def monitor_js(target_name, identifier, js_url, save_path=None):
    """Monitors changes in a JS file by fetching known API endpoints and comparing
    it against an older version saved in the save path.

    Creates a historical snapshot diff file at /path/to/save_path/YYYY-MM-DD_h_m_s.diff
    """
    if save_path:
        base_path = os.path.realpath(save_path)
    else:
        base_path = os.path.dirname(os.path.realpath(__file__))

    if not os.path.exists(base_path):
        os.mkdir(base_path)

    diff_dir = os.path.join(base_path, identifier)
    if not os.path.exists(diff_dir):
        os.mkdir(diff_dir)

    raw_js_filepath = os.path.join(diff_dir, "raw.js")
    new_js_filepath = os.path.join(diff_dir, "new.js")
    old_js_filepath = os.path.join(diff_dir, "old.js")
    source_basepath = os.path.join(diff_dir, "source")
    known_endpoints_filepath = os.path.join(diff_dir, "known_endpoints.txt")
    datetime_now = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
    diff_filepath = os.path.join(diff_dir, f"{datetime_now}.diff")
    endpoints_diff_filepath = os.path.join(diff_dir, f"{datetime_now}-endpoints.diff")

    download_file(js_url, raw_js_filepath)
    log(f"Downloaded {js_url}")

    generate_source(js_url, source_basepath)

    try:
        with open(new_js_filepath, "w") as f:
            f.write(jsbeautifier.beautify_file(raw_js_filepath))
    except UnicodeDecodeError:
        log(f"Failed to decode JS file: {js_url}")

    if not os.path.isfile(old_js_filepath):
        shutil.copyfile(new_js_filepath, old_js_filepath)
        return

    new_endpoints = get_new_endpoints(new_js_filepath, known_endpoints_filepath)
    if len(new_endpoints) > 0:
        with open(endpoints_diff_filepath, "w") as f:
            f.writelines(endpoint + "\n" for endpoint in new_endpoints)
        notify(
            f"> Detected {len(new_endpoints)} new endpoint(s) in {target_name} at {js_url}\n"
            f"```{endpoints_diff_filepath}```"
        )

    diff = list(
        difflib.unified_diff(
            open(old_js_filepath, "r").readlines(),
            open(new_js_filepath, "r").readlines(),
        )
    )

    if len(diff) == 0:
        shutil.copyfile(new_js_filepath, old_js_filepath)
        return

    with open(diff_filepath, "w") as diff_file:
        for line in diff:
            diff_file.write(line)

        notify(
            f"> Detected file changes in {target_name} at {js_url}\n"
            f"```{diff_filepath}```"
        )

    shutil.copyfile(new_js_filepath, old_js_filepath)


def detect_changes(target):
    """Detects changes in an asset resource"""
    if not target["enabled"]:
        return

    resource_url = None
    retry_attempt = 0
    while not resource_url and retry_attempt <= DEFAULT_RETRY_ATTEMPTS:
        resource_url = fetch_resource_url(
            target["webpage"],
            target["selector"],
            headers=get_optional_config("headers", target),
            asset_base_path=get_optional_config("asset_base_path", target),
            url_attribute=get_optional_config("url_attribute", target, "src"),
            dynamic=get_optional_config("dynamic", target, False),
            timeout=config["timeout"],
        )
        retry_attempt += 1

    target_name = target["name"]
    if not resource_url:
        notify(f"> Failed to fetch resource URL at {target_name}")
        return

    save_path = get_config("save_path", DEFAULT_SAVE_PATH)
    monitor_js(target_name, target["identifier"], resource_url, save_path=save_path)


@click.command
@click.option(
    "--use-config",
    default="./config.yaml",
    help="Path to custom config.yaml file to load",
)
def main(use_config):
    global config_filepath
    config_filepath = use_config

    targets = get_config("targets", [])
    if get_config("enable_multithreading", True):
        threads = []
        for target in targets:
            thread = threading.Thread(target=detect_changes, args=(target,))
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()
    else:
        for target in targets:
            detect_changes(target)

    log("Done.")


if __name__ == "__main__":
    main()
