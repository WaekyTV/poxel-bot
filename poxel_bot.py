import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import asyncio
import re
import os
import json
import random

# Import des bibliothèques Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# --- Configuration du Bot ---
# On récupère le TOKEN depuis les variables d'environnement de Replit
TOKEN = os.environ['DISCORD_TOKEN']

# --- Configuration Firebase ---
# On utilise la variable d'environnement pour stocker les clés
firebase_key_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY')
firebase_key_filename = 'serviceAccountKey.json'

if firebase_key_json:
    try:
        # Écrit le contenu de la variable d'environnement dans un fichier temporaire
        with open(firebase_key_filename, 'w') as f:
            f.write(firebase_key_json)
        print("Fichier serviceAccountKey.json créé avec succès à partir de la variable d'environnement.")
    except Exception as e:
        print(f"Erreur lors de la création du fichier Firebase : {e}")
        # Quitter si la clé ne peut pas être écrite
        exit()
else:
    print("Variable d'environnement 'FIREBASE_SERVICE_ACCOUNT_KEY' non trouvée.")
    exit()

try:
    cred = credentials.Certificate(firebase_key_filename)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialisé avec succès.")
except Exception as e:
    print(f"Erreur lors de l'initialisation de Firebase Admin SDK: {e}")
    print("Assure-toi que 'serviceAccountKey.json' est présent et valide.")
    exit()

# Les "intents" sont les permissions que ton bot demande à Discord.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Initialisation du bot avec un préfixe de commande (ex: !create_event)
# Désactiver l'aide par défaut de discord.py pour la remplacer par la nôtre
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- Fonctions Utilitaires ---

def parse_duration(duration_str: str) -> int:
    """
    Parse une chaîne de durée (ex: "2h", "30m", "5s") en secondes.
    Supporte les heures (h), minutes (m) et secondes (s).
    """
    total_seconds = 0
    matches = re.findall(r'(\d+)([hms])', duration_str.lower())

    if not matches:
        raise ValueError("Format de durée invalide. Utilisez '2h', '30m', '5s' ou une combinaison.")

    for value, unit in matches:
        value = int(value)
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
    return total_seconds

def get_participant_list_str(participants: list, guild: discord.Guild, participant_label: str) -> str:
    """
    Génère une chaîne de caractères formatée avec les pseudos des participants.
    """
    if not participants:
        return "Aucun participant pour le moment..."
    
    participant_list = []
    for user_id in participants:
        member = guild.get_member(user_id)
        if member:
            participant_list.append(f"• **{member.display_name}** ({participant_label})")
    
    return "\n".join(participant_list)

def format_timedelta(delta: timedelta) -> str:
    """
    Formate un objet timedelta en une chaîne lisible (ex: "2h 30m 5s").
    """
    if delta.total_seconds() < 0:
        return "Terminé"
    
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} jour{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} heure{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} seconde{'s' if seconds > 1 else ''}")
        
    return " ".join(parts)

async def _create_event_embed(event_data, guild, is_active: bool, is_expired: bool = False, is_cancelled: bool = False):
    """
    Crée un embed d'événement avec un visuel cohérent.
    """
    now = datetime.now(timezone.utc)
    
    if is_cancelled:
        embed_title = "ÉVÉNEMENT ANNULÉ"
        embed_color = discord.Color.from_rgb(255, 0, 0)
        footer_text = "ÉVÉNEMENT ANNULÉ | WAEKY"
        time_info = ""
    elif is_expired:
        embed_title = "ÉVÉNEMENT TERMINÉ"
        embed_color = discord.Color.from_rgb(200, 0, 0)
        footer_text = "ÉVÉNEMENT TERMINÉ | WAEKY"
        delta = now - event_data['end_time']
        time_info = f"Terminé il y a : **{format_timedelta(delta)}**"
    elif is_active:
        embed_title = "NOUVEL ÉVÉNEMENT"
        embed_color = discord.Color.from_rgb(255, 105, 180)
        footer_text = "LANCEMENT EN COURS | WAEKY"
        delta = event_data['end_time'] - now
        time_info = (f"Durée de l'événement : {event_data.get('duration_str', 'Indéfinie')}\n"
                     f"**Temps restant :** {format_timedelta(delta)}\n"
                     f"Fin de l'événement : <t:{int(event_data['end_time'].timestamp())}:R>")
    else: # Événement planifié
        embed_title = "ÉVÉNEMENT PLANIFIÉ"
        embed_color = discord.Color.from_rgb(255, 200, 50)
        footer_text = "EN ATTENTE DU LANCEMENT | WAEKY"
        delta = event_data['scheduled_start_time'] - now
        time_info = (f"Durée de l'événement : {event_data.get('duration_str', 'Indéfinie')}\n"
                     f"**Début de l'événement :** {format_timedelta(delta)}\n"
                     f"Début de l'événement : <t:{int(event_data['scheduled_start_time'].timestamp())}:F>")

    role = guild.get_role(event_data['role_id'])
    participant_list_str = get_participant_list_str(event_data.get('participants', []), guild, event_data.get('participant_label', 'Participant'))
    
    registrations_open = (is_active or ('scheduled_start_time' in event_data and not is_expired and not is_cancelled))
    
    registration_status = ""
    if is_cancelled:
        registration_status = "Inscriptions fermées."
    elif is_expired:
        registration_status = "Inscriptions terminées."
    elif len(event_data.get('participants', [])) >= event_data['max_participants']:
        registration_status = "Capacité maximale atteinte ! Inscriptions fermées."
    elif is_active:
        registration_status = "Inscriptions ouvertes jusqu'à la fin de l'événement !"
    else:
        registration_status = "Inscriptions ouvertes jusqu'au lancement de l'événement !"
    
    description = (
        f"**Nom de la partie :** {event_data['name']}\n"
        f"**Rôle attribué :** {role.name if role else 'NON SPÉCIFIÉ'}\n"
        f"**Statut de l'événement :** {embed_title}\n"
        f"--------------------------------------------------\n"
        f"{time_info}\n"
        f"Participants inscrits : {len(event_data.get('participants', []))} / {event_data['max_participants']}\n"
        f"**Statut des inscriptions :** {registration_status}\n\n"
        f"**Participants :**\n"
        f"--------------------------------------------------\n"
        f"{participant_list_str}\n"
        f"--------------------------------------------------\n"
    )
    
    if registrations_open and not is_cancelled:
        description += (
            f"Pour participer, cliquez sur le bouton S T A R T ci-dessous.\n"
            f"Une fois inscrit, rejoignez le point de ralliement {guild.get_channel(event_data['waiting_room_channel_id']).mention} pour le briefing de l'événement.\n"
        )
    
    embed = discord.Embed(
        title=f"**[ {embed_title} ]**",
        description=description,
        color=embed_color
    )
    embed.set_footer(text=footer_text)
    embed.timestamp = now
    return embed

