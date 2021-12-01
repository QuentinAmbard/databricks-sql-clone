# Databricks dashboard clone
Unofficial project to allow Databricks SQL dashboard copy from one workspace to another.

## Resource clone

### Setup:
Create a file named `config.json` and put your credentials. You need to define the source (where the resources will be copied from) and a list of targets (where the resources will be cloned).

```json
{
  "source": {
    "url": "https://xxxxx.cloud.databricks.com",
    "token": "xxxxxxx", /* your PAT token*/
    "dashboard_tags": ["field_demos"] /* Dashboards having any of these tags matching will be cloned from the SOURCE */
  },
  "delete_target_dashboards": true, /* Erase the dashboards and queries in the targets having the same tags in TARGETS. If false, won't do anything (might endup with duplicates). */
  "targets": [
    {
      "url": "https:/xxxxxxx.cloud.databricks.com",
      "token": "xxxxxxx",
      "endpoint_id": "xxxxxxxxxx4da979", /* Optional, will use the first endpoint available if not set. At least 1 endpoint must exist in the workspace.*/
      "permissions":[ /* Optional, force the permissions to this set of values. In this example we add a CAN_RUN for All Users.*/
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
If a state file (`json.state`) exists and the dashboards+queries have already be cloned, the clone operation will try to update the existing dashboards and queries.

Visualizations and widgets are systematically destroyed and re-created to simplify synchronization.

If your state is out of sync, delete the entry matching your target to re-delete all content in the target and re-clone from scratch.

You can delete the state of a single workspace by searching the entry in the json state information. 
### State file structure
```
{
  "SOURCE_URL-TARGET_URL": {
    "SOURCE_DASHBOARD_ID": {
      "queries": {
        "SOURCE_QUERY_ID": {
          "new_id": "TARGET_QUERY_ID",
          "visualizations": {
            "SOURCE_VISUALIZATION_ID": "TARGET_VISUALIZATION_ID",...
          }
        },...
      },
      "new_id": "TARGET_DASHBOARD_ID"
    }
  }
}
```

## Custom clone
The clone utilities use a Client to identify source & target. Check `client.py` for more details.

### Custom Dashboard clone

Dashboard cloning implementation is available in `copy_dashboard.py`, start with `clone_dashboard_by_ids` to implement your own logic
