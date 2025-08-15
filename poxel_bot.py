# poxel_bot.py
# Fichier principal du bot Discord pour gérer les événements, les concours et les rôles.
# Il utilise discord.py, Firebase pour la persistance des données et est conçu pour être hébergé sur Render.

import os
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput
import datetime
import pytz
import random
import firebase_admin
from firebase_admin import credentials, firestore

# --- Configuration du bot et de la base de données ---

# Le token du bot Discord. Il est recommandé de le charger depuis les variables d'environnement.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Chemin vers le fichier de clés de service Firebase.
# Chargez-le depuis une variable d'environnement ou directement (non recommandé en production).
FIREBASE_SERVICE_ACCOUNT = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

# Initialisation de Firebase Admin SDK.
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Connexion à Firebase réussie.")
except Exception as e:
    print(f"Erreur lors de l'initialisation de Firebase : {e}")
    # En cas d'erreur, le bot peut continuer à fonctionner sans DB,
    # mais les fonctionnalités persistantes ne seront pas disponibles.
    db = None


# --- Paramètres globaux du bot ---

# Couleurs pour les embeds
COLOR_PRIMARY = 0x6441a5  # Violet pour le style
COLOR_SECONDARY = 0x027afa  # Bleu pour les accents
# URL pour l'animation GIF 8-bit. Remplacez par votre propre lien si vous en avez un.
GIF_URL = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3ODc5bHJ5cWtkcWJ3bm92c2U5c3A4MHFoamJvMmE0eXQ5eG9wOTZ0MmZ0MCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/l0O2uL8yv4m51eX7a/giphy.gif"

# Définition des intents pour le bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Nécessaire pour la gestion des rôles et des membres
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Classes d'interface utilisateur (UI) ---

# Modal pour demander le pseudo en jeu lors de l'inscription
class PseudoModal(Modal, title='Inscription à l\'événement'):
    def __init__(self, event_name, event_view):
        super().__init__()
        self.event_name = event_name
        self.event_view = event_view
        self.pseudo_input = TextInput(
            label="Quel est votre pseudo en jeu ?",
            placeholder="Ex: Waeky#1234",
            min_length=1,
            max_length=32
        )
        self.add_item(self.pseudo_input)

    async def on_submit(self, interaction: discord.Interaction):
        pseudo = self.pseudo_input.value
        user_id = str(interaction.user.id)
        
        try:
            event_ref = db.collection("events").document(self.event_name)
            event_doc = await event_ref.get()
            
            if not event_doc.exists:
                await interaction.response.send_message(
                    "❌ Cet événement n'existe plus.", ephemeral=True
                )
                return

            event_data = event_doc.to_dict()
            participants = event_data.get('participants', {})
            max_participants = event_data.get('max_participants', 0)

            if len(participants) >= max_participants:
                await interaction.response.send_message(
                    "❌ Désolé, l'inscription est complète pour cet événement.", ephemeral=True
                )
                return

            participants[user_id] = pseudo
            await event_ref.update({'participants': participants})
            
            await interaction.response.send_message(
                f"✅ Vous êtes inscrit(e) à l'événement '{self.event_name}' avec le pseudo **{pseudo}** !",
                ephemeral=True
            )

            # Mettre à jour l'embed après l'inscription
            await self.event_view.update_embed(interaction, is_button_action=True)

        except Exception as e:
            print(f"Erreur lors de l'inscription via modal : {e}")
            await interaction.response.send_message(
                "❌ Une erreur est survenue lors de votre inscription.", ephemeral=True
            )

