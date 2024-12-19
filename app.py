from flask import Flask, render_template, request, redirect, url_for, flash
import requests
import sqlite3
import os
import logging
import re
import sys
import json
import time
from functools import wraps

sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)

API_KEY = 'RGAPI-090cfdcd-be3c-45fb-a7a2-f9447f586f98'
DB_FILE = 'matches_data.db'

print("http://127.0.0.1:5000/")

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    filename='app.log',
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s'
)

error_handler = logging.FileHandler('app_errors.log')
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(error_handler)

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                game_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        ''')
        conn.commit()

init_db()

def make_request(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        logging.warning(f"Requête échouée ({response.status_code}) : {url}")
    except requests.RequestException as e:
        logging.error(f"Erreur de requête pour {url} : {e}", exc_info=True)
    return None

def validate_riot_id(game_name, tag_line):
    game_name_pattern = r'^[a-zA-Z0-9_]{3,16}$'  # 3-16 caractères, lettres, chiffres, underscore
    tag_line_pattern = r'^[a-zA-Z0-9_]{3,5}$'

    if not re.match(game_name_pattern, game_name):
        return False, "Le pseudo doit contenir entre 3 et 16 caractères alphanumériques ou underscores."
    if not re.match(tag_line_pattern, tag_line):
        return False, "Le pseudo doit contenir entre 3 et 5 caractères alphanumériques ou underscores."
    return True, None

def fetch_match_from_db(game_id):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM matches WHERE game_id = ?', (game_id,))
        row = cursor.fetchone()
    return row[0] if row else None

def save_match_to_db(game_id, data):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO matches (game_id, data) VALUES (?, ?)', (game_id, data))
        conn.commit()


def rate_limited(delay=1.5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            time.sleep(delay)  # Pause avant l'exécution
            return func(*args, **kwargs)
        return wrapper
    return decorator

@rate_limited(delay=1.5)
def fetch_match_details(game_id):
    url = f"https://europe.api.riotgames.com/lol/match/v5/matches/{game_id}?api_key={API_KEY}"
    match_data = make_request(url)
    if match_data:
        save_match_to_db(game_id, json.dumps(match_data))
    return match_data

def fetch_match_details_with_limit(game_id):
    match_data = fetch_match_from_db(game_id)
    if not match_data:
        match_data = fetch_match_details(game_id)
    return match_data if isinstance(match_data, dict) else json.loads(match_data)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        game_name = request.form['game_name']
        tag_line = request.form['tag_line']

        # Validation des inputs
        is_valid, error_message = validate_riot_id(game_name, tag_line)
        if not is_valid:
            logging.warning(f"Validation échouée : {error_message}")
            flash(error_message)
            return redirect(url_for('index'))

        logging.info(f"Formulaire soumis : game_name={game_name}, tag_line={tag_line}")
        return redirect(url_for('matches', game_name=game_name, tag_line=tag_line))
    return render_template('index.html')

@app.route('/matches/<game_name>/<tag_line>')
def matches(game_name, tag_line):
    account_url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}?api_key={API_KEY}"
    account_data = make_request(account_url)
    if account_data is None or 'puuid' not in account_data:
        return f"Erreur : Impossible de récupérer les données de l'account pour {game_name}#{tag_line}"

    puuid = account_data['puuid']
    list_game_url = f"https://europe.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?api_key={API_KEY}&type=ranked&count=10"
    match_list = make_request(list_game_url)

    if match_list is None:
        return f"Erreur : Impossible de récupérer la liste des matchs pour {game_name}#{tag_line}"

    matches_details = [fetch_match_details_with_limit(game_id) for game_id in match_list]

    matches_details_filtered = filter(lambda match: match and match['info']['gameDuration'] > 30 * 60, matches_details)

    matches_details_filtered = list(map(lambda match: {**match,'info': {**match['info'],'gameDuration': (match['info']['gameDuration'] // 60) * 60}},matches_details_filtered))

    return render_template(
        'matches.html',
        matches=matches_details_filtered,
        game_name=game_name,
        tag_line=tag_line,
        puuid=puuid
    )

if __name__ == "__main__":
    app.run(debug=True)
