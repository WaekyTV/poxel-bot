# -*- coding: utf-8 -*-
"""
Poxel
Description: Un bot Discord complet axé sur l'XP, les classements, les notifications.
Auteur: Poxel (Développé et mis à jour par Gemini)
Version: 2.7 (Refactorisé)
"""

# ==================================================================================================
# 0. GESTION AUTOMATIQUE DES DÉPENDANCES
# ==================================================================================================
import subprocess
import sys
import importlib

def check_and_install_packages(packages):
    """
    Vérifie si les paquets requis sont installés et les installe s'ils ne le sont pas.
    Amélioré pour re-vérifier l'import après l'installation.
    """
    # Paquets qui peuvent échouer sans être critiques (ex: Pillow pour /rank)
    optional_packages = ["Pillow", "qrcode[pil]", "requests", "deep_translator"]
    
    for import_name, package_name in packages.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            print(f"Module '{import_name}' non trouvé. Installation de '{package_name}'...")
            try:
                # Tenter l'installation
                subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
                # Re-tenter l'importation immédiatement après l'installation
                importlib.import_module(import_name)
                print(f"'{package_name}' installé et importé avec succès.")
                
            except subprocess.CalledProcessError as e:
                # Erreur durant le pip install
                print(f"ERREUR: Impossible d'installer {package_name}. Erreur: {e}")
                if package_name in optional_packages:
                    print(f"Avertissement : La dépendance optionnelle {package_name} n'a pas pu être installée. Certaines fonctionnalités pourraient être limitées.")
                else:
                    print(f"Dépendance critique {package_name} manquante. Arrêt.")
                    sys.exit(1) # Arrêt si critique
                    
            except ImportError:
                # Erreur d'import MÊME APRÈS l'installation
                print(f"AVERTISSEMENT: Le paquet '{package_name}' est installé mais ne peut pas être importé.")
                print(f"Les fonctionnalités associées à '{import_name}' seront désactivées.")


# Dictionnaire des paquets requis: {nom d'importation: nom du paquet pip}
required_packages = {
    "discord": "discord.py",
    "pytz": "pytz",
    "PIL": "Pillow", # Pour la génération d'images
    "qrcode": "qrcode[pil]",
    "flask": "Flask", # Pour l'hébergement
    "dotenv": "python-dotenv",
    "requests": "requests", # Pour les API
    "google.api": "google-api-python-client", # Pour l'API YouTube
    "deep_translator": "deep-translator" # Pour la traduction FR
}
check_and_install_packages(required_packages)


# ==================================================================================================
# 1. IMPORTS
# ==================================================================================================
import discord
from discord import app_commands
from discord.ext import tasks
from discord.ui import Button, View, Modal, TextInput, Select
import datetime
import asyncio
import os
import json
import pytz
import re
import math
import random
import io # Pour manipuler les bytes de l'image
import logging
import xml.etree.ElementTree as ET
from flask import Flask
from threading import Thread
from typing import Optional, List, Dict, Any, Tuple, Literal
from dotenv import load_dotenv
import time # Pour la gestion du token Kick
import textwrap # Pour formater le pendu

# Imports pour la génération d'image
try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageEnhance
    import requests # Pour télécharger les polices/images
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("AVERTISSEMENT : La librairie Pillow (PIL) n'est pas installée. La carte /rank ne fonctionnera pas.")

# Import pour l'API YouTube (Refonte)
try:
    from googleapiclient.discovery import build
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False
    print("AVERTISSEMENT : La librairie google-api-python-client n'est pas installée. Les notifs YouTube (API) ne fonctionneront pas.")

# Import pour la traduction
try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    print("AVERTISSEMENT : deep-translator non installé. Les descriptions resteront en anglais.")


# ==================================================================================================
# 2. CONFIGURATION & CONSTANTES
# ==================================================================================================

# Chargement du .env
load_dotenv()

# --- Configuration du Bot Discord ---
intents = discord.Intents.all()
intents.message_content = True
client: Optional['PoxelBotClient'] = None

# --- Couleurs du Thème ---
NEON_PURPLE = 0x6441a5
NEON_BLUE = 0x027afa
NEON_GREEN = 0x00ff99
RETRO_ORANGE = 0xFF8C00
GOLD_COLOR = 0xFFD700
LIGHT_GREEN = 0x90EE90
TEAM_COLOR = 0x7289DA
FREE_GAMES_COLOR = 0x1abc9c
DARK_RED = 0x8B0000
# Couleurs Ciné Pixel
NETFLIX_COLOR = 0xE50914
DISNEY_COLOR = 0x113CCF
PRIME_COLOR = 0x00A8E1
CINEMA_COLOR = 0xFFD700 # Or pour le cinéma
DEFAULT_CINE_COLOR = 0x2C3E50

# Couleurs pour la carte /rank
RANK_CARD_GRADIENT_START = "#6500ff"
RANK_CARD_GRADIENT_MID = "#6441a5"
RANK_CARD_GRADIENT_END = "#027afa"

# --- Couleurs des Notifications ---
YOUTUBE_COLOR = 0xFF0000
TWITCH_COLOR = 0x9146FF
KICK_COLOR = 0x52C41A
TIKTOK_COLOR = 0x69C9D0

# --- Icônes des Plateformes ---
YOUTUBE_ICON = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/YouTube_full-color_icon_%282017%29.svg/1024px-YouTube_full-color_icon_%282017%29.svg.png"
TWITCH_ICON = "https://assets.stickpng.com/images/580b57fcd9996e24bc43c540.png"
KICK_ICON = "https://logos-world.net/wp-content/uploads/2024/01/Kick-Logo.png"
TIKTOK_ICON = "https://assets.stickpng.com/images/580b57fcd9996e24bc43c53e.png"
DEFAULT_ICON = "https://cdn.icon-icons.com/icons2/2716/PNG/512/discord_logo_icon_173101.png"

# Icônes Ciné Pixel
NETFLIX_ICON = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/1200px-Netflix_2015_logo.svg.png"
DISNEY_ICON = "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Disney%2B_logo.svg/1200px-Disney%2B_logo.svg.png"
PRIME_ICON = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f1/Prime_Video.png/1200px-Prime_Video.png"
CINEMA_ICON = "https://cdn-icons-png.flaticon.com/512/2809/2809590.png" # Bobine de film
TMDB_ICON = "https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.svg"


# --- Fuseaux Horaires ---
USER_TIMEZONE = pytz.timezone('Europe/Paris')
SERVER_TIMEZONE = pytz.utc

# --- Fichiers & Base de Données ---
DATABASE_FILE = 'poxel_database.json'
NOTIFICATIONS_FILE = "poxel_notifications.json"
XP_BACKUP_FILE = 'poxel_xp_backup.json'

# --- Carte /rank (Image) ---
RANK_CARD_BACKGROUND_URL = "https://cdn.discordapp.com/attachments/1420332458964156467/1431775659448991814/Espace_pixels_00307.jpg?ex=692cc8fe&is=692b777e&hm=87344ea49e25994f56dcd69e548498ec0d667f85f744e45932def8c109040128&"
RANK_CARD_FONT_URL = "https://github.com/google/fonts/raw/main/ofl/pressstart2p/PressStart2P-Regular.ttf"

# Variables globales pour la police et le fond (pour mise en cache)
pixel_font_path = "PressStart2P-Regular.ttf"
pixel_font_name = "PressStart2P-Regular"
pixel_font_l = None
pixel_font_m = None
pixel_font_s = None
rank_card_bg = None

# --- Classement ---
LEADERBOARD_EMOJIS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

# --- CLÉS API ---
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", None)
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", None) # Pour Ciné Pixel

# --- NOTIFICATIONS KICK ---
KICK_CLIENT_ID = os.getenv("KICK_CLIENT_ID")
KICK_CLIENT_SECRET = os.getenv("KICK_CLIENT_SECRET")
KICK_USERNAME = os.getenv("KICK_USERNAME", "").lower()
kick_token = None
kick_token_expiry = 0

# --- Configuration Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger("Poxel") # Renommé en "Poxel"

# ==================================================================================================
# 3. SERVEUR FLASK (Pour Hébergement)
# ==================================================================================================
app = Flask(__name__)

@app.route('/')
def home():
    """Endpoint pour afficher une simple page web (utile pour les hébergeurs)."""
    return "Poxel est en ligne !"

def run_flask():
    """Démarre le serveur Flask sur un thread séparé."""
    port = int(os.environ.get('PORT', 8080))
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=port)


# ==================================================================================================
# 4. GESTION DE LA BASE de DONNÉES (JSON)
# ==================================================================================================
def load_data():
    """Charge les données depuis le fichier JSON et initialise les clés nécessaires."""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Erreur de décodage JSON dans {DATABASE_FILE}. Création d'une base vide.")
                data = {}
    else:
        data = {}

    # Initialisation des sections principales
    data.setdefault("users", {})
    data.setdefault("teams", {})
    data.setdefault("birthdays", {})
    data.setdefault("settings", {})
    data.setdefault("avatar_stack", [])
    data.setdefault("avatar_triggers", {})

    # Initialisation des paramètres (settings)
    settings = data["settings"]

    # Personnalisation des Embeds
    styles = settings.setdefault("embed_styles", {})
    styles.setdefault("game_win", {"thumbnail_url": "https.url.com/image_victoire_retro.png"})
    styles.setdefault("game_lose", {"thumbnail_url": "https.url.com/image_defaite_retro.png"})
    styles.setdefault("game_draw", {"thumbnail_url": "https.url.com/image_egalite_retro.png"})
    settings.setdefault("time_offset_seconds", 0)

    # XP & Niveaux
    level_rewards = settings.setdefault("level_up_rewards", {})
    level_rewards.setdefault("notification_channel_id", None)
    level_rewards.setdefault("role_rewards", {})
    level_rewards.setdefault("xp_gain_per_message", {"min": 15, "max": 25})
    level_rewards.setdefault("xp_gain_cooldown_minutes", 1)

    # Anniversaires
    birth_settings = settings.setdefault("birthday_settings", {})
    birth_settings.setdefault("channel_id", None)
    birth_settings.setdefault("reward_xp", 100)

    # Jeux Gratuits
    free_games_settings = settings.setdefault("free_games_settings", {})
    free_games_settings.setdefault("channel_id", None)
    free_games_settings.setdefault("posted_deals", [])

    # Ciné Pixel (Nouveau)
    cine_settings = settings.setdefault("cine_pixel_settings", {})
    cine_settings.setdefault("channel_id", None)
    cine_settings.setdefault("last_checked_ids", []) # Pour éviter les doublons

    # Topweek
    topweek_settings = settings.setdefault("topweek_settings", {})
    topweek_settings.setdefault("channel_id", None)
    topweek_settings.setdefault("announcement_day", 6)
    topweek_settings.setdefault("announcement_time", "19:00")
    topweek_settings.setdefault("last_posted_week", None)
    topweek_rewards = topweek_settings.setdefault("rewards", {})
    topweek_rewards.setdefault("first", {"xp": 200})
    topweek_rewards.setdefault("second", {"xp": 100})
    topweek_rewards.setdefault("third", {"xp": 50})

    # Avatar Dynamique
    settings.setdefault("avatar_cooldown_seconds", 300)
    settings.setdefault("avatar_last_changed", None)
    settings.setdefault("avatar_enabled", True)
    settings.setdefault("avatar_default_url", None)

    # IA (Gemini) - SUPPRIMÉ
    settings.pop("ai_config", None)

    # Écoute Auto-Mod (XP)
    mod_listener = settings.setdefault("mod_listener_settings", {})
    mod_listener.setdefault("enabled", True)
    mod_listener.setdefault("mod_bot_channel_id", None)
    mod_listener.setdefault("event_bot_channel_id", None)
    mod_listener.setdefault("xp_penalty", {
        "warn": -25, "mute": -50, "kick": -100, "tempban": -150, "ban": -250, "signalement": -25
    })
    mod_listener.setdefault("xp_reward", {
        "event_participation": 50, "tournament_win": 200
    })

    settings.pop("arcade_embed_config", None) 
    settings.setdefault("embed_styles", {})

    return data

def save_data(data):
    """Sauvegarde les données dans le fichier JSON."""
    try:
        with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde des données dans {DATABASE_FILE}: {e}")

db = load_data()

def load_notif_data():
    """Charge les données de notification depuis son fichier dédié."""
    if not os.path.exists(NOTIFICATIONS_FILE):
        return {"servers": {}, "last_seen": {}, "channel_cache": {}}
    try:
        with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("servers", {})
            data.setdefault("last_seen", {})
            data.setdefault("channel_cache", {})
            return data
    except json.JSONDecodeError:
        logger.error(f"Erreur de décodage JSON dans {NOTIFICATIONS_FILE}. Création d'une base vide.")
        return {"servers": {}, "last_seen": {}, "channel_cache": {}}
    except Exception as e:
        logger.exception(f"Erreur imprévue lors de la lecture de {NOTIFICATIONS_FILE}")
        return {"servers": {}, "last_seen": {}, "channel_cache": {}}

def save_notif_data(data):
    """Sauvegarde les données de notification."""
    try:
        with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde des données dans {NOTIFICATIONS_FILE}: {e}")

notif_db = load_notif_data()


# ==================================================================================================
# 5. FONCTIONS UTILITAIRES
# ==================================================================================================

def get_adjusted_time() -> datetime.datetime:
    """Retourne l'heure UTC actuelle, ajustée par l'offset configuré."""
    offset = db['settings'].get('time_offset_seconds', 0)
    try:
        offset_seconds = int(offset)
    except (ValueError, TypeError):
        offset_seconds = 0
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return now_utc + datetime.timedelta(seconds=offset_seconds)

def format_cooldown(delta: datetime.timedelta) -> str:
    """Formate un timedelta en une chaîne lisible (ex: 3h 25m)."""
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "maintenant"
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days > 0: parts.append(f"{days}j")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0: parts.append(f"{minutes}m")
    if not parts and seconds > 0: parts.append(f"{seconds}s")
    return " ".join(parts) if parts else "quelques secondes"

def get_level_color(level: int) -> int:
    """Retourne une couleur hexadécimale en fonction du niveau de l'utilisateur."""
    if 1 <= level <= 5: return LIGHT_GREEN
    elif 6 <= level <= 10: return NEON_BLUE
    elif 11 <= level <= 20: return NEON_PURPLE
    elif 21 <= level <= 50: return RETRO_ORANGE
    else: return GOLD_COLOR

# --- NOUVEAU: fetch_url (Refonte "Pingcord": utilise requests avec User-Agent) ---
async def fetch_url(url: str, response_type: str = 'text', headers: Optional[Dict] = None, params: Optional[Dict] = None, data: Optional[Dict] = None, method: str = 'GET', timeout: int = 20) -> Optional[Any]:
    """
    Fonction générique pour récupérer du contenu.
    - 'bytes': Utilise 'requests' (pour images/fichiers).
    - 'text'/'json': Utilise 'requests' avec un User-Agent (pour contourner le blocage 403).
    - 'data': Permet d'envoyer une payload JSON (pour POST, ex: token Kick)
    """
    
    # Préparer les headers
    request_headers = headers or {}
    
    # Cas 1: Téléchargement de fichiers (images, polices)
    if response_type == 'bytes':
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.get(url, headers=request_headers, params=params, timeout=timeout)
            )
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"fetch_url (requests/bytes) a échoué pour {url}: {e}")
            return None
    
    # Cas 2: Récupération d'API (JSON) ou Texte (Scraping simple)
    # On ajoute un User-Agent pour ressembler à un navigateur (Style Pingcord)
    if 'User-Agent' not in request_headers:
        request_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

    try:
        loop = asyncio.get_event_loop()
        
        # Préparer les arguments pour requests
        request_args = {
            "url": url,
            "headers": request_headers,
            "params": params,
            "timeout": timeout
        }
        
        # Gérer la payload (ex: pour POST)
        if data:
            # Si c'est un POST et que le Content-Type est JSON, requests gère la sérialisation
            if method.upper() == 'POST' and request_headers.get("Content-Type") == "application/json":
                request_args["json"] = data
            else:
                request_args["data"] = data

        # Exécuter la requête (GET ou POST)
        if method.upper() == 'POST':
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(**request_args)
            )
        else: # GET par défaut
             response = await loop.run_in_executor(
                None, 
                lambda: requests.get(**request_args)
            )

        response.raise_for_status() # Lève une erreur si 4xx/5xx
        
        if response_type == 'json':
            try:
                return response.json()
            except json.JSONDecodeError as e:
                logger.error(f"fetch_url (requests/json) Erreur JSON pour {url}: {e}. Contenu: {response.text[:150]}...")
                return None
        else:
            return response.text # response_type == 'text'
            
    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else "N/A"
        # Ne pas logger en erreur si c'est un 404 (ex: Kick offline)
        if status_code == 404:
             logger.info(f"fetch_url (requests/api) a reçu un 404 (Not Found) pour {url}. C'est normal si hors ligne.")
        else:
            logger.error(f"fetch_url (requests/api) a échoué pour {url} (Code: {status_code}): {e}")
        return None
    except Exception as e:
        logger.exception(f"fetch_url (requests/api) Erreur fatale pour {url}: {e}")
        return None


def apply_embed_styles(embed: discord.Embed, style_key: str):
    """Applique les styles d'images personnalisés (thumbnail, footer) à un embed."""
    styles = db.get("settings", {}).get("embed_styles", {}).get(style_key, {})
    
    if styles.get("thumbnail_url"):
        embed.set_thumbnail(url=styles["thumbnail_url"])
        
    if styles.get("footer_image_url"):
        # Si l'embed a déjà un footer, on préserve le texte
        footer_text = embed.footer.text if embed.footer.text else ""
        embed.set_footer(text=footer_text, icon_url=styles["footer_image_url"])
    
    return embed # Retourne l'embed modifié

# ==================================================================================================
# 6. SYSTÈME D'IA GEMINI (SUPPRIMÉ)
# ==================================================================================================

# (Code pour la classe GeminiAI et son initialisation supprimé)


# ==================================================================================================
# 7. SYSTÈME D'XP & NIVEAUX (Mis à jour pour /rank)
# ==================================================================================================

def get_user_xp_data(user_id: int) -> Dict[str, Any]:
    """
    Récupère les données XP d'un utilisateur, en les créant si elles n'existent pas.
    """
    user_id_str = str(user_id)
    users_data = db.setdefault("users", {})

    if user_id_str not in users_data:
        users_data[user_id_str] = {
            "xp": 0,
            "level": 1,
            "weekly_xp": 0,
            "last_message_timestamp": None,
            "team_name": None,
            "dm_notifications_disabled": False
        }
    else:
        # Assurer la présence des clés pour les anciens utilisateurs
        user_data = users_data[user_id_str]
        user_data.setdefault("xp", 0)
        user_data.setdefault("level", 1)
        user_data.setdefault("weekly_xp", 0)
        user_data.setdefault("last_message_timestamp", None)
        user_data.setdefault("team_name", None)
        user_data.setdefault("dm_notifications_disabled", False)

    return users_data[user_id_str]

def get_xp_for_level(level: int) -> int:
    """Calcule la quantité d'XP nécessaire pour atteindre le niveau suivant."""
    return int(5 * (level ** 2) + 50 * level + 100)

def get_total_xp(user_data: dict) -> int:
    """Calcule le total d'XP accumulé par un utilisateur pour le classement général."""
    total = user_data.get('xp', 0)
    for lvl in range(1, user_data.get('level', 1)):
        total += get_xp_for_level(lvl)
    return total

def get_global_rank(user_id: int) -> int:
    """Calcule le rang global d'un utilisateur."""
    all_users_data = db.get("users", {})
    leaderboard = sorted(
        all_users_data.items(),
        key=lambda item: get_total_xp(item[1]),
        reverse=True
    )
    for i, (uid_str, data) in enumerate(leaderboard):
        if uid_str == str(user_id):
            return i + 1
    return -1

def get_weekly_rank(user_id: int) -> int:
    """Calcule le rang hebdomadaire d'un utilisateur."""
    all_users_data = db.get("users", {})
    weekly_players = {uid: data for uid, data in all_users_data.items() if data.get("weekly_xp", 0) > 0}
    if str(user_id) not in weekly_players:
        return -1 # Pas classé

    leaderboard = sorted(
        weekly_players.items(),
        key=lambda item: item[1].get("weekly_xp", 0),
        reverse=True
    )
    for i, (uid_str, data) in enumerate(leaderboard):
        if uid_str == str(user_id):
            return i + 1
    return -1
# --- Fonctions de génération de la carte /rank (Pixel Art) ---

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convertit #RRGGBB en (R, G, B)."""
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def create_gradient_image(width: int, height: int, start_hex: str, mid_hex: str, end_hex: str) -> Image:
    """Crée une image de dégradé linéaire horizontal."""
    start_rgb = hex_to_rgb(start_hex)
    mid_rgb = hex_to_rgb(mid_hex)
    end_rgb = hex_to_rgb(end_hex)
    
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    
    mid_point = width // 2
    
    for x in range(width):
        if x < mid_point:
            # Dégradé de start à mid
            ratio = x / mid_point
            r = int(start_rgb[0] * (1 - ratio) + mid_rgb[0] * ratio)
            g = int(start_rgb[1] * (1 - ratio) + mid_rgb[1] * ratio)
            b = int(start_rgb[2] * (1 - ratio) + mid_rgb[2] * ratio)
        else:
            # Dégradé de mid à end
            ratio = (x - mid_point) / (width - mid_point)
            r = int(mid_rgb[0] * (1 - ratio) + end_rgb[0] * ratio)
            g = int(mid_rgb[1] * (1 - ratio) + end_rgb[1] * ratio)
            b = int(mid_rgb[2] * (1 - ratio) + end_rgb[2] * ratio)
        
        draw.line([(x, 0), (x, height)], fill=(r, g, b))
        
    return img

