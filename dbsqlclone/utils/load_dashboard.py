import requests
from dbsqlclone.utils.client import Client
from concurrent.futures import ThreadPoolExecutor
import json
import collections
import logging

from .dump_dashboard import get_dashboard_definition_by_id
from .clone_dashboard import delete_query

logger = logging.getLogger('dbsqlclone.load')

max_workers = 3


import requests

def load_dashboards(target_client: Client, dashboard_ids, workspace_state):
    if workspace_state is None:
        workspace_state = {}
    params = [(target_client, dashboard_id, workspace_state[dashboard_id] if dashboard_id in workspace_state else {}) for dashboard_id in dashboard_ids]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
    state = {"queries": {}, "visualizations": {}, "new_id": existing_dashboard["dashboard"]["id"]}
    queries_not_matching = []
    for q in existing_dashboard["queries"]:
        matching_query = next((existing_q for existing_q in dashboard["queries"] if q['name'] == existing_q['name']), None)
        if matching_query is None:
            queries_not_matching.append(q)
        else:
            state["queries"][matching_query['id']] = {"new_id": q['id']}
    return state, queries_not_matching


#Override the existing_dashboard_id queries by trying to match them by name. If the name change, will create a new query and delete the existing one.
def clone_dashboard_without_saved_state(dashboard, target_client: Client, existing_dashboard_id, parent: str = None):
    dashboard_state, queries_not_matching = recreate_dashboard_state(target_client, dashboard, existing_dashboard_id)
    logger.debug(dashboard_state)
    state = clone_dashboard(dashboard, target_client, dashboard_state, parent)
    for q in queries_not_matching:
        logger.debug(f"deleting query {q}")
        delete_query(target_client, q)
    return state

def clone_dashboard(dashboard, target_client: Client, dashboard_state: dict = None, parent: str = None):
    if dashboard_state is None:
        dashboard_state = {}
    if "queries" not in dashboard_state:
        dashboard_state["queries"] = {}

    def load_query(q):
        #We need to replace the param queries with the newly created one
        if "parameters" in q["options"]:
            for p in q["options"]["parameters"]:
                if "queryId" in p:
                    p["queryId"] = dashboard_state["queries"][p["queryId"]]["new_id"]
                    if "parentQueryId" in p:
                        del p["parentQueryId"]
                    #if "value" in p:
                    #    del p["value"]
                    #if "$$value" in p:
                    #    del p["$$value"]
        new_query = clone_or_update_query(dashboard_state, q, target_client, parent)
        logger.debug(new_query)
        if "id" in new_query:
            if target_client.permisions_defined():
                with requests.post(target_client.url+"/api/2.0/preview/sql/permissions/queries/"+new_query["id"], headers = target_client.headers, json=target_client.permissions, timeout=120) as r:
                    permissions = r.json()
                logger.debug(f"     Permissions set to {permissions}")
            visualizations = clone_query_visualization(target_client, q, new_query)
            dashboard_state["queries"][q["id"]] = {"new_id": new_query["id"], "visualizations": visualizations}

    #First loads the queries used as parameters. They need to be loaded first as the other will depend on these
    for q in dashboard["queries"] :
        if "is_parameter_query" not in q or q["is_parameter_query"]:
            load_query(q)
    #Then loads everything else, no matter the order
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        collections.deque(executor.map(load_query, [q for q in dashboard["queries"] if "is_parameter_query" in q and not q["is_parameter_query"]]))

    duplicate_dashboard(target_client, dashboard["dashboard"], dashboard_state, parent)
    return dashboard_state

