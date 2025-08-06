import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import asyncio
import re
import os
import threading
from flask import Flask, jsonify
import requests
import time
import json
import traceback # Ajouté pour afficher la trace complète des erreurs

import firebase_admin
from firebase_admin import credentials, firestore

# --- Configuration du Bot ---
TOKEN = os.environ.get('DISCORD_TOKEN')

if not TOKEN:
    print("ERREUR : Le TOKEN Discord n'est pas configuré dans les variables d'environnement.")
    exit()

# --- Configuration Firebase ---
try:
    # Récupère les identifiants depuis la variable d'environnement
    firebase_credentials_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if not firebase_credentials_json:
        print("ERREUR : La variable d'environnement 'FIREBASE_CREDENTIALS_JSON' est manquante.")
        exit()

    # Charge les identifiants JSON depuis la chaîne de caractères
    cred_dict = json.loads(firebase_credentials_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialisé avec succès.")
except Exception as e:
    print(f"ERREUR lors de l'initialisation de Firebase Admin SDK: {e}")
    print("Assurez-vous que 'FIREBASE_CREDENTIALS_JSON' est valide et correctement formaté.")
    exit()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- Flask App pour le Keep-Alive ---
app = Flask(__name__)

@app.route('/')
def home():
    """Point d'accès simple pour vérifier que le serveur Flask est en ligne."""
    return "Bot Discord POXEL est en ligne et opérationnel !"

# Fonction pour exécuter le bot Discord avec gestion des retries
def run_discord_bot():
    """Exécute le bot Discord sur son propre thread avec une logique de retry."""
    retry_delay = 5 # Délai initial en secondes
    max_retry_delay = 600 # Délai maximum (10 minutes)

    while True:
        try:
            # Crée et définit un nouveau cycle d'événements pour ce thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            print(f"Tentative de connexion du bot Discord... (prochaine tentative dans {retry_delay}s si échec)")
            bot.run(TOKEN)
            # Si cette ligne est atteinte, cela signifie que bot.run() s'est terminé.
            # Cela ne devrait arriver que si le bot se déconnecte ou s'arrête.
            print("Le bot Discord s'est déconnecté ou l'exécution de bot.run() s'est terminée. Tentative de reconnexion...")
            retry_delay = 5 # Réinitialise le délai après une déconnexion ou une fin d'exécution
            time.sleep(retry_delay) # Attend avant de retenter la connexion
        except discord.errors.HTTPException as e:
            if e.status == 429: # Too Many Requests
                print(f"ERREUR 429 (Too Many Requests) : Discord nous limite. Nouvelle tentative dans {retry_delay}s.")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay) # Augmente le délai de manière exponentielle
            else:
                print(f"ERREUR HTTP Discord inattendue ({e.status}) : {e}. Nouvelle tentative dans {retry_delay}s.")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
        except discord.LoginFailure:
            print("ERREUR DE CONNEXION : Jeton Discord invalide. Veuillez vérifier votre DISCORD_TOKEN. Arrêt du bot.")
            break # Arrête le thread si le jeton est invalide
        except Exception as e:
            print(f"ERREUR INATTENDUE LORS DE L'EXÉCUTION DU BOT : {e}.")
            traceback.print_exc() # Affiche la trace complète de l'erreur
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)
        finally:
            # S'assure que le cycle d'événements est fermé s'il a été créé
            if 'loop' in locals() and not loop.is_closed():
                loop.close()

# Fonction pour pinger l'URL de Render et maintenir le service actif
def ping_self():
    """Tâche pour pinger l'URL du bot afin de le maintenir actif."""
    while True:
        try:
            # L'URL de votre service Render
            # Assurez-vous que cette URL est correcte pour votre déploiement Render
            # REMPLACEZ 'https://poxel-bot.onrender.com' par l'URL réelle de votre service Render !
            response = requests.get('https://poxel-bot.onrender.com')
            print(f"Ping de l'URL réussi avec le statut {response.status_code}")
        except requests.exceptions.ConnectionError:
            print("AVERTISSEMENT : Impossible de pinger l'URL. Le service Render n'est peut-être pas encore prêt ou l'URL est incorrecte.")
        except Exception as e:
            print(f"Erreur lors du ping de l'URL : {e}")
        time.sleep(300) # Attend 5 minutes (300 secondes)

