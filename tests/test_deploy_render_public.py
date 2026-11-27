import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import deploy_render_public
except ModuleNotFoundError:
    deploy_render_public = None

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "deploy_render_public.py"


@unittest.skipUnless(deploy_render_public is not None,
                     "deploy_render_public.py 不在仓库中（v1.17.1 已改用 render.yaml/gh 部署）")
class DeployTests(unittest.TestCase):
    def test_api_uses_the_supplied_access_token_without_hardcoded_placeholder(self):
        with patch.object(deploy_render_public.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b"[]"
            deploy_render_public.api("GET", "/services", token="runtime-access-token")
        command = " ".join(map(str, run.call_args[0][0]))
        self.assertIn("Authorization: Bearer runtime-access-token", command)
        self.assertNotIn("Authorization: Bearer ***", command)


if __name__ == "__main__":
    unittest.main()
