import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio
import re
import os
import json

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

# --- Événements du Bot ---

@bot.event
async def on_ready():
    """
    Se déclenche lorsque le bot est connecté à Discord.
    """
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Prêt à gérer les événements !')
    check_expired_events.start()

@bot.event
async def on_command_error(ctx, error):
    """
    Gère les erreurs de commande.
    """
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Erreur de syntaxe : Il manque un argument pour cette commande. Utilisation correcte : `{ctx.command.usage}`", ephemeral=True)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Erreur d'argument : Argument invalide. Veuillez vérifier le format de vos arguments.", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("Accès refusé : Vous n'avez pas les permissions nécessaires pour exécuter cette commande (Gérer les rôles).", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Erreur de commande : {error}")
        await ctx.send(f"Erreur du système : Une erreur inattendue s'est produite : `{e}`", ephemeral=True)

# --- Commandes du Bot ---

@bot.command(name='create_event', usage='<@rôle> <#salon> <#salon_d_attente> <durée (ex: 2h, 30m)> <max_participants> <étiquette_participants> <Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, role: discord.Role, channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, duration_str: str, max_participants: int, participant_label: str, *event_name_parts):
    """
    Crée un nouvel événement avec un rôle temporaire, un salon, une durée et une capacité maximale.
    Ex: !create_event @RoleGaming #salon-prive-gaming #attente 2h 10 participants Soirée Gaming Communauté
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

    end_time = datetime.now() + timedelta(seconds=duration_seconds)

    temp_message = await ctx.send("Création de l'événement en cours...")

    event_data_firestore = {
        'name': event_name,
        'role_id': role.id,
        'channel_id': channel.id,
        'waiting_room_channel_id': waiting_room_channel.id,
        'end_time': end_time,
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
    await channel.set_permissions(ctx.guild.default_role, read_messages=False) # Empêche tout le monde de voir le salon
    await channel.set_permissions(role, read_messages=True, send_messages=True) # Donne la permission au rôle de l'événement de voir et écrire
    
    participant_list_str = get_participant_list_str(event_data_firestore.get('participants', []), ctx.guild, participant_label)

    # Création de l'embed avec un style rétro-futuriste et néon allumé
    embed = discord.Embed(
        title=f"[ NOUVELLE MISSION ]",
        description=(
            f"```fix\n"
            f"░░ Partie : {event_name}\n"
            f"░░ Rôle attribué : {role.name}\n"
            f"░░ Durée de la session : {duration_str}\n"
            f"░░ Fin de la mission : <t:{int(end_time.timestamp())}:R>\n"
            f"```\n"
            f"░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░\n"
            f"➤ Agents en ligne : {len(event_data_firestore.get('participants', []))} / {max_participants}\n"
            f"```fix\n"
            f"Participants :\n"
            f"{participant_list_str}\n"
            f"```\n"
            f"░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░\n\n"
            f"Pour participer, cliquez sur le bouton S T A R T ci-dessous.\n"
            f"Une fois inscrit, rejoignez le point de ralliement {waiting_room_channel.mention} pour le briefing de la mission.\n"
        ),
        color=discord.Color.from_rgb(255, 105, 180) # Un rose néon flamboyant
    )
    embed.set_footer(text="[ GESTION PAR POXEL ]  |  LANCEMENT EN COURS |  WAEKY")
    embed.timestamp = datetime.now()

    await temp_message.edit(content=None, embed=embed, view=view)
    await ctx.send(f"La partie **'{event_name}'** a été lancée et se terminera dans {duration_str}.", ephemeral=True)


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

    for user_id in list(event_data.get('participants', [])):
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
            await channel.send(f"La partie **'{event_name}'** est maintenant terminée. Le rôle {role.mention if role else 'temporaire'} a été retiré aux participants.")
        except discord.Forbidden:
            print(f"Permissions insuffisantes pour envoyer un message dans le salon {channel.name}")
    else:
        print(f"Salon de la partie {event_name} non trouvé.")

    try:
        event_message = await channel.fetch_message(event_data['message_id'])
        if event_message:
            embed = event_message.embeds[0]
            embed.color = discord.Color.from_rgb(200, 0, 0) # Un rouge foncé pour l'effet "éteint"
            embed.title = f"[ MISSION TERMINÉE ]"
            embed.description = f"```fix\n" \
                                f"░░ Partie : {event_name}\n" \
                                f"░░ Rôle attribué : {role.name if role else 'NON SPÉCIFIÉ'}\n" \
                                f"```\n" \
                                f"░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░\n" \
                                f"➤ Agents en ligne : {len(event_data.get('participants', []))} / {event_data['max_participants']}\n" \
                                f"```fix\n" \
                                f"Participants :\n" \
                                f"{get_participant_list_str(event_data.get('participants', []), guild, event_data.get('participant_label', 'Participant'))}\n" \
                                f"```\n" \
                                f"░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░"
            embed.set_footer(text="[ GESTION PAR POXEL ]  |  ÉVÉNEMENT EXPIRÉ  |  WAEKY")
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
        await ctx.send(f"La partie **'{event_name}'** n'existe pas ou est déjà terminée.", ephemeral=True)
        return

    event_doc_id = existing_event_docs[0].id
    
    await ctx.send(f"La partie **'{event_name}'** est en cours de fermeture...", ephemeral=True)
    await _end_event(event_doc_id)
    await ctx.send(f"La partie **'{event_name}'** a été terminée manuellement.", ephemeral=True)


@bot.command(name='list_events')
async def list_events(ctx):
    """
    Affiche la liste de tous les événements actifs.
    """
    events_ref = db.collection('events')
    active_events_docs = events_ref.stream()

    events_list = []
    for doc in active_events_docs:
        events_list.append(doc.to_dict())

    if not events_list:
        await ctx.send("```fix\n[ STATUT ] Aucune mission active pour le moment.\n```", ephemeral=True)
        return

    embed = discord.Embed(
        title="[ MISSIONS EN COURS ]",
        description="```fix\n[ SYSTÈME ] :: ACTIVÉ\n```\nAccès aux missions actives sur le serveur :",
        color=discord.Color.from_rgb(255, 105, 180) # Un rose néon flamboyant
    )

    for data in events_list:
        guild = bot.get_guild(data['guild_id'])
        role = guild.get_role(data['role_id']) if guild else None
        
        participants_count = len(data.get('participants', []))
        
        participant_list_str = get_participant_list_str(data.get('participants', []), guild, data.get('participant_label', 'Participant'))
        
        embed.add_field(
            name=f"➤ {data['name'].upper()}",
            value=(
                f"```fix\n"
                f"░░ Rôle attribué : {role.name if role else 'INTROUVABLE'}\n"
                f"░░ Participants : {participants_count} / {data['max_participants']}\n"
                f"░░ Fin de la mission : <t:{int(data['end_time'].timestamp())}:R>\n"
                f"```"
                f"```fix\n"
                f"Participants :\n"
                f"{participant_list_str}\n"
                f"```"
            ),
            inline=False
        )
    embed.set_footer(text="[ GESTION PAR POXEL ]  |  PRÊT AU COMBAT  |  WAEKY")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


async def handle_event_participation(interaction: discord.Interaction, event_firestore_id: str, action: str):
    """
    Gère les clics sur les boutons "Participer" et "Quitter".
    Prend l'ID du document Firestore.
    """
    user = interaction.user
    event_ref = db.collection('events').document(event_firestore_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        await interaction.response.send_message("Cette mission n'existe plus ou a été terminée.", ephemeral=True)
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = interaction.guild
    role = guild.get_role(event_data['role_id'])
    
    # Vérifie si l'événement est déjà terminé
    if datetime.now() > event_data['end_time']:
        await interaction.response.send_message("Cette mission est déjà terminée, vous ne pouvez plus la rejoindre.", ephemeral=True)
        return

    if not role:
        await interaction.response.send_message("Le rôle associé à cette mission n'a pas été trouvé. La partie est peut-être mal configurée.", ephemeral=True)
        return

    current_participants = set(event_data.get('participants', []))
    max_participants = event_data['max_participants']
    participant_label = event_data['participant_label']
    waiting_room_channel = guild.get_channel(event_data['waiting_room_channel_id'])

    if action == 'join':
        if user.id in current_participants:
            await interaction.response.send_message("Vous êtes déjà dans cette partie.", ephemeral=True)
            return
        if len(current_participants) >= max_participants:
            await interaction.response.send_message("Désolé, cette partie a atteint sa capacité maximale.", ephemeral=True)
            return

        try:
            await user.add_roles(role, reason=f"Participation à la partie {event_name}")
            event_ref.update({'participants': firestore.ArrayUnion([user.id])})
            # Message de bienvenue personnalisé
            await interaction.response.send_message(
                f"| INFO | BIENVENUE ! Le rôle {role.mention} vous a été attribué. "
                f"Veuillez rejoindre le point de ralliement {waiting_room_channel.mention} et patienter d'être déplacé.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour vous donner ce rôle. Veuillez contacter un administrateur du serveur.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue lors de votre inscription : `{e}`", ephemeral=True)
            return

    elif action == 'leave':
        if user.id not in current_participants:
            await interaction.response.send_message("Vous ne participez pas à cette partie.", ephemeral=True)
            return

        try:
            await user.remove_roles(role, reason=f"Quitte la partie {event_name}")
            event_ref.update({'participants': firestore.ArrayRemove([user.id])})
            await interaction.response.send_message(f"Désinscription réussie ! Vous avez quitté la mission **'{event_name}'**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour vous retirer ce rôle. Veuillez contacter un administrateur du serveur.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue lors de votre désinscription : `{e}`", ephemeral=True)
            return

    updated_event_doc = event_ref.get()
    if updated_event_doc.exists:
        updated_event_data = updated_event_doc.to_dict()
        updated_participants_count = len(updated_event_data.get('participants', []))
        
        try:
            original_message = interaction.message
            if original_message:
                embed = original_message.embeds[0]
                
                new_description = (
                    f"```fix\n"
                    f"░░ Partie : {event_name}\n"
                    f"░░ Rôle attribué : {role.name}\n"
                    f"░░ Durée de la session : {duration_str}\n" 
                    f"░░ Fin de la mission : <t:{int(event_data['end_time'].timestamp())}:R>\n"
                    f"```\n"
                    f"░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░\n"
                    f"➤ Agents en ligne : {updated_participants_count} / {max_participants}\n"
                    f"```fix\n"
                    f"Participants :\n"
                    f"{get_participant_list_str(updated_event_data.get('participants', []), guild, participant_label)}\n"
                    f"```\n"
                    f"░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░\n\n"
                    f"Pour participer, cliquez sur le bouton S T A R T ci-dessous.\n"
                    f"Une fois inscrit, rejoignez le point de ralliement {waiting_room_channel.mention} pour le briefing de la mission.\n"
                )
                
                embed.description = new_description
                await original_message.edit(embed=embed)
        except Exception as e:
            print(f"Erreur lors de la mise à jour du message de la partie : {e}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """
    Écoute toutes les interactions (y compris les clics sur les boutons).
    """
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data['custom_id']
        if custom_id.startswith("join_event_"):
            event_firestore_id = custom_id.replace("join_event_", "")
            await handle_event_participation(interaction, event_firestore_id, 'join')
        elif custom_id.startswith("leave_event_"):
            event_firestore_id = custom_id.replace("leave_event_", "")
            await handle_event_participation(interaction, event_firestore_id, 'leave')
    
    await bot.process_commands(interaction)


@tasks.loop(minutes=1)
async def check_expired_events():
    """
    Tâche en arrière-plan pour vérifier et terminer les événements expirés.
    """
    print("Vérification des événements expirés...")
    events_ref = db.collection('events')
    now = datetime.now()
    for doc in events_ref.stream():
        event_data = doc.to_dict()
        event_end_time = event_data.get('end_time')
        
        if event_end_time and event_end_time < now:
            print(f"Événement '{event_data.get('name', doc.id)}' expiré. Fin de l'événement...")
            await _end_event(doc.id)


@bot.command(name='help', usage='poxel')
async def help_command(ctx, bot_name: str = None):
    """
    Affiche toutes les commandes disponibles du bot POXEL.
    Utilisation: !help poxel
    """
    if bot_name and bot_name.lower() != 'poxel':
        await ctx.send("Désolé, je ne suis pas ce bot. Pour l'aide de POXEL, utilisez `!help poxel`.", ephemeral=True)
        return

    embed = discord.Embed(
        title="[ MANUEL D'INSTRUCTIONS ]",
        description="""
        Poxel est votre agent de liaison pour organiser les missions sur le serveur.
        Voici les commandes disponibles :
        """,
        color=discord.Color.from_rgb(255, 105, 180) # Un rose néon flamboyant
    )

    commands_info = {
        "create_event": {
            "description": "Prépare le lancement d'une nouvelle partie.",
            "usage": "`!create_event @rôle durée(ex: 2h) max_participants étiquette Nom de la partie`\nExemple : `!create_event @Joueur 1h30m 4 participants Partie de Donjons`"
        },
        "end_event": {
            "description": "Termine une partie en cours.",
            "usage": "`!end_event Nom de la partie`\nExemple : `!end_event Ma Super Partie`"
        },
        "list_events": {
            "description": "Affiche les parties actives.",
            "usage": "`!list_events`"
        },
        "help": {
            "description": "Affiche ce message d'aide.",
            "usage": "`!help poxel`"
        }
    }

    for command_name, info in commands_info.items():
        embed.add_field(
            name=f"➤ `!{command_name}`",
            value=(
                f"**Description :** {info['description']}\n"
                f"**Utilisation :** {info['usage']}"
            ),
            inline=False
        )
    
    embed.set_footer(text="[ GESTION PAR POXEL ]  |  PRÊT AU COMBAT  |  WAEKY")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


# --- Démarrage du Bot ---
bot.run(TOKEN)
