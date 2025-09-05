# Fichier poxel_bot.py

import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput
import datetime
import asyncio
import os
import json
import pytz
import random
from flask import Flask
from threading import Thread

# --- CONFIGURATION ---
intents = discord.Intents.all()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.reactions = True

BOT_PREFIX = "!"
NEON_PURPLE = 0x6441a5
NEON_BLUE = 0x027afa
NEON_GREEN = 0x00FF00
USER_TIMEZONE = pytz.timezone('Europe/Paris')
SERVER_TIMEZONE = pytz.utc
DATABASE_FILE = 'data.json' # Renommé pour être plus générique

# --- DATABASE (SIMULATION) ---
def load_data():
    """Charge les données des événements et concours depuis le fichier de la base de données."""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {"events": {}, "contests": {}}
    return {"events": {}, "contests": {}}

def save_data(data):
    """Sauvegarde les données des événements et concours dans le fichier de la base de données."""
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

db = load_data()

# --- FLASK SERVER POUR LA PERSISTANCE ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Poxel Bot est en cours d'exécution !"

def run_flask():
    """Démarre le serveur Flask."""
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

# --- CLASSES DE BOUTONS ET DE VUES ---

class EventButtonsView(View):
    """
    Vue contenant les boutons d'inscription et de désinscription pour un événement.
    """
    def __init__(self, bot, event_name, event_data, timeout=None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.event_name = event_name
        self.event_data = event_data
        self.max_participants = self.event_data.get('max_participants', 0)
        self.current_participants = len(self.event_data.get('participants', []))
        self.update_buttons()

    def update_buttons(self):
        """Met à jour l'état visuel des boutons."""
        self.clear_items()
        
        # Bouton START (INSCRIPTION)
        start_button = Button(
            label="START",
            style=discord.ButtonStyle.success,
            emoji="✅"
        )
        if self.max_participants and self.current_participants >= self.max_participants:
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
        
        # Bouton "Liste des événements en cours"
        list_button = Button(
            label="Liste des événements en cours",
            style=discord.ButtonStyle.secondary
        )
        list_button.callback = self.on_list_click
        self.add_item(list_button)

    async def on_start_click(self, interaction: discord.Interaction):
        """Gère l'inscription d'un utilisateur."""
        user = interaction.user
        event_name = self.event_name
        
        if user.id in [p['id'] for p in self.event_data.get('participants', [])]:
            await interaction.response.send_message("Vous êtes déjà inscrit à cet événement !", ephemeral=True, delete_after=120)
            return

        # Ouverture de la modale pour le pseudo
        modal = ParticipantModal(self, event_name)
        await interaction.response.send_modal(modal)

    async def on_quit_click(self, interaction: discord.Interaction):
        """Gère la désinscription d'un utilisateur."""
        user_id = interaction.user.id
        event_name = self.event_name
        
        if user_id not in [p['id'] for p in self.event_data.get('participants', [])]:
            await interaction.response.send_message("Vous n'êtes pas inscrit à cet événement.", ephemeral=True, delete_after=120)
            return
            
        # Suppression du participant
        self.event_data['participants'] = [p for p in self.event_data['participants'] if p['id'] != user_id]
        save_data(db)
        
        self.current_participants = len(self.event_data['participants'])
        self.update_buttons()
        
        # Mise à jour de l'embed
        await update_event_embed(self.bot, event_name)
        await interaction.response.send_message("Vous vous êtes désinscrit de l'événement.", ephemeral=True, delete_after=120)

    async def on_list_click(self, interaction: discord.Interaction):
        """Affiche la liste des événements en cours."""
        active_events = [
            f"- `{name}` (début dans: {format_time_left(data['start_time'])})"
            for name, data in db['events'].items() if not data.get('is_started')
        ]
        
        if not active_events:
            await interaction.response.send_message("Il n'y a aucun événement en cours d'inscription pour le moment.", ephemeral=True, delete_after=120)
        else:
            list_text = "\n".join(active_events)
            embed = discord.Embed(
                title="LISTE DES ÉVÉNEMENTS EN COURS",
                description=list_text,
                color=NEON_PURPLE
            )
            await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=120)

