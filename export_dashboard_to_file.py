import argparse
from utils import clone_dashboard
from utils.client import Client
from utils.dump_dashboard import dump_dashboard
import json


def get_client(config_file):
    with open(config_file, "r") as r:
        config = json.loads(r.read())
        source = Client(config["source"]["url"], config["source"]["token"],
                        dashboard_tags=config["source"]["dashboard_tags"])
        return source,  config["dashboard_id"],  config["dashboard_folder"]


parser = argparse.ArgumentParser()
parser.add_argument("--config_file", default="config_export.json", required=False,
                    help="configuration file containing credential and dashboard to clone")
parser.add_argument("--state_file", default="state.json", required=False,
                    help="state containing the links between the already cloned dashboard. Used to update resources")
args = parser.parse_args()
source_client,dashboard_id_to_save,dashboard_folder_to_save  = get_client(args.config_file)
dump_dashboard(source_client,dashboard_id_to_save,dashboard_folder_to_save)
