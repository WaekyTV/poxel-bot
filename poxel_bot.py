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
DATABASE_FILE = 'events.json'

def load_data():
    """
    Charge les données des événements et concours depuis un fichier JSON.
    Simule une base de données persistante comme Firebase.
    """
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            data = json.load(f)
            # S'assurer que les clés existent pour éviter les erreurs
            data.setdefault("events", {})
            data.setdefault("contests", {})
            # Décalage par défaut de 180s (3 minutes)
            data.setdefault("settings", {"time_offset_seconds": 180})
            return data
    # Décalage par défaut de 180s (3 minutes) lors de la création du fichier
    return {"events": {}, "contests": {}, "settings": {"time_offset_seconds": 180}}

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

# --- Fonctions utlitaires pour le formatage et la gestion ---
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
            # Affichage de l'heure exacte et du compte à rebours
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
        embed.set_footer(text="Style 8-bit futuriste, néon")
        # C'est ici que vous changez le GIF pour les mises à jour de l'événement
        embed.set_image(url="https://cdn.lospec.com/gallery/loading-727267.gif ") 
        
        # Mise à jour des boutons dans la vue
        view = EventButtonsView(bot, event_name, event)
        await message.edit(embed=embed, view=view)

        # Envoi des notifications de clôture/réouverture si l'interaction est un changement de participant
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

        # Création des boutons
        start_button = Button(label="START", style=discord.ButtonStyle.success, emoji="✅")
        start_button.callback = self.on_start_click

        quit_button = Button(label="QUIT", style=discord.ButtonStyle.danger, emoji="❌")
        quit_button.callback = self.on_quit_click

        list_button = Button(label="Événements en cours", style=discord.ButtonStyle.secondary)
        list_button.callback = self.on_list_click

        # Logique visuelle pour le bouton d'inscription
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

# --- Classes et fonctions pour les concours ---
class ConcoursView(View):
    def __init__(self, concours_name, timeout=None):
        super().__init__(timeout=timeout)
        self.concours_name = concours_name
        
    @discord.ui.button(label="Participer", style=discord.ButtonStyle.success)
    async def participate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        concours_data = db.get('contests', {}).get(self.concours_name)

        if not concours_data:
            await interaction.response.send_message("Ce concours n'existe plus.", ephemeral=True)
            return

        participants = concours_data.get('participants', [])
        if user.id in [p for p in participants]:
            await interaction.response.send_message("Tu participes déjà à ce concours !", ephemeral=True)
        else:
            participants.append(user.id)
            concours_data['participants'] = participants
            db['contests'][self.concours_name] = concours_data
            save_data(db)
            await interaction.response.send_message("Tu as rejoint le concours !", ephemeral=True)
            
        await update_concours_embed(interaction.client, self.concours_name)

async def update_concours_embed(bot_instance, concours_name):
    """Met à jour l'embed du concours en temps réel."""
    concours_data = db.get('contests', {}).get(concours_name)
    if not concours_data or concours_data.get('message_id') is None:
        return

    channel = bot_instance.get_channel(concours_data['channel_id'])
    if channel:
        try:
            message = await channel.fetch_message(concours_data['message_id'])
            if message:
                participants_names = []
                for user_id in concours_data['participants']:
                    user = bot_instance.get_user(user_id)
                    if user:
                        participants_names.append(user.display_name)
                
                participants_list = "\n".join(participants_names)
                if not participants_list:
                    participants_list = "Aucun participant pour le moment."

                embed = discord.Embed(
                    title=f"🎉 {concours_data['title']} 🎉",
                    description=concours_data['description'],
                    color=NEON_BLUE
                )
                embed.add_field(name="Date de fin", value=concours_data['end_date'], inline=False)
                embed.add_field(name="Participants", value=participants_list, inline=False)
                embed.set_footer(text="Cliquez sur 'Participer' pour rejoindre le concours.")

                await message.edit(embed=embed)
        except discord.NotFound:
            print(f"Le message du concours {concours_name} n'a pas été trouvé. Il sera supprimé de la base de données.")
            if concours_name in db['contests']:
                del db['contests'][concours_name]
                save_data(db)

# --- Initialisation du bot ---
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

