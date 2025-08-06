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
TOKEN = os.environ['DISCORD_TOKEN']

# --- Configuration Firebase ---
firebase_key_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY')
firebase_key_filename = 'serviceAccountKey.json'

if firebase_key_json:
    try:
        with open(firebase_key_filename, 'w') as f:
            f.write(firebase_key_json)
        print("Fichier serviceAccountKey.json créé avec succès à partir de la variable d'environnement.")
    except Exception as e:
        print(f"Erreur lors de la création du fichier Firebase : {e}")
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
            participant_list.append(f"{participant_label} **{member.display_name}**")
    
    return "\n".join(participant_list)

def get_days_until(target_time: datetime) -> str:
    """
    Calcule le nombre de jours jusqu'à une date cible.
    """
    now = datetime.now(timezone.utc)
    delta = target_time - now
    if delta.total_seconds() < 0:
        return "Maintenant"
    days = delta.days
    if days > 0:
        return f"{days} jour{'s' if days > 1 else ''}"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours} heure{'s' if hours > 1 else ''}"
    minutes = (delta.seconds % 3600) // 60
    if minutes > 0:
        return f"{minutes} minute{'s' if minutes > 1 else ''}"
    return "Bientôt !"

async def _create_event_embed(event_data, guild, is_active: bool, is_expired: bool = False):
    """
    Crée un embed d'événement avec un visuel cohérent.
    """
    if is_expired:
        embed_title = "[ ÉVÉNEMENT TERMINÉ ]"
        embed_color = discord.Color.from_rgb(200, 0, 0)
        footer_text = "[ GESTION PAR POXEL ]  |  ÉVÉNEMENT EXPIRÉ  |  WAEKY"
        time_info = ""
    elif is_active:
        embed_title = "[ NOUVEL ÉVÉNEMENT ]"
        embed_color = discord.Color.from_rgb(255, 105, 180)
        footer_text = "[ GESTION PAR POXEL ]  |  LANCEMENT EN COURS |  WAEKY"
        time_info = (f"Durée de l'événement : {event_data.get('duration_str', 'Indéfinie')}\n"
                     f"Fin de l'événement : <t:{int(event_data['end_time'].timestamp())}:R>")
    else: # Événement planifié
        embed_title = "[ ÉVÉNEMENT PLANIFIÉ ]"
        embed_color = discord.Color.from_rgb(255, 200, 50)
        footer_text = "[ GESTION PAR POXEL ]  |  EN ATTENTE DE LANCEMENT |  WAEKY"
        days_until = get_days_until(event_data['scheduled_start_time'])
        time_info = (f"Durée de l'événement : {event_data.get('duration_str', 'Indéfinie')}\n"
                     f"Début de l'événement : dans {days_until}\n"
                     f"Début de l'événement : <t:{int(event_data['scheduled_start_time'].timestamp())}:F>")

    role = guild.get_role(event_data['role_id'])
    participant_list_str = get_participant_list_str(event_data.get('participants', []), guild, event_data.get('participant_label', 'Participant'))

    description = (
        f"```fix\n"
        f"Partie : {event_data['name']}\n"
        f"Rôle attribué : {role.name if role else 'NON SPÉCIFIÉ'}\n"
        f"{time_info}\n"
        f"```\n"
        f"Participants en ligne : {len(event_data.get('participants', []))} / {event_data['max_participants']}\n"
        f"```fix\n"
        f"Participants :\n"
        f"{participant_list_str}\n"
        f"```\n"
        f"Pour participer, cliquez sur le bouton S T A R T ci-dessous.\n"
        f"Une fois inscrit, rejoignez le point de ralliement {guild.get_channel(event_data['waiting_room_channel_id']).mention} pour le briefing de l'événement.\n"
    )
    
    embed = discord.Embed(
        title=embed_title,
        description=description,
        color=embed_color
    )
    embed.set_footer(text=footer_text)
    embed.timestamp = datetime.now()
    return embed


async def _update_event_message(ctx, event_firestore_id: str, is_active: bool, is_expired: bool = False):
    """
    Met à jour le message d'événement avec les dernières informations.
    """
    event_ref = db.collection('events').document(event_firestore_id)
    event_doc = event_ref.get()
    
    if not event_doc.exists:
        return

    event_data = event_doc.to_dict()
    guild = ctx.guild
    
    try:
        channel = guild.get_channel(event_data['channel_id'])
        if not channel: return
        
        event_message = await channel.fetch_message(event_data['message_id'])
        if not event_message: return

        # Crée une nouvelle View pour s'assurer que les boutons sont actifs
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
        
        embed = await _create_event_embed(event_data, guild, is_active, is_expired)
        
        if is_expired:
            view = None # Désactiver les boutons
        
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


