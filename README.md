# tap-yotpo

This is a [Singer](https://singer.io) tap that produces JSON-formatted data
following the [Singer spec](https://github.com/singer-io/getting-started/blob/master/SPEC.md).

This tap:

- Pulls raw data from [Yotpo](http://apidocs.yotpo.com/reference)
- Extracts the following resources:
  - [products](http://apidocs.yotpo.com/reference#draft-retrieve-all-products)
  - [reviews](http://apidocs.yotpo.com/reference#retrieve-all-reviews)
  - [emails](http://apidocs.yotpo.com/reference#raw-data)
  - [unsubscribers](http://apidocs.yotpo.com/reference#retrieve-a-list-of-unsubscribers)
  - [product_reviews](http://apidocs.yotpo.com/reference#retrieve-reviews-for-a-specific-product)
- Outputs the schema for each resource

## Quick Start

1. Install

    pip install tap-yotpo

2. Get an API key

    You can find your `api_key` and `api_secret` in your Yotpo settings.


3. Create the config file

   You must create a JSON configuration file that looks like this:

   ```json
   {
       "start_date": "2015-01-01",
       "api_key": "...",
       "api_secret": "...",
       "email_stats_lookback_days": 30
   }
   ```

   The `start_date` parameter determines the starting date for incremental syncs. The `email_stats_lookback_days` parameter
   is used to fetch updated email statistics (opens, clicks, etc) for emails sent by Yotpo.

4. Run the Tap in Discovery Mode

    tap-yotpo -c config.json -d

   See the Singer docs on discovery mode
   [here](https://github.com/singer-io/getting-started/blob/master/BEST_PRACTICES.md#discover-mode-and-connection-checks).

5. Run the Tap in Sync Mode

    tap-yotpo -c config.json -p catalog-file.json

---

Copyright &copy; 2017 Fishtown Analytics