async def _update_event_message(guild: discord.Guild, event_firestore_id: str, is_active: bool, is_expired: bool = False, is_cancelled: bool = False):
    """
    Met à jour le message d'événement avec les dernières informations.
    Les boutons sont désactivés si l'événement est terminé ou annulé.
    """
    event_ref = db.collection('events').document(event_firestore_id)
    event_doc = event_ref.get()
    
    if not event_doc.exists:
        return

    event_data = event_doc.to_dict()
    
    try:
        channel = guild.get_channel(event_data['channel_id'])
        if not channel: return
        
        event_message = await channel.fetch_message(event_data['message_id'])
        if not event_message: return

        view = None
        if not is_expired and not is_cancelled and len(event_data.get('participants', [])) < event_data['max_participants']:
            view = discord.ui.View(timeout=None)
            join_button = discord.ui.Button(
                label="S T A R T", 
                style=discord.ButtonStyle.blurple, 
                custom_id=f"join_event_{event_firestore_id}"
            )
            leave_button = discord.ui.Button(
                label="E X I T",
                style=discord.ButtonStyle.red, 
                custom_id=f"leave_event_{event_firestore_id}"
            )
            view.add_item(join_button)
            view.add_item(leave_button)
        
        embed = await _create_event_embed(event_data, guild, is_active, is_expired, is_cancelled)
        
        await event_message.edit(embed=embed, view=view)
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de la partie : {e}")

async def _delete_messages_after_delay(ctx, message: discord.Message, delay: int = 30):
    """
    Fonction utilitaire pour supprimer un message après un délai.
    """
    await asyncio.sleep(delay)
    try:
        if ctx and ctx.message:
            await ctx.message.delete()
        await message.delete()
    except discord.Forbidden:
        print("Permissions insuffisantes pour supprimer les messages.")
    except discord.NotFound:
        print("Message de commande ou de réponse non trouvé. Il a peut-être déjà été supprimé.")
    except Exception as e:
        print(f"Erreur lors de la suppression des messages : {e}")

async def _cancel_event(event_doc_id: str, reason: str = "Annulé manuellement"):
    """
    Fonction interne pour annuler un événement, retirer les rôles et nettoyer.
    """
    event_ref = db.collection('events').document(event_doc_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        print(f"Tentative d'annuler un événement non existant dans Firestore : {event_doc_id}")
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = bot.get_guild(event_data['guild_id'])
    
    if not guild:
        print(f"Guilde non trouvée pour l'événement {event_name} (ID: {event_doc_id})")
        event_ref.delete()
        return

    role = guild.get_role(event_data['role_id'])
    channel = guild.get_channel(event_data['channel_id'])
    participants_list = list(event_data.get('participants', []))

    for user_id in participants_list:
        member = guild.get_member(user_id)
        if member and role:
            try:
                await member.remove_roles(role, reason=f"Annulation de la partie {event_name}")
                print(f"Rôle {role.name} retiré à {member.display_name} pour la partie {event_name}")
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour retirer le rôle {role.name} à {member.display_name}")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle à {member.display_name}: {e}")

    # Notifie l'annulation
    if channel:
        try:
            await channel.send(f"@everyone ❌ L'événement **'{event_name}'** a été annulé : {reason}. Merci de votre compréhension.")
        except discord.Forbidden:
            print(f"Permissions insuffisantes pour envoyer un message dans le salon {channel.name}")
    
    # Met à jour le message pour indiquer l'annulation
    try:
        event_message = await channel.fetch_message(event_data['message_id'])
        if event_message:
            embed = await _create_event_embed(event_data, guild, is_active=False, is_cancelled=True)
            await event_message.edit(embed=embed, view=None)
    except discord.NotFound:
        print(f"Message de la partie {event_name} non trouvé sur Discord.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message d'annulation : {e}")

    # Supprime l'événement de Firestore
    event_ref.delete()
    print(f"Événement '{event_name}' (ID: {event_doc_id}) supprimé de Firestore.")

