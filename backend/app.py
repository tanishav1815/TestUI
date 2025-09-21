from flask import Flask, jsonify, request, g
from flask_cors import CORS
import sqlite3
import os
import random
from pathlib import Path

app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'app.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    # create tables
    cur.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        price TEXT,
        image TEXT
    )
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS swipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        action TEXT CHECK(action IN ('like','dislike')) NOT NULL,
        user_id TEXT,
        item_image TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    db.commit()

    # seed items if empty
    cur.execute('SELECT COUNT(1) as c FROM items')
    if cur.fetchone()['c'] == 0:
        sample = [
            (1, 'Red Sneakers', '$79', 'https://picsum.photos/seed/1/800/600'),
            (2, 'Blue Jacket', '$129', 'https://picsum.photos/seed/2/800/600'),
            (3, 'Classic Watch', '$199', 'https://picsum.photos/seed/3/800/600'),
            (4, 'Sunglasses', '$59', 'https://picsum.photos/seed/4/800/600'),
            (5, 'Leather Bag', '$249', 'https://picsum.photos/seed/5/800/600'),
        ]
        cur.executemany('INSERT INTO items(id,name,price,image) VALUES (?,?,?,?)', sample)
        db.commit()
    # create users table and seed a sample user if empty
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    db.commit()
    cur.execute('SELECT COUNT(1) as c FROM users')
    if cur.fetchone()['c'] == 0:
        cur.execute('INSERT INTO users(id,name) VALUES (?,?)', ('user123','Demo User'))
        db.commit()
    # create products table and seed from data/products.json if present
    cur.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        price TEXT,
        image TEXT,
        category TEXT,
        color TEXT,
        location TEXT,
        price_num REAL
    )
    ''')
    db.commit()
    # Ensure products table has new columns if upgrading old DB
    cur.execute("PRAGMA table_info(products)")
    prod_cols = [r['name'] for r in cur.fetchall()]
    if 'color' not in prod_cols:
        try:
            cur.execute("ALTER TABLE products ADD COLUMN color TEXT")
        except Exception:
            pass
    if 'location' not in prod_cols:
        try:
            cur.execute("ALTER TABLE products ADD COLUMN location TEXT")
        except Exception:
            pass
    if 'price_num' not in prod_cols:
        try:
            cur.execute("ALTER TABLE products ADD COLUMN price_num REAL")
        except Exception:
            pass
    db.commit()
    # try to load dataset file and upsert into products
    data_file = BASE_DIR / 'data' / 'products.json'
    if data_file.exists():
        import json
        with open(data_file, 'r') as f:
            items = json.load(f)
        for p in items:
            # upsert using SQLite INSERT OR REPLACE
            # parse numeric price if available
            def parse_price_num(val):
                try:
                    if val is None:
                        return None
                    s = str(val).strip()
                    # remove common currency symbols and commas
                    s = s.replace('$','').replace('₹','').replace('£','').replace(',','')
                    # keep digits and dot
                    import re
                    m = re.findall(r"[0-9]+(?:\.[0-9]+)?", s)
                    if not m:
                        return None
                    return float(m[0])
                except Exception:
                    return None

            price_num = parse_price_num(p.get('price'))
            cur.execute('INSERT OR REPLACE INTO products(id,name,price,image,category,color,location,price_num) VALUES (?,?,?,?,?,?,?,?)',
                        (p.get('id'), p.get('name'), p.get('price'), p.get('image'), p.get('category'), p.get('color'), p.get('location'), price_num))
        db.commit()
        # import CSVs from backend/Datasets if present
        datasets_dir = BASE_DIR / 'Datasets'
        if datasets_dir.exists() and datasets_dir.is_dir():
            import csv
            # determine current max id to generate ids when missing
            cur.execute('SELECT IFNULL(MAX(id), 0) as m FROM products')
            max_id = cur.fetchone()['m'] or 0
            next_id = max_id + 1
            for csvf in sorted(datasets_dir.glob('*.csv')):
                with open(csvf, newline='') as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        # normalized fields
                        pid = row.get('id') or row.get('product_id') or ''
                        try:
                            pid = int(pid) if str(pid).strip()!='' else None
                        except Exception:
                            pid = None
                        if pid is None:
                            pid = next_id
                            next_id += 1
                        name = row.get('name') or row.get('title') or f'Product {pid}'
                        price = row.get('price') or row.get('cost') or ''
                        image = row.get('image') or row.get('image_url') or ''
                        category = row.get('category') or ''
                        color = row.get('color') or ''
                        location = row.get('location') or ''
                        # parse numeric price
                        def parse_price_num_local(val):
                            try:
                                if val is None:
                                    return None
                                s = str(val).strip()
                                s = s.replace('$','').replace('₹','').replace('£','').replace(',','')
                                import re
                                m = re.findall(r"[0-9]+(?:\.[0-9]+)?", s)
                                if not m:
                                    return None
                                return float(m[0])
                            except Exception:
                                return None

                        price_num = parse_price_num_local(price)
                        cur.execute('INSERT OR REPLACE INTO products(id,name,price,image,category,color,location,price_num) VALUES (?,?,?,?,?,?,?,?)',
                                    (pid, name, price, image, category, color, location, price_num))
            db.commit()
    
    # sync products into items table for backward compatibility
    cur.execute('SELECT id,name,price,image FROM products')
    prod_rows = cur.fetchall()
    if prod_rows:
        # clear items and repopulate from products
        cur.execute('DELETE FROM items')
        cur.executemany('INSERT INTO items(id,name,price,image) VALUES (?,?,?,?)', [(r['id'], r['name'], r['price'], r['image']) for r in prod_rows])
        db.commit()
    # Migrate swipes table if missing new columns (user_id, item_image)
    cur.execute("PRAGMA table_info(swipes)")
    cols = [r['name'] for r in cur.fetchall()]
    if 'user_id' not in cols:
        cur.execute("ALTER TABLE swipes ADD COLUMN user_id TEXT")
    if 'item_image' not in cols:
        cur.execute("ALTER TABLE swipes ADD COLUMN item_image TEXT")
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def fetch_recommendations(limit=10, user_id=None, category=None, color=None, location=None, min_price=None, max_price=None):
    db = get_db()
    cur = db.cursor()
    # Common filters: category, color, location, min_price, max_price
    def build_filters(category, color, location, min_price, max_price):
        clauses = []
        params = []
        if category:
            clauses.append('p.category = ?')
            params.append(category)
        if color:
            clauses.append('p.color = ?')
            params.append(color)
        if location:
            clauses.append('p.location = ?')
            params.append(location)
        if min_price is not None:
            clauses.append('p.price_num >= ?')
            params.append(min_price)
        if max_price is not None:
            clauses.append('p.price_num <= ?')
            params.append(max_price)
        if clauses:
            return 'WHERE ' + ' AND '.join(clauses), tuple(params)
        return '', ()

    # Build filters using passed parameters
    filter_where, filter_params = build_filters(category, color, location, min_price, max_price)

    if not user_id:
        # Global ordering by score (likes - dislikes)
        sql = f'''
        SELECT p.id, p.name, p.price, p.image, p.category, p.color, p.location, p.price_num,
            IFNULL(SUM(CASE WHEN s.action='like' THEN 1 WHEN s.action='dislike' THEN -1 ELSE 0 END), 0) as score
        FROM products p
        LEFT JOIN swipes s ON s.item_id = p.id
        {filter_where}
        GROUP BY p.id
        ORDER BY score DESC, RANDOM()
        LIMIT ?
        '''
        params = tuple(filter_params) + (limit,)
        cur.execute(sql, params)
        rows = cur.fetchall()
        items = [dict(r) for r in rows]
        return items

    # Personalized recommendations: combine global score, user's item score, and user's category affinity
    # Apply same filters as global selection
    filter_where_personal = filter_where

    sql = f'''
    WITH user_cat AS (
        SELECT p.category as category, COUNT(*) as likes
        FROM swipes s JOIN products p ON s.item_id = p.id
        WHERE s.user_id = ? AND s.action = 'like'
        GROUP BY p.category
    ),
    user_item AS (
        SELECT item_id,
            SUM(CASE WHEN action='like' THEN 1 WHEN action='dislike' THEN -1 ELSE 0 END) as user_score
        FROM swipes WHERE user_id = ? GROUP BY item_id
    ),
    global_score AS (
        SELECT item_id,
            SUM(CASE WHEN action='like' THEN 1 WHEN action='dislike' THEN -1 ELSE 0 END) as gscore
        FROM swipes GROUP BY item_id
    )
    SELECT p.id, p.name, p.price, p.image, p.category,
        IFNULL(g.gscore,0) as global_score,
        IFNULL(u.user_score,0) as user_score,
        IFNULL(uc.likes,0) as cat_likes,
        (IFNULL(g.gscore,0) + IFNULL(u.user_score,0)*2 + IFNULL(uc.likes,0)*1) as score
    FROM products p
    LEFT JOIN global_score g ON g.item_id = p.id
    LEFT JOIN user_item u ON u.item_id = p.id
    LEFT JOIN user_cat uc ON uc.category = p.category
    {filter_where_personal}
    ORDER BY score DESC, RANDOM()
    LIMIT ?
    '''
    params = [user_id, user_id]
    # append filter params in same order as build_filters returned
    if filter_params:
        params.extend(filter_params)
    params.append(limit)
    params = tuple(params)
    cur.execute(sql, params)
    rows = cur.fetchall()
    items = [dict(r) for r in rows]
    return items

@app.route('/recommendations')
def recommendations():
    user_id = request.args.get('user_id')
    category = request.args.get('category')
    color = request.args.get('color')
    location = request.args.get('location')
    try:
        min_price = float(request.args.get('min_price')) if request.args.get('min_price') is not None else None
    except Exception:
        min_price = None
    try:
        max_price = float(request.args.get('max_price')) if request.args.get('max_price') is not None else None
    except Exception:
        max_price = None
    items = fetch_recommendations(limit=10, user_id=user_id, category=category, color=color, location=location, min_price=min_price, max_price=max_price)
    return jsonify({"items": items})


@app.route('/categories')
def categories():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category <> '' ORDER BY category")
    rows = cur.fetchall()
    cats = [r['category'] for r in rows]
    return jsonify({"categories": cats})

@app.route('/swipe', methods=['POST'])
def swipe():

    data = request.get_json() or {}
    action = data.get('action')
    # Accept either { action, item } or { action, item_id, image, user_id }
    item = data.get('item') or {}
    item_id = item.get('id') or data.get('item_id')
    item_image = item.get('image') or data.get('image') or data.get('item_image')
    user_id = data.get('user_id')
    if action not in ('like','dislike') or item_id is None:
        return jsonify({"error":"invalid payload"}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute('INSERT INTO swipes(item_id, action, user_id, item_image) VALUES (?,?,?,?)', (item_id, action, user_id, item_image))
    db.commit()
    return jsonify({"status":"ok"})

if __name__ == '__main__':
    # ensure DB folder exists
    os.makedirs(BASE_DIR, exist_ok=True)
    # initialize DB if needed
    with app.app_context():
        init_db()
    # allow overriding port via environment for easy local testing
    port = int(os.getenv('PORT', '5001'))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('FLASK_DEBUG', '1') in ('1','true','True')
    app.run(host=host, port=port, debug=debug)