# Vue pour les boutons d'événements
class EventView(View):
    def __init__(self, event_name, message_id, is_started, is_planned=False):
        super().__init__(timeout=None)
        self.event_name = event_name
        self.message_id = message_id
        self.is_started = is_started
        self.is_planned = is_planned

        if not self.is_started:
            self.start_button = Button(label="S'INSCRIRE", style=discord.ButtonStyle.green, custom_id="start")
            self.quit_button = Button(label="SE DÉSISTER", style=discord.ButtonStyle.red, custom_id="quit")
            self.add_item(self.start_button)
            self.add_item(self.quit_button)
            self.start_button.callback = self.start_callback
            self.quit_button.callback = self.quit_callback
        else:
            self.start_button = None
            self.quit_button = None

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        await interaction.response.send_message(
            f"❌ Une erreur s'est produite : {error}", ephemeral=True
        )

    async def update_embed(self, interaction: discord.Interaction, is_button_action=False):
        event_ref = db.collection("events").document(self.event_name)
        event_doc = await event_ref.get()
        if not event_doc.exists:
            # L'événement a été supprimé, retire la vue
            if interaction.message:
                await interaction.message.delete()
            return

        event_data = event_doc.to_dict()
        embed = create_event_embed(event_data)
        
        # Gérer l'état du bouton "S'inscrire"
        participants_count = len(event_data.get('participants', {}))
        max_participants = event_data.get('max_participants', 0)
        
        if self.start_button and participants_count >= max_participants:
            self.start_button.disabled = True
            self.start_button.label = "INSCRIPTION CLOS"
        elif self.start_button and participants_count < max_participants:
            self.start_button.disabled = False
            self.start_button.label = "S'INSCRIRE"

        if is_button_action:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # Si pas une action de bouton, éditer le message directement
            message = await interaction.channel.fetch_message(self.message_id)
            if message:
                await message.edit(embed=embed, view=self)

    async def start_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PseudoModal(self.event_name, self))

    async def quit_callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        try:
            event_ref = db.collection("events").document(self.event_name)
            event_doc = await event_ref.get()
            
            if not event_doc.exists:
                await interaction.response.send_message(
                    "❌ Cet événement n'existe plus.", ephemeral=True
                )
                return

            event_data = event_doc.to_dict()
            participants = event_data.get('participants', {})
            
            if user_id not in participants:
                await interaction.response.send_message(
                    "❌ Vous n'êtes pas inscrit(e) à cet événement.", ephemeral=True
                )
                return

            del participants[user_id]
            await event_ref.update({'participants': participants})
            
            await interaction.response.send_message(
                f"✅ Vous vous êtes désisté(e) de l'événement '{self.event_name}'.",
                ephemeral=True
            )

            # Mettre à jour l'embed après le désistement
            await self.update_embed(interaction, is_button_action=True)

        except Exception as e:
            print(f"Erreur lors du désistement : {e}")
            await interaction.response.send_message(
                "❌ Une erreur est survenue lors de votre désistement.", ephemeral=True
            )

# --- Fonctions utilitaires ---

def create_event_embed(event_data, status_message=None):
    """Crée un embed pour un événement avec le style '8-bit néon'."""
    embed = discord.Embed(
        title=f"NEW EVENT: {event_data['name']}",
        color=COLOR_PRIMARY
    )
    embed.add_field(
        name="🎮 Nom de l'événement",
        value=f"```fix\n{event_data['name']}\n```",
        inline=False
    )
    
    start_time = event_data['start_time'].astimezone(pytz.timezone('Europe/Paris'))
    duration = event_data['duration_seconds']
    end_time = start_time + datetime.timedelta(seconds=duration)
    
    embed.add_field(
        name="🗓️ Date et heure",
        value=f"```ini\n[Début : {start_time.strftime('%d/%m/%Y %H:%M')}]\n[Fin : {end_time.strftime('%d/%m/%Y %H:%M')}]\n```",
        inline=False
    )
    
    # Affichage du temps restant
    now_utc = datetime.datetime.now(pytz.utc)
    if event_data['status'] == 'ongoing':
        time_left = end_time - now_utc
        if time_left.total_seconds() > 0:
            status_value = f"```yaml\nTemps restant : {format_timedelta(time_left)}\n```"
        else:
            status_value = "```ini\n[FINI IL Y A]\n```"
    elif event_data['status'] == 'pending':
        time_until_start = start_time - now_utc
        if time_until_start.total_seconds() > 0:
            status_value = f"```fix\nDébut dans : {format_timedelta(time_until_start)}\n```"
        else:
            status_value = "```ini\n[Lancement imminent]\n```"
    else: # status == 'finished' or 'cancelled'
        status_value = f"```diff\n- {status_message}\n```"

    embed.add_field(
        name="⏳ Statut de l'événement",
        value=status_value,
        inline=False
    )
    
    participants_count = len(event_data.get('participants', {}))
    max_participants = event_data.get('max_participants', 0)
    
    participants_list = ""
    if participants_count > 0:
        for user_id, pseudo in event_data['participants'].items():
            participants_list += f"- <@{user_id}> : `{pseudo}`\n"
    else:
        participants_list = "```ini\n[Aucun participant pour le moment]\n```"

    embed.add_field(
        name=f"👥 Participants ({participants_count}/{max_participants})",
        value=participants_list,
        inline=False
    )
    
    embed.set_footer(text=f"Salon d'attente : #{event_data['wait_channel_name']} | Rôle à attribuer : @{event_data['role_name']}")
    embed.set_thumbnail(url=GIF_URL)
    
    return embed

