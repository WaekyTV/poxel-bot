# -*- coding: utf-8 -*-
"""
Description: Un bot Discord complet pour gérer la modération, les événements, concours et tournois.
Auteur: Poxel
"""
"""
Poxel
Version: 7.2 (Auto-Install Dependencies)

Changelog de la version 7.2:
- CORRECTIF : Ajout du système d'installation automatique des dépendances (discord.py, flask, etc.) pour éviter les erreurs "ModuleNotFoundError".
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
    """
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
                print(f"ERREUR: Impossible d'installer {package_name}. Erreur: {e}")
                sys.exit(1) # Arrêt critique si une dépendance majeure manque
            except ImportError:
                print(f"AVERTISSEMENT: Le paquet '{package_name}' est installé mais ne peut pas être importé.")

# Liste des paquets requis pour ce bot : {nom d'importation: nom du paquet pip}
required_packages = {
    "discord": "discord.py",
    "flask": "Flask",
    "dotenv": "python-dotenv",
    "aiohttp": "aiohttp",
    "pytz": "pytz"
}
check_and_install_packages(required_packages)

# ==================================================================================================
# 1. IMPORTS
# ==================================================================================================
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput, Select
import datetime
import asyncio
import os
import json
import pytz
import random
import math
from flask import Flask
from threading import Thread
import aiohttp
from dotenv import load_dotenv
import re # Ajouté car utilisé dans la logique de modération

# Chargement des variables d'environnement
load_dotenv()

# ==================================================================================================
# 2. CONFIGURATION & CONSTANTES
# ==================================================================================================

# --- Configuration du bot Discord ---
intents = discord.Intents.all()
# La variable 'client' sera instanciée à la fin du script, avant le démarrage.
client = None

# --- Couleurs Thématiques ---
NEON_PURPLE = 0x6441a5
NEON_BLUE = 0x027afa
NEON_GREEN = 0x00ff99
RETRO_ORANGE = 0xFF8C00
DARK_RED = 0x8B0000

# --- Fuseaux Horaires ---
USER_TIMEZONE = pytz.timezone('Europe/Paris')
SERVER_TIMEZONE = pytz.utc

# --- Fichiers & Base de Données ---
DATABASE_FILE = 'events_contests.json'

# --- Rôles & Titres Permanents ---
TROPHY_ROLE_NAME = "🏆 Trophée"
PARTICIPANT_ROLE_NAME = "Tournoi Participant"

# --- Noms des Rondes de Tournoi ---
ROUND_NAMES = ["Round 1", "Round 2", "Quart de Finale", "Demi-Finale", "FINALE"]

# --- Système de Trophées (Titres) ---
TROPHY_TITLES = {
    1: "👾 Pixie Rookie",
    3: "🎮 8-Bit Challenger",
    5: "💾 Retro Master",
    10: "🕹️ Arcade Legend",
    20: "🌌 Vintage Champion",
    50: "🏯 Pixel Overlord",
    100: "✨ Retro Immortal"
}

# --- Système de Vies (Points d'Infraction) ---
# Chaque point correspond à une vie perdue. Le nombre de points est paramétrable ici.
INFRACTION_POINTS = {
    "warn": 1,
    "mute": 1,
    "kick": 2,
    "tempban": 3,
    "ban": 5,
    "signalement": 1, # Coût en vie d'un signalement validé
    "auto_warn": 1,
    "auto_mute": 1,
    "auto_kick": 2,
    "auto_tempban": 3,
    "auto_ban": 5,
}

# --- Avatars Dynamiques (Pixel-Emotion) ---
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
    'custom': 'Forcé par un Admin'
}

# ==================================================================================================
# 3. SERVEUR FLASK (Pour Hébergement)
# ==================================================================================================
app = Flask(__name__)

@app.route('/')
def home():
    """Point de terminaison simple pour le ping de l'hébergeur."""
    return "Poxel Bot is running!"

def run_flask():
    """Démarre le serveur Flask sur un thread séparé."""
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# ==================================================================================================
# 4. GESTION DE LA BASE DE DONNÉES (JSON)
# ==================================================================================================
def load_data():
    """Charge toutes les données depuis le fichier JSON et assure l'existence des clés."""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    else:
        data = {}

    # Initialisation des clés principales si elles n'existent pas
    data.setdefault("events", {})
    data.setdefault("contests", {})
    data.setdefault("tournaments", {})
    data.setdefault("trophies", {})
    data.setdefault("default_embeds", {"events": {}, "contests": {}, "tournaments": {}})
    data.setdefault("infractions", {})
    data.setdefault("avatar_stack", [])
    data.setdefault("avatar_triggers", {})
    data.setdefault("auto_mod_profiles", {})
    data.setdefault("user_auto_mod_cooldown", {})
    data.setdefault("active_tickets", {})
    data.setdefault("voice_hubs", {})
    data.setdefault("temp_channels", {})
    data.setdefault("embed_builders", {}) # Pour le créateur d'embed
    data.setdefault("reaction_role_messages", {}) # Pour les rôles par réaction
    
    # Initialisation des paramètres (settings)
    settings = data.setdefault("settings", {})
    settings.setdefault("time_offset_seconds", 0)
    # Vies (paramétrable)
    settings.setdefault("max_lives_default", 9)
    settings.setdefault("max_lives_boost", 10)
    settings.setdefault("life_emoji_full", "❤️")
    settings.setdefault("life_emoji_empty", "🖤")
    settings.setdefault("life_emoji_boost", "💛")
    settings.setdefault("purge_duration_days", 180) # Configurable: 6 mois par défaut
    # Avatars
    settings.setdefault("avatar_cooldown_seconds", 300)
    settings.setdefault("avatar_last_changed", None)
    settings.setdefault("avatar_enabled", True)
    settings.setdefault("avatar_default_url", None)
    # Auto-Mod
    settings.setdefault("auto_mod_enabled", True)
    settings.setdefault("auto_mod_log_channel_id", None)
    # Tickets/Reports
    settings.setdefault("ticket_config", {"panel_channel_id": None, "category_id": None})
    settings.setdefault("report_config", {"panel_channel_id": None, "category_id": None})
    settings.setdefault("signalement_config", {"panel_channel_id": None, "category_id": None})
    settings.setdefault("suggestion_config", {"panel_channel_id": None, "category_id": None})
    # Bienvenue/Départ
    settings.setdefault("welcome_channel_id", None)
    settings.setdefault("farewell_channel_id", None)
    settings.setdefault("welcome_message", "🎉 Bienvenue dans l'Arcade, {user} ! Préparez-vous pour le GAME START.")
    settings.setdefault("farewell_message", "💔 Au revoir, {user}. GAME OVER. Reviens vite !")
    # Message Privé de Bienvenue
    welcome_dm = settings.setdefault("welcome_dm", {})
    welcome_dm.setdefault("enabled", False)
    welcome_dm.setdefault("title", "Bienvenue sur {guild} !")
    welcome_dm.setdefault("description", "Salut {user} ! Je suis Poxel, le bot du serveur. N'hésite pas à consulter les règles et à te présenter !")
    welcome_dm.setdefault("color", hex(NEON_GREEN))
    welcome_dm.setdefault("image_url", None)
    # Règles
    settings.setdefault("rules_role_id", None)
    settings.setdefault("rules_channel_id", None)
    settings.setdefault("rules_password", "PIXEL")
    settings.setdefault("rules_embed_title", "📜 PROTOCOLE D'ACCÈS DU JOUEUR")
    settings.setdefault("rules_embed_content", "Bienvenue, [joueur]. Pour débloquer l'accès au serveur, vous devez lire le règlement ci-dessous, trouver le mot de passe caché (indice : le mot PIXEL est la clé de l'ARCADE) et le saisir dans la modale d'acceptation. ÉCHEC = BAN.")
    settings.setdefault("rules_embed_color", hex(NEON_PURPLE))

    # --- Présentation du Bot ---
    settings.setdefault("presentation_channel_id", None)
    settings.setdefault("presentation_message_id", None)
    settings.setdefault("presentation_embed_data", {
        "title": "Poxel",
        "description": "Salut, pixel ! Je suis Poxel, ton bot de modération et d'animation avec un style 8-bit. Prépare-toi à une expérience rétro !",
        "color": hex(NEON_PURPLE),
        "image_url": None,
        "thumbnail_url": None,
        "link_url": None
    })

    # --- Censure & Compteur ---
    settings.setdefault("censor_enabled", True)
    settings.setdefault("censored_words", ["connard", "salope", "putain"]) # Mots par défaut
    settings.setdefault("member_count_channel_id", None)
    
    # Init config vocal si absente
    settings.setdefault('voice_interface_json', None)
    settings.setdefault('voice_error_json', None)

    return data

def save_data(data):
    """Sauvegarde les données dans le fichier JSON."""
    with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

db = load_data()


# ==================================================================================================
# 5. FONCTIONS UTILITAIRES GÉNÉRALES
# ==================================================================================================

def get_adjusted_time():
    """Renvoie l'heure UTC actuelle ajustée avec le décalage du serveur."""
    offset = db['settings'].get('time_offset_seconds', 0)
    return datetime.datetime.now(SERVER_TIMEZONE) + datetime.timedelta(seconds=offset)

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

async def check_admin_or_organizer(interaction: discord.Interaction, organizer_id: int):
    is_admin = interaction.user.guild_permissions.administrator
    is_org = interaction.user.id == organizer_id
    if not (is_admin or is_org):
        await interaction.response.send_message("Permission refusée.", ephemeral=True)
        return False
    return True

def parse_duration(duration_str: str):
    if not duration_str: return datetime.timedelta(seconds=0)
    s = duration_str.lower().strip()
    val = "".join(filter(str.isdigit, s))
    if not val: return datetime.timedelta(seconds=0)
    val = int(val)
    if 'm' in s: return datetime.timedelta(minutes=val)
    elif 'h' in s: return datetime.timedelta(hours=val)
    elif 'd' in s: return datetime.timedelta(days=val)
    elif 's' in s: return datetime.timedelta(seconds=val)
    return datetime.timedelta(seconds=0)

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

# ==================================================================================================
# 6. SYSTÈME DE VIES
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
    
    # Construction simple : Pleins puis Vides
    current = max(0, max_lives - lost)
    
    # Gestion du coeur boost en dernier
    is_boosted = max_lives > 9
    
    hearts = []
    for i in range(1, max_lives + 1):
        if i <= current:
            # Si c'est la 10e vie et qu'on est boosté
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
    
    asyncio.create_task(check_perma_ban(client, member))
    
    if send_dm:
        max_l = get_max_lives(member)
        cur = get_total_infraction_points(member.id)
        rem = max(0, max_l - cur)
        asyncio.create_task(send_private_notification(member, f"SANCTION ({type.upper()})", reason, damage=pts, remaining_lives=rem, is_auto=True))
    
    return True

# ==================================================================================================
# 7. SYSTÈME D'AVATAR DYNAMIQUE (CORRIGÉ & DÉPLACÉ ICI)
# ==================================================================================================

async def fetch_image_bytes(url: str):
    if not url: return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200: return await resp.read()
                print(f"AVATAR ERROR: HTTP {resp.status} pour {url}")
    except Exception as e: print(f"AVATAR ERROR: {e}")
    return None

async def revert_avatar():
    """Restaure l'avatar précédent."""
    # On récupère le client global s'il n'est pas passé en argument
    global client
    if not client or not client.is_ready(): return

    if not db.get('avatar_stack'): return
    db['avatar_stack'].pop(0)
    save_data(db)
    
    url = db['avatar_stack'][0]['image_url'] if db['avatar_stack'] else db['settings'].get('avatar_default_url')
    
    if url:
        data = await fetch_image_bytes(url)
        if data:
            try: await client.user.edit(avatar=data)
            except Exception as e: print(f"AVATAR REVERT FAIL: {e}")
    else:
        try: await client.user.edit(avatar=None)
        except: pass

async def trigger_avatar_change(trigger: str):
    """Change l'avatar selon le trigger."""
    global client
    if not client or not client.is_ready(): return
    if not db['settings'].get('avatar_enabled', True): return

    conf = db['avatar_triggers'].get(trigger)
    if not conf or not conf.get('image_url'):
        # print(f"AVATAR DEBUG: Pas de config pour '{trigger}'") # Décommenter pour debug
        return

    # Cooldown global pour éviter le spam d'API
    now = get_adjusted_time()
    last = db['settings'].get('avatar_last_changed')
    if last:
        last_dt = datetime.datetime.fromisoformat(last).replace(tzinfo=SERVER_TIMEZONE)
        cd = db['settings'].get('avatar_cooldown_seconds', 300)
        if now < last_dt + datetime.timedelta(seconds=cd):
            print(f"AVATAR: Cooldown actif, ignorer '{trigger}'")
            return

    data = await fetch_image_bytes(conf['image_url'])
    if data:
        try:
            await client.user.edit(avatar=data)
            print(f"AVATAR: Changé pour '{trigger}'")
            
            dur_str = conf.get('duration', '0s')
            delta = parse_duration(dur_str)
            revert_time = (now + delta).isoformat() if delta.total_seconds() > 0 else None
            
            db['avatar_stack'].insert(0, {
                "trigger": trigger, "image_url": conf['image_url'], "revert_time": revert_time
            })
            if len(db['avatar_stack']) > 5: db['avatar_stack'].pop()
            
            db['settings']['avatar_last_changed'] = now.isoformat()
            save_data(db)
        except Exception as e:
            print(f"AVATAR CHANGE FAIL ({trigger}): {e}")


# ==================================================================================================
# 8. LOGIQUE PARTAGÉE DE MODÉRATION (FONCTIONS PURES)
# ==================================================================================================