class ParticipantModal(Modal, title="Pseudo pour le jeu"):
    """
    Fenêtre modale pour que l'utilisateur entre son pseudo de jeu.
    """
    game_pseudo = TextInput(
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
        user = interaction.user
        game_pseudo = self.game_pseudo.value
        
        # Enregistrement du participant
        self.view.event_data['participants'].append({
            "id": user.id,
            "name": user.display_name,
            "pseudo": game_pseudo
        })
        save_data(db)
        
        self.view.current_participants = len(self.view.event_data['participants'])
        self.view.update_buttons()

        # Mise à jour de l'embed
        await update_event_embed(self.view.bot, self.event_name)
        await interaction.response.send_message(f"Vous avez été inscrit à l'événement `{self.event_name}` avec le pseudo `{game_pseudo}`.", ephemeral=True, delete_after=120)

# --- FONCTIONS UTILES ---

def format_time_left(end_time_str):
    """
    Formate le temps restant avant le début ou la fin de l'événement.
    """
    end_time_utc = datetime.datetime.fromisoformat(end_time_str).replace(tzinfo=SERVER_TIMEZONE)
    now_utc = datetime.datetime.now(SERVER_TIMEZONE)
    delta = end_time_utc - now_utc
    
    if delta.total_seconds() < 0:
        # Affiche le temps écoulé si l'événement a déjà commencé
        seconds = abs(int(delta.total_seconds()))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        if days > 0:
            return f"FINI IL Y A {days} jour(s), {hours} heure(s)"
        if hours > 0:
            return f"FINI IL Y A {hours} heure(s), {minutes} minute(s)"
        if minutes > 0:
            return f"FINI IL Y A {minutes} minute(s), {seconds} seconde(s)"
        return f"FINI IL Y A {seconds} seconde(s)"

    # Affiche le temps restant en secondes, minutes, heures et jours
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
    if event_name not in db['events']:
        return

    event = db['events'][event_name]
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
            description="Rejoignez-nous pour un événement spécial !",
            color=NEON_PURPLE
        )
        embed.add_field(name="POINT DE RALLIEMENT", value=f"<#{event['waiting_channel_id']}>", inline=True)
        embed.add_field(name="RÔLE ATTRIBUÉ", value=f"<@&{event['role_id']}>", inline=True)
        
        # Gestion du temps
        if not event.get('is_started'):
            embed.add_field(name="DÉBUT DANS", value=format_time_left(event['start_time']), inline=False)
        else:
            embed.add_field(name="TEMPS RESTANT", value=format_time_left(event['end_time']), inline=False)

        # Liste des participants
        participants_list = "\n".join([f"- **{p['name']}** ({p['pseudo']})" for p in event['participants']])
        if not participants_list:
            participants_list = "Aucun participant pour le moment."
            
        embed.add_field(name=f"PARTICIPANTS ({len(event['participants'])}/{event['max_participants']})", value=participants_list, inline=False)
        embed.set_footer(text="Style 8-bit futuriste, néon")
        embed.set_image(url="https://i.imgur.com/uCgE04g.gif") 
        
        await message.edit(embed=embed, view=EventButtonsView(bot, event_name, event))
        
    except discord.NotFound:
        del db['events'][event_name]
        save_data(db)
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'embed pour {event_name}: {e}")

# --- BOT Poxel ---
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

@bot.event
async def on_ready():
    """
    Événement qui se déclenche lorsque le bot est prêt.
    """
    print(f"Connecté en tant que {bot.user.name} ({bot.user.id})")
    print("------")
    check_events.start()
    check_contests.start()

# --- GESTION DES COMMANDES ---