# --- Fonctions Utilitaires ---
def parse_duration(duration_str: str) -> int:
    """
    Parse une chaîne de durée (ex: "2h", "30m", "5s") en secondes.
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

async def _update_event_embed(guild, event_data, message_id):
    """
    Met à jour l'embed de l'événement avec les participants actuels.
    """
    text_channel = guild.get_channel(event_data['text_channel_id'])
    if not text_channel:
        return
    try:
        event_message = await text_channel.fetch_message(message_id)
        if not event_message:
            return
        embed = event_message.embeds[0]
        participants_mentions = []
        for user_id in event_data.get('participants', []):
            member = guild.get_member(user_id)
            if member:
                participants_mentions.append(member.mention)
        players_field_value = "\n".join(participants_mentions) if participants_mentions else "*Aucun joueur inscrit pour le moment.*"
        embed.set_field_at(
            0,
            name=f"**Joueurs inscrits ({len(participants_mentions)} / {event_data['max_participants']})**",
            value=players_field_value,
            inline=False
        )
        await event_message.edit(embed=embed)
    except discord.NotFound:
        print(f"Message de la partie non trouvé pour la mise à jour : {message_id}")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de la partie : {e}")

# --- Événements du Bot ---
@bot.event
async def on_ready():
    """
    Se déclenche lorsque le bot est connecté à Discord et prêt.
    """
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Prêt à gérer les parties !')
    # Démarre la tâche de vérification des événements expirés
    check_expired_events.start()
    
    # La tâche d'auto-ping est maintenant démarrée au début du script,
    # donc pas besoin de la démarrer ici.


@bot.event
async def on_command_error(ctx, error):
    """
    Gère les erreurs de commande pour une meilleure expérience utilisateur.
    """
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"| ERREUR | ARGUMENT MANQUANT\n> `!{ctx.command.name} {ctx.command.usage}`", ephemeral=True)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"| ERREUR | ARGUMENT INVALIDE", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("| ERREUR | PERMISSION REFUSÉE", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass # Ignore les commandes qui n'existent pas
    else:
        print(f"Erreur de commande : {error}")
        await ctx.send(f"| ERREUR | INATTENDUE : `{error}`", ephemeral=True)

# --- Commandes du Bot ---
@bot.command(name='create_event', usage='<@rôle> <#salon_textuel> <durée (ex: 2h, 30m)> <max_participants> <étiquette_participants> <#salon_attente_vocal> <#salon_de_jeu_vocal> <Nom de la partie>')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, role: discord.Role, text_channel: discord.TextChannel, duration_str: str, max_participants: int, participant_label: str, waiting_room_channel: discord.VoiceChannel, destination_voice_channel: discord.VoiceChannel, *event_name_parts):
    """
    Crée une nouvelle partie avec un rôle temporaire, des salons et une durée.
    """
    event_name = " ".join(event_name_parts)
    if not event_name:
        await ctx.send("| ERREUR | NOM DE LA PARTIE MANQUANT", ephemeral=True)
        return
    if max_participants <= 0:
        await ctx.send("| ERREUR | CAPACITÉ DE JOUEURS INVALIDE", ephemeral=True)
        return

    try:
        duration_seconds = parse_duration(duration_str)
    except ValueError as e:
        await ctx.send(f"| ERREUR | {str(e).upper()}", ephemeral=True)
        return
    
    @firestore.transactional
    async def create_event_in_transaction(transaction, event_name, ctx, role, duration_seconds, max_participants, participant_label, waiting_room_channel, destination_voice_channel):
        events_ref = db.collection('events')
        existing_event_docs = events_ref.where('name', '==', event_name).get(transaction=transaction)
        
        if existing_event_docs:
            existing_event_doc = existing_event_docs[0]
            event_data = existing_event_doc.to_dict()
            
            if datetime.now(timezone.utc) > event_data['end_time'].replace(tzinfo=timezone.utc):
                await _end_event(existing_event_doc.id)
            else:
                raise Exception(f"La partie '{event_name}' existe déjà et n'est pas terminée.")

        end_time = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        temp_message = await ctx.send(">>> Chargement de la partie...")

        event_data_firestore = {
            'name': event_name,
            'role_id': role.id,
            'text_channel_id': text_channel.id,
            'waiting_room_channel_id': waiting_room_channel.id,
            'destination_voice_channel_id': destination_voice_channel.id,
            'end_time': end_time,
            'max_participants': max_participants,
            'participant_label': participant_label,
            'participants': [],
            'message_id': temp_message.id,
            'guild_id': ctx.guild.id
        }
        
        new_event_ref = events_ref.document()
        transaction.set(new_event_ref, event_data_firestore)
        event_firestore_id = new_event_ref.id

        view = discord.ui.View(timeout=None)
        start_button = discord.ui.Button(
            label="START", 
            style=discord.ButtonStyle.primary,
            custom_id=f"join_event_{event_firestore_id}",
            emoji="🎮"
        )
        leave_button = discord.ui.Button(
            label="EXIT", 
            style=discord.ButtonStyle.danger,
            custom_id=f"leave_event_{event_firestore_id}",
            emoji="🚪"
        )

        view.add_item(start_button)
        view.add_item(leave_button)

        embed = discord.Embed(
            title=f"NOUVELLE PARTIE : {event_name.upper()}",
            description=f"**Une nouvelle partie a été lancée ! Préparez-vous à jouer !**",
            color=discord.Color.from_rgb(255, 0, 154) # Rose néon
        )
        embed.add_field(name=f"**Joueurs inscrits (0 / {max_participants})**", value="*Aucun joueur inscrit pour le moment.*", inline=False)
        embed.add_field(name="**Rôle requis :**", value=f"{role.mention}", inline=True)
        embed.add_field(name="**Salon de jeu :**", value=f"{text_channel.mention}", inline=True)
        embed.add_field(name="**Durée :**", value=f"{duration_str} (Fin de partie <t:{int(end_time.timestamp())}:R>)", inline=False)
        embed.add_field(name="**Comment rejoindre ?**", value=f"1. Appuyez sur le bouton 'START'.\n2. Vous obtiendrez votre rôle et serez prêt à être déplacé vers le salon de jeu !", inline=False)
        embed.set_footer(text="| P.O.X.E.L | Appuyez sur START pour participer.", icon_url="https://images.emojiterra.com/google/noto-emoji/v2.034/512px/1f47d.png")
        embed.timestamp = datetime.now()

        await temp_message.edit(content=None, embed=embed, view=view)
        await ctx.send(f"| INFO | PARTIE '{event_name.upper()}' CRÉÉE", ephemeral=True)
        
    try:
        await create_event_in_transaction(db.transaction(), event_name, ctx, role, duration_seconds, max_participants, participant_label, waiting_room_channel, destination_voice_channel)
    except Exception as e:
        if str(e).startswith("La partie"):
            await ctx.send(f"| ERREUR | {str(e).upper()}", ephemeral=True)
        else:
            await ctx.send(f"| ERREUR | UN PROBLÈME EST SURVENU LORS DE LA CRÉATION DE LA PARTIE : {e}", ephemeral=True)


async def _end_event(event_doc_id: str):
    """
    Fonction interne pour terminer un événement, retirer les rôles et nettoyer.
    """
    event_ref = db.collection('events').document(event_doc_id)
    event_doc = event_ref.get()
    if not event_doc.exists:
        print(f"Tentative de terminer une partie non existante dans Firestore : {event_doc_id}")
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = bot.get_guild(event_data['guild_id'])
    if not guild:
        print(f"Guilde non trouvée pour la partie {event_name} (ID: {event_doc_id})")
        event_ref.delete()
        return

    role = guild.get_role(event_data['role_id'])
    text_channel = guild.get_channel(event_data['text_channel_id'])

    all_participants = list(event_data.get('participants', []))
    for user_id in all_participants:
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
    print(f"Partie '{event_name}' (ID: {event_doc_id}) supprimée de Firestore.")

    if text_channel:
        try:
            await text_channel.send(f"| ALERTE | FIN DE PARTIE : '{event_name.upper()}'")
        except discord.Forbidden:
            print(f"Permissions insuffisantes pour envoyer un message dans le salon {text_channel.name}")
    else:
        print(f"Salon de la partie {event_name} non trouvé.")

    try:
        event_message = await text_channel.fetch_message(event_data['message_id'])
        if event_message:
            embed = event_message.embeds[0]
            embed.color = discord.Color.from_rgb(0, 158, 255) # Bleu
            embed.title = f"PARTIE TERMINÉE : {event_name.upper()}"
            embed.description = f"**La partie est terminée. Bien joué !**"
            embed.clear_fields()
            embed.add_field(name="**Score final :**", value=f"{len(event_data.get('participants', []))} / {event_data['max_participants']} {event_data['participant_label']}", inline=False)
            await event_message.edit(embed=embed, view=None)
    except discord.NotFound:
        print(f"Message de la partie {event_name} (ID: {event_doc_id}) non trouvé sur Discord. Il a peut-être été supprimé manuellement.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de la partie : {e}")


@bot.command(name='end_event', usage='<Nom de la partie>')
@commands.has_permissions(manage_roles=True)
async def end_event_command(ctx, *event_name_parts):
    """
    Termine manuellement un événement et retire les rôles aux participants.
    """
    event_name = " ".join(event_name_parts)
    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()

    if not existing_event_docs:
        await ctx.send(f"| ERREUR | LA PARTIE '{event_name.upper()}' N'EXISTE PAS", ephemeral=True)
        return

    event_doc_id = existing_event_docs[0].id
    
    await ctx.send(f">>> Fin de la partie '{event_name.upper()}' en cours...", ephemeral=True)
    await _end_event(event_doc_id)
    await ctx.send(f"| INFO | PARTIE '{event_name.upper()}' TERMINÉE MANUELLEMENT", ephemeral=True)


@bot.command(name='move_participants', usage='<Nom de la partie>')
@commands.has_permissions(move_members=True)
async def move_participants(ctx, *event_name_parts):
    """
    Déplace tous les participants d'une partie vers le salon de jeu.
    """
    event_name = " ".join(event_name_parts)
    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()

    if not existing_event_docs:
        await ctx.send(f"| ERREUR | LA PARTIE '{event_name.upper()}' N'EXISTE PAS", ephemeral=True)
        return

    event_data = existing_event_docs[0].to_dict()
    guild = ctx.guild
    
    destination_channel = guild.get_channel(event_data['destination_voice_channel_id'])
    if not destination_channel:
        await ctx.send(f"| ERREUR | LE SALON DE DESTINATION N'A PAS ÉTÉ TROUVÉ.", ephemeral=True)
        return

    participants_count = 0
    for user_id in event_data.get('participants', []):
        member = guild.get_member(user_id)
        if member and member.voice and member.voice.channel:
            try:
                await member.move_to(destination_channel, reason=f"Déplacement pour la partie {event_name}")
                participants_count += 1
                await asyncio.sleep(0.5) # Pour éviter de dépasser la limite de requêtes de Discord
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour déplacer {member.display_name}.")
            except Exception as e:
                print(f"Erreur lors du déplacement de {member.display_name}: {e}")

    if participants_count > 0:
        await ctx.send(f"| INFO | {participants_count} JOUEURS ONT ÉTÉ DÉPLACÉS VERS {destination_channel.mention}", ephemeral=False)
    else:
        await ctx.send(f"| INFO | AUCUN JOUEUR À DÉPLACER POUR LA PARTIE '{event_name.upper()}'", ephemeral=True)


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
        await ctx.send("```\n[AUCUNE PARTIE EN COURS]\n```", ephemeral=True)
        return

    embed = discord.Embed(
        title="| PARTIES ACTIVES |",
        description="Voici la liste des parties en cours :",
        color=discord.Color.from_rgb(0, 158, 255) # Bleu électrique
    )

    for data in events_list:
        guild = bot.get_guild(data['guild_id'])
        role = guild.get_role(data['role_id']) if guild else None
        text_channel = guild.get_channel(data['text_channel_id']) if guild else None
        waiting_room_channel = guild.get_channel(data['waiting_room_channel_id']) if guild else None

        participants_count = len(data.get('participants', []))
        
        embed.add_field(
            name=f"🎮 {data['name'].upper()}",
            value=(
                f"**Rôle requis :** {role.mention if role else 'NON TROUVÉ'}\n"
                f"**Salon de jeu :** {text_channel.mention if text_channel else 'NON TROUVÉ'}\n"
                f"**Salon d'attente :** {waiting_room_channel.mention if waiting_room_channel else 'NON TROUVÉ'}\n"
                f"**Joueurs inscrits :** {participants_count} / {data['max_participants']} {data['participant_label']}\n"
                f"**Fin de partie :** <t:{int(data['end_time'].timestamp())}:R>"
            ),
            inline=False
        )
    embed.set_footer(text="| P.O.X.E.L | Base de données des parties", icon_url="https://images.emojiterra.com/google/noto-emoji/v2.034/512px/1f47d.png")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


@bot.command(name='intro', usage='[description]')
@commands.has_permissions(manage_guild=True)
async def intro_command(ctx):
    """
    Affiche la présentation de Poxel et ses commandes.
    """
    embed = discord.Embed(
        title="| P.O.X.E.L ASSISTANT |",
        description=(
            f"**Bonjour waeky !**\n"
            f"Je suis Poxel, votre assistant personnel pour l'organisation de parties de jeux.\n"
            f"Utilisez `!help poxel` pour voir toutes mes commandes."
        ),
        color=discord.Color.from_rgb(145, 70, 255) # Violet de Twitch
    )
    embed.set_footer(text="Système en ligne.", icon_url="https://images.emojiterra.com/google/noto-emoji/v2.034/512px/1f47d.png")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


async def handle_event_participation(interaction: discord.Interaction, event_firestore_id: str, action: str):
    """
    Gère les clics sur les boutons "START" et "EXIT".
    """
    user = interaction.user
    event_ref = db.collection('events').document(event_firestore_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        await interaction.response.send_message("| ALERTE | CETTE PARTIE N'EST PLUS ACTIVE", ephemeral=True)
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = interaction.guild
    role = guild.get_role(event_data['role_id'])

    if not role:
        await interaction.response.send_message("| ERREUR | RÔLE DE JOUEUR INTROUVABLE", ephemeral=True)
        return

    current_participants = set(event_data.get('participants', []))
    max_participants = event_data['max_participants']
    
    if action == 'join':
        if user.id in current_participants:
            await interaction.response.send_message("| ALERTE | VOUS ÊTES DÉJÀ DANS LA PARTIE", ephemeral=True)
            return
        if len(current_participants) >= max_participants:
            await interaction.response.send_message("| ALERTE | NOMBRE DE JOUEURS MAXIMAL ATTEINT", ephemeral=True)
            return

        try:
            # Ajoute le rôle directement et met à jour Firestore
            await user.add_roles(role, reason=f"Participation à la partie {event_name}")
            event_ref.update({'participants': firestore.ArrayUnion([user.id])})
            updated_event_data = event_ref.get().to_dict()
            
            await _update_event_embed(guild, updated_event_data, event_data['message_id'])
            await interaction.response.send_message(f"| INFO | BIENVENUE DANS LA PARTIE ! Votre rôle '{role.name}' a été activé. Dirigez-vous vers le salon vocal de la partie pour commencer.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("| ERREUR | PERMISSIONS INSUFFISANTES pour donner le rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"| ERREUR | INATTENDUE PENDANT L'INSCRIPTION : `{e}`", ephemeral=True)
            return

    elif action == 'leave':
        if user.id not in current_participants:
            await interaction.response.send_message("| ALERTE | VOUS NE PARTICIPEZ PAS À CETTE PARTIE", ephemeral=True)
            return

        try:
            # Retire le rôle et met à jour Firestore
            await user.remove_roles(role, reason=f"Quitte la partie {event_name}")
            event_ref.update({'participants': firestore.ArrayRemove([user.id])})
            updated_event_data = event_ref.get().to_dict()
            
            await _update_event_embed(guild, updated_event_data, event_data['message_id'])
            await interaction.response.send_message(f"| INFO | À LA PROCHAINE FOIS, {user.display_name.upper()}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("| ERREUR | PERMISSIONS INSUFFISANTES pour retirer le rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"| ERREUR | INATTENDUE PENDANT LE DÉSENGAGEMENT : `{e}`", ephemeral=True)
            return


@bot.event
async def on_interaction(interaction: discord.Interaction):
    """
    Écoute toutes les interactions, y compris les clics sur les boutons.
    """
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data['custom_id']
        if custom_id.startswith("join_event_"):
            event_firestore_id = custom_id.replace("join_event_", "")
            await handle_event_participation(interaction, event_firestore_id, 'join')
        elif custom_id.startswith("leave_event_"):
            event_firestore_id = custom_id.replace("leave_event_", "")
            await handle_event_participation(interaction, event_firestore_id, 'leave')
    
    # S'assure que les commandes sont toujours traitées
    await bot.process_commands(interaction)


@tasks.loop(minutes=1)
async def check_expired_events():
    """
    Tâche en arrière-plan pour vérifier et terminer les événements expirés.
    """
    print("Vérification des parties expirées...")
    events_ref = db.collection('events')
    now = datetime.now(timezone.utc) # Utilisez timezone.utc ici pour la cohérence
    for doc in events_ref.stream():
        event_data = doc.to_dict()
        event_end_time = event_data.get('end_time')
        
        if isinstance(event_end_time, datetime) and event_end_time.replace(tzinfo=timezone.utc) < now:
            print(f"Partie '{event_data.get('name', doc.id)}' expirée. Fin de la partie...")
            await _end_event(doc.id)


@bot.command(name='help', usage='poxel')
async def help_command(ctx, bot_name: str = None):
    """
    Affiche toutes les commandes disponibles du bot Poxel.
    """
    if bot_name and bot_name.lower() != 'poxel':
        await ctx.send("| ERREUR | BOT INCONNU", ephemeral=True)
        return

    embed = discord.Embed(
        title="| MANUEL DU JOUEUR |",
        description="Voici la liste des commandes disponibles pour Poxel :",
        color=discord.Color.from_rgb(0, 158, 255) # Bleu électrique
    )

    commands_info = {
        "create_event": {
            "description": "Crée une nouvelle partie avec un rôle temporaire et deux salons vocaux.",
            "usage": ("`!create_event @rôle #salon_textuel durée(ex: 2h) max_participants étiquette_participants #salon_attente #salon_de_jeu Nom de la partie`\n"
                      "Ex: `!create_event @Joueur #salon-jeu 1h30m 4 joueurs #salle-d-attente #salon-partie Partie de Donjons`")
        },
        "end_event": {
            "description": "Termine une partie en cours et retire les rôles aux participants.",
            "usage": "`!end_event Nom de la partie`\n"
                     "Ex: `!end_event Partie de Donjons`"
        },
        "move_participants": {
            "description": "Déplace tous les participants d'une partie vers le salon de jeu.",
            "usage": "`!move_participants Nom de la partie`\n"
                     "Ex: `!move_participants Partie de Donjons`"
        },
        "list_events": {
            "description": "Affiche toutes les parties en cours avec leurs détails.",
            "usage": "`!list_events`"
        },
        "intro": {
            "description": "Affiche la présentation de Poxel sur le serveur.",
            "usage": "`!intro`"
        },
        "help": {
            "description": "Affiche ce manuel du joueur.",
            "usage": "`!help poxel`"
        }
    }

    for command_name, info in commands_info.items():
        embed.add_field(
            name=f"**!{command_name}**",
            value=(
                f"> **Info :** {info['description']}\n"
                f"> **Syntaxe :** {info['usage']}\n"
            ),
            inline=False
        )
    
    embed.set_footer(text="| P.O.X.E.L | Bon jeu, waeky !", icon_url="https://images.emojiterra.com/google/noto-emoji/v2.034/512px/1f47d.png")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


# ==============================================================================
# === DÉMARRAGE DU BOT ET SERVEUR KEEP-ALIVE ===
# Exécute l'application Flask sur le thread principal et le bot Discord
# ainsi que la tâche de ping sur des threads séparés.
# ==============================================================================

if __name__ == "__main__":
    # Démarre la tâche d'auto-ping sur un thread séparé immédiatement.
    ping_thread = threading.Thread(target=ping_self)
    ping_thread.daemon = True
    ping_thread.start()

    # Démarre le bot Discord sur un thread séparé.
    discord_bot_thread = threading.Thread(target=run_discord_bot)
    discord_bot_thread.daemon = True
    discord_bot_thread.start()

    # Exécute l'application Flask sur le thread principal.
    # C'est cette exécution qui est détectée par Render pour maintenir le service actif.
    app.run(host='0.0.0.0', port=8080)
