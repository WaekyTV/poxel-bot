from flask import Flask
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import datetime
import asyncio
import os
import json
import pytz
import random
import threading
from firebase_admin import credentials, firestore, initialize_app

# --- Configuration du bot
# Assurez-vous d'avoir les intents nécessaires pour les messages,
# les membres, et la gestion des événements.
intents = discord.Intents.all()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.reactions = True

# Préfixe de la commande pour le bot
BOT_PREFIX = "!"

# Définition des couleurs pour l'embed, comme demandé
NEON_PURPLE = 0x6441a5
NEON_BLUE = 0x027afa
NEON_ORANGE = 0xffa500
NEON_GREEN = 0x39ff14
NEON_RED = 0xff073a

# Définition du fuseau horaire de l'utilisateur (France métropolitaine)
USER_TIMEZONE = pytz.timezone('Europe/Paris')
# Définition du fuseau horaire du serveur (UTC par convention)
SERVER_TIMEZONE = pytz.utc

# --- DATABASE (FIREBASE) ---
# En production, il faudrait utiliser le SDK Firebase pour une base de données réelle.
# Ici, nous utilisons un mockup pour simuler la base de données.
# Vous devrez utiliser vos propres identifiants Firebase en production.
try:
    # Pour le bon fonctionnement sur le serveur Render
    cred_json = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
    cred = credentials.Certificate(cred_json)
    initialize_app(cred)
    db = firestore.client()
    print("Connexion à Firebase réussie.")
