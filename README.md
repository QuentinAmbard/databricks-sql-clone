# Databricks dashboard clone
Unofficial project to allow Databricks SQL dashboard copy from one workspace to another.

## Resource clone

### Setup:
Create a file named `config.json` and put your credential. You need to define the source (where the resources will be copied from) and a list of targets (where the resources will be cloned).

```json
{
  "source": {
    "url": "https://xxxxx.cloud.databricks.com",
    "token": "xxxxxxx", /* your PAT token*/
    "dashboard_tags": ["field_demos"] /* Dashboards having any of these tags matching will be first DELETED from the targets and then cloned from the SOURCE */
  },
  "delete_target_dashboards": true, /* erase the dashboards in the targets having the same tags. If false, won't do anything (might endup with duplicates). */
  "targets": [
    {
      "url": "https:/xxxxxxx.cloud.databricks.com",
      "token": "xxxxxxx",
      "endpoint_id": "xxxxxxxxxx4da979", /* Optional, will use the first endpoint available if not set. At least 1 endpoint must exist in the workspace.*/
      "permissions":[ /* Optional, force the permissions to this set of values. In this example add a CAN_RUN for All Users.*/
        {
          "user_name": "xxx@xxx.com",
          "permission_level": "CAN_MANAGE"
        },
        {
          "group_name": "users",
          "permission_level": "CAN_RUN"
        }
      ]
    },
    {
      "url": "https://xxxxxxx.azuredatabricks.net",
      "token": "xxxxxxx"
    }
  ]
}
```

`endpoint_id` the ID of the endpoint we'll attach to the queries.

To find your `endpoint_id` on each target workspace, click in one of your endpoint.
The endpoint ID is in the URL: `https://xxxx.azuredatabricks.net/sql/endpoints/<endpoint_id>?o=xxxx`

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

If you need to copy without deleting, set `delete_target_dashboards` to false.