@bot.command(name="create_event")
async def create_event(ctx, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, game_participants_str: str, *, event_name: str):
    """
    Crée un événement pour le jour même.
    Syntaxe: !create_event 21h30 10min @role #annonce #salle 10 "pseudonyme" "nom_evenement"
    """
    if not ctx.message.author.guild_permissions.administrator:
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    if event_name in db['events']:
        await ctx.send(f"Un événement nommé `{event_name}` existe déjà. Veuillez en terminer l'ancien ou choisir un autre nom.", delete_after=120)
        await ctx.message.delete(delay=120)
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
            await ctx.message.delete(delay=120)
            return

    except (ValueError, IndexError):
        await ctx.send("Erreur de format pour l'heure ou la durée. Utilisez le format 'HHhMM' et 'Xmin'/'Xh'.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    event_data = {
        "start_time": start_time_utc.isoformat(),
        "end_time": (start_time_utc + duration).isoformat(),
        "role_id": role.id,
        "announcement_channel_id": announcement_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "participants": [],
        "is_started": False,
        "message_id": None
    }
    
    embed = discord.Embed(
        title=f"NEW EVENT: {event_name}",
        description=f"Rejoignez-nous pour un événement spécial !",
        color=NEON_PURPLE
    )
    embed.add_field(name="POINT DE RALLIEMENT", value=waiting_channel.mention, inline=True)
    embed.add_field(name="RÔLE ATTRIBUÉ", value=role.mention, inline=True)
    embed.add_field(name="DÉBUT DANS", value=format_time_left(event_data['start_time']), inline=False)
    embed.add_field(name=f"PARTICIPANTS ({len(event_data['participants'])}/{max_participants})", value="Aucun participant pour le moment.", inline=False)
    
    embed.set_footer(text="Style 8-bit futuriste, néon")
    embed.set_image(url="https://i.imgur.com/uCgE04g.gif")
    
    view = EventButtonsView(bot, event_name, event_data)
    message = await announcement_channel.send(content="@everyone", embed=embed, view=view)
    
    event_data['message_id'] = message.id
    db['events'][event_name] = event_data
    save_data(db)

    await ctx.send("L'événement a été créé avec succès !", delete_after=120)
    await ctx.message.delete(delay=120)

@bot.command(name="create_event_plan")
async def create_event_plan(ctx, date_str: str, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, game_participants_str: str, *, event_name: str):
    """
    Crée un événement planifié pour une date future.
    Syntaxe: !create_event_plan JJ/MM/AAAA 21h30 10min @role #annonce #salle 10 "pseudonyme" "nom_evenement"
    """
    if not ctx.message.author.guild_permissions.administrator:
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    if event_name in db['events']:
        await ctx.send(f"Un événement nommé `{event_name}` existe déjà. Veuillez en terminer l'ancien ou choisir un autre nom.", delete_after=120)
        await ctx.message.delete(delay=120)
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
            await ctx.message.delete(delay=120)
            return

        if start_time_utc < datetime.datetime.now(SERVER_TIMEZONE):
            await ctx.send("La date et l'heure de l'événement sont déjà passées. Veuillez choisir une date future.", delete_after=120)
            await ctx.message.delete(delay=120)
            return

    except (ValueError, IndexError):
        await ctx.send("Erreur de format pour la date, l'heure ou la durée. Utilisez le format 'JJ/MM/AAAA HHhMM' et 'Xmin'/'Xh'.", delete_after=120)
        await ctx.message.delete(delay=120)
        return
        
    event_data = {
        "start_time": start_time_utc.isoformat(),
        "end_time": (start_time_utc + duration).isoformat(),
        "role_id": role.id,
        "announcement_channel_id": announcement_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "participants": [],
        "is_started": False,
        "message_id": None
    }
    
    embed = discord.Embed(
        title=f"NEW EVENT: {event_name}",
        description=f"Rejoignez-nous pour un événement spécial, waeky !",
        color=NEON_PURPLE
    )
    embed.add_field(name="POINT DE RALLIEMENT", value=waiting_channel.mention, inline=True)
    embed.add_field(name="RÔLE ATTRIBUÉ", value=role.mention, inline=True)
    embed.add_field(name="DÉBUT DANS", value=format_time_left(event_data['start_time']), inline=False)
    embed.add_field(name=f"PARTICIPANTS ({len(event_data['participants'])}/{max_participants})", value="Aucun participant pour le moment.", inline=False)
    
    embed.set_footer(text="Style 8-bit futuriste, néon")
    embed.set_image(url="https://i.imgur.com/uCgE04g.gif")
    
    view = EventButtonsView(bot, event_name, event_data)
    message = await announcement_channel.send(content="@everyone", embed=embed, view=view)
    
    event_data['message_id'] = message.id
    db['events'][event_name] = event_data
    save_data(db)

    await ctx.send("L'événement a été planifié avec succès !", delete_after=120)
    await ctx.message.delete(delay=120)

