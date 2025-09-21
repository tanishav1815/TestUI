import json
import os


class User:
    def __init__(self, id, username, email):
        self.username = username
        self.user_id = id
        self.email = email

    def get_info(self):
        return f"User_id: {self.user_id}, Username: {self.username}, Email: {self.email}"

    def update_likes(self, product_id, product_description):
        # Ensure the preference file exists
        if not os.path.exists('user_preference.json'):
            with open('user_preference.json', 'w') as f:
                json.dump({}, f)
        with open('user_preference.json', 'r') as f:
            users = json.load(f)
        if self.user_id not in users:
            users[self.user_id] = {"liked_products": [product_description], "disliked_products": []}
        else:
            users[self.user_id]["liked_products"].append(product_description)
        with open('user_preference.json', 'w') as f:
            json.dump(users, f)

    def update_dislikes(self, product_id, product_description):
        # Ensure the preference file exists
        if not os.path.exists('user_preference.json'):
            with open('user_preference.json', 'w') as f:
                json.dump({}, f)
        with open('user_preference.json', 'r') as f:
            users = json.load(f)
        if self.user_id not in users:
            users[self.user_id] = {"liked_products": [], "disliked_products": [product_description]}
        else:
            users[self.user_id]["disliked_products"].append(product_description)
        with open('user_preference.json', 'w') as f:
            json.dump(users, f)