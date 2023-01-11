import requests
from dbsqlclone.utils.client import Client
from concurrent.futures import ThreadPoolExecutor
import json
import collections
import logging

from .dump_dashboard import get_dashboard_definition_by_id
from .clone_dashboard import delete_query


def load_dashboards(target_client: Client, dashboard_ids, workspace_state):
    if workspace_state is None:
        workspace_state = {}
    params = [(target_client, dashboard_id, workspace_state[dashboard_id] if dashboard_id in workspace_state else {}) for dashboard_id in dashboard_ids]

    with ThreadPoolExecutor(max_workers=10) as executor:
        for (dashboard_id, dashboard_state) in executor.map(lambda args, f=load_dashboard: f(*args), params):
            workspace_state[dashboard_id] = dashboard_state
    return workspace_state

def load_dashboard(target_client: Client, dashboard_id, dashboard_state, folder_prefix="./dashboards/"):
    if not folder_prefix.endswith("/"):
        folder_prefix += "/"
    with open(f'{folder_prefix}dashboard-{dashboard_id}.json', 'r') as r:
        dashboard = json.loads(r.read())
        dashboard_state = clone_dashboard(dashboard, target_client, dashboard_state)
        return dashboard_id, dashboard_state

#Try to match the existing query based on the name. This is to avoid having to delete/recreate the queries everytime
def recreate_dashboard_state(target_client, dashboard, dashboard_id):
    #Get the definition of the existing dashboard
    existing_dashboard = get_dashboard_definition_by_id(target_client, dashboard_id)
    state = {"queries": {}, "visualizations": {}}
    queries_not_matching = []
    for q in existing_dashboard["queries"]:
        matching_query = next((existing_q for existing_q in dashboard["queries"] if q['name'] == existing_q['name']), None)
        if matching_query is None:
            queries_not_matching.append(q)
        else:
            state[matching_query['id']] = {"new_id": q['id']}
    return state, queries_not_matching


#Override the existing_dashboard_id queries by trying to match them by name. If the name change, will create a new query and delete the existing one.
def clone_dashboard_without_saved_state(dashboard, target_client: Client, existing_dashboard_id, parent: str = None):
    dashboard_state, queries_not_matching = recreate_dashboard_state(target_client, dashboard, existing_dashboard_id)
    clone_dashboard(dashboard, target_client, dashboard_state, parent)
    for q in queries_not_matching:
        delete_query(target_client, q)

def clone_dashboard(dashboard, target_client: Client, dashboard_state: dict = {}, parent: str = None):
    if "queries" not in dashboard_state:
        dashboard_state["queries"] = {}

    for q in dashboard["queries"]:
        #We need to replace the param queries with the newly created one
        if "parameters" in q["options"]:
            for p in q["options"]["parameters"]:
                if "queryId" in p:
                    p["queryId"] = dashboard_state["queries"][p["queryId"]]["new_id"]
                    if "parentQueryId" in p:
                        del p["parentQueryId"]
                    del p["value"]
        new_query = clone_or_update_query(dashboard_state, q, target_client, parent)
        if target_client.permisions_defined():
            permissions = requests.post(target_client.url+"/api/2.0/preview/sql/permissions/queries/"+new_query["id"], headers = target_client.headers, json=target_client.permissions).json()
            logging.debug(f"     Permissions set to {permissions}")

        visualizations = clone_query_visualization(target_client, q, new_query)
        dashboard_state["queries"][q["id"]] = {"new_id": new_query["id"], "visualizations": visualizations}
    duplicate_dashboard(target_client, dashboard["dashboard"], dashboard_state, parent)
    return dashboard_state

