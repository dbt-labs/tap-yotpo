import singer
from singer import metrics
from singer.transform import transform as tform
from .transform import transform_dts
import pendulum # TODO

LOGGER = singer.get_logger()


class Stream(object):
    def __init__(self, tap_stream_id, pk_fields, path,
                 returns_collection=True,
                 collection_key=None,
                 pluck_results=False,
                 custom_formatter=None,
                 version=None):
        self.tap_stream_id = tap_stream_id
        self.pk_fields = pk_fields
        self.path = path
        self.returns_collection = returns_collection
        self.collection_key = collection_key
        self.pluck_results = pluck_results
        self.custom_formatter = custom_formatter or (lambda x: x)
        self.version = version

    def metrics(self, records):
        with metrics.record_counter(self.tap_stream_id) as counter:
            counter.increment(len(records))

    def write_records(self, records):
        singer.write_records(self.tap_stream_id, records)
        self.metrics(records)

    def format_response(self, response):
        if self.pluck_results:
            response = response['response']

        if self.returns_collection:
            if self.collection_key:
                records = (response or {}).get(self.collection_key, [])
            else:
                records = response or []
        else:
            records = [] if not response else [response]
        return self.custom_formatter(records)

    def transform_dts(self, ctx, records):
        return transform_dts(records, ctx.schema_dt_paths[self.tap_stream_id])


PAGE_SIZE = 100
EMAILS_PAGE_SIZE = 1000
EMAILS_LOOKBACK_DAYS = 30

class Paginated(Stream):
    def get_params(self, ctx, page):
        return {
            "count": PAGE_SIZE,
            "page": page
        }

    def on_batch_complete(self, ctx, records):
        self.write_records(records)

    def _sync(self, ctx, path=None):
        if path is None:
            path = self.path

        ctx.update_start_date_bookmark([self.tap_stream_id, 'since_date'])

        page = 1
        while True:
            params = self.get_params(ctx, page)
            resp = ctx.client.GET(self.version, {"path": path, "params": params}, self.tap_stream_id)
            records = self.format_response(resp)
            self.on_batch_complete(ctx, records)
            if len(records) == 0:
                break
            page += 1

    def sync(self, ctx):
        self._sync(ctx)

    def _transform_dt(self, time_str):
        return pendulum.parse(time_str).in_timezone("UTC")

    def update_bookmark(self, ctx, max_record_ts, path_key):
        path = [self.tap_stream_id, path_key]
        bookmark_ts = self._transform_dt(ctx.get_bookmark(path))

        last_record_ts = self._transform_dt(max_record_ts)

        if last_record_ts > bookmark_ts:
            ctx.set_bookmark(path, last_record_ts.to_date_string())

class Products(Paginated):
    def on_batch_complete(self, ctx, records):
        ctx.cache["products"].extend(records)

    def sync(self, ctx):
        self.write_records(ctx.cache["products"])

    def fetch_into_cache(self, ctx):
        ctx.cache["products"] = []
        self._sync(ctx)


class Reviews(Paginated):
    def get_params(self, ctx, page):
        since_date = ctx.get_bookmark([self.tap_stream_id, 'since_date'])
        return {
            "count": PAGE_SIZE,
            "page": page,
            "since_date": since_date
        }

    def on_batch_complete(self, ctx, records):
        self.write_records(records)

        if len(records) == 0:
            return

        last_record = records[-1]
        max_record_ts = last_record['created_at']
        self.update_bookmark(ctx, max_record_ts, 'since_date')


class Emails(Paginated):
    def get_params(self, ctx, page):
        since_date_raw = ctx.get_bookmark([self.tap_stream_id, 'since_date'])

        lookback_days = ctx.config.get('email_stats_lookback_days', EMAILS_LOOKBACK_DAYS)
        since_date = pendulum.parse(since_date_raw).in_timezone("UTC").add(days=-lookback_days)
        until_date = pendulum.tomorrow().in_timezone("UTC")

        return {
            "per_page": EMAILS_PAGE_SIZE,
            "page": page,
            "since": since_date.to_date_string(),
            "until": until_date.to_date_string(),
            "sort": "ascending"
        }

    def on_batch_complete(self, ctx, records):
        self.write_records(records)

        if len(records) == 0:
            return

        last_record = records[-1]
        max_record_ts = last_record['email_sent_timestamp']
        self.update_bookmark(ctx, max_record_ts, 'since_date')


class ProductReviews(Paginated):
    def get_params(self, ctx, page):
        # This endpoint does not support date filtering
        return {
            "per_page": PAGE_SIZE,
            "page": page,
            "sort": ["date", "time"],
            "direction": "ascending"
        }

    def sync(self, ctx):
        for product in ctx.cache['products']:
            path = self.path.format(product_id=product['external_product_id'])
            self._sync(ctx, path)


products = Products("products", ["id"], "apps/:api_key/products?utoken=:token", collection_key='products', version='v1')
all_streams = [
    products,
    Paginated("unsubscribers", ["id"], "apps/:api_key/unsubscribers?utoken=:token", collection_key='unsubscribers', pluck_results=True),
    Reviews("reviews", ["id"], "apps/:api_key/reviews?utoken=:token", collection_key="reviews", version='v1'),
    Emails("emails", ["email_address", "email_sent_timestamp"], "analytics/v1/emails/:api_key/export/raw_data?token=:token", collection_key="records"),
    ProductReviews("product_reviews", ["id"], "widget/:api_key/products/{product_id}/reviews.json", collection_key="reviews", version='v1', pluck_results=True)
]
all_stream_ids = [s.tap_stream_id for s in all_streams]
