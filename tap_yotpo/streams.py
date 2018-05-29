import singer
from singer import metrics, transform
import pendulum

LOGGER = singer.get_logger()


PAGE_SIZE = 100
EMAILS_PAGE_SIZE = 1000
EMAILS_LOOKBACK_DAYS = 30
REVIEWS_LOOKBACK_DAYS = 30


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

        self.start_date = None

    def get_start_date(self, ctx, key):
        if not self.start_date:
            self.start_date = ctx.get_bookmark([self.tap_stream_id, key])
        return self.start_date

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


class Paginated(Stream):
    def get_params(self, ctx, page):
        return {
            "count": PAGE_SIZE,
            "page": page
        }

    def on_batch_complete(self, ctx, records, product_id=None):
        self.write_records(records)
        return True

    def _sync(self, ctx, path=None, product_id=None):
        if path is None:
            path = self.path

        if product_id:
            bookmark_name = 'product_{}.since_date'.format(product_id)
        else:
            bookmark_name = 'since_date'
        ctx.update_start_date_bookmark([self.tap_stream_id, bookmark_name])

        schema = ctx.catalog.get_stream(self.tap_stream_id).schema.to_dict()

        page = 1
        while True:
            params = self.get_params(ctx, page)
            opts = {"path": path, "params": params}
            resp = ctx.client.GET(self.version, opts, self.tap_stream_id)
            raw_records = self.format_response(resp)
            records = [transform(record, schema) for record in raw_records]

            if not self.on_batch_complete(ctx, records, product_id):
                break

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
    def on_batch_complete(self, ctx, records, product_id=None):
        ctx.cache["products"].extend(records)
        return True

    def sync(self, ctx):
        self.write_records(ctx.cache["products"])

    def fetch_into_cache(self, ctx):
        ctx.cache["products"] = []
        self._sync(ctx)


class Reviews(Paginated):
    def get_params(self, ctx, page):
        since_date_raw = self.get_start_date(ctx, 'since_date')
        lookback_days = ctx.config.get('reviews_lookback_days',
                                       REVIEWS_LOOKBACK_DAYS)
        since_date = pendulum.parse(since_date_raw) \
                             .in_timezone("UTC") \
                             .add(days=-lookback_days)

        return {
            "count": PAGE_SIZE,
            "page": page,
            "since_date": since_date.to_iso8601_string(),
            "deleted": "true"
        }

    def on_batch_complete(self, ctx, records, product_id=None):
        self.write_records(records)

        if len(records) == 0:
            return False

        last_record = records[-1]
        max_record_ts = last_record['created_at']
        self.update_bookmark(ctx, max_record_ts, 'since_date')

        return True


class Emails(Paginated):
    def get_params(self, ctx, page):
        since_date_raw = self.get_start_date(ctx, 'since_date')

        lookback_days = ctx.config.get('email_stats_lookback_days',
                                       EMAILS_LOOKBACK_DAYS)

        since_date = pendulum.parse(since_date_raw) \
                             .in_timezone("UTC") \
                             .add(days=-lookback_days)

        until_date = pendulum.tomorrow().in_timezone("UTC")

        return {
            "per_page": EMAILS_PAGE_SIZE,
            "page": page,
            "since": since_date.to_date_string(),
            "until": until_date.to_date_string(),
            "sort": "ascending"
        }

    def on_batch_complete(self, ctx, records, product_id=None):
        self.write_records(records)

        if len(records) == 0:
            return False

        last_record = records[-1]
        max_record_ts = last_record['email_sent_timestamp']
        self.update_bookmark(ctx, max_record_ts, 'since_date')

        return True


class ProductReviews(Paginated):
    def get_params(self, ctx, page):
        # This endpoint does not support date filtering
        # Start at the beginning of time, and only sync
        # records that are more recent than our bookmark
        return {
            "per_page": PAGE_SIZE,
            "page": page,
            "sort": ["date", "time"],
            "direction": "asc"
        }

    def sync(self, ctx):
        for product in ctx.cache['products']:
            product_id = product['external_product_id']
            path = self.path.format(product_id=product_id)
            self._sync(ctx, path, product_id=product_id)

    def on_batch_complete(self, ctx, records, product_id=None):
        if len(records) == 0:
            return False

        bookmark_name = 'product_{}.since_date'.format(product_id)

        offset = ctx.get_bookmark([self.tap_stream_id, bookmark_name])
        current_bookmark = pendulum.parse(offset).in_timezone("UTC")

        last_record = records[-1]
        max_record_ts = pendulum.parse(last_record['created_at'])

        # if latest in batch is more recent than the current bookmark,
        # update the bookmark and write out the record
        if max_record_ts >= current_bookmark:
            self.write_records(records)
            self.update_bookmark(ctx, max_record_ts.to_date_string(),
                                 bookmark_name)
            LOGGER.info("Sending batch. Max Record {} is >= bookmark "
                        "{}".format(max_record_ts, current_bookmark))
        else:
            LOGGER.info("Skipping batch. Max Record {} is less than bookmark "
                        "{}".format(max_record_ts, current_bookmark))

        return True


products = Products(
        "products",
        ["id"],
        "apps/:api_key/products?utoken=:token",
        collection_key='products',
        version='v1'
)

all_streams = [
    products,

    Paginated(
        "unsubscribers",
        ["id"],
        "apps/:api_key/unsubscribers?utoken=:token",
        collection_key='unsubscribers',
        pluck_results=True
    ),

    Reviews(
        "reviews",
        ["id"],
        "apps/:api_key/reviews?utoken=:token",
        collection_key="reviews",
        version='v1'
    ),

    Emails(
        "emails",
        ["email_address", "email_sent_timestamp"],
        "analytics/v1/emails/:api_key/export/raw_data?token=:token",
        collection_key="records"
    ),

    ProductReviews(
        "product_reviews",
        ["id"],
        "widget/:api_key/products/{product_id}/reviews.json",
        collection_key="reviews",
        version='v1',
        pluck_results=True
    )
]
all_stream_ids = [s.tap_stream_id for s in all_streams]
