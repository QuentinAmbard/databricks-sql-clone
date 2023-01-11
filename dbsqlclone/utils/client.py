class Client():
    def __init__(self, url, token, permissions = [], endpoint_id = None, dashboard_tags = None):
        self.url = url
        self.headers = {"Authorization": "Bearer " + token, 'Content-type': 'application/json'}
        self.permissions = None
        if permissions is not None:
            self.permissions = {"access_control_list": permissions}
        self.data_source_id = None
        self.endpoint_id = endpoint_id
        self.dashboard_tags = dashboard_tags

    def permisions_defined(self):
        return self.permissions is not None and len(self.permissions["access_control_list"]) > 0