# SPDX-License-Identifier: Apache-2.0
#
# http://nexb.com and https://github.com/nexB/scancode.io
# The ScanCode.io software is licensed under the Apache License version 2.0.
# Data generated with ScanCode.io is provided as-is without warranties.
# ScanCode is a trademark of nexB Inc.
#
# You may not use this software except in compliance with the License.
# You may obtain a copy of the License at: http://apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
#
# Data Generated with ScanCode.io is provided on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, either express or implied. No content created from
# ScanCode.io should be considered or used as legal advice. Consult an Attorney
# for any legal advice.
#
# ScanCode.io is a free software code scanning tool from nexB Inc. and others.
# Visit https://github.com/nexB/scancode.io for support and download.

import logging

from django.conf import settings

import requests

label = "PurlDB"
logger = logging.getLogger(__name__)
session = requests.Session()


# Only PURLDB_URL can be provided through setting
PURLDB_API_URL = None
PURLDB_URL = settings.PURLDB_URL
if PURLDB_URL:
    PURLDB_API_URL = f'{PURLDB_URL.rstrip("/")}/api/'

# Basic Authentication
PURLDB_USER = settings.PURLDB_USER
PURLDB_PASSWORD = settings.PURLDB_PASSWORD
basic_auth_enabled = PURLDB_USER and PURLDB_PASSWORD
if basic_auth_enabled:
    session.auth = (PURLDB_USER, PURLDB_PASSWORD)

# Authentication with single API key
PURLDB_API_KEY = settings.PURLDB_API_KEY
if PURLDB_API_KEY:
    session.headers.update({"Authorization": f"Token {PURLDB_API_KEY}"})

DEFAULT_TIMEOUT = 30


def is_configured():
    """Return True if the required PurlDB settings have been set."""
    if PURLDB_API_URL:
        return True
    return False


def is_available():
    """Return True if the configured PurlDB server is available."""
    if not is_configured():
        return False

    try:
        response = session.head(PURLDB_API_URL)
        response.raise_for_status()
    except requests.exceptions.RequestException as request_exception:
        logger.debug(f"{label} is_available() error: {request_exception}")
        return False

    return response.status_code == requests.codes.ok


def request_get(url, payload=None, timeout=DEFAULT_TIMEOUT):
    """Wrap the HTTP request calls on the API."""
    if not url:
        return

    params = {}
    if "format=json" not in url:
        params.update({"format": "json"})
    if payload:
        params.update(payload)

    logger.debug(f"{label}: url={url} params={params}")
    try:
        response = session.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError, TypeError) as exception:
        logger.debug(f"{label} [Exception] {exception}")


def request_post(url, data, timeout=DEFAULT_TIMEOUT):
    try:
        response = session.post(url, data=data, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError, TypeError) as exception:
        logger.debug(f"{label} [Exception] {exception}")


def collect_response_results(response, data, timeout=DEFAULT_TIMEOUT):
    """Return all results from a purldb API response."""
    results = []
    if response and response.get("count"):
        results.extend(response["results"])
        next_page = response.get("next")
        while next_page:
            response = request_post(url=next_page, data=data, timeout=timeout)
            if response and response.get("count"):
                results.extend(response["results"])
            next_page = response.get("next")
    return results


def match_packages(
    sha1_list,
    enhance_package_data=False,
    timeout=DEFAULT_TIMEOUT,
    api_url=PURLDB_API_URL,
):
    """
    Match a list of SHA1 in the PurlDB for package-type files.

    If `enhance_package_data` is True, then purldb will enhance Package data for
    matched Packages, if possible.
    """
    data = {
        "sha1": sha1_list,
        "enhance_package_data": enhance_package_data,
    }
    response = request_post(
        url=f"{api_url}packages/filter_by_checksums/", data=data, timeout=timeout
    )

    packages = collect_response_results(response, data=data, timeout=timeout)
    return packages


def match_resources(sha1_list, timeout=DEFAULT_TIMEOUT, api_url=PURLDB_API_URL):
    """Match a list of SHA1 in the PurlDB for resource files."""
    data = {"sha1": sha1_list}
    response = request_post(
        url=f"{api_url}resources/filter_by_checksums/", data=data, timeout=timeout
    )

    resources = collect_response_results(response, data=data, timeout=timeout)
    return resources


def match_directory(fingerprint, timeout=DEFAULT_TIMEOUT, api_url=PURLDB_API_URL):
    """
    Match directory content fingerprint in the PurlDB for a single directory
    resource.
    """
    payload = {"fingerprint": fingerprint}
    response = request_get(
        url=f"{api_url}approximate_directory_content_index/match/",
        payload=payload,
        timeout=timeout,
    )

    if response and len(response) > 0:
        return response


def submit_purls(purls, timeout=DEFAULT_TIMEOUT, api_url=PURLDB_API_URL):
    """Submit list PURLs to PurlDB for indexing."""
    payload = {"package_urls": purls}
    response = request_post(
        url=f"{api_url}packages/index_packages/", data=payload, timeout=timeout
    )

    return response
