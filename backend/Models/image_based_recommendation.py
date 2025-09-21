import os
import json
import numpy as np
import pandas as pd
# Try to import TensorFlow/Keras; if unavailable, we'll fallback to imagehash
try:
    from tensorflow.keras.applications.vgg16 import VGG16, preprocess_input
    from tensorflow.keras.models import Model
    from tensorflow.keras.preprocessing import image
    from sklearn.metrics.pairwise import cosine_similarity
    TF_AVAILABLE = True
except Exception:
    TF_AVAILABLE = False
    # will use imagehash fallback
from PIL import Image
from io import BytesIO
import urllib.request
import concurrent.futures
import time

# Define BASE_DIR and progress path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROGRESS_PATH = os.path.join(BASE_DIR, "../Models/feature_progress.json")

# Load VGG16 model for feature extraction
if TF_AVAILABLE:
    base_model = VGG16(weights='imagenet', include_top=False)
    model = Model(inputs=base_model.input, outputs=base_model.output)
else:
    model = None
    print('TensorFlow unavailable — image-based recommender will use phash fallback')

try:
    from imagehash import phash
    import numpy as np
    IMAGEHASH_AVAILABLE = True
except Exception:
    IMAGEHASH_AVAILABLE = False

FEATURES_PATH = os.path.join(BASE_DIR, "../Models/all_features.npy")
NAMES_PATH = os.path.join(BASE_DIR, "../Models/all_image_names.json")
URLS_PATH = os.path.join(BASE_DIR, "../Models/all_image_urls.json")
IDS_PATH = os.path.join(BASE_DIR, "../Models/all_image_ids.json")
DB_PATH = os.path.join(BASE_DIR, "..", "app.db")

def preprocess_image(img_url):
    # download and preprocess a single image URL with simple retry/backoff
    if not img_url:
        return None
    backoff = 1.0
    for attempt in range(3):
        try:
            with urllib.request.urlopen(img_url, timeout=10) as url_response:
                img_data = url_response.read()
                img = Image.open(BytesIO(img_data)).convert('RGB')
                img = img.resize((224, 224))
                if TF_AVAILABLE:
                    img_array = image.img_to_array(img)
                    img_array_expanded = np.expand_dims(img_array, axis=0)
                    return preprocess_input(img_array_expanded)
                else:
                    # return PIL Image for phash fallback
                    return img
        except Exception as e:
            print(f"Attempt {attempt+1}: Error loading image from {img_url}: {e}")
            time.sleep(backoff)
            backoff *= 2
    return None