except Exception as e:
    print(f"Erreur de connexion à Firebase : {e}. Utilisation d'une base de données locale (events.json) en tant que maquette.")
    # On revient à la base de données locale si Firebase échoue
    db = None
    DATABASE_FILE = 'events.json'
    def load_events():
        if os.path.exists(DATABASE_FILE):
            with open(DATABASE_FILE, 'r') as f:
                return json.load(f)
        return {"events": {}, "contests": {}}

    def save_events(data):
        with open(DATABASE_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    local_db = load_events()

def get_db_data():
    """Récupère les données depuis Firebase ou la base de données locale."""
    if db:
        events_doc = db.collection('data').document('events').get()
        contests_doc = db.collection('data').document('contests').get()
        events_data = events_doc.to_dict() if events_doc.exists else {}
        contests_data = contests_doc.to_dict() if contests_doc.exists else {}
        return {"events": events_data, "contests": contests_data}
    else:
        return local_db

def save_db_data(data):
    """Sauvegarde les données vers Firebase ou la base de données locale."""
    if db:
        db.collection('data').document('events').set(data['events'])
        db.collection('data').document('contests').set(data['contests'])
    else:
        save_events(data)

# --- FLASK SERVER POUR LA PERSISTANCE (RENDER) ---
# Ceci est nécessaire pour que le bot reste en ligne sur des services comme Render.
app = Flask(__name__)

@app.route('/')
def home():
    return "Poxel Bot is running!"

def run_flask():
    """Démarre le serveur Flask."""
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# --- CLASSES DE BOUTONS ET DE VUES ---

class EventButtonsView(View):
    """
    Vue contenant les boutons d'inscription et de désinscription pour un événement.
    Les boutons sont gérés de manière dynamique.
    """
    def __init__(self, bot, event_name, timeout=None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.event_name = event_name
        self.max_participants = 0
        self.current_participants = 0
        self.update_state()

    def update_state(self):
        """Met à jour l'état de la vue en fonction des données de l'événement."""
        data = get_db_data()
        event_data = data['events'].get(self.event_name)
        if event_data:
            self.max_participants = event_data['max_participants']
            self.current_participants = len(event_data['participants'])

    def update_buttons(self):
        """Met à jour l'état visuel des boutons."""
        self.clear_items()
        self.update_state()
        
        # Bouton START (INSCRIPTION)
        start_button = Button(
            label="START",
            style=discord.ButtonStyle.success,
            emoji="✅"
        )
        if self.current_participants >= self.max_participants:
            start_button.label = "INSCRIPTION CLOS"
            start_button.disabled = True
            
        start_button.callback = self.on_start_click
        self.add_item(start_button)
        
        # Bouton QUIT (DESINSCRIPTION)
        quit_button = Button(
            label="QUIT",
            style=discord.ButtonStyle.danger,
            emoji="❌"
        )
        quit_button.callback = self.on_quit_click
        self.add_item(quit_button)
        
    async def on_start_click(self, interaction: discord.Interaction):
        """Gère l'inscription d'un utilisateur."""
        data = get_db_data()
        event_data = data['events'].get(self.event_name)
        if not event_data:
            await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id in [p['id'] for p in event_data['participants']]:
            await interaction.response.send_message("Vous êtes déjà inscrit à cet événement !", ephemeral=True)
            return

        if len(event_data['participants']) >= event_data['max_participants']:
            await interaction.response.send_message("Désolé, les inscriptions sont complètes pour cet événement.", ephemeral=True)
            return

        # Ouverture de la modale pour le pseudo
        modal = ParticipantModal(self, self.event_name)
        await interaction.response.send_modal(modal)

    async def on_quit_click(self, interaction: discord.Interaction):
        """Gère la désinscription d'un utilisateur."""
        data = get_db_data()
        event_data = data['events'].get(self.event_name)
        if not event_data:
            await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            return
            
        user_id = interaction.user.id
        if user_id not in [p['id'] for p in event_data['participants']]:
            await interaction.response.send_message("Vous n'êtes pas inscrit à cet événement.", ephemeral=True)
            return
            
        # Suppression du participant
        event_data['participants'] = [p for p in event_data['participants'] if p['id'] != user_id]
        save_db_data(data)
        
        # Mise à jour de l'embed
        await update_event_embed(self.bot, self.event_name)
        await interaction.response.send_message("Vous vous êtes désinscrit de l'événement.", ephemeral=True)

class ParticipantModal(discord.ui.Modal, title="Pseudo pour le jeu"):
    """
    Fenêtre modale pour que l'utilisateur entre son pseudo de jeu.
    """
    game_pseudo = discord.ui.TextInput(
        label="Votre pseudo pour le jeu",
        placeholder="Entrez votre pseudo ici...",
        required=True
    )

    def __init__(self, view, event_name):
        super().__init__()
        self.view = view
        self.event_name = event_name

    async def on_submit(self, interaction: discord.Interaction):
        """Ajoute l'utilisateur à la liste des participants avec son pseudo."""
        data = get_db_data()
        event_data = data['events'].get(self.event_name)
        if not event_data:
            await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            return

        user = interaction.user
        game_pseudo = self.game_pseudo.value
        
        # Enregistrement du participant
        event_data['participants'].append({
            "id": user.id,
            "name": user.display_name,
            "pseudo": game_pseudo
        })
        save_db_data(data)
        
        # Mise à jour de l'embed
        await update_event_embed(self.view.bot, self.event_name)
        await interaction.response.send_message(f"Vous avez été inscrit à l'événement `{self.event_name}` avec le pseudo `{game_pseudo}`.", ephemeral=True)

# --- FONCTIONS UTILES ---

def format_time_left(time_str):
    """
    Formate le temps restant en jours, heures, minutes et secondes.
    """
    time_utc = datetime.datetime.fromisoformat(time_str).replace(tzinfo=SERVER_TIMEZONE)
    now_utc = datetime.datetime.now(SERVER_TIMEZONE)
    delta = time_utc - now_utc
    
    if delta.total_seconds() < 0:
        return "TERMINÉ"

    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days} jour(s)")
    if hours > 0:
        parts.append(f"{hours} heure(s)")
    if minutes > 0:
        parts.append(f"{minutes} minute(s)")
    if seconds > 0:
        parts.append(f"{seconds} seconde(s)")
    
    return ", ".join(parts) or "Moins d'une seconde"

async def update_event_embed(bot, event_name):
    """
    Met à jour l'embed de l'événement avec les dernières informations (temps, participants).
    """
    data = get_db_data()
    event = data['events'].get(event_name)
    if not event:
        return

    announcement_channel_id = event['announcement_channel_id']
    message_id = event['message_id']
    
    try:
        channel = bot.get_channel(announcement_channel_id)
        if not channel:
            return
        
        message = await channel.fetch_message(message_id)
        
        # Création de l'embed mis à jour
        embed = discord.Embed(
            title=f"NEW EVENT: {event_name}",
            description="""
            Rejoignez-nous pour un événement spécial !
            """,
            color=NEON_PURPLE
        )
        embed.add_field(name="POINT DE RALLIEMENT", value=f"<#{event['waiting_channel_id']}>", inline=True)
        embed.add_field(name="RÔLE ATTRIBUÉ", value=f"<@&{event['role_id']}>", inline=True)
        
        # Gestion du temps et des inscriptions
        if not event.get('is_started'):
            embed.add_field(name="DÉBUT DANS", value=format_time_left(event['start_time']), inline=False)
            view = EventButtonsView(bot, event_name)
        else:
            embed.add_field(name="TEMPS RESTANT", value=format_time_left(event['end_time']), inline=False)
            embed.description = "L'événement est en cours. Les inscriptions sont closes."
            view = None

        # Liste des participants
        participants_list = "\n".join([f"- **{p['name']}** ({p['pseudo']})" for p in event['participants']])
        if not participants_list:
            participants_list = "Aucun participant pour le moment."
            
        embed.add_field(name=f"PARTICIPANTS ({len(event['participants'])}/{event['max_participants']})", value=participants_list, inline=False)
        embed.set_footer(text="Style 8-bit futuriste, néon")
        embed.set_image(url="https://i.imgur.com/uCgE04g.gif") 
        
        await message.edit(embed=embed, view=view)
        
    except discord.NotFound:
        del data['events'][event_name]
        save_db_data(data)
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'embed pour {event_name}: {e}")

# --- BOT Poxel ---
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

@bot.event
async def on_ready():
    """
    Événement qui se déclenche lorsque le bot est prêt et connecté à Discord.
    """
    print(f"Connecté en tant que {bot.user.name} ({bot.user.id})")
    print("------")
    # Lancement des tâches planifiées de vérification
    check_events.start()
    check_contests.start()
    
# --- GESTION DES COMMANDES ---

@bot.command(name="create_event")
@commands.has_permissions(administrator=True)
async def create_event(ctx, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, min_participants: int, *, event_name: str):
    """
    Crée un événement pour le jour même.
    Exemple: !create_event 21h14 10min @role #salon #annonce 1 "soirée gaming"
    """
    await ctx.message.delete(delay=120)
    data = get_db_data()
    if event_name in data['events']:
        await ctx.send(f"Un événement nommé `{event_name}` existe déjà. Veuillez en terminer l'ancien ou choisir un autre nom.", delete_after=120)
        return

    try:
        now = datetime.datetime.now()
        start_hour, start_minute = map(int, start_time_str.split('h'))
        start_time_naive = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        
        start_time_localized = USER_TIMEZONE.localize(start_time_naive)
        start_time_utc = start_time_localized.astimezone(SERVER_TIMEZONE)

        duration_unit = duration_str[-3:].lower()
        duration_value = int(duration_str[:-3])

        if duration_unit == 'min':
            duration = datetime.timedelta(minutes=duration_value)
        elif duration_unit == 'h':
            duration = datetime.timedelta(hours=duration_value)
        else:
            await ctx.send("Le format de durée doit être 'Xmin' ou 'Xh'.", delete_after=120)
            return

        if start_time_utc < datetime.datetime.now(SERVER_TIMEZONE):
            await ctx.send("L'heure de début est déjà passée. Veuillez choisir une heure future.", delete_after=120)
            return

    except (ValueError, IndexError):
        await ctx.send("Erreur de format. Utilisez le format 'HHhMM' et 'Xmin'/'Xh'.", delete_after=120)
        return

    if min_participants > max_participants:
        await ctx.send("Le nombre minimum de participants ne peut pas être supérieur au nombre maximum.", delete_after=120)
        return

    event_data = {
        "start_time": start_time_utc.isoformat(),
        "end_time": (start_time_utc + duration).isoformat(),
        "role_id": role.id,
        "announcement_channel_id": announcement_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "min_participants": min_participants,
        "participants": [],
        "is_started": False,
        "message_id": None,
        "reminded_30m": False,
        "reminded_day_of": False
    }
    
    embed = discord.Embed(
        title=f"NEW EVENT: {event_name}",
        description="""
        Rejoignez-nous pour un événement spécial !
        
        **Procédure:**
        1. Cliquez sur le bouton "START" pour vous inscrire.
        2. Une fenêtre modale s'ouvrira pour que vous puissiez entrer votre pseudo de jeu.
        3. Votre nom apparaîtra dans la liste des participants.
        4. Une fois l'événement démarré, le rôle temporaire vous sera attribué et vous serez informé par message privé.
        """,
        color=NEON_PURPLE
    )
    embed.add_field(name="POINT DE RALLIEMENT", value=waiting_channel.mention, inline=True)
    embed.add_field(name="RÔLE ATTRIBUÉ", value=role.mention, inline=True)
    embed.add_field(name="DÉBUT DANS", value=format_time_left(event_data['start_time']), inline=False)
    embed.add_field(name=f"PARTICIPANTS ({len(event_data['participants'])}/{max_participants})", value="Aucun participant pour le moment.", inline=False)
    
    embed.set_footer(text="Style 8-bit futuriste, néon")
    embed.set_image(url="https://i.imgur.com/uCgE04g.gif")
    
    view = EventButtonsView(bot, event_name)
    message = await announcement_channel.send(content="@everyone", embed=embed, view=view)
    
    event_data['message_id'] = message.id
    data['events'][event_name] = event_data
    save_db_data(data)
    await ctx.send("L'événement a été créé avec succès !", delete_after=120)

@bot.command(name="create_event_plan")
@commands.has_permissions(administrator=True)
async def create_event_plan(ctx, date_str: str, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, min_participants: int, *, event_name: str):
    """
    Crée un événement planifié pour une date future.
    Exemple: !create_event_plan 31/12/2025 21h30 10min @role #annonce #salle 10 "nom_evenement"
    """
    await ctx.message.delete(delay=120)
    data = get_db_data()
    if event_name in data['events']:
        await ctx.send(f"Un événement nommé `{event_name}` existe déjà. Veuillez en terminer l'ancien ou choisir un autre nom.", delete_after=120)
        return

    try:
        day, month, year = map(int, date_str.split('/'))
        start_hour, start_minute = map(int, start_time_str.split('h'))
        
        start_time_naive = datetime.datetime(year, month, day, start_hour, start_minute)
        start_time_localized = USER_TIMEZONE.localize(start_time_naive)
        start_time_utc = start_time_localized.astimezone(SERVER_TIMEZONE)

        duration_unit = duration_str[-3:].lower()
        duration_value = int(duration_str[:-3])

        if duration_unit == 'min':
            duration = datetime.timedelta(minutes=duration_value)
        elif duration_unit == 'h':
            duration = datetime.timedelta(hours=duration_value)
        else:
            await ctx.send("Le format de durée doit être 'Xmin' ou 'Xh'.", delete_after=120)
            return

        if start_time_utc < datetime.datetime.now(SERVER_TIMEZONE):
            await ctx.send("La date et l'heure de l'événement sont déjà passées. Veuillez choisir une date future.", delete_after=120)
            return

    except (ValueError, IndexError):
        await ctx.send("Erreur de format pour la date, l'heure ou la durée. Utilisez le format 'JJ/MM/AAAA HHhMM' et 'Xmin'/'Xh'.", delete_after=120)
        return
    
    if min_participants > max_participants:
        await ctx.send("Le nombre minimum de participants ne peut pas être supérieur au nombre maximum.", delete_after=120)
        return
        
    event_data = {
        "start_time": start_time_utc.isoformat(),
        "end_time": (start_time_utc + duration).isoformat(),
        "role_id": role.id,
        "announcement_channel_id": announcement_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "min_participants": min_participants,
        "participants": [],
        "is_started": False,
        "message_id": None,
        "reminded_30m": False,
        "reminded_day_of": False
    }
    
    embed = discord.Embed(
        title=f"NEW EVENT: {event_name}",
        description=f"""
        Rejoignez-nous pour un événement spécial !
        
        **Procédure:**
        1. Cliquez sur le bouton "START" pour vous inscrire.
        2. Une fenêtre modale s'ouvrira pour que vous puissiez entrer votre pseudo de jeu.
        3. Votre nom apparaîtra dans la liste des participants.
        4. Une fois l'événement démarré, le rôle temporaire vous sera attribué et vous serez informé par message privé.
        """,
        color=NEON_PURPLE
    )
    embed.add_field(name="POINT DE RALLIEMENT", value=waiting_channel.mention, inline=True)
    embed.add_field(name="RÔLE ATTRIBUÉ", value=role.mention, inline=True)
    embed.add_field(name="DÉBUT DANS", value=format_time_left(event_data['start_time']), inline=False)
    embed.add_field(name=f"PARTICIPANTS ({len(event_data['participants'])}/{max_participants})", value="Aucun participant pour le moment.", inline=False)
    
    embed.set_footer(text="Style 8-bit futuriste, néon")
    embed.set_image(url="https://i.imgur.com/uCgE04g.gif")
    
    view = EventButtonsView(bot, event_name)
    message = await announcement_channel.send(content="@everyone", embed=embed, view=view)
    
    event_data['message_id'] = message.id
    data['events'][event_name] = event_data
    save_db_data(data)
    await ctx.send("L'événement a été planifié avec succès !", delete_after=120)

@bot.command(name="end_event")
@commands.has_permissions(administrator=True)
async def end_event(ctx, *, event_name: str):
    """
    Termine un événement manuellement.
    """
    await ctx.message.delete(delay=120)
    data = get_db_data()
    if event_name not in data['events']:
        await ctx.send(f"L'événement `{event_name}` n'existe pas.", delete_after=120)
        return
        
    event_data = data['events'][event_name]
    
    for participant in event_data['participants']:
        member = ctx.guild.get_member(participant['id'])
        if member:
            try:
                role = ctx.guild.get_role(event_data['role_id'])
                if role and role in member.roles:
                    await member.remove_roles(role)
            except Exception as e:
                print(f"Impossible de retirer le rôle du membre {member.id}: {e}")
                
    del data['events'][event_name]
    save_db_data(data)
    
    channel = bot.get_channel(event_data['announcement_channel_id'])
    if channel:
        await channel.send(f"@everyone L'événement **{event_name}** est maintenant terminé. Merci à tous les participants !")
    
    await ctx.send(f"L'événement `{event_name}` a été terminé manuellement.", delete_after=120)

@bot.command(name="tirage")
@commands.has_permissions(administrator=True)
async def tirage(ctx, *, event_name: str):
    """
    Effectue un tirage au sort parmi les participants d'un événement.
    """
    await ctx.message.delete(delay=120)
    data = get_db_data()
    if event_name not in data['events']:
        await ctx.send(f"L'événement `{event_name}` n'existe pas.", delete_after=120)
        return
        
    event_data = data['events'][event_name]
    participants = event_data['participants']
    
    if not participants:
        await ctx.send(f"Il n'y a pas de participants pour le tirage au sort de l'événement `{event_name}`.", delete_after=120)
        return

    winner = random.choice(participants)
    
    embed = discord.Embed(
        title="🎉 TIRAGE AU SORT: GAGNANT ! 🎉",
        description=f"Le grand gagnant de l'événement `{event_name}` est...",
        color=NEON_GREEN
    )
    embed.add_field(name="Félicitations à", value=f"<@{winner['id']}>", inline=False)
    embed.set_footer(text="Contactez un administrateur pour votre récompense.")
    
    await ctx.send(embed=embed)

@bot.command(name="concours")
@commands.has_permissions(administrator=True)
async def concours(ctx, end_date_str: str, *, contest_name: str):
    """
    Crée un concours avec une date limite de participation.
    Exemple: !concours 31/12/2025 "Concours de Noël"
    """
    await ctx.message.delete(delay=120)
    data = get_db_data()
    if contest_name in data['contests']:
        await ctx.send(f"Un concours nommé `{contest_name}` existe déjà.", delete_after=120)
        return

    try:
        day, month, year = map(int, end_date_str.split('/'))
        end_time_naive = datetime.datetime(year, month, day, 23, 59, 59)
        end_time_localized = USER_TIMEZONE.localize(end_time_naive)
        end_time_utc = end_time_localized.astimezone(SERVER_TIMEZONE)

        if end_time_utc < datetime.datetime.now(SERVER_TIMEZONE):
            await ctx.send("La date de fin est déjà passée. Veuillez choisir une date future.", delete_after=120)
            return

    except (ValueError, IndexError):
        await ctx.send("Erreur de format pour la date. Utilisez le format 'JJ/MM/AAAA'.", delete_after=120)
        return

    contest_data = {
        "end_time": end_time_utc.isoformat(),
        "participants": [],
        "channel_id": ctx.channel.id
    }
    data['contests'][contest_name] = contest_data
    save_db_data(data)

    embed = discord.Embed(
        title=f"NEW CONTEST: {contest_name}",
        description="""
        Un nouveau concours a été lancé ! Participez pour tenter de gagner !
        
        **Pour participer:**
        1. Réagissez à ce message avec la réaction 🎉 pour vous inscrire.
        2. Le tirage au sort aura lieu à la date de fin.
        """,
        color=NEON_ORANGE
    )
    embed.add_field(name="DATE DE FIN", value=end_time_localized.strftime('%d/%m/%Y à %Hh%M'), inline=False)
    embed.add_field(name="PARTICIPANTS", value=f"0 participant(s) pour le moment.", inline=False)
    embed.set_footer(text="Bonne chance à tous !")
    
    message = await ctx.send(content="@everyone", embed=embed)
    await message.add_reaction("🎉")
    contest_data['message_id'] = message.id
    save_db_data(data)

@bot.event
async def on_raw_reaction_add(payload):
    """
    Gère l'ajout de réactions pour les concours.
    """
    if payload.member.bot:
        return

    data = get_db_data()
    for contest_name, contest_data in data['contests'].items():
        if payload.message_id == contest_data['message_id'] and str(payload.emoji) == "🎉":
            if payload.user_id not in [p['id'] for p in contest_data['participants']]:
                contest_data['participants'].append({
                    "id": payload.user_id,
                    "name": payload.member.display_name
                })
                save_db_data(data)
                
                try:
                    channel = bot.get_channel(payload.channel_id)
                    message = await channel.fetch_message(payload.message_id)
                    embed = message.embeds[0]
                    embed.set_field_at(
                        index=1,
                        name="PARTICIPANTS",
                        value=f"{len(contest_data['participants'])} participant(s) pour le moment.",
                        inline=False
                    )
                    await message.edit(embed=embed)
                except Exception as e:
                    print(f"Erreur lors de la mise à jour de l'embed du concours : {e}")

@bot.command(name="helpoxel")
async def helpoxel(ctx, *, command_name: str = None):
    """
    Affiche une aide détaillée ou la liste des commandes.
    """
    await ctx.message.delete(delay=120)
    if command_name:
        cmd = bot.get_command(command_name)
        if cmd:
            embed = discord.Embed(
                title=f"Aide pour la commande: !{cmd.name}",
                description=cmd.help or "Aucune description.",
                color=NEON_BLUE
            )
            embed.add_field(name="Syntaxe", value=f"```\n{cmd.signature}\n```", inline=False)
            await ctx.send(embed=embed, delete_after=120)
        else:
            await ctx.send(f"La commande `{command_name}` n'existe pas.", delete_after=120)
    else:
        embed = discord.Embed(
            title="MANUEL DE POXEL",
            description="Bienvenue dans le manuel de Poxel. Voici la liste des commandes disponibles :",
            color=NEON_BLUE
        )
        for cmd in bot.commands:
            embed.add_field(name=f"!{cmd.name}", value=cmd.help or "Pas de description.", inline=False)
        await ctx.send(embed=embed, delete_after=120)

@bot.event
async def on_command_error(ctx, error):
    """
    Gère les erreurs de commandes.
    """
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Erreur : Un argument est manquant. Vérifiez la syntaxe de la commande avec `!helpoxel {ctx.command.name}`.", delete_after=120)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Erreur : Un ou plusieurs arguments ne sont pas valides. Vérifiez la syntaxe avec `!helpoxel {ctx.command.name}`.", delete_after=120)
    elif isinstance(error, commands.MissingPermissions) or isinstance(error, commands.MissingRole):
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Commande non trouvée. Utilisez `!helpoxel` pour voir la liste des commandes.", delete_after=120)
    else:
        print(f"Erreur non gérée: {error}")
        await ctx.send("Une erreur inconnue est survenue.", delete_after=120)
    
    await ctx.message.delete(delay=120)

