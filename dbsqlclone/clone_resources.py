import argparse
from .utils import clone_dashboard
from .utils.client import Client
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

try:
    with open("state.json", "r") as r:
        state = json.loads(r.read())
except:
    print("state isn't available, create an empty one")
    state = {}

clone_dashboard.delete_queries(target_clients[0], "")

for target_client in target_clients:
    clone_dashboard.set_data_source_id_from_endpoint_id(target_client)
    clone_dashboard.delete_and_clone_dashboards_with_tags(source_client, target_client, source_client.dashboard_tags,
                                                         delete_target_dashboards, state)
