import os
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal
from discord.interactions import Interaction
from discord import ui
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
import asyncio
from datetime import datetime, timedelta, timezone
import pytz
import random
from flask import Flask, request
from threading import Thread

# --- Initialisation de Firebase ---
# Le fichier JSON de votre clé de service Firebase doit être placé dans le même répertoire que le bot.
FIREBASE_KEY_PATH = "firebase_key.json"
try:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase connecté.")
except Exception as e:
    print(f"Erreur de connexion à Firebase : {e}")
    db = None

# --- Configuration du bot et des variables d'environnement ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
NEON_GIF_URL = "https://media.giphy.com/media/26n6Gx9moj0ghzKkyS/giphy.gif"
COLOR_PURPLE = 0x6441a5
COLOR_BLUE = 0x027afa
COLOR_GREEN = 0x228B22
COLOR_RED = 0xFF0000

# Définir les intents nécessaires
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Dictionnaire pour stocker les messages d'aide et d'erreur, pour un nettoyage facile
help_messages = {}

# --- Modèles de données Firestore ---
events_ref = db.collection("events") if db else None
contests_ref = db.collection("contests") if db else None

# --- Fonctions utilitaires et de gestion d'erreurs ---
async def clean_up_message(message_id, channel_id):
    """
    Supprime un message après un délai de 2 minutes.
    """
    await asyncio.sleep(120)
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            message = await channel.fetch_message(message_id)
            await message.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        print(f"Erreur lors du nettoyage du message : {e}")

async def send_error_embed(ctx, title, description):
    """
    Envoie un embed d'erreur avec un style cohérent.
    """
    embed = discord.Embed(
        title=f"🛑 {title}",
        description=f"⚠️ **Erreur** : {description}",
        color=COLOR_RED
    )
    embed.set_footer(text="Ce message sera supprimé dans 2 minutes.")
    error_msg = await ctx.send(embed=embed)
    bot.loop.create_task(clean_up_message(error_msg.id, ctx.channel.id))

