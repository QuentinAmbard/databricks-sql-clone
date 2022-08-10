import argparse
from utils import clone_dashboard
from utils.load_dashboard import load_dashboard
from utils.client import Client
import json


def get_client(config_file):
    with open(config_file, "r") as r:
        config = json.loads(r.read())
        targets = []
        for target in config["targets"]:
            client = Client(target["url"], target["token"], permissions=target["permissions"])
            if "endpoint_id" in target:
                client.endpoint_id = target["endpoint_id"]
            if "sql_database_name" in target:
                client.sql_database_name = target["sql_database_name"]
            targets.append(client)
        return  targets,config["dashboard_id"],  config["dashboard_folder"]


parser = argparse.ArgumentParser()
parser.add_argument("--config_file", default="config_import.json", required=False,
                    help="configuration file containing credential and dashboard to clone")
parser.add_argument("--state_file", default="state.json", required=False,
                    help="state containing the links between the already cloned dashboard. Used to update resources")
args = parser.parse_args()

target_clients, dashboard_id_to_load,dashboard_folder  = get_client(args.config_file)
workspace_state = {}
load_dashboard(target_clients[0], dashboard_id_to_load, workspace_state, dashboard_folder)
                                                         