def create_help_embed(command=None):
    """Crée un embed pour l'aide."""
    embed = discord.Embed(
        title="MANUEL DE POXEL",
        description="Voici la liste des commandes disponibles.",
        color=COLOR_SECONDARY
    )
    embed.set_thumbnail(url=GIF_URL)
    
    if command:
        if command == "create_event":
            embed.title = "Aide pour !create_event"
            embed.description = (
                "Crée un événement immédiat.\n"
                "**Syntaxe :** `!create_event [heure de début] [durée] @[rôle] #[salon d'annonce] #[salon d'attente] [nombre max de participants] \"[nom]\"`\n"
                "**Exemple :** `!create_event 10:00 2h30m @Joueur-spécial #annonces #attente 10 \"Compétition de Pong\"`"
            )
        elif command == "create_event_plan":
            embed.title = "Aide pour !create_event_plan"
            embed.description = (
                "Planifie un événement pour une date future.\n"
                "**Syntaxe :** `!create_event_plan [date] [heure] [durée] @[rôle] #[salon d'annonce] #[salon d'attente] [nombre max de participants] \"[nom]\"`\n"
                "**Exemple :** `!create_event_plan 25/12/2024 18:00 3h @Niveau2 #general #salon-vocal 20 \"Tournoi de Noël\"`"
            )
        elif command == "end_event":
            embed.title = "Aide pour !end_event"
            embed.description = (
                "Met fin à un événement manuellement.\n"
                "**Syntaxe :** `!end_event \"[nom de l'événement]\"`\n"
                "**Exemple :** `!end_event \"Tournoi de Noël\"`"
            )
        elif command == "tirage":
            embed.title = "Aide pour !tirage"
            embed.description = (
                "Effectue un tirage au sort parmi les participants d'un événement.\n"
                "**Syntaxe :** `!tirage \"[nom de l'événement]\"`\n"
                "**Exemple :** `!tirage \"Tournoi de Noël\"`"
            )
        elif command == "concours":
            embed.title = "Aide pour !concours"
            embed.description = (
                "Crée un concours.\n"
                "**Syntaxe :** `!concours \"[nom du concours]\" [date de fin]`\n"
                "**Exemple :** `!concours \"Concours de Fan-Art\" 25/12/2024`"
            )
        elif command == "helpoxel":
            embed.title = "Aide pour !helpoxel"
            embed.description = (
                "Affiche l'aide pour les commandes du bot.\n"
                "**Syntaxe :** `!helpoxel [commande]`\n"
                "**Exemple :** `!helpoxel create_event`"
            )
        else:
            embed.description = "Commande non reconnue. Utilisez `!helpoxel` pour voir la liste des commandes."

    else:
        embed.add_field(name="!create_event", value="Crée un événement immédiat.", inline=False)
        embed.add_field(name="!create_event_plan", value="Planifie un événement futur.", inline=False)
        embed.add_field(name="!end_event", value="Termine un événement manuellement.", inline=False)
        embed.add_field(name="!tirage", value="Effectue un tirage au sort.", inline=False)
        embed.add_field(name="!concours", value="Crée un concours.", inline=False)
        embed.add_field(name="!helpoxel", value="Affiche l'aide pour les commandes.", inline=False)
    
    return embed

def format_timedelta(td):
    """Formate un timedelta en jours, heures, minutes et secondes."""
    if td.total_seconds() < 0:
        td = -td
    
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}j")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
        
    return " ".join(parts)


# --- Tâches en arrière-plan pour la gestion des événements ---

