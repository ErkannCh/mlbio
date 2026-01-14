# Backend (FastAPI) — Federated Learning avec PySyft

Ce backend expose une API HTTP qui orchestre un entraînement fédéré (FedAvg) via PySyft sur le dataset HAM10000.

## Installation

```bash
. .venv/bin/activate
pip install -r Backend/requirements.txt
```

## Lancer l’API

```bash
. .venv/bin/activate
uvicorn Backend.app:app --host 0.0.0.0 --port 8000
```

## Lancer un sweep (tableau de résultats)

La contrainte du sujet est respectée en fixant, pour chaque configuration :

- `n_data_per_client = (fraction * (1 / n_clients)) * train_size`

Exemple :

```bash
curl -X POST http://localhost:8000/fl/run \\
  -H 'content-type: application/json' \\
  -d '{\"n_clients\": 5, \"rounds\": 1, \"epochs\": 1, \"fractions\": [1.0, 0.5, 0.1]}'
```

La réponse contient une liste `results` (équivalent “table”) avec :

- `fraction_of_1_over_n_clients` (`1.0`, `0.5`, `0.1`)
- `n_data_per_client`
- `accuracy_percent`

## Notes

- En mode “simulation locale”, chaque client est un datasite PySyft local (`sy.orchestra.launch(..., server_type=\"datasite\")`).
- Le premier run peut être long (téléchargement HAM10000 via `kagglehub` en cache).

