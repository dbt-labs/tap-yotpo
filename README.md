# tap-yotpo

This is a [Singer](https://singer.io) tap that produces JSON-formatted data
following the [Singer
spec](https://github.com/singer-io/getting-started/blob/master/SPEC.md).

This tap:

- Pulls raw data from [Yotpo](http://apidocs.yotpo.com/reference)
- Extracts the following resources:
  - TODO
- Outputs the schema for each resource

## Quick Start

1. Install

    pip install tap-yotpo

2. Get an API key


3. Create the config file

   You must create a JSON configuration file that looks like this:

   ```json
   {
     ...
   }
   ```

4. Run the Tap in Discovery Mode

    tap-yotpo -c config.json -d

   See the Singer docs on discovery mode
   [here](https://github.com/singer-io/getting-started/blob/master/BEST_PRACTICES.md#discover-mode-and-connection-checks).

5. Run the Tap in Sync Mode

    tap-yotpo -c config.json -p catalog-file.json

---

Copyright &copy; 2017 Fishtown Analytics