async def _close_event(event_doc_id: str, guild: discord.Guild):
    """
    Fonction interne pour clôturer un événement et retirer les rôles.
    Utilisé pour la fin de la durée et la commande manuelle.
    """
    event_ref = db.collection('events').document(event_doc_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        print(f"Tentative de clôturer un événement non existant dans Firestore : {event_doc_id}")
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    
    role = guild.get_role(event_data['role_id'])
    channel = guild.get_channel(event_data['channel_id'])
    participants_list = list(event_data.get('participants', []))

    for user_id in participants_list:
        member = guild.get_member(user_id)
        if member and role:
            try:
                await member.remove_roles(role, reason=f"Clôture de la partie {event_name}")
                print(f"Rôle {role.name} retiré à {member.display_name} pour la partie {event_name}")
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour retirer le rôle {role.name} à {member.display_name}")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle à {member.display_name}: {e}")

    # Notifie la clôture
    if channel:
        try:
            await channel.send(f"@everyone ✅ L'événement **'{event_name}'** est maintenant terminé. Merci à tous les participants !")
        except discord.Forbidden:
            print(f"Permissions insuffisantes pour envoyer un message dans le salon {channel.name}")
    
    # Met à jour le message pour indiquer la clôture
    try:
        event_message = await channel.fetch_message(event_data['message_id'])
        if event_message:
            embed = await _create_event_embed(event_data, guild, is_active=False, is_expired=True)
            await event_message.edit(embed=embed, view=None)
    except discord.NotFound:
        print(f"Message de la partie {event_name} non trouvé sur Discord.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de clôture : {e}")

    # Supprime l'événement de Firestore
    event_ref.delete()
    print(f"Événement '{event_name}' (ID: {event_doc_id}) supprimé de Firestore.")


# --- Événements du Bot ---

@bot.event
async def on_ready():
    """
    Se déclenche lorsque le bot est connecté à Discord.
    """
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Prêt à gérer les événements, les concours et les annulations !')
    check_expired_events.start()
    check_scheduled_events.start()
    update_event_messages.start()

