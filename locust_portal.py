
import os

from locust import HttpUser, between, task


class HMSPortalUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        session_cookie = os.environ.get("HMS_TEST_SESSION")
        if not session_cookie:
            raise RuntimeError(
                "Set HMS_TEST_SESSION to a fresh local test session cookie."
            )

        self.client.cookies.set(
            "sessionid",
            session_cookie,
            domain="127.0.0.1",
            path="/",
        )

    @task(3)
    def resident_search(self):
        with self.client.get(
            "/residents/?q=aar",
            name="/residents/ [search]",
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Expected HTTP 200; got {response.status_code}"
                )

    @task(1)
    def rooms_list(self):
        with self.client.get(
            "/rooms/",
            name="/rooms/",
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Expected HTTP 200; got {response.status_code}"
                )
