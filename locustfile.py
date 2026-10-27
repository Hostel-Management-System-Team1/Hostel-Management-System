
import csv
import itertools
import re
from html import unescape
from pathlib import Path

import pyotp
from locust import HttpUser, between, task

PROJECT_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = PROJECT_DIR / "locust_users.csv"


def load_credentials():
    if not CREDENTIALS_FILE.is_file():
        raise RuntimeError(
            f"Credentials file not found: {CREDENTIALS_FILE}"
        )

    with CREDENTIALS_FILE.open(
        newline="", encoding="utf-8"
    ) as file:
        reader = csv.DictReader(file)
        required = {"username", "password", "totp_secret"}

        if not reader.fieldnames or not required.issubset(
            reader.fieldnames
        ):
            raise RuntimeError(
                "CSV must contain username, password, totp_secret."
            )

        users = list(reader)

    if not users:
        raise RuntimeError("No performance accounts found.")

    usernames = [user["username"] for user in users]

    if len(set(usernames)) != len(usernames):
        raise RuntimeError("Duplicate usernames in credentials file.")

    if any(
        not user.get("username")
        or not user.get("password")
        or not user.get("totp_secret")
        for user in users
    ):
        raise RuntimeError("A credential row contains an empty field.")

    return users


CREDENTIALS = load_credentials()
ACCOUNT_COUNTER = itertools.count()


def csrf_token(response):
    # Supports either attribute order and either quote style.
    match = re.search(
        r"""<input\b(?=[^>]*\bname=["']csrfmiddlewaretoken["'])"""
        r"""(?=[^>]*\bvalue=["']([^"']+)["'])[^>]*>""",
        response.text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    # Fallback for standard Django CSRF input markup.
    match = re.search(
        r"""name=["']csrfmiddlewaretoken["']\s+value=["']([^"']+)""",
        response.text,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def safe_response_excerpt(response):
    """Return a short diagnostic without exposing form secrets."""
    text = re.sub(r"<script\b.*?</script>", " ", response.text,
                  flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text,
                  flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = " ".join(text.split())

    # Avoid printing any hidden CSRF field or credentials.
    return text[:500]


class HMSWardenUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.authenticated = False

        account_index = next(ACCOUNT_COUNTER)
        if account_index >= len(CREDENTIALS):
            print("No unused test account available for this user.")
            return

        account = CREDENTIALS[account_index]
        self.username = account["username"]

        response = self.client.get(
            "/accounts/login/",
            name="/accounts/login/ [GET]",
            allow_redirects=False,
        )
        token = csrf_token(response)

        if response.status_code != 200 or not token:
            print(
                f"{self.username}: login form/CSRF failed "
                f"(HTTP {response.status_code})"
            )
            return

        response = self.client.post(
            "/accounts/login/",
            data={
                "username": account["username"],
                "password": account["password"],
                "csrfmiddlewaretoken": token,
                "next": "",
            },
            headers={"Referer": self.host + "/accounts/login/"},
            name="/accounts/login/ [POST]",
            allow_redirects=False,
        )

        if response.status_code not in (302, 303):
            print(
                f"{self.username}: password login failed "
                f"(HTTP {response.status_code}); "
                f"response: {safe_response_excerpt(response)}"
            )
            return

        response = self.client.get(
            "/accounts/mfa/",
            name="/accounts/mfa/ [GET]",
            allow_redirects=False,
        )
        token = csrf_token(response)

        if response.status_code != 200 or not token:
            print(
                f"{self.username}: MFA form/CSRF failed "
                f"(HTTP {response.status_code})"
            )
            return

        try:
            code = pyotp.TOTP(account["totp_secret"]).now()
        except (ValueError, TypeError) as exc:
            print(f"{self.username}: invalid TOTP secret ({exc})")
            return

        response = self.client.post(
            "/accounts/mfa/",
            data={
                "token": code,
                "csrfmiddlewaretoken": token,
                "next": "",
            },
            headers={"Referer": self.host + "/accounts/mfa/"},
            name="/accounts/mfa/ [POST]",
            allow_redirects=False,
        )

        self.authenticated = response.status_code in (302, 303)

        if self.authenticated:
            print(f"{self.username}: authentication successful")
        else:
            print(
                f"{self.username}: MFA verification failed "
                f"(HTTP {response.status_code}); "
                f"response: {safe_response_excerpt(response)}"
            )

    @task(3)
    def resident_search(self):
        if not self.authenticated:
            return

        with self.client.get(
            "/residents/?q=aar",
            name="/residents/ [search]",
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Expected HTTP 200, got {response.status_code}"
                )

    @task(1)
    def rooms_list(self):
        if not self.authenticated:
            return

        with self.client.get(
            "/rooms/",
            name="/rooms/",
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Expected HTTP 200, got {response.status_code}"
                )