@tasks.loop(minutes=1)
async def event_manager():
    if db is None:
        print("La base de données n'est pas connectée. Le gestionnaire d'événements est désactivé.")
        return

    now_utc = datetime.datetime.now(pytz.utc)
    
    # Gérer les événements en attente
    events_ref = db.collection("events")
    pending_events = events_ref.where('status', '==', 'pending').stream()
    
    async for event_doc in pending_events:
        event_data = event_doc.to_dict()
        event_name = event_doc.id
        start_time = event_data['start_time'].astimezone(pytz.utc)
        
        # 30 minutes avant le début
        if start_time - now_utc < datetime.timedelta(minutes=30) and 'remind_30min' not in event_data:
            try:
                announce_channel = bot.get_channel(event_data['announce_channel_id'])
                if announce_channel:
                    await announce_channel.send(
                        f"@everyone ⏰ L'événement **'{event_name}'** commence dans moins de 30 minutes ! "
                        "Il est temps de vous inscrire !"
                    )
                await event_doc.reference.update({'remind_30min': True})
            except Exception as e:
                print(f"Erreur lors de l'envoi du rappel de 30 minutes pour {event_name}: {e}")

        # Début de l'événement
        if now_utc >= start_time:
            try:
                guild = bot.get_guild(event_data['guild_id'])
                if not guild:
                    continue
                
                participants = event_data.get('participants', {})
                max_participants = event_data.get('max_participants', 0)
                
                # Annulation si pas assez de participants
                if len(participants) < 1 and max_participants > 0: # on peut définir un minimum si besoin, ici on met 1 pour l'exemple
                    announce_channel = bot.get_channel(event_data['announce_channel_id'])
                    if announce_channel:
                        await announce_channel.send(
                            f"@everyone ❌ L'événement **'{event_name}'** a été annulé car le nombre minimum "
                            "de participants n'a pas été atteint. 😔"
                        )
                    await event_doc.reference.update({'status': 'cancelled'})
                    # Supprimer le message embed de l'événement
                    try:
                        message = await announce_channel.fetch_message(event_data['message_id'])
                        await message.delete()
                    except discord.NotFound:
                        pass
                    continue
                
                # Attribution des rôles et envoi des DMs
                role_id = event_data['role_id']
                event_role = guild.get_role(role_id)
                if event_role:
                    for user_id_str in participants.keys():
                        user_id = int(user_id_str)
                        member = guild.get_member(user_id)
                        if member and member.bot is False:
                            try:
                                await member.add_roles(event_role)
                                await member.send(
                                    f"🎉 Félicitations, vous participez à l'événement **'{event_name}'** ! "
                                    "Le rôle temporaire vous a été attribué et vous pouvez rejoindre le salon d'attente."
                                )
                            except Exception as e:
                                print(f"Erreur d'attribution de rôle ou d'envoi de DM pour {member.name}: {e}")
                
                # Annonce du début
                announce_channel = bot.get_channel(event_data['announce_channel_id'])
                if announce_channel:
                    await announce_channel.send(
                        f"@everyone 🚀 L'événement **'{event_name}'** a commencé ! "
                        "Le rôle temporaire a été attribué aux participants. Amusez-vous bien !"
                    )
                
                # Mettre à jour l'état de l'événement dans la DB
                await event_doc.reference.update({'status': 'ongoing'})
                
                # Retirer les boutons de l'embed
                try:
                    message = await announce_channel.fetch_message(event_data['message_id'])
                    if message:
                        await message.edit(view=None)
                except discord.NotFound:
                    pass

            except Exception as e:
                print(f"Erreur lors du début de l'événement {event_name}: {e}")
    
    # Gérer les événements en cours
    ongoing_events = events_ref.where('status', '==', 'ongoing').stream()
    
    async for event_doc in ongoing_events:
        event_data = event_doc.to_dict()
        event_name = event_doc.id
        start_time = event_data['start_time'].astimezone(pytz.utc)
        duration_seconds = event_data['duration_seconds']
        end_time = start_time + datetime.timedelta(seconds=duration_seconds)
        
        # Fin de l'événement
        if now_utc >= end_time:
            try:
                guild = bot.get_guild(event_data['guild_id'])
                if not guild:
                    continue
                
                # Retirer les rôles
                role_id = event_data['role_id']
                event_role = guild.get_role(role_id)
                if event_role:
                    for user_id_str in event_data['participants'].keys():
                        user_id = int(user_id_str)
                        member = guild.get_member(user_id)
                        if member:
                            try:
                                await member.remove_roles(event_role)
                            except Exception as e:
                                print(f"Erreur de retrait de rôle pour {member.name}: {e}")
                
                # Annonce de la fin
                announce_channel = bot.get_channel(event_data['announce_channel_id'])
                if announce_channel:
                    await announce_channel.send(
                        f"@everyone ✅ L'événement **'{event_name}'** est terminé ! "
                        "Merci à tous les participants. Le rôle a été retiré."
                    )
                
                # Mettre à jour l'état de l'événement dans la DB
                await event_doc.reference.update({'status': 'finished'})

                # Supprimer le message embed de l'événement
                try:
                    message = await announce_channel.fetch_message(event_data['message_id'])
                    await message.delete()
                except discord.NotFound:
                    pass

            except Exception as e:
                print(f"Erreur lors de la fin de l'événement {event_name}: {e}")
        
        # Mettre à jour l'embed en temps réel
        else:
            try:
                announce_channel = bot.get_channel(event_data['announce_channel_id'])
                if announce_channel:
                    message = await announce_channel.fetch_message(event_data['message_id'])
                    if message:
                        embed = create_event_embed(event_data)
                        await message.edit(embed=embed)
            except discord.NotFound:
                # Le message a été supprimé manuellement, mettre fin à l'événement
                await event_doc.reference.update({'status': 'finished'})
            except Exception as e:
                print(f"Erreur de mise à jour de l'embed pour {event_name}: {e}")


