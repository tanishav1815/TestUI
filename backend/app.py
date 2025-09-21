from flask import Flask, jsonify, request, g
from flask_cors import CORS
import sqlite3
import os
import random
from pathlib import Path
from uuid import uuid4
from Models.image_based_recommendation import recommend_from_image
# image_based_recommender uses numpy, keras, etc. Make import optional so the
# server can start even if those heavy dependencies aren't installed in dev.
try:
    from Models import image_based_recommendation
except Exception as e:
    image_based_recommendation = None
    print('Warning: image_based_recommendation disabled -', e)

# NLP recommender (optional) - similar opt-in import
try:
    from Models.nlp_recommender import NLPRecommender
    try:
        _nlp = NLPRecommender()
    except Exception as _e:
        print('Warning: failed to instantiate NLPRecommender -', _e)
        _nlp = None
except Exception as e:
    _nlp = None
    # keep going if sentence-transformers not installed
    print('Warning: NLP recommender disabled -', e)

import threading

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
    # Remove hardcoded index creation and sample items insert
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
    if 'gender' not in prod_cols:
        try:
            cur.execute("ALTER TABLE products ADD COLUMN gender TEXT")
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
            # bookkeeping table to avoid re-importing the same file repeatedly
            cur.execute('CREATE TABLE IF NOT EXISTS imported_files (filename TEXT PRIMARY KEY, mtime REAL)')
            db.commit()
            # determine current max id to generate ids when missing
            cur.execute('SELECT IFNULL(MAX(id), 0) as m FROM products')
            max_id = cur.fetchone()['m'] or 0
            next_id = max_id + 1
            for csvf in sorted(datasets_dir.glob('*.csv')):
                try:
                    mtime = csvf.stat().st_mtime
                except Exception:
                    mtime = None
                # skip file if it was already imported with same mtime
                skip_file = False
                if mtime is not None:
                    cur.execute('SELECT mtime FROM imported_files WHERE filename = ?', (csvf.name,))
                    row_m = cur.fetchone()
                    if row_m and row_m['mtime'] == mtime:
                        skip_file = True
                if skip_file:
                    continue

                with open(csvf, newline='') as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        # normalized fields
                        pid = row.get('id') or row.get('product_id') or ''
                        try:
                            pid = int(pid) if str(pid).strip()!='' else None
                        except Exception:
                            pid = None
                        name = row.get('name') or row.get('title') or ''
                        price = row.get('price') or row.get('cost') or ''
                        image = (row.get('image') or row.get('image_url') or '').strip()
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

                        # if pid not provided, try to find an existing product by image or exact name+price
                        if pid is None:
                            pid = None
                            if image:
                                cur.execute('SELECT id FROM products WHERE image = ? LIMIT 1', (image,))
                                prow = cur.fetchone()
                                if prow:
                                    pid = prow['id']
                            if pid is None and name:
                                cur.execute('SELECT id FROM products WHERE name = ? AND price = ? LIMIT 1', (name, price))
                                prow = cur.fetchone()
                                if prow:
                                    pid = prow['id']
                            if pid is None:
                                pid = next_id
                                next_id += 1

                        cur.execute('INSERT OR REPLACE INTO products(id,name,price,image,category,color,location,price_num) VALUES (?,?,?,?,?,?,?,?)',
                                    (pid, name or f'Product {pid}', price, image, category, color, location, price_num))

                # record the import so we won't reprocess unchanged files
                try:
                    cur.execute('INSERT OR REPLACE INTO imported_files(filename, mtime) VALUES (?,?)', (csvf.name, mtime))
                    db.commit()
                except Exception:
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
    # Helper: get set of swiped product ids for user
    def get_swiped_ids(user_id):
        cur.execute('SELECT DISTINCT item_id FROM swipes WHERE user_id = ?', (user_id,))
        return set([row['item_id'] for row in cur.fetchall()])

    # Helper: get liked categories for user, sorted by like count desc
    def get_liked_categories(user_id):
        cur.execute('''
            SELECT p.category, COUNT(*) as cnt
            FROM swipes s JOIN products p ON s.item_id = p.id
            WHERE s.user_id = ? AND s.action = 'like' AND p.category IS NOT NULL AND p.category != ''
            GROUP BY p.category
            ORDER BY cnt DESC
        ''', (user_id,))
        return [row['category'] for row in cur.fetchall()]

    # Build filters
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

    # If no user, fallback to global logic
    if not user_id:
        filter_where, filter_params = build_filters(category, color, location, min_price, max_price)
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

    # Personalized logic
    swiped_ids = get_swiped_ids(user_id)
    liked_cats = get_liked_categories(user_id)
    result = []
    used_ids = set()

    # 1. Recommend from liked categories, not yet swiped
    for cat in liked_cats:
        filter_where, filter_params = build_filters(cat, color, location, min_price, max_price)
        sql = f"""
        SELECT p.id, p.name, p.price, p.image, p.category, p.color, p.location, p.price_num
        FROM products p
        {filter_where}
        """
        cur.execute(sql, filter_params)
        for row in cur.fetchall():
            if row['id'] not in swiped_ids and row['id'] not in used_ids:
                result.append(dict(row))
                used_ids.add(row['id'])
            if len(result) >= limit:
                return result[:limit]

    # 2. If not enough, recommend from other categories, not yet swiped
    filter_where, filter_params = build_filters(None, color, location, min_price, max_price)
    sql = f"""
    SELECT p.id, p.name, p.price, p.image, p.category, p.color, p.location, p.price_num
    FROM products p
    {filter_where}
    """
    cur.execute(sql, filter_params)
    for row in cur.fetchall():
        if row['id'] not in swiped_ids and row['id'] not in used_ids:
            result.append(dict(row))
            used_ids.add(row['id'])
        if len(result) >= limit:
            return result[:limit]

    # 3. If still not enough, recommend from liked categories (even if swiped)
    for cat in liked_cats:
        filter_where, filter_params = build_filters(cat, color, location, min_price, max_price)
        sql = f"""
        SELECT p.id, p.name, p.price, p.image, p.category, p.color, p.location, p.price_num
        FROM products p
        {filter_where}
        """
        cur.execute(sql, filter_params)
        for row in cur.fetchall():
            if row['id'] not in used_ids:
                result.append(dict(row))
                used_ids.add(row['id'])
            if len(result) >= limit:
                return result[:limit]

    # 4. Fallback: recommend any products (even if swiped)
    filter_where, filter_params = build_filters(None, color, location, min_price, max_price)
    sql = f"""
    SELECT p.id, p.name, p.price, p.image, p.category, p.color, p.location, p.price_num
    FROM products p
    {filter_where}
    """
    cur.execute(sql, filter_params)
    for row in cur.fetchall():
        if row['id'] not in used_ids:
            result.append(dict(row))
            used_ids.add(row['id'])
        if len(result) >= limit:
            return result[:limit]

    # If still empty, re-roll: return a random sample of products (including already swiped/used ones)
    cur.execute('SELECT id, name, price, image, category, color, location, price_num FROM products ORDER BY RANDOM() LIMIT ?', (limit,))
    rows = cur.fetchall()
    return [dict(r) for r in rows]

    # Always return at least some products (never empty)
    # return result[:limit] if result else []

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


