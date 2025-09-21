import os
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from Utilities.Products import read_all_products_by_category
from Models.user_feedback import get_exclude_list

class NLPRecommender:
    def __init__(self, model_name='all-MiniLM-L6-v2',
                 products_path='Models/all_products.json',
                 embeddings_path='Models/all_product_embeddings.npy'):
        self.model = SentenceTransformer(model_name)
        self.products_path = products_path
        self.embeddings_path = embeddings_path
        if os.path.exists(self.products_path) and os.path.exists(self.embeddings_path):
            with open(self.products_path, 'r', encoding='utf-8') as f:
                self.products = json.load(f)
            self.embeddings = np.load(self.embeddings_path)
            self.product_texts = [self._product_text(p) for p in self.products]
        else:
            self.products = self._load_products()
            self.product_texts = [self._product_text(p) for p in self.products]
            self.embeddings = self.model.encode(self.product_texts, show_progress_bar=True)
            # Ensure the directory exists before saving
            os.makedirs(os.path.dirname(self.products_path), exist_ok=True)
            with open(self.products_path, 'w', encoding='utf-8') as f:
                json.dump(self.products, f)
            np.save(self.embeddings_path, self.embeddings)

    def _load_products(self):
        # Flatten all products from all categories into a single list
        category_dict = read_all_products_by_category()
        products = []
        for plist in category_dict.values():
            products.extend(plist)
        return products

    def _product_text(self, product):
        # Combine name, category, and other fields for richer embedding
        name = product.get('name', '')
        category = product.get('category', '')
        desc = product.get('description', '')
        return f"{name} {category} {desc}".strip()

    def nlp_recommend(self, query, top_k=5, exclude_list=None, exclude_key='name', user_id=None, use_user_feedback=True):
        # If user_id is provided, get exclude_list from user_feedback
        if user_id and use_user_feedback:
            exclude_list = get_exclude_list(user_id, all_products=self.products)
        query_emb = self.model.encode([query])[0]
        sims = np.dot(self.embeddings, query_emb) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_emb) + 1e-8)
        top_idx = np.argsort(sims)[::-1]
        results = []
        exclude_set = set(x.lower() for x in exclude_list) if exclude_list else set()
        for i in top_idx:
            prod = self.products[i]
            prod_val = str(prod.get(exclude_key, '')).lower()
            if prod_val in exclude_set:
                continue
            results.append(prod)
            if len(results) >= top_k:
                break
        return results

if __name__ == "__main__":
    recommender = NLPRecommender()
    user_id = input("Enter user id (or leave blank): ")
    query = input("Enter a product name or description: ")
    if user_id:
        results = recommender.nlp_recommend(query, top_k=5, user_id=user_id)
    else:
        exclude = input("Enter comma-separated product names to exclude (or leave blank): ")
        exclude_list = [x.strip() for x in exclude.split(',')] if exclude else None
        results = recommender.nlp_recommend(query, top_k=5, exclude_list=exclude_list)
    print("Top recommendations:")
    for prod in results:
        print(f"- {prod.get('name')} | Category: {prod.get('category', 'N/A')} | URL: {prod.get('image_url', prod.get('url', ''))}")