# --- TÂCHES PLANIFIÉES ---

@tasks.loop(seconds=1) # Boucle toutes les secondes pour les événements
async def check_events():
    """
    Boucle de vérification qui s'exécute pour gérer les événements en temps réel.
    """
    data = get_db_data()
    events_to_delete = []
    
    for event_name, event_data in list(data['events'].items()):
        start_time_utc = datetime.datetime.fromisoformat(event_data['start_time']).replace(tzinfo=SERVER_TIMEZONE)
        now_utc = datetime.datetime.now(SERVER_TIMEZONE)
        end_time_utc = datetime.datetime.fromisoformat(event_data['end_time']).replace(tzinfo=SERVER_TIMEZONE)

        # Logique pour le rappel du matin pour les événements planifiés
        if not event_data.get('reminded_day_of') and start_time_utc.date() == now_utc.date() and now_utc.hour >= 8:
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if channel:
                await channel.send(f"@everyone 📆 **RAPPEL:** L'événement **{event_name}** est prévu pour aujourd'hui ! N'oubliez pas de vous inscrire.")
                event_data['reminded_day_of'] = True
                save_db_data(data)

        # Logique pour le rappel de 30 minutes avant le début
        if not event_data.get('is_started') and not event_data.get('reminded_30m') and (start_time_utc - now_utc).total_seconds() <= 30 * 60 and start_time_utc > now_utc:
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if channel:
                await channel.send(f"@everyone ⏰ **RAPPEL:** L'événement **{event_name}** commence dans 30 minutes ! N'oubliez pas de vous inscrire.")
                event_data['reminded_30m'] = True
                save_db_data(data)
        
        # Logique pour le démarrage de l'événement et la clôture des inscriptions
        if not event_data.get('is_started') and now_utc >= start_time_utc:
            # Annulation de l'événement si le nombre minimum de participants n'est pas atteint
            if len(event_data['participants']) < event_data['min_participants']:
                channel = bot.get_channel(event_data['announcement_channel_id'])
                if channel:
                    await channel.send(f"@everyone ❌ **ANNULATION:** L'événement **{event_name}** a été annulé car le nombre de participants minimum n'a pas été atteint.")
                
                try:
                    message = await channel.fetch_message(event_data['message_id'])
                    await message.delete()
                except discord.NotFound:
                    pass
                
                events_to_delete.append(event_name)
                continue
                
            event_data['is_started'] = True
            save_db_data(data)
            
            channel = bot.get_channel(event_data['announcement_channel_id'])
            
            for participant in event_data['participants']:
                member = bot.get_guild(channel.guild.id).get_member(participant['id'])
                if member:
                    role = member.guild.get_role(event_data['role_id'])
                    if role:
                        try:
                            await member.add_roles(role)
                        except Exception as e:
                            print(f"Impossible d'ajouter le rôle à {member.display_name}: {e}")
                            
                    try:
                        await member.send(f"🎉 **Félicitations** ! L'événement `{event_name}` a démarré. Le rôle `{role.name}` vous a été attribué. Rendez-vous dans le salon <#{event_data['waiting_channel_id']}>.")
                    except discord.Forbidden:
                        print(f"Impossible d'envoyer un message privé à {member.display_name}")
                    
            if channel:
                await channel.send(f"@everyone L'événement **{event_name}** a officiellement commencé ! Les inscriptions sont closes et le rôle a été attribué aux participants.")
            
            await update_event_embed(bot, event_name)

        # Logique pour la fin de l'événement
        if now_utc >= end_time_utc and event_data.get('is_started'):
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if channel:
                await channel.send(f"@everyone L'événement **{event_name}** est maintenant terminé. Merci à tous les participants ! 🎉")
            
            for participant in event_data['participants']:
                member = bot.get_guild(channel.guild.id).get_member(participant['id'])
                if member:
                    try:
                        role = member.guild.get_role(event_data['role_id'])
                        if role and role in member.roles:
                            await member.remove_roles(role)
                    except Exception as e:
                        print(f"Impossible de retirer le rôle du membre {member.id}: {e}")
            
            try:
                message = await channel.fetch_message(event_data['message_id'])
                await message.delete()
            except discord.NotFound:
                pass

            events_to_delete.append(event_name)
        
        await update_event_embed(bot, event_name)

    for event_name in events_to_delete:
        if event_name in data['events']:
            del data['events'][event_name]
        
    save_db_data(data)