# --- Classes de Modals et de Vues pour l'interface utilisateur ---
class PlayerModal(Modal):
    """
    Fenêtre modale pour que les participants entrent leur pseudo de jeu.
    """
    def __init__(self, event_name, event_ref, user_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.title = "🎮 Entrez votre pseudo de jeu"
        self.event_name = event_name
        self.event_ref = event_ref
        self.user_id = user_id
        self.add_item(ui.InputText(label="Pseudo", placeholder="Votre pseudo pour l'événement..."))

    async def callback(self, interaction: Interaction):
        pseudo = self.children[0].value
        event_doc = self.event_ref.get().to_dict()
        if not event_doc:
            return await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            
        participants = event_doc.get("participants", [])

        if self.user_id in [p["id"] for p in participants]:
            return await interaction.response.send_message(
                "Vous êtes déjà inscrit à cet événement !", ephemeral=True
            )

        participants.append({
            "id": self.user_id,
            "name": interaction.user.display_name,
            "pseudo": pseudo
        })

        self.event_ref.update({"participants": participants})
        
        await update_event_embed(self.event_ref.id)
        await interaction.response.send_message(
            f"Félicitations {interaction.user.mention}, vous avez rejoint l'événement **{self.event_name}** avec le pseudo **{pseudo}** !",
            ephemeral=True
        )

class EventView(View):
    """
    Vue contenant les boutons pour interagir avec un événement.
    """
    def __init__(self, event_doc_ref, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_doc_ref = event_doc_ref

    @ui.button(label="START", style=discord.ButtonStyle.green, custom_id="start_button")
    async def start_button(self, button: ui.Button, interaction: Interaction):
        event_doc = self.event_doc_ref.get().to_dict()
        if not event_doc:
            return await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            
        if len(event_doc.get("participants", [])) >= event_doc["max_participants"]:
            return await interaction.response.send_message("L'inscription est complète, désolé !", ephemeral=True)
        
        modal = PlayerModal(
            event_name=event_doc["name"],
            event_ref=self.event_doc_ref,
            user_id=interaction.user.id
        )
        await interaction.response.send_modal(modal)

    @ui.button(label="QUIT", style=discord.ButtonStyle.red, custom_id="quit_button")
    async def quit_button(self, button: ui.Button, interaction: Interaction):
        event_doc = self.event_doc_ref.get().to_dict()
        if not event_doc:
            return await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            
        participants = event_doc.get("participants", [])
        
        new_participants = [p for p in participants if p["id"] != interaction.user.id]
        if len(new_participants) < len(participants):
            self.event_doc_ref.update({"participants": new_participants})
            await update_event_embed(self.event_doc_ref.id)
            await interaction.response.send_message(
                f"Vous vous êtes désisté de l'événement **{event_doc['name']}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Vous n'êtes pas inscrit à cet événement.", ephemeral=True
            )

# --- Fonction de mise à jour de l'embed de l'événement ---
async def update_event_embed(event_id):
    """
    Met à jour l'embed de l'événement en temps réel avec les informations de Firebase.
    """
    try:
        event_doc = events_ref.document(event_id).get().to_dict()
        if not event_doc or event_doc.get("is_ended"): return

        guild = bot.get_guild(event_doc["guild_id"])
        announce_channel = guild.get_channel(event_doc["announce_channel_id"])
        embed_message = await announce_channel.fetch_message(event_doc["embed_message_id"])

        current_time = datetime.now(timezone.utc)
        start_time = datetime.fromisoformat(event_doc["start_time"])
        duration = timedelta(minutes=int(event_doc["duration_minutes"]))
        end_time = start_time + duration
        
        participants_list = event_doc.get("participants", [])

        time_left_string = ""
        is_closed = False
        
        paris_tz = pytz.timezone('Europe/Paris')
        start_time_local = start_time.astimezone(paris_tz)
        
        if current_time < start_time:
            time_left = start_time - current_time
            total_seconds = int(time_left.total_seconds())
            days, remainder = divmod(total_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            time_parts = []
            if days > 0: time_parts.append(f"{days} jour(s)")
            if hours > 0: time_parts.append(f"{hours} heure(s)")
            if minutes > 0: time_parts.append(f"{minutes} minute(s)")
            if seconds > 0 or not time_parts: time_parts.append(f"{seconds} seconde(s)")
            
            time_left_string = f"DÉBUT DANS {', '.join(time_parts)}"
            is_closed = len(participants_list) >= event_doc["max_participants"]
            if is_closed: time_left_string = "INSCRIPTIONS FERMÉES"

        elif current_time < end_time:
            time_left = end_time - current_time
            minutes, seconds = divmod(int(time_left.total_seconds()), 60)
            time_left_string = f"L'ÉVÉNEMENT EST EN COURS. FIN DANS {minutes} min, {seconds} s"
            is_closed = True
        else:
            time_since_end = current_time - end_time
            minutes, seconds = divmod(int(time_since_end.total_seconds()), 60)
            time_left_string = f"ÉVÉNEMENT TERMINÉ IL Y A {minutes} min, {seconds} s"
            is_closed = True

        embed = discord.Embed(
            title=f"NEW EVENT: {event_doc['name']}",
            description=f"**DATE :** {start_time_local.strftime('%d/%m/%Y')} à {start_time_local.strftime('%H:%M')}\n**DURÉE :** {event_doc['duration_minutes']} min\n**PARTICIPANTS :** {len(participants_list)}/{event_doc['max_participants']}\n**SALON D'ATTENTE :** <#{event_doc['waiting_channel_id']}>",
            color=COLOR_PURPLE
        )
        embed.add_field(
            name="POINT DE RALLIEMENT",
            value="\n".join([f"• {p['name']} ({p['pseudo']})" for p in participants_list]) or "Aucun participant pour l'instant.",
            inline=False
        )
        embed.set_image(url=NEON_GIF_URL)
        embed.set_footer(text=time_left_string)

        view = EventView(events_ref.document(event_id))
        
        view.children[0].label = "INSCRIPTION CLOSE" if is_closed else "START"
        view.children[0].disabled = is_closed

        await embed_message.edit(embed=embed, view=view)

    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'embed {event_id}: {e}")
        
# --- Tâche de vérification des événements en arrière-plan ---
@tasks.loop(seconds=1)
async def check_events():
    if not db: return
    
    docs = events_ref.stream()
    for doc in docs:
        event = doc.to_dict()
        event_id = doc.id
        
        if event.get("is_ended"): continue
        
        start_time = datetime.fromisoformat(event["start_time"])
        duration = timedelta(minutes=int(event["duration_minutes"]))
        end_time = start_time + duration
        now = datetime.now(timezone.utc)
        
        event_start_utc = start_time.replace(tzinfo=timezone.utc)
        event_end_utc = end_time.replace(tzinfo=timezone.utc)

        await update_event_embed(event_id)

        time_until_start = event_start_utc - now
        
        if timedelta(hours=11, minutes=59) < time_until_start < timedelta(hours=12, minutes=1) and not event.get("morning_notified", False):
            await send_event_notification(event, "rappel_matin")
            events_ref.document(event_id).update({"morning_notified": True})

        if timedelta(minutes=29) < time_until_start < timedelta(minutes=31) and not event.get("30min_notified", False):
            await send_event_notification(event, "rappel_30min")
            events_ref.document(event_id).update({"30min_notified": True})
        
        min_participants = event.get("min_participants", 1)
        if time_until_start < timedelta(minutes=30) and len(event.get("participants", [])) < min_participants and not event.get("is_canceled", False):
            await send_event_notification(event, "canceled")
            events_ref.document(event_id).update({"status": "canceled", "is_canceled": True, "is_ended": True})
            
        if now > event_start_utc and not event.get("is_started", False) and not event.get("is_canceled", False):
            await start_event(event, event_id)
            
        if now > event_end_utc and not event.get("is_ended", False):
            await end_event_automatically(event, event_id)

# Fonctions de notification
async def send_event_notification(event, type):
    guild = bot.get_guild(event["guild_id"])
    announce_channel = guild.get_channel(event["announce_channel_id"])
    
    if type == "creation":
        embed = discord.Embed(
            title=f"🎉 NOUVEL ÉVÉNEMENT : {event['name']} 🎉",
            description=f"Un nouvel événement a été créé ! Soyez le premier à vous inscrire !",
            color=COLOR_BLUE
        )
        embed.add_field(name="Détails", value=f"• **Jeu :** {event['game_name']}\n• **Heure :** {datetime.fromisoformat(event['start_time']).strftime('%Hh%M')}\n• **Durée :** {event['duration_minutes']} min\n• **Lieu de rassemblement :** <#{event['waiting_channel_id']}>")
        embed.set_footer(text="Cliquez sur le bouton 'START' pour participer !")
        await announce_channel.send("@everyone", embed=embed)
    elif type == "rappel_matin":
        await announce_channel.send(f"@everyone ⏰ Rappel ! L'événement **{event['name']}** est prévu pour aujourd'hui. N'oubliez pas de vous inscrire !")
    elif type == "rappel_30min":
        await announce_channel.send(f"@everyone ⏳ Rappel ! L'événement **{event['name']}** commence dans moins de 30 minutes. Ne tardez pas à vous inscrire !")
    elif type == "start":
        await announce_channel.send(f"@everyone 🚀 L'événement **{event['name']}** a démarré ! Rendez-vous au <#{event['waiting_channel_id']}> pour commencer !")
    elif type == "end":
        await announce_channel.send(f"@everyone ✅ L'événement **{event['name']}** est terminé. Merci à tous les participants !")
    elif type == "canceled":
        await announce_channel.send(f"@everyone ❌ L'événement **{event['name']}** a été annulé car le nombre minimum de participants n'a pas été atteint ({len(event.get('participants', []))} sur {event.get('min_participants', 1)} requis).")
        
# Fonctions de gestion de l'événement
async def start_event(event, event_id):
    guild = bot.get_guild(event["guild_id"])
    role = guild.get_role(event["role_id"])
    
    participants = event.get("participants", [])
    
    await send_event_notification(event, "start")
    
    for p in participants:
        member = guild.get_member(p["id"])
        if member:
            await member.add_roles(role)
            try:
                await member.send(
                    f"Félicitations ! L'événement **{event['name']}** a commencé.\n"
                    f"Le rôle {role.name} vous a été attribué.\n"
                    f"Rendez-vous au salon d'attente <#{event['waiting_channel_id']}> pour le début des hostilités !"
                )
            except discord.Forbidden:
                print(f"Impossible d'envoyer un message privé à {member.display_name}")
    
    events_ref.document(event_id).update({"is_started": True})

async def end_event_automatically(event, event_id):
    guild = bot.get_guild(event["guild_id"])
    role = guild.get_role(event["role_id"])
    
    participants = event.get("participants", [])
    for p in participants:
        member = guild.get_member(p["id"])
        if member and role in member.roles:
            await member.remove_roles(role)
            
    await send_event_notification(event, "end")
    
    try:
        announce_channel = guild.get_channel(event["announce_channel_id"])
        embed_message = await announce_channel.fetch_message(event["embed_message_id"])
        await embed_message.delete()
    except Exception as e:
        print(f"Impossible de supprimer l'embed de l'événement {event['name']}: {e}")

    events_ref.document(event_id).update({"is_ended": True, "status": "ended"})
    
# --- Événements du bot Discord ---
@bot.event
async def on_ready():
    """
    Se déclenche lorsque le bot est en ligne et prêt.
    """
    print(f"{bot.user} est connecté à Discord !")
    check_events.start()

@bot.event
async def on_raw_reaction_add(payload):
    """
    Gère l'inscription aux concours via les réactions.
    """
    if not db or payload.user_id == bot.user.id:
        return
    
    channel = bot.get_channel(payload.channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    docs = contests_ref.where("message_id", "==", payload.message_id).stream()
    for doc in docs:
        contest_data = doc.to_dict()
        if not contest_data.get("is_ended", False):
            if payload.user_id not in [p["id"] for p in contest_data.get("participants", [])]:
                participants = contest_data.get("participants", [])
                user = bot.get_user(payload.user_id)
                if user:
                    participants.append({
                        "id": payload.user_id,
                        "name": user.display_name
                    })
                    doc.reference.update({"participants": participants})
                    print(f"Participant {user.display_name} ajouté au concours {contest_data['name']}")
                else:
                    print(f"Impossible de trouver l'utilisateur avec l'ID {payload.user_id}")
            break

@bot.event
async def on_command_error(ctx, error):
    """
    Gère les erreurs de commande de manière personnalisée.
    """
    if isinstance(error, commands.MissingRequiredArgument):
        await send_error_embed(
            ctx,
            "Argument manquant",
            "Il manque un argument pour cette commande. Utilisez `!helpoxel` pour plus d'informations."
        )
    elif isinstance(error, commands.MissingPermissions):
        await send_error_embed(
            ctx,
            "Permissions insuffisantes",
            "Vous n'avez pas les permissions nécessaires pour exécuter cette commande."
        )
    elif isinstance(error, commands.CommandNotFound):
        await send_error_embed(
            ctx,
            "Commande inconnue",
            "Cette commande n'existe pas. Utilisez `!helpoxel` pour voir la liste des commandes."
        )
    else:
        print(f"Une erreur s'est produite : {error}")
        await send_error_embed(
            ctx,
            "Erreur interne",
            "Une erreur inattendue s'est produite. Veuillez réessayer plus tard."
        )
        
    bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))
    
# --- Commandes du bot ---
@bot.command(name="create_event")
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, start_time_str, duration_str, role: discord.Role, announce_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, min_participants: int, game_name: str, *, event_name: str):
    if not db:
        return await send_error_embed(ctx, "Base de données non disponible", "Le bot n'a pas pu se connecter à la base de données Firebase.")
    
    try:
        start_time_local_naive = datetime.strptime(start_time_str, "%Hh%M").time()
        paris_tz = pytz.timezone('Europe/Paris')
        start_datetime_local = paris_tz.localize(datetime.combine(datetime.now(paris_tz).date(), start_time_local_naive))
        start_datetime_utc = start_datetime_local.astimezone(pytz.utc)
        
        if start_datetime_utc < datetime.now(timezone.utc):
            return await send_error_embed(ctx, "Erreur de temps", "L'heure de début de l'événement est déjà passée.")
            
    except ValueError:
        return await send_error_embed(ctx, "Format d'heure invalide", "Le format d'heure doit être `HHhMM` (ex: `21h14`).")

    try:
        duration_minutes = int(duration_str.replace("min", ""))
    except ValueError:
        return await send_error_embed(ctx, "Format de durée invalide", "Le format de durée doit être `XXmin` (ex: `10min`).")
        
    existing_events = events_ref.where("name", "==", event_name).stream()
    for doc in existing_events:
        event_data = doc.to_dict()
        if not event_data.get("is_ended", False) and not event_data.get("is_canceled", False):
            return await send_error_embed(ctx, "Nom d'événement déjà utilisé", "Un événement avec ce nom est déjà en cours.")

    event_data = {
        "name": event_name,
        "start_time": start_datetime_utc.isoformat(),
        "duration_minutes": duration_minutes,
        "role_id": role.id,
        "announce_channel_id": announce_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "min_participants": min_participants,
        "game_name": game_name,
        "participants": [],
        "is_started": False,
        "is_ended": False,
        "is_canceled": False,
        "30min_notified": False,
        "morning_notified": False,
        "guild_id": ctx.guild.id
    }

    doc_ref = events_ref.add(event_data)
    
    embed = discord.Embed(
        title=f"NEW EVENT: {event_name}",
        description=f"**DATE :** {start_datetime_local.strftime('%d/%m/%Y')} à {start_datetime_local.strftime('%H:%M')}\n**DURÉE :** {duration_minutes} min\n**PARTICIPANTS :** 0/{max_participants}\n**SALON D'ATTENTE :** {waiting_channel.mention}",
        color=COLOR_PURPLE
    )
    embed.add_field(
        name="POINT DE RALLIEMENT",
        value="Aucun participant pour l'instant.",
        inline=False
    )
    embed.set_image(url=NEON_GIF_URL)
    time_left_initial = start_datetime_utc - datetime.now(timezone.utc)
    minutes, seconds = divmod(int(time_left_initial.total_seconds()), 60)
    embed.set_footer(text=f"DÉBUT DANS {minutes} minute(s), {seconds} seconde(s)")

    view = EventView(doc_ref)
    view.children[0].label = "START"
    view.children[0].disabled = False
    
    msg = await announce_channel.send(f"@everyone Un nouvel événement a été créé par {ctx.author.mention} !", embed=embed, view=view)
    
    doc_ref.update({"embed_message_id": msg.id})
    await ctx.send(f"L'événement **{event_name}** a été créé avec succès !")
    bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))