def clone_or_update_query(dashboard_state, q, target_client, parent):
    q_creation = {
        "data_source_id": target_client.data_source_id,
        "query": q["query"],
        "name": q["name"],
        "description": q["description"],
        "schedule": q.get("schedule", None),
        "tags": q.get("tags", None),
        "options": q["options"]
    }
    #Folder where the query will be installed
    if parent is not None:
        q_creation['parent'] = parent
    new_query = None
    if q['id'] in dashboard_state["queries"]:
        existing_query_id = dashboard_state["queries"][q['id']]["new_id"]
        # check if the query still exists (it might have been manually deleted by mistake)
        with requests.get(target_client.url + "/api/2.0/preview/sql/queries/" + existing_query_id, headers=target_client.headers, timeout=120) as r:
            existing_query = r.json()
        if 'id' in existing_query and 'moved_to_trash_at' not in existing_query:
            logger.debug(f"     updating the existing query {existing_query_id}")
            with requests.post(target_client.url + "/api/2.0/preview/sql/queries/" + existing_query_id, headers=target_client.headers, json=q_creation, timeout=120) as r:
                new_query = r.json()
            if "visualizations" not in new_query:
                raise Exception(f"can't update query or query without vis. Shouldn't happen: {new_query} - {q_creation} - {existing_query_id}")
            # Delete all query visualization to reset its settings
            for v in new_query["visualizations"]:
                logger.debug(f"     deleting query visualization {v['id']}")
                with requests.delete(target_client.url + "/api/2.0/preview/sql/visualizations/" + v["id"], headers=target_client.headers, timeout=120) as r:
                    r.json()
    if not new_query:
        logger.debug(f"     cloning query {q_creation}...")
        with requests.post(target_client.url + "/api/2.0/preview/sql/queries", headers=target_client.headers,json=q_creation, timeout=120) as r:
            new_query = r.json()
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
        logger.debug(f"         updating default Viz {target_default_table['id']}...")
        with requests.post(client.url+"/api/2.0/preview/sql/visualizations/"+target_default_table["id"], headers = client.headers, json=default_table_viz_data, timeout=120) as r:
            r.json()
    #Then create the other visualizations
    for v in sorted(query["visualizations"], key=lambda x: x["id"]):
        logger.debug(f"         cloning Viz {v['id']}...")
        data = {
            "name": v["name"],
            "description": v["description"],
            "options": v["options"],
            "type": v["type"],
            "query_plan": v["query_plan"],
            "query_id": target_query["id"],
        }
        with requests.post(client.url+"/api/2.0/preview/sql/visualizations", headers = client.headers, json=data, timeout=120) as r:
            new_v = r.json()
        if "id" not in new_v:
            raise Exception(f"couldn't create visualization - shouldn't happen {new_v} - {data}")
        mapping[v["id"]] = new_v["id"]
    return mapping


def duplicate_dashboard(client: Client, dashboard, dashboard_state, parent):
    data = {"name": dashboard["name"],
            "tags": dashboard["tags"],
            "data_source_id": client.data_source_id}
    #Folder where the dashboard will be installed
    if parent is not None:
        data['parent'] = parent

    new_dashboard = None
    if "new_id" in dashboard_state:
        with requests.get(client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_state["new_id"], headers = client.headers, timeout=120) as r:
            existing_dashboard = r.json()
        if "options" in existing_dashboard and "moved_to_trash_at" not in existing_dashboard["options"]:
            logger.debug("  dashboard exists, updating it")
            with requests.post(client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_state["new_id"], headers = client.headers, json=data, timeout=120) as r:
                new_dashboard = r.json()
            if "widgets" not in new_dashboard:
                logger.debug(f"ERROR: dashboard doesn't have widget, shouldn't happen - {new_dashboard}")
            else:
                #Drop all the widgets and re-create them
                for widget in new_dashboard["widgets"]:
                    logger.debug(f"    deleting widget {widget['id']} from existing dashboard {new_dashboard['id']}")
                    with requests.delete(client.url+"/api/2.0/preview/sql/widgets/"+widget['id'], headers = client.headers, timeout=120) as r:
                        r.json()
        else:
            logger.debug("    couldn't find the dashboard defined in the state, it probably has been deleted.")
    if new_dashboard is None:
        logger.debug(f"  creating new dashboard...")
        with requests.post(client.url+"/api/2.0/preview/sql/dashboards", headers = client.headers, json=data, timeout=120) as r:
            new_dashboard = r.json()
        dashboard_state["new_id"] = new_dashboard["id"]
    if client.permisions_defined():
        with requests.post(client.url+"/api/2.0/preview/sql/permissions/dashboards/"+new_dashboard["id"], headers = client.headers, json=client.permissions, timeout=120) as r:
            permissions = r.json()
        logger.debug(f"     Dashboard permissions set to {permissions}")

    def load_widget(widget):
        logger.debug(f"          cloning widget {widget}...")
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
        with requests.post(client.url+"/api/2.0/preview/sql/widgets", headers = client.headers, json=data, timeout=120) as r:
            r.json()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        collections.deque(executor.map(load_widget, dashboard["widgets"]))


    return new_dashboard