@bot.command(name="end_event")
async def end_event(ctx, *, event_name: str):
    """
    Termine un événement manuellement.
    """
    if not ctx.message.author.guild_permissions.administrator:
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    if event_name not in db['events']:
        await ctx.send(f"L'événement `{event_name}` n'existe pas.", delete_after=120)
        await ctx.message.delete(delay=120)
        return
        
    event_data = db['events'][event_name]
    
    for participant in event_data['participants']:
        member = ctx.guild.get_member(participant['id'])
        if member:
            try:
                role = ctx.guild.get_role(event_data['role_id'])
                if role and role in member.roles:
                    await member.remove_roles(role)
            except Exception as e:
                print(f"Impossible de retirer le rôle du membre {member.id}: {e}")
                
    del db['events'][event_name]
    save_data(db)
    
    channel = bot.get_channel(event_data['announcement_channel_id'])
    if channel:
        await channel.send(f"@everyone L'événement **{event_name}** est maintenant terminé. Merci à tous les participants !")
    
    await ctx.send(f"L'événement `{event_name}` a été terminé manuellement.", delete_after=120)
    await ctx.message.delete(delay=120)

@bot.command(name="tirage")
async def tirage(ctx, *, event_name: str):
    """
    Effectue un tirage au sort parmi les participants d'un événement.
    """
    if not ctx.message.author.guild_permissions.administrator:
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    if event_name not in db['events']:
        await ctx.send(f"L'événement `{event_name}` n'existe pas.", delete_after=120)
        await ctx.message.delete(delay=120)
        return
        
    event_data = db['events'][event_name]
    participants = event_data['participants']
    
    if not participants:
        await ctx.send(f"Il n'y a pas de participants pour le tirage au sort de l'événement `{event_name}`.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    winner = random.choice(participants)
    
    await ctx.send(f"🎉 **Félicitations à <@{winner['id']}>** ! 🎉\nVous êtes le grand gagnant du tirage au sort pour l'événement `{event_name}`.")
    await ctx.message.delete(delay=120)

@bot.command(name="concours")
async def concours(ctx, date_fin: str, *, nom_concours: str):
    """
    Crée un nouveau concours. Le bot annoncera le gagnant le jour de la fin.
    Syntaxe: !concours JJ/MM/AAAA "nom du concours"
    """
    if not ctx.message.author.guild_permissions.administrator:
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    if nom_concours in db['contests']:
        await ctx.send(f"Un concours nommé `{nom_concours}` existe déjà. Veuillez choisir un autre nom.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    try:
        day, month, year = map(int, date_fin.split('/'))
        end_date_naive = datetime.datetime(year, month, day)
        end_date_utc = USER_TIMEZONE.localize(end_date_naive).astimezone(SERVER_TIMEZONE)
    except (ValueError, IndexError):
        await ctx.send("Erreur de format pour la date. Utilisez le format 'JJ/MM/AAAA'.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    if end_date_utc < datetime.datetime.now(SERVER_TIMEZONE):
        await ctx.send("La date de fin du concours est déjà passée. Veuillez choisir une date future.", delete_after=120)
        await ctx.message.delete(delay=120)
        return

    contest_data = {
        "end_date": end_date_utc.isoformat(),
        "participants": [],
        "announcement_channel_id": ctx.channel.id,
        "message_id": None
    }
    
    embed = discord.Embed(
        title=f"🎉 NOUVEAU CONCOURS : {nom_concours} 🎉",
        description=f"""
        Rejoignez notre nouveau concours et tentez votre chance !
        
        **Pour participer:**
        1. Cliquez sur le bouton "Participer".
        2. Un gagnant sera tiré au sort le **{end_date_utc.astimezone(USER_TIMEZONE).strftime('%d/%m/%Y')}**.
        3. Le gagnant sera annoncé publiquement et contacté par message privé.
        """,
        color=NEON_GREEN
    )
    embed.add_field(name="Date de fin", value=end_date_utc.astimezone(USER_TIMEZONE).strftime('%d/%m/%Y'), inline=True)
    embed.add_field(name="Nombre de participants", value="0", inline=True)
    embed.set_image(url="https://i.imgur.com/vHqJ9Uf.gif") # Exemple de GIF pour les concours
    
    class ContestView(View):
        def __init__(self, contest_name, timeout=None):
            super().__init__(timeout=timeout)
            self.contest_name = contest_name
        
        @discord.ui.button(label="Participer", style=discord.ButtonStyle.primary, emoji="✅")
        async def participate_button(self, interaction: discord.Interaction, button: Button):
            user_id = interaction.user.id
            if user_id in db['contests'][self.contest_name]['participants']:
                await interaction.response.send_message("Vous êtes déjà inscrit à ce concours !", ephemeral=True, delete_after=120)
            else:
                db['contests'][self.contest_name]['participants'].append(user_id)
                save_data(db)
                await interaction.response.send_message("Vous avez participé au concours !", ephemeral=True, delete_after=120)
                await update_contest_embed(ctx.bot, self.contest_name)
    
    view = ContestView(nom_concours)
    message = await ctx.send(content="@everyone", embed=embed, view=view)
    
    contest_data['message_id'] = message.id
    db['contests'][nom_concours] = contest_data
    save_data(db)

    await ctx.message.delete(delay=120)

async def update_contest_embed(bot, contest_name):
    """Met à jour l'embed d'un concours."""
    if contest_name not in db['contests']:
        return
    
    contest = db['contests'][contest_name]
    announcement_channel_id = contest['announcement_channel_id']
    message_id = contest['message_id']
    
    try:
        channel = bot.get_channel(announcement_channel_id)
        if not channel: return
        message = await channel.fetch_message(message_id)
        
        embed = discord.Embed(
            title=f"🎉 NOUVEAU CONCOURS : {contest_name} 🎉",
            description=f"""
            Rejoignez notre nouveau concours et tentez votre chance !
            
            **Pour participer:**
            1. Cliquez sur le bouton "Participer".
            2. Un gagnant sera tiré au sort le **{datetime.datetime.fromisoformat(contest['end_date']).astimezone(USER_TIMEZONE).strftime('%d/%m/%Y')}**.
            3. Le gagnant sera annoncé publiquement et contacté par message privé.
            """,
            color=NEON_GREEN
        )
        embed.add_field(name="Date de fin", value=datetime.datetime.fromisoformat(contest['end_date']).astimezone(USER_TIMEZONE).strftime('%d/%m/%Y'), inline=True)
        embed.add_field(name="Nombre de participants", value=f"{len(contest['participants'])}", inline=True)
        embed.set_image(url="https://i.imgur.com/vHqJ9Uf.gif")
        
        await message.edit(embed=embed)
        
    except discord.NotFound:
        del db['contests'][contest_name]
        save_data(db)
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'embed pour le concours {contest_name}: {e}")

@bot.command(name="helpoxel")
async def helpoxel(ctx, command_name: str = None):
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

# --- TÂCHES PLANIFIÉES ---

@tasks.loop(seconds=1)
async def check_events():
    """
    Boucle de vérification qui s'exécute toutes les secondes pour gérer les événements en temps réel.
    """
    events_to_delete = []
    
    for event_name, event_data in list(db['events'].items()):
        start_time_utc = datetime.datetime.fromisoformat(event_data['start_time']).replace(tzinfo=SERVER_TIMEZONE)
        now_utc = datetime.datetime.now(SERVER_TIMEZONE)
        
        if not event_data.get('reminded_30m') and (start_time_utc - now_utc).total_seconds() <= 30 * 60 and start_time_utc > now_utc:
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if channel:
                await channel.send(f"@everyone ⏰ **RAPPEL:** L'événement **{event_name}** commence dans 30 minutes ! N'oubliez pas de vous inscrire.")
                event_data['reminded_30m'] = True
                save_data(db)
        
        if not event_data.get('is_started') and now_utc >= start_time_utc:
            if len(event_data['participants']) < 1:
                channel = bot.get_channel(event_data['announcement_channel_id'])
                if channel:
                    await channel.send(f"@everyone ❌ **ANNULATION:** L'événement **{event_name}** a été annulé car le nombre de participants minimum n'a pas été atteint.")
                events_to_delete.append(event_name)
                continue
                
            event_data['is_started'] = True
            save_data(db)
            
            channel = bot.get_channel(event_data['announcement_channel_id'])
            try:
                message = await channel.fetch_message(event_data['message_id'])
                await message.delete()
            except discord.NotFound:
                pass 
            
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

        end_time_utc = datetime.datetime.fromisoformat(event_data['end_time']).replace(tzinfo=SERVER_TIMEZONE)
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
                        
            events_to_delete.append(event_name)
        
        if not event_data.get('is_started'):
            await update_event_embed(bot, event_name)

    for event_name in events_to_delete:
        if event_name in db['events']:
            del db['events'][event_name]
    save_data(db)

@tasks.loop(minutes=1)
async def check_contests():
    """
    Boucle de vérification qui s'exécute toutes les minutes pour gérer les concours.
    """
    contests_to_delete = []

    for contest_name, contest_data in list(db['contests'].items()):
        end_date_utc = datetime.datetime.fromisoformat(contest_data['end_date']).replace(tzinfo=SERVER_TIMEZONE)
        now_utc = datetime.datetime.now(SERVER_TIMEZONE)

        if now_utc >= end_date_utc:
            channel = bot.get_channel(contest_data['announcement_channel_id'])
            if channel:
                participants = contest_data['participants']
                if participants:
                    winner_id = random.choice(participants)
                    winner = bot.get_guild(channel.guild.id).get_member(winner_id)
                    if winner:
                        await channel.send(f"🎉 **Félicitations à {winner.mention}** ! 🎉\nVous êtes le grand gagnant du concours `{contest_name}`.")
                        try:
                            await winner.send(f"Félicitations ! Vous avez gagné le concours `{contest_name}`. Contactez les organisateurs pour réclamer votre prix.")
                        except discord.Forbidden:
                            print(f"Impossible d'envoyer un message privé au gagnant {winner.display_name}")
                    else:
                        await channel.send(f"Le tirage au sort pour le concours `{contest_name}` a été effectué, mais le gagnant n'a pas pu être notifié. Félicitations à <@{winner_id}> !")
                else:
                    await channel.send(f"Le concours `{contest_name}` s'est terminé sans participants. Il n'y a pas de gagnant.")
            
            contests_to_delete.append(contest_name)
    
    for contest_name in contests_to_delete:
        if contest_name in db['contests']:
            del db['contests'][contest_name]
    save_data(db)


if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    bot.run(os.environ.get('DISCORD_BOT_TOKEN'))
