# ***Archival Notice***
This repository has been archived.

As a result all of its historical issues and PRs have been closed.

Please *do not clone* this repo without understanding the risk in doing so:
- It may have unaddressed security vulnerabilities
- It may have unaddressed bugs

<details>
   <summary>Click for historical readme</summary>

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

**Note:** The `product_reviews` endpoint is similar to the `reviews` endpoint, but also contains custom fields specified for your Yotpo integration. Consider disabling this endpoint if you do not have or need custom fields in the output of this integration.

## Quick Start

1. Install

    ```bash
    $ pip install tap-yotpo
    ```

2. Get an API key

    You can find your `api_key` and `api_secret` in your Yotpo settings.


3. Create the config file

   You must create a JSON configuration file that looks like this:

   ```json
   {
       &quot;start_date&quot;: &quot;2015-01-01&quot;,
       &quot;api_key&quot;: &quot;...&quot;,
       &quot;api_secret&quot;: &quot;...&quot;,
       &quot;email_stats_lookback_days&quot;: 30,
       &quot;reviews_lookback_days&quot;: 30
   }
   ```

   The `start_date` parameter determines the starting date for incremental syncs. The `email_stats_lookback_days` parameter
   is used to fetch updated email statistics (opens, clicks, etc) for emails sent by Yotpo. The `reviews_lookback_days`
   parameter is used to re-fetch reviews that have been updated (or deleted) since the last time they were synced.

4. Run the Tap in Discovery Mode

    ```bash
    $ tap-yotpo -c config.json -d
    ```

   See the Singer docs on discovery mode
   [here](https://github.com/singer-io/getting-started/blob/master/BEST_PRACTICES.md#discover-mode-and-connection-checks).

5. Run the Tap in Sync Mode

    ```bash
    $ tap-yotpo -c config.json -p catalog-file.json
    ```

---

Copyright &amp;copy; 2017 Fishtown Analytics

