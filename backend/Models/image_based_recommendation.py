import os
import json
import numpy as np
import pandas as pd
from tensorflow.keras.applications.vgg16 import VGG16, preprocess_input
from tensorflow.keras.models import Model
from tensorflow.keras.preprocessing import image
from sklearn.metrics.pairwise import cosine_similarity
from PIL import Image
from io import BytesIO
import urllib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load VGG16 model for feature extraction
base_model = VGG16(weights='imagenet', include_top=False)
model = Model(inputs=base_model.input, outputs=base_model.output)

FEATURES_PATH = os.path.join(BASE_DIR, "../Models/all_features.npy")
NAMES_PATH = os.path.join(BASE_DIR, "../Models/all_image_names.json")
URLS_PATH = os.path.join(BASE_DIR, "../Models/all_image_urls.json")

def preprocess_image(img_url):
    try:
        with urllib.request.urlopen(img_url) as url_response:
            img_data = url_response.read()
            img = Image.open(BytesIO(img_data)).convert('RGB')
            img = img.resize((224, 224))
            img_array = image.img_to_array(img)
            img_array_expanded = np.expand_dims(img_array, axis=0)
            return preprocess_input(img_array_expanded)
    except Exception as e:
        print(f"Error loading image from {img_url}: {e}")
        return None

def extract_features(model, preprocessed_img):
    if preprocessed_img is None:
        return None
    features = model.predict(preprocessed_img)
    flattened_features = features.flatten()
    normalized_features = flattened_features / np.linalg.norm(flattened_features)
    return normalized_features

def extract_all_features():
    """
    Extract features from the CSV and save them to disk. Returns (features, names, urls).
    """
    all_features = []
    all_image_names = []
    all_image_urls = []
    df = pd.read_csv(os.path.join(BASE_DIR, "../Datasets/alo_yoga_products.csv"))
    for _, row in df.iterrows():
        img_url = row.get('image_url')
        name = row.get('name', '')
        preprocessed_img = preprocess_image(img_url)
        features = extract_features(model, preprocessed_img)
        if features is not None:
            all_features.append(features)
            all_image_names.append(name)
            all_image_urls.append(img_url)
        else:
            print(f"Skipping image: {img_url}")
    # Save features and metadata for later use
    np.save(FEATURES_PATH, np.array(all_features))
    with open(NAMES_PATH, 'w') as f:
        json.dump(all_image_names, f)
    with open(URLS_PATH, 'w') as f:
        json.dump(all_image_urls, f)
    print(f"Extracted and saved features for {len(all_features)} images.")
    return np.array(all_features), all_image_names, all_image_urls

def ensure_features_exist():
    """
    Ensure that features, names, and urls files exist. If not, extract and save them.
    """
    if not (os.path.exists(FEATURES_PATH) and os.path.exists(NAMES_PATH) and os.path.exists(URLS_PATH)):
        print("Feature files not found. Extracting features from CSV...")
        extract_all_features()
    else:
        print("Feature files found. Using saved features.")

def load_catalog_features():
    """
    Loads features, names, and urls, extracting them if needed.
    Returns: (features, names, urls)
    """
    ensure_features_exist()
    all_features = np.load(FEATURES_PATH)
    with open(URLS_PATH, 'r') as f:
        all_image_urls = json.load(f)
    with open(NAMES_PATH, 'r') as f:
        all_image_names = json.load(f)
    return all_features, all_image_names, all_image_urls

def recommend_from_image(query_img_url, top_k=5):
    all_features, all_image_names, all_image_urls = load_catalog_features()
    query_preprocessed = preprocess_image(query_img_url)
    if query_preprocessed is None:
        print(f"Could not process query image: {query_img_url}")
        return []
    query_features = extract_features(model, query_preprocessed)
    if query_features is None:
        print(f"Could not extract features from query image: {query_img_url}")
        return []
    similarities = cosine_similarity([query_features], all_features)[0]
    top_indices = similarities.argsort()[-top_k:][::-1]
    recommendations = []
    for idx in top_indices:
        recommendations.append({
            "name": all_image_names[idx],
            "image_url": all_image_urls[idx]
            # "similarity": float(similarities[idx])
        })
    return recommendations