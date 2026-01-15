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

Option: pour servir aussi le frontend via le backend, build le frontend (génère `Frontend/dist`) puis relance l’API :

```bash
npm -C Frontend install
npm -C Frontend run build
```

## Lancer un sweep (tableau de résultats)

La contrainte du sujet est respectée en fixant, pour chaque configuration :

- `n_data_per_client = (fraction * (1 / n_clients)) * train_size`

Exemple :

```bash
curl -X POST http://localhost:8000/fl/run \
  -H 'content-type: application/json' \
  -d '{"n_clients": 5, "rounds": 1, "epochs": 1, "fractions": [1.0, 0.5, 0.1]}'
```

La route `/fl/run` démarre un job et renvoie un `job_id`.

- Résultats (polling) : `GET /fl/run/<job_id>`
- Courbes live (SSE) : `GET /fl/stream/<job_id>`

## Notes

- GPU : si PyTorch a été installé avec support CUDA et qu’un GPU est disponible, l’entraînement et l’évaluation utilisent automatiquement `cuda`.
  - Forcer le device : `MLBIO_DEVICE=cuda` ou `MLBIO_DEVICE=cpu` (ex: `MLBIO_DEVICE=cuda uvicorn Backend.app:app ...`).
- Perf DataLoader : `MLBIO_NUM_WORKERS=4` (ou plus selon CPU) peut accélérer le chargement quand `cuda` est utilisé (pinning activé).
- Debug device côté datasites : `MLBIO_LOG_DEVICE=1` (prints `[train_one_round] device=...`).
- En mode “simulation locale”, chaque client est un datasite PySyft local (`sy.orchestra.launch(..., server_type="datasite")`).
- Le premier run peut être long (téléchargement HAM10000 via `kagglehub` en cache).

