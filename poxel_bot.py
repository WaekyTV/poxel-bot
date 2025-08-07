import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from datetime import datetime, timedelta
import asyncio
import os
import random
import re
from dotenv import load_dotenv

# Import des bibliothèques Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# --- Configuration Firebase ---
# Le fichier 'serviceAccountKey.json' doit être dans le même dossier que ce script.
try:
    # On initialise la connexion à Firebase en utilisant le fichier de clé.
    cred_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY_PATH', 'serviceAccountKey.json')
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialisé avec succès.")
except Exception as e:
    print(f"Erreur lors de l'initialisation de Firebase Admin SDK: {e}")
    print("Assure-toi que le chemin 'FIREBASE_SERVICE_ACCOUNT_KEY_PATH' est correct et que le fichier de clé est présent.")
    exit()

# Définir le préfixe de commande et les intents nécessaires
intents = discord.Intents.default()
intents.message_content = True  # Nécessaire pour lire les commandes
intents.guilds = True
intents.members = True          # Nécessaire pour gérer les rôles des membres
intents.reactions = True

# Initialiser le bot
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Fonctions Utilitaires ---

def parse_duration(duration_str: str) -> int:
    """
    Parse une chaîne de durée (ex: "2h", "30m") en secondes.
    """
    total_seconds = 0
    matches = re.findall(r'(\d+)([hms])', duration_str.lower())

    if not matches:
        raise ValueError("Format de durée invalide. Utilisez '2h', '30m' ou une combinaison.")

    for value, unit in matches:
        value = int(value)
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
    return total_seconds

NEON_BLUE = 0x009EFF

def create_retro_embed(title, description="", color=NEON_BLUE):
    """Crée un embed avec un style rétro."""
    embed = discord.Embed(
        title=f"👾 {title.upper()} 👾",
        description=description,
        color=color
    )
    embed.set_author(name="Poxel OS", icon_url="https://placehold.co/64x64/009eff/ffffff?text=P")
    embed.set_footer(text="Système d'événements Poxel - Mode Rétro 💾")
    return embed

# --- Classes de vues et de boutons pour l'interaction utilisateur ---