def download_and_cache_assets():
    """Télécharge la police et l'image de fond si elles n'existent pas."""
    global pixel_font_l, pixel_font_m, pixel_font_s, rank_card_bg, PIL_AVAILABLE
    
    if not PIL_AVAILABLE:
        return

    # 1. Télécharger la police
    if not os.path.exists(pixel_font_path):
        try:
            logger.info(f"Téléchargement de la police pixel depuis {RANK_CARD_FONT_URL}...")
            # Utilise requests (synchrone) car c'est une tâche de démarrage
            response = requests.get(RANK_CARD_FONT_URL)
            response.raise_for_status()
            with open(pixel_font_path, "wb") as f:
                f.write(response.content)
            logger.info("Police téléchargée avec succès.")
        except Exception as e:
            logger.error(f"Impossible de télécharger la police pixel: {e}")
            PIL_AVAILABLE = False
            return

    # 2. Charger les polices en mémoire
    if pixel_font_l is None:
        try:
            pixel_font_l = ImageFont.truetype(pixel_font_path, 20) # Pour le nom
            pixel_font_m = ImageFont.truetype(pixel_font_path, 12) # Pour XP/Niveau
            pixel_font_s = ImageFont.truetype(pixel_font_path, 10) # Pour Top Week
        except Exception as e:
            logger.error(f"Impossible de charger la police pixel: {e}")
            PIL_AVAILABLE = False
            return

    # 3. Télécharger et mettre en cache l'image de fond
    if rank_card_bg is None:
        try:
            logger.info("Téléchargement de l'image de fond de la carte /rank...")
            # Utilise requests (synchrone)
            response = requests.get(RANK_CARD_BACKGROUND_URL)
            response.raise_for_status()
            img_bytes = io.BytesIO(response.content)
            rank_card_bg = Image.open(img_bytes).convert("RGBA")
            logger.info("Image de fond mise en cache.")
        except Exception as e:
            logger.error(f"Impossible de télécharger l'image de fond: {e}")
            PIL_AVAILABLE = False
            return

async def generate_rank_card_image(
    current_xp: int, 
    required_xp: int, 
    level: int, 
    global_rank: int, 
    weekly_rank: int, 
    username: str, 
    avatar_url: str
) -> Optional[io.BytesIO]:
    """
    Génère l'image de la carte /rank style pixel art, basée sur Image 1 & 2.
    """
    global PIL_AVAILABLE
    if not PIL_AVAILABLE: return None

    # S'assurer que les assets sont chargés (la fonction est synchrone)
    download_and_cache_assets()
    if not PIL_AVAILABLE or rank_card_bg is None or pixel_font_l is None:
        logger.error("Génération /rank annulée : assets non disponibles.")
        return None

    try:
        # --- Dimensions (Style Image 1) ---
        card_width = 600
        card_height = 180
        avatar_size = 128
        padding = 20

        # --- Créer le fond ---
        # Utiliser une copie du fond en cache
        img = rank_card_bg.copy()
        # Redimensionner et rogner le fond pour s'adapter à la carte
        img = ImageOps.fit(img, (card_width, card_height), method=Image.Resampling.LANCZOS)
        # Ajouter un filtre sombre pour la lisibilité
        overlay = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 150))
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        # --- Télécharger et préparer l'avatar ---
        # (Modifié pour utiliser la nouvelle fetch_url hybride)
        avatar_bytes = await fetch_url(avatar_url, response_type='bytes')
        if not avatar_bytes:
            avatar_img = Image.new('RGBA', (avatar_size, avatar_size), (80, 80, 80))
        else:
            avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

        # Créer un masque circulaire (Style Image 1)
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)

        # Appliquer le masque
        avatar_img.putalpha(mask)
        # Coller l'avatar
        avatar_x = padding
        avatar_y = (card_height - avatar_size) // 2
        img.paste(avatar_img, (avatar_x, avatar_y), avatar_img)

        # --- Positions du texte ---
        text_start_x = avatar_x + avatar_size + padding
        text_width = card_width - text_start_x - padding

        # --- Dessiner RANG et NIVEAU (Style Image 1) ---
        rank_text = "RANG"
        rank_val = f"#{global_rank}"
        level_text = "NIVEAU"
        level_val = f"{level}"
        
        # Positions en haut à droite
        level_val_size = draw.textlength(level_val, font=pixel_font_l)
        level_val_x = card_width - padding - level_val_size
        level_text_size = draw.textlength(level_text, font=pixel_font_m)
        level_text_x = level_val_x - level_text_size - 8
        
        rank_val_size = draw.textlength(rank_val, font=pixel_font_l)
        rank_val_x = level_text_x - rank_val_size - padding
        rank_text_size = draw.textlength(rank_text, font=pixel_font_m)
        rank_text_x = rank_val_x - rank_text_size - 8

        text_y = padding + 5
        draw.text((rank_text_x, text_y + 4), rank_text, fill=(200, 200, 200), font=pixel_font_m)
        draw.text((rank_val_x, text_y), rank_val, fill=(255, 255, 255), font=pixel_font_l)
        draw.text((level_text_x, text_y + 4), level_text, fill=(200, 200, 200), font=pixel_font_m)
        draw.text((level_val_x, text_y), level_val, fill=hex_to_rgb(RANK_CARD_GRADIENT_END), font=pixel_font_l)

        # --- Dessiner le nom d'utilisateur ---
        username = username[:20] # Limiter la longueur
        username_y = text_y + 35
        draw.text((text_start_x, username_y), username, fill=(255, 255, 255), font=pixel_font_l)

        # --- Barre d'XP (Style Image 2) ---
        bar_height = 28
        bar_y = username_y + 35
        bar_frame_thickness = 3
        bar_inner_height = bar_height - (bar_frame_thickness * 2)
        
        progress_percentage = min(1.0, current_xp / required_xp) if required_xp > 0 else 1.0
        bar_width_filled = int(text_width * progress_percentage)

        # Dessiner le cadre de la barre (style pixel art)
        draw.rectangle(
            (text_start_x, bar_y, text_start_x + text_width, bar_y + bar_height),
            outline=(200, 200, 200), width=bar_frame_thickness
        )
        # Dessiner le fond intérieur
        draw.rectangle(
            (text_start_x + bar_frame_thickness, bar_y + bar_frame_thickness, 
             text_start_x + text_width - bar_frame_thickness, bar_y + bar_height - bar_frame_thickness),
            fill=(40, 40, 40)
        )
        
        # Dessiner la partie remplie (avec dégradé)
        if bar_width_filled > bar_frame_thickness * 2:
            gradient_img = create_gradient_image(
                bar_width_filled, 
                bar_inner_height, 
                RANK_CARD_GRADIENT_START, 
                RANK_CARD_GRADIENT_MID, 
                RANK_CARD_GRADIENT_END
            )
            img.paste(gradient_img, (text_start_x + bar_frame_thickness, bar_y + bar_frame_thickness))

            # Dessiner les "cellules" (Style Image 2)
            cell_width = 10
            for x in range(text_start_x + bar_frame_thickness + cell_width, text_start_x + bar_width_filled, cell_width):
                draw.line(
                    (x, bar_y + bar_frame_thickness, x, bar_y + bar_height - bar_frame_thickness),
                    fill=(0, 0, 0, 100), width=1
                )

        # --- Texte XP ---
        xp_text = f"{current_xp} / {required_xp} XP"
        xp_text_x = card_width - padding - draw.textlength(xp_text, font=pixel_font_m)
        draw.text((xp_text_x, username_y + 10), xp_text, fill=(220, 220, 220), font=pixel_font_m, anchor="ra")

        # --- Rang Top Week (Sous la barre) ---
        weekly_rank_text = f"TOP WEEK: #{weekly_rank}" if weekly_rank > 0 else "TOP WEEK: Non classé"
        weekly_text_y = bar_y + bar_height + 10
        draw.text((text_start_x, weekly_text_y), weekly_rank_text, fill=(200, 200, 200), font=pixel_font_s)

        # Sauvegarder l'image en mémoire
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

    except Exception as e:
        logger.exception(f"Erreur lors de la génération de l'image /rank: {e}")
        return None


async def check_and_handle_progression(member: discord.Member, channel: Optional[discord.TextChannel] = None):
    """
    Vérifie et gère la montée de niveau du JOUEUR.
    Envoie des notifications publiques et privées.
    Attribue les rôles récompenses si configurés.
    """
    user_data = get_user_xp_data(member.id)
    leveled_up = False

    xp_needed_player = get_xp_for_level(user_data["level"])

    while user_data["xp"] >= xp_needed_player:
        leveled_up = True
        user_data["level"] += 1
        user_data["xp"] -= xp_needed_player
        new_level = user_data["level"]
        xp_needed_player = get_xp_for_level(new_level)

        rewards_settings = db["settings"].get("level_up_rewards", {})
        reward_messages = []

        # Vérifier les récompenses de rôle
        role_rewards_map = rewards_settings.get("role_rewards", {})
        role_id_to_add_str = role_rewards_map.get(str(new_level))
        if role_id_to_add_str:
            try:
                role_to_add = member.guild.get_role(int(role_id_to_add_str))
                if role_to_add and role_to_add not in member.roles:
                    try:
                        await member.add_roles(role_to_add, reason=f"Atteinte du niveau {new_level}")
                        reward_messages.append(f"✨ Rôle obtenu : {role_to_add.mention}")
                        logger.info(f"Rôle {role_to_add.name} attribué à {member.display_name} pour le niveau {new_level}.")
                    except discord.Forbidden:
                        logger.error(f"Permissions manquantes pour ajouter le rôle {role_to_add.name} à {member.display_name}")
                    except discord.HTTPException as e:
                        logger.error(f"Erreur HTTP lors de l'ajout du rôle {role_to_add.name} à {member.display_name}: {e}")
                elif not role_to_add:
                    logger.warning(f"Le rôle récompense configuré pour le niveau {new_level} (ID: {role_id_to_add_str}) est introuvable.")
            except ValueError:
                logger.error(f"ID de rôle invalide configuré pour le niveau {new_level}: {role_id_to_add_str}")

        # Préparer le message de félicitations
        level_up_desc = f"🎉 GG {member.mention} ! Tu passes au **Niveau {new_level}** !"
        if reward_messages:
            level_up_desc += "\n\n**Récompenses :**\n" + "\n".join(reward_messages)

        embed = discord.Embed(title="🌟 LEVEL UP! 🌟", description=level_up_desc, color=get_level_color(new_level))
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Continue à être actif pour grimper dans le classement ! 💬")
        
        # Appliquer le style d'embed personnalisé
        embed = apply_embed_styles(embed, "level_up")

        # Envoyer la notification publique
        public_notif_channel_id = rewards_settings.get("notification_channel_id")
        public_notif_channel = client.get_channel(public_notif_channel_id) if public_notif_channel_id else channel

        if public_notif_channel:
            try:
                await public_notif_channel.send(embed=embed)
            except discord.Forbidden:
                logger.error(f"Permissions manquantes pour l'annonce de montée de niveau dans {public_notif_channel.name}")
            except Exception as e:
                logger.error(f"Erreur inattendue lors de l'envoi de l'annonce de level up: {e}")

        # Envoyer la notification privée (si activée)
        if not user_data.get("dm_notifications_disabled", False):
            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer un MP de level up à {member.display_name} (MP bloqués).")
            except Exception as e:
                logger.error(f"Erreur inattendue lors de l'envoi du MP de level up: {e}")

        # Déclencher l'avatar dynamique
        await trigger_avatar_change('xp_gain')

    if leveled_up:
        save_data(db) # Sauvegarder uniquement si un level up a eu lieu


async def update_user_xp(user_id: int, xp_change: int, is_weekly_xp: bool = True):
    """Met à jour l'XP total et hebdomadaire d'un utilisateur."""
    if xp_change == 0:
        return

    user_data = get_user_xp_data(user_id)

    user_data["xp"] = max(0, user_data["xp"] + xp_change)
    if is_weekly_xp and xp_change > 0:
        user_data["weekly_xp"] = max(0, user_data.get("weekly_xp", 0) + xp_change)

    return user_data

# ==================================================================================================
# 8. SYSTÈME D'ANNIVERSAIRE
# ==================================================================================================

@tasks.loop(time=datetime.time(hour=0, minute=1, tzinfo=SERVER_TIMEZONE))
async def check_birthdays():
    """Tâche de fond qui vérifie et annonce les anniversaires."""
    try:
        await client.wait_until_ready()
        logger.info("Vérification des anniversaires...")
        today_str = get_adjusted_time().strftime("%m-%d")

        settings = db["settings"].get("birthday_settings", {})
        channel_id = settings.get("channel_id")
        reward_xp = settings.get("reward_xp", 100)

        if not channel_id:
            return

        channel = client.get_channel(channel_id)
        if not channel:
            return

        birthdays_today = []
        for user_id_str, bday_date in db.get("birthdays", {}).items():
            if bday_date == today_str:
                try:
                    user_id = int(user_id_str)
                    member = None
                    for guild in client.guilds:
                        member = guild.get_member(user_id)
                        if member: break
                    if member: birthdays_today.append(member)
                except ValueError: pass

        if not birthdays_today: return

        mentions = ", ".join(m.mention for m in birthdays_today)
        embed = discord.Embed(title="🎂 Joyeux Anniversaire ! 🎂", description=f"Bon anniversaire à {mentions} ! 🎉", color=GOLD_COLOR)
        embed = apply_embed_styles(embed, "birthday_announce")

        try:
            await channel.send(content="@everyone", embed=embed)
        except Exception as e:
            logger.error(f"Erreur envoi anniversaire: {e}")

        for member in birthdays_today:
            await update_user_xp(member.id, reward_xp, is_weekly_xp=True)
            await check_and_handle_progression(member, channel)
        save_data(db)
    except Exception as e:
        logger.exception(f"Erreur critique dans check_birthdays: {e}")


# ==================================================================================================
# 9. SYSTÈME DE NOTIFICATIONS (Robustesse & Scraping)
# ==================================================================================================

# --- Fonctions de vérification ---

async def get_youtube_channel_id(youtube_service, identifier: str) -> Optional[str]:
    """Trouve l'ID d'une chaîne YouTube via l'API."""
    cache_key = f"youtube:{identifier}"
    cached_id = notif_db.get("channel_cache", {}).get(cache_key)
    if cached_id: return cached_id

    def search_sync():
        try:
            if identifier.startswith('@'):
                search_response = youtube_service.search().list(part="snippet", q=identifier, type="channel", maxResults=1).execute()
                if search_response.get("items") and search_response["items"][0]["snippet"].get("customUrl") == identifier:
                    return search_response["items"][0]["snippet"]["channelId"]
            if re.match(r"UC[\w-]{21}[AQgw]", identifier): return identifier
            search_response = youtube_service.search().list(part="snippet", q=identifier, type="channel", maxResults=1).execute()
            if search_response.get("items"): return search_response["items"][0]["snippet"]["channelId"]
            return None
        except Exception: return None

    channel_id = await asyncio.to_thread(search_sync)
    if channel_id:
        notif_db.setdefault("channel_cache", {})[cache_key] = channel_id
        save_notif_data(notif_db)
    return channel_id

# --- Scraping YouTube ---
async def check_youtube_scrape(identifier: str, category: str) -> List[Dict]:
    """Vérifie YouTube en analysant la page web (Lives/Vidéos/Shorts)."""
    if identifier.startswith("UC"): base_url = f"https://www.youtube.com/channel/{identifier}"
    elif identifier.startswith("@"): base_url = f"https://www.youtube.com/{identifier}"
    else: base_url = f"https://www.youtube.com/c/{identifier}"

    if category == "live": target_url = f"{base_url}/streams"
    elif category == "short": target_url = f"{base_url}/shorts"
    else: target_url = f"{base_url}/videos"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Cache-Control': 'no-cache', 'Pragma': 'no-cache'
    }
    
    html = await fetch_url(target_url, response_type='text', headers=headers)
    if not html: return []

    events = []
    try:
        if category == "live" and '"isLive":true' in html:
            vid_match = re.search(r'"videoId":"([\w-]{11})".*?"isLive":true', html)
            title_match = re.search(r'"videoId":"[\w-]{11}".*?"title":\{"runs":\[\{"text":"(.*?)"\}', html)
            if vid_match:
                vid_id = vid_match.group(1)
                events.append({
                    "id": vid_id,
                    "title": title_match.group(1) if title_match else "Live YouTube",
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "thumbnail": f"https://i.ytimg.com/vi/{vid_id}/maxresdefault.jpg",
                    "description": "En direct sur YouTube !",
                    "creator": identifier,
                    "creator_avatar": None,
                    "timestamp": get_adjusted_time().isoformat(),
                    "is_live": True, "platform": "youtube", "game": "YouTube Live"
                })
        elif category == "video":
            vid_matches = re.findall(r'"videoId":"([\w-]{11})","thumbnail"', html)
            if vid_matches:
                vid_id = vid_matches[0]
                events.append({
                    "id": vid_id,
                    "title": "Nouvelle vidéo YouTube !",
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "thumbnail": f"https://i.ytimg.com/vi/{vid_id}/maxresdefault.jpg",
                    "description": "Nouvelle vidéo disponible",
                    "creator": identifier, "creator_avatar": None,
                    "timestamp": get_adjusted_time().isoformat(),
                    "is_live": False, "platform": "youtube", "game": "YouTube Video"
                })
        elif category == "short":
            short_matches = re.findall(r'"url":"/shorts/([\w-]{11})"', html)
            if short_matches:
                vid_id = short_matches[0]
                events.append({
                    "id": vid_id,
                    "title": "Nouveau Short YouTube !",
                    "url": f"https://www.youtube.com/shorts/{vid_id}",
                    "thumbnail": f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
                    "description": "Nouveau Short disponible",
                    "creator": identifier, "creator_avatar": None,
                    "timestamp": get_adjusted_time().isoformat(),
                    "is_live": False, "platform": "youtube", "game": "YouTube Short"
                })
    except Exception: pass
    return events

async def check_youtube(identifier: str, config: Dict, category: str) -> List[Dict]:
    scrape_events = await check_youtube_scrape(identifier, category)
    if scrape_events: return scrape_events

    if not YOUTUBE_API_AVAILABLE or not YOUTUBE_API_KEY: return []
    try:
        youtube_service = await asyncio.to_thread(build, 'youtube', 'v3', developerKey=YOUTUBE_API_KEY, cache_discovery=False)
        channel_id = await get_youtube_channel_id(youtube_service, identifier)
        if not channel_id: return []
        
        def search_sync():
            if category == "live":
                return youtube_service.search().list(part="snippet", channelId=channel_id, eventType="live", type="video", maxResults=1).execute().get("items", [])
            else:
                return youtube_service.search().list(part="snippet", channelId=channel_id, order="date", type="video", maxResults=1).execute().get("items", [])

        items = await asyncio.to_thread(search_sync)
        if not items: return []
        s = items[0]
        vid_id = s["id"]["videoId"]
        return [{
            "id": vid_id,
            "title": s["snippet"]["title"],
            "url": f"https://www.youtube.com/watch?v={vid_id}",
            "thumbnail": s["snippet"]["thumbnails"]["high"]["url"],
            "description": s["snippet"]["description"],
            "creator": s["snippet"]["channelTitle"],
            "creator_avatar": None,
            "timestamp": s["snippet"]["publishedAt"],
            "is_live": category == "live", "platform": "youtube", "game": None
        }]
    except Exception: return []


async def get_twitch_bearer_token() -> Optional[str]:
    if not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET): return None
    url = "https://id.twitch.tv/oauth2/token"
    params = {"client_id": TWITCH_CLIENT_ID, "client_secret": TWITCH_CLIENT_SECRET, "grant_type": "client_credentials"}
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.post(url, params=params))
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception: return None

async def check_twitch(identifier: str, config: Dict, category: str) -> List[Dict]:
    if category != "live": return []
    token = await get_twitch_bearer_token()
    if not token: return []
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"}
    
    # --- CORRECTION TWITCH : Extraction du pseudo depuis l'URL ---
    clean_identifier = identifier.strip().lstrip('@').replace(" ", "")
    if "twitch.tv/" in clean_identifier:
        # Prend ce qui est après le dernier / et avant un éventuel ?
        clean_identifier = clean_identifier.split("twitch.tv/")[-1].split("/")[0].split("?")[0]
    
    try:
        user_data = await fetch_url(f"https://api.twitch.tv/helix/users", response_type='json', headers=headers, params={"login": clean_identifier})
        if not user_data or not user_data.get("data"): return []
        user_info = user_data["data"][0]
        stream_data = await fetch_url(f"https://api.twitch.tv/helix/streams", response_type='json', headers=headers, params={"user_id": user_info["id"]})
        if stream_data and stream_data.get("data"):
            s = stream_data["data"][0]
            return [{
                "id": s["id"],
                "title": s["title"],
                "url": f"https://twitch.tv/{clean_identifier}",
                "thumbnail": s["thumbnail_url"].replace("{width}", "640").replace("{height}", "360"),
                "description": f"Jeu: {s.get('game_name')}",
                "creator": user_info["display_name"],
                "creator_avatar": user_info.get("profile_image_url"),
                "timestamp": s["started_at"],
                "is_live": True, "platform": "twitch", "game": s.get('game_name')
            }]
    except Exception as e:
        # Loguer l'erreur pour debug si besoin, mais ne pas crasher
        logger.error(f"Erreur Twitch pour {clean_identifier}: {e}")
        pass
    return []

# --- KICK (API V1 avec Anti-Cache renforcé) ---
async def get_kick_token():
    global kick_token, kick_token_expiry
    if kick_token and time.time() < kick_token_expiry: return kick_token
    if not KICK_CLIENT_ID or not KICK_CLIENT_SECRET: return None
    try:
        response = await fetch_url("https://id.kick.com/oauth/token", response_type='json', method='POST',
            data={"client_id": KICK_CLIENT_ID, "client_secret": KICK_CLIENT_SECRET, "grant_type": "client_credentials"})
        if response and "access_token" in response:
            kick_token = response["access_token"]
            kick_token_expiry = time.time() + response.get("expires_in", 3600) - 60
            return kick_token
    except Exception: pass
    return None

