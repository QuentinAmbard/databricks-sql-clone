from typing import List

import requests
import json
from utils.client import Client
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import collections

def get_all_dashboards(client: Client, tags = []):
    return get_all_item(client, "dashboards", tags)

def get_all_queries(client: Client, tags = []):
    return get_all_item(client, "queries", tags)

def delete_dashboard(client: Client, tags=[], ids_to_skip={}):
    print(f"cleaning up dashboards with tags in {tags}...")
    for d in get_all_dashboards(client, tags):
        if d['id'] not in ids_to_skip:
            print(f"deleting dashboard {d['id']} - {d['name']}")
            requests.delete(client.url+"/api/2.0/preview/sql/dashboards/"+d["id"], headers = client.headers).json()

def delete_queries(client: Client, tags=[], ids_to_skip={}):
    print(f"cleaning up queries with tags in {tags}...")
    queries_to_delete = get_all_queries(client, tags)
    params = [(client, q) for q in queries_to_delete if q['id'] not in ids_to_skip]
    with ThreadPoolExecutor(max_workers=10) as executor:
        collections.deque(executor.map(lambda args, f=delete_query: f(*args), params))

def delete_query(client: Client, q):
    print(f"deleting query {q['id']} - {q['name']}")
    requests.delete(client.url+"/api/2.0/preview/sql/queries/"+q["id"], headers = client.headers).json()

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

def duplicate_dashboard(client: Client, dashboard, dashboard_state):
    data = {"name": dashboard["name"], "tags": dashboard["tags"]}
    if "new_id" in dashboard_state and 'id' in requests.get(client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_state["new_id"], headers = client.headers).json():
        print("  dashboard exists, updating it")
        new_dashboard = requests.post(client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_state["new_id"], headers = client.headers, json=data).json()
        #Drop all the widgets and re-create them
        for widget in dashboard["widgets"]:
            print(f"    deleting widget {widget['id']} from existing dashboard {new_dashboard['id']}")
            requests.delete(client.url+"/api/2.0/preview/sql/widgets/"+widget['id'], headers = client.headers).json()
    else:
        print(f"  creating new dashboard...")
        new_dashboard = requests.post(client.url+"/api/2.0/preview/sql/dashboards", headers = client.headers, json=data).json()
        dashboard_state["new_id"] = new_dashboard["id"]
    if client.permisions_defined():
        permissions = requests.post(client.url+"/api/2.0/preview/sql/permissions/dashboards/"+new_dashboard["id"], headers = client.headers, json=client.permissions).json()
        print(f"     Dashboard ermissions set to {permissions}")
    for widget in dashboard["widgets"]:
        print(f"          cloning widget {widget}...")
        visualization_id_clone = None
        if "visualization" in widget:
            query_id = widget["visualization"]["query"]["id"]
            visualization_id = widget["visualization"]["id"]
            visualization_id_clone = dashboard_state["queries"][query_id]["visualizations"][visualization_id]
        data = {
            "dashboard_id": new_dashboard["id"],
            "visualization_id": visualization_id_clone,
            "text": widget["text"],
            "options": widget["options"],
            "width": widget["width"]
        }
        requests.post(client.url+"/api/2.0/preview/sql/widgets", headers = client.headers, json=data).json()

    return new_dashboard

def clone_dashboard_by_ids(source_client: Client, target_client: Client, dashboard_ids, workspace_state = {}):
    """
    :param source_client: workspace source
    :param target_client: workspace
    :param dashboard_ids:
    :param clone_state_id:
    :param state:
    :return:
    """
    params = [(source_client, target_client, dashboard_id, workspace_state[dashboard_id] if dashboard_id in workspace_state else {}) for dashboard_id in dashboard_ids]
    with ThreadPoolExecutor(max_workers=10) as executor:
        for (dashboard_id, dashboard_state) in executor.map(lambda args, f=clone_dashboard_by_id: f(*args), params):
            workspace_state[dashboard_id] = dashboard_state
    return workspace_state