# --- Événements du bot ---

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user.name} (ID: {bot.user.id})')
    print('---')
    if not event_manager.is_running():
        event_manager.start()

# --- Commandes du bot ---

@bot.command(name='create_event')
@commands.has_permissions(administrator=True)
async def create_event(
    ctx, 
    start_time_str: str, 
    duration_str: str, 
    role: discord.Role, 
    announce_channel: discord.TextChannel, 
    wait_channel: discord.TextChannel,
    max_participants: int,
    *,
    event_name: str
):
    """Crée un événement immédiat."""
    await ctx.message.delete(delay=120)
    
    # 1. Parsing de l'heure et de la durée
    try:
        start_time_naive = datetime.datetime.strptime(start_time_str, '%H:%M')
        today = datetime.date.today()
        start_time = datetime.datetime.combine(today, start_time_naive.time())
        # Convertir en UTC
        start_time = pytz.timezone('Europe/Paris').localize(start_time).astimezone(pytz.utc)

        duration_seconds = 0
        if 'h' in duration_str:
            hours_str = duration_str.split('h')[0]
            duration_seconds += int(hours_str) * 3600
            duration_str = duration_str.split('h')[1]
        if 'm' in duration_str:
            minutes_str = duration_str.split('m')[0]
            duration_seconds += int(minutes_str) * 60
            duration_str = duration_str.split('m')[1]
        if 's' in duration_str:
            seconds_str = duration_str.split('s')[0]
            duration_seconds += int(seconds_str)
            
        if duration_seconds == 0:
            await ctx.send("❌ Durée invalide. Utilisez 'h', 'm', 's'.", delete_after=120)
            return

    except Exception:
        await ctx.send("❌ Format d'heure ou de durée invalide. Utilisez 'HH:MM' et 'h/m/s'.", delete_after=120)
        return
    
    # 2. Vérification de l'heure de début
    now_utc = datetime.datetime.now(pytz.utc)
    if start_time < now_utc:
        await ctx.send("❌ L'heure de début ne peut pas être dans le passé.", delete_after=120)
        return
        
    # 3. Vérification de l'existence de l'événement
    if db:
        event_doc = db.collection("events").document(event_name).get()
        if event_doc.exists:
            await ctx.send(f"❌ Un événement avec le nom **'{event_name}'** existe déjà.", delete_after=120)
            return

    # 4. Création de l'événement et de l'embed
    event_data = {
        'name': event_name,
        'start_time': start_time,
        'duration_seconds': duration_seconds,
        'role_id': role.id,
        'role_name': role.name,
        'announce_channel_id': announce_channel.id,
        'announce_channel_name': announce_channel.name,
        'wait_channel_id': wait_channel.id,
        'wait_channel_name': wait_channel.name,
        'max_participants': max_participants,
        'participants': {},
        'status': 'pending',
        'guild_id': ctx.guild.id
    }
    
    embed = create_event_embed(event_data)
    
    message = await announce_channel.send(
        content=f"@everyone Un nouvel événement a été créé par {ctx.author.mention} !",
        embed=embed
    )
    
    # 5. Sauvegarde dans la base de données
    if db:
        event_data['message_id'] = message.id
        db.collection("events").document(event_name).set(event_data)
    
    # 6. Ajout des boutons à l'embed
    view = EventView(event_name, message.id, False)
    await message.edit(view=view)
    await ctx.send(f"✅ Événement **'{event_name}'** créé avec succès !", delete_after=120)

