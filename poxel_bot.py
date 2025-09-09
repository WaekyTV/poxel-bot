# Importations des librairies nécessaires
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput
import datetime
import asyncio
import os
import json
import pytz
import random
import math

# Importation et configuration de Flask pour l'hébergement sur Render
from flask import Flask
from threading import Thread

# Configuration du bot Discord
intents = discord.Intents.all()
BOT_PREFIX = "!"
NEON_PURPLE = 0x6441a5
NEON_BLUE = 0x027afa
USER_TIMEZONE = pytz.timezone('Europe/Paris')
SERVER_TIMEZONE = pytz.utc
DATABASE_FILE = 'events_contests.json'

def load_data():
    """
    Charge les données des événements et concours depuis un fichier JSON.
    Simule une base de données persistante comme Firebase.
    """
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {"events": {}, "contests": {}, "settings": {"time_offset_seconds": 0}}

def save_data(data):
    """Sauvegarde les données dans le fichier JSON."""
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

db = load_data()

# --- Serveur Flask pour le maintien en vie du bot ---
app = Flask(__name__)

@app.route('/')
def home():
    """Point de terminaison simple pour l'hébergement."""
    return "Poxel Bot is running!"

def run_flask():
    """Démarre le serveur Flask sur un thread séparé."""
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

# --- Fonctions utilitaires pour le formatage et la gestion ---
def get_adjusted_time():
    """Renvoie l'heure UTC actuelle ajustée avec le décalage."""
    offset = db['settings'].get('time_offset_seconds', 0)
    return datetime.datetime.now(SERVER_TIMEZONE) + datetime.timedelta(seconds=offset)

def format_time_left(end_time_str):
    """
    Formate le temps restant en jours, heures, minutes et secondes.
    """
    end_time_utc = datetime.datetime.fromisoformat(end_time_str).replace(tzinfo=SERVER_TIMEZONE)
    now_utc = get_adjusted_time()
    delta = end_time_utc - now_utc
    total_seconds = int(delta.total_seconds())
    
    if total_seconds < 0:
        total_seconds = abs(total_seconds)
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if days > 0:
            return f"FINI IL Y A {days} jour(s), {hours} heure(s)"
        if hours > 0:
            return f"FINI IL Y A {hours} heure(s), {minutes} minute(s)"
        if minutes > 0:
            return f"FINI IL Y A {minutes} minute(s), {seconds} seconde(s)"
        return f"FINI IL Y A {seconds} seconde(s)"

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    if days > 0:
        return f"{days} jour(s), {hours} heure(s)"
    elif hours > 0:
        return f"{hours} heure(s), {minutes} minute(s)"
    elif minutes > 0:
        return f"{minutes} minute(s), {seconds} seconde(s)"
    else:
        return f"{seconds} seconde(s)"

async def update_event_embed(bot, event_name, interaction=None):
    """
    Met à jour l'embed de l'événement avec les informations actuelles.
    """
    if event_name not in db['events']: return
    event = db['events'][event_name]
    announcement_channel_id = event['announcement_channel_id']
    message_id = event['message_id']
    try:
        channel = bot.get_channel(announcement_channel_id)
        if not channel: return
        message = await channel.fetch_message(message_id)

        embed = discord.Embed(
            title=f"NEW EVENT: {event_name}",
            description="Rejoignez-nous pour un événement spécial !",
            color=NEON_PURPLE
        )
        embed.add_field(name="POINT DE RALLIEMENT", value=f"<#{event['waiting_channel_id']}>", inline=True)
        embed.add_field(name="RÔLE ATTRIBUÉ", value=f"<@&{event['role_id']}>", inline=True)
        
        if not event.get('is_started'):
            start_time_utc = datetime.datetime.fromisoformat(event['start_time']).replace(tzinfo=SERVER_TIMEZONE)
            start_time_paris = start_time_utc.astimezone(USER_TIMEZONE)
            embed.add_field(name="DÉBUT PRÉVU", value=f"Le {start_time_paris.strftime('%d/%m/%Y')} à {start_time_paris.strftime('%Hh%M')}", inline=False)
            embed.add_field(name="DÉBUT DANS", value=format_time_left(event['start_time']), inline=False)
        else:
            embed.add_field(name="TEMPS RESTANT", value=format_time_left(event['end_time']), inline=False)
        
        participants_list = "\n".join([f"- **{p['name']}** ({p['pseudo']})" for p in event['participants']])
        if not participants_list: participants_list = "Aucun participant pour le moment."
            
        embed.add_field(
            name=f"PARTICIPANTS ({len(event['participants'])}/{event['max_participants']})",
            value=participants_list,
            inline=False
        )
        embed.set_image(url="https://cdn.lospec.com/gallery/loading-727267.gif ") 
        
        view = EventButtonsView(bot, event_name, event)
        await message.edit(embed=embed, view=view)

        if interaction:
            old_participant_count = event.get('last_participant_count', 0)
            new_participant_count = len(event['participants'])
            max_participants = event.get('max_participants', 0)

            if old_participant_count < max_participants and new_participant_count == max_participants:
                await channel.send(f"@everyone ⛔ **INSCRIPTIONS CLOSES !** L'événement **{event_name}** a atteint son nombre maximum de participants.")
            elif old_participant_count == max_participants and new_participant_count < max_participants:
                await channel.send(f"@everyone ✅ **RÉOUVERTURE !** Une place est disponible pour l'événement **{event_name}**.")

            event['last_participant_count'] = new_participant_count
            save_data(db)
    
    except discord.NotFound:
        if event_name in db['events']:
            del db['events'][event_name]
            save_data(db)
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'embed pour {event_name}: {e}")

