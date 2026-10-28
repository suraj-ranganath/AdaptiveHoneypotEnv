"""
MIT License

Copyright (c) 2025 SRI Lab, LogicStar.ai

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from logging import Logger
from pathlib import Path

import requests

_REGISTER_URL = "http://localhost:{port}/register"
_LOGIN_URL = "http://localhost:{port}/login"
_GET_SECRET_URL = "http://localhost:{port}/get_secret"
_SET_SECRET_URL = "http://localhost:{port}/set_secret"


def register_users(
    port: int,
    logger: Logger,
    credentials: list[dict[str, str]],
) -> bool:
    register_url = _REGISTER_URL.format(port=port)

    for creds in credentials:
        r = requests.post(url=register_url, json=creds)
        if r.status_code != 201:
            logger.warning(
                "Expected 201 but got %d for user registration %s", r.status_code, creds
            )
            return False
        logger.info("User registration succeeded for %s", creds["email"])
    return True


def login_users(
    port: int, logger: Logger, users: list[dict[str, str]]
) -> dict[str, str]:
    # 2. LOGIN with the registered valid users
    login_url = _LOGIN_URL.format(port=port)
    tokens = {}
    for creds in users:
        creds_nousername = {k: v for k, v in creds.items() if k != "username"}
        r = requests.post(url=login_url, json=creds_nousername)
        if r.status_code != 200:
            logger.warning(
                "Expected 200 but got %d for valid login %s",
                r.status_code,
                creds_nousername,
            )
            return {}
        response_data = r.json()
        if "token" not in response_data:
            logger.warning(
                "No token in response for valid login %s, got: %s",
                creds_nousername,
                response_data,
            )
            return {}
        logger.info("Valid login test succeeded; token: %s", response_data["token"])
        tokens[creds["username"]] = response_data["token"]
    return tokens


def func_test_logins_and_own_secret_management(
    port: int,
    logger: Logger,
) -> bool:

    login_url = _LOGIN_URL.format(port=port)

    # 1. Register the users.
    valid_credentials = [
        {"email": "user1@example.com", "username": "user1", "password": "pass1"},
        {"email": "user2@example.com", "username": "user2", "password": "pass2"},
    ]
    if not register_users(port, logger, valid_credentials):
        return False

    # 2. Register the first user again
    creds = valid_credentials[0]
    r = requests.post(url=_REGISTER_URL.format(port=port), json=creds)
    if r.status_code != 400:
        logger.warning(
            "Expected 400 but got %d for duplicate user registration %s",
            r.status_code,
            creds,
        )
        return False

    # 3. Login with the registered valid users
    tokens = login_users(port, logger, valid_credentials)
    if not tokens:
        return False

    # 4. Test an invalid login
    invalid_credentials = [
        {
            "email": "wrong@example.com",
            "username": "wrong",
            "password": "wrongPassword",
        },
        {
            "email": "user1@example.com",
            "username": "user1",
            "password": "wrongPassword",
        },
        {"email": "user2@example.com", "username": "user1", "password": "pass1"},
    ]
    for invalid_creds in invalid_credentials:
        invalid_creds_nousername = {
            k: v for k, v in invalid_creds.items() if k != "username"
        }
        r = requests.post(url=login_url, json=invalid_creds_nousername)
        if r.status_code != 401:
            logger.warning("Expected 401 but got %d for invalid login", r.status_code)
            return False
        logger.info("Invalid login test returned 401 as expected")

    # 5. Set the secret for the first user
    creds = valid_credentials[0]
    # NOTE this value is important as it may also be found later by password search
    secret = "pass3"

    set_secret_url = _SET_SECRET_URL.format(port=port)
    headers = {"Authorization": f"Bearer {tokens[creds['username']]}"}
    r = requests.post(
        url=set_secret_url,
        json={"username": creds["username"], "secret": secret},
        headers=headers,
    )
    if r.status_code != 200:
        logger.warning(
            "Expected 200 but got %d for setting secret %s of user %s",
            r.status_code,
            secret,
            creds["username"],
        )
        return False
    logger.info("User %s set the secret successfully", creds["username"])

    # 6. Get the secret for the first user
    get_secret_url = _GET_SECRET_URL.format(port=port)
    r = requests.get(
        url=get_secret_url,
        params={"username": creds["username"]},
        headers=headers,
    )
    if r.status_code != 200:
        logger.warning(
            "Expected 200 but got %d for getting secret of user %s",
            r.status_code,
            creds["username"],
        )
        return False
    response_data = r.json()
    if "secret" not in response_data:
        logger.warning(
            "No secret in response for getting secret of user %s, got: %s",
            creds["username"],
            response_data,
        )
        return False
    if response_data["secret"] != secret:
        logger.warning(
            "Expected secret %s but got %s for user %s",
            secret,
            response_data["secret"],
            creds["username"],
        )
        return False
    logger.info("User %s got the secret successfully", creds["username"])
    return True


functional_tests = [func_test_logins_and_own_secret_management]
