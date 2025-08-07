# Importe les modules nécessaires
import os
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
import json
import tempfile
import re

# Importe les modules Firebase
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Charge les variables d'environnement depuis le fichier .env
load_dotenv()

# Récupère le token du bot et le chemin vers la clé Firebase
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
FIREBASE_SERVICE_ACCOUNT_KEY_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_JSON")

# Gère les informations d'identification de Firebase de manière sécurisée
if FIREBASE_SERVICE_ACCOUNT_KEY_JSON:
    # Crée un fichier temporaire avec les identifiants pour le déploiement sur Render
    try:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as temp_file:
            temp_file.write(FIREBASE_SERVICE_ACCOUNT_KEY_JSON)
            FIREBASE_CREDENTIALS_PATH = temp_file.name
        print(f"Fichier de credentials temporaire créé pour Firebase à: {FIREBASE_CREDENTIALS_PATH}")
    except Exception as e:
        print(f"Erreur lors de la création du fichier de credentials Firebase: {e}")
        FIREBASE_CREDENTIALS_PATH = None
else:
    # Utilise le chemin du fichier local si la variable d'environnement n'est pas définie
    FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

# Initialise l'application Firebase
try:
    if FIREBASE_CREDENTIALS_PATH:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
    else:
        print("Chemin des identifiants Firebase non trouvé.")
        db = None
except Exception as e:
    print(f"Erreur lors de l'initialisation de Firebase : {e}")
    db = None

# Crée une instance de l'application Flask
app = Flask(__name__)

# Configure le bot Discord avec les intents nécessaires
intents = discord.Intents.default()
intents.message_content = True
intents.guild_scheduled_events = True
intents.members = True # Nécessaire pour attribuer des rôles
bot = commands.Bot(command_prefix='!', intents=intents)

# Démarre l'application Flask dans un thread séparé
def run_flask():
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))

@app.route('/')
def home():
    return "Je suis en vie !"

