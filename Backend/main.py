from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import syft as sy
import torch
from syft.service.dataset.dataset import CreateAsset, CreateDataset
from torch.utils.data import DataLoader, Subset

from Backend.prepare import create_dataset
from Backend.utils import HealthCNN


def _fedavg(state_dicts: list[dict[str, Any]]) -> dict[str, Any]:
    fed_dict: dict[str, Any] = {}
    keys = list(state_dicts[0].keys())
    for key in keys:
        fed_dict[key] = torch.stack([sd[key].float() for sd in state_dicts]).mean(0)
    return fed_dict


def _upload_call_args(client: Any, *, name: str, args_dict: dict[str, Any]) -> dict[str, Any]:
    assets = [
        CreateAsset(name=k, data=v, mock=v, mock_is_real=True)
        for k, v in args_dict.items()
    ]
    client.upload_dataset(CreateDataset(name=name, asset_list=assets))
    dataset = [d for d in client.datasets.get_all() if d.name == name][0]
    return {asset.name: asset for asset in dataset.assets}


def main(
    clients: int = 5,
    n_data: int = 500,
    rounds: int = 1,
    epochs: int = 5,
    lr: float = 5e-4,
    test_size: int = 500,
) -> float:
    from Backend.syft_jobs import train_one_round

    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(repo_root))

    server_handles = []
    try:
        server_handles = [
            sy.orchestra.launch(
                name=f"datasite-{i}",
                server_type="datasite",
                deploy_to="python",
                port=0,
                dev_mode=True,
                reset=True,
                tail=False,
            )
            for i in range(clients)
        ]
        client_handles = [
            h.login(email="info@openmined.org", password="changethis")
            for h in server_handles
        ]

        submitted_codes = []
        for c in client_handles:
            # Avoid reusing an older version of the same service function.
            try:
                old_codes = c.code.get_by_service_func_name("train_one_round")
                for old in old_codes:
                    c.code.delete(old.id)
            except Exception:
                pass

            c.code.submit(train_one_round)
            code_matches = c.code.get_by_service_func_name("train_one_round")
            code_obj = code_matches[-1]
            req = c.code.request_code_execution(code_obj)
            req.approve_with_client(c)
            submitted_codes.append(code_obj)

        full_dataset, _df = create_dataset()
        test_size = int(test_size)
        test_size = max(1, min(test_size, len(full_dataset)))
        test_indices = range(len(full_dataset) - test_size, len(full_dataset))
        test_loader = DataLoader(Subset(full_dataset, test_indices), batch_size=32)

        global_model = HealthCNN()

        for round_idx in range(rounds):
            local_states: list[dict[str, Any]] = []
            global_state = copy.deepcopy(global_model.state_dict())

            for i, c in enumerate(client_handles):
                remote_args = _upload_call_args(
                    c,
                    name=f"call-args-round-{round_idx}-client-{i}",
                    args_dict={
                        "global_state": global_state,
                        "client_id": i,
                        "n_data": n_data,
                        "epochs": epochs,
                        "lr": lr,
                    },
                )
                action_obj = c.code.call(
                    submitted_codes[i].id,
                    global_state=remote_args["global_state"],
                    client_id=remote_args["client_id"],
                    n_data=remote_args["n_data"],
                    epochs=remote_args["epochs"],
                    lr=remote_args["lr"],
                )
                local_states.append(action_obj.get())

            global_model.load_state_dict(_fedavg(local_states))

        global_model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for x, y in test_loader:
                outputs = global_model(x)
                _, predicted = torch.max(outputs.data, 1)
                total += y.size(0)
                correct += (predicted == y).sum().item()

        acc = 100 * correct / total
        print(f"Accuracy: {acc:.1f}%")
        return float(acc)
    finally:
        for h in server_handles:
            try:
                h.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    main()
