from typing import List

import requests
import json
from utils.client import Client

def get_all_dashboards(client: Client, tags = []):
    return get_all_item(client, "dashboards", tags)

def get_all_queries(client: Client, tags = []):
    return get_all_item(client, "queries", tags)

def delete_dashboard(client: Client, tags=[]):
    print(f"cleaning up dashboards with tags in {tags}...")
    for d in get_all_dashboards(client, tags):
        print(f"deleting dashboard {d['id']} - {d['name']}")
        requests.delete(client.url+"/api/2.0/preview/sql/dashboards/"+d["id"], headers = client.headers).json()

def delete_queries(client: Client, tags=[]):
    print(f"cleaning up queries with tags in {tags}...")
    for d in get_all_queries(client, tags):
        print(f"deleting query {d['id']} - {d['name']}")
        requests.delete(client.url+"/api/2.0/preview/sql/queries/"+d["id"], headers = client.headers).json()

def get_all_item(client: Client, item, tags = []):
    assert item == "queries" or item == "dashboards"
    page_size = 250
    def get_all_dashboards(dashboards, page):
        r = requests.get(client.url+"/api/2.0/preview/sql/"+item, headers = client.headers, params={"page_size": page_size, "page": page}).json()
        #Filter to keep only dashboard with the proper tags
        dashboards_tags = [d for d in r["results"] if len(set(d["tags"]) & set(tags)) > 0]
        dashboards.extend(dashboards_tags)
        if len(r["results"]) >= page_size:
            dashboards = get_all_dashboards(dashboards, page+1)
        return dashboards
    return get_all_dashboards([], 1)


def clone_query_visualization(client: Client, query, target_query):
    # Sort both lists to retain visualization order on the query screen
    def get_first_vis(q):
        orig_table_visualizations = sorted(
            [i for i in q["visualizations"] if i["type"] == "TABLE"],
            key=lambda x: x["id"],
        )
        if len(orig_table_visualizations) > 0:
            return orig_table_visualizations[0]
        return None
    #Update the default(first) visualization to match the existing one:
    # Sort this table like orig_table_visualizations.
    # The first elements in these lists should mirror one another.
    orig_default_table = get_first_vis(query)
    mapping = {}
    if orig_default_table:
        target_default_table = get_first_vis(target_query)
        default_table_viz_data = {
            "name": orig_default_table["name"],
            "description": orig_default_table["description"],
            "options": orig_default_table["options"]
        }
        mapping[orig_default_table["id"]] = target_default_table["id"]
        print(f"         updating default Viz {target_default_table['id']}...")
        requests.post(client.url+"/api/2.0/preview/sql/visualizations/"+target_default_table["id"], headers = client.headers, json=default_table_viz_data)
    #Then create the other visualizations
    for v in sorted(query["visualizations"], key=lambda x: x["id"]):
        print(f"         cloning Viz {v['id']}...")
        data = {
            "name": v["name"],
            "description": v["description"],
            "options": v["options"],
            "type": v["type"],
            "query_id": target_query["id"],
        }
        new_v = requests.post(client.url+"/api/2.0/preview/sql/visualizations", headers = client.headers, json=data).json()
        mapping[v["id"]] = new_v["id"]
    return mapping

def duplicate_dashboard(client: Client, dashboard, state):
    data = {"name": dashboard["name"], "tags": dashboard["tags"]}
    new_dashboard = requests.post(client.url+"/api/2.0/preview/sql/dashboards", headers = client.headers, json=data).json()
    print(f"     dashboard created {new_dashboard}...")
    for widget in dashboard["widgets"]:
        print(f"          cloning widget {widget}...")
        visualization_id_clone = None
        if "visualization" in widget:
            query_id = widget["visualization"]["query"]["id"]
            visualization_id = widget["visualization"]["id"]
            visualization_id_clone = state[dashboard["id"]][query_id]["visualizations"][visualization_id]
        data = {
            "dashboard_id": new_dashboard["id"],
            "visualization_id": visualization_id_clone,
            "text": widget["text"],
            "options": widget["options"],
            "width": widget["width"]
        }
        requests.post(client.url+"/api/2.0/preview/sql/widgets", headers = client.headers, json=data).json()

    return new_dashboard

def clone_dashboard_by_id(source_client: Client, target_client: Client, dashboard_ids, clone_state_id = "new_clone", state = {}):
    """
    :param source_client: workspace source
    :param target_client: workspace 
    :param dashboard_ids:
    :param clone_state_id:
    :param state:
    :return:
    """
    for dashboard_id in dashboard_ids:
        state[clone_state_id][dashboard_id] = {}
        dashboard = requests.get(source_client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_id, headers = source_client.headers).json()
        print(f"cloning dashboard {dashboard}...")
        queries = set()
        for widget in dashboard["widgets"]:
            if "visualization" in widget:
                queries.add(widget["visualization"]["query"]["id"])
        for query_id in queries:
            q = requests.get(source_client.url+"/api/2.0/preview/sql/queries/"+query_id, headers = source_client.headers).json()
            q_creation = {
                "data_source_id": target_client.data_source_id,
                "query": q["query"],
                "name": q["name"],
                "description": q["description"],
                "schedule": q["schedule"],
                "tags": q["tags"],
                "options": q["options"]
            }
            if target_client.sql_database_name:
                q_creation["query"] = q_creation["query"].replace("field_demos_retail", target_client.sql_database_name)

            print(f"     cloning query {q_creation}...")
            new_query = requests.post(target_client.url+"/api/2.0/preview/sql/queries", headers = target_client.headers, json = q_creation).json()
            visualizations = clone_query_visualization(target_client, q, new_query)
            state[clone_state_id][dashboard_id][query_id] = {"new_id": new_query["id"], "visualizations": visualizations}
        duplicate_dashboard(target_client, dashboard, state[clone_state_id])
    return state

def delete_and_clone_dashboards_with_tags(source_client: Client, target_client: Client, tags: List):
    assert len(tags) > 0
    #Cleanup all existing ressources.
    delete_queries(target_client, tags)
    delete_dashboard(target_client, tags)

    print(f"fetching existing dashboard with tags in {tags}...")
    dashboard_to_clone = get_all_dashboards(source_client, tags)

    with open("./state.json", "r") as r:
        state = json.loads(r.read())
    clone_state_id = source_client.url+"-"+target_client.url
    if clone_state_id not in state:
        state[clone_state_id] = {}

    print(f"start dashboard cloning...")
    dashboard_to_clone_ids = [d["id"] for d in dashboard_to_clone]
    state = clone_dashboard_by_id(source_client, target_client, dashboard_to_clone_ids, clone_state_id, state)
    print("-----------------------")
    print("import complete. Saving state for further update/analysis.")
    print(state)
    with open('state.json', 'w') as file:
        file.write(json.dumps(state))