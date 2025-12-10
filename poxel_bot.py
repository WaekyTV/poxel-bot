# -*- coding: utf-8 -*-
"""
Poxel (Fusion Economy & Moderation)
Description: Bot Discord complet (XP, Eco, Modération, Logs, Tickets, Cinéma, Jeux Gratuits).
Auteur: Poxel (Refactorisé)
Version: Unified 1.0
"""

# ==================================================================================================
# 0. GESTION AUTOMATIQUE DES DÉPENDANCES
# ==================================================================================================
import subprocess
import sys
import importlib
import os

def check_and_install_packages(packages):
    """
    Vérifie et installe les paquets requis.
    """
    optional_packages = ["Pillow", "qrcode[pil]", "requests", "deep_translator", "google-api-python-client"]
    
    for import_name, package_name in packages.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            print(f"Module '{import_name}' non trouvé. Installation de '{package_name}'...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
                importlib.import_module(import_name)
                print(f"'{package_name}' installé avec succès.")
            except subprocess.CalledProcessError as e:
                print(f"ERREUR: Impossible d'installer {package_name}. Erreur: {e}")
                if package_name not in optional_packages:
                    sys.exit(1)
            except ImportError:
                print(f"AVERTISSEMENT: '{package_name}' installé mais non importable.")

# Liste combinée des paquets requis
required_packages = {
    "discord": "discord.py",
    "flask": "Flask",
    "dotenv": "python-dotenv",
    "aiohttp": "aiohttp",
    "pytz": "pytz",
    "PIL": "Pillow",
    "qrcode": "qrcode[pil]",
    "requests": "requests",
    "googleapiclient": "google-api-python-client",
    "deep_translator": "deep-translator"
}
check_and_install_packages(required_packages)

# ==================================================================================================
# 1. IMPORTS GLOBAUX (Aucun autre import ne sera fait par la suite)
# ==================================================================================================
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput, Select
import datetime
import asyncio
import json
import pytz
import random
import math
import re
import io
import logging
from threading import Thread
import aiohttp
from typing import Optional, List, Dict, Any, Tuple, Literal
from dotenv import load_dotenv
import time
import textwrap

# Imports conditionnels
try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from googleapiclient.discovery import build
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False

# ==================================================================================================
# 2. CONFIGURATION & CONSTANTES
# ==================================================================================================
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger("Poxel")

# Configuration Discord
intents = discord.Intents.all()
client = None  # Sera instancié à la fin

# Couleurs Thématiques (Fusionnées)
NEON_PURPLE = 0x6441a5
NEON_BLUE = 0x027afa
NEON_GREEN = 0x00ff99
RETRO_ORANGE = 0xFF8C00
DARK_RED = 0x8B0000
GOLD_COLOR = 0xFFD700
LIGHT_GREEN = 0x90EE90
TEAM_COLOR = 0x7289DA
FREE_GAMES_COLOR = 0x1abc9c
NETFLIX_COLOR = 0xE50914
DISNEY_COLOR = 0x113CCF
PRIME_COLOR = 0x00A8E1
CINEMA_COLOR = 0xFFD700
DEFAULT_CINE_COLOR = 0x2C3E50
YOUTUBE_COLOR = 0xFF0000
TWITCH_COLOR = 0x9146FF
KICK_COLOR = 0x52C41A
TIKTOK_COLOR = 0x69C9D0

# Assets & URLs
RANK_CARD_BACKGROUND_URL = "https://cdn.discordapp.com/attachments/1420332458964156467/1431775659448991814/Espace_pixels_00307.jpg"
RANK_CARD_FONT_URL = "https://github.com/google/fonts/raw/main/ofl/pressstart2p/PressStart2P-Regular.ttf"
YOUTUBE_ICON = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/YouTube_full-color_icon_%282017%29.svg/1024px-YouTube_full-color_icon_%282017%29.svg.png"
TWITCH_ICON = "https://assets.stickpng.com/images/580b57fcd9996e24bc43c540.png"
KICK_ICON = "https://logos-world.net/wp-content/uploads/2024/01/Kick-Logo.png"
TIKTOK_ICON = "https://assets.stickpng.com/images/580b57fcd9996e24bc43c53e.png"
DEFAULT_ICON = "https://cdn.icon-icons.com/icons2/2716/PNG/512/discord_logo_icon_173101.png"

# Constantes Rank Card
RANK_CARD_GRADIENT_START = "#6500ff"
RANK_CARD_GRADIENT_MID = "#6441a5"
RANK_CARD_GRADIENT_END = "#027afa"
LEADERBOARD_EMOJIS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

# Timezones
USER_TIMEZONE = pytz.timezone('Europe/Paris')
SERVER_TIMEZONE = pytz.utc

# Noms de fichiers
DATABASE_FILE = 'poxel_database_unified.json' # Fichier unifié
NOTIFICATIONS_FILE = "poxel_notifications.json"
XP_BACKUP_FILE = 'poxel_xp_backup.json'

# Clés API
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", None)
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", None)
KICK_CLIENT_ID = os.getenv("KICK_CLIENT_ID")
KICK_CLIENT_SECRET = os.getenv("KICK_CLIENT_SECRET")
KICK_USERNAME = os.getenv("KICK_USERNAME", "").lower()

# Variables Globales Cache
kick_token = None
kick_token_expiry = 0
pixel_font_l = None
pixel_font_m = None
pixel_font_s = None
rank_card_bg = None
pixel_font_path = "PressStart2P-Regular.ttf"

# ==================================================================================================
# 3. SERVEUR FLASK
# ==================================================================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Poxel (Unified) is running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=port)

# ==================================================================================================
# 4. GESTION BASE DE DONNÉES (UNIFIÉE)
# ==================================================================================================
def load_data():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    else:
        data = {}

    # Initialisation des sections (Fusion des deux bots)
    data.setdefault("users", {}) # Economy
    data.setdefault("teams", {}) # Economy
    data.setdefault("birthdays", {}) # Economy
    data.setdefault("settings", {})
    data.setdefault("infractions", {}) # Modération
    data.setdefault("avatar_stack", [])
    data.setdefault("avatar_triggers", {})
    data.setdefault("auto_mod_profiles", {}) # Modération
    data.setdefault("active_tickets", {}) # Modération
    data.setdefault("voice_hubs", {}) # Modération
    data.setdefault("temp_channels", {}) # Modération
    data.setdefault("embed_builders", {})
    data.setdefault("reaction_role_messages", {})
    
    # Settings fusionnés
    settings = data["settings"]
    # ... Eco settings
    settings.setdefault("level_up_rewards", {})
    settings.setdefault("birthday_settings", {})
    settings.setdefault("free_games_settings", {})
    settings.setdefault("cine_pixel_settings", {})
    settings.setdefault("topweek_settings", {})
    # ... Mod settings
    settings.setdefault("max_lives_default", 9)
    settings.setdefault("max_lives_boost", 10)
    settings.setdefault("life_emoji_full", "❤️")
    settings.setdefault("life_emoji_empty", "🖤")
    settings.setdefault("auto_mod_enabled", True)
    settings.setdefault("censor_enabled", True)
    settings.setdefault("welcome_channel_id", None)
    settings.setdefault("farewell_channel_id", None)
    
    return data

def save_data(data):
    try:
        with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erreur sauvegarde DB: {e}")

def load_notif_data():
    if not os.path.exists(NOTIFICATIONS_FILE): return {"servers": {}, "last_seen": {}, "channel_cache": {}}
    try:
        with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {"servers": {}, "last_seen": {}, "channel_cache": {}}

def save_notif_data(data):
    try:
        with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception: pass

db = load_data()
notif_db = load_notif_data()


# ==================================================================================================
# 5. CONSTANTES COMPLÉMENTAIRES (MODÉRATION & JEUX)
# ==================================================================================================

# Système de Vies (Points d'Infraction)
INFRACTION_POINTS = {
    "warn": 1,
    "mute": 1,
    "kick": 2,
    "tempban": 3,
    "ban": 5,
    "signalement": 1,
    "auto_warn": 1,
    "auto_mute": 1,
    "auto_kick": 2,
    "auto_tempban": 3,
    "auto_ban": 5,
}

# Avatars Dynamiques (Mapping)
AVATAR_TRIGGERS_MAP = {
    'default': 'Avatar par Défaut',
    'warn': 'Avertissement (Warn)',
    'mute': 'Rendre Muet (Mute)',
    'kick': 'Expulsion (Kick)',
    'ban': 'Bannissement (Ban)',
    'unban': 'Débannissement (Unban)',
    'perma_ban': 'Ban Permanent (0 Vie)',
    'infraction_clear': 'Purge des Infractions',
    'channel_create': 'Création de Salon Vocal',
    'channel_delete': 'Suppression de Salon Vocal',
    'member_join': 'Nouveau Membre',
    'member_remove': 'Départ d\'un Membre',
    'rules_accepted': 'Règles Acceptées',
    'rules_failed': 'Accès Refusé (Règles)',
    'event_create': 'Création d\'Événement',
    'event_start': 'Début d\'Événement',
    'event_end': 'Fin d\'Événement',
    'tournament_create': 'Création de Tournoi',
    'tournament_start': 'Début de Tournoi',
    'tournament_end': 'Fin de Tournoi',
    'ticket_open': 'Ouverture de Ticket',
    'xp_gain': 'Gain XP/Level Up', # Ajout Economy
    'custom': 'Forcé par un Admin'
}

# Titres & Tournois
TROPHY_ROLE_NAME = "🏆 Trophée"
PARTICIPANT_ROLE_NAME = "Tournoi Participant"
ROUND_NAMES = ["Round 1", "Round 2", "Quart de Finale", "Demi-Finale", "FINALE"]
TROPHY_TITLES = {
    1: "👾 Pixie Rookie",
    3: "🎮 8-Bit Challenger",
    5: "💾 Retro Master",
    10: "🕹️ Arcade Legend",
    20: "🌌 Vintage Champion",
    50: "🏯 Pixel Overlord",
    100: "✨ Retro Immortal"
}

# ==================================================================================================
# 6. FONCTIONS UTILITAIRES GÉNÉRALES
# ==================================================================================================

def get_adjusted_time() -> datetime.datetime:
    """Renvoie l'heure UTC actuelle ajustée avec le décalage du serveur."""
    offset = db['settings'].get('time_offset_seconds', 0)
    try: offset_seconds = int(offset)
    except: offset_seconds = 0
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=offset_seconds)

def parse_duration(duration_str: str):
    """Convertit une durée (ex: '10m', '2h') en timedelta."""
    if not duration_str: return datetime.timedelta(seconds=0)
    s = duration_str.lower().strip()
    val = "".join(filter(str.isdigit, s))
    if not val: return datetime.timedelta(seconds=0)
    val = int(val)
    if 'd' in s: return datetime.timedelta(days=val)
    elif 'h' in s: return datetime.timedelta(hours=val)
    elif 'm' in s: return datetime.timedelta(minutes=val)
    elif 's' in s: return datetime.timedelta(seconds=val)
    return datetime.timedelta(seconds=0)

def format_time_left(end_time_str):
    try:
        end_time_utc = datetime.datetime.fromisoformat(end_time_str).replace(tzinfo=SERVER_TIMEZONE)
    except ValueError: return "Heure invalide"
    now_utc = get_adjusted_time()
    delta = end_time_utc - now_utc
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0: return "TERMINÉ"
    
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days > 0: return f"{days}j {hours}h"
    if hours > 0: return f"{hours}h {minutes}m"
    return f"{minutes}m {seconds}s"

def format_cooldown(delta: datetime.timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0: return "maintenant"
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days > 0: parts.append(f"{days}j")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0: parts.append(f"{minutes}m")
    if not parts and seconds > 0: parts.append(f"{seconds}s")
    return " ".join(parts) if parts else "quelques secondes"

async def check_admin_or_organizer(interaction: discord.Interaction, organizer_id: int):
    is_admin = interaction.user.guild_permissions.administrator
    is_org = interaction.user.id == organizer_id
    if not (is_admin or is_org):
        await interaction.response.send_message("Permission refusée.", ephemeral=True)
        return False
    return True

async def send_private_notification(user: discord.User, title: str, reason: str, mod=None, duration: str = None, damage: int = None, remaining_lives: int = None, is_auto: bool = False):
    try:
        author_text = "Le système de sécurité (Auto-Mod)" if is_auto else "Un administrateur"
        desc = f"**{author_text}** a pris une sanction à votre encontre."
        color = NEON_GREEN if "UNBAN" in title or "UNMUTE" in title else RETRO_ORANGE
        
        embed = discord.Embed(title=f"🚨 {title}", description=desc, color=color)
        embed.add_field(name="Raison", value=reason, inline=False)
        if duration: embed.add_field(name="Durée", value=duration, inline=True)
        if damage and damage > 0: embed.add_field(name="Vies perdues", value=f"- {damage} ❤️", inline=True)
        if remaining_lives is not None:
            hearts = "❤️" * remaining_lives + "🖤" * (9 - remaining_lives)
            embed.add_field(name="Santé", value=f"{remaining_lives} ❤️\n{hearts}", inline=False)
        
        embed.set_footer(text="Pour toute réclamation, ouvrez un ticket.")
        await user.send(embed=embed)
        return True
    except: return False

def censor_text(text: str, banned_words: list) -> (str, bool):
    censored = False
    words = text.split(' ')
    out = []
    for w in words:
        clean = ''.join(filter(str.isalnum, w)).lower()
        if clean in banned_words:
            censored = True
            out.append('*' * len(w))
        else:
            out.append(w)
    return ' '.join(out), censored

async def update_member_count_channel(guild: discord.Guild):
    cid = db['settings'].get("member_count_channel_id")
    if not cid: return
    ch = guild.get_channel(cid)
    if ch:
        try: await ch.edit(name=f"📊 Membres : {guild.member_count}")
        except: pass

def apply_embed_styles(embed: discord.Embed, style_key: str):
    styles = db.get("settings", {}).get("embed_styles", {}).get(style_key, {})
    if styles.get("thumbnail_url"): embed.set_thumbnail(url=styles["thumbnail_url"])
    if styles.get("footer_image_url"):
        footer_text = embed.footer.text if embed.footer.text else ""
        embed.set_footer(text=footer_text, icon_url=styles["footer_image_url"])
    return embed

async def translate_to_french(text: str) -> str:
    if not text or not TRANSLATOR_AVAILABLE: return text
    try:
        loop = asyncio.get_event_loop()
        translated = await loop.run_in_executor(None, lambda: GoogleTranslator(source='auto', target='fr').translate(text))
        return translated if translated else text
    except Exception as e:
        logger.warning(f"Erreur traduction: {e}")
        return text

# --- CORE WEB REQUEST (Hérité de Economy - Version Robuste) ---
async def fetch_url(url: str, response_type: str = 'text', headers: Optional[Dict] = None, params: Optional[Dict] = None, data: Optional[Dict] = None, method: str = 'GET', timeout: int = 20) -> Optional[Any]:
    request_headers = headers or {}
    if response_type == 'bytes':
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: requests.get(url, headers=request_headers, params=params, timeout=timeout))
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"fetch_url (bytes) échoué pour {url}: {e}")
            return None

    if 'User-Agent' not in request_headers:
        request_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

    try:
        loop = asyncio.get_event_loop()
        request_args = {"url": url, "headers": request_headers, "params": params, "timeout": timeout}
        if data:
            if method.upper() == 'POST' and request_headers.get("Content-Type") == "application/json": request_args["json"] = data
            else: request_args["data"] = data

        if method.upper() == 'POST': response = await loop.run_in_executor(None, lambda: requests.post(**request_args))
        else: response = await loop.run_in_executor(None, lambda: requests.get(**request_args))

        response.raise_for_status()
        
        if response_type == 'json':
            try: return response.json()
            except json.JSONDecodeError as e:
                logger.error(f"fetch_url (json) Erreur décodage pour {url}: {e}")
                return None
        else: return response.text
    except requests.exceptions.RequestException as e:
        status = e.response.status_code if e.response is not None else "N/A"
        if status != 404: logger.error(f"fetch_url (api) échoué pour {url} (Code: {status}): {e}")
        return None
    except Exception as e:
        logger.exception(f"fetch_url (api) Erreur fatale pour {url}: {e}")
        return None

# ==================================================================================================
# 7. MOTEUR GRAPHIQUE (RANK CARD - PIXEL ART)
# ==================================================================================================

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def create_gradient_image(width: int, height: int, start_hex: str, mid_hex: str, end_hex: str) -> Image:
    if not PIL_AVAILABLE: return None
    start_rgb = hex_to_rgb(start_hex)
    mid_rgb = hex_to_rgb(mid_hex)
    end_rgb = hex_to_rgb(end_hex)
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    mid_point = width // 2
    for x in range(width):
        if x < mid_point:
            ratio = x / mid_point
            r = int(start_rgb[0] * (1 - ratio) + mid_rgb[0] * ratio)
            g = int(start_rgb[1] * (1 - ratio) + mid_rgb[1] * ratio)
            b = int(start_rgb[2] * (1 - ratio) + mid_rgb[2] * ratio)
        else:
            ratio = (x - mid_point) / (width - mid_point)
            r = int(mid_rgb[0] * (1 - ratio) + end_rgb[0] * ratio)
            g = int(mid_rgb[1] * (1 - ratio) + end_rgb[1] * ratio)
            b = int(mid_rgb[2] * (1 - ratio) + end_rgb[2] * ratio)
        draw.line([(x, 0), (x, height)], fill=(r, g, b))
    return img