def clone_or_update_query(dashboard_state, q, target_client, parent):
    q_creation = {
        "data_source_id": target_client.data_source_id,
        "query": q["query"],
        "name": q["name"],
        "description": q["description"],
        "schedule": q["schedule"],
        "tags": q["tags"],
        "options": q["options"]
    }
    #Folder where the query will be installed
    if parent is not None:
        q_creation['parent'] = parent

    new_query = None
    if q['id'] in dashboard_state["queries"]:
        existing_query_id = dashboard_state["queries"][q['id']]["new_id"]
        # check if the query still exists (it might have been manually deleted by mistake)
        existing_query = requests.get(target_client.url + "/api/2.0/preview/sql/queries/" + existing_query_id,
                                      headers=target_client.headers).json()
        if 'id' in existing_query and 'moved_to_trash_at' not in existing_query:
            logging.debug(f"     updating the existing query {existing_query_id}")
            new_query = requests.post(target_client.url + "/api/2.0/preview/sql/queries/" + existing_query_id,
                                      headers=target_client.headers, json=q_creation).json()
            # Delete all query visualization to reset its settings
            for v in new_query["visualizations"]:
                logging.debug(f"     deleting query visualization {v['id']}")
                requests.delete(target_client.url + "/api/2.0/preview/sql/visualizations/" + v["id"],
                                headers=target_client.headers).json()
    if not new_query:
        logging.debug(f"     cloning query {q_creation}...")
        new_query = requests.post(target_client.url + "/api/2.0/preview/sql/queries", headers=target_client.headers,
                                  json=q_creation).json()
    return new_query


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
        if target_default_table is not None:
            mapping[orig_default_table["id"]] = target_default_table["id"]
        logging.debug(f"         updating default Viz {target_default_table['id']}...")
        requests.post(client.url+"/api/2.0/preview/sql/visualizations/"+target_default_table["id"], headers = client.headers, json=default_table_viz_data)
    #Then create the other visualizations
    for v in sorted(query["visualizations"], key=lambda x: x["id"]):
        logging.debug(f"         cloning Viz {v['id']}...")
        data = {
            "name": v["name"],
            "description": v["description"],
            "options": v["options"],
            "type": v["type"],
            "query_plan": v["query_plan"],
            "query_id": target_query["id"],
        }
        new_v = requests.post(client.url+"/api/2.0/preview/sql/visualizations", headers = client.headers, json=data).json()
        mapping[v["id"]] = new_v["id"]
    return mapping


def duplicate_dashboard(client: Client, dashboard, dashboard_state, parent):
    data = {"name": dashboard["name"], "tags": dashboard["tags"]}
    #Folder where the dashboard will be installed
    if parent is not None:
        data['parent'] = parent

    new_dashboard = None
    if "new_id" in dashboard_state:
        existing_dashboard = requests.get(client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_state["new_id"], headers = client.headers).json()
        if "options" in existing_dashboard and "moved_to_trash_at" not in existing_dashboard["options"]:
            logging.debug("  dashboard exists, updating it")
            new_dashboard = requests.post(client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_state["new_id"], headers = client.headers, json=data).json()
            #Drop all the widgets and re-create them
            for widget in new_dashboard["widgets"]:
                logging.debug(f"    deleting widget {widget['id']} from existing dashboard {new_dashboard['id']}")
                requests.delete(client.url+"/api/2.0/preview/sql/widgets/"+widget['id'], headers = client.headers).json()
        else:
            logging.debug("    couldn't find the dashboard defined in the state, it probably has been deleted.")
    if new_dashboard is None:
        logging.debug(f"  creating new dashboard...")
        new_dashboard = requests.post(client.url+"/api/2.0/preview/sql/dashboards", headers = client.headers, json=data).json()
        dashboard_state["new_id"] = new_dashboard["id"]
    if client.permisions_defined():
        permissions = requests.post(client.url+"/api/2.0/preview/sql/permissions/dashboards/"+new_dashboard["id"], headers = client.headers, json=client.permissions).json()
        logging.debug(f"     Dashboard permissions set to {permissions}")
    for widget in dashboard["widgets"]:
        logging.debug(f"          cloning widget {widget}...")
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