async def check_kick_live(identifier: str) -> List[Dict]:
    token = await get_kick_token()
    if not token: return []
    try:
        import time
        # Cache Buster pour forcer les données fraîches
        channel_response = await fetch_url(
            f"https://api.kick.com/public/v1/channels",
            response_type='json',
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Cache-Control": "no-cache, no-store, must-revalidate"},
            params={"slug": identifier, "_": str(time.time())}
        )
        if not channel_response or not channel_response.get("data"): return []
        data = channel_response["data"][0]
        stream = data.get("stream")

        if not stream or not stream.get("is_live"): return []

        # ID de session (priorité à l'ID numérique)
        session_id = str(stream.get("id") or stream.get("start_time"))
        if not session_id: return []

        # Récupération avatar
        avatar = None
        if data.get("broadcaster_user_id"):
            u_resp = await fetch_url(f"https://api.kick.com/public/v1/users", response_type='json',
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, params={"id": [data["broadcaster_user_id"]]})
            if u_resp and u_resp.get("data"): avatar = u_resp["data"][0].get("profile_picture")

        thumb = stream.get("thumbnail")
        if isinstance(thumb, dict): thumb = thumb.get("url")

        return [{
            "id": session_id,
            "title": data.get("stream_title"),
            "url": f"https://kick.com/{identifier}",
            "thumbnail": thumb,
            "description": f"Joue à : {data.get('category', {}).get('name', 'Just Chatting')}",
            "creator": data.get("slug", identifier),
            "creator_avatar": avatar,
            "timestamp": stream.get("start_time") or get_adjusted_time().isoformat(),
            "is_live": True, "platform": "kick", "game": data.get("category", {}).get("name")
        }]
    except Exception as e:
        logger.error(f"Kick Check Error: {e}")
        return []

async def check_kick(identifier: str, config: Dict, category: str) -> List[Dict]:
    if category != "live": return []
    clean_id = identifier.strip().lstrip('@').replace(" ", "")
    match = re.search(r"kick\.com/([\w-]+)", clean_id)
    if match: clean_id = match.group(1)
    return await check_kick_live(clean_id)

async def check_tiktok(identifier: str, config: Dict, category: str) -> List[Dict]:
    return []

PLATFORM_CHECKERS = {"youtube": check_youtube, "twitch": check_twitch, "kick": check_kick, "tiktok": check_tiktok}

# --- Formatage & Embeds ---
def format_template(template: Optional[str], event: Dict = None) -> str:
    if not template: return ""
    if not event: event = {}
    return template.replace("{creator}", str(event.get("creator", "Inconnu")))\
                   .replace("{title}", str(event.get("title", "Sans Titre")))\
                   .replace("{description}", str(event.get("description", "")))\
                   .replace("{game}", str(event.get("game", "Inconnu")))\
                   .replace("{url}", str(event.get("url", "")))\
                   .replace("{thumbnail}", str(event.get("thumbnail", "")))\
                   .replace("{creator_avatar}", str(event.get("creator_avatar", "")))

def build_embed_for_event(event: Dict, config: Dict) -> discord.Embed:
    platform = event.get('platform', 'unknown')
    # Couleurs & Icônes par défaut
    colors = {"youtube": YOUTUBE_COLOR, "twitch": TWITCH_COLOR, "kick": KICK_COLOR, "tiktok": TIKTOK_COLOR}
    icons = {"youtube": YOUTUBE_ICON, "twitch": TWITCH_ICON, "kick": KICK_ICON, "tiktok": TIKTOK_ICON}
    
    default_color = colors.get(platform, NEON_BLUE)
    default_icon = icons.get(platform, DEFAULT_ICON)

    # 1. Mode JSON (Prioritaire)
    if config.get("embed_json"):
        try:
            json_str = format_template(config["embed_json"], event)
            data = json.loads(json_str)
            # Support du format complet {embeds: []} ou simple objet {}
            embed_dict = data["embeds"][0] if "embeds" in data else data
            
            # Nettoyage pour éviter crashs Discord
            if "author" in embed_dict and "icon_url" in embed_dict["author"]:
                if not embed_dict["author"]["icon_url"] or not embed_dict["author"]["icon_url"].startswith("http"):
                    del embed_dict["author"]["icon_url"]
            if "thumbnail" in embed_dict and "url" in embed_dict["thumbnail"]:
                if not embed_dict["thumbnail"]["url"] or not embed_dict["thumbnail"]["url"].startswith("http"):
                    del embed_dict["thumbnail"]

            embed = discord.Embed.from_dict(embed_dict)
            # On assure l'URL minimale
            embed.url = event.get("url", "")
            if not embed.footer or not embed.footer.text:
                embed.set_footer(text=platform.capitalize())
            
            # NOTE: EN MODE JSON, ON NE FORCE PAS LE LOGO (Thumbnail).
            return embed
        except Exception as e:
            logger.error(f"Erreur JSON Embed: {e}. Passage en mode simple.")

    # 2. Mode Simple (Fallback)
    embed = discord.Embed(
        title=event.get("title", "Live"),
        url=event.get("url", ""),
        description=event.get("description") or "\u200b",
        color=default_color
    )
    
    # Auteur
    avatar = event.get('creator_avatar')
    if avatar and avatar.startswith("http"):
        embed.set_author(name=event.get("creator", "Streamer"), icon_url=avatar)
    else:
        embed.set_author(name=event.get("creator", "Streamer"))

    # Image principale
    if event.get("thumbnail"): embed.set_image(url=event.get("thumbnail"))
    
    # Champs additionnels
    if event.get("is_live") and event.get("game"):
        embed.add_field(name="Jeu", value=event.get("game"), inline=False)
    
    # Timestamp
    if event.get("timestamp"):
        try: embed.timestamp = datetime.datetime.fromisoformat(event.get("timestamp").replace("Z", "+00:00"))
        except: embed.timestamp = get_adjusted_time()

    embed.set_footer(text=platform.capitalize())
    # EN MODE SIMPLE, ON AJOUTE LE LOGO EN HAUT À DROITE
    if default_icon: embed.set_thumbnail(url=default_icon)
    
    return embed

async def send_notification(guild: discord.Guild, source_config: Dict, event: Dict):
    channel = guild.get_channel(source_config["channel_id"])
    if not channel: return
    
    config = source_config.get("config", {})
    content = format_template(config.get("message_ping", ""), event)
    embed = build_embed_for_event(event, config)
    
    am = discord.AllowedMentions(everyone=False, roles=False)
    if "@everyone" in content: am.everyone = True
    if "<@&" in content: am.roles = True
    
    try:
        await channel.send(content=content.strip() or None, embed=embed, allowed_mentions=am)
        logger.info(f"Notification envoyée sur {guild.name} pour {event.get('creator')}")
    except Exception as e:
        logger.error(f"Erreur envoi notif: {e}")

# --- Tâches de fond ---

async def process_single_source(guild: discord.Guild, source_config: Dict):
    try:
        profile_name = source_config.get("name", "Inconnu")
        platform = source_config.get("platform")
        identifier = source_config.get("id")
        category = source_config.get("category")
        
        checker = PLATFORM_CHECKERS.get(platform)
        if not checker: return

        key = f"{guild.id}:{profile_name}"
        last_id = notif_db.get("last_seen", {}).get(key)

        events = await checker(identifier, source_config.get("config", {}), category)

        # --- GESTION RELANCE LIVE ---
        if not events:
            # Si on avait un ID en mémoire et qu'on ne détecte plus rien -> Le live a coupé.
            # On efface IMMÉDIATEMENT la mémoire pour que la prochaine détection (relance) soit vue comme nouvelle.
            if last_id is not None:
                logger.info(f"[{platform}] {profile_name} est HORS LIGNE. Reset mémoire.")
                notif_db.setdefault("last_seen", {}).pop(key, None)
                save_notif_data(notif_db)
            return

        # Si on a un event
        new_event = events[0]
        new_id = str(new_event["id"])

        # Si l'ID a changé OU si on n'avait pas d'ID (première détection ou après reset)
        if str(last_id) != new_id:
            logger.info(f"[{platform}] Nouveau live/vidéo détecté pour {profile_name} (ID: {new_id})")
            await send_notification(guild, source_config, new_event)
            notif_db.setdefault("last_seen", {})[key] = new_id
            save_notif_data(notif_db)
        
    except Exception as e:
        logger.error(f"Erreur process source {source_config.get('name')}: {e}")

@tasks.loop(seconds=30)
async def check_other_platforms_loop():
    # Boucle Rapide (Twitch, Kick, TikTok)
    try:
        await client.wait_until_ready()
        # Log Heartbeat toutes les 10 itérations (environ 5 min) pour ne pas spammer, mais confirmer la vie
        # if int(datetime.datetime.now().timestamp()) % 300 < 35: 
        #    logger.info("Heartbeat: Vérification rapide active.")

        tasks_list = []
        for gid, gconf in notif_db.get("servers", {}).items():
            guild = client.get_guild(int(gid))
            if not guild: continue
            for src in gconf.get("sources", []):
                if src["platform"] != "youtube":
                    tasks_list.append(process_single_source(guild, src))
        
        if tasks_list:
            await asyncio.gather(*tasks_list, return_exceptions=True)
            
    except Exception as e:
        logger.exception(f"Crash dans check_other_platforms_loop: {e}")

@tasks.loop(minutes=1)
async def check_youtube_loop():
    # Boucle Lente (YouTube - API & Scraping)
    try:
        await client.wait_until_ready()
        # Filtrage horaire pour API YouTube (Quota) mais Scraping peut être plus fréquent si désiré
        # Ici on garde la logique "minutes=1" + filtre horaire pour l'instant
        
        current_hm = get_adjusted_time().astimezone(USER_TIMEZONE).strftime('%H:%M')
        # Horaires cibles
        targets = [f"{h:02d}:00" for h in range(24)] + [f"{h:02d}:{m:02d}" for h in [12,18,20] for m in [1,2,3,4,5,10,15,20]]
        if current_hm not in set(targets): return

        tasks_list = []
        for gid, gconf in notif_db.get("servers", {}).items():
            guild = client.get_guild(int(gid))
            if not guild: continue
            for src in gconf.get("sources", []):
                if src["platform"] == "youtube":
                    tasks_list.append(process_single_source(guild, src))
        
        if tasks_list:
            await asyncio.gather(*tasks_list, return_exceptions=True)
        save_notif_data(notif_db) # Sauvegarde périodique globale
        
    except Exception as e:
        logger.exception(f"Crash dans check_youtube_loop: {e}")


# ==================================================================================================
# 10. SYSTÈME DE JEUX GRATUITS (Refonte Visuelle "FreeStuff Style" + Traduction + Regroupement)
# ==================================================================================================

async def translate_to_french(text: str) -> str:
    """Traduit un texte en français via Google Translate (Deep Translator)."""
    if not text or not TRANSLATOR_AVAILABLE:
        return text
    
    try:
        loop = asyncio.get_event_loop()
        # Exécuter la traduction (qui est bloquante) dans un thread séparé
        translated = await loop.run_in_executor(
            None, 
            lambda: GoogleTranslator(source='auto', target='fr').translate(text)
        )
        return translated if translated else text
    except Exception as e:
        logger.warning(f"Erreur traduction: {e}")
        return text

async def create_free_game_embed(game_data: Dict) -> discord.Embed:
    """Crée un embed Discord pour un jeu gratuit (Style FreeStuff + Traduction)."""

    # --- 1. Détection de la plateforme et du Logo ---
    platforms_str = game_data.get('platforms', '').lower()
    
    # Dictionnaire des logos et couleurs
    platform_style = {
        "epic": {
            "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Epic_Games_logo.svg/1200px-Epic_Games_logo.svg.png",
            "color": 0x333333,
            "name": "Epic Games"
        },
        "steam": {
            "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/1024px-Steam_icon_logo.svg.png",
            "color": 0x1b2838,
            "name": "Steam"
        },
        "gog": {
            "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/GOG.com_logo.svg/1024px-GOG.com_logo.svg.png",
            "color": 0x86328A,
            "name": "GOG"
        },
        "ubisoft": {
            "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/78/Ubisoft_logo.svg/200px-Ubisoft_logo.svg.png",
            "color": 0x0091BD,
            "name": "Ubisoft"
        },
        "itch": {
            "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/79/Itch.io_logo.svg/1200px-Itch.io_logo.svg.png",
            "color": 0xFA5C5C,
            "name": "Itch.io"
        }
    }

    current_style = {"logo": DEFAULT_ICON, "color": FREE_GAMES_COLOR, "name": "Autre"}
    
    if "epic" in platforms_str: current_style = platform_style["epic"]
    elif "steam" in platforms_str: current_style = platform_style["steam"]
    elif "gog" in platforms_str: current_style = platform_style["gog"]
    elif "ubisoft" in platforms_str or "uplay" in platforms_str: current_style = platform_style["ubisoft"]
    elif "itch" in platforms_str: current_style = platform_style["itch"]

    # --- 2. Construction de l'Embed ---
    embed = discord.Embed(color=current_style["color"])
    embed.title = game_data.get('title', 'Jeu Gratuit !')
    url = game_data.get('open_giveaway_url') or game_data.get('gamerpower_url')
    embed.url = url

    # --- 3. Description Formatée ---
    worth = game_data.get('worth', 'N/A')
    if worth == "N/A": worth = "??"
    
    end_date_str = game_data.get('end_date')
    date_text = ""
    if end_date_str and end_date_str != 'N/A':
        try:
            date_part = end_date_str.split(" ")[0]
            y, m, d = date_part.split("-")
            date_clean = f"{d}/{m}/{y}"
            date_text = f" jusqu'au {date_clean}"
        except:
            date_text = ""

    description = f"~~{worth}~~ **Gratuit**{date_text}\n"
    description += "*Vite ! Récupère-le avant qu'il ne soit trop tard !* 🏃\n\n"
    
    raw_desc = game_data.get('description', '')
    if "Instructions:" in raw_desc:
        raw_desc = raw_desc.split("Instructions:")[0].strip()
    
    french_desc = await translate_to_french(raw_desc)
    if french_desc:
        description += f"{french_desc}\n\n"

    description += f"[**Ouvrir dans le navigateur ↗**]({url})\n"
    description += f"[**Ouvrir dans le client {current_style['name']} ↗**]({url})"

    embed.description = description
    embed.set_thumbnail(url=current_style["logo"]) # Logo Plateforme en haut à droite
    if game_data.get('image'):
        embed.set_image(url=game_data['image'])

    embed.set_footer(text=f"via GamerPower • {current_style['name']}")
    embed.timestamp = get_adjusted_time()

    return embed

@tasks.loop(hours=4)
async def check_free_games_task():
    """Tâche de fond pour vérifier et annoncer les nouveaux jeux gratuits."""
    await client.wait_until_ready()
    logger.info("Vérification des jeux gratuits...")

    settings = db["settings"].get("free_games_settings", {})
    channel_id = settings.get("channel_id")
    if not channel_id: return

    channel = client.get_channel(channel_id)
    if not channel: return

    api_url = "https://www.gamerpower.com/api/giveaways?platform=pc"
    games = await fetch_url(api_url, response_type='json')

    if not games or not isinstance(games, list): return

    posted_deals = set(settings.get("posted_deals", []))
    deals_to_save = list(posted_deals)
    embeds_to_send = []
    new_ids = []

    for game in games:
        game_id = game.get('id')
        if game_id and game_id not in posted_deals and game.get('type', 'N/A') == 'Game':
            logger.info(f"Nouveau jeu gratuit trouvé: {game.get('title')} (ID: {game_id})")
            try:
                embed = await create_free_game_embed(game)
                embeds_to_send.append(embed)
                new_ids.append(game_id)
            except Exception as e:
                logger.error(f"Erreur création embed jeu: {e}")

    if embeds_to_send:
        try:
            chunk_size = 10
            chunks = [embeds_to_send[i:i + chunk_size] for i in range(0, len(embeds_to_send), chunk_size)]
            for i, chunk in enumerate(chunks):
                message_content = f"@everyone 🚨 **ALERTE JEU GRATUIT !** 🚨\nUn ou plusieurs nouveaux cadeaux sont disponibles ! 🎁🔥" if i == 0 else None
                await channel.send(content=message_content, embeds=chunk)
                await asyncio.sleep(1.5)
            
            deals_to_save.extend(new_ids)
            db["settings"]["free_games_settings"]["posted_deals"] = deals_to_save[-300:]
            save_data(db)
        except Exception as e:
            logger.error(f"Erreur envoi jeux gratuits: {e}")


# ==================================================================================================
# 10.5. MODULE CINÉ POXEL (Refonte Totale: Multi-API, Catégories, Épisodes)
# ==================================================================================================

# --- Logos & Constantes ---
TV_TIME_LOGO = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5a/TV_Time_logo.svg/1200px-TV_Time_logo.svg.png"
CINEMA_POPCORN_LOGO = "https://cdn-icons-png.flaticon.com/512/2809/2809590.png"

# Liste complète des plateformes avec logos vérifiés et alias
STREAMING_PLATFORMS_EXT = {
    "netflix": {
        "color": 0xE50914, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/1200px-Netflix_2015_logo.svg.png", 
        "name": "Netflix",
        "aliases": ["netflix"]
    },
    "disney": {
        "color": 0x113CCF, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Disney%2B_logo.svg/1200px-Disney%2B_logo.svg.png", 
        "name": "Disney+",
        "aliases": ["disney+", "disney plus"]
    },
    "prime": {
        "color": 0x00A8E1, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f1/Prime_Video.png/1200px-Prime_Video.png", 
        "name": "Prime Video",
        "aliases": ["amazon prime video", "prime video", "amazon video"]
    },
    "apple": {
        "color": 0xA3AAAE, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/28/Apple_TV_Plus_Logo.svg/1200px-Apple_TV_Plus_Logo.svg.png", 
        "name": "Apple TV+",
        "aliases": ["apple tv+", "apple tv plus", "apple tv"]
    },
    "canal": {
        "color": 0x000000, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b1/Canal%2B_new_logo.svg/1200px-Canal%2B_new_logo.svg.png", 
        "name": "Canal+",
        "aliases": ["canal+", "canal plus"]
    },
    "crunchyroll": {
        "color": 0xF47521, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Crunchyroll_Logo.png/1200px-Crunchyroll_Logo.png", 
        "name": "Crunchyroll",
        "aliases": ["crunchyroll"]
    },
    "adn": {
        "color": 0x0090D9, 
        "icon": "https://upload.wikimedia.org/wikipedia/fr/thumb/3/3f/Logo_ADN_2016.svg/1200px-Logo_ADN_2016.svg.png", 
        "name": "ADN",
        "aliases": ["adn", "animation digital network"]
    },
    "paramount": {
        "color": 0x0064FF, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Paramount_Plus.svg/1200px-Paramount_Plus.svg.png", 
        "name": "Paramount+",
        "aliases": ["paramount+", "paramount plus"]
    },
    "max": {
        "color": 0x002BE7, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/Max_logo.svg/1200px-Max_logo.svg.png", 
        "name": "Max (HBO)",
        "aliases": ["max", "hbo max", "hbo"]
    },
    "hulu": {
        "color": 0x1CE783, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Hulu_Logo.svg/1200px-Hulu_Logo.svg.png", 
        "name": "Hulu",
        "aliases": ["hulu"]
    },
    "peacock": {
        "color": 0x000000, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/NBCUniversal_Peacock_Logo.svg/1200px-NBCUniversal_Peacock_Logo.svg.png", 
        "name": "Peacock",
        "aliases": ["peacock", "peacock premium"]
    },
    "tf1": {
        "color": 0x0099FF, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/59/TF1%2B_logo.svg/1200px-TF1%2B_logo.svg.png", 
        "name": "TF1+",
        "aliases": ["tf1+", "tf1"]
    },
    "m6": {
        "color": 0x555555, 
        "icon": "https://upload.wikimedia.org/wikipedia/fr/thumb/e/e0/M6%2B_logo.svg/1200px-M6%2B_logo.svg.png", 
        "name": "M6+",
        "aliases": ["m6+", "m6"]
    },
    "ocs": {
        "color": 0xFFA500, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6d/OCS_logo_2019.svg/1200px-OCS_logo_2019.svg.png", 
        "name": "OCS",
        "aliases": ["ocs"]
    },
    "rakuten": {
        "color": 0xBF0000, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/Rakuten_TV_logo.svg/1200px-Rakuten_TV_logo.svg.png", 
        "name": "Rakuten TV",
        "aliases": ["rakuten", "rakuten tv"]
    },
    "molotov": {
        "color": 0x2D2D2D, 
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/86/Molotov_Logo.svg/1200px-Molotov_Logo.svg.png", 
        "name": "Molotov TV",
        "aliases": ["molotov", "molotov tv"]
    },
    "cinema": {
        "color": CINEMA_COLOR, 
        "icon": CINEMA_POPCORN_LOGO, 
        "name": "Cinéma",
        "aliases": ["cinema", "theatre"]
    }
}

# Mots-clés pour les "Gros Événements" (Style spécial)
BIG_HIT_KEYWORDS = [
    "avatar", "avengers", "star wars", "one piece", "stranger things", "arcane", 
    "last of us", "house of the dragon", "rings of power", "dune", "spider-man", 
    "gta", "invincible", "demon slayer", "kimetsu no yaiba", "attack on titan", "shingeki no kyojin", "jujutsu kaisen",
    "solo leveling", "dragon ball", "one punch man", "my hero academia", "bleach"
]

# --- Helpers de Classification & API ---

def normalize_platform_name(api_provider_name: str) -> Tuple[str, Dict]:
    """Convertit le nom API en nom propre et retourne le style."""
    clean_name = api_provider_name.lower().strip()
    
    # 1. Recherche dans la liste connue
    for key, data in STREAMING_PLATFORMS_EXT.items():
        for alias in data["aliases"]:
            if alias in clean_name:
                return data["name"], data
    
    # 2. Fallback générique
    return api_provider_name, {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON, "name": api_provider_name}

