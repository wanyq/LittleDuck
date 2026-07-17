from pathlib import Path

import yaml

from littleduck_api.config import Settings
from littleduck_api.main import create_app


def test_implemented_vertical_slice_is_declared_by_baseline_contract() -> None:
    contract_path = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    application = create_app(Settings())
    implemented = application.openapi()["paths"]
    baseline = contract["paths"]

    for path, operations in implemented.items():
        baseline_path = path.replace("{generation_id}", "{generationId}")
        assert baseline_path in baseline
        for method in operations:
            if method in {"get", "post", "put", "patch", "delete"}:
                assert method in baseline[baseline_path]