class EventButtons(View):
    def __init__(self, event_firestore_id):
        super().__init__(timeout=None)
        self.event_firestore_id = event_firestore_id
        
        # Ajout du bouton "Participer"
        join_button = Button(
            label="JOIN GAME", 
            style=discord.ButtonStyle.green, 
            emoji="🎮", 
            custom_id=f"join_event_{self.event_firestore_id}"
        )
        join_button.callback = self.handle_join
        self.add_item(join_button)

        # Ajout du bouton "Quitter"
        quit_button = Button(
            label="QUIT", 
            style=discord.ButtonStyle.red, 
            emoji="🚪", 
            custom_id=f"quit_event_{self.event_firestore_id}"
        )
        quit_button.callback = self.handle_quit
        self.add_item(quit_button)

    async def handle_join(self, interaction: discord.Interaction):
        await self.handle_participation(interaction, 'join')

    async def handle_quit(self, interaction: discord.Interaction):
        await self.handle_participation(interaction, 'quit')

    async def handle_participation(self, interaction: discord.Interaction, action: str):
        """Gère les clics sur les boutons 'Participer' et 'Quitter'."""
        user = interaction.user
        event_ref = db.collection('events').document(self.event_firestore_id)
        event_doc = event_ref.get()

        if not event_doc.exists:
            await interaction.response.send_message("Cet événement n'existe plus ou a été terminé.", ephemeral=True)
            return

        event_data = event_doc.to_dict()
        event_name = event_data.get('name', 'Nom inconnu')
        guild = interaction.guild
        role = guild.get_role(event_data['role_id'])

        if not role:
            await interaction.response.send_message("Le rôle associé à cet événement n'a pas été trouvé.", ephemeral=True)
            return

        current_participants_list = event_data.get('participants', [])
        max_participants = event_data.get('max_participants')
        participant_label = event_data.get('participant_label', 'participants')

        if action == 'join':
            if user.id in current_participants_list:
                await interaction.response.send_message("Vous participez déjà à cet événement.", ephemeral=True)
                return
            if max_participants and len(current_participants_list) >= max_participants:
                await interaction.response.send_message("Désolé, cet événement a atteint sa capacité maximale.", ephemeral=True)
                return

            try:
                await user.add_roles(role, reason=f"Participation à l'événement {event_name}")
                event_ref.update({'participants': firestore.ArrayUnion([user.id])})
                await interaction.response.send_message(f"Vous avez rejoint l'événement **'{event_name}'** !", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour vous donner ce rôle.", ephemeral=True)
                return
            except Exception as e:
                await interaction.response.send_message(f"Une erreur est survenue lors de votre inscription : `{e}`", ephemeral=True)
                return

        elif action == 'quit':
            if user.id not in current_participants_list:
                await interaction.response.send_message("Vous ne participez pas à cet événement.", ephemeral=True)
                return

            try:
                await user.remove_roles(role, reason=f"Quitte l'événement {event_name}")
                event_ref.update({'participants': firestore.ArrayRemove([user.id])})
                await interaction.response.send_message(f"Vous avez quitté l'événement **'{event_name}'**.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour vous retirer ce rôle.", ephemeral=True)
                return
            except Exception as e:
                await interaction.response.send_message(f"Une erreur est survenue lors de votre désinscription : `{e}`", ephemeral=True)
                return
        
        # Mettre à jour l'embed après l'interaction
        updated_event_doc = event_ref.get()
        if updated_event_doc.exists:
            updated_event_data = updated_event_doc.to_dict()
            updated_participants_count = len(updated_event_data.get('participants', []))
            
            try:
                original_message = interaction.message
                if original_message:
                    embed = original_message.embeds[0]
                    embed.set_field_at(
                        index=2 if event_data.get('is_contest') else 1, # Index du champ "Capacité" ou "Participants"
                        name="<:retro_user:123456789012345678> Participants",
                        value=f"**{updated_participants_count}** / **{max_participants}** {participant_label}",
                        inline=False
                    )
                    await original_message.edit(embed=embed)
            except Exception as e:
                print(f"Erreur lors de la mise à jour du message de l'événement : {e}")


# --- Tâche de gestion des événements ---

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

    # Gérer le tirage au sort si c'est un concours
    if event_data.get('is_contest', False):
        participants_list = list(event_data.get('participants', []))
        winner_count = event_data.get('winner_count', 1)
        
        if len(participants_list) >= winner_count:
            winners_id = random.sample(participants_list, winner_count)
            winners_mention = [f"<@{user_id}>" for user_id in winners_id]
            winners_str = ", ".join(winners_mention)

            winner_embed = create_retro_embed(f"🎉 RÉSULTATS DU CONCOURS : {event_name} 🎉")
            winner_embed.description = f"Félicitations aux gagnants ! Voici les heureux élus du tirage au sort :\n\n{winners_str}"
            
            if channel:
                await channel.send(f"@everyone CONCOURS TERMINÉ : **{event_name}**", embed=winner_embed)

            # Envoyer un message privé à chaque gagnant
            for winner_id in winners_id:
                winner_member = guild.get_member(winner_id)
                if winner_member:
                    try:
                        await winner_member.send(f"Félicitations ! 🎉 Vous avez été tiré au sort comme gagnant du concours **'{event_name}'** sur le serveur **{guild.name}** !")
                        print(f"Message privé envoyé à {winner_member.display_name} pour le concours '{event_name}'.")
                    except discord.Forbidden:
                        print(f"Impossible d'envoyer un message privé à {winner_member.display_name}. Les DMs sont désactivés.")
                    except Exception as e:
                        print(f"Erreur lors de l'envoi du message privé à {winner_member.display_name} : {e}")

        else:
            if channel:
                await channel.send(f"@everyone 🛑 Le concours '{event_name}' a été annulé car il n'y a pas assez de participants.")

    # Retirer les rôles des participants
    for user_id in event_data.get('participants', []):
        member = guild.get_member(user_id)
        if member and role:
            try:
                await member.remove_roles(role, reason=f"Fin de l'événement {event_name}")
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour retirer le rôle {role.name} à {member.display_name}")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle à {member.display_name}: {e}")
    
    # Mettre à jour le message de l'événement
    try:
        event_message = await channel.fetch_message(event_data['message_id'])
        if event_message:
            embed = event_message.embeds[0]
            embed.color = 0x8B0000  # Rouge foncé pour indiquer la fin
            embed.description = f"**Cet événement est terminé.**"
            # Retirer tous les champs sauf le nom
            embed.clear_fields()
            embed.add_field(name="<:retro_user:123456789012345678> Participants", value=f"{len(event_data.get('participants', []))} {event_data.get('participant_label', 'participants')}", inline=False)
            await event_message.edit(embed=embed, view=None) # view=None pour retirer les boutons
    except discord.NotFound:
        print(f"Message de l'événement {event_name} non trouvé sur Discord.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de l'événement : {e}")

    # Supprimer l'événement de Firestore
    event_ref.delete()
    print(f"Événement '{event_name}' (ID: {event_doc_id}) supprimé de Firestore.")


