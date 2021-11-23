# Databricks dashboard clone
Unofficial project to allow Databricks SQL dashboard copy from one workspace to another.

## Resource clone

### Setup:
Create a file named `config.json` and put your credential. You need to define the source (where the resources will be copied from) and a list of targets (where the resources will be cloned).

```json
{
  "source": {
    "url": "https://xxxxx.cloud.databricks.com",
    "token": "xxxxxxx",
    "dashboard_tags": ["field_demos"] /* Dashboards having any of these tags matching will be deleted from target and cloned */
  },
  "delete_target_dashboards": true, /* This will erase the dashboard in the targets having the same tags. If false, won't do anything. */
  "targets": [
    {
      "url": "https:/xxxxxxx.cloud.databricks.com",
      "token": "xxxxxxx",
      "data_source_id": "xxxxxxxx-xxxx-xxxx-xxxx-a24894da3eaa"
    },
    {
      "url": "https://xxxxxxx.azuredatabricks.net",
      "token": "xxxxxxx",
      "data_source_id": "xxxxxxxx-xxxx-xxxx-xxxx-025befd8b98d"
    }
  ]
}
```
`data_source_id` is required and is the ID of the data source we'll attach to the queries/dashboard.
**This is NOT the endpoint ID that you can find in the URL**

To find your `data_source_id` on each target workspace:

- open your browser, edit an existing DBSQL query. 
- Assign the query to the SQL endpoint you want to be using
- Open the javascript console=>Network=>Filter on Fetch/XHR. 
- Click on the "Save" button of the DBSQL Query
- Open the corresponding Js query in the console 
  - click on the request "Preview"
  - search for `data_source_id`. That's the value you need to get

### Run:
Run the `clone_resources.py` script to clone all the ressources

## Dashboard update
Currently updates aren't supported, only delete & recreate. See "Handling state" for more details.

## Custom clone
The clone utilities use a Client to identify source & target. Check `client.py` for more details.
### Handling state
A state file will be used to synch data. It contains a link between the original dashboard ID / Query / Visualization and the one cloned.

In a next release this will be used to update the dashboard when already existing in the state instead of deleting it (to preserve dashboard ID and avoid breaking links).

### Custom Dashboard clone

Dashboard cloning is available in `copy_dashboard.py`.

By default, `copy_dashboard.delete_and_clone_dashboards_with_tags(source_client, dest_client, tags)` performs a DELETE on the tags matching in the target and re-create everything. It's not an UPDATE. 

It will first DELETE all the dashboard in the dest with the given tags, 
and then clone the dashboard from the source. 

If you need to copy without deleting, set `delete_target_dashboards` to true.