@bot.command(name='create_event_plan')
@commands.has_permissions(administrator=True)
async def create_event_plan(
    ctx, 
    date_str: str,
    time_str: str,
    duration_str: str, 
    role: discord.Role, 
    announce_channel: discord.TextChannel, 
    wait_channel: discord.TextChannel,
    max_participants: int,
    *,
    event_name: str
):
    """Planifie un événement pour une date future."""
    await ctx.message.delete(delay=120)
    
    # Parsing de la date, de l'heure et de la durée
    try:
        start_time_naive = datetime.datetime.strptime(f"{date_str} {time_str}", '%d/%m/%Y %H:%M')
        start_time = pytz.timezone('Europe/Paris').localize(start_time_naive).astimezone(pytz.utc)

        duration_seconds = 0
        if 'h' in duration_str:
            hours_str = duration_str.split('h')[0]
            duration_seconds += int(hours_str) * 3600
            duration_str = duration_str.split('h')[1]
        if 'm' in duration_str:
            minutes_str = duration_str.split('m')[0]
            duration_seconds += int(minutes_str) * 60
            duration_str = duration_str.split('m')[1]
        if 's' in duration_str:
            seconds_str = duration_str.split('s')[0]
            duration_seconds += int(seconds_str)

        if duration_seconds == 0:
            await ctx.send("❌ Durée invalide. Utilisez 'h', 'm', 's'.", delete_after=120)
            return

    except Exception:
        await ctx.send("❌ Format de date/heure/durée invalide. Utilisez 'JJ/MM/AAAA HH:MM' et 'h/m/s'.", delete_after=120)
        return
    
    # 2. Vérification de l'heure de début
    now_utc = datetime.datetime.now(pytz.utc)
    if start_time < now_utc:
        await ctx.send("❌ La date de l'événement ne peut pas être dans le passé.", delete_after=120)
        return
        
    # 3. Vérification de l'existence de l'événement
    if db:
        event_doc = db.collection("events").document(event_name).get()
        if event_doc.exists:
            await ctx.send(f"❌ Un événement avec le nom **'{event_name}'** existe déjà.", delete_after=120)
            return

    # 4. Création de l'événement et de l'embed
    event_data = {
        'name': event_name,
        'start_time': start_time,
        'duration_seconds': duration_seconds,
        'role_id': role.id,
        'role_name': role.name,
        'announce_channel_id': announce_channel.id,
        'announce_channel_name': announce_channel.name,
        'wait_channel_id': wait_channel.id,
        'wait_channel_name': wait_channel.name,
        'max_participants': max_participants,
        'participants': {},
        'status': 'pending',
        'guild_id': ctx.guild.id
    }
    
    embed = create_event_embed(event_data)
    
    message = await announce_channel.send(
        content=f"@everyone Un nouvel événement planifié a été créé par {ctx.author.mention} !",
        embed=embed
    )
    
    # 5. Sauvegarde dans la base de données
    if db:
        event_data['message_id'] = message.id
        db.collection("events").document(event_name).set(event_data)
    
    # 6. Ajout des boutons à l'embed
    view = EventView(event_name, message.id, False)
    await message.edit(view=view)
    await ctx.send(f"✅ Événement planifié **'{event_name}'** créé avec succès !", delete_after=120)