@tasks.loop(minutes=1)
async def check_expired_events():
    """Tâche en arrière-plan pour vérifier et terminer les événements expirés."""
    print("Vérification des événements expirés...")
    events_ref = db.collection('events')
    now = datetime.now()
    for doc in events_ref.stream():
        event_data = doc.to_dict()
        event_end_time = event_data.get('end_time')
        
        if event_end_time and isinstance(event_end_time, firestore.firestore.Timestamp):
            if event_end_time.astimezone() < now.astimezone():
                print(f"Événement '{event_data.get('name', doc.id)}' expiré. Fin de l'événement...")
                await _end_event(doc.id)


# --- Commandes du bot ---

async def _create_event_handler(ctx, role: discord.Role, channel: discord.TextChannel, duration: str, max_participants: int, participant_label: str, event_name: str, is_contest: bool, winner_count: int = 1, start_date: str = None, start_time: str = None):
    """Fonction interne pour gérer la création d'un événement ou d'un concours."""
    
    # Vérifier si l'événement existe déjà dans Firestore
    events_ref = db.collection('events')
    existing_event = events_ref.where('name', '==', event_name).get()
    if existing_event:
        await ctx.send(f"⚠️ Un événement nommé '{event_name}' existe déjà.", delete_after=60)
        await asyncio.sleep(60)
        await ctx.message.delete()
        return

    try:
        duration_seconds = parse_duration(duration)
        if duration_seconds <= 0:
            raise ValueError("La durée doit être positive.")

        now = datetime.now()
        
        if start_date and start_time:
            start_datetime = datetime.strptime(f"{start_date} {start_time}", "%d/%m/%Y %Hh%M")
        else:
            # Pour un événement "immédiat", l'heure de début est l'heure actuelle
            start_datetime = now
        
        end_datetime = start_datetime + timedelta(seconds=duration_seconds)

        if start_datetime < now:
            raise ValueError("La date et l'heure de début doivent être dans le futur.")

    except (ValueError, IndexError, TypeError) as e:
        await ctx.send(f"❌ Erreur de format des arguments. {e}\nUtilisation correcte dans `!helpoxel`", delete_after=60)
        await asyncio.sleep(60)
        await ctx.message.delete()
        return

    # Créer un message temporaire pour obtenir l'ID du message
    temp_message = await ctx.send("Création de l'événement en cours...")

    # Sauvegarder l'événement dans Firestore
    event_data_firestore = {
        'name': event_name,
        'role_id': role.id,
        'channel_id': channel.id,
        'end_time': end_datetime,
        'start_time': start_datetime,
        'max_participants': max_participants,
        'participant_label': participant_label,
        'participants': [],
        'message_id': temp_message.id,
        'guild_id': ctx.guild.id,
        'is_contest': is_contest,
        'winner_count': winner_count
    }
    doc_ref = db.collection('events').document()
    doc_ref.set(event_data_firestore)
    event_firestore_id = doc_ref.id

    # Création des boutons
    view = EventButtons(event_firestore_id)

    # Création de l'embed
    if is_contest:
        embed_title = f"🏆 NOUVEAU CONCOURS : {event_name}"
        announcement_text = f"@everyone Un nouveau concours a été créé : **{event_name}** ! Bonne chance à tous !"
    else:
        embed_title = f"NEW EVENT : {event_name}"
        announcement_text = f"@everyone Un nouvel événement a été créé : **{event_name}** !"
    
    embed = create_retro_embed(embed_title)
    embed.description = (
        f"**Rôle attribué :** {role.mention}\n"
        f"**Accès au salon :** {channel.mention}\n"
    )
    if is_contest:
        embed.add_field(name="<:retro_prize:123456789012345678> Gagnants", value=f"**{winner_count}** {participant_label}(s) seront tirés au sort !", inline=False)
    
    if start_date and start_time:
        embed.add_field(name="<:retro_time:123456789012345678> Durée", value=f"Commence le <t:{int(start_datetime.timestamp())}:f> (se termine <t:{int(end_datetime.timestamp())}:R>)", inline=False)
    else:
        embed.add_field(name="<:retro_time:123456789012345678> Durée", value=f"Commence maintenant (se termine <t:{int(end_datetime.timestamp())}:R>)", inline=False)
    
    embed.add_field(name="<:retro_user:123456789012345678> Participants", value=f"**0** / **{max_participants}** {participant_label}", inline=False)

    await temp_message.edit(content=announcement_text, embed=embed, view=view)
    await ctx.send(f"L'événement **'{event_name}'** a été créé avec succès.", delete_after=60)


