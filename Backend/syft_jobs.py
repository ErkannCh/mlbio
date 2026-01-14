from __future__ import annotations

from typing import Any

from syft.service.code.user_code import syft_function


@syft_function()
def train_one_round(
    global_state: dict[str, Any],
    client_id: int,
    n_data: int,
    epochs: int = 5,
    lr: float = 5e-4,
    batch_size: int = 16,
) -> dict[str, Any]:
    # PySyft user-code execution may not preserve module-level imports.
    # Keep the function self-contained (imports + helper defs inside).
    import os
    from glob import glob

    import kagglehub
    import pandas as pd
    import torch
    import torch.nn as nn
    import torch.optim as optim
    import torchvision.transforms as transforms
    from PIL import Image
    from torch.utils.data import DataLoader, Dataset, Subset

    def _select_device() -> torch.device:
        requested = os.getenv("MLBIO_DEVICE", "").strip().lower()
        if requested in {"cpu", "cuda"}:
            if requested == "cuda" and not torch.cuda.is_available():
                return torch.device("cpu")
            return torch.device(requested)
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if hasattr(global_state, "syft_action_data"):
        global_state = global_state.syft_action_data
    if hasattr(client_id, "syft_action_data"):
        client_id = int(client_id.syft_action_data)
    if hasattr(n_data, "syft_action_data"):
        n_data = int(n_data.syft_action_data)
    if hasattr(epochs, "syft_action_data"):
        epochs = int(epochs.syft_action_data)
    if hasattr(lr, "syft_action_data"):
        lr = float(lr.syft_action_data)

    class SkinCancerDataset(Dataset):
        def __init__(self, dataframe, transform=None):
            self.df = dataframe
            self.transform = transform
            self.labels = pd.Categorical(self.df["dx"]).codes

        def __len__(self):
            return len(self.df)

        def __getitem__(self, idx):
            idx = int(idx)
            img_path = self.df.iloc[idx]["path"]
            image = Image.open(img_path).convert("RGB")
            label = int(self.labels[idx])
            if self.transform:
                image = self.transform(image)
            return image, label

    def create_dataset():
        base_path = kagglehub.dataset_download("kmader/skin-cancer-mnist-ham10000")
        image_path_dict = {
            os.path.splitext(os.path.basename(x))[0]: x
            for x in glob(os.path.join(base_path, "*", "*.jpg"))
        }

        df = pd.read_csv(os.path.join(base_path, "HAM10000_metadata.csv"))
        df["path"] = df["image_id"].map(image_path_dict)

        transform = transforms.Compose(
            [
                transforms.Resize((64, 64)),
                transforms.ToTensor(),
                transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
            ]
        )
        df = df.sample(frac=1, random_state=42).reset_index(drop=True)
        full_dataset = SkinCancerDataset(df, transform=transform)
        return full_dataset, df

    class HealthCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.layers = nn.Sequential(
                nn.Conv2d(3, 32, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.MaxPool2d(2),
                nn.Conv2d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.MaxPool2d(2),
                nn.Flatten(),
                nn.Linear(64 * 16 * 16, 256),
                nn.ReLU(),
                nn.Linear(256, 7),
            )

        def forward(self, x):
            return self.layers(x)

    full_dataset, df = create_dataset()

    class_counts = df["dx"].value_counts().sort_index().values
    weights = 1.0 / class_counts
    weights = weights / weights.sum() * 7
    class_weights = torch.FloatTensor(weights)
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    device = _select_device()
    model = HealthCNN()
    model.load_state_dict(global_state)
    model.to(device)
    criterion.to(device)

    opt = optim.Adam(model.parameters(), lr=lr)
    start = int(client_id) * int(n_data)
    end = (int(client_id) + 1) * int(n_data)
    loader = DataLoader(Subset(full_dataset, range(start, end)), batch_size=batch_size)

    model.train()
    for _ in range(int(epochs)):
        for x, y in loader:
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            opt.zero_grad()
            loss = criterion(model(x), y)
            loss.backward()
            opt.step()

    return {k: v.detach().cpu() for k, v in model.state_dict().items()}
