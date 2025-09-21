import os
import sqlite3

# Always use the main backend/app.db, not Utilities/app.db
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.db')

def read_products():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM products')
    products = [dict(row) for row in cur.fetchall()]
    conn.close()
    return products

def infer_category(name):
    name = name.lower()
    categories = [
        ("bra", ["bra"]),
        ("legging", ["legging", "tights"]),
        ("skirt", ["skirt"]),
        ("bomber", ["bomber", "jacket"]),
        ("hoodie", ["hoodie"]),
        ("pullover", ["pullover", "sweatshirt"]),
        ("shorts", ["shorts"]),
        ("tee", ["tee", "t-shirt", "shirt"]),
        ("vest", ["vest"]),
        ("trouser", ["trouser", "pant", "pants"]),
        ("swimsuit", ["swimsuit", "one-piece"]),
        ("bikini", ["bikini"]),
        ("dress", ["dress"]),
        ("suit", ["suit"]),
        ("jacket", ["jacket"]),
        ("sweatpant", ["sweatpant"]),
        ("coverup", ["coverup"]),
        ("pajama", ["pajama"]),
        ("top", ["top"]),
        ("tank", ["tank"]),
        ("crop", ["crop"]),
        ("outerwear", ["outerwear"]),
        ("activewear", ["activewear"]),
        ("sleepwear", ["sleepwear"]),
        ("lingerie", ["lingerie"]),
        ("sweater", ["sweater"]),
        ("coat", ["coat"]),
        ("blazer", ["blazer"]),
        ("jeans", ["jeans"]),
        ("denim", ["denim"]),
        ("romper", ["romper"]),
        ("jumpsuit", ["jumpsuit"]),
        ("cardigan", ["cardigan"]),
        ("windbreaker", ["windbreaker"]),
        ("puffer", ["puffer"]),
    ]
    for cat, keywords in categories:
        for kw in keywords:
            if kw in name:
                return cat
    return "other"

def read_all_products_by_category():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM products')
    products = [dict(row) for row in cur.fetchall()]
    conn.close()
    category_dict = {}
    for product in products:
        name = product.get('name') or product.get('product_name')
        if not name:
            continue
        category = infer_category(name)
        if category not in category_dict:
            category_dict[category] = []
        category_dict[category].append(product)
    return category_dict
