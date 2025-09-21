import os
import json

USER_FEEDBACK_PATH = 'Models/user_preference.json'


def _load_feedback():
    if os.path.exists(USER_FEEDBACK_PATH):
        with open(USER_FEEDBACK_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_feedback(feedback):
    os.makedirs(os.path.dirname(USER_FEEDBACK_PATH), exist_ok=True)
    with open(USER_FEEDBACK_PATH, 'w', encoding='utf-8') as f:
        json.dump(feedback, f)


def _extract_reasons(product):
    # Extracts key attributes for dislike reasons
    # You can expand this list as needed
    reasons = {}
    for attr in ["category", "current_color", "style", "pattern", "brand"]:
        val = product.get(attr)
        if val:
            reasons[attr] = val
    return reasons


def _extract_liked_reasons(product):
    # Extracts key attributes for like reasons
    reasons = {}
    for attr in ["category", "current_color", "style", "pattern", "brand"]:
        val = product.get(attr)
        if val:
            reasons[attr] = val
    return reasons


def add_liked_product(user_id, product, key='name'):
    feedback = _load_feedback()
    user_data = feedback.get(user_id, {"products": [], "reasons": {}, "liked_products": [], "liked_reasons": {}})
    prod_val = product.get(key)
    if prod_val and prod_val not in user_data.get("liked_products", []):
        user_data.setdefault("liked_products", []).append(prod_val)
    # Extract and store liked reasons
    liked_reasons = _extract_liked_reasons(product)
    for attr, val in liked_reasons.items():
        if attr not in user_data.get("liked_reasons", {}):
            user_data.setdefault("liked_reasons", {})[attr] = []
        if val not in user_data["liked_reasons"][attr]:
            user_data["liked_reasons"][attr].append(val)
    feedback[user_id] = user_data
    _save_feedback(feedback)


def _concise_dislike_reasons(user_data):
    # Remove dislike reasons that are also liked
    concise = {}
    for attr, vals in user_data.get("reasons", {}).items():
        liked_vals = set(user_data.get("liked_reasons", {}).get(attr, []))
        concise[attr] = [v for v in vals if v not in liked_vals]
    return concise


def add_disliked_product(user_id, product, key='name'):
    feedback = _load_feedback()
    user_data = feedback.get(user_id, {"products": [], "reasons": {}, "liked_products": [], "liked_reasons": {}})
    prod_val = product.get(key)
    if prod_val and prod_val not in user_data["products"]:
        user_data["products"].append(prod_val)
    # Extract and store reasons
    reasons = _extract_reasons(product)
    for attr, val in reasons.items():
        if attr not in user_data["reasons"]:
            user_data["reasons"][attr] = []
        if val not in user_data["reasons"][attr]:
            user_data["reasons"][attr].append(val)
    # Concise dislike reasons by removing overlaps with liked reasons
    user_data["reasons"] = _concise_dislike_reasons(user_data)
    feedback[user_id] = user_data
    _save_feedback(feedback)


def get_exclude_list(user_id, recommender=None, expand_similar=False, top_k=3, key='name', all_products=None):
    feedback = _load_feedback()
    user_data = feedback.get(user_id, {"products": [], "reasons": {}})
    exclude_list = list(user_data["products"])
    # Exclude by reasons (attributes)
    if all_products:
        for prod in all_products:
            for attr, vals in user_data["reasons"].items():
                if prod.get(attr) in vals and prod.get(key) not in exclude_list:
                    exclude_list.append(prod.get(key))
    if expand_similar and recommender is not None:
        for prod_val in user_data["products"]:
            similar = recommender.recommend(prod_val, top_k=top_k)
            for sim_prod in similar:
                sim_val = sim_prod.get(key)
                if sim_val and sim_val not in exclude_list:
                    exclude_list.append(sim_val)
    return exclude_list
