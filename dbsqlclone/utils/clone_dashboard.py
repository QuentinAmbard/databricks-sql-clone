from typing import List

import requests
import json
from dbsqlclone.utils.client import Client
from concurrent.futures import ThreadPoolExecutor
import collections
from dbsqlclone.utils.dump_dashboard import dump_dashboards
import logging

def get_all_dashboards(client: Client, tags = []):
    return get_all_item(client, "dashboards", tags)

def get_all_queries(client: Client, tags = []):
    return get_all_item(client, "queries", tags)

def delete_dashboard(client: Client, tags=[], ids_to_skip={}):
    logging.debug(f"cleaning up dashboards with tags in {tags}...")
    for d in get_all_dashboards(client, tags):
        if d['id'] not in ids_to_skip:
            logging.debug(f"deleting dashboard {d['id']} - {d['name']}")
            requests.delete(client.url+"/api/2.0/preview/sql/dashboards/"+d["id"], headers = client.headers).json()

def delete_queries(client: Client, tags=[], ids_to_skip={}):
    logging.debug(f"cleaning up queries with tags in {tags}...")
    queries_to_delete = get_all_queries(client, tags)
    params = [(client, q) for q in queries_to_delete if q['id'] not in ids_to_skip]
    with ThreadPoolExecutor(max_workers=10) as executor:
        collections.deque(executor.map(lambda args, f=delete_query: f(*args), params))

def delete_query(client: Client, q):
    logging.debug(f"deleting query {q['id']} - {q['name']}")
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

def delete_and_clone_dashboards_with_tags(source_client: Client, target_client: Client, tags: List,
                                          delete_target_dashboards: bool, state):
    assert len(tags) > 0
    logging.debug(f"fetching existing dashboard with tags in {tags}...")
    workspace_state_id = source_client.url+"-"+target_client.url

    dashboards_to_clone = get_all_dashboards(source_client, tags)
    if workspace_state_id not in state:
        state[workspace_state_id] = {}
    workspace_state = state[workspace_state_id]

    logging.debug(f"start cloning {len(dashboards_to_clone)} dashboards...")
    dashboard_to_clone_ids = [d["id"] for d in dashboards_to_clone]

    dump_dashboards(source_client, dashboard_to_clone_ids)
    state[workspace_state_id] = load_dashboards(target_client, dashboard_to_clone_ids, workspace_state)

    # Cleanup all existing resources, but skip the queries used in the new dashboard (to support update)
    if delete_target_dashboards:
        new_queries = set()
        new_dashboards = set()
        for origin_dashboard_id in state[workspace_state_id]:
            new_dashboards.add(state[workspace_state_id][origin_dashboard_id]["new_id"])
            for origin_query_id in state[workspace_state_id][origin_dashboard_id]["queries"]:
                new_queries.add(state[workspace_state_id][origin_dashboard_id]["queries"][origin_query_id]["new_id"])
        delete_queries(target_client, tags, new_queries)
        delete_dashboard(target_client, tags, new_dashboards)

    logging.debug("-----------------------")
    logging.debug("import complete. Saving state for further update/analysis.")
    logging.debug(state)
    with open('state.json', 'w') as file:
        file.write(json.dumps(state, indent=4, sort_keys=True))


def set_data_source_id_from_endpoint_id(client):
    logging.debug("Fetching endpoints to extract data_source id...")
    data_sources = requests.get(client.url+"/api/2.0/preview/sql/data_sources", headers=client.headers).json()
    assert len(data_sources) > 0, "No endpoints available. Please create at least 1 endpoint before cloning the dashboards."
    if client.endpoint_id is None:
        logging.debug(f"No endpoint id found. Using the first endpoint available: {data_sources[0]}")
        client.data_source_id = data_sources[0]['id']
    for data_source in data_sources:
        if "endpoint_id" in data_source and data_source['endpoint_id'] == client.endpoint_id:
            logging.debug(f"found datasource {data_source['id']} for endpoint {data_source['endpoint_id']}")
            client.data_source_id = data_source['id']
            break
    assert client.data_source_id is not None, f"Couldn't find an endpoint with ID {client.endpoint_id} in workspace {client.url}. Please use the endpoint ID from the URL."