@bot.command(name="create_event_plan")
@commands.has_permissions(manage_roles=True)
async def create_event_plan(ctx, date_str, start_time_str, duration_str, role: discord.Role, announce_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, min_participants: int, game_name: str, *, event_name: str):
    if not db:
        return await send_error_embed(ctx, "Base de données non disponible", "Le bot n'a pas pu se connecter à la base de données Firebase.")
        
    try:
        start_datetime_naive = datetime.strptime(f"{date_str} {start_time_str}", "%d/%m/%Y %Hh%M")
        paris_tz = pytz.timezone('Europe/Paris')
        start_datetime_local = paris_tz.localize(start_datetime_naive)
        start_datetime_utc = start_datetime_local.astimezone(pytz.utc)
        
        if start_datetime_utc < datetime.now(timezone.utc):
            return await send_error_embed(ctx, "Erreur de temps", "La date et l'heure de début de l'événement sont déjà passées.")
            
    except ValueError:
        return await send_error_embed(ctx, "Format de date/heure invalide", "Le format doit être `JJ/MM/AAAA HHhMM`.")

    try:
        duration_minutes = int(duration_str.replace("min", ""))
    except ValueError:
        return await send_error_embed(ctx, "Format de durée invalide", "Le format de durée doit être `XXmin` (ex: `10min`).")
        
    existing_events = events_ref.where("name", "==", event_name).stream()
    for doc in existing_events:
        event_data = doc.to_dict()
        if not event_data.get("is_ended", False) and not event_data.get("is_canceled", False):
            return await send_error_embed(ctx, "Nom d'événement déjà utilisé", "Un événement avec ce nom est déjà en cours.")
    
    event_data = {
        "name": event_name,
        "start_time": start_datetime_utc.isoformat(),
        "duration_minutes": duration_minutes,
        "role_id": role.id,
        "announce_channel_id": announce_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "min_participants": min_participants,
        "game_name": game_name,
        "participants": [],
        "is_started": False,
        "is_ended": False,
        "is_canceled": False,
        "30min_notified": False,
        "morning_notified": False,
        "guild_id": ctx.guild.id
    }

    doc_ref = events_ref.add(event_data)

    embed = discord.Embed(
        title=f"NEW EVENT: {event_name}",
        description=f"**DATE :** {start_datetime_local.strftime('%d/%m/%Y')} à {start_datetime_local.strftime('%H:%M')}\n**DURÉE :** {duration_minutes} min\n**PARTICIPANTS :** 0/{max_participants}\n**SALON D'ATTENTE :** {waiting_channel.mention}",
        color=COLOR_PURPLE
    )
    embed.add_field(
        name="POINT DE RALLIEMENT",
        value="Aucun participant pour l'instant.",
        inline=False
    )
    embed.set_image(url=NEON_GIF_URL)
    embed.set_footer(text=f"DÉBUT LE {start_datetime_local.strftime('%d/%m/%Y')} à {start_datetime_local.strftime('%H:%M')}")

    view = EventView(doc_ref)
    
    msg = await announce_channel.send(f"@everyone Un nouvel événement a été planifié par {ctx.author.mention} !", embed=embed, view=view)
    doc_ref.update({"embed_message_id": msg.id})
    await ctx.send(f"L'événement planifié **{event_name}** a été créé avec succès !")
    bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))