@bot.event
async def on_ready():
    """Événement déclenché quand le bot est prêt."""
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    print("------")
    print(f"Heure actuelle du serveur (UTC) : {datetime.datetime.now(SERVER_TIMEZONE)}")
    print(f"Heure ajustée pour le bot (UTC) : {get_adjusted_time()}")
    print(f"Décalage actuel : {db['settings'].get('time_offset_seconds', 0)} secondes")
    check_events.start()
    check_contests_end.start()

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
        # Création de l'heure exacte sans les secondes ni les microsecondes pour éviter le décalage
        start_time_paris = now_paris.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        # Gestion du passage au jour suivant si l'heure est déjà passée
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
    embed.set_footer(text="Style 8-bit futuriste, néon")
    # C'est ici que vous changez le GIF lors de la création de l'événement
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
    embed.set_footer(text="Style 8-bit futuriste, néon")
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
            # Fermeture visuelle de l'embed et suppression des boutons
            embed = message.embeds[0]
            embed.title = f"Événement terminé: {event_name}"
            embed.description = "Cet événement est maintenant terminé. Merci à tous les participants !"
            embed.set_field_at(0, name="ÉTAT", value="TERMINÉ", inline=False)
            if len(embed.fields) > 1:
                for _ in range(len(embed.fields) - 1):
                    embed.remove_field(1)
            await message.edit(embed=embed, view=None)
        except discord.NotFound:
            pass # Le message a déjà été supprimé
            
    if announcement_channel:
        await announcement_channel.send(f"@everyone L'événement **{event_name}** est maintenant terminé. Merci à tous les participants !")
    
    del db['events'][event_name]
    save_data(db)
    await ctx.send(f"L'événement `{event_name}` a été terminé manuellement.", delete_after=120)

@bot.command(name="event_tirage")
@commands.has_permissions(administrator=True)
async def event_tirage(ctx, event_name: str):
    """Effectue un tirage au sort parmi les participants d'un événement."""
    await ctx.message.delete(delay=120)
    if event_name not in db['events']:
        await ctx.send(f"L'événement `{event_name}` n'existe pas.", delete_after=120)
        return
        
    participants = db['events'][event_name]['participants']
    if not participants:
        await ctx.send(f"Il n'y a pas de participants pour le tirage au sort de l'événement `{event_name}`.", delete_after=120)
        return

    winner = random.choice(participants)
    await ctx.send(f"🎉 **Félicitations à <@{winner['id']}>** ! 🎉\nVous êtes le grand gagnant du tirage au sort pour l'événement `{event_name}`.")

# --- Commandes du nouveau système de concours ---
@bot.command(name="concours")
@commands.has_permissions(administrator=True)
async def create_concours(ctx, date_fin: str, titre: str, *, description: str):
    """
    Crée un concours.
    Exemple: !concours 31/12/2025 "Titre du concours" "Description du concours"
    """
    try:
        fin_date = datetime.datetime.strptime(date_fin, "%d/%m/%Y").date()
    except ValueError:
        await ctx.send("Le format de la date de fin est incorrect. Utilisez `jj/mm/aaaa`.")
        return

    concours_name = f"{titre.replace(' ', '_')}_{fin_date.strftime('%Y%m%d')}"

    if concours_name in db.get('contests', {}):
        await ctx.send("Un concours avec ce titre et cette date existe déjà. Veuillez en choisir un autre.")
        return

    embed = discord.Embed(
        title=f"🎉 {titre} 🎉",
        description=description,
        color=NEON_BLUE
    )
    embed.add_field(name="Date de fin", value=date_fin, inline=False)
    embed.add_field(name="Participants", value="Aucun participant pour le moment.", inline=False)
    embed.set_footer(text="Cliquez sur 'Participer' pour rejoindre le concours.")

    view = ConcoursView(concours_name)
    message = await ctx.send(embed=embed, view=view)

    await ctx.send(f"@everyone Un nouveau concours vient de commencer ! {titre}\nPour participer, cliquez sur le bouton 'Participer' ci-dessous !")

    db['contests'][concours_name] = {
        "title": titre,
        "description": description,
        "end_date": date_fin,
        "end_timestamp": datetime.datetime.combine(fin_date, datetime.time.max).isoformat(),
        "channel_id": ctx.channel.id,
        "message_id": message.id,
        "participants": []
    }
    save_data(db)

@bot.command(name="tirage")
@commands.has_permissions(administrator=True)
async def tirage_au_sort(ctx, concours_name: str):
    """
    Tire au sort un participant d'un concours.
    Exemple: !tirage "Titre_du_concours_jj/mm/aaaa"
    """
    concours_data = db.get('contests', {}).get(concours_name)

    if not concours_data:
        await ctx.send("Ce concours n'existe pas.")
        return

    participants = concours_data.get('participants', [])
    if not participants:
        await ctx.send("Il n'y a aucun participant pour ce concours.")
        return

    gagnant_id = random.choice(participants)
    
    annonce_embed = discord.Embed(
        title=f"Le tirage au sort de {concours_data['title']} est terminé !",
        description=f"Le grand gagnant est... **<@{gagnant_id}>** !",
        color=NEON_PURPLE
    )
    annonce_embed.set_image(url="https://i.imgur.com/K1h5nUu.gif") 
    await ctx.send(f"@everyone Le tirage au sort du concours **{concours_data['title']}** a eu lieu !", embed=annonce_embed)

    try:
        user = bot.get_user(gagnant_id)
        if user:
            await user.send(f"Félicitations **{user.display_name}** ! Tu as remporté le concours **{concours_data['title']}** ! 🎉\nN'hésite pas à contacter les organisateurs pour récupérer ton prix.")
    except discord.Forbidden:
        await ctx.send(f"Je n'ai pas pu envoyer de message privé à <@{gagnant_id}>. Assure-toi que tes paramètres de confidentialité le permettent.")

    del db['contests'][concours_name]
    save_data(db)
    