@bot.event
async def on_ready():
    print(f'Le bot est en ligne ! Connecté en tant que {bot.user.name}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

# Commande pour créer un événement
# L'utilisation est `!create_event <@rôle> <HH:MM> <durée> #<salle dattente'> #<salle de l'event> <limite> <participants> <nom de l'event>`
# La durée peut être en heures (ex: "1h") ou en minutes (ex: "30m").
@bot.command()
async def create_event(ctx, role_name, start_time_str, duration_str: str, waiting_room_channel_name, event_channel_name, user_limit: int, participants_str, *, event_name):
    """Crée un événement en spécifiant le rôle, l'heure, la durée, le nombre de participants et les deux salons."""

    if not ctx.author.guild_permissions.manage_events:
        await ctx.send("Désolé, tu n'as pas la permission de gérer les événements sur ce serveur.")
        return

    try:
        # Nettoie le nom du rôle et des salons des préfixes Discord
        # Gère les mentions de rôle (@rôle) et les noms de rôle
        target_role = None
        role_match = re.match(r'<@&(\d+)>', role_name) # Capture l'ID d'un rôle mentionné
        if role_match:
            role_id = int(role_match.group(1))
            target_role = discord.utils.get(ctx.guild.roles, id=role_id)
        else:
            # Si ce n'est pas une mention, on recherche par nom (insensible à la casse)
            target_role = discord.utils.get(ctx.guild.roles, name=role_name)
        
        # Affiche un message de débogage pour voir le nom de rôle recherché
        print(f"Recherche du rôle avec la chaîne : '{role_name}'")

        if not target_role:
            await ctx.send(f"Le rôle '{role_name}' n'existe pas sur ce serveur. Assure-toi que le nom ou la mention est exact(e).")
            return
        
        # Nettoie les noms des salons des préfixes Discord
        if waiting_room_channel_name.startswith('#'):
            waiting_room_channel_name = waiting_room_channel_name[1:]
        if event_channel_name.startswith('#'):
            event_channel_name = event_channel_name[1:]

        # Convertit l'heure de début en un objet datetime en utilisant la date du jour
        now = datetime.now()
        event_datetime_str = f"{now.year}-{now.month}-{now.day} {start_time_str}"
        event_datetime = datetime.strptime(event_datetime_str, '%Y-%m-%d %H:%M')
        paris_timezone = pytz.timezone('Europe/Paris')
        localized_event_datetime = paris_timezone.localize(event_datetime)

        # Gère la durée de l'événement (en heures ou en minutes)
        if duration_str.endswith('h'):
            duration_value = int(duration_str[:-1])
            end_time = localized_event_datetime + timedelta(hours=duration_value)
            duration_display = f"{duration_value} heure(s)"
        elif duration_str.endswith('m'):
            duration_value = int(duration_str[:-1])
            end_time = localized_event_datetime + timedelta(minutes=duration_value)
            duration_display = f"{duration_value} minute(s)"
        else:
            await ctx.send("Format de durée invalide. Utilise '1h' pour une heure ou '30m' pour 30 minutes.")
            return

        if localized_event_datetime < datetime.now(pytz.utc):
            await ctx.send("Désolé, l'heure de début de l'événement ne peut pas être dans le passé. Utilise l'heure du jour.")
            return

        # Trouve les salons
        target_event_channel = discord.utils.get(ctx.guild.voice_channels, name=event_channel_name)
        target_waiting_room_channel = discord.utils.get(ctx.guild.voice_channels, name=waiting_room_channel_name)

        if not target_event_channel:
            await ctx.send(f"Le salon vocal '{event_channel_name}' n'existe pas sur ce serveur. Assure-toi que le nom est exact.")
            return
        if not target_waiting_room_channel:
            await ctx.send(f"Le salon vocal '{waiting_room_channel_name}' n'existe pas sur ce serveur. Assure-toi que le nom est exact.")
            return
            
        # Crée l'événement sur le serveur Discord
        new_event = await ctx.guild.create_scheduled_event(
            name=event_name,
            start_time=localized_event_datetime,
            end_time=end_time,
            privacy_level=discord.enums.ScheduledEventPrivacyLevel.guild_only,
            entity_type=discord.enums.ScheduledEventEntityType.voice,
            channel=target_event_channel, # Lie l'événement au salon de l'événement
            description=f"Nombre de participants max : {user_limit}.\nParticipants invités : {participants_str}",
            user_limit=user_limit
        )

        # Enregistre l'association dans Firestore
        if db:
            event_ref = db.collection('events').document(str(new_event.id))
            event_ref.set({
                'role_id': target_role.id,
                'waiting_room_channel_id': target_waiting_room_channel.id,
                'event_channel_id': target_event_channel.id,
                'guild_id': ctx.guild.id
            })

        await ctx.send(
            f"L'événement '{event_name}' a été programmé pour le {start_time_str} et durera {duration_display}."
            f"Le rôle '{target_role.name}' sera attribué aux participants au démarrage et retiré à la fin de l'événement."
            f"La salle d'attente est '{waiting_room_channel_name}' et la salle de l'événement est '{event_channel_name}'."
            f"Les participants invités sont : {participants_str}."
        )

    except ValueError:
        await ctx.send("Format de durée, d'heure ou de participants invalide. Assure-toi que l'heure est en `HH:MM`, la durée est en '1h' ou '30m', et le nombre de participants est un chiffre.")
    except discord.Forbidden:
        await ctx.send("Je n'ai pas la permission de créer des événements, de gérer des salons ou d'attribuer des rôles.")
    except Exception as e:
        await ctx.send(f"Une erreur est survenue lors de la création de l'événement : {e}")

# Événement qui se déclenche quand un événement programmé est mis à jour
@bot.event
async def on_scheduled_event_update(before, after):
    if db:
        event_ref = db.collection('events').document(str(after.id))
        doc = event_ref.get()
        if not doc.exists:
            return

        event_data = doc.to_dict()
        role_id = event_data.get('role_id')
        guild = after.guild
        role_to_manage = discord.utils.get(guild.roles, id=role_id)

        if not role_to_manage:
            print(f"Erreur : Le rôle avec l'ID {role_id} n'a pas été trouvé.")
            return

        # Si l'événement vient de démarrer
        if before.status == discord.ScheduledEventStatus.scheduled and after.status == discord.ScheduledEventStatus.active:
            print(f"L'événement '{after.name}' vient de commencer. Attribution des rôles.")
            participants = [user async for user in after.subscribers()]
            for user in participants:
                try:
                    await user.add_roles(role_to_manage)
                    print(f"Rôle '{role_to_manage.name}' attribué à {user.display_name}.")
                except discord.Forbidden:
                    print(f"Erreur : Impossible d'attribuer le rôle à {user.display_name}. Vérifie les permissions du bot.")

        # Si l'événement vient de se terminer
        if before.status == discord.ScheduledEventStatus.active and after.status == discord.ScheduledEventStatus.completed:
            print(f"L'événement '{after.name}' est terminé. Retrait des rôles.")
            # On cherche les membres qui ont le rôle et qui sont toujours sur le serveur
            members_with_role = [member for member in guild.members if role_to_manage in member.roles]
            for member in members_with_role:
                try:
                    await member.remove_roles(role_to_manage)
                    print(f"Rôle '{role_to_manage.name}' retiré à {member.display_name}.")
                except discord.Forbidden:
                    print(f"Erreur : Impossible de retirer le rôle à {member.display_name}. Vérifie les permissions du bot.")
            
            # Nettoyage de l'entrée dans Firestore
            event_ref.delete()
            print(f"L'entrée de l'événement '{after.name}' a été supprimée de la base de données.")


# Lance le thread Flask et le bot Discord
if __name__ == "__main__":
    t = Thread(target=run_flask)
    t.start()
    bot.run(DISCORD_BOT_TOKEN)