@bot.command(name="end_event")
@commands.has_permissions(manage_roles=True)
async def end_event(ctx, *, event_name: str):
    if not db:
        return await send_error_embed(ctx, "Base de données non disponible", "Le bot n'a pas pu se connecter à la base de données Firebase.")
        
    docs = events_ref.where("name", "==", event_name).where("is_ended", "==", False).stream()
    doc_found = False
    for doc in docs:
        doc_found = True
        event_data = doc.to_dict()
        await end_event_automatically(event_data, doc.id)
        await ctx.send(f"L'événement **{event_name}** a été manuellement terminé.")
        bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))
        break
    
    if not doc_found:
        await send_error_embed(ctx, "Événement introuvable", f"Aucun événement actif nommé **{event_name}** n'a été trouvé.")
        bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))
        
@bot.command(name="tirage")
@commands.has_permissions(manage_roles=True)
async def tirage(ctx, *, event_name: str):
    if not db:
        return await send_error_embed(ctx, "Base de données non disponible", "Le bot n'a pas pu se connecter à la base de données Firebase.")
        
    docs = events_ref.where("name", "==", event_name).stream()
    doc_found = False
    for doc in docs:
        doc_found = True
        event_data = doc.to_dict()
        participants = event_data.get("participants", [])
        
        if not participants:
            return await send_error_embed(ctx, "Pas de participants", "Il n'y a aucun participant pour ce tirage au sort.")
            
        winner_data = random.choice(participants)
        winner = discord.utils.get(ctx.guild.members, id=winner_data["id"])
        
        if winner:
            await ctx.send(f"🎉 Félicitations à {winner.mention} ! Vous avez été tiré au sort pour l'événement **{event_name}** !")
            try:
                await winner.send(f"Félicitations ! Vous avez gagné le tirage au sort pour l'événement **{event_name}** ! Contactez l'administrateur pour récupérer votre prix.")
            except discord.Forbidden:
                print(f"Impossible d'envoyer un message privé au gagnant {winner.display_name}")
        else:
            await send_error_embed(ctx, "Erreur de tirage", "Impossible de trouver le gagnant. Le participant a peut-être quitté le serveur.")
        
        bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))
        break
    
    if not doc_found:
        await send_error_embed(ctx, "Événement introuvable", f"Aucun événement nommé **{event_name}** n'a été trouvé.")
        bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))

