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
IDS_PATH = os.path.join(BASE_DIR, "../Models/all_image_ids.json")
DB_PATH = os.path.join(BASE_DIR, "..", "app.db")

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

def extract_all_features_from_db():
    """
    Extract features from products table in app.db and save them to disk.
    This function is idempotent: it will reuse existing features for products whose
    image URL hasn't changed, append new product features, and remove features for
    deleted products. Features and metadata are stored in FEATURES_PATH, NAMES_PATH,
    URLS_PATH and IDS_PATH (product ids aligned with arrays).
    Returns (features, names, urls, ids).
    """
    import sqlite3

    # load existing cached metadata if present
    existing_features = None
    existing_names = []
    existing_urls = []
    existing_ids = []
    if os.path.exists(FEATURES_PATH) and os.path.exists(NAMES_PATH) and os.path.exists(URLS_PATH) and os.path.exists(IDS_PATH):
        try:
            existing_features = np.load(FEATURES_PATH)
            with open(NAMES_PATH, 'r') as f:
                existing_names = json.load(f)
            with open(URLS_PATH, 'r') as f:
                existing_urls = json.load(f)
            with open(IDS_PATH, 'r') as f:
                existing_ids = json.load(f)
        except Exception as e:
            print(f"Warning: failed to load existing feature cache: {e}")
            existing_features = None

    # read products from DB
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT id, name, image FROM products ORDER BY id')
    rows = cur.fetchall()

    # map existing ids to index for quick reuse
    id_to_index = {int(pid): idx for idx, pid in enumerate(existing_ids)} if existing_ids else {}

    new_features = []
    new_names = []
    new_urls = []
    new_ids = []

    for r in rows:
        pid = int(r['id'])
        name = r['name'] or ''
        img_url = r['image'] or ''

        reused = False
        if existing_features is not None and pid in id_to_index:
            idx = id_to_index[pid]
            # reuse only if url unchanged and index in bounds
            if idx < len(existing_urls) and existing_urls[idx] == img_url:
                feat = existing_features[idx]
                new_features.append(feat)
                new_names.append(existing_names[idx] if idx < len(existing_names) else name)
                new_urls.append(img_url)
                new_ids.append(pid)
                reused = True

        if not reused:
            preprocessed_img = preprocess_image(img_url)
            features = extract_features(model, preprocessed_img)
            if features is not None:
                new_features.append(features)
                new_names.append(name)
                new_urls.append(img_url)
                new_ids.append(pid)
            else:
                print(f"Skipping product id {pid} image: {img_url}")

    conn.close()

    if len(new_features) == 0:
        # ensure at least an empty array to avoid issues
        all_features = np.zeros((0, model.output_shape[1]*model.output_shape[2]*model.output_shape[3])) if hasattr(model.output_shape, '__len__') else np.array([])
    else:
        all_features = np.vstack(new_features)

    # persist cache
    try:
        np.save(FEATURES_PATH, all_features)
        with open(NAMES_PATH, 'w') as f:
            json.dump(new_names, f)
        with open(URLS_PATH, 'w') as f:
            json.dump(new_urls, f)
        with open(IDS_PATH, 'w') as f:
            json.dump(new_ids, f)
        print(f"Extracted and saved features for {len(new_ids)} products.")
    except Exception as e:
        print(f"Error saving feature cache: {e}")

    return all_features, new_names, new_urls, new_ids

def ensure_features_exist():
    """
    Ensure that feature cache exists (or create/update it from DB).
    """
    # Always attempt to sync cache with DB to pick up new/removed products
    extract_all_features_from_db()

def load_catalog_features():
    """
    Loads features, names, urls and ids, extracting from DB if needed.
    Returns: (features, names, urls, ids)
    """
    ensure_features_exist()
    all_features = np.load(FEATURES_PATH)
    with open(URLS_PATH, 'r') as f:
        all_image_urls = json.load(f)
    with open(NAMES_PATH, 'r') as f:
        all_image_names = json.load(f)
    with open(IDS_PATH, 'r') as f:
        all_image_ids = json.load(f)
    return all_features, all_image_names, all_image_urls, all_image_ids

def recommend_from_image(query_img_url, top_k=5):
    all_features, all_image_names, all_image_urls, all_image_ids = load_catalog_features()
    query_preprocessed = preprocess_image(query_img_url)
    if query_preprocessed is None:
        print(f"Could not process query image: {query_img_url}")
        return []
    query_features = extract_features(model, query_preprocessed)
    if query_features is None:
        print(f"Could not extract features from query image: {query_img_url}")
        return []
    if all_features.size == 0:
        return []
    similarities = cosine_similarity([query_features], all_features)[0]
    top_indices = similarities.argsort()[-top_k:][::-1]
    recommendations = []
    for idx in top_indices:
        recommendations.append({
            "product_id": int(all_image_ids[idx]),
            "name": all_image_names[idx],
            "image_url": all_image_urls[idx]
            # "similarity": float(similarities[idx])
        })
    return recommendations
# Example usage:
# query_image_url = "https://example.com/path/to/query/image.jpg"
# recommendations = recommend_from_image(query_image_url, top_k=5)
# for rec in recommendations:
#     print(rec)
#         and `input_tensor` is `None`.
#     if include_top and classifier_activation not in {None, "softmax"}:
#         raise ValueError(
#             "If using `include_top` with `weights='imagenet'`, "
#             "`classifier_activation` should be `None` or ""'softmax'. "
#             f"Received: classifier_activation={classifier_activation}"
#         )