# Frontend (Vue + Vite)

UI pour lancer les expériences (PySyft + FedAvg) et afficher le tableau de résultats.

## Lancer le backend

```bash
. .venv/bin/activate
pip install -r Backend/requirements.txt
uvicorn Backend.app:app --host 0.0.0.0 --port 8000
```

## Lancer le frontend

```sh
npm install
```

```sh
npm run dev
```

Le proxy Vite est configuré pour appeler le backend via `/fl/*` sur `http://localhost:8000`.

Ouvre ensuite `http://localhost:5173`.