async def update_contest_embed(bot, contest_name):
    """Met à jour l'embed du concours."""
    if contest_name not in db['contests']: return
    contest = db['contests'][contest_name]
    announcement_channel_id = contest['announcement_channel_id']
    message_id = contest['message_id']
    
    try:
        channel = bot.get_channel(announcement_channel_id)
        if not channel: return
        message = await channel.fetch_message(message_id)

        # Création de l'embed
        embed = discord.Embed(
            title=contest['title'],
            description=contest['description'],
            color=NEON_BLUE
        )
        
        end_date_time = datetime.datetime.fromisoformat(contest['end_time']).replace(tzinfo=SERVER_TIMEZONE)
        end_date_paris = end_date_time.astimezone(USER_TIMEZONE)
        
        participants_list = "\n".join([f"- <@{p['id']}>" for p in contest['participants']])
        if not participants_list: participants_list = "Aucun participant pour le moment."
        
        embed.add_field(name="INSCRITS", value=participants_list, inline=False)
        embed.add_field(name="FIN DU CONCOURS", value=f"Le {end_date_paris.strftime('%d/%m/%Y')} à {end_date_paris.strftime('%H:%M')}", inline=False)
        embed.add_field(name="TEMPS RESTANT", value=format_time_left(contest['end_time']), inline=False)
        
        view = ContestButtonsView(bot, contest_name, contest)
        await message.edit(embed=embed, view=view)

    except discord.NotFound:
        if contest_name in db['contests']:
            del db['contests'][contest_name]
            save_data(db)
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'embed du {contest_name}: {e}")