async def get_watch_providers(media_type: str, tmdb_id: int, content_category: str = None) -> Tuple[str, Dict, str]:
    """
    Récupère les plateformes de streaming via TMDB.
    Gère la priorité pour afficher la plateforme 'Up to date' en logo.
    Retourne (NomPrincipal, StylePrincipal, TexteAutresPlateformes).
    """
    if not TMDB_API_KEY: return "Inconnu", {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}, ""
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
    data = await fetch_url(url, response_type='json')
    
    if not data or "results" not in data or "FR" not in data["results"]:
        return "Inconnu", {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}, ""
    
    fr_providers = data["results"]["FR"]
    # On regarde principalement le "flatrate" (Abonnement)
    flatrate = fr_providers.get("flatrate", [])
    
    if not flatrate:
        # Fallback sur "buy" ou "rent" si pas de flatrate (optionnel, mais utile)
        flatrate = fr_providers.get("buy", []) or fr_providers.get("rent", [])
        if not flatrate:
            return "Inconnu", {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}, ""

    # Liste de tous les providers trouvés (Nom, Style) - SANS DOUBLONS
    found_providers_dict = {} # Use dict to remove duplicates by normalized name
    
    for provider in flatrate:
        p_name = provider["provider_name"]
        norm_name, norm_style = normalize_platform_name(p_name)
        if norm_name not in found_providers_dict:
            found_providers_dict[norm_name] = norm_style

    if not found_providers_dict:
        return "Inconnu", {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}, ""

    # Conversion en liste de tuples pour le tri
    found_providers = list(found_providers_dict.items())

    # --- LOGIQUE DE PRIORITÉ INTELLIGENTE (Fix One Punch Man & co) ---
    # L'objectif est de mettre en avant la plateforme qui a la SAISON EN COURS (Simulcast)
    
    primary_name, primary_style = found_providers[0] # Par défaut le premier
    
    if content_category == 'anime':
        # Pour les animés : Crunchyroll et ADN sont prioritaires sur Netflix/Prime
        # car ils ont souvent la saison "en cours" alors que Netflix a les anciennes.
        
        # On cherche si Crunchyroll est présent
        crunchy = next((p for p in found_providers if p[0] == "Crunchyroll"), None)
        adn = next((p for p in found_providers if p[0] == "ADN"), None)
        
        if crunchy:
            primary_name, primary_style = crunchy
        elif adn:
            primary_name, primary_style = adn
        
    elif content_category == 'series':
        # Priorité aux créateurs de contenu originaux
        # HBO -> Max
        max_hbo = next((p for p in found_providers if p[0] == "Max (HBO)"), None)
        if max_hbo: 
            primary_name, primary_style = max_hbo
        else:
            # Disney+ > Netflix (car Disney garde souvent ses exclus)
            disney = next((p for p in found_providers if p[0] == "Disney+"), None)
            if disney:
                primary_name, primary_style = disney

    # Construction du texte pour les autres plateformes
    other_names = [name for name, style in found_providers if name != primary_name]
    other_text = ""
    if other_names:
        other_text = ", ".join(other_names)

    return primary_name, primary_style, other_text

def classify_content(item_data: Dict, media_type: str) -> str:
    """
    Classe le contenu dans : 'anime', 'cartoon', 'series', 'movie'.
    """
    if media_type == 'movie':
        genre_ids = item_data.get('genre_ids', [])
        origin_country = item_data.get('origin_country', [])
        original_lang = item_data.get('original_language', '')
        
        # Cas film d'animation
        if 16 in genre_ids: # 16 = Animation
            if 'JP' in origin_country or original_lang == 'ja':
                return 'anime'
            return 'cartoon'
        return 'movie'
    
    else: # TV Show
        genre_ids = item_data.get('genre_ids', [])
        origin_country = item_data.get('origin_country', [])
        original_lang = item_data.get('original_language', '')
        
        if 16 in genre_ids: # Animation
            if 'JP' in origin_country or original_lang == 'ja':
                return 'anime'
            return 'cartoon'
        return 'series'

def is_big_event(item_data: Dict) -> bool:
    """Détermine si c'est un gros événement (Mots-clés + Popularité)."""
    title = item_data.get('title', item_data.get('name', '')).lower()
    if any(k in title for k in BIG_HIT_KEYWORDS):
        return True
    # Popularité extrême
    if item_data.get('vote_count', 0) > 3000 and item_data.get('vote_average', 0) > 8.0:
        return True
    return False

# --- Génération d'Embed (Le Cœur Visuel) ---

async def create_cine_pixel_embed(item_id: int, media_type: str, category: str, is_episode: bool = False, season_data: Optional[Dict] = None, episode_data: Optional[Dict] = None) -> discord.Embed:
    """
    Génère l'embed final avec logos corrigés et suppression des textes inutiles.
    """
    # 1. Fetch Détails Complets (en Français)
    url_details = f"https://api.themoviedb.org/3/{media_type}/{item_id}?api_key={TMDB_API_KEY}&language=fr-FR"
    details = await fetch_url(url_details, response_type='json')
    if not details: return None

    # 2. Identifier la Plateforme
    platform_name = "Inconnu"
    platform_style = {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}
    other_platforms = ""
    
    # Cas Cinéma (Films récents < 3 mois)
    is_cinema = False
    if media_type == 'movie':
        release_date = details.get('release_date', '2000-01-01')
        try:
            rel_dt = datetime.datetime.strptime(release_date, "%Y-%m-%d").date()
            if (get_adjusted_time().date() - rel_dt).days < 90:
                platform_style = STREAMING_PLATFORMS_EXT["cinema"]
                platform_name = "Cinéma"
                is_cinema = True
        except: pass
    
    if not is_cinema:
        # Récupération intelligente via Watch Providers avec catégorie pour priorité
        p_name, p_style, others = await get_watch_providers(media_type, item_id, category)
        if p_name != "Inconnu":
            platform_name = p_name
            platform_style = p_style
            other_platforms = others
        else:
            platform_name = "Plateforme Inconnue"

    # 3. Vérifier "Gros Événement"
    big_event = is_big_event(details)
    embed_color = GOLD_COLOR if big_event else platform_style.get("color", DEFAULT_CINE_COLOR)

    # 4. Titres & Textes
    title = details.get('title') if media_type == 'movie' else details.get('name')
    overview = details.get('overview', '')
    if not overview: overview = "Aucun synopsis disponible."
    
    display_title = title
    if is_episode and episode_data:
        s_num = episode_data.get('season_number')
        e_num = episode_data.get('episode_number')
        e_name = episode_data.get('name', '')
        display_title = f"{title} — S{s_num:02d}E{e_num:02d}"
        if e_name: display_title += f" : {e_name}"
    elif media_type != 'movie' and season_data:
        s_num = season_data.get('season_number')
        display_title = f"{title} — Saison {s_num}"

    # 5. Création de l'Embed
    embed = discord.Embed(title=f"{'🌟 ' if big_event else ''}{display_title}", url=f"https://www.themoviedb.org/{media_type}/{item_id}", color=embed_color)
    
    # LOGO PLATEFORME PRINCIPALE EN HAUT À DROITE
    embed.set_thumbnail(url=platform_style["icon"])

    # Description Contextuelle
    desc_text = ""
    
    if is_episode:
        desc_text += f"🆕 **Nouvel Épisode !**\nL'épisode vient de sortir sur **{platform_name}**. Foncez le regarder !\n\n"
    elif media_type != 'movie' and season_data:
        desc_text += f"🔥 **Nouvelle Saison !**\nLa saison {season_data.get('season_number')} est disponible sur **{platform_name}**.\n\n"
    else: 
        verb = "Sortie en salle" if platform_name == "Cinéma" else "Disponible"
        desc_text += f"🎬 **{verb} sur {platform_name} !**\n\n"

    desc_text += f"{overview[:400]}..." if len(overview) > 400 else overview
    embed.description = desc_text

    # Champs Infos
    embed.add_field(name="📅 Date", value=details.get('release_date') or details.get('first_air_date') or "Inconnue", inline=True)
    embed.add_field(name="⭐ Note", value=f"{details.get('vote_average', 0):.1f}/10", inline=True)
    
    # Affichage intelligent des plateformes (NETTOYÉ)
    if platform_name != "Inconnu":
        # Juste le nom, sans le texte "(Nouveauté / Saison en cours)" que tu n'aimais pas
        main_val = f"**{platform_name}**"
        
        if other_platforms:
            main_val += f"\n\n*Également disponible sur :*\n{other_platforms}"
        
        embed.add_field(name="📺 Regarder sur", value=main_val, inline=False)

    # Image
    img_path = details.get('backdrop_path') or details.get('poster_path')
    if is_episode and episode_data and episode_data.get('still_path'):
        img_path = episode_data.get('still_path')
    
    if img_path:
        embed.set_image(url=f"https://image.tmdb.org/t/p/original{img_path}")

    # 6. Footer
    footer_text = "Poxel Ciné • Données TMDB & JustWatch"
    if category == 'anime': footer_text += " • AniList"
    
    embed.set_footer(text=footer_text, icon_url=TV_TIME_LOGO)
    embed.add_field(name="\u200b", value=f"📱 **Conseil Pro :** Utilisez l'app [TV Time](https://www.tvtime.com/) pour suivre votre progression !", inline=False)

    return embed

# --- Logique de Boucle & Vérification (Le Moteur) ---

async def check_updates_for_category(category_key: str, media_type: str, is_anime: bool = False, is_cartoon: bool = False):
    """
    Vérifie les nouveautés pour une catégorie spécifique.
    """
    settings = db["settings"].get("cine_pixel_channels", {})
    channel_id = settings.get(category_key)
    if not channel_id: return

    channel = client.get_channel(channel_id)
    if not channel: return

    # URL TMDB adaptée
    if "news" in category_key:
        if media_type == 'movie':
            url = f"https://api.themoviedb.org/3/movie/now_playing?api_key={TMDB_API_KEY}&language=fr-FR&page=1"
        else: # TV
            url = f"https://api.themoviedb.org/3/tv/on_the_air?api_key={TMDB_API_KEY}&language=fr-FR&page=1"
    else: 
        url = f"https://api.themoviedb.org/3/tv/airing_today?api_key={TMDB_API_KEY}&language=fr-FR&page=1"

    data = await fetch_url(url, response_type='json')
    if not data or "results" not in data: return

    history_key = f"history_{category_key}"
    history = db["settings"].setdefault("cine_history", {}).setdefault(history_key, [])
    
    embeds_to_send = []
    new_ids_processed = []

    today = get_adjusted_time().date()

    for item in data["results"]:
        item_id = item["id"]
        
        detected_cat = classify_content(item, media_type)
        
        should_process = False
        if is_anime and detected_cat == 'anime': should_process = True
        elif is_cartoon and detected_cat == 'cartoon': should_process = True
        elif not is_anime and not is_cartoon and detected_cat == 'series' and media_type == 'tv': should_process = True
        elif media_type == 'movie' and not is_anime and not is_cartoon: should_process = True

        if not should_process: continue

        unique_key = f"{item_id}_{today}"
        if unique_key in history: continue

        try:
            embed = None
            
            # CAS : SORTIES / NEWS
            if "news" in category_key:
                if media_type == 'tv':
                    first_air = item.get('first_air_date')
                    # Si sortie récente (cette semaine)
                    if first_air and (today - datetime.datetime.strptime(first_air, "%Y-%m-%d").date()).days < 7:
                        embed = await create_cine_pixel_embed(item_id, media_type, detected_cat, is_episode=False)
                else: # Film
                    embed = await create_cine_pixel_embed(item_id, media_type, detected_cat, is_episode=False)

            # CAS : ÉPISODES
            elif "episodes" in category_key and media_type == 'tv':
                details_url = f"https://api.themoviedb.org/3/tv/{item_id}?api_key={TMDB_API_KEY}&language=fr-FR"
                det = await fetch_url(details_url, response_type='json')
                
                last_ep = det.get('last_episode_to_air')
                if last_ep:
                    ep_date_str = last_ep.get('air_date')
                    if ep_date_str == str(today): 
                        embed = await create_cine_pixel_embed(item_id, media_type, detected_cat, is_episode=True, episode_data=last_ep)

            if embed:
                embeds_to_send.append(embed)
                new_ids_processed.append(unique_key)

        except Exception as e:
            logger.error(f"Erreur traitement item {item_id} ({category_key}): {e}")

    if embeds_to_send:
        for emb in embeds_to_send:
            try:
                await channel.send(embed=emb)
                await asyncio.sleep(1.5)
            except: pass
        
        history.extend(new_ids_processed)
        db["settings"]["cine_history"][history_key] = history[-200:]
        save_data(db)
        logger.info(f"Ciné Poxel ({category_key}): {len(embeds_to_send)} notifs envoyées.")


@tasks.loop(hours=4)
async def check_cine_news_task():
    """Tâche principale qui lance les vérifications pour toutes les catégories."""
    await client.wait_until_ready()
    if not TMDB_API_KEY: return
    
    logger.info("Ciné Poxel: Lancement du scan complet (4h)...")
    
    # 1. NEWS / SORTIES
    await check_updates_for_category('news_series', 'tv', is_anime=False, is_cartoon=False)
    await check_updates_for_category('news_anime', 'tv', is_anime=True)
    await check_updates_for_category('news_cartoons', 'tv', is_cartoon=True)
    await check_updates_for_category('news_movies', 'movie')
    
    # 2. ÉPISODES
    await check_updates_for_category('episodes_series', 'tv', is_anime=False, is_cartoon=False)
    await check_updates_for_category('episodes_anime', 'tv', is_anime=True)
    await check_updates_for_category('episodes_cartoons', 'tv', is_cartoon=True)


# ==================================================================================================
# 11. CLASSE DU CLIENT DISCORD & ÉVÉNEMENTS DE BASE
# ==================================================================================================

class PoxelBotClient(discord.Client):
    """Client Discord personnalisé avec CommandTree."""
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.persistent_views_added = False

    async def setup_hook(self):
        """Fonction appelée lors de l'initialisation pour synchroniser les commandes."""
        try:
            synced = await self.tree.sync()
            logger.info(f"Synchronisé {len(synced)} commandes slash.")
        except Exception as e:
            logger.exception(f"Échec de la synchronisation des commandes slash : {e}")

    async def on_ready(self):
        """Événement déclenché lorsque le bot est connecté et prêt."""
        logger.info(f"Connecté en tant que {self.user.name} ({self.user.id})")
        logger.info(f"Latence API: {round(self.latency * 1000)}ms")
        logger.info(f"Présent sur {len(self.guilds)} serveur(s).")
        
        if PIL_AVAILABLE:
            download_and_cache_assets()

        if not check_birthdays.is_running(): check_birthdays.start()
        
        if not check_youtube_loop.is_running(): check_youtube_loop.start()
        if not check_other_platforms_loop.is_running(): check_other_platforms_loop.start()
        
        if not check_free_games_task.is_running(): check_free_games_task.start()
        if not check_cine_news_task.is_running(): check_cine_news_task.start()

        if not weekly_xp_reset.is_running(): weekly_xp_reset.start()
        if not post_weekly_leaderboard.is_running(): post_weekly_leaderboard.start()
        if not check_avatar_revert.is_running(): check_avatar_revert.start()
        if not backup_xp_data.is_running(): backup_xp_data.start()

client = PoxelBotClient(intents=intents)

@client.event
async def on_message(message: discord.Message):
    """Gère les messages pour le gain d'XP et l'écoute des autres bots."""
    if not message.guild or message.author.bot or message.webhook_id:
        return

    author = message.author
    user_data = get_user_xp_data(author.id)
    now = get_adjusted_time()
    settings = db.get("settings", {})

    xp_config = settings.get("level_up_rewards", {})
    cooldown_minutes = xp_config.get("xp_gain_cooldown_minutes", 1)
    can_gain_xp = True

    last_ts_str = user_data.get("last_message_timestamp")
    if last_ts_str:
        try:
            last_ts = datetime.datetime.fromisoformat(last_ts_str).replace(tzinfo=SERVER_TIMEZONE)
            if now < last_ts + datetime.timedelta(minutes=cooldown_minutes):
                can_gain_xp = False
        except ValueError:
            user_data["last_message_timestamp"] = now.isoformat()

    if can_gain_xp:
        min_xp = xp_config.get("xp_gain_per_message", {}).get("min", 15)
        max_xp = xp_config.get("xp_gain_per_message", {}).get("max", 25)
        xp_gain = random.randint(min_xp, max_xp)

        user_data["last_message_timestamp"] = now.isoformat()
        await update_user_xp(author.id, xp_gain, is_weekly_xp=True)
        await check_and_handle_progression(author, message.channel)
        save_data(db)


    # --- Écoute des Bots Mod/Event (Ajustement XP) ---
    mod_listener_config = settings.get("mod_listener_settings", {})
    if mod_listener_config.get("enabled", True):
        mod_channel_id = mod_listener_config.get("mod_bot_channel_id")
        event_channel_id = mod_listener_config.get("event_bot_channel_id")
        xp_penalties = mod_listener_config.get("xp_penalty", {})
        xp_rewards = mod_listener_config.get("xp_reward", {})

        if message.author.bot and message.channel.id in [mod_channel_id, event_channel_id] and message.embeds:
            embed = message.embeds[0]
            target_member: Optional[discord.Member] = None
            xp_to_change: int = 0
            reason: str = ""

            if message.channel.id == mod_channel_id and (embed.description or embed.title):
                member_mention_match = re.search(r'<@!?(\d+)>', embed.description or "")
                target_user_id = None
                
                if member_mention_match:
                    target_user_id = int(member_mention_match.group(1))
                else:
                    author_text = embed.author.name if embed.author else ""
                    footer_text = embed.footer.text if embed.footer else ""
                    id_match = re.search(r'\((\d{17,19})\)', author_text) or re.search(r'ID: (\d{17,19})', footer_text)
                    if id_match:
                        target_user_id = int(id_match.group(1))
                    else:
                        name_match = re.search(r'^(.*?)\s*#\d{4}', author_text) 
                        if name_match:
                             target_member_by_name = discord.utils.get(message.guild.members, name=name_match.group(1))
                             if target_member_by_name:
                                target_user_id = target_member_by_name.id
                                
                if target_user_id:
                    target_member = message.guild.get_member(target_user_id)

                if target_member and embed.title:
                    title_lower = embed.title.lower()
                    for sanction, xp_penalty in xp_penalties.items():
                        if sanction in title_lower:
                            xp_to_change = xp_penalty
                            reason = f"Sanction '{sanction}' détectée (Bot Mod)"
                            break

            elif message.channel.id == event_channel_id:
                if embed.description and "félicitations au vainqueur" in embed.description.lower():
                    winner_mention = re.search(r'<@!?(\d+)>', embed.description)
                    if winner_mention:
                        winner_id = int(winner_mention.group(1))
                        target_member = message.guild.get_member(winner_id)
                        xp_to_change = xp_rewards.get("tournament_win", 0)
                        reason = "Victoire en tournoi détectée (Bot Event)"

            if target_member and xp_to_change != 0:
                logger.info(f"Écoute Bot: {xp_to_change:+d} XP pour {target_member.display_name}. Raison: {reason}")
                await update_user_xp(target_member.id, xp_to_change, is_weekly_xp=(xp_to_change > 0))
                save_data(db)


@client.event
async def on_member_join(member: discord.Member):
    """Gère l'arrivée d'un nouveau membre."""
    logger.info(f"{member.name} a rejoint {member.guild.name}.")
    settings = db.get("settings", {})

    # --- Message public ---
    welcome_channel_id = settings.get("welcome_channel_id")
    welcome_message = settings.get("welcome_message", "Bienvenue {user} !")
    if welcome_channel_id and welcome_message:
        channel = member.guild.get_channel(welcome_channel_id)
        if channel:
            try:
                content = welcome_message.replace("{user}", member.mention) \
                                         .replace("{guild.name}", member.guild.name) \
                                         .replace("{member_count}", str(member.guild.member_count))
                embed = discord.Embed(description=content, color=NEON_GREEN)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed = apply_embed_styles(embed, "welcome") # Appliquer style
                await channel.send(embed=embed)
            except discord.Forbidden:
                logger.error(f"Permissions manquantes pour envoyer le message de bienvenue dans {channel.name}")
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi du message de bienvenue: {e}")

    # --- Message privé ---
    dm_config = settings.get('welcome_dm', {})
    if dm_config.get('enabled', False):
        try:
            title = dm_config.get('title', 'Bienvenue !').replace('{guild}', member.guild.name)
            description = dm_config.get('description', 'Salut {user} !').replace('{user}', member.mention).replace('{guild}', member.guild.name)
            color_str = dm_config.get('color', hex(NEON_GREEN))
            try: color_val = int(color_str.replace("#", ""), 16)
            except: color_val = NEON_GREEN
            image_url = dm_config.get('image_url')

            embed_dm = discord.Embed(title=title, description=description, color=color_val)
            if image_url: embed_dm.set_image(url=image_url)
            embed_dm.set_thumbnail(url=member.guild.icon.url if member.guild.icon else client.user.display_avatar.url)
            await member.send(embed=embed_dm)
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un MP de bienvenue à {member.name} (DMs bloqués).")
        except Exception as e:
            logger.exception(f"Erreur inattendue lors de l'envoi du MP de bienvenue: {e}")

    await trigger_avatar_change('member_join')

@client.event
async def on_member_remove(member: discord.Member):
    """Gère le départ d'un membre."""
    logger.info(f"{member.name} a quitté {member.guild.name}.")
    settings = db.get("settings", {})
    farewell_channel_id = settings.get("farewell_channel_id")
    farewell_message = settings.get("farewell_message", "Au revoir {user}.")

    if farewell_channel_id and farewell_message:
        channel = member.guild.get_channel(farewell_channel_id)
        if channel:
            try:
                content = farewell_message.replace("{user}", member.display_name)
                embed = discord.Embed(description=content, color=DARK_RED)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed = apply_embed_styles(embed, "farewell") # Appliquer style
                await channel.send(embed=embed)
            except discord.Forbidden:
                logger.error(f"Permissions manquantes pour envoyer le message de départ dans {channel.name}")
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi du message de départ: {e}")

    await trigger_avatar_change('member_remove')

# ==================================================================================================
# 12. COMMANDES SLASH (Utilitaires & Systèmes de Base)
# ==================================================================================================

