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

dashboard_to_clone = "048c6d42-ad56-4667-ada1-e35f80164248"

target_client = target_clients[0]


#dashboard_def = dump_dashboard.get_dashboard_definition_by_id(source_client, dashboard_to_clone)
#print(dashboard_def)
#To recreate a new dashboard
with open("test/19394330-2274-4b4b-90ce-d415a7ff2130.json", "r") as r:
    dashboard_def = json.loads(r.read())

target_client.endpoint_id = "af7c852cda9c4198"
#clone_dashboard.set_data_source_id_from_endpoint_id(target_client)
existing_id = "19394330-2274-4b4b-90ce-d415a7ff2130"
state = load_dashboard.clone_dashboard_without_saved_state(dashboard_def, target_client, existing_id)
print(state)
assert state['new_id'] == existing_id
#load_dashboard.clone_dashboard(dashboard_def, target_client, {}, None)


