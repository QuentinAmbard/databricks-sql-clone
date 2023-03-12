import argparse
from dbsqlclone.utils import load_dashboard
from dbsqlclone.utils import dump_dashboard
from dbsqlclone.utils import clone_dashboard
from dbsqlclone.utils.client import Client
import json


def get_client(config_file):
    with open(config_file, "r") as r:
        config = json.loads(r.read())
        source = Client(config["source"]["url"], config["source"]["token"],
                        dashboard_tags=config["source"]["dashboard_tags"])
        targets = []
        for target in config["targets"]:
            client = Client(target["url"], target["token"], permissions=target["permissions"])
            if "endpoint_id" in target:
                client.endpoint_id = target["endpoint_id"]
            targets.append(client)
        return source, targets, config["delete_target_dashboards"]


parser = argparse.ArgumentParser()
parser.add_argument("--config_file", default="config.json", required=False,
                    help="configuration file containing credential and dashboard to clone")
parser.add_argument("--state_file", default="state.json", required=False,
                    help="state containing the links between the already cloned dashboard. Used to update resources")
args = parser.parse_args()

source_client, target_clients, delete_target_dashboards = get_client(args.config_file)

dashboard_to_clone = "1a83e520-bcd4-4271-a2a3-9544ae06430e"

target_client = target_clients[0]

import logging
logging.basicConfig()
load_dashboard.logger.setLevel(logging.DEBUG)

dashboard_def = dump_dashboard.get_dashboard_definition_by_id(source_client, dashboard_to_clone)
#print(dashboard_def)
#To recreate a new dashboard
#with open(f"test/{dashboard_to_clone}.json", "r") as r:
#    dashboard_def = json.loads(r.read())

#target_client.data_source_id = "aa143a10-aad0-41a3-a7bd-9158962b4d2c"
target_client.endpoint_id = "dcc40c6f1a1d3a58"
clone_dashboard.set_data_source_id_from_endpoint_id(target_client)
print(target_client.data_source_id)
existing_id = "9fc6a3bb-ff36-4e06-b5f9-912d7e77dc05"
state = load_dashboard.clone_dashboard_without_saved_state(dashboard_def, target_client, existing_id)
#state = load_dashboard.clone_dashboard(dashboard_def, target_client)
from dbsqlclone.utils import load_dashboard
load_dashboard.max_workers = 2
print(state)
assert state['new_id'] == existing_id
#load_dashboard.clone_dashboard(dashboard_def, target_client, {}, None)