@bot.command(name='create_event')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, role: discord.Role, channel: discord.TextChannel, duration: str, max_participants: int, participant_label: str, *, event_name: str):
    """Crée un événement immédiat. Ex: !create_event @Joueur #salon-jeu 1h30m 10 joueurs Partie de Donjons"""
    await _create_event_handler(ctx, role=role, channel=channel, duration=duration, max_participants=max_participants, participant_label=participant_label, event_name=event_name, is_contest=False)

@bot.command(name='create_event_plan')
@commands.has_permissions(manage_roles=True)
async def create_event_plan(ctx, role: discord.Role, channel: discord.TextChannel, duration: str, start_date: str, start_time: str, max_participants: int, participant_label: str, *, event_name: str):
    """Crée un événement planifié. Ex: !create_event_plan @Role #salon 2h 25/12/2025 21h00 10 joueurs Événement de Noël"""
    await _create_event_handler(ctx, role=role, channel=channel, duration=duration, start_date=start_date, start_time=start_time, max_participants=max_participants, participant_label=participant_label, event_name=event_name, is_contest=False)

@bot.command(name='create_contest')
@commands.has_permissions(manage_roles=True)
async def create_contest(ctx, role: discord.Role, channel: discord.TextChannel, winner_count: int, duration: str, max_participants: int, participant_label: str, *, event_name: str):
    """Crée un concours immédiat. Ex: !create_contest @Concours #salon-jeu 3 1h 10 participants Le Grand Tournoi"""
    if winner_count < 1:
        await ctx.send("Le nombre de gagnants doit être d'au moins 1.", delete_after=60)
        return
    await _create_event_handler(ctx, role=role, channel=channel, duration=duration, max_participants=max_participants, participant_label=participant_label, event_name=event_name, is_contest=True, winner_count=winner_count)

@bot.command(name='create_contest_plan')
@commands.has_permissions(manage_roles=True)
async def create_contest_plan(ctx, role: discord.Role, channel: discord.TextChannel, winner_count: int, duration: str, start_date: str, start_time: str, max_participants: int, participant_label: str, *, event_name: str):
    """Crée un concours planifié. Ex: !create_contest_plan @Concours #salon-jeu 3 2h 25/12/2025 21h00 10 participants Le Concours de Noël"""
    if winner_count < 1:
        await ctx.send("Le nombre de gagnants doit être d'au moins 1.", delete_after=60)
        return
    await _create_event_handler(ctx, role=role, channel=channel, duration=duration, start_date=start_date, start_time=start_time, max_participants=max_participants, participant_label=participant_label, event_name=event_name, is_contest=True, winner_count=winner_count)


@bot.command(name='end_event')
@commands.has_permissions(manage_roles=True)
async def end_event_command(ctx, *, event_name: str):
    """Termine manuellement un événement et retire les rôles. Ex: !end_event Ma Super Partie"""
    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()

    if not existing_event_docs:
        await ctx.send(f"L'événement **'{event_name}'** n'existe pas ou est déjà terminé.", delete_after=60)
        return

    event_doc_id = existing_event_docs[0].id
    
    await ctx.send(f"L'événement **'{event_name}'** est en cours de fermeture...", delete_after=60)
    await _end_event(event_doc_id)
    await ctx.send(f"L'événement **'{event_name}'** a été terminé manuellement.", delete_after=60)


