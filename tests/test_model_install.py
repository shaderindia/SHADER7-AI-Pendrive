"""PC installation must reject checkout manifests without model weights."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import server


class ModelInstallTests(unittest.TestCase):
    def test_missing_weight_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = b"test model"
            digest = hashlib.sha256(data).hexdigest()
            manifest = root / "manifests" / "registry.ollama.ai" / "library" / "test" / "latest"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"config": {"digest": f"sha256:{digest}", "size": len(data)}, "layers": []}))
            with patch.object(server, "MODEL_DIR", str(root)):
                with self.assertRaisesRegex(ValueError, "missing or incomplete"):
                    server.validate_model_store()
                blobs = root / "blobs"
                blobs.mkdir()
                (blobs / f"sha256-{digest}").write_bytes(data)
                server.validate_model_store()


if __name__ == "__main__":
    unittest.main()
