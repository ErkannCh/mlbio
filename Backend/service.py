from __future__ import annotations

from collections.abc import Callable

from Backend.main import main as run_one_experiment
from Backend.prepare import create_dataset
from Backend.schemas import RunResult


def run_fl_sweep(
    *,
    n_clients: int,
    rounds: int,
    epochs: int,
    lr: float,
    test_size: int,
    fractions: list[float],
    progress_cb: Callable[[int, RunResult | None], None] | None = None,
    event_cb: Callable[[dict], None] | None = None,
) -> list[RunResult]:
    full_dataset, _df = create_dataset()
    train_size = max(1, len(full_dataset) - int(test_size))

    results: list[RunResult] = []
    for idx, frac in enumerate(fractions):
        # Each client uses frac * (1/n_clients) of the available training set.
        n_data = max(1, int(train_size * float(frac) / n_clients))
        if event_cb is not None:
            event_cb(
                {
                    "type": "scenario_started",
                    "scenario": int(idx),
                    "scenarios_total": int(len(fractions)),
                    "fraction_of_1_over_n_clients": float(frac),
                    "n_clients": int(n_clients),
                    "n_data_per_client": int(n_data),
                    "rounds": int(rounds),
                    "epochs": int(epochs),
                    "lr": float(lr),
                    "test_size": int(test_size),
                }
            )
        scenario_event_cb = None
        if event_cb is not None:
            def scenario_event_cb(ev: dict) -> None:  # type: ignore[no-redef]
                ev2 = dict(ev)
                ev2.setdefault("scenario", int(idx))
                ev2.setdefault("fraction_of_1_over_n_clients", float(frac))
                event_cb(ev2)
        acc = run_one_experiment(
            clients=n_clients,
            n_data=n_data,
            rounds=rounds,
            epochs=epochs,
            lr=lr,
            test_size=test_size,
            event_cb=scenario_event_cb,
        )
        result = RunResult(
            fraction_of_1_over_n_clients=float(frac),
            n_data_per_client=n_data,
            accuracy_percent=float(acc),
        )
        results.append(result)
        if progress_cb is not None:
            progress_cb(idx + 1, result)
        if event_cb is not None:
            event_cb(
                {
                    "type": "scenario_finished",
                    "scenario": int(idx),
                    "fraction_of_1_over_n_clients": float(frac),
                    "accuracy_percent": float(acc),
                }
            )
    return results