@bot.command(name="concours")
@commands.has_permissions(manage_roles=True)
async def create_contest(ctx, end_date_str: str, *, contest_name: str):
    if not db:
        return await send_error_embed(ctx, "Base de données non disponible", "Le bot n'a pas pu se connecter à la base de données Firebase.")
        
    try:
        end_date = datetime.strptime(end_date_str, "%d/%m/%Y")
        end_date_utc = pytz.timezone('Europe/Paris').localize(end_date).astimezone(pytz.utc)
        
        if end_date_utc < datetime.now(timezone.utc):
            return await send_error_embed(ctx, "Date invalide", "La date de fin du concours est déjà passée.")
    except ValueError:
        return await send_error_embed(ctx, "Format de date invalide", "Le format de la date de fin doit être `JJ/MM/AAAA`.")

    contest_data = {
        "name": contest_name,
        "end_date": end_date_utc.isoformat(),
        "participants": [],
        "is_ended": False,
        "guild_id": ctx.guild.id
    }
    
    doc_ref = contests_ref.add(contest_data)
    
    embed = discord.Embed(
        title=f"🎉 CONCOURS : {contest_name} 🎉",
        description=f"Un nouveau concours a été lancé ! La date limite de participation est le **{end_date.strftime('%d/%m/%Y')}**.\n\nRéagissez à ce message pour vous inscrire !",
        color=COLOR_BLUE
    )
    
    msg = await ctx.send("@everyone", embed=embed)
    await msg.add_reaction("✅")

    doc_ref.update({"message_id": msg.id})
    await ctx.send(f"Le concours **{contest_name}** a été créé avec succès !")
    bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))

