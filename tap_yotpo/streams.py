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

class Paginated(Stream):
    def get_params(self, ctx, page):
        return {
            "count": PAGE_SIZE,
            "page": page
        }

    def on_batch_complete(self, ctx, records):
        self.write_records(records)

    def sync(self, ctx):
        ctx.update_start_date_bookmark([self.tap_stream_id, 'since_date'])

        page = 1
        while True:
            params = self.get_params(ctx, page)
            resp = ctx.client.GET(self.version, {"path": self.path, "params": params}, self.tap_stream_id)
            records = self.format_response(resp)
            self.on_batch_complete(ctx, records)
            if len(records) == 0:
                break
            page += 1

class FilterablePaginated(Paginated):
    def get_params(self, ctx, page):
        since_date = ctx.get_bookmark([self.tap_stream_id, 'since_date'])
        return {
            "count": PAGE_SIZE,
            "page": page,
            "since_date": since_date
        }

    def _transform_dt(self, time_str):
        return pendulum.parse(time_str).in_timezone("UTC")

    def on_batch_complete(self, ctx, records):
        self.write_records(records)

        path = [self.tap_stream_id, 'since_date']
        bookmark_ts = self._transform_dt(ctx.get_bookmark(path))

        if len(records) == 0:
            return

        max_batch_ts = max([self._transform_dt(r['created_at']) for r in records])
        if max_batch_ts > bookmark_ts:
            ctx.set_bookmark(path, max_batch_ts.to_date_string())

class Emails(Paginated):
    def get_params(self, ctx, page):
        since_date_raw = ctx.get_bookmark([self.tap_stream_id, 'since_date'])

        # Look back one month to grab opens, clicks, etc
        since_date = pendulum.parse(since_date_raw).in_timezone("UTC").add(months=-1)
        until_date = pendulum.tomorrow().in_timezone("UTC")

        return {
            "per_page": EMAILS_PAGE_SIZE,
            "page": page,
            "since": since_date.to_date_string(),
            "until": until_date.to_date_string(),
            "sort": "ascending"
        }



def _get_response(records):
    return records['response']

all_streams = [
    Paginated("products", ["id"], "apps/:api_key/products?utoken=:token", collection_key='products', version='v1'),
    Paginated("unsubscribers", ["id"], "apps/:api_key/unsubscribers?utoken=:token", collection_key='unsubscribers', pluck_results=True),
    FilterablePaginated("reviews", ["id"], "apps/:api_key/reviews?utoken=:token", collection_key="reviews", version='v1'),
    Emails("emails", ["email_address", "email_sent_timestamp"], "analytics/v1/emails/:api_key/export/raw_data?token=:token", collection_key="records")

]
all_stream_ids = [s.tap_stream_id for s in all_streams]
