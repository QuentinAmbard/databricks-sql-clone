import requests
from utils.client import Client
import json

def dump_dashboards(source_client: Client, dashboard_ids):
    for id in dashboard_ids:
        dump_dashboard(source_client, id)

def dump_dashboard(source_client: Client, dashboard_id, folder_prefix="./dashboards/"):
    dashboard = get_dashboard_by_id(source_client, dashboard_id)
    with open(f'{folder_prefix}dashboard-{dashboard_id}.json', 'w') as file:
        file.write(json.dumps(dashboard, indent=4, sort_keys=True))

def get_dashboard_by_id(source_client: Client, dashboard_id):
    print(f"getting dashboard definition from {dashboard_id}...")
    result = {"queries": []}
    dashboard = requests.get(source_client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_id, headers = source_client.headers).json()
    result["dashboard"] = dashboard
    query_ids = list()

    def recursively_append_param_queries(q):
        for p in q["options"]["parameters"]:
            if "queryId" in p:
                query_ids.insert(0, p["queryId"])
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
        result["queries"].append(q)
    return result