import requests
import singer
from singer import metrics
import backoff

LOGGER = singer.get_logger()

AUTH_URL = "https://api.yotpo.com/oauth/token"
BASE_URL = "https://api.yotpo.com"
BASE_URL_V1 = "https://api.yotpo.com/v1"

GRANT_TYPE = "client_credentials"


class RateLimitException(Exception):
    pass


def _join(a, b):
    return a.rstrip("/") + "/" + b.lstrip("/")


class Client(object):
    def __init__(self, config):
        self.user_agent = config.get("user_agent")
        self.api_key = config.get("api_key")
        self.api_secret = config.get("api_secret")
        self.session = requests.Session()
        self.base_url = BASE_URL
        self._token = None

    @property
    def token(self):
        if self._token is None:
            raise RuntimeError("Client is not yet authenticated")
        return self._token

    def prepare_and_send(self, request):
        if self.user_agent:
            request.headers["User-Agent"] = self.user_agent
        return self.session.send(request.prepare())

    def url(self, version, raw_path):
        path = raw_path \
                .replace(":api_key", self.api_key) \
                .replace(":token", self.token)

        if version == 'v1':
            return _join(BASE_URL_V1, path)
        else:
            return _join(BASE_URL, path)

    def create_get_request(self, version, path, **kwargs):
        return requests.Request(method="GET",
                                url=self.url(version, path),
                                **kwargs)

    @backoff.on_exception(backoff.expo,
                          RateLimitException,
                          max_tries=10,
                          factor=2)
    def request_with_handling(self, request, tap_stream_id):
        with metrics.http_request_timer(tap_stream_id) as timer:
            response = self.prepare_and_send(request)
            timer.tags[metrics.Tag.http_status_code] = response.status_code
        if response.status_code in [429, 503, 504]:
            raise RateLimitException()
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def authenticate(self):
        auth_body = {
            "client_id": self.api_key,
            "client_secret": self.api_secret,
            "grant_type": GRANT_TYPE
        }

        request = requests.Request(method="POST", url=AUTH_URL, data=auth_body)
        response = self.prepare_and_send(request)
        response.raise_for_status()
        data = response.json()
        self._token = data['access_token']

    def GET(self, version, request_kwargs, *args, **kwargs):
        req = self.create_get_request(version, **request_kwargs)
        return self.request_with_handling(req, *args, **kwargs)
