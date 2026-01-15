from __future__ import annotations

import copy
import os
from typing import Any
from collections.abc import Callable

import syft as sy
import torch
import torch.nn as nn
from syft.service.dataset.dataset import CreateAsset, CreateDataset
from torch.utils.data import DataLoader, Subset

from Backend.prepare import create_dataset
from Backend.utils import HealthCNN


def _select_device() -> torch.device:
    requested = os.getenv("MLBIO_DEVICE", "").strip().lower()
    if requested in {"cpu", "cuda"}:
        if requested == "cuda" and not torch.cuda.is_available():
            print("MLBIO_DEVICE=cuda demandé, mais CUDA indisponible -> fallback CPU")
            return torch.device("cpu")
        return torch.device(requested)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _state_dict_to_cpu(state_dict: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in state_dict.items():
        if isinstance(v, torch.Tensor):
            out[k] = v.detach().cpu()
        else:
            out[k] = v
    return out


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
    event_cb: Callable[[dict[str, Any]], None] | None = None,
) -> float:
    from Backend.syft_jobs import train_one_round

    server_handles = []
    try:
        device = _select_device()
        print(f"Backend device: {device}")
        if event_cb is not None:
            event_cb({"type": "backend_device", "device": str(device)})

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
        test_loader = DataLoader(
            Subset(full_dataset, test_indices),
            batch_size=32,
            num_workers=int(os.getenv("MLBIO_NUM_WORKERS", "0")),
            pin_memory=(device.type == "cuda"),
        )
        test_criterion = nn.CrossEntropyLoss()

        global_model = HealthCNN()
        global_model.to(device)

        for round_idx in range(rounds):
            local_states: list[dict[str, Any]] = []
            # PySyft serialization expects CPU tensors for upload/calls.
            global_state = _state_dict_to_cpu(copy.deepcopy(global_model.state_dict()))

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
                result = action_obj.get()
                if isinstance(result, dict) and "state_dict" in result:
                    local_states.append(result["state_dict"])
                    if event_cb is not None and isinstance(result.get("metrics"), dict):
                        # Evaluate the *client* model on the server-side test set.
                        # If per-epoch checkpoints are provided, compute test metrics per epoch
                        # so the frontend can display acc/loss vs epochs based on `test_size`.
                        epoch_states = result.get("epoch_state_dicts")
                        if isinstance(epoch_states, list) and epoch_states:
                            epoch_test_acc: list[float] = []
                            epoch_test_loss: list[float] = []
                            n_test_samples: int = 0
                            for sd in epoch_states:
                                client_model = HealthCNN()
                                client_model.load_state_dict(sd)
                                client_model.to(device)
                                client_model.eval()
                                loss_sum = 0.0
                                correct, total = 0, 0
                                with torch.no_grad():
                                    for x, y in test_loader:
                                        x = x.to(device, non_blocking=True)
                                        y = y.to(device, non_blocking=True)
                                        outputs = client_model(x)
                                        loss = test_criterion(outputs, y)
                                        loss_sum += float(loss.item()) * y.size(0)
                                        _, predicted = torch.max(outputs.data, 1)
                                        total += y.size(0)
                                        correct += (predicted == y).sum().item()
                                n_test_samples = int(total)
                                epoch_test_acc.append(float(100 * correct / max(1, total)))
                                epoch_test_loss.append(float(loss_sum / max(1, total)))
                            client_test_acc = epoch_test_acc[-1]
                            client_test_loss = epoch_test_loss[-1]
                        else:
                            client_model = HealthCNN()
                            client_model.load_state_dict(result["state_dict"])
                            client_model.to(device)
                            client_model.eval()
                            loss_sum = 0.0
                            correct, total = 0, 0
                            with torch.no_grad():
                                for x, y in test_loader:
                                    x = x.to(device, non_blocking=True)
                                    y = y.to(device, non_blocking=True)
                                    outputs = client_model(x)
                                    loss = test_criterion(outputs, y)
                                    loss_sum += float(loss.item()) * y.size(0)
                                    _, predicted = torch.max(outputs.data, 1)
                                    total += y.size(0)
                                    correct += (predicted == y).sum().item()
                            client_test_acc = float(100 * correct / max(1, total))
                            client_test_loss = float(loss_sum / max(1, total))
                            epoch_test_acc = None
                            epoch_test_loss = None
                            n_test_samples = int(total)

                        event_cb(
                            {
                                "type": "client_metrics",
                                "round": int(round_idx),
                                "client_id": int(i),
                                "metrics": {
                                    **result["metrics"],
                                    "test_accuracy_percent": float(client_test_acc),
                                    "test_loss": float(client_test_loss),
                                    "n_test_samples": int(n_test_samples),
                                    "epoch_test_acc": epoch_test_acc,
                                    "epoch_test_loss": epoch_test_loss,
                                },
                            }
                        )
                else:
                    # Backward compatibility: older train_one_round returned a raw state_dict.
                    local_states.append(result)

            global_model.load_state_dict(_fedavg(local_states))

            global_model.eval()
            loss_sum = 0.0
            correct, total = 0, 0
            with torch.no_grad():
                for x, y in test_loader:
                    x = x.to(device, non_blocking=True)
                    y = y.to(device, non_blocking=True)
                    outputs = global_model(x)
                    loss = test_criterion(outputs, y)
                    loss_sum += float(loss.item()) * y.size(0)
                    _, predicted = torch.max(outputs.data, 1)
                    total += y.size(0)
                    correct += (predicted == y).sum().item()
            round_acc = 100 * correct / max(1, total)
            round_loss = loss_sum / max(1, total)
            if event_cb is not None:
                event_cb(
                    {
                        "type": "global_metrics",
                        "round": int(round_idx),
                        "test_accuracy_percent": float(round_acc),
                        "test_loss": float(round_loss),
                    }
                )

        global_model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for x, y in test_loader:
                x = x.to(device, non_blocking=True)
                y = y.to(device, non_blocking=True)
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