# --- Événements du Bot ---

@bot.event
async def on_ready():
    """
    Se déclenche lorsque le bot est connecté à Discord.
    """
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Prêt à gérer les événements et les concours !')
    check_expired_events.start()
    check_scheduled_events.start()

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

@bot.command(name='create_event', usage='<@rôle> <#salon> <#salon_d_attente> <durée (ex: 2h, 30m)> <max_participants> <étiquette_participants> <Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, role: discord.Role, channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, duration_str: str, max_participants: int, participant_label: str, *event_name_parts):
    """
    Crée un nouvel événement immédiat.
    Ex: !create_event @RoleGaming #salon-prive-gaming #attente 2h 10 joueurs Soirée Gaming Communauté
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

    if max_participants <= 0:
        await ctx.send("Le nombre maximum de participants doit être supérieur à zéro.", ephemeral=True)
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
    await ctx.send(f"@everyone 🎉 Un nouvel événement a commencé ! Rejoignez **{event_name}** dans {channel.mention} !")

    # Message de confirmation qui sera supprimé après un délai
    confirmation_msg = await ctx.send(f"La partie **'{event_name}'** a été lancée et se terminera dans {duration_str}.", ephemeral=True)
    await _delete_messages_after_delay(ctx, confirmation_msg, delay=30)


@bot.command(name='planifier_evenement', usage='<@rôle> <#salon> <#salon_d_attente> <durée (ex: 2h, 30m)> <date_début (YYYY-MM-DDTHH:mm)> <max_participants> <étiquette_participants> <Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def planifier_evenement(ctx, role: discord.Role, channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, duration_str: str, scheduled_time_str: str, max_participants: int, participant_label: str, *event_name_parts):
    """
    Planifie un nouvel événement pour un lancement ultérieur.
    Ex: !planifier_evenement @RoleGaming #salon-prive #attente 2h 2024-08-01T20:00 10 joueurs Soirée Gaming Futur
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

    if max_participants <= 0:
        await ctx.send("Le nombre maximum de participants doit être supérieur à zéro.", ephemeral=True)
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
    await ctx.send(f"@everyone 📣 Un nouvel événement planifié a été créé : **{event_name}** ! Il démarrera à <t:{int(scheduled_start_time.timestamp())}:F>. Rejoignez-le maintenant dans {channel.mention} !")

    # Message de confirmation qui sera supprimé après un délai
    confirmation_msg = await ctx.send(f"La partie **'{event_name}'** a été planifiée pour démarrer à <t:{int(scheduled_start_time.timestamp())}:F>.", ephemeral=True)
    await _delete_messages_after_delay(ctx, confirmation_msg, delay=30)


async def _end_event(event_doc_id: str):
    """
    Fonction interne pour terminer un événement, retirer les rôles et nettoyer.
    Prend l'ID du document Firestore.
    """
    event_ref = db.collection('events').document(event_doc_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        print(f"Tentative de terminer un événement non existant dans Firestore : {event_doc_id}")
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
                await member.remove_roles(role, reason=f"Fin de la partie {event_name}")
                print(f"Rôle {role.name} retiré à {member.display_name} pour la partie {event_name}")
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour retirer le rôle {role.name} à {member.display_name}")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle à {member.display_name}: {e}")

    event_ref.delete()
    print(f"Événement '{event_name}' (ID: {event_doc_id}) supprimé de Firestore.")

    if channel:
        try:
            # Envoi de la notification @everyone
            await channel.send(f"@everyone 🛑 L'événement **'{event_name}'** est maintenant terminé. Merci à tous les participants !")
        except discord.Forbidden:
            print(f"Permissions insuffisantes pour envoyer un message dans le salon {channel.name}")
    else:
        print(f"Salon de la partie {event_name} non trouvé.")

    try:
        event_message = await channel.fetch_message(event_data['message_id'])
        if event_message:
            embed = await _create_event_embed(event_data, guild, is_active=False, is_expired=True)
            await event_message.edit(embed=embed, view=None)
    except discord.NotFound:
        print(f"Message de la partie {event_name} (ID: {event_doc_id}) non trouvé sur Discord. Il a peut-être été supprimé manuellement.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de la partie : {e}")


@bot.command(name='end_event', usage='<Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def end_event_command(ctx, *event_name_parts):
    """
    Termine manuellement un événement et retire les rôles aux participants.
    Ex: !end_event Soirée Gaming Communauté
    """
    event_name = " ".join(event_name_parts)
    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()

    if not existing_event_docs:
        response_msg = await ctx.send(f"L'événement **'{event_name}'** n'existe pas ou est déjà terminé.", ephemeral=True)
        await _delete_messages_after_delay(ctx, response_msg, delay=30)
        return

    event_doc_id = existing_event_docs[0].id
    
    response_msg = await ctx.send(f"L'événement **'{event_name}'** est en cours de fermeture...", ephemeral=True)
    await _end_event(event_doc_id)
    confirmation_msg = await ctx.send(f"L'événement **'{event_name}'** a été terminé manuellement.", ephemeral=True)
    
    await _delete_messages_after_delay(ctx, response_msg, delay=30)
    await _delete_messages_after_delay(ctx, confirmation_msg, delay=30)


@bot.command(name='list_events')
async def list_events(ctx):
    """
    Affiche la liste de tous les événements actifs et planifiés et supprime les messages.
    """
    events_ref = db.collection('events')
    active_events_docs = events_ref.stream()

    events_list = []
    for doc in active_events_docs:
        events_list.append(doc.to_dict())

    if not events_list:
        response_msg = await ctx.send("```fix\n[ STATUT ] Aucun événement actif ou planifié pour le moment.\n```", ephemeral=True)
        await _delete_messages_after_delay(ctx, response_msg, delay=30)
        return

    embed = discord.Embed(
        title="[ ÉVÉNEMENTS EN COURS ]",
        description="""
        Poxel est votre agent de liaison pour organiser les événements sur le serveur.
        Voici la liste des événements actifs et planifiés :
        """,
        color=discord.Color.from_rgb(255, 105, 180) # Un rose néon flamboyant
    )

    for data in events_list:
        guild = bot.get_guild(data['guild_id'])
        role = guild.get_role(data['role_id']) if guild else None
        
        participants_count = len(data.get('participants', []))
        
        # Détermine si l'événement est actif ou planifié
        if 'scheduled_start_time' in data:
            status = "PLANIFIÉ"
            time_info = f"Début de l'événement : <t:{int(data['scheduled_start_time'].timestamp())}:R>"
            field_name = f"➤ `[PLANIFIÉ]` {data['name'].upper()}"
        else:
            status = "EN COURS"
            time_info = f"Fin de l'événement : <t:{int(data['end_time'].timestamp())}:R>"
            field_name = f"➤ `[EN COURS]` {data['name'].upper()}"

        embed.add_field(
            name=field_name,
            value=(
                f"**Rôle attribué :** {role.name if role else 'INTROUVABLE'}\n"
                f"**Participants :** {participants_count} / {data['max_participants']}\n"
                f"**Statut :** {status}\n"
                f"**{time_info}**\n"
            ),
            inline=False
        )
    embed.set_footer(text="[ GESTION PAR POXEL ]  |  PRÊT AU COMBAT  |  WAEKY")
    embed.timestamp = datetime.now()
    
    response_msg = await ctx.send(embed=embed)
    await _delete_messages_after_delay(ctx, response_msg, delay=30)


@bot.command(name='tirage_au_sort', usage='<nombre_de_gagnants> <titre_du_concours>')
@commands.has_permissions(manage_roles=True)
async def tirage_au_sort(ctx, num_winners: int, *raffle_title_parts):
    """
    Crée un concours où les membres peuvent s'inscrire pour un tirage au sort.
    Ex: !tirage_au_sort 10 Un lot de 50€
    """
    raffle_title = " ".join(raffle_title_parts)
    if not raffle_title:
        await ctx.send("Veuillez spécifier un titre pour le concours.", ephemeral=True)
        return
    if num_winners <= 0:
        await ctx.send("Le nombre de gagnants doit être supérieur à zéro.", ephemeral=True)
        return
    
    # Vérifier s'il y a déjà un tirage en cours
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
        title=f"[ NOUVEAU CONCOURS ] : {raffle_title}",
        description=f"🎉 Un tout nouveau concours a été lancé ! 🎉\n\n"
                    f"Pour y participer, cliquez sur le bouton `PARTICIPER` ci-dessous.\n"
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
    
    await ctx.send(f"@everyone 🎁 **Nouveau concours** : {raffle_title} ! Tentez votre chance ici : {raffle_message.jump_url}")

@bot.command(name='draw_raffle', usage='<titre_du_concours>')
@commands.has_permissions(manage_roles=True)
async def draw_raffle(ctx, *raffle_title_parts):
    """
    Tire au sort les gagnants d'un concours en cours.
    Ex: !draw_raffle Un lot de 50€
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

    if not participants or len(participants) < num_winners:
        await ctx.send(f"Il n'y a pas assez de participants pour tirer {num_winners} gagnants.", ephemeral=True)
        return

    winners_ids = random.sample(participants, k=num_winners)
    winners_mentions = [f'<@{w_id}>' for w_id in winners_ids]
    
    winners_str = ", ".join(winners_mentions)
    
    embed = discord.Embed(
        title=f"[ RÉSULTATS DU CONCOURS ] : {raffle_title}",
        description=f"🎉 **Félicitations aux gagnants !** 🎉\n\n"
                    f"Les gagnants sont : {winners_str}",
        color=discord.Color.from_rgb(0, 255, 0)
    )

    await ctx.send(f"@everyone 🏆 Le tirage au sort de **{raffle_title}** est terminé ! Découvrez les gagnants ci-dessous :", embed=embed)
    
    # Désactiver le tirage au sort en cours
    raffle_doc.reference.update({'is_active': False})


@bot.command(name='help')
async def help_command(ctx):
    """
    Affiche un message d'aide détaillé et supprime les messages après un délai.
    """
    commands_info = {
        "create_event": {
            "description": "Crée un nouvel événement immédiat.",
            "usage": "`!create_event @rôle #salon #salon_d_attente durée(ex: 2h) max_participants étiquette_participants Nom de l'événement`\n"
                     "Ex: `!create_event @Joueur #salon-jeu #attente 1h30m 4 joueurs Partie de Donjons`"
        },
        "planifier_evenement": {
            "description": "Planifie un événement pour un lancement ultérieur.",
            "usage": "`!planifier_evenement @rôle #salon #salon_d_attente durée date_début(YYYY-MM-DDTHH:mm) max_participants étiquette_participants Nom`\n"
                     "Ex: `!planifier_evenement @RoleGaming #prive #attente 2h 2024-08-01T20:00 10 joueurs Soirée Futur`"
        },
        "end_event": {
            "description": "Termine un événement en cours et retire les rôles aux participants.",
            "usage": "`!end_event Nom de l'événement`\n"
                     "Ex: `!end_event Ma Super Partie`"
        },
        "list_events": {
            "description": "Affiche tous les événements actifs avec leurs détails.",
            "usage": "`!list_events`"
        },
        "tirage_au_sort": {
            "description": "Crée un concours et met en place un tirage au sort.",
            "usage": "`!tirage_au_sort nombre_de_gagnants titre_du_concours`\n"
                     "Ex: `!tirage_au_sort 10 Un lot de 50€`"
        },
        "draw_raffle": {
            "description": "Tire au sort les gagnants d'un concours.",
            "usage": "`!draw_raffle titre_du_concours`"
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
    if not is_scheduled and datetime.now(timezone.utc) > event_data['end_time']:
        await interaction.response.send_message("Cet événement est déjà terminé, vous ne pouvez plus le rejoindre.", ephemeral=True)
        return

    if not role:
        await interaction.response.send_message("Le rôle associé à cet événement n'a pas été trouvé. L'événement est peut-être mal configuré.", ephemeral=True)
        return

    current_participants = set(event_data.get('participants', []))
    max_participants = event_data['max_participants']
    participant_label = event_data['participant_label']
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
                    f"| INFO | INSCRIPTION REÇUE ! Vous avez été ajouté à la liste des participants. Le rôle {role.mention} vous sera attribué au lancement de l'événement.",
                    ephemeral=True
                )
            else:
                await user.add_roles(role, reason=f"Participation à l'événement {event_name}")
                await interaction.response.send_message(
                    f"| INFO | BIENVENUE ! Le rôle {role.mention} vous a été attribué. "
                    f"Veuillez rejoindre le point de ralliement {waiting_room_channel.mention} et patienter d'être déplacé.",
                    ephemeral=True
                )

            event_ref.update({'participants': firestore.ArrayUnion([user.id])})

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
        expired_events_docs = events_ref.where('end_time', '<=', now).get()
        
        for doc in expired_events_docs:
            await _end_event(doc.id)

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
        scheduled_events_docs = events_ref.where('scheduled_start_time', '<=', now).get()

        for doc in scheduled_events_docs:
            event_data = doc.to_dict()
            event_firestore_id = doc.id
            
            guild = bot.get_guild(event_data['guild_id'])
            if not guild:
                print(f"Guilde non trouvée pour l'événement planifié {event_firestore_id}.")
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
            await _update_event_message(guild.get_channel(event_data['channel_id']), event_firestore_id, True)

            # Envoie une notification aux participants
            if channel:
                mention_list = ' '.join([f'<@{p_id}>' for p_id in participants_list])
                await channel.send(f"@everyone 🚀 L'événement **'{event_data['name']}'** est maintenant actif ! Rejoignez {guild.get_channel(event_data['waiting_room_channel_id']).mention} pour le briefing.")

    except Exception as e:
        print(f"Erreur dans la tâche check_scheduled_events : {e}")

# Exécute le bot
bot.run(TOKEN)
