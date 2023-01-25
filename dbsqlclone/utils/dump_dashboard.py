import requests
from .client import Client
import json
from concurrent.futures import ThreadPoolExecutor
import collections
import os
import logging

logger = logging.getLogger('dbsqlclone.dump')


def dump_dashboards(source_client: Client, dashboard_ids):
    params = [(source_client, id) for id in dashboard_ids]
    with ThreadPoolExecutor(max_workers=10) as executor:
        collections.deque(executor.map(lambda args, f=dump_dashboard: f(*args), params))

def dump_dashboard(source_client: Client, dashboard_id, folder_prefix="./dashboards/"):
    dashboard = get_dashboard_definition_by_id(source_client, dashboard_id)
    if not folder_prefix.endswith("/"):
        folder_prefix += "/"
    if not os.path.exists(folder_prefix):
        os.makedirs(folder_prefix)
    with open(f'{folder_prefix}dashboard-{dashboard_id}.json', 'w') as file:
        file.write(json.dumps(dashboard, indent=4, sort_keys=True))

def get_dashboard_definition_by_id(source_client: Client, dashboard_id):
    logger.debug(f"getting dashboard definition from {dashboard_id}...")
    result = {"queries": [], "id": dashboard_id}
    dashboard = requests.get(source_client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_id, headers = source_client.headers).json()
    result["dashboard"] = dashboard
    query_ids = list()
    param_query_ids = set()

    def recursively_append_param_queries(q):
        for p in q["options"]["parameters"]:
            if "queryId" in p:
                query_ids.insert(0, p["queryId"])
                param_query_ids.add(p["queryId"])
                #get the details of the underlying query to recursively append children queries from parameters if any
                child_q = requests.get(source_client.url + "/api/2.0/preview/sql/queries/" + p["queryId"], headers=source_client.headers).json()
                recursively_append_param_queries(child_q)
    #fetch all the queries required for the widgets, recursively
    for widget in dashboard["widgets"]:
        if "visualization" in widget:
            #First we need to add the queries from the parameters to make sure we clone them too
            if "options" in widget["visualization"]["query"] and \
                    "parameters" in widget["visualization"]["query"]["options"]:
                recursively_append_param_queries(widget["visualization"]["query"])
            query_ids.append(widget["visualization"]["query"]["id"])

    #removes duplicated but keep order (we need to start with the param queries first)
    query_ids = list(dict.fromkeys(query_ids))
    for query_id in query_ids:
        q = requests.get(source_client.url + "/api/2.0/preview/sql/queries/" + query_id, headers=source_client.headers).json()
        q["is_parameter_query"] = query_id in param_query_ids
        result["queries"].append(q)
    return result