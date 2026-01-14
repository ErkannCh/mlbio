import pandas as pd
import os
from glob import glob
from torch.utils.data import Dataset
from PIL import Image
import torchvision.transforms as transforms
import kagglehub

class SkinCancerDataset(Dataset):
    def __init__(self, dataframe, transform=None):
        self.df = dataframe
        self.transform = transform
        self.labels = pd.Categorical(self.df['dx']).codes

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        idx = int(idx)
        img_path = self.df.iloc[idx]["path"]
        image = Image.open(img_path).convert('RGB')
        label = int(self.labels[idx])
        if self.transform:
            image = self.transform(image)
        return image, label


def create_dataset():
    base_path = kagglehub.dataset_download("kmader/skin-cancer-mnist-ham10000")
    image_path_dict = {os.path.splitext(os.path.basename(x))[0]: x for x in glob(os.path.join(base_path, '*', '*.jpg'))}
    print(f"Dataset downloaded to: {base_path}")

    df = pd.read_csv(os.path.join(base_path, 'HAM10000_metadata.csv'))
    df['path'] = df['image_id'].map(image_path_dict)
    lesion_type_dict = {
        'nv': 'Melanocytic nevi',
        'mel': 'Melanoma',
        'bkl': 'Benign keratosis-like lesions',
        'bcc': 'Basal cell carcinoma',
        'akiec': 'Actinic keratoses',
        'vasc': 'Vascular lesions',
        'df': 'Dermatofibroma'
    }
    df['cell_type'] = df['dx'].map(lesion_type_dict)
    transform = transforms.Compose([
        transforms.Resize((64, 64)),
        transforms.ToTensor(),
        transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5])
    ])
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    full_dataset = SkinCancerDataset(df, transform=transform)
    return full_dataset, df