def download_and_cache_assets():
    global pixel_font_l, pixel_font_m, pixel_font_s, rank_card_bg, PIL_AVAILABLE
    if not PIL_AVAILABLE: return
    
    if not os.path.exists(pixel_font_path):
        try:
            response = requests.get(RANK_CARD_FONT_URL)
            response.raise_for_status()
            with open(pixel_font_path, "wb") as f: f.write(response.content)
        except Exception as e:
            logger.error(f"Download Font Error: {e}")
            PIL_AVAILABLE = False
            return

    if pixel_font_l is None:
        try:
            pixel_font_l = ImageFont.truetype(pixel_font_path, 20)
            pixel_font_m = ImageFont.truetype(pixel_font_path, 12)
            pixel_font_s = ImageFont.truetype(pixel_font_path, 10)
        except Exception: PIL_AVAILABLE = False; return

    if rank_card_bg is None:
        try:
            response = requests.get(RANK_CARD_BACKGROUND_URL)
            response.raise_for_status()
            img_bytes = io.BytesIO(response.content)
            rank_card_bg = Image.open(img_bytes).convert("RGBA")
        except Exception: PIL_AVAILABLE = False; return

async def generate_rank_card_image(current_xp: int, required_xp: int, level: int, global_rank: int, weekly_rank: int, username: str, avatar_url: str) -> Optional[io.BytesIO]:
    if not PIL_AVAILABLE: return None
    download_and_cache_assets()
    if not PIL_AVAILABLE or rank_card_bg is None or pixel_font_l is None: return None

    try:
        card_width, card_height, avatar_size, padding = 600, 180, 128, 20
        img = rank_card_bg.copy()
        img = ImageOps.fit(img, (card_width, card_height), method=Image.Resampling.LANCZOS)
        overlay = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 150))
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        avatar_bytes = await fetch_url(avatar_url, response_type='bytes')
        if avatar_bytes:
            avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
            avatar_img.putalpha(mask)
            img.paste(avatar_img, (padding, (card_height - avatar_size) // 2), avatar_img)

        text_start_x = padding + avatar_size + padding
        text_width = card_width - text_start_x - padding
        
        # Rank & Level
        rank_val, level_val = f"#{global_rank}", f"{level}"
        level_val_size = draw.textlength(level_val, font=pixel_font_l)
        level_val_x = card_width - padding - level_val_size
        level_text_size = draw.textlength("NIVEAU", font=pixel_font_m)
        level_text_x = level_val_x - level_text_size - 8
        rank_val_size = draw.textlength(rank_val, font=pixel_font_l)
        rank_val_x = level_text_x - rank_val_size - padding
        rank_text_size = draw.textlength("RANG", font=pixel_font_m)
        
        text_y = padding + 5
        draw.text((rank_val_x - rank_text_size - 8, text_y + 4), "RANG", fill=(200, 200, 200), font=pixel_font_m)
        draw.text((rank_val_x, text_y), rank_val, fill=(255, 255, 255), font=pixel_font_l)
        draw.text((level_text_x, text_y + 4), "NIVEAU", fill=(200, 200, 200), font=pixel_font_m)
        draw.text((level_val_x, text_y), level_val, fill=hex_to_rgb(RANK_CARD_GRADIENT_END), font=pixel_font_l)

        # Username
        draw.text((text_start_x, text_y + 35), username[:20], fill=(255, 255, 255), font=pixel_font_l)

        # XP Bar
        bar_height, bar_y, bar_frame = 28, text_y + 70, 3
        progress = min(1.0, current_xp / required_xp) if required_xp > 0 else 1.0
        bar_width_filled = int(text_width * progress)
        
        draw.rectangle((text_start_x, bar_y, text_start_x + text_width, bar_y + bar_height), outline=(200, 200, 200), width=bar_frame)
        draw.rectangle((text_start_x + bar_frame, bar_y + bar_frame, text_start_x + text_width - bar_frame, bar_y + bar_height - bar_frame), fill=(40, 40, 40))
        
        if bar_width_filled > bar_frame * 2:
            grad = create_gradient_image(bar_width_filled, bar_height - bar_frame * 2, RANK_CARD_GRADIENT_START, RANK_CARD_GRADIENT_MID, RANK_CARD_GRADIENT_END)
            img.paste(grad, (text_start_x + bar_frame, bar_y + bar_frame))
            for x in range(text_start_x + bar_frame + 10, text_start_x + bar_width_filled, 10):
                draw.line((x, bar_y + bar_frame, x, bar_y + bar_height - bar_frame), fill=(0, 0, 0, 100), width=1)

        # Footer Stats
        xp_text = f"{current_xp} / {required_xp} XP"
        draw.text((card_width - padding - draw.textlength(xp_text, font=pixel_font_m), text_y + 45), xp_text, fill=(220, 220, 220), font=pixel_font_m)
        draw.text((text_start_x, bar_y + bar_height + 10), f"TOP WEEK: #{weekly_rank}" if weekly_rank > 0 else "TOP WEEK: N/A", fill=(200, 200, 200), font=pixel_font_s)

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"Rank Card Error: {e}")
        return None


# ==================================================================================================
# 8. SYSTÈME D'XP & NIVEAUX (LOGIQUE)
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
                    except discord.Forbidden:
                        logger.error(f"Permissions manquantes pour ajouter le rôle {role_to_add.name}")
            except ValueError: pass

        # Préparer le message de félicitations
        level_up_desc = f"🎉 GG {member.mention} ! Tu passes au **Niveau {new_level}** !"
        if reward_messages:
            level_up_desc += "\n\n**Récompenses :**\n" + "\n".join(reward_messages)

        def get_level_color(lvl):
            if 1 <= lvl <= 5: return LIGHT_GREEN
            elif 6 <= lvl <= 10: return NEON_BLUE
            elif 11 <= lvl <= 20: return NEON_PURPLE
            elif 21 <= lvl <= 50: return RETRO_ORANGE
            else: return GOLD_COLOR

        embed = discord.Embed(title="🌟 LEVEL UP! 🌟", description=level_up_desc, color=get_level_color(new_level))
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Continue à être actif pour grimper dans le classement ! 💬")
        
        embed = apply_embed_styles(embed, "level_up")

        # Envoyer la notification publique
        public_notif_channel_id = rewards_settings.get("notification_channel_id")
        # Utiliser le client global s'il est dispo, sinon utiliser le channel passé en arg
        public_notif_channel = None
        if client and public_notif_channel_id:
            public_notif_channel = client.get_channel(public_notif_channel_id)
        
        target_channel = public_notif_channel or channel

        if target_channel:
            try:
                await target_channel.send(embed=embed)
            except: pass

        # Envoyer la notification privée
        if not user_data.get("dm_notifications_disabled", False):
            try:
                await member.send(embed=embed)
            except: pass

        # Déclencher l'avatar dynamique
        await trigger_avatar_change('xp_gain')

    if leveled_up:
        save_data(db)

async def update_user_xp(user_id: int, xp_change: int, is_weekly_xp: bool = True):
    """Met à jour l'XP total et hebdomadaire d'un utilisateur."""
    if xp_change == 0: return

    user_data = get_user_xp_data(user_id)
    user_data["xp"] = max(0, user_data["xp"] + xp_change)
    if is_weekly_xp and xp_change > 0:
        user_data["weekly_xp"] = max(0, user_data.get("weekly_xp", 0) + xp_change)
    return user_data

# ==================================================================================================
# 9. SYSTÈME DE VIES & INFRACTIONS (LOGIQUE)
# ==================================================================================================

def get_total_infraction_points(user_id: int) -> int:
    infs = db['infractions'].get(str(user_id), [])
    return sum(i.get('points_lost', 0) for i in infs)

def get_max_lives(member: discord.Member) -> int:
    if not isinstance(member, discord.Member): return db['settings'].get("max_lives_default", 9)
    return db['settings'].get("max_lives_boost", 10) if member.premium_since else db['settings'].get("max_lives_default", 9)

def display_lives(member: discord.Member, custom_points: int = None) -> str:
    max_lives = get_max_lives(member)
    lost = custom_points if custom_points is not None else get_total_infraction_points(member.id)
    
    fh = db['settings'].get("life_emoji_full", "❤️")
    eh = db['settings'].get("life_emoji_empty", "🖤")
    bh = db['settings'].get("life_emoji_boost", "💛")
    
    current = max(0, max_lives - lost)
    is_boosted = max_lives > 9
    
    hearts = []
    for i in range(1, max_lives + 1):
        if i <= current:
            if i == 10 and is_boosted: hearts.append(bh)
            else: hearts.append(fh)
        else:
            hearts.append(eh)
            
    return "".join(hearts)

async def check_perma_ban(client: discord.Client, member: discord.Member):
    max_l = get_max_lives(member)
    pts = get_total_infraction_points(member.id)
    if pts >= max_l:
        r = f"GAME OVER: {pts}/{max_l} vies perdues."
        try:
            await send_private_notification(member, "BAN DÉFINITIF", r, remaining_lives=0, is_auto=True)
            await member.ban(reason=r)
            await trigger_avatar_change('perma_ban')
            return True
        except: pass
    return False

def add_infraction_with_life_check(client, interaction, member, type, reason, custom_points=None, profile_name=None, send_dm=True):
    pts = custom_points if custom_points is not None else INFRACTION_POINTS.get(type, 0)
    rec = {
        "type": type, "reason": reason, "points_lost": pts,
        "timestamp": get_adjusted_time().isoformat(),
        "profile": profile_name
    }
    db['infractions'].setdefault(str(member.id), []).append(rec)
    save_data(db)
    
    if client:
        asyncio.create_task(check_perma_ban(client, member))
    
    if send_dm:
        max_l = get_max_lives(member)
        cur = get_total_infraction_points(member.id)
        rem = max(0, max_l - cur)
        asyncio.create_task(send_private_notification(member, f"SANCTION ({type.upper()})", reason, damage=pts, remaining_lives=rem, is_auto=True))
    
    return True

# ==================================================================================================
# 10. ACTIONS DE MODÉRATION (LOGIQUE PURE)
# ==================================================================================================

async def poxel_ban_logic(interaction: discord.Interaction, user: discord.User, reason: str, custom_points: int = None):
    """Logique centrale du Ban."""
    await interaction.response.defer(ephemeral=True)
    member = interaction.guild.get_member(user.id)
    max_lives = get_max_lives(member) if member else db['settings'].get("max_lives_default", 9)
    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("ban", 5)
    current_loss = get_total_infraction_points(user.id)
    remaining = max(0, max_lives - (current_loss + points))

    await send_private_notification(user, "BAN PERMANENT", reason, interaction.user, duration="Définitif", damage=points, remaining_lives=remaining)
    await asyncio.sleep(2)

    try:
        await interaction.guild.ban(user, reason=reason)
        add_infraction_with_life_check(client, interaction, user, "ban", reason, custom_points=points, send_dm=False)
        await trigger_avatar_change('ban')
        await interaction.followup.send(f"✅ **{user.name}** a été banni (MP envoyé).", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Erreur : Je n'ai pas la permission de bannir cet utilisateur.", ephemeral=True)

async def poxel_tempban_logic(interaction: discord.Interaction, user: discord.User, duration_str: str, reason: str, custom_points: int = None):
    """Logique centrale du Tempban."""
    await interaction.response.defer(ephemeral=True)
    delta = parse_duration(duration_str)
    if delta.total_seconds() <= 0: return await interaction.followup.send("❌ Durée invalide.", ephemeral=True)

    member = interaction.guild.get_member(user.id)
    max_lives = get_max_lives(member) if member else db['settings'].get("max_lives_default", 9)
    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("tempban", 3)
    current_loss = get_total_infraction_points(user.id)
    remaining = max(0, max_lives - (current_loss + points))

    await send_private_notification(user, "TEMPBAN", reason, interaction.user, duration=duration_str, damage=points, remaining_lives=remaining)
    await asyncio.sleep(2)

    unban_time = get_adjusted_time() + delta
    db.setdefault('scheduled_unbans', []).append({"guild_id": interaction.guild_id, "user_id": user.id, "unban_at": unban_time.isoformat()})
    save_data(db)

    try:
        await interaction.guild.ban(user, reason=f"Tempban ({duration_str}): {reason}")
        add_infraction_with_life_check(client, interaction, user, "tempban", f"({duration_str}) {reason}", custom_points=points, send_dm=False)
        await trigger_avatar_change('ban')
        await interaction.followup.send(f"✅ **{user.name}** banni pour {duration_str} (MP envoyé).", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Erreur permission.", ephemeral=True)

async def poxel_kick_logic(interaction: discord.Interaction, member: discord.Member, reason: str, custom_points: int = None):
    await interaction.response.defer(ephemeral=True)
    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("kick", 2)
    max_lives = get_max_lives(member)
    current_loss = get_total_infraction_points(member.id)
    remaining = max(0, max_lives - (current_loss + points))

    await send_private_notification(member, "KICK (EXPULSION)", reason, interaction.user, damage=points, remaining_lives=remaining)
    await asyncio.sleep(2)

    try:
        await member.kick(reason=reason)
        add_infraction_with_life_check(client, interaction, member, "kick", reason, custom_points=points, send_dm=False)
        await trigger_avatar_change('kick')
        await interaction.followup.send(f"✅ **{member.display_name}** expulsé (MP envoyé).", ephemeral=True)
    except: await interaction.followup.send("❌ Erreur permission.", ephemeral=True)

async def poxel_mute_logic(interaction: discord.Interaction, member: discord.Member, duration_str: str, reason: str, custom_points: int = None):
    await interaction.response.defer(ephemeral=True)
    delta = parse_duration(duration_str)
    if delta.total_seconds() <= 0: return await interaction.followup.send("❌ Durée invalide.", ephemeral=True)

    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("mute", 1)
    max_lives = get_max_lives(member)
    current_loss = get_total_infraction_points(member.id)
    remaining = max(0, max_lives - (current_loss + points))

    await send_private_notification(member, "MUTE (MISE EN SOURDINE)", reason, interaction.user, duration=duration_str, damage=points, remaining_lives=remaining)
    await asyncio.sleep(2)

    try:
        await member.timeout(discord.utils.utcnow() + delta, reason=reason)
        unmute_time = get_adjusted_time() + delta
        db.setdefault('scheduled_unmutes', []).append({"guild_id": interaction.guild_id, "user_id": member.id, "unmute_at": unmute_time.isoformat()})
        save_data(db)
        add_infraction_with_life_check(client, interaction, member, "mute", reason, custom_points=points, send_dm=False)
        await trigger_avatar_change('mute')
        await interaction.followup.send(f"✅ **{member.display_name}** rendu muet pour {duration_str} (MP envoyé).", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

async def poxel_warn_logic(interaction: discord.Interaction, user: discord.User, reason: str, custom_points: int = None):
    await interaction.response.defer(ephemeral=True)
    member = interaction.guild.get_member(user.id)
    max_lives = get_max_lives(member) if member else db['settings'].get("max_lives_default", 9)
    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("warn", 1)
    current_loss = get_total_infraction_points(user.id)
    remaining = max(0, max_lives - (current_loss + points))

    await send_private_notification(user, "AVERTISSEMENT", reason, interaction.user, damage=points, remaining_lives=remaining)
    await asyncio.sleep(1)
    
    add_infraction_with_life_check(client, interaction, user, "warn", reason, custom_points=points, send_dm=False)
    await trigger_avatar_change('warn')
    await interaction.followup.send(f"✅ **{user.name}** averti.", ephemeral=True)

async def poxel_unban_logic(interaction: discord.Interaction, user_id: str, reason: str = "Levée de sanction manuelle"):
    await interaction.response.defer(ephemeral=True)
    try:
        # Nécessite que client soit global ou passé. Ici on assume global 'client'
        if not client: return await interaction.followup.send("Erreur interne (Client not ready).", ephemeral=True)
        user = await client.fetch_user(int(user_id))
        
        embed_dm = discord.Embed(title="✅ DÉBANNISSEMENT (UNBAN)", description=f"Un administrateur du serveur **{interaction.guild.name}** a levé votre bannissement.", color=NEON_GREEN)
        embed_dm.add_field(name="Raison", value=reason, inline=False)
        try: await user.send(embed=embed_dm)
        except: pass

        await interaction.guild.unban(user, reason=f"Unban par admin: {reason}")
        if user_id in db['infractions']:
            del db['infractions'][user_id]
            save_data(db)
        await trigger_avatar_change('unban') 
        await interaction.followup.send(f"✅ **{user.name}** a été débanni.", ephemeral=True)
    except: await interaction.followup.send(f"❌ Utilisateur ID {user_id} introuvable ou erreur.", ephemeral=True)

async def poxel_unmute_logic(interaction: discord.Interaction, user_id: int):
    await interaction.response.defer(ephemeral=True)
    try:
        if not client: return
        user = await client.fetch_user(user_id)
        try: await user.send(f"🔊 Votre mute sur **{interaction.guild.name}** a été levé.")
        except: pass

        member = interaction.guild.get_member(user.id)
        if member:
            await member.timeout(None, reason="Unmute manuel par admin.")
            await interaction.followup.send(f"✅ **{user.name}** unmute.", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ **{user.name}** notifié (Hors serveur).", ephemeral=True)
            
        remaining = [t for t in db.get('scheduled_unmutes', []) if t['user_id'] != user.id]
        db['scheduled_unmutes'] = remaining
        save_data(db)
    except Exception as e: await interaction.followup.send(f"Erreur: {e}", ephemeral=True)

async def poxel_clear_infs_logic(interaction: discord.Interaction, member: discord.Member, reason: str):
    await interaction.response.defer(ephemeral=True)
    user_id_str = str(member.id)
    if user_id_str in db['infractions']:
        try: await member.send(f"♻️ Votre casier a été purgé sur **{interaction.guild.name}**. Raison: {reason}")
        except: pass
        del db['infractions'][user_id_str]
        save_data(db)
        await trigger_avatar_change('infraction_clear') 
        await interaction.followup.send(f"✅ Casier de **{member.display_name}** purgé.", ephemeral=True)
    else:
        await interaction.followup.send(f"**{member.display_name}** a déjà un casier vierge.", ephemeral=True)


# ==================================================================================================
# 11. SYSTÈME DE NOTIFICATIONS (STREAMING & VIDÉOS)
# ==================================================================================================

# --- Fonctions YouTube ---

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

# --- Fonctions Twitch ---

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
    
    clean_identifier = identifier.strip().lstrip('@').replace(" ", "")
    if "twitch.tv/" in clean_identifier:
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
        logger.error(f"Erreur Twitch pour {clean_identifier}: {e}")
    return []

# --- Fonctions Kick ---

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
        channel_response = await fetch_url(
            f"https://api.kick.com/public/v1/channels",
            response_type='json',
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Cache-Control": "no-cache"},
            params={"slug": identifier, "_": str(time.time())}
        )
        if not channel_response or not channel_response.get("data"): return []
        data = channel_response["data"][0]
        stream = data.get("stream")

        if not stream or not stream.get("is_live"): return []

        session_id = str(stream.get("id") or stream.get("start_time"))
        if not session_id: return []

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
    # Placeholder pour TikTok (nécessite API externe payante généralement)
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
    colors = {"youtube": YOUTUBE_COLOR, "twitch": TWITCH_COLOR, "kick": KICK_COLOR, "tiktok": TIKTOK_COLOR}
    icons = {"youtube": YOUTUBE_ICON, "twitch": TWITCH_ICON, "kick": KICK_ICON, "tiktok": TIKTOK_ICON}
    
    default_color = colors.get(platform, NEON_BLUE)
    default_icon = icons.get(platform, DEFAULT_ICON)

    if config.get("embed_json"):
        try:
            json_str = format_template(config["embed_json"], event)
            data = json.loads(json_str)
            embed_dict = data["embeds"][0] if "embeds" in data else data
            
            if "author" in embed_dict and "icon_url" in embed_dict["author"]:
                if not embed_dict["author"]["icon_url"] or not embed_dict["author"]["icon_url"].startswith("http"):
                    del embed_dict["author"]["icon_url"]
            
            embed = discord.Embed.from_dict(embed_dict)
            embed.url = event.get("url", "")
            if not embed.footer or not embed.footer.text:
                embed.set_footer(text=platform.capitalize())
            return embed
        except Exception: pass

    embed = discord.Embed(
        title=event.get("title", "Live"),
        url=event.get("url", ""),
        description=event.get("description") or "\u200b",
        color=default_color
    )
    
    avatar = event.get('creator_avatar')
    if avatar and avatar.startswith("http"):
        embed.set_author(name=event.get("creator", "Streamer"), icon_url=avatar)
    else:
        embed.set_author(name=event.get("creator", "Streamer"))

    if event.get("thumbnail"): embed.set_image(url=event.get("thumbnail"))
    if event.get("is_live") and event.get("game"):
        embed.add_field(name="Jeu", value=event.get("game"), inline=False)
    
    if event.get("timestamp"):
        try: embed.timestamp = datetime.datetime.fromisoformat(event.get("timestamp").replace("Z", "+00:00"))
        except: embed.timestamp = get_adjusted_time()

    embed.set_footer(text=platform.capitalize())
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

        if not events:
            if last_id is not None:
                logger.info(f"[{platform}] {profile_name} est HORS LIGNE. Reset mémoire.")
                notif_db.setdefault("last_seen", {}).pop(key, None)
                save_notif_data(notif_db)
            return

        new_event = events[0]
        new_id = str(new_event["id"])

        if str(last_id) != new_id:
            logger.info(f"[{platform}] Nouveau live/vidéo détecté pour {profile_name} (ID: {new_id})")
            await send_notification(guild, source_config, new_event)
            notif_db.setdefault("last_seen", {})[key] = new_id
            save_notif_data(notif_db)
        
    except Exception as e:
        logger.error(f"Erreur process source {source_config.get('name')}: {e}")

@tasks.loop(seconds=30)
async def check_other_platforms_loop(client_ref: discord.Client):
    await client_ref.wait_until_ready()
    tasks_list = []
    for gid, gconf in notif_db.get("servers", {}).items():
        guild = client_ref.get_guild(int(gid))
        if not guild: continue
        for src in gconf.get("sources", []):
            if src["platform"] != "youtube":
                tasks_list.append(process_single_source(guild, src))
    
    if tasks_list: await asyncio.gather(*tasks_list, return_exceptions=True)

@tasks.loop(minutes=1)
async def check_youtube_loop(client_ref: discord.Client):
    await client_ref.wait_until_ready()
    current_hm = get_adjusted_time().astimezone(USER_TIMEZONE).strftime('%H:%M')
    targets = [f"{h:02d}:00" for h in range(24)] + [f"{h:02d}:{m:02d}" for h in [12,18,20] for m in [1,2,3,4,5,10,15,20]]
    if current_hm not in set(targets): return

    tasks_list = []
    for gid, gconf in notif_db.get("servers", {}).items():
        guild = client_ref.get_guild(int(gid))
        if not guild: continue
        for src in gconf.get("sources", []):
            if src["platform"] == "youtube":
                tasks_list.append(process_single_source(guild, src))
    
    if tasks_list: await asyncio.gather(*tasks_list, return_exceptions=True)
    save_notif_data(notif_db)


# ==================================================================================================
# 12. SYSTÈME DE JEUX GRATUITS (EPIC, STEAM, GOG...)
# ==================================================================================================

async def create_free_game_embed(game_data: Dict) -> discord.Embed:
    """Crée un embed pour un jeu gratuit."""
    platforms_str = game_data.get('platforms', '').lower()
    
    platform_style = {
        "epic": {"logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Epic_Games_logo.svg/1200px-Epic_Games_logo.svg.png", "color": 0x333333, "name": "Epic Games"},
        "steam": {"logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/1024px-Steam_icon_logo.svg.png", "color": 0x1b2838, "name": "Steam"},
        "gog": {"logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/GOG.com_logo.svg/1024px-GOG.com_logo.svg.png", "color": 0x86328A, "name": "GOG"},
        "ubisoft": {"logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/78/Ubisoft_logo.svg/200px-Ubisoft_logo.svg.png", "color": 0x0091BD, "name": "Ubisoft"},
        "itch": {"logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/79/Itch.io_logo.svg/1200px-Itch.io_logo.svg.png", "color": 0xFA5C5C, "name": "Itch.io"}
    }

    current_style = {"logo": DEFAULT_ICON, "color": FREE_GAMES_COLOR, "name": "Autre"}
    if "epic" in platforms_str: current_style = platform_style["epic"]
    elif "steam" in platforms_str: current_style = platform_style["steam"]
    elif "gog" in platforms_str: current_style = platform_style["gog"]
    elif "ubisoft" in platforms_str or "uplay" in platforms_str: current_style = platform_style["ubisoft"]
    elif "itch" in platforms_str: current_style = platform_style["itch"]

    embed = discord.Embed(color=current_style["color"])
    embed.title = game_data.get('title', 'Jeu Gratuit !')
    url = game_data.get('open_giveaway_url') or game_data.get('gamerpower_url')
    embed.url = url

    worth = game_data.get('worth', '??')
    description = f"~~{worth}~~ **Gratuit**\n*Vite ! Récupère-le avant qu'il ne soit trop tard !* 🏃\n\n"
    
    raw_desc = game_data.get('description', '')
    if "Instructions:" in raw_desc: raw_desc = raw_desc.split("Instructions:")[0].strip()
    french_desc = await translate_to_french(raw_desc)
    description += f"{french_desc}\n\n"
    description += f"[**Ouvrir dans le navigateur ↗**]({url})"

    embed.description = description
    embed.set_thumbnail(url=current_style["logo"])
    if game_data.get('image'): embed.set_image(url=game_data['image'])
    embed.set_footer(text=f"via GamerPower • {current_style['name']}")
    embed.timestamp = get_adjusted_time()
    return embed

@tasks.loop(hours=4)
async def check_free_games_task(client_ref: discord.Client):
    await client_ref.wait_until_ready()
    settings = db["settings"].get("free_games_settings", {})
    channel_id = settings.get("channel_id")
    if not channel_id: return

    channel = client_ref.get_channel(channel_id)
    if not channel: return

    games = await fetch_url("https://www.gamerpower.com/api/giveaways?platform=pc", response_type='json')
    if not games or not isinstance(games, list): return

    posted_deals = set(settings.get("posted_deals", []))
    deals_to_save = list(posted_deals)
    embeds_to_send = []
    new_ids = []

    for game in games:
        game_id = game.get('id')
        if game_id and game_id not in posted_deals and game.get('type') == 'Game':
            try:
                embed = await create_free_game_embed(game)
                embeds_to_send.append(embed)
                new_ids.append(game_id)
            except: pass

    if embeds_to_send:
        for i, chunk in enumerate([embeds_to_send[i:i + 10] for i in range(0, len(embeds_to_send), 10)]):
            msg = "@everyone 🚨 **ALERTE JEU GRATUIT !** 🚨" if i == 0 else None
            try: await channel.send(content=msg, embeds=chunk)
            except: pass
            await asyncio.sleep(1.5)
        
        deals_to_save.extend(new_ids)
        db["settings"]["free_games_settings"]["posted_deals"] = deals_to_save[-300:]
        save_data(db)

# ==================================================================================================
# 13. CINÉ POXEL (FILMS & SÉRIES)
# ==================================================================================================

STREAMING_PLATFORMS_EXT = {
    "netflix": {"color": NETFLIX_COLOR, "icon": NETFLIX_ICON, "name": "Netflix", "aliases": ["netflix"]},
    "disney": {"color": DISNEY_COLOR, "icon": DISNEY_ICON, "name": "Disney+", "aliases": ["disney+", "disney plus"]},
    "prime": {"color": PRIME_COLOR, "icon": PRIME_ICON, "name": "Prime Video", "aliases": ["amazon prime video", "prime video"]},
    "apple": {"color": 0xA3AAAE, "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/28/Apple_TV_Plus_Logo.svg/1200px-Apple_TV_Plus_Logo.svg.png", "name": "Apple TV+", "aliases": ["apple tv+"]},
    "crunchyroll": {"color": 0xF47521, "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Crunchyroll_Logo.png/1200px-Crunchyroll_Logo.png", "name": "Crunchyroll", "aliases": ["crunchyroll"]},
    "adn": {"color": 0x0090D9, "icon": "https://upload.wikimedia.org/wikipedia/fr/thumb/3/3f/Logo_ADN_2016.svg/1200px-Logo_ADN_2016.svg.png", "name": "ADN", "aliases": ["adn"]},
    "cinema": {"color": CINEMA_COLOR, "icon": CINEMA_ICON, "name": "Cinéma", "aliases": ["cinema"]}
}

BIG_HIT_KEYWORDS = ["avatar", "avengers", "star wars", "one piece", "stranger things", "arcane", "gta", "demon slayer", "jujutsu kaisen", "dragon ball"]

def normalize_platform_name(api_name: str) -> Tuple[str, Dict]:
    clean = api_name.lower().strip()
    for _, data in STREAMING_PLATFORMS_EXT.items():
        if any(alias in clean for alias in data["aliases"]): return data["name"], data
    return api_name, {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON, "name": api_name}

async def get_watch_providers(media_type: str, tmdb_id: int, category: str = None) -> Tuple[str, Dict, str]:
    if not TMDB_API_KEY: return "Inconnu", {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}, ""
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
    data = await fetch_url(url, response_type='json')
    
    if not data or "results" not in data or "FR" not in data["results"]:
        return "Inconnu", {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}, ""
    
    fr = data["results"]["FR"]
    flatrate = fr.get("flatrate", []) or fr.get("buy", []) or fr.get("rent", [])
    if not flatrate: return "Inconnu", {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}, ""

    providers = {}
    for p in flatrate:
        norm_name, norm_style = normalize_platform_name(p["provider_name"])
        if norm_name not in providers: providers[norm_name] = norm_style

    if not providers: return "Inconnu", {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}, ""
    
    prov_list = list(providers.items())
    primary_name, primary_style = prov_list[0]

    # Priorité Anime
    if category == 'anime':
        for name, style in prov_list:
            if name in ["Crunchyroll", "ADN"]:
                primary_name, primary_style = name, style
                break

    others = ", ".join([n for n, _ in prov_list if n != primary_name])
    return primary_name, primary_style, others

def classify_content(item: Dict, media_type: str) -> str:
    genre_ids = item.get('genre_ids', [])
    country = item.get('origin_country', [])
    lang = item.get('original_language', '')
    is_anim = 16 in genre_ids
    is_jp = 'JP' in country or lang == 'ja'
    
    if is_anim: return 'anime' if is_jp else 'cartoon'
    return 'movie' if media_type == 'movie' else 'series'

async def create_cine_pixel_embed(item_id: int, media_type: str, category: str, is_episode: bool = False, episode_data: Optional[Dict] = None) -> discord.Embed:
    url = f"https://api.themoviedb.org/3/{media_type}/{item_id}?api_key={TMDB_API_KEY}&language=fr-FR"
    details = await fetch_url(url, response_type='json')
    if not details: return None

    # Détection Plateforme
    p_name, p_style, others = "Inconnu", {"color": DEFAULT_CINE_COLOR, "icon": DEFAULT_ICON}, ""
    if media_type == 'movie':
        rel = details.get('release_date', '2000-01-01')
        try:
            if (get_adjusted_time().date() - datetime.datetime.strptime(rel, "%Y-%m-%d").date()).days < 90:
                p_name, p_style = "Cinéma", STREAMING_PLATFORMS_EXT["cinema"]
        except: pass
    
    if p_name == "Inconnu":
        p_name, p_style, others = await get_watch_providers(media_type, item_id, category)

    is_big = any(k in details.get('title', details.get('name', '')).lower() for k in BIG_HIT_KEYWORDS) or (details.get('vote_count', 0) > 3000 and details.get('vote_average', 0) > 8.0)
    
    title = details.get('title') if media_type == 'movie' else details.get('name')
    if is_episode and episode_data:
        title += f" — S{episode_data.get('season_number'):02d}E{episode_data.get('episode_number'):02d}"

    embed = discord.Embed(title=f"{'🌟 ' if is_big else ''}{title}", url=f"https://www.themoviedb.org/{media_type}/{item_id}", color=GOLD_COLOR if is_big else p_style["color"])
    embed.set_thumbnail(url=p_style["icon"])
    
    desc = f"🎬 **{'Sortie en salle' if p_name == 'Cinéma' else 'Disponible'} sur {p_name} !**\n\n"
    overview = details.get('overview', 'Synopsis indisponible.')
    desc += f"{overview[:400]}..." if len(overview) > 400 else overview
    embed.description = desc

    if p_name != "Inconnu":
        val = f"**{p_name}**" + (f"\n*Aussi sur : {others}*" if others else "")
        embed.add_field(name="📺 Regarder sur", value=val, inline=False)

    img = details.get('backdrop_path') or details.get('poster_path')
    if is_episode and episode_data and episode_data.get('still_path'): img = episode_data.get('still_path')
    if img: embed.set_image(url=f"https://image.tmdb.org/t/p/original{img}")
    
    embed.set_footer(text="Poxel Ciné • Données TMDB")
    return embed

async def check_updates_for_category(client_ref, category_key: str, media_type: str, **kwargs):
    channel_id = db["settings"].get("cine_pixel_channels", {}).get(category_key)
    if not channel_id: return
    channel = client_ref.get_channel(channel_id)
    if not channel: return

    is_news = "news" in category_key
    url = f"https://api.themoviedb.org/3/{'movie/now_playing' if is_news and media_type == 'movie' else 'tv/on_the_air' if is_news else 'tv/airing_today'}?api_key={TMDB_API_KEY}&language=fr-FR&page=1"
    
    data = await fetch_url(url, response_type='json')
    if not data or "results" not in data: return

    history_key = f"history_{category_key}"
    history = db["settings"].setdefault("cine_history", {}).setdefault(history_key, [])
    today = get_adjusted_time().date()
    new_ids = []

    for item in data["results"]:
        cat = classify_content(item, media_type)
        if kwargs.get('is_anime') and cat != 'anime': continue
        if kwargs.get('is_cartoon') and cat != 'cartoon': continue
        if not kwargs.get('is_anime') and not kwargs.get('is_cartoon') and cat == 'anime': continue # Avoid anime in series channel

        unique_key = f"{item['id']}_{today}"
        if unique_key in history: continue

        embed = None
        try:
            if is_news:
                date_key = 'release_date' if media_type == 'movie' else 'first_air_date'
                rel_date = item.get(date_key)
                if rel_date and (today - datetime.datetime.strptime(rel_date, "%Y-%m-%d").date()).days < 7:
                    embed = await create_cine_pixel_embed(item['id'], media_type, cat)
            else: # Episodes
                det = await fetch_url(f"https://api.themoviedb.org/3/tv/{item['id']}?api_key={TMDB_API_KEY}&language=fr-FR", response_type='json')
                last = det.get('last_episode_to_air')
                if last and last.get('air_date') == str(today):
                    embed = await create_cine_pixel_embed(item['id'], media_type, cat, is_episode=True, episode_data=last)
            
            if embed:
                await channel.send(embed=embed)
                new_ids.append(unique_key)
                await asyncio.sleep(1.5)
        except: pass

    history.extend(new_ids)
    db["settings"]["cine_history"][history_key] = history[-200:]
    save_data(db)

@tasks.loop(hours=4)
async def check_cine_news_task(client_ref: discord.Client):
    await client_ref.wait_until_ready()
    if not TMDB_API_KEY: return
    
    # News
    await check_updates_for_category(client_ref, 'news_series', 'tv')
    await check_updates_for_category(client_ref, 'news_anime', 'tv', is_anime=True)
    await check_updates_for_category(client_ref, 'news_cartoons', 'tv', is_cartoon=True)
    await check_updates_for_category(client_ref, 'news_movies', 'movie')
    # Episodes
    await check_updates_for_category(client_ref, 'episodes_series', 'tv')
    await check_updates_for_category(client_ref, 'episodes_anime', 'tv', is_anime=True)
    await check_updates_for_category(client_ref, 'episodes_cartoons', 'tv', is_cartoon=True)

# ==================================================================================================
# 14. AUTOMATISATION SOCIALE (ANNIVERSAIRES & TOPWEEK & BACKUP)
# ==================================================================================================

@tasks.loop(time=datetime.time(hour=0, minute=1, tzinfo=SERVER_TIMEZONE))
async def check_birthdays(client_ref: discord.Client):
    await client_ref.wait_until_ready()
    settings = db["settings"].get("birthday_settings", {})
    channel_id = settings.get("channel_id")
    if not channel_id: return
    channel = client_ref.get_channel(channel_id)
    if not channel: return

    today = get_adjusted_time().strftime("%m-%d")
    mentions = []
    for uid, date in db.get("birthdays", {}).items():
        if date == today:
            member = channel.guild.get_member(int(uid))
            if member: mentions.append(member)

    if mentions:
        txt = ", ".join(m.mention for m in mentions)
        embed = discord.Embed(title="🎂 Joyeux Anniversaire ! 🎂", description=f"Bon anniversaire à {txt} ! 🎉", color=GOLD_COLOR)
        embed = apply_embed_styles(embed, "birthday_announce")
        try: await channel.send(content="@everyone", embed=embed)
        except: pass
        
        for m in mentions:
            await update_user_xp(m.id, settings.get("reward_xp", 100))
            await check_and_handle_progression(m, channel)
        save_data(db)

@tasks.loop(time=datetime.time(hour=0, minute=0, second=5, tzinfo=SERVER_TIMEZONE))
async def weekly_xp_reset(client_ref: discord.Client):
    await client_ref.wait_until_ready()
    if get_adjusted_time().weekday() == 0: # Lundi
        for _, data in db.get("users", {}).items(): data["weekly_xp"] = 0
        save_data(db)

@tasks.loop(hours=1)
async def post_weekly_leaderboard(client_ref: discord.Client):
    await client_ref.wait_until_ready()
    settings = db["settings"].get("topweek_settings", {})
    cid = settings.get("channel_id")
    if not cid: return
    
    now = get_adjusted_time()
    if now.weekday() != settings.get("announcement_day", 6): return
    target_hm = settings.get("announcement_time", "19:00")
    if now.strftime("%H:%M") != target_hm: return
    
    week_id = now.strftime('%Y-%U')
    if settings.get("last_posted_week") == week_id: return

    channel = client_ref.get_channel(cid)
    if not channel: return

    players = {u: d for u, d in db.get("users", {}).items() if d.get("weekly_xp", 0) > 0}
    if not players:
        settings["last_posted_week"] = week_id
        save_data(db)
        return

    top = sorted(players.items(), key=lambda x: x[1].get("weekly_xp", 0), reverse=True)[:3]
    embed = discord.Embed(title="🏆 Palmarès Hebdomadaire ! 🏆", description="Bravo aux meilleurs joueurs de la semaine !", color=GOLD_COLOR)
    
    rewards = settings.get("rewards", {})
    reward_keys = ["first", "second", "third"]
    
    lines = []
    for i, (uid, data) in enumerate(top):
        member = channel.guild.get_member(int(uid))
        name = member.display_name if member else "Joueur parti"
        lines.append(f"{LEADERBOARD_EMOJIS[i]} **{name}** - `{data['weekly_xp']}` XP")
        
        bonus = rewards.get(reward_keys[i], {}).get("xp", 0)
        if bonus > 0:
            await update_user_xp(int(uid), bonus, False)
            if member: await check_and_handle_progression(member, channel)

    embed.description += "\n\n" + "\n".join(lines)
    embed = apply_embed_styles(embed, "topweek_announce")
    await channel.send(embed=embed)
    
    settings["last_posted_week"] = week_id
    save_data(db)

@tasks.loop(hours=6)
async def backup_xp_data(client_ref: discord.Client):
    try:
        backup = {u: {"xp": d.get("xp"), "level": d.get("level")} for u, d in db.get("users", {}).items()}
        with open(XP_BACKUP_FILE, 'w') as f: json.dump({"timestamp": get_adjusted_time().isoformat(), "users": backup}, f)
    except: pass


# ==================================================================================================
# 16. SYSTÈME VOCAL (INTERFACE & LOGIQUE UI)
# ==================================================================================================

# --- Utilitaire de nettoyage JSON (Local) ---
def sanitize_voice_json(data):
    """Nettoie le JSON pour éviter les erreurs d'URL vides."""
    if not isinstance(data, dict): return data
    if 'thumbnail' in data and not data['thumbnail'].get('url'): del data['thumbnail']
    if 'image' in data and not data['image'].get('url'): del data['image']
    if 'footer' in data and not data['footer'].get('icon_url'):
        if 'text' not in data['footer']: del data['footer']
        else: del data['footer']['icon_url']
    if 'author' in data and not data['author'].get('icon_url'): 
        if 'name' not in data['author']: del data['author']
        else: del data['author']['icon_url']
    return data

# --- CONFIGURATION PAR DÉFAUT DE L'INTERFACE ---
VOICE_BUTTONS_DEFAULTS = {
    "vd_limit": {"emoji": "👥", "label": "Limit", "style": discord.ButtonStyle.secondary, "row": 0},
    "vd_privacy": {"emoji": "🛡️", "label": "Privacy", "style": discord.ButtonStyle.secondary, "row": 0},
    "vd_trust": {"emoji": "👤", "label": "Trust", "style": discord.ButtonStyle.secondary, "row": 0},
    "vd_untrust": {"emoji": "💔", "label": "Untrust", "style": discord.ButtonStyle.secondary, "row": 0},
    "vd_kick": {"emoji": "🦵", "label": "Kick", "style": discord.ButtonStyle.secondary, "row": 0},
    "vd_block": {"emoji": "🚫", "label": "Block", "style": discord.ButtonStyle.secondary, "row": 1},
    "vd_unblock": {"emoji": "✅", "label": "Unblock", "style": discord.ButtonStyle.secondary, "row": 1},
    "vd_transfer": {"emoji": "👑", "label": "Transfer", "style": discord.ButtonStyle.secondary, "row": 1},
    "vd_claim": {"emoji": "✊", "label": "Claim", "style": discord.ButtonStyle.secondary, "row": 1},
    "vd_delete": {"emoji": "🗑️", "label": "Delete", "style": discord.ButtonStyle.secondary, "row": 1}
}

VOICE_PRIVACY_DEFAULTS = {
    "lock": {"emoji": "🔒", "label": "Verrouiller", "description": "Fermer l'accès au salon."},
    "unlock": {"emoji": "🔓", "label": "Déverrouiller", "description": "Ouvrir l'accès à tous."},
    "hide": {"emoji": "🙈", "label": "Invisible", "description": "Cacher le salon aux autres."},
    "show": {"emoji": "👁️", "label": "Visible", "description": "Rendre le salon visible."},
    "close_chat": {"emoji": "💬", "label": "Fermer le chat", "description": "Chat réservé aux membres."},
    "open_chat": {"emoji": "🗨️", "label": "Ouvrir le chat", "description": "Chat ouvert à tous."}
}

def get_voice_ui_config(item_id: str, item_type: str = "button"):
    defaults = VOICE_BUTTONS_DEFAULTS if item_type == "button" else VOICE_PRIVACY_DEFAULTS
    saved_config = db.get('settings', {}).get('voice_ui', {}).get(item_type, {}).get(item_id, {})
    base = defaults.get(item_id, {}).copy()
    base.update(saved_config)
    return base

# --- LOGIQUE DES PERMISSIONS VOCALES ---
async def update_voice_permission(channel, target, connect=None, view=None, speak=None):
    overwrite = channel.overwrites_for(target)
    if connect is not None: overwrite.connect = connect
    if view is not None: overwrite.view_channel = view
    if speak is not None: overwrite.speak = speak
    await channel.set_permissions(target, overwrite=overwrite)

# --- VUES ET MODALES DE L'INTERFACE ---

class VoiceLimitModal(Modal, title="Configurer la Limite"):
    limit = TextInput(label="Nombre max d'utilisateurs (0-99)", placeholder="0 = Illimité", min_length=1, max_length=2)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.limit.value)
            if limit < 0 or limit > 99: raise ValueError
            if interaction.user.voice and interaction.user.voice.channel:
                await interaction.user.voice.channel.edit(user_limit=limit)
                await interaction.response.send_message(f"✅ Limite définie à **{limit if limit > 0 else 'Illimité'}**.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Vous n'êtes plus dans le salon.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Nombre invalide.", ephemeral=True)

class VoicePrivacyView(View):
    def __init__(self, voice_channel):
        super().__init__(timeout=60)
        self.voice_channel = voice_channel
        self.build_select_menu()

    def build_select_menu(self):
        options = []
        for key in VOICE_PRIVACY_DEFAULTS.keys():
            cfg = get_voice_ui_config(key, "privacy")
            options.append(discord.SelectOption(
                label=cfg.get('label') or key,
                value=key,
                emoji=cfg.get('emoji'),
                description=cfg.get('description')
            ))

        self.select = Select(placeholder="Choisir une option de confidentialité...", options=options)
        self.select.callback = self.callback
        self.add_item(self.select)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        val = self.select.values[0]
        vc = self.voice_channel
        everyone = vc.guild.default_role
        
        cfg = get_voice_ui_config(val, "privacy")
        label = cfg.get('label', val)
        emoji = cfg.get('emoji', '')
        msg = f"{emoji} **{label}** appliqué."

        if val == "lock": await update_voice_permission(vc, everyone, connect=False)
        elif val == "unlock": await update_voice_permission(vc, everyone, connect=True)
        elif val == "hide": await update_voice_permission(vc, everyone, view=False)
        elif val == "show": await update_voice_permission(vc, everyone, view=True)
        elif val == "close_chat": await vc.set_permissions(everyone, send_messages=False)
        elif val == "open_chat": await vc.set_permissions(everyone, send_messages=True)
            
        await interaction.followup.send(msg, ephemeral=True)

class VoiceUserActionView(View):
    def __init__(self, action: str, voice_channel: discord.VoiceChannel, current_list: list = None):
        super().__init__(timeout=60)
        self.action = action
        self.voice_channel = voice_channel
        self.current_list = current_list or []

        if action in ["untrust", "unblock"]:
            options = []
            for uid in self.current_list:
                member = voice_channel.guild.get_member(uid)
                label = member.display_name if member else f"Utilisateur {uid}"
                options.append(discord.SelectOption(label=label, value=str(uid)))
            
            if not options: self.add_item(Select(placeholder="Personne dans la liste...", options=[discord.SelectOption(label="Vide", value="none")], disabled=True))
            else:
                select = Select(placeholder=f"Choisir les membres à {action}...", options=options[:25], max_values=min(len(options), 25))
                select.callback = self.callback_string
                self.add_item(select)
        else:
            select = discord.ui.UserSelect(placeholder=f"Rechercher des membres pour {action}...", max_values=5)
            select.callback = self.callback_user
            self.add_item(select)

    async def callback_user(self, interaction: discord.Interaction): await self.process_users(interaction, interaction.data['values'])
    async def callback_string(self, interaction: discord.Interaction):
        if self.children[0].values[0] == "none": return
        await self.process_users(interaction, self.children[0].values)

    async def process_users(self, interaction: discord.Interaction, user_ids):
        await interaction.response.defer(ephemeral=True)
        vc = self.voice_channel
        channel_id = str(vc.id)
        if channel_id not in db['temp_channels']: db['temp_channels'][channel_id] = {'owner_id': interaction.user.id, 'trusted': [], 'blocked': []}
        channel_data = db['temp_channels'][channel_id]
        updated_names = []

        for uid_str in user_ids:
            try: uid = int(uid_str)
            except ValueError: continue
            member = interaction.guild.get_member(uid)
            if not member and self.action not in ["untrust", "unblock"]: continue
            if uid == interaction.user.id: continue

            if self.action == "trust":
                if uid not in channel_data['trusted']:
                    channel_data['trusted'].append(uid)
                    await update_voice_permission(vc, member, connect=True, view=True)
                    try: await member.send(f"🛡️ **De confiance !** Vous êtes désormais de confiance dans le salon de {interaction.user.display_name}.")
                    except: pass
                    updated_names.append(member.display_name)
            elif self.action == "kick":
                if member and member in vc.members:
                    await member.move_to(None)
                    updated_names.append(member.display_name)
            elif self.action == "block":
                if uid not in channel_data['blocked']:
                    channel_data['blocked'].append(uid)
                    if member:
                        await update_voice_permission(vc, member, connect=False)
                        if member in vc.members: await member.move_to(None)
                    updated_names.append(member.display_name if member else str(uid))
            elif self.action == "transfer":
                if member:
                    channel_data['owner_id'] = uid
                    await update_voice_permission(vc, member, connect=True, view=True, speak=True)
                    await vc.edit(name=f"🎧 Salon de {member.display_name}")
                    await interaction.followup.send(f"👑 **Transfert !** Le salon appartient maintenant à {member.mention}.", ephemeral=True)
                    save_data(db)
                    return 

        if self.action == "untrust":
            for uid_str in user_ids:
                uid = int(uid_str)
                if uid in channel_data['trusted']:
                    channel_data['trusted'].remove(uid)
                    member = interaction.guild.get_member(uid)
                    if member: await vc.set_permissions(member, overwrite=None)
                    updated_names.append(member.display_name if member else str(uid))
        elif self.action == "unblock":
            for uid_str in user_ids:
                uid = int(uid_str)
                if uid in channel_data['blocked']:
                    channel_data['blocked'].remove(uid)
                    member = interaction.guild.get_member(uid)
                    if member: await vc.set_permissions(member, overwrite=None)
                    updated_names.append(member.display_name if member else str(uid))

        save_data(db)
        if updated_names:
            action_map = {"trust": "ajoutés aux amis", "untrust": "retirés", "block": "bloqués", "unblock": "débloqués", "kick": "exclus"}
            await interaction.followup.send(f"✅ Utilisateurs {action_map.get(self.action, 'modifiés')} : {', '.join(updated_names)}", ephemeral=True)
        else: await interaction.followup.send("❌ Aucune modification effectuée.", ephemeral=True)

class VoiceDeleteConfirmView(View):
    def __init__(self, voice_channel):
        super().__init__(timeout=30)
        self.voice_channel = voice_channel
    @discord.ui.button(label="Confirmer la suppression", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        try: await self.voice_channel.delete()
        except: await interaction.followup.send("❌ Impossible de supprimer le salon.", ephemeral=True)

# --- VUE PRINCIPALE (PANEL PERMANENT) ---
class VoiceDashboardView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.rebuild_buttons()

    def rebuild_buttons(self):
        self.clear_items()
        for btn_id in VOICE_BUTTONS_DEFAULTS.keys():
            cfg = get_voice_ui_config(btn_id, "button")
            label = cfg.get("label")
            if not label or label.strip() == "": label = None
            
            button = Button(
                style=cfg.get("style", discord.ButtonStyle.secondary),
                label=label,
                emoji=cfg.get("emoji"),
                custom_id=btn_id,
                row=cfg.get("row", 0)
            )
            if btn_id == "vd_limit": button.callback = self.btn_limit
            elif btn_id == "vd_privacy": button.callback = self.btn_privacy
            elif btn_id == "vd_trust": button.callback = self.btn_trust
            elif btn_id == "vd_untrust": button.callback = self.btn_untrust
            elif btn_id == "vd_kick": button.callback = self.btn_kick
            elif btn_id == "vd_block": button.callback = self.btn_block
            elif btn_id == "vd_unblock": button.callback = self.btn_unblock
            elif btn_id == "vd_transfer": button.callback = self.btn_transfer
            elif btn_id == "vd_claim": button.callback = self.btn_claim
            elif btn_id == "vd_delete": button.callback = self.btn_delete
            self.add_item(button)

    async def get_active_channel(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await self.send_error(interaction)
            return None, None
        vc = interaction.user.voice.channel
        channel_id = str(vc.id)
        if channel_id not in db['temp_channels']:
            await interaction.response.send_message("❌ Ce salon vocal n'est pas géré par le bot.", ephemeral=True)
            return None, None
        data = db['temp_channels'][channel_id]
        if interaction.data.get('custom_id') == "vd_claim": return interaction.user.voice.channel, False
        is_owner = data['owner_id'] == interaction.user.id
        if not is_owner:
            await interaction.response.send_message("❌ Vous n'êtes pas le propriétaire de ce salon.", ephemeral=True)
            return None, None
        return vc, is_owner

    async def send_error(self, interaction: discord.Interaction):
        hub_channel = None
        for hub_id in db.get('voice_hubs', {}):
            try:
                hub_channel = interaction.guild.get_channel(int(hub_id))
                if hub_channel: break
            except: pass
        hub_mention = hub_channel.mention if hub_channel else "un salon créateur"
        
        error_json_str = db.get('settings', {}).get('voice_error_json')
        embed = None
        if error_json_str:
            try:
                data = json.loads(error_json_str)
                if 'embeds' in data: data = data['embeds'][0]
                desc = data.get('description', '').replace('{user}', interaction.user.mention).replace('{hub}', hub_mention)
                data['description'] = desc
                embed = discord.Embed.from_dict(data)
            except: pass
        if not embed:
            embed = discord.Embed(title="❌ Erreur Vocal", description=f"Vous n'êtes pas dans un salon vocal temporaire.\nRejoignez d'abord {hub_mention}.", color=0x8B0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def btn_limit(self, interaction: discord.Interaction):
        vc, is_owner = await self.get_active_channel(interaction)
        if vc: await interaction.response.send_modal(VoiceLimitModal())
    async def btn_privacy(self, interaction: discord.Interaction):
        vc, is_owner = await self.get_active_channel(interaction)
        if vc: await interaction.response.send_message("Configuration Confidentialité :", view=VoicePrivacyView(vc), ephemeral=True)
    async def btn_trust(self, interaction: discord.Interaction):
        vc, is_owner = await self.get_active_channel(interaction)
        if vc: await interaction.response.send_message("Ajouter confiance :", view=VoiceUserActionView("trust", vc), ephemeral=True)
    async def btn_untrust(self, interaction: discord.Interaction):
        vc, is_owner = await self.get_active_channel(interaction)
        if vc:
            trusted = db['temp_channels'][str(vc.id)].get('trusted', [])
            await interaction.response.send_message("Retirer la confiance :", view=VoiceUserActionView("untrust", vc, trusted), ephemeral=True)
    async def btn_kick(self, interaction: discord.Interaction):
        vc, is_owner = await self.get_active_channel(interaction)
        if vc: await interaction.response.send_message("Expulser un membre :", view=VoiceUserActionView("kick", vc), ephemeral=True)
    async def btn_block(self, interaction: discord.Interaction):
        vc, is_owner = await self.get_active_channel(interaction)
        if vc: await interaction.response.send_message("Bloquer un membre :", view=VoiceUserActionView("block", vc), ephemeral=True)
    async def btn_unblock(self, interaction: discord.Interaction):
        vc, is_owner = await self.get_active_channel(interaction)
        if vc:
            blocked = db['temp_channels'][str(vc.id)].get('blocked', [])
            await interaction.response.send_message("Débloquer un membre :", view=VoiceUserActionView("unblock", vc, blocked), ephemeral=True)
    async def btn_transfer(self, interaction: discord.Interaction):
        vc, is_owner = await self.get_active_channel(interaction)
        if vc: await interaction.response.send_message("Transférer la propriété :", view=VoiceUserActionView("transfer", vc), ephemeral=True)
    async def btn_claim(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel: return await self.send_error(interaction)
        channel_id = str(interaction.user.voice.channel.id)
        if channel_id not in db['temp_channels']: return await interaction.response.send_message("❌ Ce n'est pas un salon temporaire.", ephemeral=True)
        data = db['temp_channels'][channel_id]
        current_owner = interaction.guild.get_member(data['owner_id'])
        if not current_owner or current_owner not in interaction.user.voice.channel.members:
            data['owner_id'] = interaction.user.id
            save_data(db)
            await interaction.user.voice.channel.edit(name=f"🎧 Salon de {interaction.user.display_name}")
            await interaction.response.send_message(f"👑 Propriété récupérée !", ephemeral=True)
        else: await interaction.response.send_message(f"❌ Le propriétaire est encore là !", ephemeral=True)
    async def btn_delete(self, interaction: discord.Interaction):
        vc, is_owner = await self.get_active_channel(interaction)
        if vc: await interaction.response.send_message("⚠️ **Vous êtes sûr ?**", view=VoiceDeleteConfirmView(vc), ephemeral=True)

# --- CLASSES AUXILIAIRES DE CONFIGURATION ---
class VoiceUIEditModal(Modal):
    def __init__(self, item_id, item_label, item_type, view_ref):
        super().__init__(title=f"Éditer : {item_label}")
        self.item_id = item_id
        self.item_type = item_type
        self.view_ref = view_ref
        current_cfg = get_voice_ui_config(item_id, item_type)
        self.emoji_input = TextInput(label="Emoji", placeholder="ex: 🚀", default=current_cfg.get('emoji'), max_length=5, required=True)
        self.label_input = TextInput(label="Texte (Vide pour cacher)", placeholder="Texte...", default=current_cfg.get('label'), required=False)
        self.add_item(self.emoji_input)
        self.add_item(self.label_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_emoji = self.emoji_input.value.strip()
        new_label = self.label_input.value.strip()
        db.setdefault('settings', {}).setdefault('voice_ui', {}).setdefault(self.item_type, {})[self.item_id] = {"emoji": new_emoji, "label": new_label}
        save_data(db)
        await interaction.followup.send(f"✅ Élément **{self.item_id}** mis à jour !", ephemeral=True)

class VoiceElementSelectView(View):
    def __init__(self, config_type):
        super().__init__(timeout=180)
        self.config_type = config_type
        options = []
        source_dict = VOICE_BUTTONS_DEFAULTS if config_type == "button" else VOICE_PRIVACY_DEFAULTS
        for key, default_data in source_dict.items():
            current = get_voice_ui_config(key, config_type)
            options.append(discord.SelectOption(label=f"{key} ({default_data['label']})", value=key, description=f"Actuel: {current.get('emoji')} {current.get('label')}", emoji=current.get('emoji')))
        self.select = Select(placeholder=f"Choisir un élément ({config_type})...", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        item_id = self.select.values[0]
        defaults = VOICE_BUTTONS_DEFAULTS if self.config_type == "button" else VOICE_PRIVACY_DEFAULTS
        item_label = defaults[item_id]['label']
        await interaction.response.send_modal(VoiceUIEditModal(item_id, item_label, self.config_type, self))

class VoiceUIConfigView(View):
    def __init__(self):
        super().__init__(timeout=180)
    @discord.ui.button(label="Configurer les Boutons (Panel)", style=discord.ButtonStyle.primary, emoji="🎛️")
    async def config_buttons(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Quel bouton voulez-vous modifier ?", view=VoiceElementSelectView("button"), ephemeral=True)
    @discord.ui.button(label="Configurer le Menu Privacy", style=discord.ButtonStyle.success, emoji="🔒")
    async def config_privacy(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Quelle option du menu Privacy voulez-vous modifier ?", view=VoiceElementSelectView("privacy"), ephemeral=True)

# --- CLASSES HUB MANAGEMENT ---
class HubSelectView(View):
    def __init__(self, client_ref, action: str):
        super().__init__(timeout=180)
        self.client = client_ref
        self.action = action
        options = []
        for hub_id, hub_data in db.get('voice_hubs', {}).items():
            if isinstance(hub_data, dict) and 'name' in hub_data:
                options.append(discord.SelectOption(label=hub_data['name'], value=str(hub_id)))
        if not options:
            self.select = Select(placeholder=f"Aucun hub à {action}.", options=[discord.SelectOption(label="...", value="no_options_placeholder")], disabled=True)
        else:
            self.select = Select(placeholder=f"Choisir un hub à {action}...", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)
    async def on_select(self, interaction: discord.Interaction):
        if interaction.data['values'][0] == "no_options_placeholder": return await interaction.response.defer()
        hub_id = self.select.values[0]
        if self.action == "modifier": await interaction.response.send_modal(ModifyHubModal(hub_id))
        elif self.action == "supprimer":
            hub_channel = interaction.guild.get_channel(int(hub_id))
            if hub_channel: await hub_channel.delete()
            if hub_id in db['voice_hubs']: del db['voice_hubs'][hub_id]
            save_data(db)
            await interaction.response.send_message("Hub supprimé.", ephemeral=True)

class ModifyHubModal(Modal, title="Modifier un Hub Vocal"):
    def __init__(self, hub_id: str):
        super().__init__()
        self.hub_id = hub_id
        hub_data = db['voice_hubs'].get(hub_id, {})
        self.hub_name = TextInput(label="Nouveau nom", default=hub_data.get('name'))
        self.user_limit = TextInput(label="Nouvelle limite", default=str(hub_data.get('limit', '0')))
        self.category_id_input = TextInput(label="Nouvel ID catégorie (opt)", required=False)
        self.add_item(self.hub_name)
        self.add_item(self.user_limit)
        self.add_item(self.category_id_input)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        hub_data = db['voice_hubs'].get(self.hub_id)
        hub_channel = interaction.guild.get_channel(int(self.hub_id))
        if not hub_data or not hub_channel: return await interaction.followup.send("Hub introuvable.", ephemeral=True)
        try:
            limit = int(self.user_limit.value)
            hub_data['limit'] = limit
            hub_data['name'] = self.hub_name.value
            new_category = hub_channel.category
            if self.category_id_input.value:
                cat_id = int(self.category_id_input.value)
                new_category = interaction.guild.get_channel(cat_id)
            await hub_channel.edit(name=self.hub_name.value, category=new_category)
            save_data(db)
            await interaction.followup.send("Hub mis à jour.", ephemeral=True)
        except Exception as e: await interaction.followup.send(f"Erreur : {e}", ephemeral=True)

class CreateHubModal(Modal, title="Créer un Hub Vocal"):
    def __init__(self, category: discord.CategoryChannel):
        super().__init__()
        self.category = category
        self.hub_name = TextInput(label="Nom du salon Hub", placeholder="Ex: ➕ Créer un salon")
        self.user_limit = TextInput(label="Limite (0=illimité)", default="0")
        self.add_item(self.hub_name)
        self.add_item(self.user_limit)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            limit = int(self.user_limit.value)
            if not (0 <= limit <= 99): raise ValueError()
            new_hub_channel = await self.category.create_voice_channel(name=self.hub_name.value)
            db['voice_hubs'][str(new_hub_channel.id)] = {"name": self.hub_name.value, "limit": limit, "category_id": self.category.id}
            save_data(db)
            await interaction.followup.send(f"Hub '{self.hub_name.value}' créé.", ephemeral=True)
        except Exception as e: await interaction.followup.send(f"Erreur: {e}", ephemeral=True)

class VoiceHubConfigView(View):
    def __init__(self, client_ref):
        super().__init__(timeout=300)
        self.client = client_ref
    @discord.ui.button(label="Créer un Hub", style=discord.ButtonStyle.success, emoji="➕")
    async def create_hub(self, interaction: discord.Interaction, button: Button):
        categories = [c for c in interaction.guild.categories]
        if not categories: return await interaction.response.send_message("Aucune catégorie trouvée.", ephemeral=True)
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in categories]
        select = Select(placeholder="Choisissez une catégorie...", options=options)
        async def select_callback(inter: discord.Interaction):
            cat = inter.guild.get_channel(int(inter.data['values'][0]))
            await inter.response.send_modal(CreateHubModal(cat))
        select.callback = select_callback
        view = View().add_item(select)
        await interaction.response.send_message("Dans quelle catégorie ?", view=view, ephemeral=True)
    @discord.ui.button(label="Modifier un Hub", style=discord.ButtonStyle.primary, emoji="✏️")
    async def modify_hub(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Choisissez un hub :", view=HubSelectView(self.client, "modifier"), ephemeral=True)
    @discord.ui.button(label="Supprimer un Hub", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_hub(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Choisissez un hub :", view=HubSelectView(self.client, "supprimer"), ephemeral=True)

class VoiceInterfaceConfigModal(Modal, title="Design Interface Vocale (JSON)"):
    json_input = TextInput(label="JSON de l'Embed Interface", style=discord.TextStyle.paragraph, placeholder='{"title": "Contrôle Vocal", "description": "..."}', required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = json.loads(self.json_input.value)
            data = sanitize_voice_json(data)
            db.setdefault('settings', {})['voice_interface_json'] = json.dumps(data)
            save_data(db)
            await interaction.response.send_message("✅ Design de l'interface vocale mis à jour !", ephemeral=True)
        except json.JSONDecodeError: await interaction.response.send_message("❌ JSON Invalide.", ephemeral=True)

class VoiceErrorConfigModal(Modal, title="Design Erreur Vocale (JSON)"):
    json_input = TextInput(label="JSON Message Erreur", style=discord.TextStyle.paragraph, placeholder='{"title": "Erreur", "description": "Rejoignez un salon..."}', required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = json.loads(self.json_input.value)
            data = sanitize_voice_json(data)
            db.setdefault('settings', {})['voice_error_json'] = json.dumps(data)
            save_data(db)
            await interaction.response.send_message("✅ Design du message d'erreur mis à jour !", ephemeral=True)
        except json.JSONDecodeError: await interaction.response.send_message("❌ JSON Invalide.", ephemeral=True)

# ==================================================================================================
# 17. SYSTÈME D'AIDE (INTERACTIF)
# ==================================================================================================

HELP_ADMIN_IMAGES = [""] 
HELP_PLAYER_IMAGES = [""]

class HelpView(View):
    def __init__(self, embeds, user):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.current_page = 0
        self.user = user
        self.add_buttons()

    def add_buttons(self):
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
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == len(self.embeds) - 1
        await interaction.response.edit_message(embed=embed, view=self)

async def send_player_help_logic(interaction: discord.Interaction):
    if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
    embeds = []
    images = [url for url in HELP_PLAYER_IMAGES if url.strip()]
    if images:
        for i, img_url in enumerate(images):
            embed = discord.Embed(title=f"🎮 Aide Joueur - Poxel (Page {i+1}/{len(images)})", color=NEON_GREEN)
            embed.set_image(url=img_url)
            embeds.append(embed)
    else:
        embed = discord.Embed(title="🎮 Commandes & Infos pour les Joueurs", description="Voici les fonctionnalités que tu peux utiliser !", color=NEON_GREEN)
        embed.add_field(name="❤️ `/vies`", value="Affiche ta barre de vie, tes infractions et quand elles expirent.", inline=False)
        embed.add_field(name="📈 `/rank`", value="Affiche ta carte de niveau et tes classements.", inline=False)
        embed.add_field(name="🎤 Salons Vocaux", value="Rejoins un salon vocal `➕ Créer un salon` pour avoir ton propre canal.", inline=False)
        embed.add_field(name="🎟️ Support", value="Utilise les salons de tickets/reports pour contacter le staff.", inline=False)
        embeds.append(embed)
    view = HelpView(embeds, interaction.user)
    await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)

async def send_admin_help_logic(interaction: discord.Interaction):
    if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
    embeds = []
    images = [url for url in HELP_ADMIN_IMAGES if url.strip()]
    if images:
        for i, img_url in enumerate(images):
            embed = discord.Embed(title=f"📚 Aide Modération - Poxel (Page {i+1}/{len(images)})", color=NEON_BLUE)
            embed.set_image(url=img_url)
            embeds.append(embed)
    else:
        embed1 = discord.Embed(title="📚 Aide Admin (1/1) - Modération & Config", color=NEON_BLUE)
        embed1.add_field(name="🛡️ **Modération**", value="`/ban`, `/tempban`, `/kick`, `/mute`, `/unmute`, `/warn`, `/unban`", inline=False)
        embed1.add_field(name="⚙️ **Configuration**", value="`/config`, `/ticket`, `/report`, `/signalement`, `/suggestion`", inline=False)
        embed1.add_field(name="🎥 **Ciné Pixel**", value="`/cineconfig set_channel`, `/news_series`, `/news_movies`", inline=False)
        embeds.append(embed1)
    view = HelpView(embeds, interaction.user)
    await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)


# ==================================================================================================
# 18. INTERFACES DE CONFIGURATION GÉNÉRALE (SETTINGS)
# ==================================================================================================

# --- MODALES DE CONFIGURATION GÉNÉRALE ---

class PurgeSettingsModal(Modal, title="Configurer Purge d'Infractions"):
    def __init__(self):
        super().__init__()
        self.duration_input = TextInput(label="Durée avant purge (jours)", default=str(db['settings'].get("purge_duration_days", 180)))
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            days = int(self.duration_input.value)
            if days <= 0: return await interaction.followup.send("La durée doit être d'au moins 1 jour.", ephemeral=True)
            db['settings']['purge_duration_days'] = days
            save_data(db)
            await interaction.followup.send(f"✅ Purge automatique réglée sur **{days} jours**.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Nombre invalide.", ephemeral=True)

class LifeEmojiConfigModal(Modal, title="Configurer les Emojis de Vie"):
    def __init__(self):
        super().__init__()
        self.full_input = TextInput(label="Cœur Plein", default=db['settings'].get("life_emoji_full", "❤️"))
        self.empty_input = TextInput(label="Cœur Vide", default=db['settings'].get("life_emoji_empty", "🖤"))
        self.boost_input = TextInput(label="Cœur Boost (10e vie)", default=db['settings'].get("life_emoji_boost", "💛"))
        self.add_item(self.full_input)
        self.add_item(self.empty_input)
        self.add_item(self.boost_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db['settings']['life_emoji_full'] = self.full_input.value.strip()
        db['settings']['life_emoji_empty'] = self.empty_input.value.strip()
        db['settings']['life_emoji_boost'] = self.boost_input.value.strip()
        save_data(db)
        await interaction.followup.send("✅ Emojis de vie mis à jour !", ephemeral=True)

class SetLogChannelModal(Modal, title="Configurer Salon Logs Modération"):
    channel_id_input = TextInput(label="ID du Salon de Logs", placeholder="Vide pour désactiver", required=False)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        val = self.channel_id_input.value.strip()
        if val:
            try:
                cid = int(val)
                db['settings']['auto_mod_log_channel_id'] = cid
                save_data(db)
                await interaction.followup.send(f"✅ Salon de logs défini (ID: {cid}).", ephemeral=True)
            except: await interaction.followup.send("❌ ID Invalide.", ephemeral=True)
        else:
            db['settings']['auto_mod_log_channel_id'] = None
            save_data(db)
            await interaction.followup.send("✅ Logs de modération désactivés.", ephemeral=True)

# --- VUES DE CONFIGURATION ---

class GeneralSettingsView(View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Emojis de Vie", style=discord.ButtonStyle.secondary, emoji="❤️", row=0)
    async def set_life_emojis(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(LifeEmojiConfigModal())

    @discord.ui.button(label="Durée Purge", style=discord.ButtonStyle.primary, emoji="🗓️", row=0)
    async def set_purge_duration(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PurgeSettingsModal())

    @discord.ui.button(label="Salon Logs Mod", style=discord.ButtonStyle.secondary, emoji="📜", row=0)
    async def set_log_channel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(SetLogChannelModal())

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=1)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Panneau de configuration principal:", view=MainConfigView(interaction.client))

class CensorConfigView(View):
    def __init__(self):
        super().__init__(timeout=300)
        self.update_button()

    def update_button(self):
        for i in self.children[:]:
            if getattr(i, 'custom_id', '') == 'tgl_censor': self.remove_item(i)
        enabled = db['settings'].get("censor_enabled", True)
        btn = Button(label=f"Censure: {'ON' if enabled else 'OFF'}", style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger, custom_id="tgl_censor", row=0)
        btn.callback = self.toggle
        self.add_item(btn)

    async def toggle(self, interaction: discord.Interaction):
        db['settings']["censor_enabled"] = not db['settings'].get("censor_enabled", True)
        save_data(db)
        self.update_button()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Ajouter Mot", style=discord.ButtonStyle.primary, emoji="➕", row=1)
    async def add_w(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(self.WordModal("add"))

    @discord.ui.button(label="Retirer Mot", style=discord.ButtonStyle.secondary, emoji="➖", row=1)
    async def rem_w(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(self.WordModal("remove"))

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=2)
    async def back(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Panneau principal:", view=MainConfigView(interaction.client))

    class WordModal(Modal):
        def __init__(self, action):
            super().__init__(title=f"{action.capitalize()} Mot")
            self.action = action
            self.w = TextInput(label="Mot", required=True)
            self.add_item(self.w)
        async def on_submit(self, interaction: discord.Interaction):
            w = self.w.value.lower().strip()
            l = db['settings'].setdefault('censored_words', [])
            if self.action == "add" and w not in l: l.append(w)
            elif self.action == "remove" and w in l: l.remove(w)
            save_data(db)
            await interaction.response.send_message(f"✅ Liste mise à jour.", ephemeral=True)

class MainConfigView(View):
    def __init__(self, client_ref):
        super().__init__(timeout=300)
        self.client = client_ref

    @discord.ui.button(label="Salons Vocaux", style=discord.ButtonStyle.primary, emoji="🎤", row=0)
    async def voice_config(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Configuration Vocale :", view=VoiceHubConfigView(self.client))

    @discord.ui.button(label="Censure", style=discord.ButtonStyle.secondary, emoji="🤬", row=0)
    async def censor(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="📝 Censure :", view=CensorConfigView())

    @discord.ui.button(label="Paramètres Généraux", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def general(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="⚙️ Général :", view=GeneralSettingsView())

# ==================================================================================================
# 19. PANELS PERMANENTS (MODÉRATION, CONFIG, JOUEURS)
# ==================================================================================================

# --- MODALES D'ACTIONS RAPIDES (Liées aux boutons des panels) ---

class ModReasonModal(Modal):
    def __init__(self, action: str, target: discord.User):
        super().__init__(title=f"Action: {action.upper()}")
        self.action = action
        self.target = target
        self.reason = TextInput(label="Raison", required=True)
        self.add_item(self.reason)
        if action in ["tempban", "mute"]:
            self.duration = TextInput(label="Durée (ex: 1h, 30m)", required=True)
            self.add_item(self.duration)
        if action in ["ban", "kick", "mute", "warn", "tempban"]:
            self.lives = TextInput(label="Vies (Vide=Défaut)", required=False)
            self.add_item(self.lives)

    async def on_submit(self, interaction: discord.Interaction):
        reason_text = self.reason.value
        points = int(self.lives.value) if hasattr(self, 'lives') and self.lives.value.isdigit() else None
        
        # Appel aux logiques définies dans la Partie 3
        if self.action == "ban": await poxel_ban_logic(interaction, self.target, reason_text, points)
        elif self.action == "kick": await poxel_kick_logic(interaction, self.target, reason_text, points)
        elif self.action == "warn": await poxel_warn_logic(interaction, self.target, reason_text, points)
        elif self.action == "unban": await poxel_unban_logic(interaction, str(self.target.id), reason_text)
        elif self.action == "tempban": await poxel_tempban_logic(interaction, self.target, self.duration.value, reason_text, points)
        elif self.action == "mute": await poxel_mute_logic(interaction, self.target, self.duration.value, reason_text, points)
        elif self.action == "unmute": await poxel_unmute_logic(interaction, self.target.id)
        elif self.action == "clear_all": await poxel_clear_infs_logic(interaction, self.target, reason_text)

class ModUserSelect(discord.ui.UserSelect):
    def __init__(self, action):
        self.action = action
        super().__init__(placeholder="Sélectionner le membre...", min_values=1, max_values=1)
    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        if self.action == "infractions":
            await interaction.response.defer(ephemeral=True)
            infs = db['infractions'].get(str(target.id), [])
            desc = "\n".join([f"• {i['type'].upper()}: {i['reason']}" for i in infs]) if infs else "Aucune infraction."
            await interaction.followup.send(embed=discord.Embed(title=f"Dossier {target}", description=desc, color=NEON_PURPLE), ephemeral=True)
        else:
            await interaction.response.send_modal(ModReasonModal(self.action, target))

class ModUserSelectView(View):
    def __init__(self, action):
        super().__init__(timeout=60)
        self.add_item(ModUserSelect(action))

# --- VUES DES PANELS ---

class ModerationPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def check_perm(self, interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Accès refusé.", ephemeral=True)
            return False
        return True

    async def open_sel(self, interaction, action):
        if await self.check_perm(interaction):
            await interaction.response.send_message(f"Action: **{action.upper()}**", view=ModUserSelectView(action), ephemeral=True)

    @discord.ui.button(label="Ban", emoji="🔨", style=discord.ButtonStyle.secondary, custom_id="mod_ban", row=0)
    async def ban(self, interaction: discord.Interaction, button: Button): await self.open_sel(interaction, "ban")
    
    @discord.ui.button(label="Kick", emoji="🦵", style=discord.ButtonStyle.secondary, custom_id="mod_kick", row=0)
    async def kick(self, interaction: discord.Interaction, button: Button): await self.open_sel(interaction, "kick")

    @discord.ui.button(label="Mute", emoji="🔇", style=discord.ButtonStyle.secondary, custom_id="mod_mute", row=0)
    async def mute(self, interaction: discord.Interaction, button: Button): await self.open_sel(interaction, "mute")

    @discord.ui.button(label="Warn", emoji="⚠️", style=discord.ButtonStyle.secondary, custom_id="mod_warn", row=0)
    async def warn(self, interaction: discord.Interaction, button: Button): await self.open_sel(interaction, "warn")

    @discord.ui.button(label="Tempban", emoji="⏳", style=discord.ButtonStyle.secondary, custom_id="mod_tempban", row=1)
    async def tempban(self, interaction: discord.Interaction, button: Button): await self.open_sel(interaction, "tempban")

    @discord.ui.button(label="Unban", emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="mod_unban", row=1)
    async def unban(self, interaction: discord.Interaction, button: Button): await self.open_sel(interaction, "unban")

    @discord.ui.button(label="Unmute", emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="mod_unmute", row=1)
    async def unmute(self, interaction: discord.Interaction, button: Button): await self.open_sel(interaction, "unmute")

    @discord.ui.button(label="Dossier", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="mod_infs", row=2)
    async def infs(self, interaction: discord.Interaction, button: Button): await self.open_sel(interaction, "infractions")

    @discord.ui.button(label="Reset", emoji="♻️", style=discord.ButtonStyle.secondary, custom_id="mod_clear_all", row=2)
    async def clear_all(self, interaction: discord.Interaction, button: Button): await self.open_sel(interaction, "clear_all")

class PlayerPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Mes Infractions", emoji="🚨", style=discord.ButtonStyle.secondary, custom_id="play_infs", row=0)
    async def my_infs(self, interaction: discord.Interaction, button: Button):
        infs = db['infractions'].get(str(interaction.user.id), [])
        desc = "\n".join([f"• {i['type'].upper()}: {i['reason']}" for i in infs]) if infs else "Vous êtes clean !"
        await interaction.response.send_message(embed=discord.Embed(title="Vos Infractions", description=desc, color=NEON_PURPLE), ephemeral=True)

    @discord.ui.button(label="Mes Vies", emoji="❤️", style=discord.ButtonStyle.secondary, custom_id="play_lives", row=0)
    async def my_lives(self, interaction: discord.Interaction, button: Button):
        lives = display_lives(interaction.user)
        await interaction.response.send_message(embed=discord.Embed(title="Vos Vies", description=lives, color=NEON_PURPLE), ephemeral=True)

    @discord.ui.button(label="Aide", emoji="📚", style=discord.ButtonStyle.secondary, custom_id="play_help", row=0)
    async def help_p(self, interaction: discord.Interaction, button: Button):
        await send_player_help_logic(interaction)

    @discord.ui.button(label="Mon Vocal", emoji="🎤", style=discord.ButtonStyle.secondary, custom_id="play_vocal", row=1)
    async def my_vocal(self, interaction: discord.Interaction, button: Button):
        view = VoiceDashboardView()
        vc, _ = await view.get_active_channel(interaction)
        if vc:
            embed = discord.Embed(title="🎛️ Contrôle Vocal", description=f"Salon: **{vc.name}**", color=NEON_BLUE)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ConfigPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Interface Design", emoji="🎨", style=discord.ButtonStyle.secondary, custom_id="conf_ui_design", row=0)
    async def design_ui(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator: return
        await interaction.response.send_modal(VoiceInterfaceConfigModal())

    @discord.ui.button(label="Interface Erreur", emoji="⚠️", style=discord.ButtonStyle.secondary, custom_id="conf_err_design", row=0)
    async def design_err(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator: return
        await interaction.response.send_modal(VoiceErrorConfigModal())


# ==================================================================================================
# 20. UTILITAIRES JSON & EMBED
# ==================================================================================================

def sanitize_embed_json(data):
    """Nettoie récursivement le JSON pour supprimer les clés d'URL vides ou invalides."""
    if isinstance(data, dict):
        url_keys = ['url', 'icon_url', 'proxy_icon_url']
        obj_keys = ['image', 'thumbnail', 'author', 'footer', 'video', 'provider']
        keys_to_remove = []
        for k, v in data.items():
            if k in url_keys:
                if not isinstance(v, str) or not v.strip() or not v.startswith(('http://', 'https://')):
                    keys_to_remove.append(k)
            elif k in obj_keys:
                if isinstance(v, dict):
                    sanitize_embed_json(v)
                    if not v: keys_to_remove.append(k)
            elif isinstance(v, (dict, list)):
                sanitize_embed_json(v)
        for k in keys_to_remove: del data[k]
    elif isinstance(data, list):
        for item in data: sanitize_embed_json(item)
    return data

# ==================================================================================================
# 21. LOGIQUE DE CONFIGURATION DES PANELS (DESIGN & BOUTONS)
# ==================================================================================================

class PanelDesignModal(Modal):
    def __init__(self, panel_type):
        super().__init__(title=f"Design: {panel_type.capitalize()}")
        self.panel_type = panel_type
        self.json_input = TextInput(label="JSON Embed", style=discord.TextStyle.paragraph, placeholder='{"title": "..."}', required=True)
        self.add_item(self.json_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            json.loads(self.json_input.value)
            db.setdefault('settings', {})[f'panel_{self.panel_type}_json'] = self.json_input.value
            save_data(db)
            await interaction.response.send_message(f"✅ Design **{self.panel_type}** sauvegardé.", ephemeral=True)
        except: await interaction.response.send_message("❌ JSON Invalide.", ephemeral=True)

class PanelButtonEditModal(Modal):
    def __init__(self, btn_id, panel_type):
        super().__init__(title="Éditer Bouton")
        self.btn_id = btn_id
        self.panel_type = panel_type
        # Récupérer la config actuelle ou défaut via une fonction helper simulée ici
        # (Dans la fusion, get_panel_button_config doit être accessible ou on accède direct à la DB)
        saved = db.get('settings', {}).get('panel_ui', {}).get(panel_type, {}).get(btn_id, {})
        self.emoji_inp = TextInput(label="Emoji", default=saved.get('emoji', ''), max_length=5, required=True)
        self.label_inp = TextInput(label="Texte (Vide = caché)", default=saved.get('label', ''), required=False)
        self.add_item(self.emoji_inp)
        self.add_item(self.label_inp)

    async def on_submit(self, interaction: discord.Interaction):
        db.setdefault('settings', {}).setdefault('panel_ui', {}).setdefault(self.panel_type, {})[self.btn_id] = {
            "emoji": self.emoji_inp.value.strip(),
            "label": self.label_inp.value.strip()
        }
        save_data(db)
        await interaction.response.send_message("✅ Bouton mis à jour ! (Re-postez le panel pour voir les changements)", ephemeral=True)

class PanelConfigSelectView(View):
    def __init__(self, panel_type):
        super().__init__()
        self.panel_type = panel_type
        options = []
        # On définit les clés basiques pour l'édition (mapping simplifié pour l'exemple)
        keys = []
        if panel_type == "mod": keys = ["mod_ban", "mod_kick", "mod_mute", "mod_warn", "mod_tempban", "mod_unban", "mod_unmute", "mod_clear", "mod_infs", "mod_clear_all"]
        elif panel_type == "conf": keys = ["conf_mc_toggle", "conf_mc_setup", "conf_ui_design", "conf_err_design"]
        elif panel_type == "player": keys = ["play_infs", "play_lives", "play_help", "play_vocal"]
        
        for k in keys: options.append(discord.SelectOption(label=k, value=k))
        
        self.sel = Select(placeholder="Choisir un bouton...", options=options[:25])
        self.sel.callback = self.cb
        self.add_item(self.sel)
        
    async def cb(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PanelButtonEditModal(self.sel.values[0], self.panel_type))

class PanelSelectionView(View):
    def __init__(self, mode): # mode = 'design' or 'buttons'
        super().__init__(timeout=60)
        self.mode = mode
        options = [
            discord.SelectOption(label="Modération", value="mod", emoji="🛡️"),
            discord.SelectOption(label="Configuration", value="conf", emoji="⚙️"),
            discord.SelectOption(label="Joueurs", value="player", emoji="🎮")
        ]
        self.select = Select(placeholder="Choisir le panel...", options=options)
        self.select.callback = self.callback
        self.add_item(self.select)

    async def callback(self, interaction: discord.Interaction):
        ptype = self.select.values[0]
        if self.mode == 'design': await interaction.response.send_modal(PanelDesignModal(ptype))
        elif self.mode == 'buttons': await interaction.response.send_message(f"Configuration boutons **{ptype}** :", view=PanelConfigSelectView(ptype), ephemeral=True)

# ==================================================================================================
# 22. SYSTÈMES DE TICKETS & INSTALLATION
# ==================================================================================================

class GenericTicketView(View):
    def __init__(self, system_type, label, emoji):
        super().__init__(timeout=None)
        self.system_type = system_type
        self.add_item(Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary, custom_id=f"gen_ticket_{system_type}"))

class SystemSetupView(View):
    def __init__(self, system_type: str):
        super().__init__(timeout=60)
        self.system_type = system_type
        self.add_item(discord.ui.ChannelSelect(channel_types=[discord.ChannelType.category], placeholder="Choisir la catégorie d'installation..."))
        self.children[0].callback = self.callback

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        category = self.children[0].values[0]
        configs = {
            "ticket": {"name": "🎫-tickets", "title": "Support Ticket", "desc": "Cliquez ci-dessous pour ouvrir un ticket.", "btn": "Ouvrir un Ticket", "emoji": "📩"},
            "report": {"name": "🚨-report", "title": "Signalement", "desc": "Signalez un comportement inapproprié.", "btn": "Faire un Signalement", "emoji": "⚠️"},
            "signalement": {"name": "🛑-plaintes", "title": "Plaintes", "desc": "Déposez une plainte formelle.", "btn": "Déposer une Plainte", "emoji": "📝"},
            "suggestion": {"name": "💡-suggestions", "title": "Boîte à Idées", "desc": "Proposez vos améliorations !", "btn": "Faire une Suggestion", "emoji": "💡"}
        }
        conf = configs.get(self.system_type)
        if not conf: return await interaction.followup.send("Type de système inconnu.", ephemeral=True)

        try:
            channel = await interaction.guild.create_text_channel(name=conf['name'], category=category)
            custom_json = db.get('default_embeds', {}).get(self.system_type)
            if custom_json:
                try: embed = discord.Embed.from_dict(json.loads(custom_json))
                except: embed = discord.Embed(title=conf['title'], description=conf['desc'], color=NEON_BLUE)
            else:
                embed = discord.Embed(title=conf['title'], description=conf['desc'], color=NEON_BLUE)
            
            view = GenericTicketView(self.system_type, conf['btn'], conf['emoji'])
            await channel.send(embed=embed, view=view)
            db['settings'][f'{self.system_type}_config'] = {"channel_id": channel.id, "category_id": category.id}
            save_data(db)
            await interaction.followup.send(f"✅ Système **{self.system_type}** installé dans {channel.mention}.", ephemeral=True)
        except Exception as e: await interaction.followup.send(f"Erreur : {e}", ephemeral=True)

class TicketsSupportView(View):
    def __init__(self):
        super().__init__(timeout=180)
    @discord.ui.button(label="Panel Ticket", style=discord.ButtonStyle.secondary, emoji="🎟️", row=0)
    async def ticket_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Configuration Ticket :", view=SystemSetupView("ticket"), ephemeral=True)
    @discord.ui.button(label="Panel Report", style=discord.ButtonStyle.secondary, emoji="🚨", row=0)
    async def report_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Configuration Report :", view=SystemSetupView("report"), ephemeral=True)
    @discord.ui.button(label="Panel Signalement", style=discord.ButtonStyle.secondary, emoji="🎯", row=1)
    async def signalement_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Configuration Signalement :", view=SystemSetupView("signalement"), ephemeral=True)
    @discord.ui.button(label="Panel Suggestion", style=discord.ButtonStyle.secondary, emoji="💡", row=1)
    async def suggestion_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Configuration Suggestion :", view=SystemSetupView("suggestion"), ephemeral=True)

# ==================================================================================================
# 23. EMBED BUILDER
# ==================================================================================================

class EmbedJSONModal(Modal, title="Importer Embed depuis JSON"):
    json_data = TextInput(label="Code JSON (Discohook)", style=discord.TextStyle.paragraph, placeholder='{"title": "...", "description": "..."}', required=True)
    content_input = TextInput(label="Texte hors embed (@everyone...)", placeholder="Message normal au dessus de l'embed", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        try:
            data = json.loads(self.json_data.value)
            embed_data = data['embeds'][0] if 'embeds' in data and isinstance(data['embeds'], list) and len(data['embeds']) > 0 else (data if 'title' in data or 'description' in data else {})
            content = self.content_input.value.strip() or (data.get('content') if not self.content_input.value.strip() else "")
            
            db['embed_builders'][user_id] = {"type": "json", "content": content, "data": embed_data, "reactions": db['embed_builders'].get(user_id, {}).get("reactions", [])}
            save_data(db)
            await interaction.followup.send("✅ JSON importé.", ephemeral=True)
            await interaction.message.edit(embed=EmbedBuilderView.generate_preview(user_id), view=EmbedBuilderView(user_id))
        except: await interaction.followup.send("❌ JSON Invalide.", ephemeral=True)

class EmbedSimpleModal(Modal, title="Créateur Simple"):
    title_input = TextInput(label="Titre")
    desc_input = TextInput(label="Description", style=discord.TextStyle.paragraph)
    color_input = TextInput(label="Couleur (Hex)", default="#6441a5")
    content_input = TextInput(label="Texte hors embed", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        try: color_val = int(self.color_input.value.replace("#", ""), 16)
        except: color_val = NEON_PURPLE
        embed_data = {"title": self.title_input.value, "description": self.desc_input.value, "color": color_val}
        db['embed_builders'][user_id] = {"type": "simple", "content": self.content_input.value.strip(), "data": embed_data, "reactions": db['embed_builders'].get(user_id, {}).get("reactions", [])}
        save_data(db)
        await interaction.followup.send("✅ Données mises à jour.", ephemeral=True)
        await interaction.message.edit(embed=EmbedBuilderView.generate_preview(user_id), view=EmbedBuilderView(user_id))

class ReactionRoleSelectView(View):
    def __init__(self, user_id, text, emoji, view_ref):
        super().__init__(timeout=180)
        self.user_id = user_id; self.text = text; self.emoji = emoji; self.view_ref = view_ref
        self.role_select = discord.ui.RoleSelect(placeholder="Choisissez le rôle...")
        self.role_select.callback = self.cb
        self.add_item(self.role_select)
    async def cb(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        role = self.role_select.values[0]
        user_id_str = str(self.user_id)
        builder = db['embed_builders'].get(user_id_str)
        if not builder: return await interaction.followup.send("Session expirée.", ephemeral=True)
        builder.setdefault('reactions', []).append({"text": self.text, "emoji": self.emoji, "role_id": role.id})
        save_data(db)
        await interaction.followup.send(f"✅ Rôle {role.mention} lié à {self.emoji}.", ephemeral=True)
        await interaction.edit_original_response(content="Menu Principal", embed=EmbedBuilderView.generate_preview(user_id_str), view=EmbedBuilderView(user_id_str))

class ReactionAddModal(Modal, title="Ajouter une Réaction"):
    def __init__(self, view_ref):
        super().__init__(); self.view_ref = view_ref
    emoji_input = TextInput(label="Emoji", placeholder="👻")
    text_input = TextInput(label="Description", placeholder="Cliquez...", required=False)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Choisissez le rôle :", view=ReactionRoleSelectView(interaction.user.id, self.text_input.value, self.emoji_input.value.strip(), self.view_ref), ephemeral=True)

class ChannelPickView(View):
    def __init__(self, user_id):
        super().__init__(timeout=60); self.user_id = str(user_id)
        self.channel_select = discord.ui.ChannelSelect(channel_types=[discord.ChannelType.text, discord.ChannelType.news])
        self.channel_select.callback = self.on_select
        self.add_item(self.channel_select)
    async def on_select(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = self.channel_select.values[0]
        builder = db['embed_builders'].get(self.user_id)
        if not builder: return await interaction.followup.send("Données introuvables.", ephemeral=True)
        try:
            embed_dict = sanitize_embed_json(builder['data'])
            embed = discord.Embed.from_dict(embed_dict)
            if builder.get('reactions'):
                desc_add = "\n\n" + "\n".join([f"{r['emoji']} : {r['text']}" for r in builder['reactions'] if r['text']])
                if len(desc_add) > 2: embed.description = (embed.description or "") + desc_add
            
            message = await channel.send(content=builder.get('content') or None, embed=embed)
            if builder.get('reactions'):
                reaction_map = {}
                for react in builder['reactions']:
                    try:
                        await message.add_reaction(react['emoji'])
                        reaction_map[react['emoji']] = react['role_id']
                    except: pass
                db.setdefault('reaction_role_messages', {})[str(message.id)] = reaction_map
                save_data(db)
            await interaction.followup.send(f"✅ Publié dans {channel.mention} !", ephemeral=True)
            del db['embed_builders'][self.user_id]
            save_data(db)
        except Exception as e: await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

class EmbedBuilderView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None); self.user_id = str(user_id)
    
    @staticmethod
    def generate_preview(user_id):
        builder = db['embed_builders'].get(str(user_id))
        if not builder: return discord.Embed(title="Aucun brouillon", description="Commencez par importer un JSON.", color=discord.Color.light_grey())
        try:
            data = builder['data'].copy()
            embed = discord.Embed.from_dict(data)
            embed.set_footer(text="Prévisualisation")
            if builder.get('reactions'):
                val = "\n".join([f"{r['emoji']} ➡️ <@&{r['role_id']}>" for r in builder['reactions']])
                embed.add_field(name="Rôles-Réactions", value=val, inline=False)
            return embed
        except: return discord.Embed(title="Erreur Preview", color=discord.Color.red())

    @discord.ui.button(label="JSON", style=discord.ButtonStyle.secondary, emoji="📥", row=0)
    async def imp_json(self, interaction: discord.Interaction, button: Button): await interaction.response.send_modal(EmbedJSONModal())
    @discord.ui.button(label="Simple", style=discord.ButtonStyle.secondary, emoji="✏️", row=0)
    async def ed_simple(self, interaction: discord.Interaction, button: Button): await interaction.response.send_modal(EmbedSimpleModal())
    @discord.ui.button(label="Réaction", style=discord.ButtonStyle.primary, emoji="🎭", row=1)
    async def add_r(self, interaction: discord.Interaction, button: Button): await interaction.response.send_modal(ReactionAddModal(self))
    @discord.ui.button(label="Rafraîchir", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def refresh(self, interaction: discord.Interaction, button: Button): await interaction.response.edit_message(embed=self.generate_preview(interaction.user.id), view=self)
    @discord.ui.button(label="Publier", style=discord.ButtonStyle.success, emoji="✅", row=2)
    async def pub(self, interaction: discord.Interaction, button: Button): await interaction.response.send_message("Destination :", view=ChannelPickView(interaction.user.id), ephemeral=True)

class EmbedPanelPermanentView(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Ouvrir Créateur", style=discord.ButtonStyle.primary, emoji="🛠️", custom_id="open_embed_builder")
    async def open(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        if user_id not in db['embed_builders']: db['embed_builders'][user_id] = {}
        await interaction.response.send_message(embed=EmbedBuilderView.generate_preview(user_id), view=EmbedBuilderView(user_id), ephemeral=True)

# --- COMMANDES DE DÉPLOIEMENT ---

panel_group = app_commands.Group(name="setup_panel", description="Installer les panels permanents.", default_permissions=discord.Permissions(administrator=True))
panel_conf_group = app_commands.Group(name="panel_config", description="Configurer les boutons.", default_permissions=discord.Permissions(administrator=True))
embed_group = app_commands.Group(name="embed", description="Outils d'embed.", default_permissions=discord.Permissions(administrator=True))

class AdminHelpPanelView(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Aide Admin", style=discord.ButtonStyle.primary, emoji="📚", custom_id="admin_help_open")
    async def open(self, interaction: discord.Interaction, button: Button): await send_admin_help_logic(interaction)

@panel_group.command(name="moderation", description="Poste le panel de modération.")
async def setup_mod_panel(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="🛡️ Modération", color=DARK_RED), view=ModerationPanelView())
    await interaction.response.send_message("✅ Panel Modération posté !", ephemeral=True)

@panel_group.command(name="config", description="Poste le panel de configuration.")
async def setup_conf_panel(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="⚙️ Configuration", color=NEON_BLUE), view=ConfigPanelView())
    await interaction.response.send_message("✅ Panel Config posté !", ephemeral=True)

@panel_group.command(name="players", description="Poste le panel joueurs.")
async def setup_play_panel(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="🎮 Espace Joueurs", color=NEON_GREEN), view=PlayerPanelView())
    await interaction.response.send_message("✅ Panel Joueurs posté !", ephemeral=True)

@panel_group.command(name="admin_help", description="Poste le panel d'aide admin.")
async def setup_admin_help(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="📚 Aide Admin", color=NEON_PURPLE), view=AdminHelpPanelView())
    await interaction.response.send_message("✅ Panel Aide Admin posté !", ephemeral=True)

@embed_group.command(name="setup_panel", description="Poste le panel de création d'embed.")
async def embed_setup(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="🛠️ Créateur d'Embeds", description="Cliquez pour ouvrir l'outil.", color=NEON_BLUE), view=EmbedPanelPermanentView())
    await interaction.response.send_message("✅ Panel Embed posté !", ephemeral=True)

@app_commands.command(name="ticket", description="Installer le panel Ticket.")
@app_commands.default_permissions(administrator=True)
async def ticket_cmd(interaction: discord.Interaction): await interaction.response.send_message("Config Ticket :", view=SystemSetupView("ticket"), ephemeral=True)

@app_commands.command(name="report", description="Installer le panel Report.")
@app_commands.default_permissions(administrator=True)
async def report_cmd(interaction: discord.Interaction): await interaction.response.send_message("Config Report :", view=SystemSetupView("report"), ephemeral=True)

@app_commands.command(name="annonce", description="Faire une annonce.")
@app_commands.default_permissions(administrator=True)
async def annonce(interaction: discord.Interaction, titre: str, message: str, image: str = None):
    embed = discord.Embed(title=titre, description=message, color=RETRO_ORANGE)
    if image: embed.set_image(url=image)
    embed.set_footer(text=f"Par {interaction.user.display_name}")
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Annonce publiée !", ephemeral=True)


# ==================================================================================================
# 24. CLASSE CLIENT DISCORD (FUSIONNÉE)
# ==================================================================================================

class PoxelClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.persistent_views_added = False
        self.last_member_count_update = {}

    async def setup_hook(self):
        """Enregistrement des commandes et synchronisation."""
        # Ajout des groupes de commandes
        self.tree.add_command(birthday_group)
        self.tree.add_command(birthday_admin_group)
        self.tree.add_command(notif_group)
        self.tree.add_command(freegames_group)
        self.tree.add_command(cineconfig_group)
        self.tree.add_command(team_group)
        self.tree.add_command(avatar_group)
        self.tree.add_command(topweek_admin_group)
        self.tree.add_command(adminxp_group)
        self.tree.add_command(voice_config_group)
        self.tree.add_command(panel_group)
        self.tree.add_command(panel_conf_group)
        self.tree.add_command(embed_group)
        self.tree.add_command(membercount_group)

        # Ajout des commandes isolées (définies globalement avec @app_commands.command)
        # Économie / Utilitaires
        self.tree.add_command(ping)
        self.tree.add_command(rank)
        self.tree.add_command(birthdaylist)
        self.tree.add_command(nextbirthday)
        self.tree.add_command(free)
        self.tree.add_command(cmd_news_series)
        self.tree.add_command(cmd_news_anime)
        self.tree.add_command(cmd_news_cartoons)
        self.tree.add_command(cmd_news_movies)
        self.tree.add_command(cmd_episodes_series)
        self.tree.add_command(cmd_episodes_anime)
        self.tree.add_command(cmd_episodes_cartoons)
        self.tree.add_command(admin_test_news)
        self.tree.add_command(config_listener)
        self.tree.add_command(reset_listener)
        self.tree.add_command(rewards)
        self.tree.add_command(admin_sync)
        self.tree.add_command(teamlist)
        self.tree.add_command(poxel_help) # poxel_help admin
        self.tree.add_command(help_joueur) # poxel_help_joueur
        self.tree.add_command(avatar_config_panel)

        # Modération
        self.tree.add_command(ban)
        self.tree.add_command(tempban)
        self.tree.add_command(kick)
        self.tree.add_command(mute)
        self.tree.add_command(unmute)
        self.tree.add_command(warn)
        self.tree.add_command(unban)
        self.tree.add_command(infractions)
        self.tree.add_command(clear_all_infractions)
        self.tree.add_command(clear)
        self.tree.add_command(slowmode)
        self.tree.add_command(vies)
        self.tree.add_command(config) # Main config panel
        self.tree.add_command(vocal_cmd)
        self.tree.add_command(annonce)
        self.tree.add_command(ticket_cmd)
        self.tree.add_command(report_cmd)
        self.tree.add_command(signalement_cmd)
        self.tree.add_command(suggestion_cmd)
        self.tree.add_command(config_embed_system)
        
        # Synchronisation
        try:
            await self.tree.sync()
            logger.info(f"Commandes synchronisées avec succès.")
        except Exception as e:
            logger.error(f"Erreur sync commandes: {e}")

    async def on_ready(self):
        logger.info(f"Connecté en tant que {self.user.name} ({self.user.id})")
        logger.info(f"Latence: {round(self.latency * 1000)}ms | Serveurs: {len(self.guilds)}")

        # Chargement des Assets Graphiques
        if PIL_AVAILABLE: download_and_cache_assets()

        # Initialisation des Vues Persistantes (Pour que les boutons marchent après reboot)
        if not self.persistent_views_added:
            self.add_view(RulesAcceptView(self))
            self.add_view(VoiceDashboardView())
            self.add_view(ModerationPanelView())
            self.add_view(ConfigPanelView())
            self.add_view(PlayerPanelView())
            self.add_view(EmbedPanelPermanentView())
            self.add_view(AdminHelpPanelView())
            self.add_view(AvatarConfigView(self))
            self.persistent_views_added = True
            logger.info("Vues persistantes chargées.")

        # Démarrage des Tâches de Fond (Economy + Modération)
        tasks_to_start = [
            check_birthdays, check_free_games_task, check_cine_news_task,
            weekly_xp_reset, post_weekly_leaderboard, backup_xp_data,
            check_avatar_revert, check_unbans, check_unmutes,
            check_infraction_purge, check_member_count,
            check_youtube_loop, check_other_platforms_loop
        ]
        
        for task in tasks_to_start:
            if not task.is_running():
                task.start(self) # On passe 'self' comme argument client_ref

    async def try_update_member_count(self, guild: discord.Guild):
        """Met à jour le compteur de membres avec anti-spam."""
        now = datetime.datetime.now().timestamp()
        last_update = self.last_member_count_update.get(guild.id, 0)
        if now - last_update > 300: # 5 minutes cooldown
            self.last_member_count_update[guild.id] = now
            await update_member_count_channel(guild)

    # --- ÉVÉNEMENTS MEMBRES ---

    async def on_member_join(self, member: discord.Member):
        logger.info(f"+ {member.name} a rejoint {member.guild.name}.")
        settings = db.get("settings", {})

        # 1. Message de Bienvenue (Salon)
        channel_id = settings.get("welcome_channel_id")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                welcome_raw = settings.get("welcome_message", "Bienvenue {user} !")
                # Support JSON ou Texte Simple
                try:
                    if welcome_raw.strip().startswith("{"):
                        data = json.loads(welcome_raw)
                        replacements = {"{user}": member.mention, "{user.name}": member.name, "{guild}": member.guild.name, "{member_count}": str(member.guild.member_count)}
                        data = recursive_replace(data, replacements)
                        if 'content' in data: 
                            await channel.send(content=data['content'])
                        if 'embeds' in data and data['embeds']:
                            await channel.send(embed=discord.Embed.from_dict(data['embeds'][0]))
                    else:
                        # Fallback Style Simple Poxel
                        content = welcome_raw.replace("{user}", member.mention).replace("{guild.name}", member.guild.name).replace("{member_count}", str(member.guild.member_count))
                        embed = discord.Embed(description=content, color=NEON_GREEN)
                        embed.set_thumbnail(url=member.display_avatar.url)
                        embed = apply_embed_styles(embed, "welcome")
                        await channel.send(embed=embed)
                except Exception as e: logger.error(f"Erreur Welcome: {e}")

        # 2. Message Privé (DM)
        dm_config = settings.get('welcome_dm', {})
        if dm_config.get('enabled', False):
            try:
                json_raw = dm_config.get('json_data')
                embed_dm = None
                if json_raw:
                    try:
                        data = json.loads(json_raw)
                        replacements = {"{user}": member.mention, "{user.name}": member.name, "{guild}": member.guild.name}
                        data = recursive_replace(data, replacements)
                        embed_dm = discord.Embed.from_dict(data['embeds'][0] if 'embeds' in data else data)
                    except: pass
                
                if not embed_dm:
                    # Fallback Simple
                    title = dm_config.get('title', 'Bienvenue !').replace('{guild}', member.guild.name)
                    desc = dm_config.get('description', 'Salut {user} !').replace('{user}', member.mention)
                    col = int(dm_config.get('color', hex(NEON_GREEN)).replace("#", ""), 16)
                    embed_dm = discord.Embed(title=title, description=desc, color=col)
                    if dm_config.get('image_url'): embed_dm.set_image(url=dm_config.get('image_url'))
                
                await member.send(embed=embed_dm)
            except: pass

        # 3. Triggers
        await trigger_avatar_change('member_join')
        await self.try_update_member_count(member.guild)

    async def on_member_remove(self, member: discord.Member):
        logger.info(f"- {member.name} a quitté {member.guild.name}.")
        settings = db.get("settings", {})

        # 1. Message de Départ
        channel_id = settings.get("farewell_channel_id")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                farewell_raw = settings.get("farewell_message", "Au revoir {user}.")
                try:
                    if farewell_raw.strip().startswith("{"):
                        data = json.loads(farewell_raw)
                        replacements = {"{user}": member.name, "{guild}": member.guild.name}
                        data = recursive_replace(data, replacements)
                        if 'embeds' in data: await channel.send(embed=discord.Embed.from_dict(data['embeds'][0]))
                    else:
                        content = farewell_raw.replace("{user}", member.display_name)
                        embed = discord.Embed(description=content, color=DARK_RED)
                        embed.set_thumbnail(url=member.display_avatar.url)
                        embed = apply_embed_styles(embed, "farewell")
                        await channel.send(embed=embed)
                except: pass

        # 2. Triggers
        await trigger_avatar_change('member_remove')
        await self.try_update_member_count(member.guild)

    # --- ÉVÉNEMENTS VOCAUX ---

    async def on_voice_state_update(self, member, before, after):
        # Création de Hub
        if after.channel and str(after.channel.id) in db.get('voice_hubs', {}):
            hub_data = db['voice_hubs'][str(after.channel.id)]
            try:
                cat = after.channel.category
                tname = f"🎧 Salon de {member.display_name}"
                new_chan = await cat.create_voice_channel(name=tname, user_limit=hub_data.get('limit', 0))
                db['temp_channels'][str(new_chan.id)] = {'owner_id': member.id, 'trusted': [], 'blocked': []}
                save_data(db)
                await member.move_to(new_chan)
                await trigger_avatar_change('channel_create')
            except Exception as e: logger.error(f"Erreur Voice Hub: {e}")

        # Suppression de Salon Vide
        if before.channel and str(before.channel.id) in db.get('temp_channels', {}) and not before.channel.members:
            try:
                await before.channel.delete()
                del db['temp_channels'][str(before.channel.id)]
                save_data(db)
                await trigger_avatar_change('channel_delete')
            except: pass

    # --- ÉVÉNEMENTS MESSAGE (Le Gros Morceau) ---

    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot: return
        settings = db.get("settings", {})

        # 1. CENSURE
        if settings.get("censor_enabled", True) and not message.author.guild_permissions.administrator:
            clean, censored = censor_text(message.content, settings.get("censored_words", []))
            if censored:
                try:
                    await message.delete()
                    # Webhook imitation
                    whs = await message.channel.webhooks()
                    wh = whs[0] if whs else await message.channel.create_webhook(name="PoxelCensor")
                    await wh.send(content=clean, username=message.author.display_name, avatar_url=message.author.display_avatar.url)
                    return # Stop processing here
                except: pass

        # 2. AUTO-MOD (Nova-Guard)
        if settings.get("auto_mod_enabled", True) and not message.author.guild_permissions.administrator:
            norm_content = normalize_text(message.content)
            triggered = None
            
            # Vérification cooldown utilisateur
            uid = str(message.author.id)
            now_ts = time.time()
            last_trig = db.get('user_auto_mod_cooldown', {}).get(uid, 0)
            
            for pname, pdata in db.get('auto_mod_profiles', {}).items():
                if now_ts - last_trig < pdata.get('cooldown_seconds', 0): continue
                
                for kw in pdata.get('keywords', []):
                    if normalize_text(kw) in norm_content:
                        triggered = (pname, pdata)
                        break
                if triggered: break
            
            if triggered:
                pname, pdata = triggered
                db.setdefault('user_auto_mod_cooldown', {})[uid] = now_ts
                
                actions = pdata.get('actions', [])
                if actions:
                    act = actions[0] # Premier action définie
                    atype = act.get('type')
                    pts = act.get('points', 1)
                    reason = f"Nova-Guard: {pname}"
                    
                    # Application Sanction
                    try: await message.delete()
                    except: pass
                    
                    if atype == 'warn':
                        await poxel_warn_logic(message, message.author, reason, pts)
                    elif atype == 'mute':
                        dur = act.get('duration', '5m')
                        await poxel_mute_logic(message, message.author, dur, reason, pts)
                    elif atype == 'kick':
                        await poxel_kick_logic(message, message.author, reason, pts)
                    elif atype == 'ban':
                        await poxel_ban_logic(message, message.author, reason, pts)
                    
                    # Logs
                    log_id = settings.get("auto_mod_log_channel_id")
                    if log_id:
                        ch = self.get_channel(log_id)
                        if ch: await ch.send(f"🛡️ **Auto-Mod** ({pname}) sur {message.author.mention} : {atype.upper()}")
                    return

        # 3. SYSTÈME XP (Economy)
        user_data = get_user_xp_data(message.author.id)
        now = get_adjusted_time()
        xp_conf = settings.get("level_up_rewards", {})
        
        # Cooldown XP
        can_xp = True
        last_ts = user_data.get("last_message_timestamp")
        if last_ts:
            try:
                ltime = datetime.datetime.fromisoformat(last_ts).replace(tzinfo=SERVER_TIMEZONE)
                if now < ltime + datetime.timedelta(minutes=xp_conf.get("xp_gain_cooldown_minutes", 1)):
                    can_xp = False
            except: pass
        
        if can_xp:
            gain = random.randint(xp_conf.get("xp_gain_per_message", {}).get("min", 15), xp_conf.get("xp_gain_per_message", {}).get("max", 25))
            user_data["last_message_timestamp"] = now.isoformat()
            await update_user_xp(message.author.id, gain)
            await check_and_handle_progression(message.author, message.channel)
            save_data(db)

        # 4. ÉCOUTE BOTS (Mod/Event Listeners)
        # Logique pour détecter les embeds d'autres bots (ex: Carl-bot, etc.) et donner de l'XP
        listener = settings.get("mod_listener_settings", {})
        if listener.get("enabled", True) and message.embeds:
            mod_ch = listener.get("mod_bot_channel_id")
            evt_ch = listener.get("event_bot_channel_id")
            
            if message.channel.id in [mod_ch, evt_ch]:
                emb = message.embeds[0]
                target = None
                xp_val = 0
                
                # Extraction ID (Regex)
                txt = (emb.description or "") + (emb.footer.text if emb.footer else "")
                ids = re.findall(r'(\d{17,19})', txt)
                if ids:
                    target = message.guild.get_member(int(ids[0]))
                
                if target:
                    # Logique Event (Victoire)
                    if message.channel.id == evt_ch and "vainqueur" in (emb.description or "").lower():
                        xp_val = listener.get("xp_reward", {}).get("tournament_win", 200)
                    
                    # Logique Sanction (Pénalité XP)
                    elif message.channel.id == mod_ch:
                        title = (emb.title or "").lower()
                        penalties = listener.get("xp_penalty", {})
                        for k, v in penalties.items():
                            if k in title: 
                                xp_val = v
                                break
                    
                    if xp_val != 0:
                        await update_user_xp(target.id, xp_val, is_weekly_xp=(xp_val > 0))
                        save_data(db)
                        logger.info(f"Listener XP: {target.name} {xp_val:+d} XP.")

    # --- ÉVÉNEMENTS RÉACTIONS (Rôles) ---

    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.user.id: return
        msg_id = str(payload.message_id)
        conf = db.get('reaction_role_messages', {}).get(msg_id)
        if conf and str(payload.emoji) in conf:
            guild = self.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(conf[str(payload.emoji)])
            if member and role: 
                try: await member.add_roles(role)
                except: pass

    async def on_raw_reaction_remove(self, payload):
        if payload.user_id == self.user.id: return
        msg_id = str(payload.message_id)
        conf = db.get('reaction_role_messages', {}).get(msg_id)
        if conf and str(payload.emoji) in conf:
            guild = self.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(conf[str(payload.emoji)])
            if member and role: 
                try: await member.remove_roles(role)
                except: pass


# ==================================================================================================
# 25. COMMANDES DE SYNCHRONISATION ET AIDE ADMIN
# ==================================================================================================

# --- Commande de Synchronisation Manuelle (Admin) ---
@app_commands.command(name="admin_sync", description="[Admin] Force la synchronisation des commandes avec Discord.")
@app_commands.default_permissions(administrator=True)
async def admin_sync(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        synced = await interaction.client.tree.sync()
        command_names = [c.name for c in synced]
        await interaction.followup.send(f"✅ **Synchronisation réussie !**\n**{len(synced)} commandes actives :**\n`{', '.join(command_names)}`", ephemeral=True)
    except Exception as e:
        logger.exception(f"Erreur Sync Manuelle: {e}")
        await interaction.followup.send(f"❌ Erreur lors de la synchronisation : `{e}`", ephemeral=True)

# --- Commande Aide Admin (Globale) ---
@app_commands.command(name="poxel_help", description="Affiche le panneau d'aide administrateur.")
@app_commands.default_permissions(administrator=True)
async def poxel_help(interaction: discord.Interaction):
    await send_admin_help_logic(interaction)

# --- Commande Aide Joueur (Globale) ---
@app_commands.command(name="poxel_help_joueur", description="Affiche le panneau d'aide pour les joueurs.")
async def help_joueur(interaction: discord.Interaction):
    await send_player_help_logic(interaction)

# ==================================================================================================
# 26. DÉMARRAGE DU BOT
# ==================================================================================================

if __name__ == "__main__":
    # 1. Vérification du Token
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    if not DISCORD_TOKEN:
        logger.critical("ERREUR CRITIQUE: La variable 'DISCORD_TOKEN' est introuvable dans le fichier .env.")
        logger.critical("Le bot ne peut pas démarrer sans son token.")
        sys.exit(1)

    # 2. Lancement du Serveur Web (Flask) pour le ping (Hébergement)
    # Le serveur tourne sur un thread séparé pour ne pas bloquer le bot
    try:
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("Serveur Flask démarré en arrière-plan (Port 8080).")
    except Exception as e:
        logger.error(f"Erreur lors du démarrage du serveur Flask: {e}")

    # 3. Initialisation et Lancement du Client Discord
    # Les intents sont définis au tout début (Partie 1)
    client = PoxelClient(intents=intents)

    try:
        logger.info("Tentative de connexion aux passerelles Discord...")
        
        # Debug optionnel : Afficher les commandes enregistrées avant le run (localement)
        # Note : Cela n'affiche que les commandes ajoutées via @client.tree.command (pas les groupes dans setup_hook)
        # cmds = client.tree.get_commands()
        # logger.info(f"Commandes pré-chargées : {[c.name for c in cmds]}")

        client.run(DISCORD_TOKEN, log_handler=None) # On utilise notre propre logger configuré en Partie 1

    except discord.errors.LoginFailure:
        logger.critical("ERREUR D'AUTHENTIFICATION: Le token Discord fourni est invalide.")
        logger.critical("Veuillez vérifier le fichier .env et régénérer le token si nécessaire.")
    except discord.errors.PrivilegedIntentsRequired:
        logger.critical("ERREUR D'INTENTS: Les 'Privileged Intents' (Presence, Server Members, Message Content) ne sont pas activés.")
        logger.critical("Allez sur le Portail Développeur Discord -> Bot -> Privileged Gateway Intents et activez-les tous.")
    except Exception as e:
        logger.exception(f"Erreur fatale inattendue lors de l'exécution du bot: {e}")
    finally:
        logger.info("Arrêt du processus Poxel.")