@bot.command(name="end_contest")
@commands.has_permissions(manage_roles=True)
async def end_contest(ctx, *, contest_name: str):
    if not db:
        return await send_error_embed(ctx, "Base de données non disponible", "Le bot n'a pas pu se connecter à la base de données Firebase.")

    docs = contests_ref.where("name", "==", contest_name).where("is_ended", "==", False).stream()
    doc_found = False
    for doc in docs:
        doc_found = True
        contest_data = doc.to_dict()
        participants = contest_data.get("participants", [])
        
        if not participants:
            return await send_error_embed(ctx, "Pas de participants", "Il n'y a aucun participant pour ce concours.")
            
        winner_data = random.choice(participants)
        winner = discord.utils.get(ctx.guild.members, id=winner_data["id"])
        
        if winner:
            await ctx.send(f"@everyone 🎉 Le tirage au sort du concours **{contest_name}** est terminé !\nLe grand gagnant est... {winner.mention} ! Félicitations !")
            try:
                await winner.send(f"Félicitations ! Vous avez gagné le concours **{contest_name}** ! Contactez l'administrateur pour récupérer votre prix.")
            except discord.Forbidden:
                print(f"Impossible d'envoyer un message privé au gagnant {winner.display_name}")
        else:
            await send_error_embed(ctx, "Erreur de tirage", "Impossible de trouver le gagnant. Le participant a peut-être quitté le serveur.")
        
        doc.reference.update({"is_ended": True})
        await ctx.send(f"Le concours **{contest_name}** a été manuellement terminé.")
        bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))
        break
    
    if not doc_found:
        await send_error_embed(ctx, "Concours introuvable", f"Aucun concours actif nommé **{contest_name}** n'a été trouvé.")
        bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))