@tasks.loop(seconds=30) # Vérifie les concours toutes les 30 secondes
async def check_contests():
    """
    Boucle de vérification qui s'exécute pour gérer les concours.
    """
    data = get_db_data()
    contests_to_delete = []

    for contest_name, contest_data in list(data['contests'].items()):
        end_time_utc = datetime.datetime.fromisoformat(contest_data['end_time']).replace(tzinfo=SERVER_TIMEZONE)
        now_utc = datetime.datetime.now(SERVER_TIMEZONE)

        if now_utc >= end_time_utc:
            channel = bot.get_channel(contest_data['channel_id'])
            participants = contest_data['participants']
            
            if channel:
                if not participants:
                    await channel.send(f"@everyone Le concours **{contest_name}** s'est terminé sans participants. Il n'y a pas de gagnant.")
                else:
                    winner = random.choice(participants)
                    await channel.send(f"🎉 **Félicitations à <@{winner['id']}>** ! 🎉\nVous êtes le grand gagnant du concours **{contest_name}**.")
                    
                    try:
                        winner_member = bot.get_guild(channel.guild.id).get_member(winner['id'])
                        if winner_member:
                            await winner_member.send(f"Félicitations ! Vous avez gagné le concours `{contest_name}`. Un administrateur vous contactera pour vous expliquer la marche à suivre.")
                    except discord.Forbidden:
                        print(f"Impossible d'envoyer un message privé au gagnant {winner['name']}")

            contests_to_delete.append(contest_name)
    
    for contest_name in contests_to_delete:
        if contest_name in data['contests']:
            del data['contests'][contest_name]
    
    save_db_data(data)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bot.run(os.environ.get('DISCORD_BOT_TOKEN'))