def extract_features(model, preprocessed_img):
    if preprocessed_img is None:
        return None
    if TF_AVAILABLE and model is not None:
        features = model.predict(preprocessed_img)
        flattened_features = features.flatten()
        normalized_features = flattened_features / np.linalg.norm(flattened_features)
        return normalized_features
    # fallback: use imagehash.phash on PIL image stored in preprocessed_img (we need raw bytes)
    if IMAGEHASH_AVAILABLE:
        try:
            # preprocess_image for phash will return raw bytes instead of array in fallback mode
            # here preprocessed_img is actual PIL Image in that fallback case
            h = phash(preprocessed_img)
            # convert hash to numpy vector of bits
            bits = np.array([(h.hash >> i) & 1 for i in range(h.hash.size)], dtype=np.float32)
            return bits
        except Exception:
            return None
    return None

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

    # prepare work items
    tasks = []
    for r in rows:
        pid = int(r['id'])
        name = r['name'] or ''
        img_url = r['image'] or ''
        tasks.append((pid, name, img_url))

    total = len(tasks)
    processed = 0
    # write initial progress
    try:
        with open(PROGRESS_PATH, 'w') as pf:
            json.dump({'status':'running','total':total,'processed':0,'last':None}, pf)
    except Exception:
        pass

    # first, determine which we can reuse
    reuse_map = {}
    for pid, name, img_url in tasks:
        if existing_features is not None and pid in id_to_index:
            idx = id_to_index[pid]
            if idx < len(existing_urls) and existing_urls[idx] == img_url:
                reuse_map[pid] = {
                    'feature': existing_features[idx],
                    'name': existing_names[idx] if idx < len(existing_names) else name,
                    'url': img_url
                }

    # prepare list of items that need extraction
    to_extract = [(pid,name,img_url) for (pid,name,img_url) in tasks if pid not in reuse_map]

    new_features = []
    new_names = []
    new_urls = []
    new_ids = []

    # reuse existing first (preserve order by rows)
    for pid, name, img_url in tasks:
        if pid in reuse_map:
            entry = reuse_map[pid]
            new_features.append(entry['feature'])
            new_names.append(entry['name'])
            new_urls.append(entry['url'])
            new_ids.append(pid)
        else:
            new_features.append(None)  # placeholder to keep indices aligned
            new_names.append(name)
            new_urls.append(img_url)
            new_ids.append(pid)

    # download and preprocess images in parallel, but run model.predict in a single batch
    preprocessed_list = [None] * len(new_ids)
    index_map = {pid: idx for idx, pid in enumerate(new_ids)}

    def fetch_preprocess(item):
        pid, name, img_url = item
        return (pid, preprocess_image(img_url))

    if to_extract:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(fetch_preprocess, it): it for it in to_extract}
            for fut in concurrent.futures.as_completed(futures):
                pid, pre = fut.result()
                idx = index_map.get(pid)
                if idx is not None:
                    preprocessed_list[idx] = pre
                processed += 1
                # update progress
                try:
                    with open(PROGRESS_PATH, 'w') as pf:
                        json.dump({'status':'running','total':total,'processed':processed,'last':pid}, pf)
                except Exception:
                    pass

    # now run feature extraction with model.predict for non-empty preprocessed entries
    batch_inputs = []
    batch_idxs = []
    for idx, pre in enumerate(preprocessed_list):
        if pre is not None:
            batch_inputs.append(pre)
            batch_idxs.append(idx)

    if batch_inputs:
        try:
            # stack inputs and run predict in one batch
            X = np.vstack(batch_inputs)
            feats = model.predict(X)
            # flatten each feature and normalize
            for i, feat in enumerate(feats):
                flat = feat.flatten()
                norm = flat / np.linalg.norm(flat) if np.linalg.norm(flat) != 0 else flat
                target_idx = batch_idxs[i]
                new_features[target_idx] = norm
        except Exception as e:
            print('Error during batch feature extraction:', e)

    # Any entries still None (failed loads) will be skipped
    final_features = []
    final_names = []
    final_urls = []
    final_ids = []
    for idx, feat in enumerate(new_features):
        if feat is None:
            # skip
            continue
        final_features.append(feat)
        final_names.append(new_names[idx])
        final_urls.append(new_urls[idx])
        final_ids.append(new_ids[idx])

    # update progress to complete
    try:
        with open(PROGRESS_PATH, 'w') as pf:
            json.dump({'status':'done','total':total,'processed':total,'last':None}, pf)
    except Exception:
        pass

    conn.close()

    if len(final_features) == 0:
        all_features = np.zeros((0, model.output_shape[1]*model.output_shape[2]*model.output_shape[3])) if hasattr(model.output_shape, '__len__') else np.array([])
    else:
        all_features = np.vstack(final_features)

    # persist cache
    try:
        np.save(FEATURES_PATH, all_features)
        with open(NAMES_PATH, 'w') as f:
            json.dump(final_names, f)
        with open(URLS_PATH, 'w') as f:
            json.dump(final_urls, f)
        with open(IDS_PATH, 'w') as f:
            json.dump(final_ids, f)
        print(f"Extracted and saved features for {len(final_ids)} products.")
    except Exception as e:
        print(f"Error saving feature cache: {e}")

    return all_features, final_names, final_urls, final_ids

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