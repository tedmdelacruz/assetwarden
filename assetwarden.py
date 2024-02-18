import difflib
import os
import shutil
import threading
from datetime import datetime

import jsbeautifier
import requests
import yaml
from discord_notify import Notifier
from selenium import webdriver
from selenium.common.exceptions import (NoSuchElementException,
                                        StaleElementReferenceException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_SAVE_PATH = "./monitored_files"

config_file = open("config.yaml", "r")
config = yaml.safe_load(config_file)
config_file.close()


def download_file(url, download_filepath):
    """Downloads a resource from a URL into the local file system. Opted for requests
    instead of urllib library due to its better handling of encodings"""
    response = requests.get(url)
    with open(download_filepath, "wb") as f:
        f.write(response.content)


def notify(message):
    """Sends a notification via Discord"""
    notifier = Notifier(config["discord_webhook_url"])
    notifier.send(message, print_message=False)


def get_config(key, default):
    """Fetches a config item from ./config.yaml"""
    try:
        return config[key]
    except KeyError:
        return default


def fetch_resource_url(
    url, selector, url_attribute="src", timeout=DEFAULT_TIMEOUT_SECONDS
):
    """Fetches a resource URL from a webpage element given a CSS selector. Useful for 
    retrieving URLs from <script src="{resource_url}"></script> or <link href="{resource_url}/>
    """
    try:
        print(f"Fetching resource from {url}...")

        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-dev-shm-usage")
        ignored_exceptions = (StaleElementReferenceException,)
        browser = webdriver.Chrome(options=chrome_options)
        browser.get(url)

        return (
            WebDriverWait(browser, timeout, ignored_exceptions=ignored_exceptions)
            .until(ec.presence_of_element_located((By.CSS_SELECTOR, selector)))
            .get_attribute(url_attribute)
        )

    except (TimeoutException, StaleElementReferenceException, NoSuchElementException):
        print("Timed out. Retrying...")
    except WebDriverException as e:
        print(e)


def make_diff(target_name, identifier, js_url, save_path=None):
    """Generates a diff of a newer version of a JS by comparing it against an
    older version saved in the save path
    
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
    datetime_now = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
    diff_filepath = os.path.join(diff_dir, f"{datetime_now}.diff")

    download_file(js_url, raw_js_filepath)
    print(f"Downloaded {js_url}")

    try:
        with open(new_js_filepath, "w") as f:
            f.write(jsbeautifier.beautify_file(raw_js_filepath))
    except UnicodeDecodeError:
        print(f"Failed to decode JS file: {js_url}")

    if not os.path.isfile(old_js_filepath):
        shutil.copyfile(new_js_filepath, old_js_filepath)
        return

    with open(diff_filepath, "w") as diff_file:
        diff = list(
            difflib.unified_diff(
                open(old_js_filepath, "r").readlines(),
                open(new_js_filepath, "r").readlines(),
            )
        )

        if len(diff) > 0:
            for line in diff:
                diff_file.write(line)

            notify(
                f"> Detected file changes in {target_name} at \n"
                f"```{diff_filepath}```"
            )

    shutil.copyfile(new_js_filepath, old_js_filepath)


def detect_changes(target):
    """Detects changes in a target JS file"""
    import ipdb; ipdb.set_trace()
    if not target["enabled"]:
        return

    url_attribute = target["url_attribute"] if "url_attribute" in target else "src"
    resource_url = None
    while not resource_url:
        resource_url = fetch_resource_url(
            target["webpage"], target["selector"], url_attribute, config["timeout"]
        )

    save_path = get_config("save_path", DEFAULT_SAVE_PATH)
    make_diff(target["name"], target["identifier"], resource_url, save_path=save_path)

def group_targets(targets):
    """Groups targets by webpage"""
    grouped_targets = {}
    for target in targets:
        if not target["webpage"] in grouped_targets.keys():
            grouped_targets[target["webpage"]] = []
        grouped_targets[target["webpage"]].append(target)
        yield grouped_targets


def main():

    if get_config("enable_multithreading", True):
        threads = []
        for target in group_targets(config["targets"]):
            import ipdb; ipdb.set_trace()
            thread = threading.Thread(target=detect_changes, args=(target,))
            thread.start()
            threads.append(thread)
    else:
        for target in config["targets"]:
            detect_changes(target)


if __name__ == "__main__":
    main()