@bot.command(name="end_concours")
@commands.has_permissions(administrator=True)
async def end_concours(ctx, concours_name: str, *, raison: str):
    """
    Annule un concours en cours.
    Exemple: !end_concours "Titre_du_concours_jj/mm/aaaa" "Raison de l'annulation"
    """
    if concours_name not in db.get('contests', {}):
        await ctx.send("Ce concours n'existe pas.")
        return

    await ctx.send(f"@everyone Le concours **{db['contests'][concours_name]['title']}** a été annulé. Raison : {raison}")

    del db['contests'][concours_name]
    save_data(db)
    await ctx.send("Le concours a été annulé et supprimé de la base de données.")

# --- Tâches planifiées pour la gestion des événements et des concours ---
@tasks.loop(seconds=1)
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
            if len(event_data['participants']) < 1: # Minimum de participants
                if channel:
                    await channel.send(f"@everyone ❌ **ANNULATION:** L'événement **{event_name}** a été annulé car le nombre de participants minimum n'a pas été atteint.")
                    try:
                        message = await channel.fetch_message(event_data['message_id'])
                        embed = message.embeds[0]
                        embed.title = f"Événement annulé: {event_name}"
                        embed.description = "Cet événement a été annulé car le nombre de participants minimum n'a pas été atteint."
                        embed.clear_fields()
                        embed.add_field(name="ÉTAT", value="ANNULÉ", inline=False)
                        embed.set_image(url="https://i.imgur.com/uCgE04g.gif") # Optionnel : vous pouvez ajouter une image d'annulation si vous voulez
                        await message.edit(embed=embed, view=None)
                    except discord.NotFound:
                        pass # Le message a déjà été supprimé
                events_to_delete.append(event_name)
                continue
                
            event_data['is_started'] = True
            save_data(db)
            
            # Fermeture visuelle de l'embed et suppression des boutons
            try:
                message = await channel.fetch_message(event_data['message_id'])
                embed = message.embeds[0]
                embed.title = f"Événement en cours: {event_name}"
                embed.description = "Cet événement a officiellement commencé. Rendez-vous dans le salon de jeu !"
                embed.clear_fields()
                embed.add_field(name="ÉTAT", value="EN COURS", inline=False)
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

        # Logique de fin de l'événement
        end_time_utc = datetime.datetime.fromisoformat(event_data['end_time']).replace(tzinfo=SERVER_TIMEZONE)
        if now_utc >= end_time_utc and event_data.get('is_started'):
            channel = bot.get_channel(event_data['announcement_channel_id'])
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
        
        # Mise à jour de l'embed pour le temps restant et les participants
        if not event_data.get('is_started'):
            await update_event_embed(bot, event_name)

    for event_name in events_to_delete:
        del db['events'][event_name]
    save_data(db)

@tasks.loop(minutes=1)
async def check_contests_end():
    """Tâche en arrière-plan pour vérifier la fin des concours."""
    now_utc = datetime.datetime.utcnow().replace(tzinfo=SERVER_TIMEZONE)
    contests_to_delete = []
    for concours_name, concours_data in list(db.get('contests', {}).items()):
        try:
            end_time_utc = datetime.datetime.fromisoformat(concours_data['end_timestamp']).replace(tzinfo=SERVER_TIMEZONE)
            if now_utc >= end_time_utc:
                channel = bot.get_channel(concours_data['channel_id'])
                if channel:
                    await channel.send(f"@everyone Le concours **{concours_data['title']}** est terminé ! Utilisez `!tirage {concours_name}` pour annoncer le gagnant.")
                contests_to_delete.append(concours_name)
        except Exception as e:
            print(f"Erreur lors de la vérification du concours {concours_name}: {e}")
            contests_to_delete.append(concours_name)
    
    for concours_name in contests_to_delete:
        db['contests'][concours_name]['status'] = 'ended'
        save_data(db)


if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    bot.run(os.environ.get('DISCORD_BOT_TOKEN'))