@bot.command(name='list_events')
async def list_events(ctx):
    """Affiche tous les événements actifs avec leurs détails. Ex: !list_events"""
    events_ref = db.collection('events')
    active_events_docs = events_ref.stream()

    events_list = []
    for doc in active_events_docs:
        events_list.append(doc.to_dict())

    if not events_list:
        await ctx.send("Aucun événement actif pour le moment.", delete_after=60)
        return

    embed = create_retro_embed("Liste des événements actifs")

    for data in events_list:
        guild = bot.get_guild(data['guild_id'])
        role = guild.get_role(data['role_id']) if guild else None
        channel = guild.get_channel(data['channel_id']) if guild else None
        
        participants_count = len(data.get('participants', []))
        event_type = "Concours" if data.get('is_contest') else "Événement"
        
        embed.add_field(
            name=f"🎮 {data['name']}",
            value=(
                f"**Type :** {event_type}\n"
                f"**Rôle :** {role.mention if role else 'Introuvable'}\n"
                f"**Salon :** {channel.mention if channel else 'Introuvable'}\n"
                f"**Participants :** {participants_count} / {data['max_participants']} {data['participant_label']}\n"
                f"**Fin :** <t:{int(data['end_time'].timestamp())}:R>"
            ),
            inline=False
        )

    await ctx.send(embed=embed, delete_after=300)

# --- Événements du Bot ---

@bot.event
async def on_ready():
    """Se déclenche lorsque le bot est connecté à Discord."""
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Prêt à gérer les événements !')
    check_expired_events.start()

@bot.event
async def on_command_error(ctx, error):
    """Gère les erreurs de commande."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Il manque un argument pour cette commande. Utilisation correcte dans le manuel `!helpoxel`.", delete_after=60)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Argument invalide. Veuillez vérifier le format de vos arguments dans le manuel `!helpoxel`.", delete_after=60)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("Vous n'avez pas les permissions nécessaires pour exécuter cette commande (Gérer les rôles).", delete_after=60)
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Erreur de commande : {error}")
        await ctx.send(f"Une erreur inattendue s'est produite : `{error}`", delete_after=60)

@bot.command(name='helpoxel')
async def help_command(ctx):
    """Affiche le manuel d'aide de Poxel."""
    embed = create_retro_embed("🕹️ MANUEL DE POXEL")
    embed.description = "Je suis Poxel, votre assistant pour gérer les événements sur Discord. Voici comment m'utiliser :"

    commands_info = {
        "create_event": {
            "description": "Crée un événement immédiat.",
            "usage": "`!create_event @rôle #salon durée(ex: 1h30m) max_participants nom_étiquette nom_de_l'événement`"
        },
        "create_event_plan": {
            "description": "Crée un événement planifié.",
            "usage": "`!create_event_plan @rôle #salon durée(ex: 1h30m) date(JJ/MM/AAAA) heure(HHhMM) max_participants nom_étiquette nom_de_l'événement`"
        },
        "create_contest": {
            "description": "Crée un concours immédiat.",
            "usage": "`!create_contest @rôle #salon nb_gagnants durée(ex: 1h30m) max_participants nom_étiquette nom_de_l'événement`"
        },
        "create_contest_plan": {
            "description": "Crée un concours planifié.",
            "usage": "`!create_contest_plan @rôle #salon nb_gagnants durée(ex: 1h30m) date(JJ/MM/AAAA) heure(HHhMM) max_participants nom_étiquette nom_de_l'événement`"
        },
        "end_event": {
            "description": "Termine un événement en cours manuellement.",
            "usage": "`!end_event nom_de_l'événement`"
        },
        "list_events": {
            "description": "Affiche tous les événements actifs avec leurs détails.",
            "usage": "`!list_events`"
        }
    }

    for command_name, info in commands_info.items():
        embed.add_field(
            name=f"**!{command_name}**",
            value=f"{info['description']}\nUtilisation : {info['usage']}",
            inline=False
        )
    
    embed.set_footer(text="Poxel est là pour vous aider, waeky !")
    await ctx.send(embed=embed, delete_after=180)


# --- Démarrage du Bot ---
bot.run(BOT_TOKEN)
