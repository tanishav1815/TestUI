# Backend

This is a simple Flask API that returns sample product recommendations and accepts swipe actions.

Setup and run (recommended using venv):

1. python3 -m venv .venv
2. source .venv/bin/activate
3. pip install -r requirements.txt
4. python app.py

The server will listen on port 5000.

Database notes:
- On first run the app will create `app.db` in the `backend/` folder and seed it with sample items.
- To reset the DB delete `backend/app.db` and restart the app.