@bot.command(name="list_events")
async def list_events(ctx):
    if not db:
        return await send_error_embed(ctx, "Base de données non disponible", "Le bot n'a pas pu se connecter à la base de données Firebase.")
    
    active_events = events_ref.where("is_ended", "==", False).stream()
    
    event_list = ""
    for event in active_events:
        event_data = event.to_dict()
        event_list += f"• **{event_data['name']}** - Participants : {len(event_data['participants'])}/{event_data['max_participants']}\n"
        
    embed = discord.Embed(
        title="Liste des événements en cours",
        description=event_list if event_list else "Aucun événement en cours pour le moment.",
        color=COLOR_BLUE
    )
    embed.set_footer(text="Utilisez !helpoxel pour créer un événement.")
    await ctx.send(embed=embed)
    bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))
    
@bot.command(name="my_permissions")
async def my_permissions(ctx):
    if ctx.author.guild_permissions.manage_roles:
        await ctx.send(f"✅ {ctx.author.mention}, vous avez les permissions de `Gérer les rôles`, vous pouvez donc utiliser les commandes d'administration du bot.")
    else:
        await ctx.send(f"❌ {ctx.author.mention}, vous n'avez pas les permissions de `Gérer les rôles` et ne pouvez pas utiliser les commandes d'administration du bot.")
    bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))

