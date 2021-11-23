class Client():
    def __init__(self, url, token, data_source_id = None, dashboard_tags = None, sql_database_name=None):
        self.url = url
        self.headers = {"Authorization": "Bearer " + token, 'Content-type': 'application/json'}
        self.data_source_id = data_source_id
        self.dashboard_tags = dashboard_tags
        self.sql_database_name = sql_database_name