# --- Commande Ping ---
@client.tree.command(name="ping", description="Vérifie la latence du bot.")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latence : **{latency}ms**",
        color=NEON_GREEN if latency < 150 else (RETRO_ORANGE if latency < 300 else DARK_RED)
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Commande /rank (REMPLACE /xp) ---
@client.tree.command(name="rank", description="Affiche ton profil de progression, ton rang global et ton rang hebdo.")
@app_commands.describe(membre="Voir le profil d'un autre membre (optionnel).")
async def rank(interaction: discord.Interaction, membre: Optional[discord.Member] = None):
    # CORRECTION: defer() doit être éphémère pour que followup() le soit aussi.
    await interaction.response.defer(ephemeral=True)

    target_user = membre or interaction.user
    if target_user.bot:
        await interaction.followup.send("Les bots n'ont pas de profil.", ephemeral=True)
        return

    user_data = get_user_xp_data(target_user.id)

    # Récupérer les classements
    global_rank = get_global_rank(target_user.id)
    weekly_rank = get_weekly_rank(target_user.id)

    current_level = user_data["level"]
    current_xp = user_data["xp"]
    required_xp = get_xp_for_level(current_level)

    # Générer l'image de la carte /rank
    rank_card_buffer = await generate_rank_card_image(
        current_xp, required_xp, current_level, global_rank, weekly_rank,
        target_user.display_name, target_user.display_avatar.url
    )

    if rank_card_buffer:
        rank_card_file = discord.File(rank_card_buffer, filename=f"{target_user.name}_rank_card.png")
        await interaction.followup.send(file=rank_card_file, ephemeral=True)
    else:
        # Fallback texte si Pillow a échoué
        embed = discord.Embed(
            title=f"📊 Profil XP – {target_user.display_name}",
            color=get_level_color(current_level)
        )
        embed.description = (
            f"**Niveau :** {current_level}\n"
            f"**XP :** {current_xp} / {required_xp}\n"
            f"**Rang Global :** #{global_rank if global_rank != -1 else 'N/A'}\n"
            f"**Rang Hebdo :** #{weekly_rank if weekly_rank != -1 else 'N/A'}"
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text="Erreur: La génération de l'image de la carte a échoué.")
        await interaction.followup.send(embed=embed, ephemeral=True)


# --- Commandes Anniversaire ---
birthday_group = app_commands.Group(name="birthday", description="Gère ton anniversaire.")