@bot.command(name="helpoxel")
async def helpoxel(ctx, command_name: str = None):
    embed_color = COLOR_BLUE
    embed_title = "MANUEL DE POXEL"
    embed_description = ""
    
    if command_name:
        if command_name == "create_event":
            embed_description = """
            **!create_event [heure de début] [durée] @[rôle] #[salon d'annonce] #[salon d'attente] [nombre max de participants] [nombre min de participants] "[nom du jeu]" "[nom de l'événement]"**
            
            Crée un événement qui débute le jour même.
            • **Exemple :** `!create_event 21h14 10min @role #salon #annonce 10 2 "pixels" "soirée gaming"`
            """
        elif command_name == "create_event_plan":
            embed_description = """
            **!create_event_plan [date] [heure] [durée] @[rôle] #[salon d'annonce] #[salon d'attente] [nombre max de participants] [nombre min de participants] "[nom du jeu]" "[nom de l'événement]"**
            
            Crée un événement qui débute plusieurs jours ou mois à l'avance.
            • **Exemple :** `!create_event_plan 25/12/2025 21h00 60min @role #annonce #rassemblement 10 4 "Minecraft" "Noël mincraft"`
            """
        elif command_name == "end_event":
            embed_description = """
            **!end_event "[nom de l'événement]"**
            
            Termine manuellement un événement en cours.
            """
        elif command_name == "tirage":
            embed_description = """
            **!tirage "[nom de l'événement]"**
            
            Effectue un tirage au sort parmi les participants d'un événement.
            """
        elif command_name == "concours":
            embed_description = """
            **!concours "[nom du concours]" [date de fin]**
            
            Crée un concours avec une date limite de participation. Les utilisateurs s'inscrivent en réagissant à l'annonce.
            • **Exemple :** `!concours "concours du nouvel an" 01/01/2026`
            """
        elif command_name == "end_contest":
            embed_description = """
            **!end_contest "[nom du concours]"**
            
            Termine un concours et tire le grand gagnant au sort.
            """
        elif command_name == "list_events":
            embed_description = """
            **!list_events**
            
            Affiche tous les événements actifs sur le serveur.
            """
        elif command_name == "my_permissions":
            embed_description = """
            **!my_permissions**
            
            Vérifie si vous avez les permissions nécessaires pour utiliser les commandes d'administration du bot.
            """
        else:
            embed_description = f"La commande `!{command_name}` n'existe pas."
    else:
        embed_description = """
        Voici la liste des commandes disponibles pour Poxel :
        • `!create_event` : Crée un événement qui débute le jour même.
        • `!create_event_plan` : Planifie un événement pour plus tard.
        • `!end_event` : Termine manuellement un événement.
        • `!tirage` : Effectue un tirage au sort parmi les participants d'un événement.
        • `!concours` : Crée un concours.
        • `!end_contest` : Termine un concours et tire un gagnant au sort.
        • `!list_events` : Affiche les événements en cours.
        • `!my_permissions` : Vérifie vos permissions.
        • `!helpoxel [commande]` : Affiche l'aide détaillée pour une commande spécifique.
        """
        
    embed = discord.Embed(title=embed_title, description=embed_description, color=embed_color)
    help_msg = await ctx.send(embed=embed)
    
    help_messages[help_msg.id] = True
    bot.loop.create_task(clean_up_message(ctx.message.id, ctx.channel.id))
    bot.loop.create_task(clean_up_message(help_msg.id, ctx.channel.id))

# --- Point de terminaison Flask pour le ping de Render ---
app = Flask(__name__)

@app.route("/")
def home():
    return "Poxel Bot est en ligne !"

def run_flask_server():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    t = Thread(target=run_flask_server)
    t.start()
    bot.run(TOKEN)