@bot.event
async def on_command_error(ctx, error):
    """
    Gère les erreurs de commande et supprime les messages d'erreur et de commande après un délai.
    """
    if isinstance(error, commands.MissingRequiredArgument):
        response_msg = await ctx.send(f"Erreur de syntaxe : Il manque un argument pour cette commande. Utilisation correcte : `{ctx.command.usage}`", ephemeral=True)
    elif isinstance(error, commands.BadArgument):
        response_msg = await ctx.send(f"Erreur d'argument : Argument invalide. Veuillez vérifier le format de vos arguments.", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        response_msg = await ctx.send("Accès refusé : Vous n'avez pas les permissions nécessaires pour exécuter cette commande (Gérer les rôles).", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        print(f"Erreur de commande : {error}")
        response_msg = await ctx.send(f"Erreur du système : Une erreur inattendue s'est produite.", ephemeral=True)
        
    await _delete_messages_after_delay(ctx, response_msg, delay=30)


# --- Commandes du Bot ---

@bot.command(name='create_event', usage='<@rôle> <#salon> <#salon_d_attente> <durée (ex: 2h, 30m)> <max_participants> <min_participants> <étiquette_participants> <Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, role: discord.Role, channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, duration_str: str, max_participants: int, min_participants: int, participant_label: str, *event_name_parts):
    """
    Crée un nouvel événement immédiat.
    Ex: !create_event @RoleGaming #salon-prive-gaming #attente 2h 10 3 joueurs Soirée Gaming Communauté
    """
    event_name = " ".join(event_name_parts)
    if not event_name:
        await ctx.send("Veuillez spécifier un nom pour l'événement.", ephemeral=True)
        return

    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()
    if existing_event_docs:
        await ctx.send(f"Un événement nommé '{event_name}' existe déjà. Terminez l'ancien pour en créer un nouveau.", ephemeral=True)
        return

    if max_participants <= 0 or min_participants <= 0 or min_participants > max_participants:
        await ctx.send("Le nombre de participants doit être supérieur à zéro, et le minimum doit être inférieur ou égal au maximum.", ephemeral=True)
        return

    try:
        duration_seconds = parse_duration(duration_str)
    except ValueError as e:
        await ctx.send(str(e), ephemeral=True)
        return
    
    end_time = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)

    temp_message = await ctx.send("Création de l'événement en cours...")

    event_data_firestore = {
        'name': event_name,
        'role_id': role.id,
        'channel_id': channel.id,
        'waiting_room_channel_id': waiting_room_channel.id,
        'end_time': end_time,
        'duration_str': duration_str,
        'max_participants': max_participants,
        'min_participants': min_participants,
        'participant_label': participant_label,
        'participants': [],
        'message_id': temp_message.id,
        'guild_id': ctx.guild.id
    }
    doc_ref = db.collection('events').add(event_data_firestore)
    event_firestore_id = doc_ref[1].id

    view = discord.ui.View(timeout=None)
    join_button = discord.ui.Button(
        label="S T A R T", 
        style=discord.ButtonStyle.blurple, 
        custom_id=f"join_event_{event_firestore_id}"
    )
    leave_button = discord.ui.Button(
        label="E X I T",
        style=discord.ButtonStyle.red, 
        custom_id=f"leave_event_{event_firestore_id}"
    )
    view.add_item(join_button)
    view.add_item(leave_button)

    # Mise à jour des permissions du rôle pour le salon
    await channel.set_permissions(ctx.guild.default_role, read_messages=False)
    await channel.set_permissions(role, read_messages=True, send_messages=True)
    
    embed = await _create_event_embed(event_data_firestore, ctx.guild, is_active=True)
    
    await temp_message.edit(content=None, embed=embed, view=view)
    
    # Envoi de la notification @everyone
    await ctx.send(f"@everyone 📣 New Event launched : **{event_name}** ! It will last **{duration_str}** and registrations are now open !")

    # Message de confirmation qui sera supprimé après un délai
    confirmation_msg = await ctx.send(f"The event **'{event_name}'** has been launched and will end in {duration_str}.", ephemeral=True)
    await _delete_messages_after_delay(ctx, confirmation_msg, delay=30)


@bot.command(name='planifier_evenement', usage='<@rôle> <#salon> <#salon_d_attente> <durée (ex: 2h)> <date_début (YYYY-MM-DDTHH:mm)> <max_participants> <min_participants> <étiquette_participants> <Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def planifier_evenement(ctx, role: discord.Role, channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, duration_str: str, scheduled_time_str: str, max_participants: int, min_participants: int, participant_label: str, *event_name_parts):
    """
    Planifie un nouvel événement pour un lancement ultérieur.
    Ex: !planifier_evenement @RoleGaming #prive #attente 2h 2024-08-01T20:00 10 3 joueurs Soirée Futur
    """
    event_name = " ".join(event_name_parts)
    if not event_name:
        await ctx.send("Veuillez spécifier un nom pour l'événement.", ephemeral=True)
        return

    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()
    if existing_event_docs:
        await ctx.send(f"Un événement nommé '{event_name}' existe déjà. Terminez l'ancien pour en créer un nouveau.", ephemeral=True)
        return

    if max_participants <= 0 or min_participants <= 0 or min_participants > max_participants:
        await ctx.send("Le nombre de participants doit être supérieur à zéro, et le minimum doit être inférieur ou égal au maximum.", ephemeral=True)
        return

    try:
        duration_seconds = parse_duration(duration_str)
        scheduled_start_time_naive = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')
        scheduled_start_time = scheduled_start_time_naive.replace(tzinfo=timezone.utc)
    except ValueError as e:
        await ctx.send(f"Erreur dans le format de la durée ou de l'heure. Détails: `{e}`. Utilisez le format 'YYYY-MM-DDTHH:mm'.", ephemeral=True)
        return

    if scheduled_start_time < datetime.now(timezone.utc):
        await ctx.send("La date et l'heure de début doivent être dans le futur.", ephemeral=True)
        return

    temp_message = await ctx.send("Planification de l'événement en cours...")

    event_data_firestore = {
        'name': event_name,
        'role_id': role.id,
        'channel_id': channel.id,
        'waiting_room_channel_id': waiting_room_channel.id,
        'duration_str': duration_str,
        'scheduled_start_time': scheduled_start_time,
        'max_participants': max_participants,
        'min_participants': min_participants,
        'participant_label': participant_label,
        'participants': [],
        'message_id': temp_message.id,
        'guild_id': ctx.guild.id
    }
    doc_ref = db.collection('events').add(event_data_firestore)
    event_firestore_id = doc_ref[1].id

    view = discord.ui.View(timeout=None)
    join_button = discord.ui.Button(
        label="S T A R T", 
        style=discord.ButtonStyle.blurple, 
        custom_id=f"join_event_{event_firestore_id}"
    )
    leave_button = discord.ui.Button(
        label="E X I T",
        style=discord.ButtonStyle.red, 
        custom_id=f"leave_event_{event_firestore_id}"
    )
    view.add_item(join_button)
    view.add_item(leave_button)

    embed = await _create_event_embed(event_data_firestore, ctx.guild, is_active=False)

    await temp_message.edit(content=None, embed=embed, view=view)
    
    # Envoi de la notification @everyone
    await ctx.send(f"@everyone 📣 New Scheduled Event has been created : **{event_name}** ! "
                   f"It will start at <t:{int(scheduled_start_time.timestamp())}:F> (in **{format_timedelta(scheduled_start_time - datetime.now(timezone.utc))}**). "
                   f"Registrations are now open !")

    # Message de confirmation qui sera supprimé après un délai
    confirmation_msg = await ctx.send(f"The event **'{event_name}'** has been scheduled to start at <t:{int(scheduled_start_time.timestamp())}:F>.", ephemeral=True)
    await _delete_messages_after_delay(ctx, confirmation_msg, delay=30)


@bot.command(name='cloture_event', usage='<Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def cloture_event_command(ctx, *event_name_parts):
    """
    Clôture manuellement un événement en cours.
    Ex: !cloture_event Ma Super Partie
    """
    event_name = " ".join(event_name_parts)
    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()

    if not existing_event_docs:
        response_msg = await ctx.send(f"L'événement **'{event_name}'** n'existe pas ou est déjà terminé.", ephemeral=True)
        await _delete_messages_after_delay(ctx, response_msg, delay=30)
        return

    event_doc = existing_event_docs[0]
    event_doc_id = event_doc.id
    
    event_data = event_doc.to_dict()
    if 'end_time' not in event_data:
        response_msg = await ctx.send(f"L'événement **'{event_name}'** est un événement planifié. Veuillez utiliser `!annule_event` pour l'annuler.", ephemeral=True)
        await _delete_messages_after_delay(ctx, response_msg, delay=30)
        return

    response_msg = await ctx.send(f"L'événement **'{event_name}'** est en cours de clôture...", ephemeral=True)
    await _close_event(event_doc_id, ctx.guild)
    confirmation_msg = await ctx.send(f"L'événement **'{event_name}'** a été clôturé manuellement.", ephemeral=True)
    
    await _delete_messages_after_delay(ctx, response_msg, delay=30)
    await _delete_messages_after_delay(ctx, confirmation_msg, delay=30)

@bot.command(name='annule_event', usage='<Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def annule_event_command(ctx, *event_name_parts):
    """
    Annule un événement en cours ou planifié et retire les rôles.
    Ex: !annule_event Ma Super Partie
    """
    event_name = " ".join(event_name_parts)
    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()

    if not existing_event_docs:
        response_msg = await ctx.send(f"L'événement **'{event_name}'** n'existe pas ou est déjà terminé.", ephemeral=True)
        await _delete_messages_after_delay(ctx, response_msg, delay=30)
        return

    event_doc_id = existing_event_docs[0].id
    
    response_msg = await ctx.send(f"L'événement **'{event_name}'** est en cours d'annulation...", ephemeral=True)
    await _cancel_event(event_doc_id, "Annulé manuellement par un administrateur.")
    confirmation_msg = await ctx.send(f"L'événement **'{event_name}'** a été annulé manuellement.", ephemeral=True)
    
    await _delete_messages_after_delay(ctx, response_msg, delay=30)
    await _delete_messages_after_delay(ctx, confirmation_msg, delay=30)

@bot.command(name='annule_concours', usage='<Titre du concours>')
@commands.has_permissions(manage_roles=True)
async def annule_concours(ctx, *raffle_title_parts):
    """
    Annule un concours en cours.
    Ex: !annule_concours Un lot de 50€
    """
    raffle_title = " ".join(raffle_title_parts)
    raffle_ref = db.collection('raffles')
    raffle_docs = raffle_ref.where('title', '==', raffle_title).get()

    if not raffle_docs:
        await ctx.send(f"Le concours '{raffle_title}' n'existe pas.", ephemeral=True)
        return

    raffle_doc = raffle_docs[0]
    await ctx.send(f"@everyone ❌ Le concours **'{raffle_title}'** a été annulé par un administrateur.")
    raffle_doc.reference.delete()
    
    await ctx.send(f"Le concours **'{raffle_title}'** a été annulé et supprimé.", ephemeral=True)

@bot.command(name='list_events')
async def list_events(ctx):
    """
    Affiche la liste de tous les événements actifs et planifiés.
    """
    events_ref = db.collection('events')
    active_events_docs = events_ref.stream()

    events_list = []
    for doc in active_events_docs:
        events_list.append(doc.to_dict())

    if not events_list:
        response_msg = await ctx.send("[ STATUT ] Aucun événement actif ou planifié pour le moment.", ephemeral=True)
        await _delete_messages_after_delay(ctx, response_msg, delay=30)
        return

    embed = discord.Embed(
        title="ÉVÉNEMENTS EN COURS",
        description="""
        Poxel est votre agent de liaison pour organiser les événements sur le serveur.
        Voici la liste des événements actifs et planifiés :
        """,
        color=discord.Color.from_rgb(255, 105, 180)
    )

    for data in events_list:
        guild = bot.get_guild(data['guild_id'])
        role = guild.get_role(data['role_id']) if guild else None
        
        participants_count = len(data.get('participants', []))
        
        # Détermine si l'événement est actif ou planifié
        if 'scheduled_start_time' in data:
            status = "PLANIFIÉ"
            time_info = f"Début de l'événement : <t:{int(data['scheduled_start_time'].timestamp())}:R>"
            field_name = f"➤ [PLANIFIÉ] {data['name'].upper()}"
        else:
            status = "EN COURS"
            time_info = f"Fin de l'événement : <t:{int(data['end_time'].timestamp())}:R>"
            field_name = f"➤ [EN COURS] {data['name'].upper()}"

        embed.add_field(
            name=field_name,
            value=(
                f"**Rôle attribué :** {role.name if role else 'INTROUVABLE'}\n"
                f"**Participants :** {participants_count} / {data['max_participants']}\n"
                f"**Participants Min :** {data['min_participants']}\n"
                f"**Statut :** {status}\n"
                f"**{time_info}**\n"
            ),
            inline=False
        )
    embed.set_footer(text="[ GESTION PAR POXEL ]  |  PRÊT AU COMBAT  |  WAEKY")
    embed.timestamp = datetime.now()
    
    response_msg = await ctx.send(embed=embed)
    await _delete_messages_after_delay(ctx, response_msg, delay=30)


@bot.command(name='tirage_au_sort', usage='<Titre du concours> <nombre_de_gagnants>')
@commands.has_permissions(manage_roles=True)
async def tirage_au_sort(ctx, *raffle_title_and_winners):
    """
    Crée un concours où les membres peuvent s'inscrire pour un tirage au sort.
    Ex: !tirage_au_sort Un lot de 50€ 10
    """
    if len(raffle_title_and_winners) < 2:
        await ctx.send("Veuillez spécifier un titre pour le concours et le nombre de gagnants. `!tirage_au_sort titre_du_concours nombre_de_gagnants`", ephemeral=True)
        return

    try:
        num_winners = int(raffle_title_and_winners[-1])
    except ValueError:
        await ctx.send("Le nombre de gagnants doit être un nombre valide.", ephemeral=True)
        return

    raffle_title = " ".join(raffle_title_and_winners[:-1])

    if not raffle_title:
        await ctx.send("Veuillez spécifier un titre pour le concours.", ephemeral=True)
        return
    if num_winners <= 0:
        await ctx.send("Le nombre de gagnants doit être supérieur à zéro.", ephemeral=True)
        return
    
    raffle_ref = db.collection('raffles')
    existing_raffle_docs = raffle_ref.where('title', '==', raffle_title).get()
    if existing_raffle_docs:
        await ctx.send(f"Un concours avec le titre '{raffle_title}' existe déjà.", ephemeral=True)
        return
    
    raffle_data = {
        'title': raffle_title,
        'winners_count': num_winners,
        'participants': [],
        'guild_id': ctx.guild.id,
        'channel_id': ctx.channel.id,
        'is_active': True,
        'created_at': datetime.now(timezone.utc)
    }

    doc_ref = raffle_ref.add(raffle_data)
    raffle_firestore_id = doc_ref[1].id
    
    embed = discord.Embed(
        title=f"NEW RAFFLE : {raffle_title}",
        description=f"🎉 A brand new raffle has been launched ! 🎉\n\n"
                    f"To participate, click on the `PARTICIPER` button below.\n"
                    f"**Nombre de gagnants :** {num_winners}\n\n"
                    f"Bonne chance à tous !",
        color=discord.Color.from_rgb(255, 215, 0)
    )
    embed.set_footer(text="Cliquez sur 'PARTICIPER' pour tenter votre chance !")
    
    view = discord.ui.View(timeout=None)
    join_button = discord.ui.Button(
        label="PARTICIPER",
        style=discord.ButtonStyle.green,
        custom_id=f"join_raffle_{raffle_firestore_id}"
    )
    view.add_item(join_button)

    raffle_message = await ctx.send(embed=embed, view=view)
    raffle_ref.document(raffle_firestore_id).update({'message_id': raffle_message.id})
    
    await ctx.send(f"@everyone 🎁 **New Raffle** : {raffle_title} ! Try your luck here : {raffle_message.jump_url}")

@bot.command(name='cloture_concours', usage='<titre_du_concours>')
@commands.has_permissions(manage_roles=True)
async def cloture_concours(ctx, *raffle_title_parts):
    """
    Tire au sort les gagnants d'un concours en cours.
    Ex: !cloture_concours Un lot de 50€
    """
    raffle_title = " ".join(raffle_title_parts)
    raffle_ref = db.collection('raffles')
    raffle_docs = raffle_ref.where('title', '==', raffle_title).get()

    if not raffle_docs:
        await ctx.send(f"Le concours '{raffle_title}' n'existe pas.", ephemeral=True)
        return
    
    raffle_doc = raffle_docs[0]
    raffle_data = raffle_doc.to_dict()
    participants = raffle_data.get('participants', [])
    num_winners = raffle_data['winners_count']

    if not participants:
        await ctx.send(f"Il n'y a aucun participant inscrit au concours '{raffle_title}'. Il est annulé.", ephemeral=True)
        await ctx.send(f"@everyone ❌ Le concours **'{raffle_title}'** est annulé car il n'y a aucun participant.")
        raffle_doc.reference.delete()
        return

    if len(participants) < num_winners:
        await ctx.send(f"Il n'y a pas assez de participants ({len(participants)}) pour tirer {num_winners} gagnants. Le concours a été annulé.", ephemeral=True)
        await ctx.send(f"@everyone ❌ Le concours **'{raffle_title}'** est annulé car il n'y a pas assez de participants.")
        raffle_doc.reference.delete()
        return

    winners_ids = random.sample(participants, k=num_winners)
    winners_mentions = [f'<@{w_id}>' for w_id in winners_ids]
    
    winners_str = ", ".join(winners_mentions)
    
    embed = discord.Embed(
        title=f"RÉSULTATS DU CONCOURS : {raffle_title}",
        description=f"🎉 **Félicitations aux gagnants !** 🎉\n\n"
                    f"Les gagnants sont : {winners_str}",
        color=discord.Color.from_rgb(0, 255, 0)
    )

    await ctx.send(f"@everyone 🏆 Le tirage au sort de **{raffle_title}** est terminé ! Découvrez les gagnants ci-dessous :", embed=embed)
    
    # Désactiver le tirage au sort en cours et supprimer l'entrée de la base de données
    raffle_doc.reference.delete()


@bot.command(name='help')
async def help_command(ctx):
    """
    Affiche un message d'aide détaillé.
    """
    commands_info = {
        "create_event": {
            "description": "Crée un nouvel événement immédiat.",
            "usage": "`!create_event @rôle #salon #salon_d_attente durée(ex: 2h) max_participants min_participants étiquette_participants Nom de l'événement`\n"
                     "Ex: `!create_event @Joueur #salon-jeu #attente 1h30m 4 2 joueurs Partie de Donjons`"
        },
        "planifier_evenement": {
            "description": "Planifie un événement pour un lancement ultérieur.",
            "usage": "`!planifier_evenement @rôle #salon #salon_d_attente durée date_début(YYYY-MM-DDTHH:mm) max_participants min_participants étiquette_participants Nom`\n"
                     "Ex: `!planifier_evenement @RoleGaming #prive #attente 2h 2024-08-01T20:00 10 5 joueurs Soirée Futur`"
        },
        "cloture_event": {
            "description": "Clôture manuellement un événement en cours et retire les rôles.",
            "usage": "`!cloture_event Nom de l'événement`\n"
                     "Ex: `!cloture_event Ma Super Partie`"
        },
        "annule_event": {
            "description": "Annule un événement en cours ou planifié.",
            "usage": "`!annule_event Nom de l'événement`\n"
                     "Ex: `!annule_event Ma Super Partie`"
        },
        "tirage_au_sort": {
            "description": "Crée un concours où les membres peuvent s'inscrire pour un tirage au sort.",
            "usage": "`!tirage_au_sort titre_du_concours nombre_de_gagnants`\n"
                     "Ex: `!tirage_au_sort Un lot de 50€ 10`"
        },
        "cloture_concours": {
            "description": "Tire au sort les gagnants d'un concours et l'annonce.",
            "usage": "`!cloture_concours titre_du_concours`"
        },
        "annule_concours": {
            "description": "Annule un concours en cours.",
            "usage": "`!annule_concours titre_du_concours`"
        },
        "list_events": {
            "description": "Affiche tous les événements actifs avec leurs détails.",
            "usage": "`!list_events`"
        },
        "help": {
            "description": "Affiche ce message d'aide pour Poxel.",
            "usage": "`!help`"
        }
    }

    embed = discord.Embed(
        title="[ AIDE POXEL ]",
        description="""
        Salut waeky ! Je suis Poxel, ton agent de liaison personnel.
        Voici la liste de mes commandes pour t'aider à organiser des événements et des concours :
        """,
        color=discord.Color.from_rgb(255, 105, 180)
    )

    for command_name, info in commands_info.items():
        embed.add_field(
            name=f"**!{command_name}**",
            value=f"{info['description']}\nUtilisation : {info['usage']}",
            inline=False
        )
    
    embed.set_footer(text="Poxel est là pour vous aider, waeky !")
    response_msg = await ctx.send(embed=embed)
    await _delete_messages_after_delay(ctx, response_msg, delay=60) # Délai plus long pour l'aide

# --- Listener pour les interactions (boutons) ---

@bot.event
async def on_interaction(interaction):
    """
    Gère les clics sur les boutons.
    """
    if interaction.type == discord.InteractionType.component:
        custom_id_parts = interaction.data['custom_id'].split('_')
        
        # Gérer les boutons d'événements
        if len(custom_id_parts) >= 3 and custom_id_parts[1] == 'event':
            action = custom_id_parts[0]
            event_firestore_id = custom_id_parts[2]
            
            if action in ['join', 'leave']:
                await handle_event_participation(interaction, event_firestore_id, action)
        
        # Gérer les boutons de tirages au sort
        elif len(custom_id_parts) >= 3 and custom_id_parts[1] == 'raffle':
            action = custom_id_parts[0]
            raffle_firestore_id = custom_id_parts[2]

            if action == 'join':
                await handle_raffle_join(interaction, raffle_firestore_id)

    await bot.process_commands(interaction)

async def handle_event_participation(interaction: discord.Interaction, event_firestore_id: str, action: str):
    """
    Gère les clics sur les boutons "Participer" et "Quitter" pour les événements.
    """
    user = interaction.user
    event_ref = db.collection('events').document(event_firestore_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        await interaction.response.send_message("Cet événement n'existe plus ou a été terminé.", ephemeral=True)
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = interaction.guild
    role = guild.get_role(event_data['role_id'])
    is_scheduled = 'scheduled_start_time' in event_data

    # Vérifie si l'événement est déjà terminé
    if not is_scheduled and datetime.now(timezone.utc) > event_data.get('end_time', datetime.now(timezone.utc)):
        await interaction.response.send_message("Cet événement est déjà terminé, vous ne pouvez plus le rejoindre.", ephemeral=True)
        return

    if not role:
        await interaction.response.send_message("Le rôle associé à cet événement n'a pas été trouvé. L'événement est peut-être mal configuré.", ephemeral=True)
        return

    current_participants = set(event_data.get('participants', []))
    max_participants = event_data['max_participants']
    waiting_room_channel = guild.get_channel(event_data['waiting_room_channel_id'])

    if action == 'join':
        if user.id in current_participants:
            await interaction.response.send_message("Vous êtes déjà dans cet événement.", ephemeral=True)
            return
        
        if len(current_participants) >= max_participants:
            await interaction.response.send_message("Désolé, cet événement a atteint sa capacité maximale.", ephemeral=True)
            return

        try:
            # Si l'événement est planifié, le rôle n'est donné qu'au début
            if is_scheduled:
                await interaction.response.send_message(
                    f"| INFO | REGISTRATION RECEIVED ! You have been added to the list of participants. The role {role.mention} will be assigned to you at the launch of the event.",
                    ephemeral=True
                )
            else:
                await user.add_roles(role, reason=f"Participation à l'événement {event_name}")
                await interaction.response.send_message(
                    f"| INFO | WELCOME ! The role {role.mention} has been assigned to you. "
                    f"Please join the rally point {waiting_room_channel.mention} and wait to be moved.",
                    ephemeral=True
                )

            event_ref.update({'participants': firestore.ArrayUnion([user.id])})
            
            # Vérifie si le nombre max de participants est atteint après l'ajout
            updated_event_doc = event_ref.get()
            updated_participants = updated_event_doc.to_dict().get('participants', [])
            if len(updated_participants) >= max_participants:
                await interaction.channel.send(f"@everyone 🛑 Registrations for the event **'{event_name}'** are now closed, maximum capacity has been reached !")

            # Mise à jour de l'embed
            await _update_event_message(guild, event_firestore_id, is_active=not is_scheduled)

        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour vous donner ce rôle. Veuillez contacter un administrateur du serveur.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue lors de votre inscription : `{e}`", ephemeral=True)
            return

    elif action == 'leave':
        if user.id not in current_participants:
            await interaction.response.send_message("Vous ne participez pas à cet événement.", ephemeral=True)
            return

        try:
            # Le rôle n'est retiré que si l'événement n'est pas planifié
            if not is_scheduled:
                await user.remove_roles(role, reason=f"Retrait de l'événement {event_name}")
            
            event_ref.update({'participants': firestore.ArrayRemove([user.id])})
            await interaction.response.send_message(f"Vous avez quitté l'événement **'{event_name}'**. Le rôle {role.mention} a été retiré si l'événement était actif.", ephemeral=True)
            
            # Mise à jour de l'embed
            await _update_event_message(guild, event_firestore_id, is_active=not is_scheduled)

        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour vous retirer ce rôle. Veuillez contacter un administrateur du serveur.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue lors de votre départ : `{e}`", ephemeral=True)
            return

async def handle_raffle_join(interaction: discord.Interaction, raffle_firestore_id: str):
    """
    Gère les clics sur les boutons de tirage au sort.
    """
    user = interaction.user
    raffle_ref = db.collection('raffles').document(raffle_firestore_id)
    raffle_doc = raffle_ref.get()

    if not raffle_doc.exists:
        await interaction.response.send_message("Ce concours n'existe plus ou est terminé.", ephemeral=True)
        return
    
    raffle_data = raffle_doc.to_dict()
    if not raffle_data.get('is_active', False):
        await interaction.response.send_message("Ce concours est déjà terminé.", ephemeral=True)
        return
    
    participants = raffle_data.get('participants', [])
    if user.id in participants:
        await interaction.response.send_message("Vous êtes déjà inscrit à ce concours.", ephemeral=True)
        return
    
    raffle_ref.update({'participants': firestore.ArrayUnion([user.id])})
    await interaction.response.send_message(f"Vous êtes maintenant inscrit au concours **'{raffle_data['title']}'** ! Bonne chance !", ephemeral=True)

# --- Tâches en arrière-plan ---

@tasks.loop(minutes=1)
async def check_expired_events():
    """
    Tâche en arrière-plan pour vérifier et terminer les événements expirés.
    """
    try:
        now = datetime.now(timezone.utc)
        events_ref = db.collection('events')
        # Filtre les événements qui ont une `end_time` et qui sont expirés
        expired_events_docs = events_ref.where('end_time', '<=', now).get()
        
        for doc in expired_events_docs:
            event_data = doc.to_dict()
            guild = bot.get_guild(event_data['guild_id'])
            if guild:
                # Clôture l'événement
                await _close_event(doc.id, guild)
            else:
                # Si la guilde n'existe plus, on supprime l'événement de la DB
                doc.reference.delete()

    except Exception as e:
        print(f"Erreur dans la tâche check_expired_events : {e}")

@tasks.loop(minutes=1)
async def check_scheduled_events():
    """
    Tâche en arrière-plan pour lancer les événements planifiés.
    """
    try:
        now = datetime.now(timezone.utc)
        events_ref = db.collection('events')
        # Filtre les événements qui ont une `scheduled_start_time` et qui sont prêts à démarrer
        scheduled_events_docs = events_ref.where('scheduled_start_time', '<=', now).get()

        for doc in scheduled_events_docs:
            event_data = doc.to_dict()
            event_firestore_id = doc.id
            
            guild = bot.get_guild(event_data['guild_id'])
            if not guild:
                doc.reference.delete()
                print(f"Guilde non trouvée pour l'événement planifié {event_firestore_id}. Événement supprimé.")
                continue

            participants_count = len(event_data.get('participants', []))
            if participants_count < event_data['min_participants']:
                # Annule l'événement si le minimum de participants n'est pas atteint
                await _cancel_event(event_firestore_id, f"Nombre de participants insuffisant ({participants_count}/{event_data['min_participants']}).")
                continue

            role = guild.get_role(event_data['role_id'])
            
            participants_list = event_data.get('participants', [])
            for user_id in participants_list:
                member = guild.get_member(user_id)
                if member and role:
                    try:
                        await member.add_roles(role, reason=f"Lancement de l'événement planifié '{event_data['name']}'")
                        print(f"Rôle {role.name} donné à {member.display_name} pour l'événement planifié {event_data['name']}")
                    except discord.Forbidden:
                        print(f"Permissions insuffisantes pour donner le rôle {role.name} à {member.display_name}")
                    except Exception as e:
                        print(f"Erreur lors de l'attribution du rôle à {member.display_name}: {e}")

            # Met à jour le document dans Firestore en le convertissant en événement actif
            end_time = datetime.now(timezone.utc) + timedelta(seconds=parse_duration(event_data['duration_str']))
            doc.reference.update({
                'end_time': end_time,
                'is_active': True,
                'message_id': event_data['message_id'],
                'guild_id': event_data['guild_id']
            })
            doc.reference.update({ 'scheduled_start_time': firestore.DELETE_FIELD })
            
            # Met à jour les permissions du rôle pour le salon
            channel = guild.get_channel(event_data['channel_id'])
            if channel:
                await channel.set_permissions(guild.default_role, read_messages=False)
                await channel.set_permissions(role, read_messages=True, send_messages=True)
            
            # Met à jour le message embed pour qu'il reflète que l'événement est maintenant actif
            await _update_event_message(guild, event_firestore_id, is_active=True)

            # Envoie une notification aux participants
            if channel:
                mention_list = ' '.join([f'<@{p_id}>' for p_id in participants_list])
                await channel.send(f"@everyone 🚀 The event **'{event_data['name']}'** is now active and registrations are closed ! Join {guild.get_channel(event_data['waiting_room_channel_id']).mention} for the briefing.")

    except Exception as e:
        print(f"Erreur dans la tâche check_scheduled_events : {e}")

@tasks.loop(seconds=10)
async def update_event_messages():
    """
    Tâche en arrière-plan pour rafraîchir les messages des événements actifs et planifiés.
    """
    try:
        events_ref = db.collection('events')
        active_events_docs = events_ref.stream()

        for doc in active_events_docs:
            event_data = doc.to_dict()
            guild = bot.get_guild(event_data['guild_id'])
            if not guild:
                continue
            
            is_active = 'end_time' in event_data
            is_expired = False
            is_cancelled = False
            
            if is_active:
                if datetime.now(timezone.utc) > event_data['end_time']:
                    is_expired = True
                
            await _update_event_message(guild, doc.id, is_active, is_expired, is_cancelled)
            
    except Exception as e:
        print(f"Erreur dans la tâche update_event_messages : {e}")


# Exécute le bot
bot.run(TOKEN)