@bot.command(name='end_event')
@commands.has_permissions(administrator=True)
async def end_event(ctx, *, event_name: str):
    """Met fin à un événement manuellement."""
    await ctx.message.delete(delay=120)
    if not db:
        await ctx.send("❌ La base de données n'est pas connectée. Impossible de terminer l'événement.", delete_after=120)
        return
        
    event_ref = db.collection("events").document(event_name)
    event_doc = await event_ref.get()

    if not event_doc.exists:
        await ctx.send(f"❌ L'événement **'{event_name}'** n'existe pas.", delete_after=120)
        return

    event_data = event_doc.to_dict()
    
    if event_data['status'] in ['finished', 'cancelled']:
        await ctx.send(f"❌ L'événement **'{event_name}'** est déjà terminé ou annulé.", delete_after=120)
        return

    try:
        guild = bot.get_guild(event_data['guild_id'])
        if guild:
            role_id = event_data['role_id']
            event_role = guild.get_role(role_id)
            if event_role:
                for user_id_str in event_data['participants'].keys():
                    user_id = int(user_id_str)
                    member = guild.get_member(user_id)
                    if member:
                        try:
                            await member.remove_roles(event_role)
                        except Exception as e:
                            print(f"Erreur de retrait de rôle for {member.name}: {e}")
        
        announce_channel = bot.get_channel(event_data['announce_channel_id'])
        if announce_channel:
            await announce_channel.send(
                f"@everyone ✅ L'événement **'{event_name}'** a été terminé manuellement par {ctx.author.mention}."
            )
            # Supprimer le message embed de l'événement
            try:
                message = await announce_channel.fetch_message(event_data['message_id'])
                await message.delete()
            except discord.NotFound:
                pass

        await event_ref.update({'status': 'finished', 'end_time': datetime.datetime.now(pytz.utc)})
        await ctx.send(f"✅ L'événement **'{event_name}'** a été terminé avec succès.", delete_after=120)
    except Exception as e:
        await ctx.send(f"❌ Une erreur est survenue lors de la clôture de l'événement: {e}", delete_after=120)


@bot.command(name='tirage')
@commands.has_permissions(administrator=True)
async def tirage(ctx, *, event_name: str):
    """Effectue un tirage au sort parmi les participants d'un événement."""
    await ctx.message.delete(delay=120)
    if not db:
        await ctx.send("❌ La base de données n'est pas connectée. Impossible de faire le tirage.", delete_after=120)
        return
        
    event_ref = db.collection("events").document(event_name)
    event_doc = await event_ref.get()

    if not event_doc.exists:
        await ctx.send(f"❌ L'événement **'{event_name}'** n'existe pas.", delete_after=120)
        return

    event_data = event_doc.to_dict()
    participants = list(event_data.get('participants', {}).keys())

    if not participants:
        await ctx.send(f"❌ Aucun participant pour l'événement **'{event_name}'**.", delete_after=120)
        return

    winner_id = random.choice(participants)
    winner_pseudo = event_data['participants'][winner_id]
    
    await ctx.send(
        f"🎉 Le tirage au sort pour l'événement **'{event_name}'** est terminé ! "
        f"Le grand gagnant est <@{winner_id}> avec le pseudo **{winner_pseudo}** ! Félicitations !"
    )

@bot.command(name='helpoxel')
async def helpoxel(ctx, command_name: str = None):
    """Affiche un embed avec la liste des commandes ou l'aide détaillée."""
    await ctx.message.delete(delay=120)
    
    embed = create_help_embed(command_name)
    await ctx.send(embed=embed, delete_after=120)

@bot.command(name='test_admin')
@commands.has_permissions(administrator=True)
async def test_admin(ctx):
    """Commande pour tester les droits d'administration."""
    await ctx.message.delete(delay=120)
    await ctx.send("✅ Vous avez les droits d'administration sur le bot.", delete_after=120)


# --- Gestion des erreurs de commande ---

@bot.event
async def on_command_error(ctx, error):
    # Ignorer les commandes qui n'existent pas
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Commande non reconnue. Utilisez `!helpoxel` pour voir la liste des commandes.", delete_after=120)
        return
        
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ **{ctx.author.mention}**, vous n'avez pas les permissions nécessaires pour exécuter cette commande.", delete_after=120)
        await ctx.message.delete(delay=120)
        return
        
    if isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Commande mal écrite ou arguments invalides. Utilisez `!helpoxel {ctx.command.name}` pour l'aide.", delete_after=120)
        await ctx.message.delete(delay=120)
        return
        
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant. Utilisez `!helpoxel {ctx.command.name}` pour l'aide.", delete_after=120)
        await ctx.message.delete(delay=120)
        return
        
    # Gérer les autres erreurs
    print(f"Erreur de commande : {error}")
    await ctx.send(f"❌ Une erreur inattendue est survenue : {error}", delete_after=120)
    await ctx.message.delete(delay=120)


# --- Lancement du bot ---

if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("Erreur: Le token Discord n'a pas été trouvé. Assurez-vous d'avoir défini la variable d'environnement DISCORD_TOKEN.")
    else:
        bot.run(DISCORD_TOKEN)