@birthday_group.command(name="set", description="Enregistre ton anniversaire (JJ/MM).")
@app_commands.describe(date="Ta date d'anniversaire (ex: 25/12).")
async def birthday_set(interaction: discord.Interaction, date: str):
    user_id_str = str(interaction.user.id)
    try:
        parsed_date = datetime.datetime.strptime(date.strip(), "%d/%m")
        birthday_key = f"{parsed_date.month:02d}-{parsed_date.day:02d}"
        db.setdefault("birthdays", {})[user_id_str] = birthday_key
        save_data(db)
        await interaction.response.send_message(f"✅ Anniversaire enregistré pour le **{parsed_date.day:02d}/{parsed_date.month:02d}**.", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ Format de date invalide. Utilise **JJ/MM** (ex: 05/01).", ephemeral=True)

@birthday_group.command(name="remove", description="Supprime ton anniversaire enregistré.")
async def birthday_remove(interaction: discord.Interaction):
    user_id_str = str(interaction.user.id)
    if user_id_str in db.get("birthdays", {}):
        del db["birthdays"][user_id_str]
        save_data(db)
        await interaction.response.send_message("✅ Ton anniversaire a été supprimé.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Tu n'avais pas enregistré d'anniversaire.", ephemeral=True)

client.tree.add_command(birthday_group)

@client.tree.command(name="birthdaylist", description="Affiche la liste des prochains anniversaires.")
async def birthdaylist(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    birthdays = db.get("birthdays", {})
    if not birthdays:
        return await interaction.followup.send("Aucun anniversaire enregistré.", ephemeral=True)

    today_str = get_adjusted_time().strftime("%m-%d")
    upcoming = []
    past = []

    for user_id_str, bday_date in birthdays.items():
        try:
            member = interaction.guild.get_member(int(user_id_str))
            if member:
                if bday_date >= today_str:
                    upcoming.append((member, bday_date))
                else:
                    past.append((member, bday_date))
        except (ValueError, AttributeError):
            continue

    upcoming.sort(key=lambda x: x[1])
    past.sort(key=lambda x: x[1])
    sorted_birthdays = upcoming + past

    if not sorted_birthdays:
        return await interaction.followup.send("Aucun anniversaire trouvé pour les membres actuels.", ephemeral=True)

    embed = discord.Embed(title="🎂 Prochains Anniversaires 🎂", color=GOLD_COLOR)
    description = ""
    count = 0
    mois_fr = ["", "Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Aoû", "Sep", "Oct", "Nov", "Déc"]
    for member, bday_date in sorted_birthdays:
        try:
            month, day = map(int, bday_date.split('-'))
            formatted_date = f"{day:02d} {mois_fr[month]}"
            description += f"• **{member.display_name}** - {formatted_date}\n"
            count += 1
            if count >= 15:
                description += "*... et plus encore !*"
                break
        except (ValueError, IndexError):
            continue

    embed.description = description if description else "Aucun anniversaire à afficher."
    await interaction.followup.send(embed=embed, ephemeral=True)

@client.tree.command(name="nextbirthday", description="Affiche le prochain anniversaire.")
async def nextbirthday(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    birthdays = db.get("birthdays", {})
    if not birthdays: return await interaction.followup.send("Aucun anniversaire enregistré.", ephemeral=True)

    today = get_adjusted_time().date()
    today_str = today.strftime("%m-%d")
    upcoming = []
    past = []

    for user_id_str, bday_date in birthdays.items():
        try:
            member = interaction.guild.get_member(int(user_id_str))
            if member:
                if bday_date >= today_str: upcoming.append((member, bday_date))
                else: past.append((member, bday_date))
        except: continue

    upcoming.sort(key=lambda x: x[1])
    past.sort(key=lambda x: x[1])
    sorted_birthdays = upcoming + past

    if not sorted_birthdays: return await interaction.followup.send("Aucun anniversaire pour les membres actuels.", ephemeral=True)

    next_bday_member, next_bday_date_str = sorted_birthdays[0]
    month, day = map(int, next_bday_date_str.split('-'))

    next_bday_dt = datetime.datetime(today.year, month, day)
    if next_bday_dt.date() < today:
        next_bday_dt = datetime.datetime(today.year + 1, month, day)

    embed = discord.Embed(
        title="🎉 Prochain Anniversaire 🎉",
        description=f"Le prochain est celui de **{next_bday_member.mention}** : {discord.utils.format_dt(next_bday_dt, style='R')} !",
        color=NEON_GREEN
    )
    embed.set_footer(text=f"Date : {discord.utils.format_dt(next_bday_dt, style='D')}")
    await interaction.followup.send(embed=embed, ephemeral=True)

birthday_admin_group = app_commands.Group(name="birthdayadmin", description="Commandes admin pour les anniversaires.", default_permissions=discord.Permissions(administrator=True))

@birthday_admin_group.command(name="config", description="Configure le salon d'annonce des anniversaires.")
@app_commands.describe(salon="Le salon où annoncer les anniversaires.")
async def birthday_admin_config(interaction: discord.Interaction, salon: discord.TextChannel):
    db.setdefault("settings", {}).setdefault("birthday_settings", {})["channel_id"] = salon.id
    save_data(db)
    await interaction.response.send_message(f"✅ Annonces d'anniversaire configurées pour {salon.mention}.", ephemeral=True)

client.tree.add_command(birthday_admin_group)

# --- Commandes Notifications (Refonte "nom" et "api_key") ---
notif_group = app_commands.Group(name="notif", description="Gère le système de notifications.", default_permissions=discord.Permissions(administrator=True))

async def platform_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    platforms = ["YouTube", "Twitch", "Kick", "TikTok"]
    return [
        app_commands.Choice(name=p, value=p.lower())
        for p in platforms if current.lower() in p.lower()
    ]

# Autocomplete basé sur le NOM du profil
async def profile_name_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    guild_id_str = str(interaction.guild_id)
    sources = notif_db.get("servers", {}).get(guild_id_str, {}).get("sources", [])
    choices = set()
    for source in sources:
        name = source.get("name") # Utilise .get() pour sécurité
        if name and current.lower() in name.lower():
            choices.add(name)
    return [app_commands.Choice(name=choice, value=choice) for choice in choices][:25]


@notif_group.command(name="add", description="Ajoute un profil de notification.")
@app_commands.autocomplete(plateforme=platform_autocomplete)
@app_commands.describe(
    nom="Un nom unique pour ce profil (ex: Waeky - Lives).",
    plateforme="La plateforme (YouTube, Twitch...).",
    categorie="Notifier les Vides ou les Lives ?",
    identifiant="Nom d'utilisateur, ID de chaîne, ou URL.",
    canal="Le salon où envoyer les notifications.",
    api_key="Clé API (Optionnel, requis pour TikTok)."
)
async def notif_add(
    interaction: discord.Interaction, 
    nom: str, 
    plateforme: str,
    categorie: Literal["Live", "Vidéo"],
    identifiant: str, 
    canal: discord.TextChannel,
    api_key: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    guild_id_str = str(interaction.guild_id)
    platform_lower = plateforme.lower()
    if platform_lower not in PLATFORM_CHECKERS:
        await interaction.followup.send(f"Plateforme '{plateforme}' non supportée.", ephemeral=True)
        return

    # Validation YouTube (doit utiliser l'API)
    if platform_lower == "youtube" and not YOUTUBE_API_KEY:
        await interaction.followup.send("❌ Erreur: `YOUTUBE_API_KEY` n'est pas définie dans le fichier `.env` du bot. Impossible d'ajouter une notification YouTube.", ephemeral=True)
        return
        
    # Validation TikTok (doit avoir une clé)
    if platform_lower == "tiktok" and not api_key:
        await interaction.followup.send("❌ Erreur: TikTok nécessite une `api_key` (ex: de RapidAPI) pour fonctionner. Commande annulée.", ephemeral=True)
        return

    clean_name = nom.strip()
    g_sources = notif_db.setdefault("servers", {}).setdefault(guild_id_str, {}).setdefault("sources", [])
    
    # CORRIGÉ (v2): Utilise .get("name") pour éviter le KeyError sur les anciens profils
    if any(s.get("name") == clean_name for s in g_sources):
        await interaction.followup.send(f"❌ Un profil avec le nom `{clean_name}` existe déjà.", ephemeral=True)
        return

    # AJOUTÉ: Définir un message @everyone par défaut
    default_message = "@everyone {creator} est en ligne !"

    # Ajout de la configuration
    g_sources.append({
        "name": clean_name, # Clé unique
        "platform": platform_lower,
        "id": identifiant.strip(), # L'ID/URL/Nom
        "category": categorie.lower(), # live ou video (CORRIGÉ v3)
        "channel_id": canal.id,
        "config": {
            "api_key": api_key, # Clé spécifique (pour TikTok)
            "message_ping": default_message, # (MODIFIÉ: Message par défaut avec @everyone)
            "embed_json": None
        }
    })
    save_notif_data(notif_db)
    await interaction.followup.send(f"✅ Profil **{clean_name}** (`{platform_lower.capitalize()}` / `{categorie.capitalize()}`) ajouté pour {canal.mention}. Le ping `@everyone` est activé par défaut. Utilise `/notif config` pour le modifier.", ephemeral=True)


@notif_group.command(name="remove", description="Supprime un profil de notification.")
@app_commands.autocomplete(nom=profile_name_autocomplete)
@app_commands.describe(nom="Le nom unique du profil à supprimer.")
async def notif_remove(interaction: discord.Interaction, nom: str):
    await interaction.response.defer(ephemeral=True)
    guild_id_str = str(interaction.guild_id)
    g_config = notif_db.get("servers", {}).get(guild_id_str)

    if not g_config or not g_config.get("sources"):
        await interaction.followup.send("Aucun profil à supprimer.", ephemeral=True)
        return

    initial_count = len(g_config["sources"])
    # CORRIGÉ (v2): Utilise .get("name")
    g_config["sources"] = [s for s in g_config["sources"] if s.get("name") != nom]

    if len(g_config["sources"]) < initial_count:
        save_notif_data(notif_db)
        # Nettoyer aussi les "last_seen"
        last_seen = notif_db.setdefault("last_seen", {})
        last_seen_key = f"{guild_id_str}:{nom}"
        if last_seen_key in last_seen:
            del last_seen[last_seen_key]
        save_notif_data(notif_db)
        await interaction.followup.send(f"🗑️ Profil `{nom}` supprimé.", ephemeral=True)
    else:
        await interaction.followup.send(f"Profil `{nom}` non trouvé.", ephemeral=True)


@notif_group.command(name="list", description="Affiche les profils de notifications configurés.")
async def notif_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild_id_str = str(interaction.guild_id)
    g_sources = notif_db.get("servers", {}).get(guild_id_str, {}).get("sources", [])

    if not g_sources:
        await interaction.followup.send("Aucun profil de notification configuré.", ephemeral=True)
        return

    embed = discord.Embed(title=f"📡 Profils de notifications - {interaction.guild.name}", color=NEON_BLUE)
    description = ""
    # CORRIGÉ (v2): Utilise .get() partout
    for source in sorted(g_sources, key=lambda s: (s.get('platform', 'z'), s.get('name', 'z'))):
        channel = interaction.guild.get_channel(source.get("channel_id"))
        channel_mention = channel.mention if channel else "`Salon introuvable`"
        platform = source.get('platform', 'N/A').capitalize()
        category = source.get('category', 'N/A').capitalize()
        name = source.get('name', 'Profil Invalide')
        
        description += f"• **{name}** (`{platform}` / `{category}`)\n"
        description += f"  ID: `{source.get('id', 'N/A')}` ➡️ {channel_mention}\n"

    embed.description = description
    await interaction.followup.send(embed=embed, ephemeral=True)


# --- Commande d'Édition (Style /notif add) ---
@notif_group.command(name="edit", description="Modifie un profil existant directement (Arguments optionnels).")
@app_commands.autocomplete(nom=profile_name_autocomplete)
@app_commands.describe(
    nom="Le nom unique du profil à modifier.",
    identifiant="Nouveau pseudo/ID (Laisser vide pour ne pas changer)",
    canal="Nouveau salon (Laisser vide pour ne pas changer)",
    message="Nouveau message/ping (Laisser vide pour ne pas changer)",
    json="Nouveau JSON (Laisser vide pour ne pas changer)",
    api_key="Nouvelle clé API (Laisser vide pour ne pas changer)"
)
async def notif_edit(
    interaction: discord.Interaction,
    nom: str,
    identifiant: Optional[str] = None,
    canal: Optional[discord.TextChannel] = None,
    message: Optional[str] = None,
    json: Optional[str] = None,
    api_key: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    guild_id_str = str(interaction.guild_id)
    g_sources = notif_db.get("servers", {}).get(guild_id_str, {}).get("sources", [])

    source_to_edit = None
    for s in g_sources:
        if s.get("name") == nom:
            source_to_edit = s
            break

    if not source_to_edit:
        await interaction.followup.send(f"❌ Profil `{nom}` introuvable.", ephemeral=True)
        return

    changes = []
    config = source_to_edit.setdefault("config", {})

    # Mise à jour des champs si fournis
    if identifiant:
        source_to_edit["id"] = identifiant.strip()
        changes.append(f"• **Identifiant :** `{identifiant.strip()}`")
    
    if canal:
        source_to_edit["channel_id"] = canal.id
        changes.append(f"• **Salon :** {canal.mention}")

    if message:
        config["message_ping"] = message.strip()
        changes.append("• **Message :** Mis à jour")

    if json:
        config["embed_json"] = json.strip()
        changes.append("• **JSON :** Mis à jour")
    
    if api_key:
        config["api_key"] = api_key.strip()
        changes.append("• **API Key :** Mise à jour")

    if not changes:
        await interaction.followup.send("ℹ️ Aucune modification demandée (tous les champs optionnels étaient vides).", ephemeral=True)
        return

    save_notif_data(notif_db)
    
    response_text = f"✅ **Profil `{nom}` modifié avec succès !**\n" + "\n".join(changes)
    await interaction.followup.send(response_text, ephemeral=True)


# --- MODAL DE CONFIGURATION (Message / JSON / API) ---
class NotifConfigModal(Modal):
    def __init__(self, source_data: Dict):
        profile_name = source_data.get('name', 'Erreur')
        category = source_data.get('category', 'N/A').capitalize()
        super().__init__(title=f"Options: {profile_name} ({category})")
        
        self.source_data = source_data
        config = source_data.get("config", {})

        self.message_ping = TextInput(
            label="Message & Ping (HORS embed)",
            placeholder="Ex: @everyone {creator} est en live! {url}",
            default=config.get("message_ping", ""),
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.message_ping)
        
        self.embed_json = TextInput(
            label="Configuration JSON (Avancé)",
            placeholder="Collez le JSON d'embed ici. Laissez vide pour le mode simple.",
            default=config.get("embed_json", ""),
            required=False,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.embed_json)

        self.api_key = TextInput(
            label="Clé API (Requis pour TikTok)",
            placeholder="Clé API d'un service tiers (ex: RapidAPI).",
            default=config.get("api_key", ""),
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.api_key)


    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True) 
        config = self.source_data.setdefault("config", {})
        
        config["message_ping"] = self.message_ping.value.strip() or None
        config["embed_json"] = self.embed_json.value.strip() or None
        config["api_key"] = self.api_key.value.strip() or None 
        
        # Nettoyage
        config.pop("embed_title_simple", None)
        config.pop("embed_desc_simple", None)
        config.pop("embed_color_image_simple", None)
        
        response_message = f"⚙️ Configuration avancée de `{self.source_data.get('name')}` mise à jour."
        
        if config["embed_json"]:
            try:
                test_json_string = format_template(config["embed_json"])
                json.loads(test_json_string)
                response_message += "\n✅ JSON valide. Le mode simple sera ignoré."
            except json.JSONDecodeError as e:
                response_message += f"\n⚠️ **Erreur JSON :** `{e}`. Le bot tentera quand même."
        else:
            response_message += "\nℹ️ JSON vide. Mode simple activé."

        save_notif_data(notif_db)
        response_message += "\nUtilise `/notif test` pour confirmer."
        await interaction.followup.send(response_message, ephemeral=True)


@notif_group.command(name="config", description="Configure les options (Message, JSON) d'un profil (Mode Fenêtre).")
@app_commands.autocomplete(nom=profile_name_autocomplete)
@app_commands.describe(nom="Le nom unique du profil à configurer.")
async def notif_config(interaction: discord.Interaction, nom: str):
    guild_id_str = str(interaction.guild_id)
    g_sources = notif_db.get("servers", {}).get(guild_id_str, {}).get("sources", [])

    source_found = None
    for source in g_sources:
        if source.get("name") == nom:
            source_found = source
            break

    if not source_found:
        await interaction.response.send_message(f"Profil `{nom}` non trouvé.", ephemeral=True)
    else:
        await interaction.response.send_modal(NotifConfigModal(source_found))


@notif_group.command(name="test", description="Envoie une notification de test pour un profil.")
@app_commands.autocomplete(nom=profile_name_autocomplete)
@app_commands.describe(nom="Le nom unique du profil à tester.")
async def notif_test(interaction: discord.Interaction, nom: str):
    await interaction.response.defer(ephemeral=True)
    guild_id_str = str(interaction.guild_id)
    g_sources = notif_db.get("servers", {}).get(guild_id_str, {}).get("sources", [])

    source_to_test = None
    for s in g_sources:
        # CORRIGÉ (v2): Utilise .get("name")
        if s.get("name") == nom:
            source_to_test = s
            break

    if not source_to_test:
        await interaction.followup.send(f"Profil `{nom}` non trouvé.", ephemeral=True)
        return

    # S'assurer que la config existe
    source_to_test.setdefault("config", {})
    
    # Adapter le test à la catégorie (Live ou Vidéo)
    category = source_to_test.get("category", "live") # 'live' par défaut
    platform = source_to_test.get("platform", "unknown")
    identifier = source_to_test.get("id", "Testeur")

    # === DÉBUT DE LA CORRECTION (Placeholders par plateforme) ===

    is_live = (category == "live")
    
    # Définir les placeholders par défaut
    title = f"📣 LIVE (TEST) SUR {platform.capitalize()}"
    desc = f"Je suis en live! (Ceci est un test /notif test pour {platform})"
    game = "Inconnu"
    thumbnail_img = "https://via.placeholder.com/400x225.png/9146FF/FFFFFF?text=Test+PoxelBot"
    url = "https://discord.com"

    if platform == "kick":
        title = "🟢 LIVE KICK (TEST)"
        desc = "Je suis en live sur Kick! (Ceci est un test /notif test)"
        game = "Just Chatting"
        thumbnail_img = "https://i.imgur.com/tD36A9j.png" # Image d'exemple Kick
        url = f"https://kick.com/{identifier}"

    elif platform == "twitch":
        title = "🟣 LIVE TWITCH (TEST)"
        desc = "Grosse game sur Twitch! (Ceci est un test /notif test)"
        game = "Apex Legends"
        thumbnail_img = "https://i.imgur.com/vIqI4So.png" # Image d'exemple Twitch
        url = f"https://twitch.tv/{identifier}"
        
    elif platform == "youtube":
        if is_live:
            title = "🟥 LIVE YOUTUBE (TEST)"
            desc = "On se retrouve en direct sur YouTube! (Ceci est un test /notif test)"
            game = "YouTube" # L'API YT ne fournit pas toujours le jeu
        else: # category == "video"
            title = "🎥 NOUVELLE VIDÉO (TEST)"
            desc = "Ma dernière vidéo est sortie! (Ceci est un test /notif test)"
            game = "YouTube"
        thumbnail_img = "https://i.imgur.com/f033z2b.png" # Image d'exemple YouTube
        url = f"https://www.youtube.com/watch?v=dQw4w9WgXcQ" # Lien exemple

    # Créer un événement de test
    test_event = {
        "id": f"test_{int(get_adjusted_time().timestamp())}",
        "title": title,
        "url": url,
        "thumbnail": thumbnail_img, # Utilise la nouvelle image d'exemple
        "description": desc,
        "creator": identifier, 
        "creator_avatar": interaction.user.display_avatar.url, # Utilise ton avatar Discord pour le test
        "timestamp": get_adjusted_time().isoformat(),
        "is_live": is_live,
        "platform": platform,
        "game": game 
    }
    
    # === FIN DE LA CORRECTION ===
    
    # Envoyer la notification en utilisant la config SAUVEGARDÉE
    try:
        await send_notification(interaction.guild, source_to_test, test_event)
        await interaction.followup.send(f"Notification de test (`{category}`) envoyée pour `{nom}` avec la configuration sauvegardée ! L'embed doit correspondre au style demandé.", ephemeral=True)
    except Exception as e:
        logger.exception(f"Erreur lors de l'ENVOI du test pour {nom}: {e}")
        await interaction.followup.send(f"❌ **Erreur lors de la création de l'embed de test.**\n"
                                        f"Vérifie ton JSON ou ta configuration simple.\n"
                                        f"Erreur: `{e}`", ephemeral=True)

# --- NOUVEAU: Commande de Check Forcé ---
@notif_group.command(name="check_now", description="Force la vérification immédiate de TOUTES les sources (YouTube inclus !).")
async def notif_check_now(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild_id_str = str(interaction.guild_id)
    g_config = notif_db.get("servers", {}).get(guild_id_str)
    
    if not g_config or not g_config.get("sources"):
        await interaction.followup.send("Aucune notification configurée sur ce serveur.", ephemeral=True)
        return

    sources = g_config["sources"]
    await interaction.followup.send(f"🔄 **Vérification forcée lancée pour {len(sources)} sources (YouTube compris)...**\n*Cela peut prendre quelques instants.*", ephemeral=True)

    tasks_list = []
    for source in sources:
        # On appelle directement la fonction de traitement (Partie 3)
        tasks_list.append(process_single_source(interaction.guild, source))

    if tasks_list:
        await asyncio.gather(*tasks_list, return_exceptions=True)
    
    # On force la sauvegarde après le scan manuel
    save_notif_data(notif_db)

    try:
        await interaction.edit_original_response(content=f"✅ **Vérification manuelle terminée !**\nLes nouvelles notifications ont été envoyées (s'il y en avait).")
    except:
        pass # Si le message a été supprimé entre temps

client.tree.add_command(notif_group)

# --- Commandes Freegames ---
freegames_group = app_commands.Group(name="freegames", description="Gère les notifications de jeux gratuits.", default_permissions=discord.Permissions(administrator=True))

@freegames_group.command(name="config", description="Configure le salon pour les annonces de jeux gratuits.")
@app_commands.describe(salon="Le salon où envoyer les notifications.")
async def freegames_config(interaction: discord.Interaction, salon: discord.TextChannel):
    db.setdefault("settings", {}).setdefault("free_games_settings", {})["channel_id"] = salon.id
    save_data(db)
    await interaction.response.send_message(f"✅ Annonces de jeux gratuits configurées pour {salon.mention}.", ephemeral=True)

@freegames_group.command(name="remove", description="Désactive les annonces de jeux gratuits (Supprime le salon configuré).")
async def freegames_remove(interaction: discord.Interaction):
    settings = db.setdefault("settings", {}).setdefault("free_games_settings", {})
    if settings.get("channel_id"):
        settings["channel_id"] = None
        save_data(db)
        await interaction.response.send_message("✅ Le salon des jeux gratuits a été supprimé. Les annonces sont désactivées.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucun salon n'était configuré pour les jeux gratuits.", ephemeral=True)

client.tree.add_command(freegames_group)


@client.tree.command(name="free", description="Affiche les derniers jeux gratuits trouvés.")
async def free(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    api_url = "https://www.gamerpower.com/api/giveaways?platform=pc&sort-by=date" # PC, trié par date
    # (Va utiliser le nouveau fetch_url hybride)
    games = await fetch_url(api_url, response_type='json')

    if games is None or not isinstance(games, list):
        await interaction.followup.send("Impossible de récupérer la liste des jeux gratuits pour le moment.", ephemeral=True)
        return

    if not games:
        await interaction.followup.send("Aucun jeu gratuit trouvé actuellement.", ephemeral=True)
        return

    # Construire les embeds
    embeds_to_send = []
    # Pas de limite ici, on prend tout (le chunking gère l'affichage)
    for game_data in games: 
        try:
            embed = await create_free_game_embed(game_data)
            embeds_to_send.append(embed)
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'embed pour le jeu {game_data.get('title')}: {e}")

    if embeds_to_send:
        # Envoi groupé (chunking par 10)
        chunk_size = 10
        chunks = [embeds_to_send[i:i + chunk_size] for i in range(0, len(embeds_to_send), chunk_size)]
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                await interaction.followup.send(content="🎁 **Voici TOUS les jeux PC gratuits trouvés :**", embeds=chunk, ephemeral=True)
            else:
                await interaction.followup.send(embeds=chunk, ephemeral=True)
    else:
        # Si aucun embed n'a pu être créé
        await interaction.followup.send("Erreur lors de la récupération des détails des jeux gratuits.", ephemeral=True)

# ==================================================================================================
# 12.5. COMMANDES CINÉ PIXEL (NOUVEAU - Catégorisé)
# ==================================================================================================

# --- Commande de Configuration ---
cineconfig_group = app_commands.Group(name="cineconfig", description="Configure les salons pour Ciné Pixel.", default_permissions=discord.Permissions(administrator=True))

@cineconfig_group.command(name="set_channel", description="Associe un salon à une catégorie de sorties.")
@app_commands.describe(
    categorie="La catégorie à configurer.",
    salon="Le salon où envoyer les notifications."
)
@app_commands.choices(categorie=[
    app_commands.Choice(name="Sorties Séries", value="news_series"),
    app_commands.Choice(name="Sorties Anime", value="news_anime"),
    app_commands.Choice(name="Sorties Cartoons", value="news_cartoons"),
    app_commands.Choice(name="Sorties Films", value="news_movies"),
    app_commands.Choice(name="Épisodes Séries", value="episodes_series"),
    app_commands.Choice(name="Épisodes Anime", value="episodes_anime"),
    app_commands.Choice(name="Épisodes Cartoons", value="episodes_cartoons"),
])
async def cineconfig_set(interaction: discord.Interaction, categorie: str, salon: discord.TextChannel):
    db.setdefault("settings", {}).setdefault("cine_pixel_channels", {})[categorie] = salon.id
    save_data(db)
    
    # Mapping des noms lisibles
    nice_names = {
        "news_series": "Sorties Séries", "news_anime": "Sorties Anime", "news_cartoons": "Sorties Cartoons",
        "news_movies": "Sorties Films", "episodes_series": "Épisodes Séries", 
        "episodes_anime": "Épisodes Anime", "episodes_cartoons": "Épisodes Cartoons"
    }
    
    await interaction.response.send_message(f"✅ La catégorie **{nice_names[categorie]}** est maintenant envoyée dans {salon.mention}.", ephemeral=True)

@cineconfig_group.command(name="remove_channel", description="Désactive les notifications pour une catégorie.")
@app_commands.describe(categorie="La catégorie à désactiver.")
@app_commands.choices(categorie=[
    app_commands.Choice(name="Sorties Séries", value="news_series"),
    app_commands.Choice(name="Sorties Anime", value="news_anime"),
    app_commands.Choice(name="Sorties Cartoons", value="news_cartoons"),
    app_commands.Choice(name="Sorties Films", value="news_movies"),
    app_commands.Choice(name="Épisodes Séries", value="episodes_series"),
    app_commands.Choice(name="Épisodes Anime", value="episodes_anime"),
    app_commands.Choice(name="Épisodes Cartoons", value="episodes_cartoons"),
])
async def cineconfig_remove(interaction: discord.Interaction, categorie: str):
    channels_config = db.setdefault("settings", {}).setdefault("cine_pixel_channels", {})
    if categorie in channels_config:
        del channels_config[categorie]
        save_data(db)
        await interaction.response.send_message(f"✅ Notifications désactivées pour la catégorie sélectionnée.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucune notification n'était configurée pour cette catégorie.", ephemeral=True)

client.tree.add_command(cineconfig_group)

# --- Helper pour les Commandes Privées ---
async def handle_manual_cine_check(interaction: discord.Interaction, category_key: str, media_type: str, is_anime: bool = False, is_cartoon: bool = False):
    """
    Exécute une vérification manuelle et envoie les résultats à l'utilisateur (privé).
    """
    await interaction.response.defer(ephemeral=True)
    if not TMDB_API_KEY:
        await interaction.followup.send("❌ Clé API TMDB manquante.", ephemeral=True)
        return

    # URL TMDB adaptée
    if "news" in category_key:
        if media_type == 'movie':
            url = f"https://api.themoviedb.org/3/movie/now_playing?api_key={TMDB_API_KEY}&language=fr-FR&page=1"
        else: # TV
            url = f"https://api.themoviedb.org/3/tv/on_the_air?api_key={TMDB_API_KEY}&language=fr-FR&page=1"
    else: 
        url = f"https://api.themoviedb.org/3/tv/airing_today?api_key={TMDB_API_KEY}&language=fr-FR&page=1"

    data = await fetch_url(url, response_type='json')
    if not data or "results" not in data:
        await interaction.followup.send("Aucune donnée trouvée.", ephemeral=True)
        return

    embeds_to_send = []
    today = get_adjusted_time().date()

    for item in data["results"]:
        item_id = item["id"]
        
        # Filtrage
        detected_cat = classify_content(item, media_type)
        should_process = False
        if is_anime and detected_cat == 'anime': should_process = True
        elif is_cartoon and detected_cat == 'cartoon': should_process = True
        elif not is_anime and not is_cartoon and detected_cat == 'series' and media_type == 'tv': should_process = True
        elif media_type == 'movie' and not is_anime and not is_cartoon: should_process = True

        if not should_process: continue

        try:
            embed = None
            if "news" in category_key:
                if media_type == 'tv':
                    first_air = item.get('first_air_date')
                    # Pour la commande manuelle, on est plus souple sur la date (2 semaines)
                    if first_air and (today - datetime.datetime.strptime(first_air, "%Y-%m-%d").date()).days < 14:
                        embed = await create_cine_pixel_embed(item_id, media_type, detected_cat, is_episode=False)
                else: # Movie
                    embed = await create_cine_pixel_embed(item_id, media_type, detected_cat, is_episode=False)

            elif "episodes" in category_key and media_type == 'tv':
                details_url = f"https://api.themoviedb.org/3/tv/{item_id}?api_key={TMDB_API_KEY}&language=fr-FR"
                det = await fetch_url(details_url, response_type='json')
                last_ep = det.get('last_episode_to_air')
                if last_ep:
                    # Pour manuel, on affiche si récent (pas juste aujourd'hui)
                    embed = await create_cine_pixel_embed(item_id, media_type, detected_cat, is_episode=True, episode_data=last_ep)

            if embed:
                embeds_to_send.append(embed)
        except: pass

    if embeds_to_send:
        # Envoi par paquets de 10 (car c'est privé, pas de risque de spam channel)
        # Mais attention limite taille. On reste prudent avec 5.
        chunk_size = 5
        chunks = [embeds_to_send[i:i + chunk_size] for i in range(0, len(embeds_to_send), chunk_size)]
        
        await interaction.followup.send(f"🎬 **Résultats pour {category_key} :**", ephemeral=True)
        for chunk in chunks:
            await interaction.followup.send(embeds=chunk, ephemeral=True)
    else:
        await interaction.followup.send("Aucun résultat récent trouvé pour cette catégorie.", ephemeral=True)

# --- Commandes Publiques (Manuelles / Privées) ---

@client.tree.command(name="news_series", description="[Privé] Voir les sorties récentes de séries.")
async def cmd_news_series(interaction: discord.Interaction):
    await handle_manual_cine_check(interaction, 'news_series', 'tv', is_anime=False, is_cartoon=False)

@client.tree.command(name="news_anime", description="[Privé] Voir les sorties récentes d'animés.")
async def cmd_news_anime(interaction: discord.Interaction):
    await handle_manual_cine_check(interaction, 'news_anime', 'tv', is_anime=True)

@client.tree.command(name="news_cartoons", description="[Privé] Voir les sorties récentes de cartoons.")
async def cmd_news_cartoons(interaction: discord.Interaction):
    await handle_manual_cine_check(interaction, 'news_cartoons', 'tv', is_cartoon=True)

@client.tree.command(name="news_movies", description="[Privé] Voir les sorties récentes de films.")
async def cmd_news_movies(interaction: discord.Interaction):
    await handle_manual_cine_check(interaction, 'news_movies', 'movie')

@client.tree.command(name="episodes_series", description="[Privé] Voir les épisodes de séries sortis aujourd'hui.")
async def cmd_episodes_series(interaction: discord.Interaction):
    await handle_manual_cine_check(interaction, 'episodes_series', 'tv', is_anime=False, is_cartoon=False)

@client.tree.command(name="episodes_anime", description="[Privé] Voir les épisodes d'animés sortis aujourd'hui.")
async def cmd_episodes_anime(interaction: discord.Interaction):
    await handle_manual_cine_check(interaction, 'episodes_anime', 'tv', is_anime=True)

@client.tree.command(name="episodes_cartoons", description="[Privé] Voir les épisodes de cartoons sortis aujourd'hui.")
async def cmd_episodes_cartoons(interaction: discord.Interaction):
    await handle_manual_cine_check(interaction, 'episodes_cartoons', 'tv', is_cartoon=True)


# --- NOUVEAU: Commande de Test Admin (Force Post No Limit) ---
@client.tree.command(name="admin_test_news", description="[Admin] Force la publication (FreeGames ou CinéPixel) SANS LIMITES.")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(module="Le module à tester.")
async def admin_test_news(
    interaction: discord.Interaction,
    module: Literal["FreeGames", "CinéPixel"]
):
    await interaction.response.defer(ephemeral=True)
    
    if module == "FreeGames":
        free_channel_id = db["settings"].get("free_games_settings", {}).get("channel_id")
        if not free_channel_id:
            await interaction.followup.send("❌ Salon FreeGames non configuré.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(free_channel_id)
        if not channel:
            await interaction.followup.send("❌ Salon FreeGames introuvable.", ephemeral=True)
            return
            
        # Fetch
        api_url = "https://www.gamerpower.com/api/giveaways?platform=pc"
        games = await fetch_url(api_url, response_type='json')
        
        if games:
            embeds_to_send = []
            for game in games: # No limit, on prend tout pour le test
                try:
                    embed = await create_free_game_embed(game)
                    embeds_to_send.append(embed)
                except: pass
            
            if embeds_to_send:
                # CORRECTION CRITIQUE: Envoi 1 par 1 pour éviter l'erreur "Embed size > 6000"
                # Les descriptions cumulées de 5 ou 10 embeds dépassent la limite Discord.
                await interaction.followup.send(f"✅ Envoi de {len(embeds_to_send)} embeds en cours (1 par 1 pour sécurité)...", ephemeral=True)
                
                for i, embed in enumerate(embeds_to_send):
                    msg = None
                    if i == 0:
                        msg = f"[TEST ADMIN] @everyone 🚨 **ALERTE JEU GRATUIT !** 🚨\nUn ou plusieurs nouveaux cadeaux sont disponibles ! 🎁🔥"
                    
                    try:
                        await channel.send(content=msg, embed=embed)
                        await asyncio.sleep(1.5) # Pause anti-ratelimit
                    except Exception as e:
                        logger.error(f"Erreur envoi embed {i}: {e}")

                await interaction.followup.send(f"✅ Test terminé.", ephemeral=True)
            else:
                await interaction.followup.send("⚠️ API OK mais aucun embed généré.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Erreur API GamerPower (vide ou HS).", ephemeral=True)

    elif module == "CinéPixel":
        if not TMDB_API_KEY:
            await interaction.followup.send("❌ Clé API TMDB manquante.", ephemeral=True)
            return
        
        # Pour le test, on prend le salon des Séries par défaut ou on demande de configurer
        channels_cfg = db["settings"].get("cine_pixel_channels", {})
        target_channel_id = channels_cfg.get("news_series") or channels_cfg.get("news_movies")
        
        if not target_channel_id:
            await interaction.followup.send("❌ Aucun salon Ciné Pixel configuré (commencez par /cineconfig set_channel news_series ...).", ephemeral=True)
            return
            
        channel = interaction.guild.get_channel(target_channel_id)
        if not channel:
            await interaction.followup.send("❌ Salon introuvable.", ephemeral=True)
            return

        # Fetch Séries pour le test
        url_tv = f"https://api.themoviedb.org/3/tv/on_the_air?api_key={TMDB_API_KEY}&language=fr-FR&page=1"
        data_tv = await fetch_url(url_tv, response_type='json')
        
        embeds_to_send = []
        
        # --- AJOUT DU TEST BIG EVENT ---
        # On force l'ajout d'Arcane (94605) pour valider le style "Big Event"
        try:
            embed_big = await create_cine_pixel_embed(94605, "tv", "news_anime", is_episode=False)
            if embed_big: 
                embeds_to_send.append(embed_big)
                await interaction.channel.send(content="[DEBUG] Ajout forcé de 'Arcane' pour tester le style Big Event.", ephemeral=True)
        except Exception as e:
            logger.error(f"Test Big Event failed: {e}")
        # -------------------------------

        if data_tv and "results" in data_tv:
            for tv in data_tv["results"]: # No limit
                # On teste avec des séries standards
                embed = await create_cine_pixel_embed(tv["id"], "tv", "series", is_episode=False)
                if embed: embeds_to_send.append(embed)
        
        if embeds_to_send:
            await interaction.followup.send(f"✅ Envoi de {len(embeds_to_send)} embeds de test dans {channel.mention} (1 par 1)...", ephemeral=True)
            
            for i, embed in enumerate(embeds_to_send):
                msg = None
                if i == 0:
                    msg = f"[TEST ADMIN] 🍿 **CINÉ PIXEL ACTU !**"
                
                try:
                    await channel.send(content=msg, embed=embed)
                    await asyncio.sleep(1.5)
                except Exception as e:
                    logger.error(f"Erreur envoi embed {i}: {e}")

            await interaction.followup.send(f"✅ Test terminé.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Aucune donnée trouvée sur TMDB.", ephemeral=True)


# ==================================================================================================
# 13. SYSTÈME DE TEAM
# ==================================================================================================
team_group = app_commands.Group(name="team", description="Gère ton équipe.")

async def team_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete pour les noms de teams."""
    teams = db.get("teams", {})
    return [
        app_commands.Choice(name=name, value=name)
        for name, data in teams.items()
        if isinstance(data, dict) and isinstance(data.get("name"), str) and current.lower() in data["name"].lower()
    ][:25]

def get_team_color(team_data: Dict) -> int:
    """Retourne la couleur de la team ou la couleur par défaut."""
    color_hex = team_data.get("color_hex")
    if color_hex and re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", color_hex):
        try:
            return int(color_hex.lstrip('#'), 16)
        except ValueError:
            return TEAM_COLOR 
    return TEAM_COLOR 

# --- Commandes Team ---
@team_group.command(name="create", description="Crée une nouvelle équipe.")
@app_commands.describe(nom="Le nom de votre équipe.")
async def team_create(interaction: discord.Interaction, nom: str):
    user_data = get_user_xp_data(interaction.user.id)
    if user_data.get("team_name"):
        await interaction.response.send_message("❌ Tu fais déjà partie d'une équipe !", ephemeral=True)
        return

    team_name = nom.strip()
    if not team_name:
        await interaction.response.send_message("❌ Le nom de l'équipe ne peut pas être vide.", ephemeral=True)
        return

    if team_name in db.get("teams", {}):
        await interaction.response.send_message("❌ Une équipe avec ce nom existe déjà.", ephemeral=True)
        return

    # Créer la team
    db.setdefault("teams", {})[team_name] = {
        "name": team_name,
        "creator_id": interaction.user.id,
        "members": [interaction.user.id],
        "logo_url": None,
        "role_id": None,
        "color_hex": f"#{TEAM_COLOR:06x}" 
    }
    user_data["team_name"] = team_name
    save_data(db)

    embed = discord.Embed(
        title=f"🎉 Équipe Créée : {team_name}",
        description=f"Félicitations {interaction.user.mention}, tu as fondé l'équipe **{team_name}** !",
        color=TEAM_COLOR
    )
    await interaction.response.send_message(embed=embed)


@team_group.command(name="add", description="Ajoute un membre à ton équipe (tu dois être le créateur).")
@app_commands.describe(membre="Le membre à ajouter.")
async def team_add(interaction: discord.Interaction, membre: discord.Member):
    user_data = get_user_xp_data(interaction.user.id)
    team_name = user_data.get("team_name")
    if not team_name:
        await interaction.response.send_message("❌ Tu n'es dans aucune équipe.", ephemeral=True)
        return

    team_data = db.get("teams", {}).get(team_name)
    if not team_data or team_data.get("creator_id") != interaction.user.id:
        await interaction.response.send_message("❌ Seul le créateur de l'équipe peut ajouter des membres.", ephemeral=True)
        return

    if membre.bot or membre.id == interaction.user.id:
        await interaction.response.send_message("❌ Tu ne peux pas t'ajouter toi-même ou un bot.", ephemeral=True)
        return

    target_data = get_user_xp_data(membre.id)
    if target_data.get("team_name"):
        await interaction.response.send_message(f"❌ {membre.display_name} est déjà dans une équipe.", ephemeral=True)
        return

    if membre.id in team_data.get("members", []):
        await interaction.response.send_message(f"❌ {membre.display_name} est déjà dans ton équipe.", ephemeral=True)
        return

    # Ajouter le membre
    team_data.setdefault("members", []).append(membre.id)
    target_data["team_name"] = team_name
    save_data(db)

    await interaction.response.send_message(f"✅ {membre.mention} a été ajouté à l'équipe **{team_name}**.", ephemeral=True)


@team_group.command(name="remove", description="Retire un membre ou dissout l'équipe si tu es le créateur.")
@app_commands.describe(membre="Le membre à retirer (optionnel, si créateur).")
async def team_remove(interaction: discord.Interaction, membre: Optional[discord.Member] = None):
    user_data = get_user_xp_data(interaction.user.id)
    team_name = user_data.get("team_name")
    if not team_name:
        await interaction.response.send_message("❌ Tu n'es dans aucune équipe.", ephemeral=True)
        return

    team_data = db.get("teams", {}).get(team_name)
    if not team_data: 
        user_data["team_name"] = None
        save_data(db)
        await interaction.response.send_message("❌ Erreur : Ton équipe n'existe plus. Ton statut a été réinitialisé.", ephemeral=True)
        return

    is_creator = team_data.get("creator_id") == interaction.user.id

    if membre: # Action de retirer un membre (par le créateur)
        if not is_creator:
            await interaction.response.send_message("❌ Seul le créateur peut retirer des membres.", ephemeral=True)
            return
        if membre.id == interaction.user.id:
            await interaction.response.send_message("❌ Le créateur ne peut pas se retirer. Utilise `/team remove` sans argument pour dissoudre.", ephemeral=True)
            return
        if membre.id not in team_data.get("members", []):
            await interaction.response.send_message(f"❌ {membre.display_name} n'est pas dans ton équipe.", ephemeral=True)
            return

        # Retirer le membre
        team_data["members"].remove(membre.id)
        target_data = get_user_xp_data(membre.id)
        target_data["team_name"] = None
        save_data(db)
        await interaction.response.send_message(f"👢 {membre.mention} a été retiré de l'équipe **{team_name}**.", ephemeral=True)

    elif is_creator: # Action de dissoudre (par le créateur)
        # Informer les membres et réinitialiser leur statut
        member_ids = team_data.get("members", [])
        for mid in member_ids:
            member_data = get_user_xp_data(mid)
            member_data["team_name"] = None
        
        # Supprimer la team
        del db["teams"][team_name]
        save_data(db)
        await interaction.response.send_message(f"💥 L'équipe **{team_name}** a été dissoute.", ephemeral=True)

    else: # Action de quitter (par un membre non-créateur)
        if interaction.user.id in team_data.get("members", []): 
            team_data["members"].remove(interaction.user.id)
        user_data["team_name"] = None
        save_data(db)
        await interaction.response.send_message(f"👋 Tu as quitté l'équipe **{team_name}**.", ephemeral=True)


@team_group.command(name="set_logo", description="Définit le logo de ton équipe (URL).")
@app_commands.describe(url="L'URL de l'image pour le logo.")
async def team_set_logo(interaction: discord.Interaction, url: str):
    user_data = get_user_xp_data(interaction.user.id)
    team_name = user_data.get("team_name")
    if not team_name: return await interaction.response.send_message("❌ Tu n'es dans aucune équipe.", ephemeral=True)
    team_data = db.get("teams", {}).get(team_name)
    if not team_data or team_data.get("creator_id") != interaction.user.id: return await interaction.response.send_message("❌ Seul le créateur peut définir le logo.", ephemeral=True)

    if not url.startswith(("http://", "https://")):
        return await interaction.response.send_message("❌ URL invalide.", ephemeral=True)

    team_data["logo_url"] = url
    save_data(db)
    await interaction.response.send_message(f"🖼️ Logo de l'équipe **{team_name}** mis à jour.", ephemeral=True)


@team_group.command(name="set_role", description="Définit un rôle associé à l'équipe.")
@app_commands.describe(role="Le rôle à associer à l'équipe.")
async def team_set_role(interaction: discord.Interaction, role: discord.Role):
    user_data = get_user_xp_data(interaction.user.id)
    team_name = user_data.get("team_name")
    if not team_name: return await interaction.response.send_message("❌ Tu n'es dans aucune équipe.", ephemeral=True)
    team_data = db.get("teams", {}).get(team_name)
    if not team_data or team_data.get("creator_id") != interaction.user.id: return await interaction.response.send_message("❌ Seul le créateur peut définir le rôle.", ephemeral=True)

    team_data["role_id"] = role.id
    save_data(db)
    await interaction.response.send_message(f"🏷️ Rôle associé à l'équipe **{team_name}** défini sur {role.mention}.", ephemeral=True)


@team_group.command(name="set_color", description="Définit la couleur de l'embed de l'équipe (#RRGGBB).")
@app_commands.describe(couleur="La couleur hexadécimale (ex: #6441a5).")
async def team_set_color(interaction: discord.Interaction, couleur: str):
    user_data = get_user_xp_data(interaction.user.id)
    team_name = user_data.get("team_name")
    if not team_name: return await interaction.response.send_message("❌ Tu n'es dans aucune équipe.", ephemeral=True)
    team_data = db.get("teams", {}).get(team_name)
    if not team_data or team_data.get("creator_id") != interaction.user.id: return await interaction.response.send_message("❌ Seul le créateur peut définir la couleur.", ephemeral=True)

    if not re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", couleur):
        return await interaction.response.send_message("❌ Format de couleur invalide. Utilise #RRGGBB.", ephemeral=True)

    team_data["color_hex"] = couleur
    save_data(db)
    await interaction.response.send_message(f"🎨 Couleur de l'équipe **{team_name}** mise à jour.", ephemeral=True)


@team_group.command(name="info", description="Affiche les informations d'une équipe.")
@app_commands.describe(nom="Le nom de l'équipe (optionnel, affiche la tienne sinon).")
@app_commands.autocomplete(nom=team_autocomplete)
async def team_info(interaction: discord.Interaction, nom: Optional[str] = None):
    target_team_name = nom
    if not target_team_name:
        user_data = get_user_xp_data(interaction.user.id)
        target_team_name = user_data.get("team_name")
        if not target_team_name:
            return await interaction.response.send_message("❌ Tu n'es dans aucune équipe. Spécifie un nom.", ephemeral=True)

    team_data = db.get("teams", {}).get(target_team_name)
    if not team_data:
        return await interaction.response.send_message(f"❌ L'équipe **{target_team_name}** n'existe pas.", ephemeral=True)

    creator_mention_str = "`Inconnu`"
    if team_data.get("creator_id"):
        try:
            creator = await client.fetch_user(team_data.get("creator_id"))
            creator_mention_str = creator.mention
        except (discord.NotFound, discord.HTTPException):
             logger.warning(f"Impossible de fetch le créateur de team ID: {team_data.get('creator_id')}")
             creator_mention_str = f"`ID:{team_data.get('creator_id')}`"


    member_ids = team_data.get("members", [])
    members_mentions = []
    for mid in member_ids:
        member = interaction.guild.get_member(mid)
        members_mentions.append(member.mention if member else f"`ID:{mid}`")

    role = interaction.guild.get_role(team_data.get("role_id", 0))
    color = get_team_color(team_data)

    embed = discord.Embed(
        title=f"🔰 Infos Équipe : {target_team_name}",
        color=color
    )
    if team_data.get("logo_url"):
        embed.set_thumbnail(url=team_data["logo_url"])

    embed.add_field(name="👑 Créateur", value=creator_mention_str, inline=True)
    embed.add_field(name="👥 Membres", value=str(len(member_ids)), inline=True)
    embed.add_field(name="🏷️ Rôle Associé", value=role.mention if role else "`Aucun`", inline=True)

    members_str = ", ".join(members_mentions)
    if len(members_str) > 1020: members_str = members_str[:1020] + "..." 
    embed.add_field(name="📜 Liste des Membres", value=members_str if members_str else "`Aucun`", inline=False)
    
    embed = apply_embed_styles(embed, "team_info") 
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="teamlist", description="Affiche la liste de toutes les équipes.")
async def teamlist(interaction: discord.Interaction):
    teams = db.get("teams", {})
    if not teams:
        return await interaction.response.send_message("Aucune équipe créée pour le moment.", ephemeral=True)

    embed = discord.Embed(title="📋 Liste des Équipes", color=TEAM_COLOR)
    description = ""
    sorted_teams = sorted(teams.items())

    for name, data in sorted_teams:
        creator_id = data.get("creator_id")
        creator_mention = f"<@{creator_id}>" if creator_id else "`Inconnu`"
        member_count = len(data.get("members", []))
        description += f"• **{name}** (Créateur: {creator_mention}) - {member_count} membre{'s' if member_count != 1 else ''}\n"
        if len(description) > 3900: 
            description += "\n*... et plus encore.*"
            break

    embed.description = description
    await interaction.response.send_message(embed=embed)

client.tree.add_command(team_group)

# ==================================================================================================
# 14. SYSTÈME D'AVATAR DYNAMIQUE
# ==================================================================================================

async def fetch_image_bytes(url: str) -> Optional[bytes]:
    """Télécharge une image depuis une URL et retourne les bytes."""
    if not url or not url.startswith(('http://', 'https://')):
        logger.error(f"Avatar Fetch: URL invalide ou manquante: {url}")
        return None
    
    image_bytes = await fetch_url(url, response_type='bytes')
    if not image_bytes:
        logger.error(f"Avatar Fetch: Impossible de télécharger l'image pour {url}")
        return None
    return image_bytes


async def trigger_avatar_change(trigger_key: str, force: bool = False):
    """Logique principale pour gérer les changements d'avatar."""
    if not db['settings'].get('avatar_enabled', True):
        logger.debug(f"Avatar: Changement pour '{trigger_key}' ignoré (Système désactivé).")
        return

    now_utc = get_adjusted_time()

    if not force:
        last_change_str = db['settings'].get('avatar_last_changed')
        if last_change_str:
            try:
                last_change_time = datetime.datetime.fromisoformat(last_change_str).replace(tzinfo=SERVER_TIMEZONE)
                cooldown_seconds = db['settings'].get('avatar_cooldown_seconds', 300)
                if now_utc < last_change_time + datetime.timedelta(seconds=cooldown_seconds):
                    logger.info(f"Avatar: Changement pour '{trigger_key}' ignoré (Cooldown global actif).")
                    return
            except ValueError:
                logger.error(f"Avatar: Timestamp 'avatar_last_changed' invalide: {last_change_str}")
                db['settings']['avatar_last_changed'] = None

    trigger_config = db.get('avatar_triggers', {}).get(trigger_key)
    if not trigger_config or not trigger_config.get('image_url'):
        logger.debug(f"Avatar: Déclencheur '{trigger_key}' non configuré ou sans image URL.")
        default_url = db['settings'].get('avatar_default_url')
        if default_url and trigger_key != 'default':
            logger.debug(f"Avatar: Utilisation de l'avatar par défaut car '{trigger_key}' n'est pas configuré.")
            await trigger_avatar_change('default', force=force)
        return

    image_url = trigger_config['image_url']
    duration_str = trigger_config.get('duration', '0s')
    duration_delta = parse_duration(duration_str)
    if not isinstance(duration_delta, datetime.timedelta):
        logger.error(f"Avatar: Durée invalide '{duration_str}' pour trigger '{trigger_key}'. Utilisation de 0s.")
        duration_delta = datetime.timedelta(seconds=0)

    current_avatar_url = client.user.avatar.url if client.user.avatar else db['settings'].get('avatar_default_url')

    image_bytes = await fetch_image_bytes(image_url)
    if not image_bytes:
        logger.error(f"Avatar: Impossible de télécharger l'image pour '{trigger_key}' depuis {image_url}.")
        return

    try:
        await client.user.edit(avatar=image_bytes)
        logger.info(f"Avatar: Changé pour le déclencheur '{trigger_key}'.")

        revert_time_iso = (now_utc + duration_delta).isoformat() if duration_delta.total_seconds() > 0 else None
        avatar_stack = db.setdefault('avatar_stack', [])
        avatar_stack.insert(0, {
            'trigger': trigger_key,
            'image_url': image_url,
            'revert_time': revert_time_iso,
            'previous_avatar_url': current_avatar_url
        })
        db['avatar_stack'] = avatar_stack[:10]
        db['settings']['avatar_last_changed'] = now_utc.isoformat()
        save_data(db)

    except discord.errors.HTTPException as e:
        if e.status == 429:
            retry_after = e.retry_after or 60
            logger.warning(f"Avatar: Rate limit atteint. Prochain changement possible dans {retry_after:.2f}s.")
        else:
            logger.error(f"Avatar: Erreur HTTP lors du changement d'avatar: {e.status} - {e.text}")
    except Exception as e:
        logger.exception(f"Avatar: Erreur inattendue lors du changement d'avatar: {e}")


async def revert_avatar():
    """Restaure l'avatar précédent depuis la pile."""
    avatar_stack = db.get('avatar_stack', [])
    if not avatar_stack:
        logger.debug("Avatar Revert: Pile vide, rien à restaurer.")
        return
    avatar_stack.pop(0)
    target_state = avatar_stack[0] if avatar_stack else None
    target_url = target_state['image_url'] if target_state else db['settings'].get('avatar_default_url')
    logger.info(f"Avatar Revert: Tentative de restauration vers {'l\'état précédent (' + target_state['trigger'] + ')' if target_state else 'l\'avatar par défaut'}.")
    if target_url:
        image_bytes = await fetch_image_bytes(target_url)
        if image_bytes:
            try:
                await client.user.edit(avatar=image_bytes)
                logger.info(f"Avatar Revert: Avatar restauré avec succès.")
            except discord.errors.HTTPException as e:
                logger.error(f"Avatar Revert: Erreur HTTP lors de la restauration: {e.status} - {e.text}")
            except Exception as e:
                logger.exception(f"Avatar Revert: Erreur inattendue lors de la restauration: {e}")
        else:
            logger.error(f"Avatar Revert: Impossible de télécharger l'image précédente/défaut depuis {target_url}.")
            try:
                await client.user.edit(avatar=None)
                logger.warning("Avatar Revert: Image précédente/défaut introuvable, avatar retiré.")
            except Exception: pass
    else:
        try:
            await client.user.edit(avatar=None)
            logger.info("Avatar Revert: Pile vide et pas de défaut, avatar retiré.")
        except discord.errors.HTTPException as e:
            logger.error(f"Avatar Revert: Erreur HTTP lors de la suppression de l'avatar: {e.status} - {e.text}")
        except Exception as e:
            logger.exception(f"Avatar Revert: Erreur inattendue lors de la suppression de l'avatar: {e}")
    db['avatar_stack'] = avatar_stack
    save_data(db)


def parse_duration(duration_str: str) -> datetime.timedelta:
    """Parse une chaîne de durée comme '5m', '1h', '2d' en timedelta."""
    duration_str = duration_str.lower().strip()
    if not re.match(r"^\d+[smhd]$", duration_str):
        return datetime.timedelta(seconds=0)
    num = int(duration_str[:-1])
    unit = duration_str[-1]
    if unit == 's': return datetime.timedelta(seconds=num)
    elif unit == 'm': return datetime.timedelta(minutes=num)
    elif unit == 'h': return datetime.timedelta(hours=num)
    elif unit == 'd': return datetime.timedelta(days=num)
    return datetime.timedelta(seconds=0)


avatar_group = app_commands.Group(name="avatar", description="Gère le système d'avatar dynamique.")
avatar_config_group = app_commands.Group(name="config", description="Configure le système d'avatar.", parent=avatar_group, default_permissions=discord.Permissions(administrator=True))
AVATAR_TRIGGERS_MAP = {
    'xp_gain': 'Gain XP/Level Up',
    'member_join': 'Arrivée Membre',
    'member_remove': 'Départ Membre',
    'default': 'Défaut'
}

class AvatarCooldownModal(Modal, title="Définir Cooldown Avatar"):
    cooldown_input = TextInput(label="Cooldown (secondes)", default=str(db['settings'].get('avatar_cooldown_seconds', 300)))
    async def on_submit(self, interaction: discord.Interaction):
        try:
            cooldown = int(self.cooldown_input.value)
            if cooldown < 0: raise ValueError("Doit être positif")
            db['settings']['avatar_cooldown_seconds'] = cooldown
            save_data(db)
            await interaction.response.send_message(f"✅ Cooldown global défini à {cooldown}s.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Entrez un nombre de secondes valide (>= 0).", ephemeral=True)

class AvatarDefaultModal(Modal, title="Définir Avatar par Défaut"):
    url_input = TextInput(label="URL de l'image (laisser vide pour supprimer)", required=False, default=db['settings'].get('avatar_default_url', ''))
    async def on_submit(self, interaction: discord.Interaction):
        url = self.url_input.value.strip() or None
        db['settings']['avatar_default_url'] = url
        save_data(db)
        message = "✅ Avatar par défaut mis à jour." if url else "🗑️ Avatar par défaut supprimé."
        await interaction.response.send_message(message, ephemeral=True)

class AvatarTriggerModal(Modal):
    def __init__(self, trigger_key: str):
        super().__init__(title=f"Configurer Trigger: {AVATAR_TRIGGERS_MAP.get(trigger_key, trigger_key)}")
        self.trigger_key = trigger_key
        trigger_data = db.get('avatar_triggers', {}).get(trigger_key, {})
        self.add_item(TextInput(label="URL de l'image (laisser vide pour supprimer)", required=False, default=trigger_data.get('image_url', '')))
        self.add_item(TextInput(label="Durée avant retour (ex: 5m, 1h, 0s)", default=trigger_data.get('duration', '0s')))
    async def on_submit(self, interaction: discord.Interaction):
        image_url = self.children[0].value.strip() or None
        duration_str = self.children[1].value.strip() or '0s'
        if not image_url:
            if self.trigger_key in db.get('avatar_triggers', {}):
                del db['avatar_triggers'][self.trigger_key]
                message = f"🗑️ Déclencheur '{self.trigger_key}' supprimé."
            else:
                message = f"ℹ️ Déclencheur '{self.trigger_key}' n'existait pas."
        else:
            if not re.match(r"^\d+[smhd]$", duration_str.lower()) and duration_str != '0s':
                await interaction.response.send_message("❌ Format de durée invalide. Utilisez Xm, Xh, Xd ou 0s.", ephemeral=True)
                return
            db.setdefault('avatar_triggers', {})[self.trigger_key] = {'image_url': image_url, 'duration': duration_str}
            message = f"✅ Déclencheur '{self.trigger_key}' configuré."
        save_data(db)
        await interaction.response.send_message(message, ephemeral=True)

class AvatarTriggerSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=display, value=key, description=f"Clé: {key}")
            for key, display in AVATAR_TRIGGERS_MAP.items()
        ]
        custom_keys = [k for k in db.get('avatar_triggers', {}) if k not in AVATAR_TRIGGERS_MAP]
        for key in custom_keys:
            options.append(discord.SelectOption(label=f"Custom: {key}", value=key, description=f"Clé: {key}"))
        super().__init__(placeholder="Choisir un déclencheur à configurer...", options=options)
    async def callback(self, interaction: discord.Interaction):
        trigger_key = self.values[0]
        await interaction.response.send_modal(AvatarTriggerModal(trigger_key))

class AvatarConfigView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_toggle_button()
        self.add_item(AvatarTriggerSelect())
    def update_toggle_button(self):
        for item in self.children[:]:
            if getattr(item, 'custom_id', None) == 'toggle_avatar_system':
                self.remove_item(item)
        is_enabled = db['settings'].get('avatar_enabled', True)
        label = "Désactiver Système" if is_enabled else "Activer Système"
        style = discord.ButtonStyle.danger if is_enabled else discord.ButtonStyle.success
        emoji = "✅" if is_enabled else "❌"
        toggle_button = Button(label=label, style=style, emoji=emoji, custom_id="toggle_avatar_system", row=2)
        toggle_button.callback = self.toggle_system
        self.add_item(toggle_button)
    async def toggle_system(self, interaction: discord.Interaction):
        is_enabled = db['settings'].get('avatar_enabled', True)
        db['settings']['avatar_enabled'] = not is_enabled
        save_data(db)
        self.update_toggle_button()
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"Système d'avatar maintenant {'activé' if not is_enabled else 'désactivé'}.", ephemeral=True)
    @discord.ui.button(label="Définir Cooldown", style=discord.ButtonStyle.secondary, emoji="⏳", row=1)
    async def set_cooldown(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AvatarCooldownModal())
    @discord.ui.button(label="Définir Défaut", style=discord.ButtonStyle.secondary, emoji="🖼️", row=1)
    async def set_default(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AvatarDefaultModal())

@avatar_config_group.command(name="panel", description="Ouvre le panneau de configuration de l'avatar.")
async def avatar_config_panel(interaction: discord.Interaction):
    status = "Activé" if db['settings'].get('avatar_enabled', True) else "Désactivé"
    cooldown = db['settings'].get('avatar_cooldown_seconds', 300)
    default_url = db['settings'].get('avatar_default_url', 'Non défini')
    embed = discord.Embed(title="⚙️ Config Avatar Dynamique", description=f"**État :** {status} | **Cooldown :** {cooldown}s\n**Défaut :** {default_url}", color=NEON_BLUE)
    embed.add_field(name="Instructions", value="• Utilisez les boutons pour activer/désactiver, définir le cooldown ou l'avatar par défaut.\n• Utilisez le menu déroulant pour configurer l'image et la durée de chaque déclencheur.", inline=False)
    await interaction.response.send_message(embed=embed, view=AvatarConfigView(), ephemeral=True)

client.tree.add_command(avatar_group)

# ==================================================================================================
# 15. SYSTÈME TOPWEEK
# ==================================================================================================
topweek_admin_group = app_commands.Group(name="topweekadmin", description="[Admin] Gère le classement hebdomadaire.", default_permissions=discord.Permissions(administrator=True))

@topweek_admin_group.command(name="config", description="Configure l'annonce du classement hebdo.")
@app_commands.describe(
    salon="Le salon où poster l'annonce.",
    jour="Le jour de l'annonce (0=Lundi, 6=Dimanche).",
    heure="L'heure de l'annonce en UTC (HH:MM)."
)
async def topweek_config(interaction: discord.Interaction, salon: discord.TextChannel, jour: app_commands.Range[int, 0, 6], heure: str):
    try:
        time_obj = datetime.datetime.strptime(heure.strip(), "%H:%M").time()
    except ValueError:
        return await interaction.response.send_message("❌ Format d'heure invalide. Utilisez `HH:MM` (ex: 19:00).", ephemeral=True)
    settings = db.setdefault("settings", {}).setdefault("topweek_settings", {})
    settings["channel_id"] = salon.id
    settings["announcement_day"] = jour
    settings["announcement_time"] = time_obj.strftime("%H:%M")
    save_data(db)
    jours_semaine = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    await interaction.response.send_message(f"✅ Annonce TopWeek configurée pour {salon.mention}, chaque **{jours_semaine[jour]}** à **{heure} UTC**.", ephemeral=True)

client.tree.add_command(topweek_admin_group)

# --- Commandes Admin XP ---
adminxp_group = app_commands.Group(name="adminxp", description="Commandes admin pour gérer l'XP des joueurs.", default_permissions=discord.Permissions(administrator=True))

@adminxp_group.command(name="give", description="Donne/Retire de l'XP à un joueur.")
@app_commands.describe(membre="Le membre concerné.", montant="Quantité d'XP (+/-).", raison="Motif.")
async def adminxp_give(interaction: discord.Interaction, membre: discord.Member, montant: int, raison: str):
    if membre.bot: return await interaction.response.send_message("❌ Pas d'XP pour les bots.", ephemeral=True)

    await update_user_xp(membre.id, montant, is_weekly_xp=(montant > 0)) 
    save_data(db)
    await check_and_handle_progression(membre, interaction.channel) 

    await interaction.response.send_message(f"✅ {montant:+d} XP ajusté pour {membre.mention}. Raison: {raison}", ephemeral=True)

@adminxp_group.command(name="setlevel", description="Définit directement le niveau d'un joueur.")
@app_commands.describe(membre="Le membre concerné.", niveau="Le nouveau niveau (XP sera mis à 0).")
async def adminxp_setlevel(interaction: discord.Interaction, membre: discord.Member, niveau: app_commands.Range[int, 1]):
    if membre.bot: return await interaction.response.send_message("❌ Pas de niveau pour les bots.", ephemeral=True)

    user_data = get_user_xp_data(membre.id)
    user_data["level"] = niveau
    user_data["xp"] = 0 
    user_data["weekly_xp"] = 0 
    save_data(db)

    await interaction.response.send_message(f"✅ Niveau de {membre.mention} défini sur **{niveau}** (XP réinitialisé).", ephemeral=True)

@adminxp_group.command(name="resetweekly", description="Réinitialise l'XP hebdomadaire de tous les joueurs.")
async def adminxp_resetweekly(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    count = 0
    for user_id, user_data in db.get("users", {}).items():
        if user_data.get("weekly_xp", 0) != 0:
            user_data["weekly_xp"] = 0
            count += 1
    if count > 0:
        save_data(db)
    await interaction.followup.send(f"✅ XP hebdomadaire réinitialisé pour {count} joueur(s).", ephemeral=True)

client.tree.add_command(adminxp_group)


# Commande Config Listener
@client.tree.command(name="config_listener", description="[Admin] Configure les salons d'écoute des bots Mod/Event.")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    mod_channel="Salon des logs du bot de modération.",
    event_channel="Salon des annonces du bot d'événements.",
    activer="Activer ou désactiver l'écoute."
)
async def config_listener(
    interaction: discord.Interaction,
    mod_channel: Optional[discord.TextChannel] = None,
    event_channel: Optional[discord.TextChannel] = None,
    activer: Optional[bool] = None
):
    settings = db.setdefault("settings", {}).setdefault("mod_listener_settings", {})
    changes = []
    if mod_channel is not None:
        settings["mod_bot_channel_id"] = mod_channel.id
        changes.append(f"Salon Mod défini sur {mod_channel.mention}")
    if event_channel is not None:
        settings["event_bot_channel_id"] = event_channel.id
        changes.append(f"Salon Event défini sur {event_channel.mention}")
    if activer is not None:
        settings["enabled"] = activer
        changes.append(f"Écoute {'activée' if activer else 'désactivée'}")

    if not changes:
        mod_ch_id = settings.get("mod_bot_channel_id")
        ev_ch_id = settings.get("event_bot_channel_id")
        mod_ch = client.get_channel(mod_ch_id) if mod_ch_id else None
        ev_ch = client.get_channel(ev_ch_id) if ev_ch_id else None
        status = "Activée" if settings.get("enabled", True) else "Désactivée"
        await interaction.response.send_message(
            f"**Configuration Écoute Bots:**\n"
            f"• Statut: `{status}`\n"
            f"• Salon Mod: {mod_ch.mention if mod_ch else '`Non défini`'}\n"
            f"• Salon Event: {ev_ch.mention if ev_ch else '`Non défini`'}",
            ephemeral=True
        )
    else:
        save_data(db)
        await interaction.response.send_message("✅ Configuration de l'écoute mise à jour:\n• " + "\n• ".join(changes), ephemeral=True)

# --- NOUVEAU: Commande pour réinitialiser le Listener (Désactiver et vider les salons) ---
@client.tree.command(name="reset_listener", description="[Admin] Désactive l'écoute des bots et supprime les salons configurés.")
@app_commands.default_permissions(administrator=True)
async def reset_listener(interaction: discord.Interaction):
    settings = db.setdefault("settings", {}).setdefault("mod_listener_settings", {})
    settings["mod_bot_channel_id"] = None
    settings["event_bot_channel_id"] = None
    settings["enabled"] = False
    save_data(db)
    await interaction.response.send_message("✅ Écoute des bots désactivée et configuration des salons supprimée.", ephemeral=True)

# Commande /rewards (pour config level up)
@client.tree.command(name="rewards", description="[Admin] Configure les récompenses de montée de niveau.")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    salon_notif="Salon pour annoncer les level up (optionnel).",
    niveau="Niveau requis pour le rôle (optionnel).",
    role="Rôle à attribuer à ce niveau (optionnel)."
)
async def rewards(interaction: discord.Interaction, salon_notif: Optional[discord.TextChannel] = None, niveau: Optional[app_commands.Range[int, 1]] = None, role: Optional[discord.Role] = None):
    
    settings = db.setdefault("settings", {}).setdefault("level_up_rewards", {})
    changes = []

    if salon_notif:
        settings["notification_channel_id"] = salon_notif.id
        changes.append(f"Salon d'annonce défini sur {salon_notif.mention}")

    if niveau and role:
        settings.setdefault("role_rewards", {})[str(niveau)] = str(role.id)
        changes.append(f"Récompense de niveau {niveau} définie sur {role.mention}")
    elif niveau or role:
        await interaction.response.send_message("❌ Pour ajouter une récompense de rôle, tu dois fournir **à la fois** le niveau et le rôle.", ephemeral=True)
        return

    if not changes:
        await interaction.response.send_message("ℹ️ Aucune modification effectuée. Fournis un salon, ou un duo niveau/rôle.", ephemeral=True)
    else:
        save_data(db)
        await interaction.response.send_message(f"✅ Configuration des récompenses mise à jour:\n• " + "\n• ".join(changes), ephemeral=True)


# --- NOUVEAU: Commande de Synchronisation Manuelle ---
@client.tree.command(name="admin_sync", description="[Admin] Force la synchronisation des commandes avec Discord.")
@app_commands.default_permissions(administrator=True)
async def admin_sync(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        synced = await client.tree.sync()
        command_names = [c.name for c in synced]
        await interaction.followup.send(f"✅ **Synchronisation réussie !**\n**{len(synced)} commandes actives :**\n`{', '.join(command_names)}`", ephemeral=True)
    except Exception as e:
        logger.exception(f"Erreur Sync Manuelle: {e}")
        await interaction.followup.send(f"❌ Erreur lors de la synchronisation : `{e}`", ephemeral=True)

# ==================================================================================================
# 14. SYSTÈME D'AVATAR DYNAMIQUE (Suite)
# ==================================================================================================

# Tâche de fond de vérification de réversion d'avatar
@tasks.loop(seconds=5)
async def check_avatar_revert():
    """Vérifie périodiquement si un avatar temporaire doit être restauré."""
    await client.wait_until_ready()
    avatar_stack = db.get('avatar_stack', [])
    if not avatar_stack: return
    now_utc = get_adjusted_time()
    current_state = avatar_stack[0]
    revert_time_iso = current_state.get('revert_time')
    if revert_time_iso:
        try:
            revert_time = datetime.datetime.fromisoformat(revert_time_iso).replace(tzinfo=SERVER_TIMEZONE)
            if now_utc >= revert_time:
                logger.info(f"Avatar Check: Temps de réversion atteint pour trigger '{current_state.get('trigger')}'. Restauration...")
                await revert_avatar()
        except ValueError:
            logger.error(f"Avatar Check: Timestamp 'revert_time' invalide dans la pile: {revert_time_iso}")

# ==================================================================================================
# 15. SYSTÈME TOPWEEK (Suite)
# ==================================================================================================

# --- Tâches Topweek ---
@tasks.loop(time=datetime.time(hour=0, minute=0, second=5, tzinfo=SERVER_TIMEZONE))
async def weekly_xp_reset():
    """Réinitialise l'XP hebdomadaire si c'est lundi (début de semaine)."""
    await client.wait_until_ready()
    # weekday() -> Lundi=0, Dimanche=6
    if get_adjusted_time().weekday() == 0: 
        logger.info("Réinitialisation de l'XP hebdomadaire.")
        modified = False
        for user_id, user_data in db.get("users", {}).items():
            if user_data.get("weekly_xp", 0) != 0:
                user_data["weekly_xp"] = 0
                modified = True
        if modified:
            save_data(db)
            logger.info("XP hebdomadaire réinitialisée pour tous les joueurs actifs.")
        else:
            logger.info("Aucun XP hebdomadaire à réinitialiser.")

@tasks.loop(hours=1)
async def post_weekly_leaderboard():
    """Poste le classement hebdomadaire à l'heure configurée."""
    await client.wait_until_ready()
    settings = db.get("settings", {}).get("topweek_settings", {})
    now = get_adjusted_time()
    channel_id = settings.get("channel_id")
    announcement_day = settings.get("announcement_day", 6)
    announcement_time_str = settings.get("announcement_time", "19:00")
    if not channel_id or now.weekday() != announcement_day:
        return
    try:
        announcement_time = datetime.datetime.strptime(announcement_time_str, "%H:%M").time()
    except ValueError:
        logger.error(f"TopWeek: Heure d'annonce invalide: {announcement_time_str}")
        return
    if now.time().hour != announcement_time.hour or now.time().minute < announcement_time.minute:
        return
    current_week_str = now.strftime('%Y-%U')
    if settings.get("last_posted_week") == current_week_str:
        logger.debug(f"TopWeek: Classement déjà posté pour la semaine {current_week_str}.")
        return

    channel = client.get_channel(channel_id)
    if not channel:
        logger.error(f"TopWeek: Salon d'annonce introuvable (ID: {channel_id}).")
        return
    
    logger.info(f"TopWeek: Publication du classement hebdomadaire dans #{channel.name}...")
    all_users_data = db.get("users", {})
    weekly_players = {uid: data for uid, data in all_users_data.items() if data.get("weekly_xp", 0) > 0}
    if not weekly_players:
        logger.info("TopWeek: Classement vide, rien à poster.")
        db["settings"]["topweek_settings"]["last_posted_week"] = current_week_str
        save_data(db)
        return

    leaderboard = sorted(weekly_players.items(), key=lambda item: item[1].get("weekly_xp", 0), reverse=True)
    embed = discord.Embed(title="🏆 Palmarès Hebdomadaire Terminé ! 🏆", description="Félicitations aux joueurs les plus actifs de la semaine passée !", color=GOLD_COLOR)
    lines = []
    rewards_config = settings.get("rewards", {})
    reward_winners = {}
    for i, (user_id_str, data) in enumerate(leaderboard[:3]):
        try:
            user_id = int(user_id_str)
            member = channel.guild.get_member(user_id)
            name = member.display_name if member else f"ID:{user_id_str}"
            xp_hebdo = data.get('weekly_xp', 0)
            lines.append(f"{LEADERBOARD_EMOJIS[i]} **{name}** - `{xp_hebdo:,}` XP")
            if i == 0: reward = rewards_config.get("first", {}).get("xp", 0)
            elif i == 1: reward = rewards_config.get("second", {}).get("xp", 0)
            else: reward = rewards_config.get("third", {}).get("xp", 0)
            if reward > 0:
                reward_winners[user_id] = {"xp": reward}
        except (ValueError, AttributeError):
            continue
    embed.description += "\n\n" + "\n".join(lines)
    embed.set_footer(text="L'XP hebdomadaire sera réinitialisée. Préparez-vous pour la nouvelle semaine !")
    embed = apply_embed_styles(embed, "topweek_announce") 
    
    try:
        await channel.send(embed=embed)
        logger.info(f"TopWeek: Classement publié avec succès.")
        if reward_winners:
            logger.info(f"TopWeek: Application des récompenses XP pour {len(reward_winners)} joueur(s).")
            for user_id, gains in reward_winners.items():
                await update_user_xp(user_id, gains["xp"], is_weekly_xp=False)
                member = channel.guild.get_member(user_id)
                if member:
                    await check_and_handle_progression(member, channel)
            save_data(db)
        db["settings"]["topweek_settings"]["last_posted_week"] = current_week_str
        save_data(db)
    except discord.Forbidden:
        logger.error(f"TopWeek: Permissions manquantes pour poster le classement dans #{channel.name}")
    except Exception as e:
        logger.exception(f"TopWeek: Erreur lors de la publication du classement: {e}")


# ==================================================================================================
# 16. TÂCHE DE SAUVEGARDE XP
# ==================================================================================================
@tasks.loop(hours=6)
async def backup_xp_data():
    """Sauvegarde périodiquement les données XP essentielles."""
    await client.wait_until_ready()
    logger.info("Création d'une sauvegarde XP...")
    try:
        backup_data = {
            uid: {"xp": data.get("xp", 0), "level": data.get("level", 1)}
            for uid, data in db.get("users", {}).items()
        }
        backup_wrapper = {"timestamp": get_adjusted_time().isoformat(), "users": backup_data}
        with open(XP_BACKUP_FILE, 'w', encoding='utf-8') as f:
            json.dump(backup_wrapper, f, indent=2)
        logger.info(f"Sauvegarde XP terminée avec succès ({len(backup_data)} utilisateurs).")
    except Exception as e:
        logger.exception(f"Erreur lors de la sauvegarde XP: {e}")

# ==================================================================================================
# 17. COMMANDES D'AIDE (Refonte Images & Renommage)
# ==================================================================================================

# --- CONFIGURATION DES IMAGES D'AIDE ---
# Ajoutez vos liens d'images ici pour activer le "Mode Image".
# Laissez vide ("") pour rester en "Mode Simple" (texte uniquement).
# Si vous mettez plusieurs liens, cela créera plusieurs pages.
HELP_ADMIN_IMAGES = [
    "", # Page 1 Admin (ex: "https://mon-lien.com/image1.png")
]

HELP_PLAYER_IMAGES = [
    "", # Page 1 Joueur (ex: "https://mon-lien.com/image_joueur.png")
]

class HelpView(View):
    """Vue pour naviguer entre les pages d'aide."""
    def __init__(self, embeds, user):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.current_page = 0
        self.user = user
        self.add_buttons()

    def add_buttons(self):
        # On vide les boutons précédents pour éviter les doublons lors des mises à jour
        self.clear_items()
        
        prev_button = Button(label="◀️", style=discord.ButtonStyle.secondary, disabled=True)
        prev_button.callback = self.prev_page
        self.add_item(prev_button)

        next_button = Button(label="▶️", style=discord.ButtonStyle.secondary, disabled=len(self.embeds) <= 1)
        next_button.callback = self.next_page
        self.add_item(next_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce n'est pas votre panneau d'aide.", ephemeral=True)
            return False
        return True

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        await self.update_message(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = min(len(self.embeds) - 1, self.current_page + 1)
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = self.embeds[self.current_page]
        # Mettre à jour l'état des boutons
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == len(self.embeds) - 1
        await interaction.response.edit_message(embed=embed, view=self)

@client.tree.command(name="poxel_help", description="Affiche la liste des commandes d'administration (Poxel).")
@app_commands.default_permissions(administrator=True)
async def help_command(interaction: discord.Interaction):
    embeds = []

    # Vérification du Mode Image
    images = [url for url in HELP_ADMIN_IMAGES if url.strip()]
    
    if images:
        # MODE IMAGE
        for i, img_url in enumerate(images):
            # On garde un titre et une couleur pour l'embed, mais le contenu principal est l'image
            embed = discord.Embed(title=f"📚 Aide Admin - Poxel (Page {i+1}/{len(images)})", color=NEON_BLUE)
            embed.set_image(url=img_url)
            embeds.append(embed)
    else:
        # MODE SIMPLE (Texte par défaut)
        embed1 = discord.Embed(title="📚 Aide Admin (1/1) - Config & Systèmes", color=NEON_BLUE)
        embed1.add_field(name="`/poxel_help` / `/poxel_help_joueur`", value="Affiche les panneaux d'aide.", inline=False)
        embed1.add_field(name="`/avatar config panel`", value="Configure l'avatar dynamique.", inline=False)
        embed1.add_field(name="`/notif`", value="Gère les notifications (add/remove/list/config/test).", inline=False)
        embed1.add_field(name="`/admin_sync`", value="Force la synchronisation des commandes.", inline=False) 
        embed1.add_field(name="`/freegames config` / `/freegames disable`", value="Gère le salon des jeux gratuits.", inline=False)
        embed1.add_field(name="`/cineconfig set_channel` / `/cineconfig remove_channel`", value="Gère les salons Ciné Pixel.", inline=False) 
        embed1.add_field(name="`/birthdayadmin config`", value="Définit le salon des anniversaires.", inline=False)
        embed1.add_field(name="`/topweekadmin config`", value="Configure l'annonce du classement hebdo.", inline=False)
        embed1.add_field(name="`/rewards`", value="Configure les récompenses de niveau (salon, rôle).", inline=False)
        embed1.add_field(name="`/config_listener` / `/reset_listener`", value="Gère l'écoute des bots Mod/Event.", inline=False)
        embed1.add_field(name="`/adminxp`", value="Gère l'XP des joueurs (give/setlevel/resetweekly).", inline=False)
        embeds.append(embed1)

    view = HelpView(embeds, interaction.user)
    await interaction.response.send_message(embed=embeds[0], view=view, ephemeral=True)


@client.tree.command(name="poxel_help_joueur", description="Affiche les commandes et fonctionnalités disponibles (Poxel).")
async def help_joueur(interaction: discord.Interaction):
    embeds = []

    # Vérification du Mode Image
    images = [url for url in HELP_PLAYER_IMAGES if url.strip()]

    if images:
        # MODE IMAGE
        for i, img_url in enumerate(images):
            embed = discord.Embed(title=f"🎮 Aide Joueur - Poxel (Page {i+1}/{len(images)})", color=NEON_GREEN)
            embed.set_image(url=img_url)
            embeds.append(embed)
    else:
        # MODE SIMPLE (Texte par défaut)
        embed1 = discord.Embed(title="🎮 Commandes Joueur (1/1) - Profil & Social", color=NEON_GREEN)
        embed1.add_field(name="**__PROFIL & CLASSEMENTS__**", value="\u200b", inline=False)
        embed1.add_field(name="`/rank`", value="Affiche ton profil XP et tes rangs.", inline=True)
        embed1.add_field(name="**__SOCIAL & PERSONNALISATION__**", value="\u200b", inline=False)
        embed1.add_field(name="`/team`", value="Commandes pour créer/gérer ton équipe.", inline=True)
        embed1.add_field(name="`/teamlist`", value="Voir la liste des équipes.", inline=True)
        embed1.add_field(name="`/birthday`", value="Gère ton anniversaire (set/remove).", inline=True)
        embed1.add_field(name="`/birthdaylist`", value="Voir les anniversaires.", inline=True)
        embed1.add_field(name="`/nextbirthday`", value="Voir le prochain anniversaire.", inline=True)
        embed1.add_field(name="**__UTILITAIRES__**", value="\u200b", inline=False)
        embed1.add_field(name="`/free`", value="Voir les jeux gratuits du moment.", inline=True)
        embed1.add_field(name="`/news_series` / `/news_movies`", value="Voir les sorties récentes (privé).", inline=True) 
        embed1.add_field(name="`/episodes_series` / `/episodes_anime`", value="Voir les épisodes du jour (privé).", inline=True)
        embed1.add_field(name="`/ping`", value="Vérifie la latence du bot.", inline=True)
        embeds.append(embed1)

    view = HelpView(embeds, interaction.user)
    await interaction.response.send_message(embed=embeds[0], view=view, ephemeral=True)


# ==================================================================================================
# 18. COMMANDES ADMIN RESTANTES (Récap)
# ==================================================================================================

# (Les commandes adminxp, rewards, config_listener, admin_sync, topweekadmin_config sont déjà dans la Partie 5)

# ==================================================================================================
# 19. DÉMARRAGE DU BOT ET DES TÂCHES
# ==================================================================================================
if __name__ == "__main__":
    # Démarre le serveur Flask sur un thread séparé pour garder le bot en vie sur les hébergeurs
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    if not DISCORD_TOKEN:
        logger.critical("ERREUR: Token Discord non trouvé dans .env.")
        sys.exit(1)

    # Lancer le bot Discord
    try:
        logger.info("Lancement du client Discord...")
        
        # Debug: Lister les commandes enregistrées AVANT le run
        cmds = client.tree.get_commands()
        cmd_names = [c.name for c in cmds]
        logger.info(f"Commandes locales enregistrées ({len(cmds)}) : {cmd_names}")

        client.run(DISCORD_TOKEN, log_handler=None)
    except discord.errors.LoginFailure:
        logger.critical("ERREUR: Token Discord invalide. Veuillez vérifier votre token.")
    except discord.errors.PrivilegedIntentsRequired:
        logger.critical("ERREUR: Intents privilégiés (Présence, Membres) requis mais non activés sur le portail développeur Discord.")
    except Exception as e:
        logger.exception(f"Erreur fatale lors du lancement ou de l'exécution du client Discord: {e}")
    finally:
        logger.info("Arrêt du bot.")