def clone_dashboard_by_id(source_client: Client, target_client: Client, dashboard_id, dashboard_state):
    if "queries" not in dashboard_state:
        dashboard_state["queries"] = {}
    dashboard = requests.get(source_client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_id, headers = source_client.headers).json()
    print(f"cloning dashboard {dashboard}...")
    queries = list()
    for widget in dashboard["widgets"]:
        if "visualization" in widget:
            #First we need to add the queries from the parameters to make sure we clone them too
            if "options" in widget["visualization"]["query"] and \
                    "parameters" in widget["visualization"]["query"]["options"]:
                for p in widget["visualization"]["query"]["options"]["parameters"]:
                    if "queryId" in p:
                        queries.append(p["queryId"])
            queries.append(widget["visualization"]["query"]["id"])
    print(queries)

    #removes duplicated but keep order (we need to start with the param queries first)
    queries = list(dict.fromkeys(queries))

    for query_id in queries:
        q = requests.get(source_client.url + "/api/2.0/preview/sql/queries/" + query_id, headers=source_client.headers).json()
        #We need to replace the param queries with the newly created one
        if "parameters" in q["options"]:
            for p in q["options"]["parameters"]:
                p["queryId"] = dashboard_state["queries"][p["queryId"]]["new_id"]
                del p["parentQueryId"]
                del p["value"]
        new_query = clone_or_update_query(dashboard_state, q, target_client)
        if target_client.permisions_defined():
            permissions = requests.post(target_client.url+"/api/2.0/preview/sql/permissions/queries/"+new_query["id"], headers = target_client.headers, json=target_client.permissions).json()
            print(f"     Permissions set to {permissions}")

        visualizations = clone_query_visualization(target_client, q, new_query)
        dashboard_state["queries"][query_id] = {"new_id": new_query["id"], "visualizations": visualizations}
    duplicate_dashboard(target_client, dashboard, dashboard_state)
    return dashboard_id, dashboard_state


def clone_or_update_query(dashboard_state, q, target_client):
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
    new_query = None
    if q['id'] in dashboard_state["queries"]:
        existing_query_id = dashboard_state["queries"][q['id']]["new_id"]
        # check if the query still exists (it might have been manually deleted by mistake)
        if 'id' in requests.get(target_client.url + "/api/2.0/preview/sql/queries/" + existing_query_id,
                                headers=target_client.headers).json():
            print(f"     updating the existing query {existing_query_id}")
            new_query = requests.post(target_client.url + "/api/2.0/preview/sql/queries/" + existing_query_id,
                                      headers=target_client.headers, json=q_creation).json()
            # Delete all query visualization to reset its settings
            for v in new_query["visualizations"]:
                print(f"     deleting query visualization {v['id']}")
                requests.delete(target_client.url + "/api/2.0/preview/sql/visualizations/" + v["id"],
                                headers=target_client.headers).json()
    if not new_query:
        print(f"     cloning query {q_creation}...")
        new_query = requests.post(target_client.url + "/api/2.0/preview/sql/queries", headers=target_client.headers,
                                  json=q_creation).json()
    return new_query


def delete_and_clone_dashboards_with_tags(source_client: Client, target_client: Client, tags: List,
                                          delete_target_dashboards: bool, state):
    assert len(tags) > 0
    print(f"fetching existing dashboard with tags in {tags}...")
    workspace_state_id = source_client.url+"-"+target_client.url

    dashboards_to_clone = get_all_dashboards(source_client, tags)
    if workspace_state_id not in state:
        state[workspace_state_id] = {}
    workspace_state = state[workspace_state_id]

    print(f"start cloning {len(dashboards_to_clone)} dashboards...")
    dashboard_to_clone_ids = [d["id"] for d in dashboards_to_clone]
    state[workspace_state_id] = clone_dashboard_by_ids(source_client, target_client, dashboard_to_clone_ids, workspace_state)

    # Cleanup all existing ressources, but skip the queries used in the new dashboard (to support update)
    if delete_target_dashboards:
        new_queries = set()
        new_dashboards = set()
        for origin_dashboard_id in state[workspace_state_id]:
            new_dashboards.add(state[workspace_state_id][origin_dashboard_id]["new_id"])
            for origin_query_id in state[workspace_state_id][origin_dashboard_id]["queries"]:
                new_queries.add(state[workspace_state_id][origin_dashboard_id]["queries"][origin_query_id]["new_id"])
        delete_queries(target_client, tags, new_queries)
        delete_dashboard(target_client, tags, new_dashboards)

    print("-----------------------")
    print("import complete. Saving state for further update/analysis.")
    print(state)
    with open('state.json', 'w') as file:
        file.write(json.dumps(state))


def set_data_source_id_from_endpoint_id(client):
    print("Fetching endpoints to extract data_source id...")
    data_sources = requests.get(client.url+"/api/2.0/preview/sql/data_sources", headers=client.headers).json()
    assert len(data_sources) > 0, "No endpoints available. Please create at least 1 endpoint before cloning the dashboards."
    if client.endpoint_id is None:
        print(f"No endpoint id found. Using the first endpoint available: {data_sources[0]}")
        client.data_source_id = data_sources[0]['id']
    for data_source in data_sources:
        if "endpoint_id" in data_source and data_source['endpoint_id'] == client.endpoint_id:
            print(f"found datasource {data_source['id']} for endpoint {data_source['endpoint_id']}")
            client.data_source_id = data_source['id']
            break
    assert client.data_source_id is not None, f"Couldn't find an endpoint with ID {client.endpoint_id} in workspace {client.url}. Please use the endpoint ID from the URL."