async def poxel_ban_logic(interaction: discord.Interaction, user: discord.User, reason: str, custom_points: int = None):
    """Logique centrale du Ban (Supporte User pour ban ID)."""
    await interaction.response.defer(ephemeral=True)
    
    # Tentative de récupération membre pour les vies (si présent)
    member = interaction.guild.get_member(user.id)
    max_lives = get_max_lives(member) if member else db['settings'].get("max_lives_default", 9)
    
    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("ban", 5)
    current_loss = get_total_infraction_points(user.id)
    remaining = max(0, max_lives - (current_loss + points))

    # 1. MP
    await send_private_notification(
        user, "BAN PERMANENT", reason, interaction.user, 
        duration="Définitif", damage=points, remaining_lives=remaining
    )
    
    # 2. Cooldown
    await asyncio.sleep(2)

    # 3. Action
    try:
        await interaction.guild.ban(user, reason=reason)
        
        # Enregistrement DB (on passe 'user' qui a un ID, même si pas member)
        # Note: add_infraction attend un objet avec .id, user fonctionne
        add_infraction_with_life_check(client, interaction, user, "ban", reason, custom_points=points, send_dm=False)
        await trigger_avatar_change('ban')
        
        db.setdefault('banned_users_data', {})[str(user.id)] = {"reason": reason, "date": get_adjusted_time().isoformat()}
        save_data(db)

        await interaction.followup.send(f"✅ **{user.name}** a été banni (MP envoyé).", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Erreur : Je n'ai pas la permission de bannir cet utilisateur.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

async def poxel_tempban_logic(interaction: discord.Interaction, user: discord.User, duration_str: str, reason: str, custom_points: int = None):
    """Logique centrale du Tempban."""
    await interaction.response.defer(ephemeral=True)

    delta = parse_duration(duration_str)
    if delta.total_seconds() <= 0:
        return await interaction.followup.send("❌ Durée invalide.", ephemeral=True)

    member = interaction.guild.get_member(user.id)
    max_lives = get_max_lives(member) if member else db['settings'].get("max_lives_default", 9)
    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("tempban", 3)
    current_loss = get_total_infraction_points(user.id)
    remaining = max(0, max_lives - (current_loss + points))

    # 1. MP
    await send_private_notification(
        user, "TEMPBAN", reason, interaction.user, 
        duration=duration_str, damage=points, remaining_lives=remaining
    )
    
    # 2. Cooldown
    await asyncio.sleep(2)

    # 3. Schedule & Action
    unban_time = get_adjusted_time() + delta
    db.setdefault('scheduled_unbans', []).append({
        "guild_id": interaction.guild_id,
        "user_id": user.id,
        "unban_at": unban_time.isoformat()
    })
    save_data(db)

    try:
        await interaction.guild.ban(user, reason=f"Tempban ({duration_str}): {reason}")
        add_infraction_with_life_check(client, interaction, user, "tempban", f"({duration_str}) {reason}", custom_points=points, send_dm=False)
        await trigger_avatar_change('ban')
        await interaction.followup.send(f"✅ **{user.name}** banni pour {duration_str} (MP envoyé).", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Erreur permission.", ephemeral=True)

async def poxel_kick_logic(interaction: discord.Interaction, member: discord.Member, reason: str, custom_points: int = None):
    """Logique centrale du Kick (Requiert Membre présent)."""
    await interaction.response.defer(ephemeral=True)

    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("kick", 2)
    max_lives = get_max_lives(member)
    current_loss = get_total_infraction_points(member.id)
    remaining = max(0, max_lives - (current_loss + points))

    # 1. MP
    await send_private_notification(
        member, "KICK (EXPULSION)", reason, interaction.user, 
        damage=points, remaining_lives=remaining
    )
    
    # 2. Cooldown
    await asyncio.sleep(2)

    # 3. Action
    try:
        await member.kick(reason=reason)
        add_infraction_with_life_check(client, interaction, member, "kick", reason, custom_points=points, send_dm=False)
        await trigger_avatar_change('kick')
        await interaction.followup.send(f"✅ **{member.display_name}** expulsé (MP envoyé).", ephemeral=True)
    except:
        await interaction.followup.send("❌ Erreur permission.", ephemeral=True)

async def poxel_mute_logic(interaction: discord.Interaction, member: discord.Member, duration_str: str, reason: str, custom_points: int = None):
    """Logique centrale du Mute (Requiert Membre présent)."""
    await interaction.response.defer(ephemeral=True)

    delta = parse_duration(duration_str)
    if delta.total_seconds() <= 0:
        return await interaction.followup.send("❌ Durée invalide.", ephemeral=True)

    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("mute", 1)
    max_lives = get_max_lives(member)
    current_loss = get_total_infraction_points(member.id)
    remaining = max(0, max_lives - (current_loss + points))

    # 1. MP
    await send_private_notification(
        member, "MUTE (MISE EN SOURDINE)", reason, interaction.user, 
        duration=duration_str, damage=points, remaining_lives=remaining
    )
    
    # 2. Cooldown
    await asyncio.sleep(2)

    # 3. Action
    try:
        await member.timeout(discord.utils.utcnow() + delta, reason=reason)
        
        unmute_time = get_adjusted_time() + delta
        db.setdefault('scheduled_unmutes', []).append({
            "guild_id": interaction.guild_id,
            "user_id": member.id,
            "unmute_at": unmute_time.isoformat()
        })
        save_data(db)

        add_infraction_with_life_check(client, interaction, member, "mute", reason, custom_points=points, send_dm=False)
        await trigger_avatar_change('mute')
        await interaction.followup.send(f"✅ **{member.display_name}** rendu muet pour {duration_str} (MP envoyé).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

async def poxel_warn_logic(interaction: discord.Interaction, user: discord.User, reason: str, custom_points: int = None):
    """Logique centrale du Warn."""
    await interaction.response.defer(ephemeral=True)

    member = interaction.guild.get_member(user.id)
    max_lives = get_max_lives(member) if member else db['settings'].get("max_lives_default", 9)
    points = custom_points if custom_points is not None else INFRACTION_POINTS.get("warn", 1)
    current_loss = get_total_infraction_points(user.id)
    remaining = max(0, max_lives - (current_loss + points))

    # 1. MP
    await send_private_notification(
        user, "AVERTISSEMENT", reason, interaction.user, 
        damage=points, remaining_lives=remaining
    )
    
    await asyncio.sleep(1)
    
    add_infraction_with_life_check(client, interaction, user, "warn", reason, custom_points=points, send_dm=False)
    await trigger_avatar_change('warn')
    await interaction.followup.send(f"✅ **{user.name}** averti.", ephemeral=True)

async def poxel_unban_logic(interaction: discord.Interaction, user_id: str, reason: str = "Levée de sanction manuelle"):
    """Logique centrale de l'Unban."""
    await interaction.response.defer(ephemeral=True)
    try:
        user = await client.fetch_user(int(user_id))
        max_lives = db['settings'].get("max_lives_default", 9)
        
        embed_dm = discord.Embed(
            title="✅ DÉBANNISSEMENT (UNBAN)",
            description=f"Un administrateur du serveur **{interaction.guild.name}** a levé votre bannissement.",
            color=NEON_GREEN
        )
        embed_dm.add_field(name="Raison", value=reason, inline=False)
        embed_dm.add_field(name="Vies restaurées", value=f"{max_lives} coeurs (Maximum)", inline=True)
        embed_dm.set_footer(text="Vous pouvez rejoindre le serveur.")
        
        try: await user.send(embed=embed_dm)
        except: pass

        await interaction.guild.unban(user, reason=f"Unban par admin: {reason}")
        
        if user_id in db['infractions']:
            del db['infractions'][user_id]
            save_data(db)
        
        await trigger_avatar_change('unban') 
        await interaction.followup.send(f"✅ **{user.name}** a été débanni.", ephemeral=True)
        
    except discord.NotFound:
        await interaction.followup.send(f"❌ Utilisateur ID {user_id} introuvable.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

async def poxel_unmute_logic(interaction: discord.Interaction, user_id: int):
    """Logique centrale de l'Unmute."""
    await interaction.response.defer(ephemeral=True)
    try:
        user = await client.fetch_user(user_id)
        
        embed_dm = discord.Embed(
            title="🔊 FIN DE MUTE (UNMUTE)",
            description=f"Un administrateur du serveur **{interaction.guild.name}** a levé votre mute.",
            color=NEON_GREEN
        )
        embed_dm.add_field(name="Info", value="La sanction a été levée, vous pouvez à nouveau discuter sans infraction dans le chat.", inline=False)
        embed_dm.set_footer(text="La parole vous est rendue.")
        
        try: await user.send(embed=embed_dm)
        except: pass

        member = interaction.guild.get_member(user.id)
        if member:
            await member.timeout(None, reason="Unmute manuel par admin.")
            await interaction.followup.send(f"✅ **{user.name}** unmute (MP envoyé).", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ **{user.name}** notifié par MP (Timeout impossible à retirer : hors serveur).", ephemeral=True)
            
        remaining = []
        for task in db.get('scheduled_unmutes', []):
            if task['user_id'] != user.id: remaining.append(task)
        db['scheduled_unmutes'] = remaining
        save_data(db)

    except Exception as e:
        await interaction.followup.send(f"Erreur: {e}", ephemeral=True)

async def poxel_clear_infs_logic(interaction: discord.Interaction, member: discord.Member, reason: str):
    """Logique centrale du Clear Infractions."""
    await interaction.response.defer(ephemeral=True)
    user_id_str = str(member.id)
    
    if user_id_str in db['infractions']:
        max_lives = get_max_lives(member)
        embed_dm = discord.Embed(title="♻️ CASIER PURGÉ", description=f"Un administrateur du serveur **{interaction.guild.name}** a effacé votre casier judiciaire.", color=NEON_GREEN)
        embed_dm.add_field(name="Raison", value=reason, inline=False)
        embed_dm.add_field(name="Vies restaurées", value=f"{max_lives} coeurs (Maximum)", inline=True)
        
        try: await member.send(embed=embed_dm)
        except: pass

        del db['infractions'][user_id_str]
        save_data(db)
        
        await trigger_avatar_change('infraction_clear') 
        await interaction.followup.send(f"✅ Casier de **{member.display_name}** purgé.", ephemeral=True)
    else:
        await interaction.followup.send(f"**{member.display_name}** a déjà un casier vierge.", ephemeral=True)

# ==================================================================================================
# COMMANDES SLASH (RACCORDS)
# ==================================================================================================

@app_commands.command(name="ban", description="Bannit définitivement (MP -> Cooldown -> Ban).")
@app_commands.describe(user="L'utilisateur à bannir (ID ou Mention)", reason="Raison", custom_points="Vies perdues")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, user: discord.User, reason: str, custom_points: app_commands.Range[int, 0, 10] = None):
    await poxel_ban_logic(interaction, user, reason, custom_points)

@app_commands.command(name="tempban", description="Bannit temporairement (MP -> Cooldown -> Ban).")
@app_commands.describe(user="L'utilisateur (ID ou Mention)", duration="Durée (ex: 7d)", reason="Raison", custom_points="Vies perdues")
@app_commands.default_permissions(ban_members=True)
async def tempban(interaction: discord.Interaction, user: discord.User, duration: str, reason: str, custom_points: app_commands.Range[int, 0, 10] = None):
    await poxel_tempban_logic(interaction, user, duration, reason, custom_points)

@app_commands.command(name="kick", description="Expulse un utilisateur (MP -> Cooldown -> Kick).")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str, custom_points: app_commands.Range[int, 0, 10] = None):
    await poxel_kick_logic(interaction, member, reason, custom_points)

@app_commands.command(name="mute", description="Rend muet (MP -> Cooldown -> Mute).")
async def mute(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str, custom_points: app_commands.Range[int, 0, 10] = None):
    await poxel_mute_logic(interaction, member, duration, reason, custom_points)

@app_commands.command(name="warn", description="Avertissement (MP -> Warn).")
async def warn(interaction: discord.Interaction, user: discord.User, reason: str, custom_points: app_commands.Range[int, 0, 10] = None):
    await poxel_warn_logic(interaction, user, reason, custom_points)

@app_commands.command(name="unban", description="Débannit (ID -> MP -> Unban).")
@app_commands.describe(user_id="ID de l'utilisateur", reason="Raison")
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "Levée de sanction manuelle"):
    await poxel_unban_logic(interaction, user_id, reason)

@app_commands.command(name="unmute", description="Lève le mute (ID -> MP -> Unmute).")
async def unmute(interaction: discord.Interaction, user: discord.User):
    await poxel_unmute_logic(interaction, user.id)

@app_commands.command(name="clear_all_infractions", description="Purge le casier (MP -> Clear).")
async def clear_all_infractions(interaction: discord.Interaction, member: discord.Member, reason: str):
    await poxel_clear_infs_logic(interaction, member, reason)

# Commandes utilitaires (inchangées)
@app_commands.command(name="infractions", description="Affiche la liste des infractions d'un utilisateur.")
async def infractions(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    user_id_str = str(member.id)
    infractions_list = db['infractions'].get(user_id_str, [])
    total_points = get_total_infraction_points(member.id)
    embed = discord.Embed(title=f"🚨 FICHIER D'INFRACTIONS : {member.display_name}", color=NEON_PURPLE)
    if not infractions_list: embed.description = "Aucune infraction enregistrée."
    else:
        description = []
        for i, inf in enumerate(infractions_list):
            points = inf.get('points_lost', INFRACTION_POINTS.get(inf.get('type', '?'), 0))
            description.append(f"**{i+1}. {inf['type'].upper()}** (`{points} pts`) : {inf['reason'][:60]}...")
        embed.description = "\n".join(description)
    embed.set_footer(text=f"Total: {total_points} points.")
    await interaction.followup.send(embed=embed, ephemeral=True)

@app_commands.command(name="clear", description="Supprime un nombre de messages.")
async def clear(interaction: discord.Interaction, nombre: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=nombre)
    await interaction.followup.send(discord.Embed(title="💥 CLEANUP", description=f"**{len(deleted)}** messages désintégrés.", color=NEON_BLUE), ephemeral=True)

@app_commands.command(name="slowmode", description="Définit un mode lent.")
async def slowmode(interaction: discord.Interaction, duration: str):
    await interaction.response.defer(ephemeral=True)
    delta = parse_duration(duration)
    seconds = int(delta.total_seconds())
    if not (0 <= seconds <= 21600): return await interaction.followup.send("Durée invalide (max 6h).", ephemeral=True)
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.followup.send(discord.Embed(title="⏳ SLOWMODE", description=f"Délai : **{duration}**.", color=RETRO_ORANGE))


# ==================================================================================================
# 11. SALONS VOCAUX TEMPORAIRES (VOICE HUBS & INTERFACE)
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

# --- CONFIG VOICE UI ---
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

# --- COMMANDES CONFIG ---
voice_config_group = app_commands.Group(name="voice_config", description="Configuration avancée des salons vocaux.", default_permissions=discord.Permissions(administrator=True))

@voice_config_group.command(name="interface_design", description="Configure l'apparence du panneau de contrôle vocal (JSON).")
async def config_interface_design(interaction: discord.Interaction):
    await interaction.response.send_modal(VoiceInterfaceConfigModal())

@voice_config_group.command(name="error_design", description="Configure l'apparence du message 'Pas de salon' (JSON).")
async def config_error_design(interaction: discord.Interaction):
    await interaction.response.send_modal(VoiceErrorConfigModal())

@voice_config_group.command(name="ui", description="Configurer les émojis et textes des boutons et menus.")
async def config_ui_global(interaction: discord.Interaction):
    await interaction.response.send_message("🎨 **Personnalisation de l'Interface Vocale**", view=VoiceUIConfigView(), ephemeral=True)

@voice_config_group.command(name="setup_panel", description="Poste le panneau de contrôle PERMANENT dans ce salon.")
async def setup_voice_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    interface_json_str = db.get('settings', {}).get('voice_interface_json')
    embed = None
    if interface_json_str:
        try:
            data = json.loads(interface_json_str)
            if 'embeds' in data: data = data['embeds'][0]
            embed = discord.Embed.from_dict(data)
        except: pass
    if not embed:
        embed = discord.Embed(title="🎛️ Contrôle des Salons Vocaux", description="Gérez votre salon ici.", color=NEON_BLUE)
        embed.set_footer(text="Système TempVoice Poxel")
    await interaction.channel.send(embed=embed, view=VoiceDashboardView())
    await interaction.followup.send("✅ Panneau de contrôle posté !", ephemeral=True)

# --- CLASSES AUXILIAIRES ---
class HubSelectView(View):
    def __init__(self, client, action: str):
        super().__init__(timeout=180)
        self.client = client
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
    def __init__(self, client):
        super().__init__(timeout=300)
        self.client = client
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
    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=1)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Panneau de configuration principal:", view=MainConfigView(self.client))

# --- DESIGN MODALS ---
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
# 12. MESSAGES DE BIENVENUE/DÉPART (PIXEL-GREETING)
# ==================================================================================================

class WelcomeDMModal(Modal, title="Configurer le MP de Bienvenue"):
    def __init__(self):
        super().__init__()
        dm_config = db['settings'].get('welcome_dm', {})
        self.title_input = TextInput(label="Titre", default=dm_config.get('title'), required=False)
        self.description_input = TextInput(label="Description", style=discord.TextStyle.paragraph, default=dm_config.get('description'), required=False)
        self.color_input = TextInput(label="Couleur", default=dm_config.get('color'), required=False)
        self.image_url_input = TextInput(label="Image", default=dm_config.get('image_url'), required=False)
        self.json_input = TextInput(label="JSON Discohook (Prioritaire)", style=discord.TextStyle.paragraph, default=dm_config.get('json_data', ''), required=False)
        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.color_input)
        self.add_item(self.image_url_input)
        self.add_item(self.json_input)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db['settings']['welcome_dm'].update({
            'title': self.title_input.value, 'description': self.description_input.value,
            'color': self.color_input.value, 'image_url': self.image_url_input.value or None,
            'json_data': self.json_input.value.strip() or None
        })
        save_data(db)
        await interaction.followup.send("Configuration MP sauvegardée.", ephemeral=True)

class WelcomeDMConfigView(View):
    def __init__(self, client):
        super().__init__(timeout=300)
        self.client = client
        self.update_toggle_button()
    def update_toggle_button(self):
        for item in self.children[:]:
            if getattr(item, 'custom_id', None) == 'toggle_welcome_dm': self.remove_item(item)
        is_enabled = db['settings'].get('welcome_dm', {}).get("enabled", False)
        label = "Désactiver le MP" if is_enabled else "Activer le MP"
        style = discord.ButtonStyle.danger if is_enabled else discord.ButtonStyle.success
        toggle_button = Button(label=label, style=style, emoji="✅" if is_enabled else "❌", custom_id="toggle_welcome_dm", row=0)
        toggle_button.callback = self.toggle_dm
        self.add_item(toggle_button)
    @discord.ui.button(label="Modifier le Contenu", style=discord.ButtonStyle.primary, emoji="✏️", row=1)
    async def edit_content(self, interaction: discord.Interaction, button: Button): await interaction.response.send_modal(WelcomeDMModal())
    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=1)
    async def back_button(self, interaction: discord.Interaction, button: Button): await interaction.response.edit_message(content="💌 Configuration Pixel-Greeting :", view=PixelGreetingConfigView())
    async def toggle_dm(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        current = db['settings'].get('welcome_dm', {}).get("enabled", False)
        db['settings']['welcome_dm']["enabled"] = not current
        save_data(db)
        self.update_toggle_button()
        await interaction.edit_original_response(view=self)
        await interaction.followup.send(f"MP {'activé' if not current else 'désactivé'}.", ephemeral=True)

class GreetingChannelSelectView(View):
    def __init__(self, greeting_type: str):
        super().__init__(timeout=60)
        self.greeting_type = greeting_type
        self.channel_select = discord.ui.ChannelSelect(channel_types=[discord.ChannelType.text, discord.ChannelType.news], placeholder="Choisir le salon...")
        self.channel_select.callback = self.on_select
        self.add_item(self.channel_select)
    async def on_select(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db['settings'][f"{self.greeting_type}_channel_id"] = self.channel_select.values[0].id
        save_data(db)
        await interaction.followup.send(f"✅ Salon de **{self.greeting_type}** défini.", ephemeral=True)
        self.channel_select.disabled = True
        await interaction.edit_original_response(view=self)

class SetGreetingMessageModal(Modal):
    def __init__(self, type: str):
        super().__init__(title=f"Message de {type.capitalize()}")
        self.type = type
        self.message_input = TextInput(label="Message / JSON", style=discord.TextStyle.paragraph, default=db['settings'].get(f"{self.type}_message"), required=True)
        self.add_item(self.message_input)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db['settings'][f"{self.type}_message"] = self.message_input.value
        save_data(db)
        await interaction.followup.send(f"Message de {self.type} mis à jour.", ephemeral=True)

class PixelGreetingConfigView(View):
    def __init__(self):
        super().__init__(timeout=300)
    @discord.ui.button(label="Salon de Bienvenue", style=discord.ButtonStyle.primary, emoji="📥", row=0)
    async def set_welcome_channel(self, interaction: discord.Interaction, button: Button): await interaction.response.send_message("Où afficher les bienvenues ?", view=GreetingChannelSelectView("welcome"), ephemeral=True)
    @discord.ui.button(label="Message de Bienvenue", style=discord.ButtonStyle.success, emoji="💬", row=0)
    async def set_welcome_message(self, interaction: discord.Interaction, button: Button): await interaction.response.send_modal(SetGreetingMessageModal("welcome"))
    @discord.ui.button(label="Message Privé de Bienvenue", style=discord.ButtonStyle.blurple, emoji="📧", row=1)
    async def configure_welcome_dm(self, interaction: discord.Interaction, button: Button): await interaction.response.edit_message(content="⚙️ Config MP Bienvenue :", view=WelcomeDMConfigView(client))
    @discord.ui.button(label="Salon de Départ", style=discord.ButtonStyle.secondary, emoji="📤", row=2)
    async def set_farewell_channel(self, interaction: discord.Interaction, button: Button): await interaction.response.send_message("Où afficher les départs ?", view=GreetingChannelSelectView("farewell"), ephemeral=True)
    @discord.ui.button(label="Message de Départ", style=discord.ButtonStyle.danger, emoji="💔", row=2)
    async def set_farewell_message(self, interaction: discord.Interaction, button: Button): await interaction.response.send_modal(SetGreetingMessageModal("farewell"))
    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=3)
    async def back_button(self, interaction: discord.Interaction, button: Button): await interaction.response.edit_message(content="Panneau principal:", view=MainConfigView(client))


# ==================================================================================================
# 13. SALON DES RÈGLES (RULE-GATE)
# ==================================================================================================

class RulesPasswordModal(Modal, title="Accepter le Règlement"):
    password_input = TextInput(label="Mot de Passe du Règlement", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        submitted_password = self.password_input.value.strip()
        required_password = db['settings'].get("rules_password", "PIXEL")
        
        if submitted_password.upper() == required_password.upper():
            role_id = db['settings'].get("rules_role_id")
            if not role_id:
                await interaction.followup.send("Erreur: Rôle d'accès non configuré.", ephemeral=True)
                return
            
            role = interaction.guild.get_role(role_id)
            if not role:
                await interaction.followup.send("Erreur: Le rôle configuré est introuvable.", ephemeral=True)
                return

            try:
                await interaction.user.add_roles(role, reason="Règlement accepté")
                await interaction.followup.send(f"✅ **ACCÈS AUTORISÉ !** Le rôle {role.mention} vous a été attribué.", ephemeral=True)
                await trigger_avatar_change('rules_accepted')
            except discord.Forbidden:
                await interaction.followup.send("Erreur: Je n'ai pas la permission de vous donner ce rôle.", ephemeral=True)
        else:
            await interaction.followup.send(
                "🚫 Mot de passe incorrect. Veuillez relire attentivement le règlement et réessayer.",
                ephemeral=True
            )

class RulesAcceptView(View):
    def __init__(self, client):
        super().__init__(timeout=None)
        self.client = client
    
    @discord.ui.button(label="ACCEPTER LE RÈGLEMENT & JOUER", style=discord.ButtonStyle.success, emoji="✅", custom_id="accept_rules_button")
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RulesPasswordModal())

class RulesConfigModal(Modal, title="Configurer le Contenu des Règles"):
    def __init__(self):
        super().__init__()
        self.title_input = TextInput(label="Titre de l'embed", default=db['settings'].get('rules_embed_title'))
        # Label mis à jour pour indiquer JSON
        self.content_input = TextInput(label="Contenu/JSON (Mdp caché ici)", style=discord.TextStyle.paragraph, default=db['settings'].get('rules_embed_content'))
        self.password_input = TextInput(label="Mot de passe requis", default=db['settings'].get('rules_password'))
        self.color_input = TextInput(label="Couleur de l'embed (Hex)", default=db['settings'].get('rules_embed_color'))
        self.add_item(self.title_input)
        self.add_item(self.content_input)
        self.add_item(self.password_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db['settings']['rules_embed_title'] = self.title_input.value
        db['settings']['rules_embed_content'] = self.content_input.value
        db['settings']['rules_password'] = self.password_input.value
        db['settings']['rules_embed_color'] = self.color_input.value
        save_data(db)
        await interaction.followup.send("Configuration des règles sauvegardée.", ephemeral=True)

class RuleGateConfigView(View):
    def __init__(self, client):
        super().__init__(timeout=300)
        self.client = client

    @discord.ui.button(label="Définir Salon", style=discord.ButtonStyle.primary, emoji="📍")
    async def set_channel(self, interaction: discord.Interaction, button: Button):
        view = View()
        select = discord.ui.ChannelSelect(placeholder="Choisissez le salon pour les règles...")

        async def select_callback(inter: discord.Interaction):
            channel = select.values[0]
            db['settings']['rules_channel_id'] = channel.id
            save_data(db)
            await inter.response.send_message(f"Salon des règles défini sur {channel.mention}.", ephemeral=True)
            for item in view.children: item.disabled = True
            await interaction.edit_original_response(view=view)

        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("Choisissez le salon dans le menu ci-dessous :", view=view, ephemeral=True)

    @discord.ui.button(label="Définir Rôle", style=discord.ButtonStyle.primary, emoji="🔑")
    async def set_role(self, interaction: discord.Interaction, button: Button):
        view = View()
        select = discord.ui.RoleSelect(placeholder="Choisissez le rôle à attribuer...")

        async def select_callback(inter: discord.Interaction):
            role = select.values[0]
            db['settings']['rules_role_id'] = role.id
            save_data(db)
            await inter.response.send_message(f"Rôle d'accès défini sur {role.mention}.", ephemeral=True)
            for item in view.children: item.disabled = True
            await interaction.edit_original_response(view=view)

        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("Choisissez le rôle dans le menu ci-dessous :", view=view, ephemeral=True)

    @discord.ui.button(label="Éditer Contenu", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit_content(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RulesConfigModal())

    @discord.ui.button(label="Publier / Mettre à jour", style=discord.ButtonStyle.success, emoji="🚀", row=1)
    async def publish_rules(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        channel_id = db['settings'].get('rules_channel_id')
        if not channel_id:
            await interaction.followup.send("Veuillez d'abord définir un salon.", ephemeral=True)
            return
        channel = self.client.get_channel(channel_id)
        if not channel:
            await interaction.followup.send("Le salon configuré est introuvable.", ephemeral=True)
            return

        # LOGIQUE INTELLIGENTE : DÉTECTION JSON OU TEXTE
        content_raw = db['settings'].get('rules_embed_content', '')
        embed = None
        
        try:
            # On tente de parser en JSON (Discohook)
            if content_raw.strip().startswith('{'):
                data = json.loads(content_raw)
                # Discohook met parfois tout dans 'embeds', parfois direct
                embed_data = data['embeds'][0] if 'embeds' in data and data['embeds'] else data
                embed = discord.Embed.from_dict(embed_data)
        except Exception:
            pass # Si erreur, on continue vers le mode texte classique

        # Si pas de JSON valide, on crée l'embed classique
        if not embed:
            color_hex = db['settings'].get('rules_embed_color', '0x000000').replace("#", "")
            try: color_int = int(color_hex, 16)
            except: color_int = NEON_PURPLE
            
            embed = discord.Embed(
                title=db['settings'].get('rules_embed_title'),
                description=content_raw,
                color=color_int
            )

        await channel.send(embed=embed, view=RulesAcceptView(self.client))
        await interaction.followup.send(f"Embed des règles publié dans {channel.mention}.", ephemeral=True)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=1)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Panneau de configuration principal:", view=MainConfigView(self.client))


# ==================================================================================================
# 14. CLASSES DE CONFIGURATION (CENSURE, GENERAL, AVATAR, AUTOMOD, PRESENTATION, LOGS)
# ==================================================================================================

# --- CENSURE ---
class CensorWordModal(Modal):
    def __init__(self, action: str):
        super().__init__(title=f"{action.capitalize()} un mot")
        self.action = action
        self.word_input = TextInput(label="Mot (un seul, sans ponctuation)", required=True)
        self.add_item(self.word_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        word = self.word_input.value.lower().strip()
        censored_words = db['settings'].get('censored_words', [])

        if self.action == "ajouter":
            if word not in censored_words:
                censored_words.append(word)
                await interaction.followup.send(f"Le mot `{word}` a été ajouté à la censure.", ephemeral=True)
            else:
                await interaction.followup.send(f"Le mot `{word}` est déjà dans la liste.", ephemeral=True)
        elif self.action == "retirer":
            if word in censored_words:
                censored_words.remove(word)
                await interaction.followup.send(f"Le mot `{word}` a été retiré de la censure.", ephemeral=True)
            else:
                await interaction.followup.send(f"Le mot `{word}` n'était pas dans la liste.", ephemeral=True)
        
        db['settings']['censored_words'] = censored_words
        save_data(db)

class CensorConfigView(View):
    def __init__(self, client):
        super().__init__(timeout=300)
        self.client = client
        self.update_toggle_button()

    def update_toggle_button(self):
        for item in self.children[:]:
            if getattr(item, 'custom_id', None) == 'toggle_censor':
                self.remove_item(item)

        is_enabled = db['settings'].get("censor_enabled", True)
        label = "Censure : ACTIVÉE" if is_enabled else "Censure : DÉSACTIVÉE"
        style = discord.ButtonStyle.success if is_enabled else discord.ButtonStyle.danger
        emoji = "✅" if is_enabled else "❌"
        
        toggle_button = Button(label=label, style=style, emoji=emoji, custom_id="toggle_censor", row=0)
        toggle_button.callback = self.toggle_censor
        self.add_item(toggle_button)

    @discord.ui.button(label="Ajouter un Mot", style=discord.ButtonStyle.primary, emoji="➕", row=1)
    async def add_word(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CensorWordModal(action="ajouter"))

    @discord.ui.button(label="Retirer un Mot", style=discord.ButtonStyle.primary, emoji="➖", row=1)
    async def remove_word(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CensorWordModal(action="retirer"))

    @discord.ui.button(label="Voir la Liste", style=discord.ButtonStyle.secondary, emoji="📄", row=1)
    async def view_list(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        words = db['settings'].get('censored_words', [])
        if not words:
            await interaction.followup.send("La liste des mots censurés est vide.", ephemeral=True)
        else:
            description = ", ".join(f"`{w}`" for w in words)
            embed = discord.Embed(title="Liste des Mots Censurés", description=description, color=NEON_BLUE)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=2)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Panneau de configuration principal:", view=MainConfigView(self.client))

    async def toggle_censor(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        current_state = db['settings'].get("censor_enabled", True)
        db['settings']["censor_enabled"] = not current_state
        save_data(db)
        
        self.update_toggle_button()
        await interaction.edit_original_response(view=self)
        await interaction.followup.send(f"La censure est maintenant {'activée' if not current_state else 'désactivée'}.", ephemeral=True)

# --- GENERAL & PRESENTATION & LOGS ---
class PurgeSettingsModal(Modal, title="Configurer Purge d'Infractions"):
    def __init__(self):
        super().__init__()
        self.duration_input = TextInput(label="Durée avant purge (jours)", default=str(db['settings'].get("purge_duration_days", 180)))
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            days = int(self.duration_input.value)
            if days <= 0:
                await interaction.followup.send("La durée doit être d'au moins 1 jour.", ephemeral=True)
                return
            db['settings']['purge_duration_days'] = days
            save_data(db)
            await interaction.followup.send(f"La durée de purge des infractions est maintenant de {days} jours.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Veuillez entrer un nombre de jours valide.", ephemeral=True)

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
        await interaction.followup.send("Emojis de vie mis à jour ! Utilisez /vies pour voir le changement.", ephemeral=True)

class PresentationConfigModal(Modal, title="Configurer la Présentation"):
    def __init__(self):
        super().__init__()
        data = db['settings'].get('presentation_embed_data', {})
        self.titre = TextInput(label="Titre", default=data.get('title', "Poxel"))
        self.desc = TextInput(label="Description", style=discord.TextStyle.paragraph, default=data.get('description', "Description du bot..."))
        self.color = TextInput(label="Couleur (Hex)", default=data.get('color', "#6441a5"))
        self.add_item(self.titre)
        self.add_item(self.desc)
        self.add_item(self.color)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db['settings']['presentation_embed_data'] = {
            "title": self.titre.value,
            "description": self.desc.value,
            "color": self.color.value,
            "image_url": None, 
            "link_url": None
        }
        save_data(db)
        await interaction.followup.send("Configuration de la présentation mise à jour.", ephemeral=True)

class SetLogChannelModal(Modal, title="Configurer Salon Logs Modération"):
    def __init__(self):
        super().__init__()
        self.channel_id_input = TextInput(
            label="ID du Salon de Logs", 
            placeholder="Laissez vide pour désactiver", 
            required=False,
            default=str(db['settings'].get("auto_mod_log_channel_id") or "")
        )
        self.add_item(self.channel_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel_id_str = self.channel_id_input.value.strip()
        
        if channel_id_str:
            try:
                channel_id = int(channel_id_str)
                channel = interaction.guild.get_channel(channel_id)
                if not channel:
                    await interaction.followup.send("⚠️ Attention : Ce salon semble introuvable sur le serveur, mais l'ID a été enregistré.", ephemeral=True)
                else:
                    await interaction.followup.send(f"Salon de logs défini sur {channel.mention}.", ephemeral=True)
                
                db['settings']['auto_mod_log_channel_id'] = channel_id
            except ValueError:
                await interaction.followup.send("L'ID doit être un nombre valide.", ephemeral=True)
                return
        else:
            db['settings']['auto_mod_log_channel_id'] = None
            await interaction.followup.send("Logs de modération désactivés.", ephemeral=True)
            
        save_data(db)

# --- NOUVEAU: VUE DE CONFIGURATION SYSTÈME (MENU DÉROULANT CATÉGORIE) ---
class GenericTicketView(View):
    def __init__(self, system_type, label, emoji):
        super().__init__(timeout=None)
        self.system_type = system_type
        # Bouton statique pour l'instant - La logique d'interaction (ouverture ticket) 
        # nécessiterait une View persistante complexe non incluse ici pour rester simple.
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
            
            # Embed Custom ou Défaut
            custom_json = db.get('default_embeds', {}).get(self.system_type)
            if custom_json:
                try: embed = discord.Embed.from_dict(json.loads(custom_json))
                except: embed = discord.Embed(title=conf['title'], description=conf['desc'], color=NEON_BLUE)
            else:
                embed = discord.Embed(title=conf['title'], description=conf['desc'], color=NEON_BLUE)
            
            view = GenericTicketView(self.system_type, conf['btn'], conf['emoji'])
            await channel.send(embed=embed, view=view)
            
            # Sauvegarde config
            db['settings'][f'{self.system_type}_config'] = {"channel_id": channel.id, "category_id": category.id}
            save_data(db)
            
            await interaction.followup.send(f"✅ Système **{self.system_type}** installé avec succès dans {channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Erreur lors de l'installation : {e}", ephemeral=True)

class TicketsSupportView(View):
    """Sous-menu pour les boutons de configuration des tickets."""
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

class GeneralSettingsView(View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Emojis de Vie", style=discord.ButtonStyle.secondary, emoji="❤️", row=0)
    async def set_life_emojis(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(LifeEmojiConfigModal())

    @discord.ui.button(label="Durée Purge Infractions", style=discord.ButtonStyle.primary, emoji="🗓️", row=0)
    async def set_purge_duration(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PurgeSettingsModal())

    @discord.ui.button(label="Salon Logs Mod", style=discord.ButtonStyle.secondary, emoji="📜", row=0)
    async def set_log_channel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(SetLogChannelModal())

    @discord.ui.button(label="Présentation Bot", style=discord.ButtonStyle.success, emoji="📢", row=1)
    async def config_presentation(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PresentationConfigModal())

    @discord.ui.button(label="Tickets & Support", style=discord.ButtonStyle.blurple, emoji="🎫", row=2)
    async def config_tickets(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Configuration des Panels de Support :", view=TicketsSupportView(), ephemeral=True)

    # --- SUPPRIMÉ : BOUTON ANNONCE ---
    # --- SUPPRIMÉ : BOUTON MEMBERCOUNT ---

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=3)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        if 'client' in globals():
             await interaction.response.edit_message(content="Panneau de configuration principal:", view=MainConfigView(client))
        else:
             await interaction.response.send_message("Erreur: Client non trouvé.", ephemeral=True)

# --- AVATARS ---
class AvatarTriggerEditModal(Modal):
    def __init__(self, trigger_key=None, view_ref=None):
        super().__init__(title=f"Éditer: {trigger_key}" if trigger_key else "Nouveau Déclencheur")
        self.trigger_key = trigger_key
        self.view_ref = view_ref
        trigger_data = db.get('avatar_triggers', {}).get(trigger_key, {})
        
        self.key_input = TextInput(label="Clé (ex: warn, custom)", default=trigger_key)
        self.url_input = TextInput(label="URL Image (vide = suppr)", default=trigger_data.get('image_url'), required=False)
        self.duration_input = TextInput(label="Durée (ex: 5m, 1h, 0s)", default=trigger_data.get('duration', '0s'), required=False)

        self.add_item(self.key_input)
        self.add_item(self.url_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        key = self.key_input.value.strip()
        url = self.url_input.value.strip() or None
        duration = self.duration_input.value.strip() or '0s'

        if not key:
            return await interaction.followup.send("La clé est vide.", ephemeral=True)

        if url is None:
            if key in db.get('avatar_triggers', {}):
                del db['avatar_triggers'][key]
                save_data(db)
                await interaction.followup.send(f"Déclencheur '{key}' supprimé.", ephemeral=True)
        else:
            db.setdefault('avatar_triggers', {})[key] = {'image_url': url, 'duration': duration}
            save_data(db)
            await interaction.followup.send(f"Déclencheur '{key}' sauvegardé.", ephemeral=True)
        
        if self.view_ref and hasattr(self.view_ref, 'update_trigger_select'):
            self.view_ref.update_trigger_select()

class AvatarTriggerDeleteView(View):
    def __init__(self):
        super().__init__(timeout=180)
        triggers = db.get('avatar_triggers', {})
        options = []
        if triggers:
            for key, config in triggers.items():
                name = AVATAR_TRIGGERS_MAP.get(key, key)
                if config.get('image_url'):
                    options.append(discord.SelectOption(label=name, value=key))

        if not options:
            self.add_item(Select(placeholder="Rien à supprimer.", options=[discord.SelectOption(label="...", value="none")], disabled=True))
        else:
            select = Select(placeholder="Supprimer des déclencheurs...", options=options, max_values=min(len(options), 25))
            select.callback = self.on_select
            self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.data['values'][0] == "none": return
        await interaction.response.defer(ephemeral=True)
        for k in interaction.data['values']:
            if k in db['avatar_triggers']: del db['avatar_triggers'][k]
        save_data(db)
        await interaction.followup.send("Déclencheurs supprimés.", ephemeral=True)

class AvatarTriggerManagementView(View):
    def __init__(self, client):
        super().__init__(timeout=300)
        self.client = client
        self.update_trigger_select()

    def update_trigger_select(self):
        for item in self.children:
            if isinstance(item, Select): self.remove_item(item)
        
        triggers = db.get('avatar_triggers', {})
        options = []
        for name in list(AVATAR_TRIGGERS_MAP.keys()) + [k for k in triggers if k not in AVATAR_TRIGGERS_MAP]:
             if name in triggers and triggers[name].get('image_url'):
                friendly_name = AVATAR_TRIGGERS_MAP.get(name, name)
                options.append(discord.SelectOption(label=f"Gérer: {friendly_name}", value=name))
        
        if not options:
            self.add_item(Select(placeholder="Aucun déclencheur.", options=[discord.SelectOption(label="...", value="none")], disabled=True))
        else:
            select = Select(placeholder="Modifier un déclencheur...", options=options)
            select.callback = self.on_select_trigger
            self.add_item(select)

    async def on_select_trigger(self, interaction: discord.Interaction):
        if interaction.data['values'][0] == "none": return
        await interaction.response.send_modal(AvatarTriggerEditModal(trigger_key=interaction.data['values'][0], view_ref=self))

    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success, emoji="➕", row=1)
    async def add(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AvatarTriggerEditModal(view_ref=self))

    @discord.ui.button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def delete(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Suppression :", view=AvatarTriggerDeleteView(), ephemeral=True)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=2)
    async def back(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Configuration Avatars :", view=AvatarConfigView(self.client))

class AvatarSetDefaultModal(Modal, title="Avatar par Défaut"):
    url_input = TextInput(label="URL de l'image (vide pour supprimer)", required=False)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db['settings']['avatar_default_url'] = self.url_input.value.strip() or None
        save_data(db)
        await interaction.followup.send("Avatar par défaut mis à jour.", ephemeral=True)

class AvatarSetCooldownModal(Modal, title="Cooldown Avatars"):
    cooldown_input = TextInput(label="Secondes", default=str(db['settings'].get("avatar_cooldown_seconds", 300)))
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            db['settings']['avatar_cooldown_seconds'] = int(self.cooldown_input.value)
            save_data(db)
            await interaction.followup.send("Cooldown mis à jour.", ephemeral=True)
        except: await interaction.followup.send("Nombre invalide.", ephemeral=True)

class AvatarConfigView(View):
    def __init__(self, client):
        super().__init__(timeout=300)
        self.client = client
        self.update_toggle()

    def update_toggle(self):
        for i in self.children[:]:
            if getattr(i, 'custom_id', '') == 'tgl': self.remove_item(i)
        
        on = db['settings'].get("avatar_enabled", True)
        label = "Avatars : ACTIVÉS" if on else "Avatars : DÉSACTIVÉS"
        style = discord.ButtonStyle.success if on else discord.ButtonStyle.danger
        emoji = "✅" if on else "❌"
        
        btn = Button(label=label, style=style, emoji=emoji, custom_id="tgl", row=0)
        btn.callback = self.toggle
        self.add_item(btn)

    async def toggle(self, interaction: discord.Interaction):
        db['settings']["avatar_enabled"] = not db['settings'].get("avatar_enabled", True)
        save_data(db)
        self.update_toggle()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Définir Avatar Défaut", style=discord.ButtonStyle.primary, emoji="🖼️", row=1)
    async def set_default(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AvatarSetDefaultModal())

    @discord.ui.button(label="Gérer Déclencheurs", style=discord.ButtonStyle.primary, emoji="🔧", row=1)
    async def manage(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Gestion :", view=AvatarTriggerManagementView(self.client), ephemeral=True)

    @discord.ui.button(label="Cooldown", style=discord.ButtonStyle.secondary, emoji="⏳", row=2)
    async def cooldown(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AvatarSetCooldownModal())

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=2)
    async def back(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Panneau principal:", view=MainConfigView(self.client))

# --- AUTOMOD (NOVA-GUARD) ---
class ActionEditModal(Modal, title="Modifier Sanction"):
    def __init__(self, client, profile_name, action_index=None, view_ref=None):
        super().__init__()
        self.client = client
        self.profile_name = profile_name
        self.action_index = action_index
        self.view_ref = view_ref
        self.type_input = TextInput(label="Type (warn, mute, kick, tempban, ban)", required=True)
        self.points_input = TextInput(label="Vies perdues", default="1", required=True)
        self.duration_input = TextInput(label="Durée (mute/tempban)", required=False, placeholder="Ex: 15m")
        self.add_item(self.type_input)
        self.add_item(self.points_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        atype = self.type_input.value.lower().strip()
        if atype not in ['warn', 'mute', 'kick', 'tempban', 'ban']:
            return await interaction.followup.send("Type invalide.", ephemeral=True)
        try: pts = int(self.points_input.value)
        except: return await interaction.followup.send("Points invalides.", ephemeral=True)
        
        action = {"type": atype, "points": pts, "duration": self.duration_input.value.strip() or None}
        profile = db['auto_mod_profiles'][self.profile_name]
        if self.action_index is not None: profile['actions'][self.action_index] = action
        else: profile.setdefault('actions', []).append(action)
        save_data(db)
        await interaction.followup.send("Sanction sauvegardée.", ephemeral=True)

class ProfileDetailView(View):
    def __init__(self, client, profile_name):
        super().__init__(timeout=300)
        self.client = client
        self.profile_name = profile_name

    def create_embed(self):
        profile = db['auto_mod_profiles'].get(self.profile_name, {})
        desc = f"**Mots-clés:** ` {', '.join(profile.get('keywords', []))} `\n"
        desc += f"**Cooldown:** `{profile.get('cooldown_seconds', 30)}s`\n\n**Sanctions:**\n"
        for i, act in enumerate(profile.get('actions', [])):
            dur = f" ({act.get('duration')})" if act.get('duration') else ""
            desc += f"`{i+1}.` **{act['type'].upper()}**{dur} - **{act['points']} vie(s)**\n"
        return discord.Embed(title=f"Profil: {self.profile_name}", description=desc, color=NEON_BLUE)

    @discord.ui.button(label="Ajouter Sanction", style=discord.ButtonStyle.success, emoji="➕")
    async def add(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ActionEditModal(self.client, self.profile_name, view_ref=self))

    @discord.ui.button(label="Suppr. Dernière", style=discord.ButtonStyle.danger, emoji="➖")
    async def rem(self, interaction: discord.Interaction, button: Button):
        p = db['auto_mod_profiles'].get(self.profile_name, {})
        if p.get('actions'):
            p['actions'].pop()
            save_data(db)
            await interaction.message.edit(embed=self.create_embed(), view=self)
            await interaction.response.send_message("Supprimée.", ephemeral=True)

    @discord.ui.button(label="Suppr. Profil", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def delete(self, interaction: discord.Interaction, button: Button):
        if self.profile_name in db['auto_mod_profiles']:
            del db['auto_mod_profiles'][self.profile_name]
            save_data(db)
        await interaction.response.edit_message(content="Profil supprimé.", view=AutoModConfigView(self.client), embed=None)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=1)
    async def back(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Configuration Nova-Guard :", view=AutoModConfigView(self.client), embed=None)

class ProfileEditModal(Modal):
    def __init__(self, client, view_ref=None):
        super().__init__(title="Nouveau Profil")
        self.client = client
        self.view_ref = view_ref
        self.name_input = TextInput(label="Nom du Profil", required=True)
        self.keywords_input = TextInput(label="Mots-clés (séparés par virgule)", style=discord.TextStyle.paragraph, required=True)
        self.cooldown_input = TextInput(label="Cooldown (sec)", default="30", required=True)
        self.add_item(self.name_input)
        self.add_item(self.keywords_input)
        self.add_item(self.cooldown_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.name_input.value.strip()
        if name in db['auto_mod_profiles']: return await interaction.followup.send("Existe déjà.", ephemeral=True)
        try: cd = int(self.cooldown_input.value)
        except: return await interaction.followup.send("Cooldown invalide.", ephemeral=True)
        
        db['auto_mod_profiles'][name] = {
            "keywords": [k.strip().lower() for k in self.keywords_input.value.split(',') if k.strip()],
            "cooldown_seconds": cd,
            "actions": []
        }
        save_data(db)
        if self.view_ref: self.view_ref.update_profile_select()
        await interaction.followup.send(f"Profil '{name}' créé.", ephemeral=True)

class AutoModConfigView(View):
    def __init__(self, client):
        super().__init__(timeout=300)
        self.client = client
        self.update_toggle()
        self.update_profile_select()

    def update_toggle(self):
        for i in self.children[:]:
            if getattr(i, 'custom_id', '') == 'tgl': self.remove_item(i)
        
        on = db['settings'].get("auto_mod_enabled", True)
        # DESIGN UNIFIÉ
        label = "Nova-Guard : ACTIVÉ" if on else "Nova-Guard : DÉSACTIVÉ"
        style = discord.ButtonStyle.success if on else discord.ButtonStyle.danger
        emoji = "✅" if on else "❌"
        
        btn = Button(label=label, style=style, emoji=emoji, custom_id="tgl", row=0)
        btn.callback = self.toggle
        self.add_item(btn)

    def update_profile_select(self):
        for item in self.children[:]:
            if isinstance(item, Select): self.remove_item(item)
        
        opts = [discord.SelectOption(label=n, value=n) for n in db.get('auto_mod_profiles', {})]
        if not opts:
            self.add_item(Select(placeholder="Aucun profil.", options=[discord.SelectOption(label="...", value="none")], disabled=True))
        else:
            sel = Select(placeholder="Gérer un profil...", options=opts)
            sel.callback = self.on_select
            self.add_item(sel)

    async def toggle(self, interaction: discord.Interaction):
        db['settings']["auto_mod_enabled"] = not db['settings'].get("auto_mod_enabled", True)
        save_data(db)
        self.update_toggle()
        self.update_profile_select() # Rebuild select to maintain order
        await interaction.response.edit_message(view=self)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.data['values'][0] == "none": return
        name = interaction.data['values'][0]
        view = ProfileDetailView(self.client, name)
        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=True)

    @discord.ui.button(label="Créer Profil", style=discord.ButtonStyle.success, emoji="➕", row=1)
    async def add(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ProfileEditModal(self.client, view_ref=self))

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=1)
    async def back(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Panneau principal:", view=MainConfigView(self.client))

# ==================================================================================================
# 15. MENU PRINCIPAL DE CONFIGURATION (MainConfigView) - COMPLET
# ==================================================================================================

class MainConfigView(View):
    def __init__(self, client):
        super().__init__(timeout=300)
        self.client = client

    @discord.ui.button(label="Nova-Guard (Auto-Mod)", style=discord.ButtonStyle.blurple, emoji="🛡️", row=0)
    async def auto_mod(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="⚙️ Configuration Nova-Guard :", view=AutoModConfigView(self.client))

    @discord.ui.button(label="Salons Vocaux", style=discord.ButtonStyle.primary, emoji="🎤", row=0)
    async def voice_config(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Configuration Vocale :", view=VoiceHubConfigView(self.client))

    @discord.ui.button(label="Bienvenue & Adieu", style=discord.ButtonStyle.success, emoji="👋", row=1)
    async def greeting(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="💌 Configuration Pixel-Greeting :", view=PixelGreetingConfigView())

    @discord.ui.button(label="Règles (Rule-Gate)", style=discord.ButtonStyle.red, emoji="📜", row=1)
    async def rules(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="🔒 Configuration Rule-Gate :", view=RuleGateConfigView(self.client))

    @discord.ui.button(label="Censure Mots", style=discord.ButtonStyle.secondary, emoji="🤬", row=2)
    async def censor(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="📝 Censure :", view=CensorConfigView(self.client))

    @discord.ui.button(label="Avatars Dynamiques", style=discord.ButtonStyle.primary, emoji="🎭", row=2)
    async def avatar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="🎭 Avatars :", view=AvatarConfigView(self.client))

    @discord.ui.button(label="Paramètres Généraux", style=discord.ButtonStyle.secondary, emoji="⚙️", row=3)
    async def general(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="⚙️ Général :", view=GeneralSettingsView())

# --- Classes Welcome (Exemple Design Unifié) ---
class WelcomeDMConfigView(View):
    def __init__(self, client):
        super().__init__(timeout=300)
        self.client = client
        self.update_toggle()

    def update_toggle(self):
        for i in self.children[:]:
            if getattr(i, 'custom_id', '') == 'tgl': self.remove_item(i)
        
        on = db['settings'].get('welcome_dm', {}).get("enabled", False)
        # DESIGN UNIFIÉ
        label = "MP Bienvenue : ACTIVÉ" if on else "MP Bienvenue : DÉSACTIVÉ"
        style = discord.ButtonStyle.success if on else discord.ButtonStyle.danger
        emoji = "✅" if on else "❌"
        
        btn = Button(label=label, style=style, emoji=emoji, custom_id="tgl", row=0)
        btn.callback = self.toggle
        self.add_item(btn)

    async def toggle(self, interaction: discord.Interaction):
        curr = db['settings'].get('welcome_dm', {}).get("enabled", False)
        db['settings']['welcome_dm']["enabled"] = not curr
        save_data(db)
        self.update_toggle()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Modifier Contenu", style=discord.ButtonStyle.primary, emoji="✏️", row=1)
    async def edit(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WelcomeDMModal())

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, emoji="↩️", row=1)
    async def back(self, interaction: discord.Interaction, button: Button):
        # Redirection vers le menu Greeting global (Partie 4) ou Main
        await interaction.response.edit_message(content="Menu Principal:", view=MainConfigView(self.client))

# ==================================================================================================
# 16. EMBED BUILDER
# ==================================================================================================

embed_group = app_commands.Group(name="embed", description="Crée, configure et publie des embeds interactifs.", default_permissions=discord.Permissions(administrator=True))

class EmbedJSONModal(Modal, title="Importer Embed depuis JSON"):
    json_data = TextInput(label="Code JSON (Discohook)", style=discord.TextStyle.paragraph, placeholder='{"title": "...", "description": "..."}', required=True)
    content_input = TextInput(label="Texte hors embed (@everyone...)", placeholder="Message normal au dessus de l'embed", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        try:
            data = json.loads(self.json_data.value)
            
            embed_data = {}
            content = self.content_input.value.strip()
            
            if 'embeds' in data and isinstance(data['embeds'], list) and len(data['embeds']) > 0:
                embed_data = data['embeds'][0]
            elif 'title' in data or 'description' in data:
                embed_data = data
            
            if not content and 'content' in data:
                content = data['content']

            db['embed_builders'][user_id] = {
                "type": "json",
                "content": content,
                "data": embed_data,
                "reactions": db['embed_builders'].get(user_id, {}).get("reactions", [])
            }
            save_data(db)
            
            await interaction.followup.send("✅ JSON importé avec succès ! Utilisez les boutons ci-dessous pour continuer.", ephemeral=True)
            await interaction.message.edit(embed=EmbedBuilderView.generate_preview(user_id), view=EmbedBuilderView(user_id))

        except json.JSONDecodeError:
            await interaction.followup.send("❌ Erreur : Le JSON fourni est invalide.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur inattendue : {e}", ephemeral=True)

class EmbedSimpleModal(Modal, title="Créateur Simple"):
    title_input = TextInput(label="Titre")
    desc_input = TextInput(label="Description", style=discord.TextStyle.paragraph)
    color_input = TextInput(label="Couleur (Hex)", default="#6441a5")
    content_input = TextInput(label="Texte hors embed (@everyone...)", placeholder="Message normal au dessus de l'embed", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        
        color_val = 0x6441a5
        try:
            color_val = int(self.color_input.value.replace("#", ""), 16)
        except: pass

        embed_data = {
            "title": self.title_input.value,
            "description": self.desc_input.value,
            "color": color_val
        }

        db['embed_builders'][user_id] = {
            "type": "simple",
            "content": self.content_input.value.strip(),
            "data": embed_data,
            "reactions": db['embed_builders'].get(user_id, {}).get("reactions", [])
        }
        save_data(db)
        await interaction.followup.send("✅ Données mises à jour.", ephemeral=True)
        await interaction.message.edit(embed=EmbedBuilderView.generate_preview(user_id), view=EmbedBuilderView(user_id))

class ReactionRoleSelectView(View):
    def __init__(self, user_id: int, text: str, emoji: str, view_ref):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.text = text
        self.emoji = emoji
        self.view_ref = view_ref

        self.role_select = discord.ui.RoleSelect(placeholder="Choisissez le rôle à donner...")
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)

    async def role_select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        role = self.role_select.values[0]
        user_id_str = str(self.user_id)
        
        builder = db['embed_builders'].get(user_id_str)
        if not builder:
            return await interaction.followup.send("Session expirée.", ephemeral=True)

        builder.setdefault('reactions', []).append({
            "text": self.text,
            "emoji": self.emoji,
            "role_id": role.id
        })
        save_data(db)
        
        await interaction.followup.send(f"✅ Rôle {role.mention} lié à l'émoji {self.emoji}.", ephemeral=True)
        await interaction.edit_original_response(content="Menu Principal", embed=EmbedBuilderView.generate_preview(user_id_str), view=EmbedBuilderView(user_id_str))

class ReactionAddModal(Modal, title="Ajouter une Réaction"):
    def __init__(self, view_ref):
        super().__init__()
        self.view_ref = view_ref

    emoji_input = TextInput(label="Emoji", placeholder="👻")
    text_input = TextInput(label="Description (pour le message)", placeholder="Cliquez pour obtenir le rôle...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        view = ReactionRoleSelectView(interaction.user.id, self.text_input.value, self.emoji_input.value.strip(), self.view_ref)
        await interaction.response.send_message("Choisissez maintenant le rôle associé :", view=view, ephemeral=True)

class ChannelPickView(View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = str(user_id)
        
        self.channel_select = discord.ui.ChannelSelect(channel_types=[discord.ChannelType.text, discord.ChannelType.news], placeholder="Où publier l'embed ?")
        self.channel_select.callback = self.on_select
        self.add_item(self.channel_select)

    async def on_select(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = self.channel_select.values[0]
        
        builder = db['embed_builders'].get(self.user_id)
        if not builder: return await interaction.followup.send("Données introuvables.", ephemeral=True)

        try:
            embed_dict = builder['data']
            # Nettoyage des clés vides
            if 'fields' in embed_dict and not embed_dict['fields']: del embed_dict['fields']
            if 'footer' in embed_dict and not embed_dict['footer']: del embed_dict['footer']
            if 'image' in embed_dict and not embed_dict['image']: del embed_dict['image']
            if 'thumbnail' in embed_dict and not embed_dict['thumbnail']: del embed_dict['thumbnail']
            if 'author' in embed_dict and not embed_dict['author']: del embed_dict['author']

            embed = discord.Embed.from_dict(embed_dict)
            
            if builder.get('reactions'):
                desc_add = "\n\n"
                for react in builder['reactions']:
                    if react['text']:
                        desc_add += f"{react['emoji']} : {react['text']}\n"
                if len(desc_add) > 2:
                    embed.description = (embed.description or "") + desc_add

            content = builder.get('content', '')
            message = await channel.send(content=content if content else None, embed=embed)
            
            if builder.get('reactions'):
                reaction_map = {}
                for react in builder['reactions']:
                    try:
                        await message.add_reaction(react['emoji'])
                        reaction_map[react['emoji']] = react['role_id']
                    except Exception as e:
                        await interaction.followup.send(f"⚠️ Erreur ajout réaction {react['emoji']}: {e}", ephemeral=True)
                
                db.setdefault('reaction_role_messages', {})[str(message.id)] = reaction_map
                save_data(db)

            await interaction.followup.send(f"✅ Embed publié avec succès dans {channel.mention} !", ephemeral=True)
            del db['embed_builders'][self.user_id]
            save_data(db)

        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la publication : {e}", ephemeral=True)


class EmbedBuilderView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = str(user_id)

    @staticmethod
    def generate_preview(user_id):
        builder = db['embed_builders'].get(str(user_id))
        if not builder:
            return discord.Embed(title="Aucun brouillon", description="Commencez par importer un JSON ou utiliser l'éditeur simple.", color=discord.Color.light_grey())
        
        try:
            data = builder['data'].copy()
            embed = discord.Embed.from_dict(data)
            embed.set_footer(text="Prévisualisation - Poxel Builder")
            
            if builder.get('reactions'):
                field_val = ""
                for r in builder['reactions']:
                    role_id = r['role_id']
                    field_val += f"{r['emoji']} ➡️ <@&{role_id}>\n"
                embed.add_field(name="Rôles-Réactions configurés", value=field_val, inline=False)
            
            if builder.get('content'):
                embed.add_field(name="Texte hors embed", value=builder['content'], inline=False)
                
            return embed
        except:
            return discord.Embed(title="Erreur Preview", description="Le JSON semble invalide pour Discord.", color=discord.Color.red())

    @discord.ui.button(label="📋 Importer JSON", style=discord.ButtonStyle.secondary, emoji="📥", row=0)
    async def import_json(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(EmbedJSONModal())

    @discord.ui.button(label="📝 Éditeur Simple", style=discord.ButtonStyle.secondary, emoji="✏️", row=0)
    async def editor_simple(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(EmbedSimpleModal())

    @discord.ui.button(label="➕ Ajouter Réaction", style=discord.ButtonStyle.primary, emoji="🎭", row=1)
    async def add_react(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) not in db['embed_builders']:
            return await interaction.response.send_message("Veuillez d'abord créer une base d'embed (JSON ou Simple).", ephemeral=True)
        await interaction.response.send_modal(ReactionAddModal(self))

    @discord.ui.button(label="👀 Rafraîchir", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def refresh_preview(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(embed=self.generate_preview(interaction.user.id), view=self)

    @discord.ui.button(label="🚀 Publier", style=discord.ButtonStyle.success, emoji="✅", row=2)
    async def publish(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) not in db['embed_builders']:
            return await interaction.response.send_message("Rien à publier.", ephemeral=True)
        await interaction.response.send_message("Choisissez le salon de destination :", view=ChannelPickView(interaction.user.id), ephemeral=True)

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) in db['embed_builders']:
            del db['embed_builders'][str(interaction.user.id)]
            save_data(db)
        await interaction.response.edit_message(content="Opération annulée.", embed=None, view=None)


# --- NOUVEAU : SYSTÈME DE PANEL PERMANENT EMBED BUILDER ---

class EmbedPanelPermanentView(View):
    def __init__(self):
        super().__init__(timeout=None) # Vue permanente

    @discord.ui.button(label="Ouvrir le Créateur d'Embed", style=discord.ButtonStyle.primary, emoji="🛠️", custom_id="open_embed_builder")
    async def open_builder(self, interaction: discord.Interaction, button: Button):
        help_json = db.get('settings', {}).get('embed_help_json')
        help_embed = None
        
        default_help = {
            "title": "📚 Guide : Créateur d'Embeds",
            "description": "Bienvenue dans l'outil de création ! Voici comment faire :\n\n1. Allez sur **[Discohook.org](https://discohook.org)** pour designer votre embed.\n2. Copiez le **JSON** en bas de page.\n3. Cliquez sur **Importer JSON** ci-dessous et collez le code.\n4. Ajoutez des réactions si besoin.\n5. Publiez !",
            "color": 0x6441a5
        }

        if help_json:
            try:
                data = json.loads(help_json)
                if 'embeds' in data: data = data['embeds'][0]
                help_embed = discord.Embed.from_dict(data)
            except: pass
        
        if not help_embed:
            help_embed = discord.Embed.from_dict(default_help)

        user_id = str(interaction.user.id)
        if user_id not in db['embed_builders']:
            db['embed_builders'][user_id] = {} 

        await interaction.response.send_message(
            embed=help_embed,
            view=EmbedBuilderView(user_id),
            ephemeral=True
        )

class EmbedHelpConfigModal(Modal, title="Configurer le Guide (JSON)"):
    json_input = TextInput(label="JSON du Guide Explicatif", style=discord.TextStyle.paragraph, placeholder='{"title": "Guide", "description": "Lien: discohook.org...", "color": 123456}', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = json.loads(self.json_input.value)
            if 'embeds' in data: data = data['embeds'][0]
            
            db.setdefault('settings', {})['embed_help_json'] = json.dumps(data)
            save_data(db)
            await interaction.response.send_message("✅ Guide explicatif mis à jour !", ephemeral=True)
        except json.JSONDecodeError:
            await interaction.response.send_message("❌ JSON Invalide.", ephemeral=True)

@embed_group.command(name="builder", description="Ouvre le constructeur d'embed (Version simple).")
async def embed_builder_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in db['embed_builders']:
        db['embed_builders'][user_id] = {} 
    
    embed = EmbedBuilderView.generate_preview(user_id)
    await interaction.response.send_message(
        "**🛠️ Poxel Embed Builder**", 
        embed=embed, 
        view=EmbedBuilderView(user_id), 
        ephemeral=True
    )

@embed_group.command(name="setup_panel", description="Poste le panel permanent de création d'embeds.")
async def embed_setup_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(
        title="🛠️ Espace de Création d'Embeds",
        description="Cliquez sur le bouton ci-dessous pour ouvrir l'outil de création et voir le guide d'utilisation.",
        color=NEON_BLUE
    )
    await interaction.channel.send(embed=embed, view=EmbedPanelPermanentView())
    await interaction.followup.send("✅ Panel permanent posté !", ephemeral=True)

@embed_group.command(name="config_help", description="Configurer le message d'aide qui s'affiche dans l'outil.")
async def embed_config_help(interaction: discord.Interaction):
    await interaction.response.send_modal(EmbedHelpConfigModal())


# ==================================================================================================
# 17. NOUVEAUX PANELS DE CONTRÔLE (MOD, CONFIG, JOUEURS)
# ==================================================================================================

# --- DEFAULTS ---
# TOUT EN SECONDAIRE (GRIS) sauf spécifié autrement
MOD_BUTTONS_DEFAULTS = {
    "mod_ban": {"label": "Ban", "emoji": "🔨", "style": discord.ButtonStyle.secondary, "row": 0},
    "mod_kick": {"label": "Kick", "emoji": "🦵", "style": discord.ButtonStyle.secondary, "row": 0},
    "mod_mute": {"label": "Mute", "emoji": "🔇", "style": discord.ButtonStyle.secondary, "row": 0},
    "mod_warn": {"label": "Warn", "emoji": "⚠️", "style": discord.ButtonStyle.secondary, "row": 0},
    "mod_tempban": {"label": "Tempban", "emoji": "⏳", "style": discord.ButtonStyle.secondary, "row": 1},
    "mod_unban": {"label": "Unban", "emoji": "🔓", "style": discord.ButtonStyle.secondary, "row": 1},
    "mod_unmute": {"label": "Unmute", "emoji": "🔊", "style": discord.ButtonStyle.secondary, "row": 1},
    "mod_clear": {"label": "Clear", "emoji": "🧹", "style": discord.ButtonStyle.secondary, "row": 1},
    "mod_infs": {"label": "Infractions", "emoji": "📋", "style": discord.ButtonStyle.secondary, "row": 2},
    "mod_clear_all": {"label": "Reset Dossier", "emoji": "♻️", "style": discord.ButtonStyle.secondary, "row": 2},
    "mod_slowmode": {"label": "Slowmode", "emoji": "🐌", "style": discord.ButtonStyle.secondary, "row": 2},
    "mod_config": {"label": "Config Générale", "emoji": "⚙️", "style": discord.ButtonStyle.secondary, "row": 3}
    # mod_help RETIRÉ ICI
}

CONFIG_BUTTONS_DEFAULTS = {
    "conf_mc_toggle": {"label": "MemberCount", "emoji": "📊", "style": discord.ButtonStyle.secondary, "row": 0}, # Dynamic
    "conf_mc_setup": {"label": "MemberCount Setup", "emoji": "🛠️", "style": discord.ButtonStyle.secondary, "row": 0},
    "conf_ui_design": {"label": "Interface Design", "emoji": "🎨", "style": discord.ButtonStyle.secondary, "row": 1},
    "conf_err_design": {"label": "Erreur Design", "emoji": "⚠️", "style": discord.ButtonStyle.secondary, "row": 1},
    "conf_emojis": {"label": "Custom Emojis UI", "emoji": "😄", "style": discord.ButtonStyle.secondary, "row": 1},
    "conf_panel_design": {"label": "Design Panel Embeds", "emoji": "🎨", "style": discord.ButtonStyle.secondary, "row": 2},
    "conf_panel_buttons": {"label": "Config Panel Buttons", "emoji": "🔘", "style": discord.ButtonStyle.secondary, "row": 2},
    "conf_embed_help": {"label": "Config Guide Embed", "emoji": "📚", "style": discord.ButtonStyle.secondary, "row": 2} # New button
}

PLAYER_BUTTONS_DEFAULTS = {
    "play_infs": {"label": "Mes Infractions", "emoji": "🚨", "style": discord.ButtonStyle.secondary, "row": 0},
    "play_lives": {"label": "Mes Vies", "emoji": "❤️", "style": discord.ButtonStyle.secondary, "row": 0},
    "play_help": {"label": "Aide Joueur", "emoji": "📚", "style": discord.ButtonStyle.secondary, "row": 0},
    "play_vocal": {"label": "Mon Panel Vocal", "emoji": "🎤", "style": discord.ButtonStyle.secondary, "row": 1}
}

def get_panel_button_config(btn_id: str, panel_type: str):
    """Retrieves button config from DB or defaults."""
    if panel_type == "mod": defaults = MOD_BUTTONS_DEFAULTS
    elif panel_type == "conf": defaults = CONFIG_BUTTONS_DEFAULTS
    else: defaults = PLAYER_BUTTONS_DEFAULTS
    
    saved = db.get('settings', {}).get('panel_ui', {}).get(panel_type, {}).get(btn_id, {})
    base = defaults.get(btn_id, {}).copy()
    base.update(saved)
    return base

def apply_button_config(view: View, panel_type: str):
    """Updates all buttons in a view based on DB config."""
    for child in view.children:
        if isinstance(child, Button) and child.custom_id:
            cfg = get_panel_button_config(child.custom_id, panel_type)
            # Special case for MemberCount Toggle logic override
            if child.custom_id == "conf_mc_toggle": continue 
            
            if cfg.get('label'): child.label = cfg['label']
            else: child.label = None # Hide text if empty
            
            if cfg.get('emoji'): child.emoji = cfg['emoji']
            # Style is usually fixed logic, but can be overridden if needed (omitted for safety here)
            child.style = discord.ButtonStyle.secondary # Force grey

# --- MODALES & VUES DE MODÉRATION (NOUVEAU SYSTÈME AVEC LOGIQUE PARTAGÉE) ---

class ModClearModal(Modal, title="Nettoyage de Messages"):
    amount = TextInput(label="Nombre de messages", placeholder="1-100", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            num = int(self.amount.value)
            if not 1 <= num <= 100: raise ValueError
            deleted = await interaction.channel.purge(limit=num)
            await interaction.followup.send(f"✅ **{len(deleted)}** messages effacés.", ephemeral=True)
        except:
            await interaction.followup.send("❌ Nombre invalide (1-100).", ephemeral=True)

class ModReasonModal(Modal):
    def __init__(self, action: str, target: discord.User):
        super().__init__(title=f"Action: {action.upper()} - {target.name}")
        self.action = action
        self.target = target
        
        self.reason = TextInput(label="Raison", placeholder="Raison de la sanction...", required=True)
        self.add_item(self.reason)
        
        if action in ["tempban", "mute"]:
            self.duration = TextInput(label="Durée", placeholder="ex: 1h, 30m, 1d", required=True)
            self.add_item(self.duration)
            
        # Ajout du champ pour les vies (Optionnel)
        if action in ["ban", "kick", "mute", "warn", "tempban"]:
            self.lives = TextInput(label="Vies à retirer (Optionnel)", placeholder="Laisser vide pour défaut", required=False, max_length=2)
            self.add_item(self.lives)

    async def on_submit(self, interaction: discord.Interaction):
        # Récupération des inputs
        reason_text = self.reason.value
        target = self.target
        points = None
        
        if hasattr(self, 'lives') and self.lives.value.strip():
            try:
                points = int(self.lives.value.strip())
            except: pass # On garde None si invalide

        # APPEL AUX FONCTIONS PARTAGÉES (Comme les commandes)
        if self.action == "ban":
            if isinstance(target, discord.Member):
                await poxel_ban_logic(interaction, target, reason_text, points)
            else:
                await interaction.response.send_message("❌ Membre introuvable (Ban ID via bouton non supporté, utilisez /ban id).", ephemeral=True)
            
        elif self.action == "kick":
            if isinstance(target, discord.Member):
                await poxel_kick_logic(interaction, target, reason_text, points)
            else: await interaction.response.send_message("❌ Membre introuvable sur le serveur.", ephemeral=True)

        elif self.action == "warn":
            if isinstance(target, discord.Member):
                await poxel_warn_logic(interaction, target, reason_text, points)
            else: await interaction.response.send_message("❌ Membre introuvable.", ephemeral=True)

        elif self.action == "unban":
            # Target est un User (pas forcément Member)
            await poxel_unban_logic(interaction, str(target.id), reason_text)

        elif self.action == "tempban":
            if isinstance(target, discord.Member):
                await poxel_tempban_logic(interaction, target, self.duration.value, reason_text, points)
            else: await interaction.response.send_message("❌ Membre introuvable.", ephemeral=True)

        elif self.action == "mute":
            if isinstance(target, discord.Member):
                await poxel_mute_logic(interaction, target, self.duration.value, reason_text, points)
            else: await interaction.response.send_message("❌ Membre introuvable.", ephemeral=True)
            
        elif self.action == "unmute":
            await poxel_unmute_logic(interaction, target.id)
        
        elif self.action == "clear_all":
            if isinstance(target, discord.Member):
                await poxel_clear_infs_logic(interaction, target, reason_text)
            else: await interaction.response.send_message("❌ Membre introuvable.", ephemeral=True)

class ModSlowmodeModal(Modal, title="Définir le Slowmode"):
    duration = TextInput(label="Durée", placeholder="ex: 10s, 1m, 1h (0 pour désactiver)", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        delta = parse_duration(self.duration.value)
        seconds = int(delta.total_seconds())
        if not (0 <= seconds <= 21600):
            await interaction.followup.send("La durée doit être entre 0s et 6h.", ephemeral=True)
            return
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.followup.send(f"🐌 Slowmode défini à {self.duration.value}.", ephemeral=True)

class ModUserSelect(discord.ui.UserSelect):
    def __init__(self, action: str):
        self.action = action
        super().__init__(placeholder="Rechercher le joueur...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0] # Returns Member or User object directly
        
        # Pour "Infractions", pas besoin de modal de raison
        if self.action == "infractions":
            await interaction.response.defer(ephemeral=True)
            user_id_str = str(target.id)
            infs = db['infractions'].get(user_id_str, [])
            desc = "\n".join([f"• {i['type'].upper()}: {i['reason']}" for i in infs]) if infs else "Aucune infraction."
            embed = discord.Embed(title=f"Dossier {target}", description=desc, color=NEON_PURPLE)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # Pour les autres, on ouvre le modal de raison
            await interaction.response.send_modal(ModReasonModal(self.action, target))

class ModUserSelectView(View):
    def __init__(self, action: str):
        super().__init__(timeout=60)
        self.add_item(ModUserSelect(action))

class MemberCountSetupView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(discord.ui.ChannelSelect(channel_types=[discord.ChannelType.category], placeholder="Choisir la catégorie..."))
        self.children[0].callback = self.callback
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cat = self.children[0].values[0]
        try:
            old_id = db['settings'].get("member_count_channel_id")
            if old_id:
                try: await interaction.guild.get_channel(old_id).delete()
                except: pass
            chan = await interaction.guild.create_voice_channel(name=f"📊 Membres : {interaction.guild.member_count}", category=cat)
            db['settings']['member_count_channel_id'] = chan.id
            save_data(db)
            await interaction.followup.send(f"✅ Compteur créé dans {cat.name}.", ephemeral=True)
        except Exception as e: await interaction.followup.send(f"Erreur: {e}", ephemeral=True)

# --- VUES DES PANELS ---

class ModerationPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        apply_button_config(self, "mod")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Accès réservé aux administrateurs.", ephemeral=True)
            return False
        return True

    async def open_selector(self, interaction, action):
        await interaction.response.send_message("🔎 **Sélectionnez le joueur cible :**", view=ModUserSelectView(action), ephemeral=True)

    @discord.ui.button(custom_id="mod_ban", row=0)
    async def ban(self, interaction: discord.Interaction, button: Button): await self.open_selector(interaction, "ban")
    
    @discord.ui.button(custom_id="mod_kick", row=0)
    async def kick(self, interaction: discord.Interaction, button: Button): await self.open_selector(interaction, "kick")

    @discord.ui.button(custom_id="mod_mute", row=0)
    async def mute(self, interaction: discord.Interaction, button: Button): await self.open_selector(interaction, "mute")

    @discord.ui.button(custom_id="mod_warn", row=0)
    async def warn(self, interaction: discord.Interaction, button: Button): await self.open_selector(interaction, "warn")

    @discord.ui.button(custom_id="mod_tempban", row=1)
    async def tempban(self, interaction: discord.Interaction, button: Button): await self.open_selector(interaction, "tempban")

    @discord.ui.button(custom_id="mod_unban", row=1)
    async def unban(self, interaction: discord.Interaction, button: Button): await self.open_selector(interaction, "unban")

    @discord.ui.button(custom_id="mod_unmute", row=1)
    async def unmute(self, interaction: discord.Interaction, button: Button): await self.open_selector(interaction, "unmute")

    @discord.ui.button(custom_id="mod_clear", row=1)
    async def clear(self, interaction: discord.Interaction, button: Button): await interaction.response.send_modal(ModClearModal())

    @discord.ui.button(custom_id="mod_infs", row=2)
    async def infs(self, interaction: discord.Interaction, button: Button): await self.open_selector(interaction, "infractions")

    @discord.ui.button(custom_id="mod_clear_all", row=2)
    async def clear_all(self, interaction: discord.Interaction, button: Button): await self.open_selector(interaction, "clear_all")

    @discord.ui.button(custom_id="mod_slowmode", row=2)
    async def slowmode(self, interaction: discord.Interaction, button: Button): await interaction.response.send_modal(ModSlowmodeModal())

    @discord.ui.button(custom_id="mod_config", row=3)
    async def open_config(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Panneau Config :", view=MainConfigView(client), ephemeral=True)

    # --- BOUTON AIDE RETIRÉ ---


class ConfigPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        apply_button_config(self, "conf")
        self.update_mc_button()

    def update_mc_button(self):
        # Override dynamique pour le statut
        is_active = db['settings'].get("member_count_channel_id") is not None
        for child in self.children:
            if child.custom_id == "conf_mc_toggle":
                child.style = discord.ButtonStyle.success if is_active else discord.ButtonStyle.danger
                # On garde l'emoji custom s'il existe, sinon défaut
                cfg = get_panel_button_config("conf_mc_toggle", "conf")
                child.emoji = cfg.get('emoji', '📊')
                child.label = f"{cfg.get('label', 'MemberCount')}: {'ON' if is_active else 'OFF'}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Accès réservé aux administrateurs.", ephemeral=True)
            return False
        return True

    @discord.ui.button(custom_id="conf_mc_toggle", row=0)
    async def toggle_mc(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        guild = interaction.guild
        current_id = db['settings'].get("member_count_channel_id")
        
        if current_id: # Désactivation
            try:
                chan = guild.get_channel(current_id)
                if chan: await chan.delete()
            except: pass
            db['settings']['member_count_channel_id'] = None
        else: # Activation
            try:
                new_chan = await guild.create_voice_channel(name=f"📊 Membres : {guild.member_count}")
                db['settings']['member_count_channel_id'] = new_chan.id
            except: pass
        
        save_data(db)
        self.update_mc_button()
        await interaction.edit_original_response(view=self)

    @discord.ui.button(custom_id="conf_mc_setup", row=0)
    async def setup_mc(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Où créer le compteur ?", view=MemberCountSetupView(), ephemeral=True)

    @discord.ui.button(custom_id="conf_ui_design", row=1)
    async def design_ui(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(VoiceInterfaceConfigModal())

    @discord.ui.button(custom_id="conf_err_design", row=1)
    async def design_err(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(VoiceErrorConfigModal())

    @discord.ui.button(custom_id="conf_emojis", row=1)
    async def design_emojis(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Customisation UI", view=VoiceUIConfigView(), ephemeral=True)

    @discord.ui.button(custom_id="conf_panel_design", row=2)
    async def panel_design(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Quel panel designer ?", view=PanelSelectionView("design"), ephemeral=True)

    @discord.ui.button(custom_id="conf_panel_buttons", row=2)
    async def panel_buttons(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Quel panel configurer ?", view=PanelSelectionView("buttons"), ephemeral=True)

    @discord.ui.button(custom_id="conf_embed_help", row=2)
    async def embed_help(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(EmbedHelpConfigModal())


class PlayerPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        apply_button_config(self, "player")

    @discord.ui.button(custom_id="play_infs", row=0)
    async def my_infs(self, interaction: discord.Interaction, button: Button):
        user_id_str = str(interaction.user.id)
        infs = db['infractions'].get(user_id_str, [])
        desc = "\n".join([f"• {i['type'].upper()}: {i['reason']}" for i in infs]) if infs else "Vous êtes clean !"
        embed = discord.Embed(title="Vos Infractions", description=desc, color=NEON_PURPLE)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(custom_id="play_lives", row=0)
    async def my_lives(self, interaction: discord.Interaction, button: Button):
        lives = display_lives(interaction.user)
        embed = discord.Embed(title="Vos Vies", description=lives, color=NEON_PURPLE)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(custom_id="play_help", row=0)
    async def help_player(self, interaction: discord.Interaction, button: Button):
        # Appel de la fonction partagée définie dans la Partie 6
        await send_player_help_logic(interaction)

    @discord.ui.button(custom_id="play_vocal", row=1)
    async def my_vocal(self, interaction: discord.Interaction, button: Button):
        view = VoiceDashboardView()
        vc, owner = await view.get_active_channel(interaction)
        if vc:
            # Même logique JSON custom
            interface_json_str = db.get('settings', {}).get('voice_interface_json')
            embed = None
            if interface_json_str:
                try:
                    data = json.loads(interface_json_str)
                    if 'embeds' in data: data = data['embeds'][0]
                    embed = discord.Embed.from_dict(data)
                except: pass
            if not embed: embed = discord.Embed(title="Contrôle Vocal", color=NEON_BLUE)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# --- NOUVEAU: VUE PANEL AIDE ADMIN PERMANENT ---
class AdminHelpPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Afficher l'Aide Administrateur", style=discord.ButtonStyle.primary, emoji="📚", custom_id="admin_help_open")
    async def open_help(self, interaction: discord.Interaction, button: Button):
        # Cette fonction doit être importée ou définie dans le contexte (sera dans Partie 6)
        # Comme nous séparons les fichiers, nous ne pouvons pas importer directement 'send_admin_help_logic' ici si elle est dans Partie 6
        # Solution: Nous allons définir une logique simple ici qui renvoie vers Partie 6 via l'interaction, ou dupliquer la logique d'appel.
        # Pour rester propre, nous supposons que tout est dans un fichier final 'app.py'.
        # Si c'est séparé, il faudra veiller à l'ordre des définitions.
        # Ici, nous utilisons la fonction globale qui sera disponible au runtime.
        await send_admin_help_logic(interaction)


# --- CONFIGURATION DES PANELS ---

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
        except:
            await interaction.response.send_message("❌ JSON Invalide.", ephemeral=True)

class PanelButtonEditModal(Modal):
    def __init__(self, btn_id, panel_type):
        super().__init__(title="Éditer Bouton")
        self.btn_id = btn_id
        self.panel_type = panel_type
        
        cfg = get_panel_button_config(btn_id, panel_type)
        self.emoji_inp = TextInput(label="Emoji", default=cfg.get('emoji'), max_length=5, required=True)
        self.label_inp = TextInput(label="Texte (Vide = caché)", default=cfg.get('label'), required=False)
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
        
        if panel_type == "mod": defaults = MOD_BUTTONS_DEFAULTS
        elif panel_type == "conf": defaults = CONFIG_BUTTONS_DEFAULTS
        else: defaults = PLAYER_BUTTONS_DEFAULTS
        
        for k, v in defaults.items():
            options.append(discord.SelectOption(label=v['label'], value=k, emoji=v.get('emoji')))
            
        self.sel = Select(placeholder="Choisir un bouton...", options=options)
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
        if self.mode == 'design':
            await interaction.response.send_modal(PanelDesignModal(ptype))
        elif self.mode == 'buttons':
            await interaction.response.send_message(f"Configuration boutons **{ptype}** :", view=PanelConfigSelectView(ptype), ephemeral=True)

# --- COMMANDES ---

panel_group = app_commands.Group(name="setup_panel", description="Installer les panels permanents.", default_permissions=discord.Permissions(administrator=True))
panel_conf_group = app_commands.Group(name="panel_config", description="Configurer les boutons des panels.", default_permissions=discord.Permissions(administrator=True))

@panel_group.command(name="moderation", description="Poste le panel de modération.")
async def setup_mod_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    json_conf = db.get('settings', {}).get('panel_mod_json')
    embed = None
    if json_conf:
        try: embed = discord.Embed.from_dict(json.loads(json_conf))
        except: pass
    if not embed: embed = discord.Embed(title="🛡️ Panel de Modération", description="Outils pour l'équipe.", color=DARK_RED)
    await interaction.channel.send(embed=embed, view=ModerationPanelView())
    await interaction.followup.send("✅ Panel Modération posté !", ephemeral=True)

@panel_group.command(name="config", description="Poste le panel de configuration.")
async def setup_conf_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    json_conf = db.get('settings', {}).get('panel_conf_json')
    embed = None
    if json_conf:
        try: embed = discord.Embed.from_dict(json.loads(json_conf))
        except: pass
    if not embed: embed = discord.Embed(title="⚙️ Panel Configuration", description="Gestion du serveur.", color=NEON_BLUE)
    await interaction.channel.send(embed=embed, view=ConfigPanelView())
    await interaction.followup.send("✅ Panel Config posté !", ephemeral=True)

@panel_group.command(name="players", description="Poste le panel pour les joueurs.")
async def setup_player_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    json_conf = db.get('settings', {}).get('panel_player_json')
    embed = None
    if json_conf:
        try: embed = discord.Embed.from_dict(json.loads(json_conf))
        except: pass
    if not embed: embed = discord.Embed(title="🎮 Espace Joueurs", description="Vos outils personnels.", color=NEON_GREEN)
    await interaction.channel.send(embed=embed, view=PlayerPanelView())
    await interaction.followup.send("✅ Panel Joueurs posté !", ephemeral=True)

@panel_group.command(name="admin_help", description="Poste le panel d'aide pour les administrateurs.")
async def setup_admin_help_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="📚 Aide Administrateur", description="Cliquez ci-dessous pour ouvrir le guide des commandes.", color=NEON_PURPLE)
    await interaction.channel.send(embed=embed, view=AdminHelpPanelView())
    await interaction.followup.send("✅ Panel Aide Admin posté !", ephemeral=True)

@panel_group.command(name="design", description="Changer l'apparence des embeds des panels (JSON).")
@app_commands.describe(panel_type="Quel panel modifier ?", json_data="Le code JSON de l'embed")
@app_commands.choices(panel_type=[
    app_commands.Choice(name="Modération", value="mod"),
    app_commands.Choice(name="Configuration", value="conf"),
    app_commands.Choice(name="Joueurs", value="player")
])
async def design_panels(interaction: discord.Interaction, panel_type: app_commands.Choice[str], json_data: str):
    try:
        json.loads(json_data) 
        db.setdefault('settings', {})[f'panel_{panel_type.value}_json'] = json_data
        save_data(db)
        await interaction.response.send_message(f"✅ Design du panel **{panel_type.name}** sauvegardé !", ephemeral=True)
    except: await interaction.response.send_message("❌ JSON Invalide.", ephemeral=True)

@panel_conf_group.command(name="buttons", description="Modifier les boutons (Emoji/Texte) des panels.")
@app_commands.describe(panel_type="Quel panel configurer ?")
@app_commands.choices(panel_type=[
    app_commands.Choice(name="Modération", value="mod"),
    app_commands.Choice(name="Configuration", value="conf"),
    app_commands.Choice(name="Joueurs", value="player")
])
async def conf_buttons(interaction: discord.Interaction, panel_type: app_commands.Choice[str]):
    await interaction.response.send_message(f"Customisation boutons **{panel_type.name}** :", view=PanelConfigSelectView(panel_type.value), ephemeral=True)

# ==================================================================================================
# 16. COMPTEUR DE MEMBRES
# ==================================================================================================
membercount_group = app_commands.Group(name="membercount", description="Gère le salon du compteur de membres.", default_permissions=discord.Permissions(administrator=True))

@membercount_group.command(name="setup", description="Crée le salon de comptage des membres.")
@app_commands.describe(category="La catégorie où créer le salon de comptage.")
async def membercount_setup(interaction: discord.Interaction, category: discord.CategoryChannel):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    old_channel_id = db['settings'].get("member_count_channel_id")
    if old_channel_id:
        try:
            old_channel = await guild.fetch_channel(old_channel_id)
            await old_channel.delete(reason="Remplacement par un nouveau salon de comptage.")
        except (discord.NotFound, discord.Forbidden):
            pass

    try:
        overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
        new_channel = await guild.create_voice_channel(
            name=f"📊 Membres : {guild.member_count}",
            category=category,
            overwrites=overwrites,
            reason="Création du salon de comptage des membres"
        )
        db['settings']['member_count_channel_id'] = new_channel.id
        save_data(db)
        await interaction.followup.send(f"Salon de comptage créé avec succès dans la catégorie {category.name}!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("Erreur: Je n'ai pas la permission de créer un salon dans cette catégorie.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Une erreur est survenue : {e}", ephemeral=True)

@membercount_group.command(name="disable", description="Désactive et supprime le salon de comptage des membres.")
async def membercount_disable(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    channel_id = db['settings'].get("member_count_channel_id")

    if channel_id:
        try:
            channel = await guild.fetch_channel(channel_id)
            await channel.delete(reason="Désactivation du comptage des membres.")
        except (discord.NotFound, discord.Forbidden): pass
        db['settings']['member_count_channel_id'] = None
        save_data(db)
        await interaction.followup.send("Le salon de comptage des membres a été désactivé et supprimé.", ephemeral=True)
    else:
        await interaction.followup.send("Le salon de comptage n'est pas activé.", ephemeral=True)


# ==================================================================================================
# 17. COMMANDES D'AIDE
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
        embeds.append(embed1)
    view = HelpView(embeds, interaction.user)
    await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)

@app_commands.command(name="poxel_mod_help", description="[Admin] Affiche les commandes de modération.")
@app_commands.default_permissions(administrator=True)
async def help_command(interaction: discord.Interaction):
    await send_admin_help_logic(interaction)

@app_commands.command(name="poxel_mod_help_joueur", description="[Joueur] Affiche les commandes disponibles.")
async def help_joueur(interaction: discord.Interaction):
    await send_player_help_logic(interaction)

@app_commands.command(name="vocal", description="Affiche le panneau de contrôle de ton salon vocal temporaire.")
async def vocal_cmd(interaction: discord.Interaction):
    view = VoiceDashboardView()
    vc, is_owner = await view.get_active_channel(interaction)
    if not vc: return 
    interface_json_str = db.get('settings', {}).get('voice_interface_json')
    embed = None
    if interface_json_str:
        try:
            data = json.loads(interface_json_str)
            if 'embeds' in data: data = data['embeds'][0]
            embed = discord.Embed.from_dict(data)
        except: pass
    if not embed:
        embed = discord.Embed(title="🎛️ Contrôle des Salons Vocaux", description=f"Gestion du salon : **{vc.name}**", color=NEON_BLUE)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@app_commands.command(name="vies", description="Affiche le statut de vos cœurs (vies) et vos points d'infraction.")
@app_commands.default_permissions(None)
async def vies(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    member = interaction.user
    lives_display = display_lives(member)
    max_lives = get_max_lives(member)
    total_points = get_total_infraction_points(member.id)
    is_booster = max_lives > db['settings'].get("max_lives_default", 9)
    embed = discord.Embed(title="❤️ STATUS DE VIES", description=f"**{member.display_name}**, voici vos cœurs :", color=NEON_PURPLE)
    embed.add_field(name="Barre de Vie", value=lives_display, inline=False)
    embed.add_field(name="Points Perdus", value=f"{total_points} / {max_lives}", inline=True)
    embed.add_field(name="Statut Boost", value="✅ Actif" if is_booster else "❌ Inactif", inline=True)
    infractions_list = db['infractions'].get(str(member.id), [])
    if infractions_list:
        latest_inf_time = max(datetime.datetime.fromisoformat(inf['timestamp']).replace(tzinfo=SERVER_TIMEZONE) for inf in infractions_list)
        purge_days = db['settings'].get('purge_duration_days', 180)
        purge_threshold = latest_inf_time + datetime.timedelta(days=purge_days)
        time_left = format_time_left(purge_threshold.isoformat())
        footer = f"Prochaine réinitialisation dans {time_left} (si aucune nouvelle infraction)."
    else:
        footer = "Statut Parfait. Continuez comme ça !"
    embed.set_footer(text=footer)
    await interaction.followup.send(embed=embed, ephemeral=True)

@app_commands.command(name="config", description="Ouvre le panneau de configuration principal du bot.")
@app_commands.default_permissions(administrator=True)
async def config(interaction: discord.Interaction):
    await interaction.response.send_message("Panneau de configuration principal:", view=MainConfigView(client), ephemeral=True)

# --- NOUVELLES COMMANDES DE SETUP ET RACCOURCIS ---

@app_commands.command(name="annonce", description="Faire une annonce dans ce salon.")
@app_commands.describe(titre="Titre de l'annonce", message="Contenu de l'annonce", image="URL d'une image (optionnel)")
@app_commands.default_permissions(administrator=True)
async def annonce(interaction: discord.Interaction, titre: str, message: str, image: str = None):
    embed = discord.Embed(title=titre, description=message, color=RETRO_ORANGE)
    if image: embed.set_image(url=image)
    embed.set_footer(text=f"Annonce par {interaction.user.display_name}")
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Annonce publiée !", ephemeral=True)

@app_commands.command(name="ticket", description="Installer le panel Ticket (Raccourci).")
@app_commands.default_permissions(administrator=True)
async def ticket_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("Configuration Ticket :", view=SystemSetupView("ticket"), ephemeral=True)

@app_commands.command(name="report", description="Installer le panel Report (Raccourci).")
@app_commands.default_permissions(administrator=True)
async def report_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("Configuration Report :", view=SystemSetupView("report"), ephemeral=True)

@app_commands.command(name="signalement", description="Installer le panel Signalement (Raccourci).")
@app_commands.default_permissions(administrator=True)
async def signalement_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("Configuration Signalement :", view=SystemSetupView("signalement"), ephemeral=True)

@app_commands.command(name="suggestion", description="Installer le panel Suggestion (Raccourci).")
@app_commands.default_permissions(administrator=True)
async def suggestion_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("Configuration Suggestion :", view=SystemSetupView("suggestion"), ephemeral=True)

@app_commands.command(name="config_embed_system", description="Configurer les embeds par défaut des systèmes (JSON).")
@app_commands.describe(system="Le système à configurer", json_data="Le code JSON de l'embed")
@app_commands.choices(system=[
    app_commands.Choice(name="Ticket", value="ticket"),
    app_commands.Choice(name="Report", value="report"),
    app_commands.Choice(name="Signalement", value="signalement"),
    app_commands.Choice(name="Suggestion", value="suggestion")
])
@app_commands.default_permissions(administrator=True)
async def config_embed_system(interaction: discord.Interaction, system: app_commands.Choice[str], json_data: str):
    try:
        json.loads(json_data) 
        db.setdefault('default_embeds', {})[system.value] = json_data
        save_data(db)
        await interaction.response.send_message(f"✅ Embed pour **{system.name}** sauvegardé !", ephemeral=True)
    except: await interaction.response.send_message("❌ JSON Invalide.", ephemeral=True)

# ==================================================================================================
# 19. CLASSE CLIENT DISCORD & ÉVÉNEMENTS
# ==================================================================================================

# Les fonctions revert_avatar et trigger_avatar_change sont maintenant dans la Partie 2.

def recursive_replace(obj, replacements):
    if isinstance(obj, str):
        for k, v in replacements.items(): obj = obj.replace(k, str(v))
        return obj
    elif isinstance(obj, list): return [recursive_replace(i, replacements) for i in obj]
    elif isinstance(obj, dict): return {k: recursive_replace(v, replacements) for k, v in obj.items()}
    return obj

def normalize_text(text: str) -> str:
    import unicodedata
    import re
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode("utf-8")
    text = text.lower()
    replacements = {'0': 'o', '1': 'i', '3': 'e', '4': 'a', '@': 'a', '5': 's', '$': 's', '7': 't', '!': 'i', '+': 't', '(': 'c', '[': 'c', '{': 'c'}
    for k, v in replacements.items(): text = text.replace(k, v)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text

def sanitize_embed_json(data):
    """Nettoie récursivement le JSON pour supprimer les clés d'URL vides ou invalides."""
    if isinstance(data, dict):
        # Liste des clés qui attendent une URL
        url_keys = ['url', 'icon_url', 'proxy_icon_url']
        # Clés parentes qui contiennent des objets avec des URLs (image, thumbnail, author, footer)
        obj_keys = ['image', 'thumbnail', 'author', 'footer', 'video', 'provider']
        
        keys_to_remove = []
        for k, v in data.items():
            if k in url_keys:
                # Si la valeur est vide ou ne commence pas par http, on marque pour suppression
                if not isinstance(v, str) or not v.strip() or not v.startswith(('http://', 'https://')):
                    keys_to_remove.append(k)
            elif k in obj_keys:
                # Si c'est un objet (image, author...), on nettoie récursivement
                if isinstance(v, dict):
                    sanitize_embed_json(v)
                    # Si l'objet devient vide après nettoyage (ex: author sans name ni icon_url), on peut le supprimer
                    if not v: keys_to_remove.append(k)
            elif isinstance(v, (dict, list)):
                # Récursion pour les autres structures
                sanitize_embed_json(v)
        
        for k in keys_to_remove:
            del data[k]
            
    elif isinstance(data, list):
        for item in data:
            sanitize_embed_json(item)
            
    return data

class PoxelClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.persistent_views_added = False
        self.last_member_count_update = {}

    async def setup_hook(self):
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
        self.tree.add_command(config)
        self.tree.add_command(embed_group)
        self.tree.add_command(membercount_group)
        self.tree.add_command(help_command) 
        self.tree.add_command(help_joueur)
        self.tree.add_command(voice_config_group)
        self.tree.add_command(vocal_cmd)
        self.tree.add_command(panel_group)
        self.tree.add_command(panel_conf_group)
        # Ajout des nouvelles commandes
        self.tree.add_command(annonce)
        self.tree.add_command(ticket_cmd)
        self.tree.add_command(report_cmd)
        self.tree.add_command(signalement_cmd)
        self.tree.add_command(suggestion_cmd)
        self.tree.add_command(config_embed_system)
        
        await self.tree.sync()
        print(f"Synced {len(await self.tree.fetch_commands())} commands.")

    async def on_ready(self):
        print(f"Logged in as {self.user.name} ({self.user.id})")
        if not self.persistent_views_added:
            self.add_view(RulesAcceptView(self))
            self.add_view(VoiceDashboardView())
            self.add_view(ModerationPanelView())
            self.add_view(ConfigPanelView())
            self.add_view(PlayerPanelView())
            self.add_view(EmbedPanelPermanentView())
            self.add_view(AdminHelpPanelView()) # AJOUTÉ ICI POUR LA PERSISTANCE
            # On ajoute aussi la vue générique pour qu'elle fonctionne après redémarrage
            # Note: Pour une vraie persistance, il faudrait recréer les vues avec les bons custom_ids
            # Pour l'instant, c'est fonctionnel pour la session courante ou via les commandes setup
            self.persistent_views_added = True
            print("Persistent views initialised.")
        if not check_avatar_revert.is_running(): check_avatar_revert.start(self)
        if not check_unbans.is_running(): check_unbans.start(self)
        if not check_unmutes.is_running(): check_unmutes.start(self)
        if not check_infraction_purge.is_running(): check_infraction_purge.start(self)
        if not check_member_count.is_running(): check_member_count.start(self)

    async def try_update_member_count(self, guild: discord.Guild):
        now = datetime.datetime.now().timestamp()
        last_update = self.last_member_count_update.get(guild.id, 0)
        if now - last_update > 360:
            self.last_member_count_update[guild.id] = now
            await update_member_count_channel(guild)
            print(f"DEBUG: Compteur mis à jour pour {guild.name}")

    async def on_member_join(self, member: discord.Member):
        channel_id = db['settings'].get("welcome_channel_id")
        welcome_raw = db['settings'].get("welcome_message")
        if not welcome_raw: welcome_raw = "🎉 Bienvenue {user} sur le serveur !"
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if not channel:
                try: channel = await member.guild.fetch_channel(channel_id)
                except: pass
            if channel:
                replacements = {"{user}": member.mention, "{user.name}": member.name, "{guild}": member.guild.name, "{guild.name}": member.guild.name, "{member_count}": str(member.guild.member_count)}
                embed = None
                content = None
                try:
                    if welcome_raw.strip().startswith("{"):
                        data = json.loads(welcome_raw)
                        data = recursive_replace(data, replacements)
                        if 'content' in data: content = data['content']
                        embed_data = data['embeds'][0] if 'embeds' in data and data['embeds'] else data
                        embed_data = sanitize_embed_json(embed_data)
                        if embed_data: embed = discord.Embed.from_dict(embed_data)
                except Exception: pass
                if not embed and not content:
                    clean_text = welcome_raw
                    for k, v in replacements.items(): clean_text = clean_text.replace(k, v)
                    embed = discord.Embed(title="🎉 Bienvenue !", description=clean_text, color=NEON_GREEN)
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text="Loading next level...")
                try: await channel.send(content=content, embed=embed)
                except Exception: pass

        dm_config = db['settings'].get('welcome_dm', {})
        if dm_config.get('enabled', False):
            replacements = {"{user}": member.mention, "{user.name}": member.name, "{guild}": member.guild.name, "{guild.name}": member.guild.name}
            embed_dm = None
            json_raw = dm_config.get('json_data')
            if json_raw:
                try:
                    data = json.loads(json_raw)
                    data = recursive_replace(data, replacements)
                    embed_data = data['embeds'][0] if 'embeds' in data and data['embeds'] else data
                    embed_dm = discord.Embed.from_dict(sanitize_embed_json(embed_data))
                except: pass
            if not embed_dm:
                default_title = "Bienvenue sur {guild} !"
                default_desc = "Salut {user} ! Je suis Poxel."
                title = dm_config.get('title') or default_title
                desc = dm_config.get('description') or default_desc
                title = title.replace('{guild}', member.guild.name).replace('{user}', member.name)
                desc = desc.replace('{guild}', member.guild.name).replace('{user}', member.mention).replace('{user.name}', member.name)
                embed_dm = discord.Embed(title=title, description=desc, color=NEON_GREEN)
                if dm_config.get('image_url'): embed_dm.set_image(url=dm_config.get('image_url'))
            if embed_dm:
                try: await member.send(embed=embed_dm)
                except discord.Forbidden: pass
        
        # Appel Avatar corrigé (fonction importée de Partie 2 si tout est dans un fichier)
        await trigger_avatar_change('member_join')
        await self.try_update_member_count(member.guild)

    async def on_member_remove(self, member: discord.Member):
        channel_id = db['settings'].get("farewell_channel_id")
        farewell_raw = db['settings'].get("farewell_message")
        if not farewell_raw: farewell_raw = "Au revoir {user} !"
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if not channel:
                try: channel = await member.guild.fetch_channel(channel_id)
                except: pass
            if channel:
                replacements = {"{user}": member.display_name, "{user.name}": member.name, "{guild}": member.guild.name, "{guild.name}": member.guild.name}
                embed = None
                content = None
                try:
                    if farewell_raw.strip().startswith("{"):
                        data = json.loads(farewell_raw)
                        data = recursive_replace(data, replacements)
                        if 'content' in data: content = data['content']
                        embed_data = data['embeds'][0] if 'embeds' in data and data['embeds'] else data
                        if embed_data: embed = discord.Embed.from_dict(sanitize_embed_json(embed_data))
                except: pass
                if not embed and not content:
                    clean_text = farewell_raw
                    for k, v in replacements.items(): clean_text = clean_text.replace(k, v)
                    embed = discord.Embed(title="💔 Départ", description=clean_text, color=DARK_RED)
                    embed.set_thumbnail(url=member.display_avatar.url)
                try: await channel.send(content=content, embed=embed)
                except Exception: pass
        await trigger_avatar_change('member_remove')
        await self.try_update_member_count(member.guild)

    async def on_voice_state_update(self, member, before, after):
        if after.channel and str(after.channel.id) in db['voice_hubs']:
            hub_data = db['voice_hubs'][str(after.channel.id)]
            category = after.channel.category
            try:
                temp_channel_name = f"🎧 Salon de {member.display_name}"
                temp_channel = await category.create_voice_channel(name=temp_channel_name, user_limit=hub_data['limit'])
                db['temp_channels'][str(temp_channel.id)] = {'owner_id': member.id, 'trusted': [], 'blocked': [], 'created_at': datetime.datetime.now().isoformat()}
                save_data(db)
                await member.move_to(temp_channel)
                await trigger_avatar_change('channel_create')
            except Exception as e: print(f"Erreur création salon temp: {e}")
        if before.channel and str(before.channel.id) in db['temp_channels'] and not before.channel.members:
            try:
                await before.channel.delete(reason="Salon temporaire vide.")
                del db['temp_channels'][str(before.channel.id)]
                save_data(db)
                await trigger_avatar_change('channel_delete')
            except Exception as e: print(f"Erreur suppression salon temp: {e}")

    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot: return
        if db['settings'].get('censor_enabled', True):
            if not message.author.guild_permissions.administrator:
                censored_content, was_censored = censor_text(message.content, db['settings'].get('censored_words', []))
                if was_censored:
                    try:
                        await message.delete()
                        webhook = await message.channel.create_webhook(name=message.author.display_name)
                        await webhook.send(content=censored_content, username=message.author.display_name, avatar_url=message.author.display_avatar.url)
                        await webhook.delete()
                    except: pass
                    return
        if not db['settings'].get('auto_mod_enabled', True): return
        if message.author.guild_permissions.administrator: return
        
        # Logique Automod simplifiée pour éviter surcharge ici
        original_content = message.content
        normalized_content = normalize_text(original_content)
        user_id_str = str(message.author.id)
        triggered_profile_name = None
        triggered_profile_data = None
        for profile_name, profile in db.get('auto_mod_profiles', {}).items():
            for keyword in profile.get('keywords', []):
                kw_clean = normalize_text(keyword)
                if f" {kw_clean} " in f" {normalized_content} " or (" " in kw_clean and kw_clean in normalized_content):
                    triggered_profile_name = profile_name
                    triggered_profile_data = profile
                    break
            if triggered_profile_name: break
            
        if triggered_profile_name:
            # Action Automod : MP -> Delete -> Action
            now = get_adjusted_time()
            actions = triggered_profile_data.get('actions', [])
            if actions:
                action = actions[0] # Simplifié pour l'exemple
                action_type = action.get('type')
                points = action.get('points', 1)
                reason = f"Nova-Guard: {triggered_profile_name}"
                
                # MP Auto
                max_lives = get_max_lives(message.author)
                current_loss = get_total_infraction_points(message.author.id)
                remaining = max(0, max_lives - (current_loss + points))
                
                await send_private_notification(
                    message.author, 
                    f"SANCTION AUTO : {action_type.upper()}", 
                    reason, 
                    self.user, 
                    damage=points, 
                    remaining_lives=remaining, 
                    is_auto=True
                )
                
                try: await message.delete()
                except: pass
                
                # Action Discord
                try:
                    if action_type == 'mute': await message.author.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=5), reason=reason)
                    elif action_type == 'kick': await message.author.kick(reason=reason)
                    elif action_type == 'ban': await message.author.ban(reason=reason)
                except: pass
                
                add_infraction_with_life_check(self, None, message.author, f"auto_{action_type}", reason, custom_points=points, profile_name=triggered_profile_name, send_dm=False)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.user.id: return
        config = db.get('reaction_role_messages', {}).get(str(payload.message_id))
        if not config: return
        role_id = config.get(str(payload.emoji))
        if role_id:
            guild = self.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(role_id)
            if member and role:
                try: await member.add_roles(role, reason="Rôle-réaction")
                except: pass

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.user.id: return
        config = db.get('reaction_role_messages', {}).get(str(payload.message_id))
        if not config: return
        role_id = config.get(str(payload.emoji))
        if role_id:
            guild = self.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(role_id)
            if member and role:
                try: await member.remove_roles(role, reason="Rôle-réaction retiré")
                except: pass

@tasks.loop(seconds=5)
async def check_avatar_revert(client: discord.Client):
    if not db.get('avatar_stack'): return
    now_utc = get_adjusted_time()
    current_state = db['avatar_stack'][0]
    if current_state['revert_time']:
        revert_time = datetime.datetime.fromisoformat(current_state['revert_time']).replace(tzinfo=SERVER_TIMEZONE)
        if now_utc >= revert_time: await revert_avatar()

@tasks.loop(minutes=1)
async def check_unbans(client: discord.Client):
    await client.wait_until_ready()
    now_utc = get_adjusted_time()
    unbans_to_process = db.get('scheduled_unbans', [])
    if not unbans_to_process: return
    remaining_unbans = []
    for unban_info in unbans_to_process:
        unban_at = datetime.datetime.fromisoformat(unban_info['unban_at']).replace(tzinfo=SERVER_TIMEZONE)
        if now_utc >= unban_at:
            try:
                guild = client.get_guild(unban_info['guild_id'])
                # Fetch user pour le DM même si hors serveur
                user = await client.fetch_user(unban_info['user_id'])
                
                # MP de fin de tempban
                try:
                    embed_dm = discord.Embed(
                        title="🔓 FIN DE TEMPBAN",
                        description=f"Votre bannissement temporaire sur **{guild.name}** est arrivé à échéance.",
                        color=NEON_GREEN
                    )
                    embed_dm.add_field(name="Info", value=f"Vous êtes à nouveau le bienvenu sur {guild.name}.", inline=False)
                    await user.send(embed=embed_dm)
                except: pass

                if guild and user: await guild.unban(user, reason="Fin du bannissement temporaire.")
            except: pass
        else: remaining_unbans.append(unban_info)
    if len(remaining_unbans) != len(unbans_to_process):
        db['scheduled_unbans'] = remaining_unbans
        save_data(db)

@tasks.loop(minutes=1)
async def check_unmutes(client: discord.Client):
    await client.wait_until_ready()
    now_utc = get_adjusted_time()
    unmutes_to_process = db.get('scheduled_unmutes', [])
    if not unmutes_to_process: return
    remaining_unmutes = []
    
    for unmute_info in unmutes_to_process:
        unmute_at = datetime.datetime.fromisoformat(unmute_info['unmute_at']).replace(tzinfo=SERVER_TIMEZONE)
        if now_utc >= unmute_at:
            try:
                guild = client.get_guild(unmute_info['guild_id'])
                user = await client.fetch_user(unmute_info['user_id'])
                
                # MP de fin de mute
                try:
                    embed_dm = discord.Embed(
                        title="🔊 FIN DE MUTE TEMPORAIRE",
                        description=f"Votre mute temporaire sur **{guild.name}** est fini.",
                        color=NEON_GREEN
                    )
                    embed_dm.add_field(name="Info", value="le mute a pris fin la sanction est donc lever tu peux reparler dans le chat.", inline=False)
                    await user.send(embed=embed_dm)
                except: pass
                
                # Pas d'action Discord nécessaire car le Timeout expire seul, mais on nettoie la DB
            except: pass
        else: remaining_unmutes.append(unmute_info)
    
    if len(remaining_unmutes) != len(unmutes_to_process):
        db['scheduled_unmutes'] = remaining_unmutes
        save_data(db)

@tasks.loop(hours=24)
async def check_infraction_purge(client: discord.Client):
    now_utc = get_adjusted_time()
    purge_delta = datetime.timedelta(days=db['settings'].get('purge_duration_days', 180))
    for user_id_str, infractions_list in list(db['infractions'].items()):
        if not infractions_list: continue
        try:
            latest = max(datetime.datetime.fromisoformat(inf['timestamp']).replace(tzinfo=SERVER_TIMEZONE) for inf in infractions_list)
            if now_utc >= latest + purge_delta:
                # Avant de supprimer, on notifie l'utilisateur
                try:
                    user = await client.fetch_user(int(user_id_str))
                    # On suppose que le max est le défaut car on n'a pas l'objet Member pour vérifier le boost
                    max_lives = db['settings'].get("max_lives_default", 9) 
                    
                    embed_dm = discord.Embed(
                        title="🎉 RESTAURATION AUTOMATIQUE DES VIES",
                        description=f"Félicitations ! Après une longue période sans infraction (6 mois), votre casier a été entièrement purgé.",
                        color=NEON_GREEN
                    )
                    embed_dm.add_field(name="Vies restaurées", value=f"{max_lives} coeurs (Maximum)", inline=True)
                    embed_dm.set_footer(text="Système de purge automatique Poxel.")
                    await user.send(embed=embed_dm)
                except: pass

                del db['infractions'][user_id_str]
                save_data(db)
        except: pass

@tasks.loop(minutes=6)
async def check_member_count(client: discord.Client):
    await client.wait_until_ready()
    for guild in client.guilds:
        await update_member_count_channel(guild)

# ==================================================================================================
# 21. DÉMARRAGE DU BOT
# ==================================================================================================

if __name__ == "__main__":
    intents = discord.Intents.all()
    intents.members = True
    intents.presences = True
    intents.message_content = True
    
    client = PoxelClient(intents=intents)

    flask_thread = Thread(target=run_flask, daemon=True) 
    flask_thread.start()
    
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    if not DISCORD_TOKEN:
        print("ERREUR CRITIQUE: Token Discord non trouvé.")
        import sys
        sys.exit(1)

    try:
        print("Lancement du client Discord...")
        client.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"Erreur fatale lors du lancement: {e}")