@app.route('/search')
def search():
    q = (request.args.get('q') or '').strip()
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

    db = get_db()
    cur = db.cursor()
    clauses = []
    params = []
    if q:
        clauses.append("(name LIKE ? OR category LIKE ? OR color LIKE ? OR location LIKE ?)")
        like_q = f"%{q}%"
        params.extend([like_q, like_q, like_q, like_q])
    if color:
        clauses.append('color = ?')
        params.append(color)
    if location:
        clauses.append('location = ?')
        params.append(location)
    if min_price is not None:
        clauses.append('price_num >= ?')
        params.append(min_price)
    if max_price is not None:
        clauses.append('price_num <= ?')
        params.append(max_price)

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    sql = f"SELECT id, name, price, image, category, color, location, price_num FROM products {where} LIMIT 50"
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    items = [dict(r) for r in rows]
    return jsonify({"items": items})


@app.route('/similar')
def similar():
    # expect ?product_id=123 or ?image_url=...
    product_id = request.args.get('product_id')
    image_url = request.args.get('image_url')
    top_k = int(request.args.get('k') or 6)
    db = get_db()
    cur = db.cursor()
    category = None
    if product_id:
        cur.execute('SELECT image, category FROM products WHERE id = ?', (product_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"items": []})
        image_url = row['image']
        category = row['category']
    if not image_url:
        return jsonify({"items": []})

    # 1. Category-based recommendations (excluding current product)
    category_recs = []
    if category:
        cur.execute('SELECT id, name, price, image, category FROM products WHERE category = ? AND id != ?', (category, product_id))
        category_recs = [dict(r) for r in cur.fetchall()]
    used_ids = set([int(product_id)]) if product_id else set()
    for r in category_recs:
        used_ids.add(r['id'])

    # 2. Image-based recommendations (excluding already included)
    image_recs = []
    if image_based_recommendation is not None:
        try:
            recs = image_based_recommendation.recommend_from_image(image_url, top_k=top_k)
            for r in recs:
                pid = r.get('product_id')
                if pid and pid not in used_ids:
                    cur.execute('SELECT id, name, price, image, category FROM products WHERE id = ?', (pid,))
                    prow = cur.fetchone()
                    if prow:
                        image_recs.append(dict(prow))
                        used_ids.add(pid)
        except Exception as e:
            print('image recommender error in /similar:', e)

    # 3. NLP-based recommendations (excluding already included)
    nlp_recs = []
    if _nlp is not None and product_id:
        try:
            cur.execute('SELECT name, category FROM products WHERE id = ?', (product_id,))
            prow = cur.fetchone()
            if prow:
                query_text = f"{prow['name']} {prow.get('category','')}"
                nlp_results = _nlp.nlp_recommend(query_text, top_k=top_k)
                for r in nlp_results:
                    pid = r.get('id') or r.get('product_id')
                    if pid and pid not in used_ids:
                        cur.execute('SELECT id, name, price, image, category FROM products WHERE id = ?', (pid,))
                        prow2 = cur.fetchone()
                        if prow2:
                            nlp_recs.append(dict(prow2))
                            used_ids.add(pid)
        except Exception as e:
            print('nlp recommender error in /similar:', e)

    # Combine all recommendations in order: category, image, nlp
    combined = category_recs + image_recs + nlp_recs
    return jsonify({"items": combined})


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
    recs = recommend_from_image(item_image, top_k=5) if image_based_recommendation is not None and item_image else ([],[])
    combined=[]
    return jsonify({"status":"ok","recommendations": recs})