# --- Classes de boutons et de vues (UI) ---
class EventButtonsView(View):
    """Vue pour les boutons d'inscription aux événements."""
    def __init__(self, bot, event_name, event_data, timeout=None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.event_name = event_name
        self.event_data = event_data
        self.max_participants = self.event_data.get('max_participants', 10)
        self.current_participants = len(self.event_data.get('participants', []))

        start_button = Button(label="START", style=discord.ButtonStyle.success, emoji="✅")
        start_button.callback = self.on_start_click

        quit_button = Button(label="QUIT", style=discord.ButtonStyle.danger, emoji="❌")
        quit_button.callback = self.on_quit_click

        list_button = Button(label="Événements en cours", style=discord.ButtonStyle.secondary)
        list_button.callback = self.on_list_click

        if self.current_participants >= self.max_participants:
            start_button.label = "INSCRIPTIONS CLOSES"
            start_button.disabled = True
        
        self.add_item(start_button)
        self.add_item(quit_button)
        self.add_item(list_button)

    async def on_start_click(self, interaction: discord.Interaction):
        """Gère l'inscription d'un utilisateur."""
        user = interaction.user
        if user.id in [p['id'] for p in self.event_data['participants']]:
            await interaction.response.send_message("Vous êtes déjà inscrit à cet événement !", ephemeral=True)
            return
        
        modal = ParticipantModal(self, self.event_name)
        await interaction.response.send_modal(modal)

    async def on_quit_click(self, interaction: discord.Interaction):
        """Gère la désinscription d'un utilisateur."""
        user_id = interaction.user.id
        initial_participant_count = len(self.event_data['participants'])
        
        if user_id not in [p['id'] for p in self.event_data['participants']]:
            await interaction.response.send_message("Vous n'êtes pas inscrit à cet événement.", ephemeral=True)
            return
            
        self.event_data['participants'] = [p for p in self.event_data['participants'] if p['id'] != user_id]
        save_data(db)
        
        await update_event_embed(self.bot, self.event_name, interaction=interaction)
        await interaction.response.send_message("Vous vous êtes désinscrit de l'événement.", ephemeral=True)

    async def on_list_click(self, interaction: discord.Interaction):
        """Affiche la liste des événements en cours d'inscription."""
        active_events = [
            f"- `{name}` (début dans: {format_time_left(data['start_time'])})"
            for name, data in db['events'].items() if not data.get('is_started')
        ]
        
        if not active_events:
            await interaction.response.send_message("Il n'y a aucun événement en cours d'inscription pour le moment.", ephemeral=True)
        else:
            list_text = "\n".join(active_events)
            embed = discord.Embed(
                title="LISTE DES ÉVÉNEMENTS EN COURS",
                description=list_text,
                color=NEON_PURPLE
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class ContestButtonsView(View):
    """Vue pour les boutons d'inscription aux concours."""
    def __init__(self, bot, contest_name, contest_data, timeout=None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.contest_name = contest_name
        self.contest_data = contest_data
        
        start_button = Button(label="START", style=discord.ButtonStyle.success, emoji="✅")
        start_button.callback = self.on_start_click
        
        self.add_item(start_button)
        
    async def on_start_click(self, interaction: discord.Interaction):
        """Gère l'inscription au concours."""
        user = interaction.user
        if user.id in [p['id'] for p in self.contest_data['participants']]:
            await interaction.response.send_message("Vous êtes déjà inscrit à ce !", ephemeral=True)
            return
            
        self.contest_data['participants'].append({
            "id": user.id,
            "name": user.display_name
        })
        save_data(db)
        
        await update_contest_embed(self.bot, self.contest_name)
        await interaction.response.send_message("Vous êtes inscrit au !", ephemeral=True)

class ParticipantModal(Modal, title="Vérification de votre pseudo"):
    """Fenêtre modale pour que l'utilisateur entre son pseudo de jeu."""
    game_pseudo = TextInput(
        label="Entrez votre pseudo pour le jeu",
        placeholder="Laissez vide si c'est le même que votre pseudo Discord",
        required=False
    )
    def __init__(self, view, event_name):
        super().__init__()
        self.view = view
        self.event_name = event_name

    async def on_submit(self, interaction: discord.Interaction):
        """Ajoute le participant à l'événement et met à jour l'embed."""
        user = interaction.user
        game_pseudo = self.game_pseudo.value
        if not game_pseudo:
            game_pseudo = user.display_name
        
        self.view.event_data['participants'].append({
            "id": user.id,
            "name": user.display_name,
            "pseudo": game_pseudo
        })
        save_data(db)
        
        await update_event_embed(self.view.bot, self.event_name, interaction=interaction)
        await interaction.response.send_message(f"Vous avez été inscrit à l'événement `{self.event_name}` avec le pseudo `{game_pseudo}`.", ephemeral=True)

# --- Initialisation du bot ---
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)


@bot.event
async def on_command(ctx):
    """Supprime le message de commande après son exécution."""
    if ctx.guild: # Vérifie que la commande n'est pas en message privé
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            print("Le bot n'a pas la permission de supprimer des messages.")
        except discord.NotFound:
            pass # Le message a déjà été supprimé

@bot.event
async def on_ready():
    """Événement déclenché quand le bot est prêt."""
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    print("------")
    print(f"Heure actuelle du serveur (UTC) : {datetime.datetime.now(SERVER_TIMEZONE)}")
    print(f"Heure ajustée pour le bot (UTC) : {get_adjusted_time()}")
    print(f"Décalage actuel : {db['settings'].get('time_offset_seconds', 0)} secondes")
    check_events.start()
    check_contests.start()

# --- Commandes du bot ---
@bot.command(name="set_offset")
@commands.has_permissions(administrator=True)
async def set_offset(ctx, offset_str: str):
    """
    Définit le décalage de temps pour corriger l'horloge du serveur.
    Syntaxe: !set_offset 180s (pour +3min) ou -180s (pour -3min)
    """
    await ctx.message.delete(delay=120)
    try:
        value = int(offset_str[:-1])
        unit = offset_str[-1].lower()
        if unit != 's':
            await ctx.send("Le format doit être un nombre suivi de 's' (ex: 180s).", delete_after=120)
            return

        db['settings']['time_offset_seconds'] = value
        save_data(db)
        await ctx.send(f"Le décalage de temps a été ajusté à {value} secondes.", delete_after=120)
    except (ValueError, IndexError):
        await ctx.send("Format invalide. Utilisez 'nombre' + 's' (ex: 180s).", delete_after=120)


@bot.command(name="create_event")
@commands.has_permissions(administrator=True)
async def create_event(ctx, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, game_participants_str: str, event_name: str):
    """
    Crée un événement le jour même.
    Syntaxe: !create_event 21h30 10min @role #annonce #salle 10 "pseudonyme" "nom_evenement"
    """
    await ctx.message.delete(delay=120)
    if event_name in db['events']:
        await ctx.send(f"Un événement nommé `{event_name}` existe déjà.", delete_after=120)
        return

    try:
        now_paris = datetime.datetime.now(USER_TIMEZONE)
        start_hour, start_minute = map(int, start_time_str.split('h'))
        start_time_paris = now_paris.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        if start_time_paris < now_paris:
            start_time_paris += datetime.timedelta(days=1)
        
        start_time_utc = start_time_paris.astimezone(SERVER_TIMEZONE)

        duration_value, duration_unit = int(duration_str[:-3]), duration_str[-3:].lower()
        if duration_unit == 'min': duration = datetime.timedelta(minutes=duration_value)
        elif duration_unit == 'h': duration = datetime.timedelta(hours=duration_value)
        else:
            await ctx.send("Le format de durée doit être 'Xmin' ou 'Xh'.", delete_after=120)
            return
    except (ValueError, IndexError):
        await ctx.send("Erreur de format. Utilisez 'HHhMM' et 'Xmin'/'Xh'.", delete_after=120)
        return

    event_data = {
        "start_time": start_time_utc.isoformat(),
        "end_time": (start_time_utc + duration).isoformat(),
        "role_id": role.id,
        "announcement_channel_id": announcement_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "participants": [],
        "last_participant_count": 0,
        "is_started": False,
        "message_id": None,
        "reminded_30m": False,
        "reminded_morning": False
    }
    
    embed = discord.Embed(title=f"NEW EVENT: {event_name}", description="Rejoignez-nous pour un événement spécial !", color=NEON_PURPLE)
    embed.add_field(name="POINT DE RALLIEMENT", value=waiting_channel.mention, inline=True)
    embed.add_field(name="RÔLE ATTRIBUÉ", value=role.mention, inline=True)
    
    start_time_paris_str = start_time_paris.strftime('%Hh%M le %d/%m')
    embed.add_field(name="DÉBUT PRÉVU", value=start_time_paris_str, inline=True)
    embed.add_field(name="DÉBUT DANS", value=format_time_left(event_data['start_time']), inline=True)

    embed.add_field(name=f"PARTICIPANTS (0/{max_participants})", value="Aucun participant pour le moment.", inline=False)
    embed.set_image(url="https://i.imgur.com/uCgE04g.gif")
    
    view = EventButtonsView(bot, event_name, event_data)
    message = await announcement_channel.send(content="@everyone", embed=embed, view=view)
    
    event_data['message_id'] = message.id
    db['events'][event_name] = event_data
    save_data(db)
    await ctx.send("L'événement a été créé avec succès !", delete_after=120)

@bot.command(name="create_event_plan")
@commands.has_permissions(administrator=True)
async def create_event_plan(ctx, date_str: str, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, game_participants_str: str, event_name: str):
    """
    Crée un événement planifié.
    Syntaxe: !create_event_plan JJ/MM/AAAA 21h30 10min @role #annonce #salle 10 "pseudonyme" "nom_evenement"
    """
    await ctx.message.delete(delay=120)
    if event_name in db['events']:
        await ctx.send(f"Un événement nommé `{event_name}` existe déjà.", delete_after=120)
        return

    try:
        day, month, year = map(int, date_str.split('/'))
        start_hour, start_minute = map(int, start_time_str.split('h'))
        start_time_naive = datetime.datetime(year, month, day, start_hour, start_minute)
        start_time_localized = USER_TIMEZONE.localize(start_time_naive)
        start_time_utc = start_time_localized.astimezone(SERVER_TIMEZONE)

        if start_time_utc < get_adjusted_time():
            await ctx.send("La date et l'heure sont déjà passées. Veuillez choisir une date future.", delete_after=120)
            return

        duration_value, duration_unit = int(duration_str[:-3]), duration_str[-3:].lower()
        if duration_unit == 'min': duration = datetime.timedelta(minutes=duration_value)
        elif duration_unit == 'h': duration = datetime.timedelta(hours=duration_value)
        else:
            await ctx.send("Le format de durée doit être 'Xmin' ou 'Xh'.", delete_after=120)
            return
    except (ValueError, IndexError):
        await ctx.send("Erreur de format pour la date, l'heure ou la durée.", delete_after=120)
        return
        
    event_data = {
        "start_time": start_time_utc.isoformat(),
        "end_time": (start_time_utc + duration).isoformat(),
        "role_id": role.id,
        "announcement_channel_id": announcement_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "participants": [],
        "last_participant_count": 0,
        "is_started": False,
        "message_id": None,
        "reminded_30m": False,
        "reminded_morning": False
    }
    
    embed = discord.Embed(title=f"NEW EVENT: {event_name}", description="Rejoignez-nous pour un événement spécial !", color=NEON_PURPLE)
    embed.add_field(name="POINT DE RALLIEMENT", value=waiting_channel.mention, inline=True)
    embed.add_field(name="RÔLE ATTRIBUÉ", value=role.mention, inline=True)

    start_time_paris_str = start_time_localized.strftime('%Hh%M le %d/%m/%Y')
    embed.add_field(name="DÉBUT PRÉVU", value=start_time_paris_str, inline=True)
    embed.add_field(name="DÉBUT DANS", value=format_time_left(event_data['start_time']), inline=True)
    
    embed.add_field(name=f"PARTICIPANTS (0/{max_participants})", value="Aucun participant pour le moment.", inline=False)
    embed.set_image(url="https://i.imgur.com/uCgE04g.gif")
    
    view = EventButtonsView(bot, event_name, event_data)
    message = await announcement_channel.send(content="@everyone", embed=embed, view=view)
    
    event_data['message_id'] = message.id
    db['events'][event_name] = event_data
    save_data(db)
    await ctx.send("L'événement a été planifié avec succès !", delete_after=120)

@bot.command(name="end_event")
@commands.has_permissions(administrator=True)
async def end_event(ctx, event_name: str):
    """Termine un événement manuellement."""
    await ctx.message.delete(delay=120)
    if event_name not in db['events']:
        await ctx.send(f"L'événement `{event_name}` n'existe pas.", delete_after=120)
        return
    
    event_data = db['events'][event_name]
    announcement_channel = bot.get_channel(event_data['announcement_channel_id'])
    
    for participant in event_data['participants']:
        member = ctx.guild.get_member(participant['id'])
        if member:
            try:
                role = ctx.guild.get_role(event_data['role_id'])
                if role and role in member.roles: await member.remove_roles(role)
            except Exception as e:
                print(f"Impossible de retirer le rôle du membre {member.id}: {e}")
                
    if announcement_channel and event_data['message_id']:
        try:
            message = await announcement_channel.fetch_message(event_data['message_id'])
            embed = message.embeds[0]
            embed.title = f"Événement terminé: {event_name}"
            embed.description = "Cet événement est maintenant terminé. Merci à tous les participants !"
            embed.set_field_at(0, name="ÉTAT", value="TERMINÉ", inline=False)
            if len(embed.fields) > 1:
                for _ in range(len(embed.fields) - 1):
                    embed.remove_field(1)
            # Suppression du GIF et des boutons
            embed.set_image(url="")
            await message.edit(embed=embed, view=None)
        except discord.NotFound:
            pass
            
    if announcement_channel:
        await announcement_channel.send(f"@everyone L'événement **{event_name}** est maintenant terminé. Merci à tous les participants !")
    
    del db['events'][event_name]
    save_data(db)
    await ctx.send(f"L'événement `{event_name}` a été terminé manuellement.", delete_after=120)

@bot.command(name="tirage")
@commands.has_permissions(administrator=True)
async def tirage(ctx, contest_name: str):
    """
    Effectue un tirage au sort pour un concours.
    Syntaxe: !tirage [nom_du_concours]
    """
    await ctx.message.delete(delay=120)
    
    if contest_name not in db['contests']:
        await ctx.send(f"Le `{contest_name}` n'existe pas. Assurez-vous d'utiliser le nom exact du concours.", delete_after=120)
        return
    
    contest_data = db['contests'][contest_name]
    participants = contest_data['participants']
    channel = bot.get_channel(contest_data['announcement_channel_id'])

    if not participants:
        await ctx.send(f"Il n'y a pas de participants pour le tirage au sort du concours `{contest_name}`.", delete_after=120)
        return

    winner_data = random.choice(participants)
    winner_id = winner_data['id']
    winner_member = ctx.guild.get_member(winner_id)
    
    # Annonce publique
    if channel:
        await channel.send(f"@everyone 🎉 **Félicitations à <@{winner_id}>** ! 🎉\nVous êtes le grand gagnant du tirage au sort pour le concours **{contest_name}** !")
    
    # Envoi d'un message privé à l'administrateur
    try:
        admin_dm_message = f"**TIRAGE AU SORT TERMINÉ**\nLe concours **{contest_name}** a désigné un gagnant :\nPseudo discord du gagnant : <@{winner_id}>"
        await ctx.author.send(admin_dm_message)
        print(f"Message privé envoyé à l'administrateur pour le tirage au sort de {contest_name}.")
    except discord.Forbidden:
        print("Impossible d'envoyer un message privé à l'administrateur. Les DMs sont peut-être désactivés.")
        await ctx.send("Impossible de vous envoyer la notification privée. Assurez-vous d'avoir activé les messages privés sur ce serveur.", delete_after=120)
    
    # Envoi d'un message privé au gagnant
    if winner_member:
        try:
            embed_dm = discord.Embed(
                title="🏆VOUS AVEZ GAGNÉ UN CONCOURS !",
                description=f"Félicitations, <@{winner_id}> !\n\nVous êtes le grand gagnant du concours **{contest_name}** !\n\nContactez l'administration pour réclamer votre prix.",
                color=NEON_BLUE
            )
            embed_dm.set_footer(text="Message de Poxel Bot")
            await winner_member.send(embed=embed_dm)
        except discord.Forbidden:
            print(f"Impossible d'envoyer un message privé au gagnant {winner_member.name}.")

@bot.command(name="concours")
@commands.has_permissions(administrator=True)
async def create_contest(ctx, end_date_str: str, end_time_str: str, title: str, *, description: str):
    """
    Crée un concours avec une date, un titre et une description.
    Syntaxe: !concours [date_de_fin] [heure_de_fin] "Titre" "Description"
    Exemple: !concours 31/12/2025 23h59 "Concours de Dessin" "Dessinez votre personnage préféré !"
    """
    await ctx.message.delete(delay=120)
    
    # Vérification des paramètres
    if not (end_date_str and end_time_str and title and description):
        await ctx.send("Syntaxe invalide. Utilisez: `!concours [date] [heure] \"Titre\" \"Description\"`", delete_after=120)
        return
        
    contest_name = title.strip()
    
    try:
        # Création de la date de fin
        day, month, year = map(int, end_date_str.split('/'))
        hour, minute = map(int, end_time_str.split('h'))
        end_time_naive = datetime.datetime(year, month, day, hour, minute)
        end_time_localized = USER_TIMEZONE.localize(end_time_naive)
        end_time_utc = end_time_localized.astimezone(SERVER_TIMEZONE)

        if end_time_utc < get_adjusted_time():
            await ctx.send("La date et l'heure de fin du concours sont déjà passées.", delete_after=120)
            return
            
    except (ValueError, IndexError):
        await ctx.send("Format de date ou d'heure invalide. Utilisez 'JJ/MM/AAAA' et 'HHhMM'.", delete_after=120)
        return

    contest_data = {
        "title": title,
        "description": description,
        "end_time": end_time_utc.isoformat(),
        "participants": [],
        "announcement_channel_id": ctx.channel.id,
        "message_id": None,
        "is_finished": False
    }
    
    # Création de l'embed du concours
    embed = discord.Embed(
        title=title,
        description=description,
        color=NEON_BLUE
    )
    embed.add_field(name="FIN DU CONCOURS", value=f"Le {end_time_localized.strftime('%d/%m/%Y')} à {end_time_localized.strftime('%H:%M')}", inline=False)
    embed.add_field(name="TEMPS RESTANT", value=format_time_left(contest_data['end_time']), inline=False)
    embed.add_field(name="INSCRITS", value="Aucun participant pour le moment.", inline=False)
    
    view = ContestButtonsView(bot, contest_name, contest_data)
    message = await ctx.channel.send(content="@everyone 🏆 **NOUVEAU CONCOURS !**", embed=embed, view=view)
    
    contest_data['message_id'] = message.id
    db['contests'][contest_name] = contest_data
    save_data(db)
    await ctx.send(f"Le concours `{contest_name}` a été créé avec succès !", delete_after=120)

@bot.command(name="end_concours")
@commands.has_permissions(administrator=True)
async def end_contest_manual(ctx, contest_name: str, *, reason: str = None):
    """
    Annule un concours.
    Syntaxe: !end_concours "nom_du_concours" "Raison de l'annulation"
    """
    await ctx.message.delete(delay=120)
    if contest_name not in db['contests']:
        await ctx.send(f"Le concours `{contest_name}` n'existe pas.", delete_after=120)
        return
        
    contest_data = db['contests'][contest_name]
    announcement_channel = bot.get_channel(contest_data['announcement_channel_id'])
    
    # Mise à jour de l'embed
    if announcement_channel and contest_data['message_id']:
        try:
            message = await announcement_channel.fetch_message(contest_data['message_id'])
            embed = message.embeds[0]
            embed.title = f"Concours annulé: {contest_name}"
            embed.description = "Ce concours est maintenant annulé."
            if reason:
                embed.description += f"\n**Raison:** {reason}"
            embed.clear_fields()
            embed.add_field(name="ÉTAT", value="ANNULÉ", inline=False)
            # Suppression des boutons
            await message.edit(embed=embed, view=None)
        except discord.NotFound:
            pass
    
    if announcement_channel:
        await announcement_channel.send(f"@everyone ❌ Le concours **{contest_name}** a été annulé.")
    
    del db['contests'][contest_name]
    save_data(db)
    await ctx.send(f"Le concours `{contest_name}` a été annulé manuellement.", delete_after=120)

@bot.command(name="helpoxel", aliases=["help"])
async def help_command(ctx):
    """Affiche toutes les commandes disponibles."""
    await ctx.message.delete()
    
    embed = discord.Embed(
        title="Guide des commandes Poxel",
        description="Voici la liste des commandes disponibles pour ce serveur. Les commandes avec `(ADMIN)` ne peuvent être utilisées que par les administrateurs.",
        color=0x6441a5 # NEON_PURPLE
    )

    # Catégorie des commandes d'événements
    embed.add_field(name="🎉 Commandes d'Événements (ADMIN)", value="---", inline=False)
    embed.add_field(name="`!create_event`", value="Crée un événement le jour même.\n`!create_event [heure] [durée] @role #annonce #salle [nombre] \"pseudo\" \"nom_evenement\"`", inline=False)
    embed.add_field(name="`!create_event_plan`", value="Crée un événement planifié.\n`!create_event_plan [date] [heure] [durée] @role #annonce #salle [nombre] \"pseudo\" \"nom_evenement\"`", inline=False)
    embed.add_field(name="`!listevents`", value="Affiche la liste de tous les événements actifs.", inline=False)
    embed.add_field(name="`!end_event`", value="Termine un événement manuellement.", inline=False)
    
    # Catégorie des commandes de concours
    embed.add_field(name="🏆 Commandes de Concours", value="---", inline=False)
    embed.add_field(name="`!concours` (ADMIN)", value="Crée un concours.\n`!concours [date] [heure] \"Titre\" \"Description\"`", inline=False)
    embed.add_field(name="`!end_concours` (ADMIN)", value="Annule un concours.\n`!end_concours \"Nom_du_concours\" \"Raison\"`", inline=False)
    embed.add_field(name="`!tirage` (ADMIN)", value="Effectue un tirage au sort.\n`!tirage \"Nom_du_concours\"`", inline=False)

    # Catégorie des commandes utilitaires
    embed.add_field(name="🛠️ Commandes Utilitaires", value="---", inline=False)
    embed.add_field(name="`!helpoxel`", value="Affiche ce manuel d'aide. Alias : `!help`", inline=False)
    embed.add_field(name="`!set_offset` (ADMIN)", value="Définit le décalage de temps.\n`!set_offset 180s` (pour +3min)", inline=False)

    await ctx.send(embed=embed, ephemeral=True)
# --- Tâches planifiées pour la gestion des événements et des concours ---
@tasks.loop(seconds=10)
async def check_events():
    """Vérifie l'état de tous les événements en temps réel."""
    events_to_delete = []
    for event_name, event_data in list(db['events'].items()):
        start_time_utc = datetime.datetime.fromisoformat(event_data['start_time']).replace(tzinfo=SERVER_TIMEZONE)
        now_utc = get_adjusted_time()
        
        # Rappel 30 minutes avant le début
        if not event_data.get('reminded_30m') and (start_time_utc - now_utc).total_seconds() <= 30 * 60 and start_time_utc > now_utc:
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if channel:
                await channel.send(f"@everyone ⏰ **RAPPEL:** L'événement **{event_name}** commence dans 30 minutes ! N'oubliez pas de vous inscrire.")
                event_data['reminded_30m'] = True
                save_data(db)
        
        # Logique de démarrage de l'événement
        if not event_data.get('is_started') and now_utc >= start_time_utc:
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if len(event_data['participants']) < 1:
                if channel:
                    await channel.send(f"@everyone ❌ **ANNULATION:** L'événement **{event_name}** a été annulé car le nombre de participants minimum n'a pas été atteint.")
                    try:
                        message = await channel.fetch_message(event_data['message_id'])
                        embed = message.embeds[0]
                        embed.title = f"Événement annulé: {event_name}"
                        embed.description = "Cet événement a été annulé car le nombre de participants minimum n'a pas été atteint."
                        embed.clear_fields()
                        embed.add_field(name="ÉTAT", value="ANNULÉ", inline=False)
                        embed.set_image(url="")
                        await message.edit(embed=embed, view=None)
                    except discord.NotFound:
                        pass
                events_to_delete.append(event_name)
                continue
                
            event_data['is_started'] = True
            save_data(db)
            
            try:
                message = await channel.fetch_message(event_data['message_id'])
                embed = message.embeds[0]
                embed.title = f"Événement en cours: {event_name}"
                embed.description = "Cet événement a officiellement commencé. Rendez-vous dans le salon de jeu !"
                embed.clear_fields()
                embed.add_field(name="ÉTAT", value="EN COURS", inline=False)
                embed.set_image(url="")
                await message.edit(embed=embed, view=None)
            except discord.NotFound:
                pass
            
            for participant in event_data['participants']:
                member = bot.get_guild(channel.guild.id).get_member(participant['id'])
                if member:
                    role = member.guild.get_role(event_data['role_id'])
                    if role: await member.add_roles(role)
                    try:
                        await member.send(f"🎉 **Félicitations** ! L'événement `{event_name}` a démarré. Le rôle `{role.name}` vous a été attribué. Rendez-vous dans le salon <#{event_data['waiting_channel_id']}>.")
                    except discord.Forbidden:
                        print(f"Impossible d'envoyer un MP à {member.display_name}.")
                        
            if channel: await channel.send(f"@everyone L'événement **{event_name}** a officiellement commencé ! Les inscriptions sont closes et le rôle a été attribué aux participants.")

        end_time_utc = datetime.datetime.fromisoformat(event_data['end_time']).replace(tzinfo=SERVER_TIMEZONE)
        if now_utc >= end_time_utc and event_data.get('is_started'):
            channel = bot.get_channel(event_data['announcement_channel_id'])
            
            # Mise à jour de l'embed pour indiquer la fin de l'événement
            if channel and event_data['message_id']:
                try:
                    message = await channel.fetch_message(event_data['message_id'])
                    embed = message.embeds[0]
                    embed.title = f"Événement terminé: {event_name}"
                    embed.description = "Cet événement est maintenant terminé. Merci à tous les participants !"
                    embed.clear_fields()
                    embed.add_field(name="ÉTAT", value="TERMINÉ", inline=False)
                    embed.set_image(url="")
                    await message.edit(embed=embed, view=None)
                except discord.NotFound:
                    print(f"Message d'événement non trouvé pour {event_name}.")
            
            if channel: await channel.send(f"@everyone L'événement **{event_name}** est maintenant terminé. Merci à tous les participants ! 🎉")
            
            for participant in event_data['participants']:
                member = bot.get_guild(channel.guild.id).get_member(participant['id'])
                if member:
                    try:
                        role = member.guild.get_role(event_data['role_id'])
                        if role and role in member.roles: await member.remove_roles(role)
                    except Exception as e:
                        print(f"Impossible de retirer le rôle du membre {member.id}: {e}")
                        
            events_to_delete.append(event_name)
        
        if not event_data.get('is_started') and event_data['message_id']:
            await update_event_embed(bot, event_name)

    for event_name in events_to_delete:
        del db['events'][event_name]
    save_data(db)

@tasks.loop(seconds=10)
async def check_contests():
    """Vérifie l'état des concours et les termine s'ils sont arrivés à échéance."""
    now_utc = get_adjusted_time()
    for contest_name, contest_data in list(db['contests'].items()):
        end_time_utc = datetime.datetime.fromisoformat(contest_data['end_time']).replace(tzinfo=SERVER_TIMEZONE)

        # Mise à jour de l'embed uniquement si le concours n'est pas terminé
        if now_utc < end_time_utc and contest_data['message_id']:
            await update_contest_embed(bot, contest_name)

        if now_utc >= end_time_utc and not contest_data.get('is_finished'):
            channel = bot.get_channel(contest_data['announcement_channel_id'])
            message_id = contest_data['message_id']
            if not contest_data['participants']:
                # Annulation si personne ne s'est inscrit
                if channel and message_id:
                    try:
                        message = await channel.fetch_message(message_id)
                        embed = message.embeds[0]
                        embed.title = f"Concours annulé: {contest_name}"
                        embed.description = "Ce concours a été annulé car personne ne s'y est inscrit."
                        embed.clear_fields()
                        embed.add_field(name="ÉTAT", value="ANNULÉ", inline=False)
                        await message.edit(embed=embed, view=None)
                        await channel.send(f"@everyone ❌ Le concours **{contest_name}** a été annulé car il n'y a eu aucun participant.")
                    except discord.NotFound:
                        pass
                contests_to_delete.append(contest_name)
            # Mise à jour de l'embed pour indiquer la fin du concours
            if channel and message_id:
                try:
                    message = await channel.fetch_message(message_id)
                    embed = message.embeds[0]
                    embed.title = f"Concours terminé: {contest_name}"
                    embed.description = "Ce concours est maintenant terminé !"
                    embed.clear_fields()
                    embed.add_field(name="ÉTAT", value="TERMINÉ", inline=False)
                    # Suppression des boutons
                    await message.edit(embed=embed, view=None)
                    
                    await channel.send(f"@everyone Le concours **{contest_name}** est maintenant terminé. Un gagnant va maintenant être désigné.")
                except discord.NotFound:
                    pass
            
            contest_data['is_finished'] = True
            save_data(db)

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    bot.run(os.environ.get('DISCORD_BOT_TOKEN'))

