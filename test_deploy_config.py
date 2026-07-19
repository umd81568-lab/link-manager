import io
import json
import os
import unittest
from unittest import mock

import deploy_all
import deploy_config


class DeployConfigTest(unittest.TestCase):
    def test_cli_host_overrides_env_and_default(self):
        with mock.patch.dict(os.environ, {"DEPLOY_HOST": "10.0.0.2", "DEPLOY_SSH_PORT": "2222"}, clear=False):
            args = type("Args", (), {"host": "10.0.0.3", "user": None, "ssh_port": None, "key_file": None})()
            settings = deploy_config.resolve_ssh_target(args)
        self.assertEqual(settings["host"], "10.0.0.3")
        self.assertEqual(settings["ssh_port"], 2222)

    def test_env_host_used_when_cli_missing(self):
        with mock.patch.dict(os.environ, {"DEPLOY_HOST": "10.0.0.4"}, clear=False):
            args = type("Args", (), {"host": None, "user": None, "ssh_port": None, "key_file": None})()
            settings = deploy_config.resolve_ssh_target(args)
        self.assertEqual(settings["host"], "10.0.0.4")

    def test_default_host_used_when_cli_and_env_missing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            args = type("Args", (), {"host": None, "user": None, "ssh_port": None, "key_file": None})()
            settings = deploy_config.resolve_ssh_target(args)
        self.assertEqual(settings["host"], deploy_config.DEFAULT_DEPLOY_HOST)

    def test_deploy_all_reports_missing_local_file_as_json(self):
        with mock.patch.object(deploy_all, "LOCAL_LINK_SCRIPT", "/tmp/does-not-exist.py"):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                result = deploy_all.main(["secret"])
        self.assertEqual(result, 1)
        payload = json.loads(stdout.getvalue().strip())
        self.assertEqual(payload["error"], "missing_local_file")
        self.assertIn("link_manager_local.py", payload["hint"])


if __name__ == "__main__":
    unittest.main()
