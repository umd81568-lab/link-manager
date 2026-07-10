import importlib
import json
import os
import shutil
import tempfile
import unittest


class LiveFeaturesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="lm-live-test-")
        os.environ["LINK_DATA_DIR"] = cls.tmp
        os.environ["LINK_MAP_FILE"] = os.path.join(cls.tmp, "links.json")
        os.environ["LINK_META_FILE"] = os.path.join(cls.tmp, "links.meta.json")
        os.environ["LINK_LIVE_FILE"] = os.path.join(cls.tmp, "live.json")
        os.environ["LINK_LIVE_TEMPLATE_DIR"] = os.path.join(cls.tmp, "templates")
        os.environ["LINK_LIVE_QR_DIR"] = os.path.join(cls.tmp, "qr")
        import link_manager_local

        cls.mod = importlib.reload(link_manager_local)
        cls.client = cls.mod.app.test_client()
        cls.auth_headers = {"X-Login-Password": "admin"}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_live_link_end_to_end(self):
        r = self.client.post(
            "/api/live/domains/add",
            data=json.dumps({"domain": "https://example.com"}),
            content_type="application/json",
            headers=self.auth_headers,
        )
        self.assertEqual(r.status_code, 200, r.data)

        html = "<html><body><h1>{{name}}</h1><p>{{key1}}</p></body></html>"
        r = self.client.post(
            "/api/live/templates/detect",
            data={"html": html},
            headers=self.auth_headers,
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.get_json()["fields"], ["name", "key1"])

        r = self.client.post(
            "/api/live/templates/create",
            data={"name": "tpl1", "html": html, "fields_override": "name,key1"},
            headers=self.auth_headers,
        )
        self.assertEqual(r.status_code, 200, r.data)
        template_id = r.get_json()["id"]

        r = self.client.post(
            "/api/live/links/create",
            data=json.dumps(
                {
                    "domain": "https://example.com",
                    "template_id": template_id,
                    "params_json": '{"name":"Rahim"}',
                    "custom_query": "key1=value1&key2=value2",
                }
            ),
            content_type="application/json",
            headers=self.auth_headers,
        )
        self.assertEqual(r.status_code, 200, r.data)
        body = r.get_json()
        self.assertIn("/live/", body["url"])
        self.assertIn("key1=value1", body["url"])
        self.assertTrue(body["qr_url"].startswith("/live/qr/"))

        link_id = body["id"]
        r = self.client.get(f"/live/{link_id}?name=Karim&key1=hello")
        self.assertEqual(r.status_code, 200, r.data)
        page = r.get_data(as_text=True)
        self.assertIn("Karim", page)
        self.assertIn("hello", page)

        r = self.client.get(f"/live/{link_id}?name=%3Cscript%3Ealert(1)%3C/script%3E&key1=x")
        self.assertEqual(r.status_code, 200, r.data)
        page = r.get_data(as_text=True)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)


if __name__ == "__main__":
    unittest.main()
