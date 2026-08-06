import unittest
from unittest.mock import patch

import deploy_render_public


class RenderDeployTests(unittest.TestCase):
    def test_api_uses_the_supplied_access_token_without_hardcoded_placeholder(self):
        with patch.object(deploy_render_public.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "{}"
            run.return_value.stderr = ""
            deploy_render_public.api("GET", "/services", token="runtime-access-token")

        command = run.call_args.args[0]
        self.assertIn("Authorization: Bearer runtime-access-token", command)
        self.assertNotIn("Authorization: Bearer ***", command)


if __name__ == "__main__":
    unittest.main()