@app.route('/admin/extract_features', methods=['POST'])
def admin_extract_features():
    """Admin endpoint to synchronously extract image features from products DB.
    Use after installing heavy deps (tensorflow, pillow, sklearn, pandas).
    """
    if image_based_recommendation is None:
        return jsonify({"error":"image_recommender_unavailable"}), 503
    try:
        # If image recommender available, start extraction in background (non-blocking)
        def run_extract():
            try:
                image_based_recommendation.extract_all_features_from_db()
            except Exception as ee:
                print('background extract error', ee)
        t = threading.Thread(target=run_extract, daemon=True)
        t.start()
        return jsonify({"status":"started"})
    except Exception as e:
        print('admin extract error', e)
        return jsonify({"error":"extract_failed","message": str(e)}), 500


@app.route('/admin/generate_nlp', methods=['POST'])
def admin_generate_nlp():
    """Admin endpoint to (re)generate NLP embeddings using sentence-transformers.
    """
    global _nlp
    if _nlp is None:
        try:
            from Models.nlp_recommender import NLPRecommender
            _nlp = NLPRecommender()
        except Exception as e:
            print('admin nlp error', e)
            return jsonify({"error":"nlp_unavailable","message": str(e)}), 503
    return jsonify({"status":"ok"})


@app.route('/admin/extract_progress')
def admin_extract_progress():
    """Return progress info written by image recommender to progress JSON file."""
    prog_path = Path(__file__).resolve().parent / 'Models' / 'feature_progress.json'
    if not prog_path.exists():
        return jsonify({"status":"idle"})
    try:
        import json
        with open(prog_path, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        print('progress read error', e)
        return jsonify({"status":"unknown"}), 500

@app.route('/admin/reset_db', methods=['POST'])
def admin_reset_db():
    """Dangerous: Drop all tables and re-initialize the database."""
    db = get_db()
    cur = db.cursor()
    # Get all table names
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row['name'] for row in cur.fetchall()]
    for table in tables:
        if table.startswith('sqlite_'):
            continue  # skip SQLite internal tables
        cur.execute(f"DROP TABLE IF EXISTS {table}")
    db.commit()
    # Re-initialize
    init_db()
    return jsonify({'status': 'ok', 'message': 'Database reset and re-initialized.'})

@app.route('/create_user', methods=['POST'])
def create_user():
    data = request.get_json() or {}
    name = data.get('name')
    user_id = data.get('id') or str(uuid4())
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('INSERT INTO users(id, name) VALUES (?, ?)', (user_id, name))
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({'error': 'User ID already exists'}), 400
    return jsonify({'id': user_id, 'name': name})

@app.route('/users', methods=['GET'])
def list_users():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, name FROM users ORDER BY created_at DESC')
    users = [dict(row) for row in cur.fetchall()]
    return jsonify({'users': users})

# Gender categorization utility
GENDER_KEYWORDS = {
    'male': ['men', 'man', 'male', 'boy', 'guys', 'gentlemen', 'mens', 'boys'],
    'female': ['women', 'woman', 'female', 'girl', 'ladies', 'womens', 'girls', 'lady'],
}
def infer_gender(text):
    if not text:
        return 'unknown'
    t = text.lower()
    for gender, keywords in GENDER_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                return gender
    return 'unknown'

@app.route('/admin/categorize_gender', methods=['POST'])
def admin_categorize_gender():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, name, category FROM products')
    products = cur.fetchall()
    updated = 0
    for p in products:
        text = f"{p['name']} {p['category']}"
        gender = infer_gender(text)
        cur.execute('UPDATE products SET gender = ? WHERE id = ?', (gender, p['id']))
        updated += 1
    db.commit()
    return jsonify({'status': 'ok', 'updated': updated})

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
