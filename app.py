from flask import Flask, render_template, request, redirect, url_for, flash
import requests
import json
import os
import logging
import re
import time
from functools import wraps


app = Flask(__name__)

API_KEY = 'RGAPI-090cfdcd-be3c-45fb-a7a2-f9447f586f98'
MATCHES_FILE = 'matches_data.json'



# Configuration des logs
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)



def validate_riot_id(game_name, tag_line):
    game_name_pattern = r'^[a-zA-Z0-9_]{3,16}$'  # 3-16 caractères, lettres, chiffres, underscore
    tag_line_pattern = r'^[a-zA-Z0-9_]{3,5}$'

    if not re.match(game_name_pattern, game_name):
        return False, "Le pseudo doit contenir entre 3 et 16 caractères alphanumériques ou underscores."
    if not re.match(tag_line_pattern, tag_line):
        return False, "Le pseudo doit contenir entre 3 et 5 caractères alphanumériques ou underscores."
    return True, None
# Route principale avec le formulaire pour entrer le pseudo + tag line

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        game_name = request.form['game_name']
        tag_line = request.form['tag_line']

        # Validation des inputs
        is_valid, error_message = validate_riot_id(game_name, tag_line)
        if not is_valid:
            logging.warning(f"Validation échouée : {error_message}")
            flash(error_message)  # Ajoute un message flash
            return redirect(url_for('index'))  # Retourne à la page d'accueil

        logging.info(f"Formulaire soumis : game_name={game_name}, tag_line={tag_line}")
        return redirect(url_for('matches', game_name=game_name, tag_line=tag_line))
    return render_template('index.html')

# Fonction pour faire les requêtes
def make_request(url):
    logging.info(f"Requête envoyée à : {url}")
    response = requests.get(url)
    if response.status_code == 200:
        logging.info(f"Requête réussie pour : {url}")
        return response.json()
    elif response.status_code == 403:
        logging.error(f"Erreur 403 : Accès interdit pour {url}")
    else:
        logging.error(f"Erreur {response.status_code} pour {url}")
        try:
            logging.error(f"Réponse : {response.json()}")
        except Exception:
            pass
    return None


# Charger les matchs stockés localement
def load_matches():
    if os.path.exists(MATCHES_FILE):
        with open(MATCHES_FILE, 'r') as file:
            return json.load(file)
    return {}

# Sauvegarder les nouveaux matchs localement
def save_matches(matches):
    with open(MATCHES_FILE, 'w') as file:
        json.dump(matches, file, indent=4)

def match_generator(match_list, stored_matches):
    """Générateur pour récupérer les détails des matchs un par un."""
    for game_id in match_list:
        try:
            if game_id not in stored_matches:
                # Récupérer les détails du match s'il n'est pas déjà stocké
                match_data = fetch_match_details(game_id)
                if match_data:
                    stored_matches[game_id] = match_data
                    save_matches(stored_matches)
            yield stored_matches[game_id]  # Produit un match à la fois
        except Exception as e:
            logging.error(f"Erreur lors de la récupération du match {game_id} : {e}")

def rate_limited(delay=1.5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, ** kwargs):
            time.sleep(delay)  # Pause avant l'exécution
            return func(*args, **kwargs)
        return wrapper
    return decorator


@rate_limited(delay=1.5)
def fetch_match_details(game_id):
    url = f"https://europe.api.riotgames.com/lol/match/v5/matches/{game_id}?api_key={API_KEY}"
    return make_request(url)





# Route qui affiche l'historique des matchs
@app.route('/matches/<game_name>/<tag_line>')
def matches(game_name, tag_line):
    # Obtenir le PUUID du joueur
    account_url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}?api_key={API_KEY}"
    account_data = make_request(account_url)
    if account_data is None or 'puuid' not in account_data:
        return f"Erreur : Impossible de récupérer les données de l'account pour {game_name}#{tag_line}"

    puuid = account_data['puuid']

    # Récupérer la liste des matchs
    list_game_url = f"https://europe.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?api_key={API_KEY}&type=ranked&count=20"
    match_list = make_request(list_game_url)

    if match_list is None:
        return f"Erreur : Impossible de récupérer la liste des matchs pour {game_name}#{tag_line}"

    # Charger les matchs stockés localement
    stored_matches = load_matches()

    # Utiliser le générateur pour récupérer les détails des matchs
    matches_details = list(match_generator(match_list, stored_matches))

    return render_template(
        'matches.html',
        matches=matches_details,
        game_name=game_name,
        tag_line=tag_line,
        puuid=puuid
    )


if __name__ == "__main__":
    app.run(debug=True)
