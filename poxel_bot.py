import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, InputText
import datetime
import asyncio
import uuid
import humanize
import json
import os
import threading
from flask import Flask

# Définir l'intent nécessaire pour gérer les membres et les interactions
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

# --- Configuration du bot (mise à jour pour les variables d'environnement) ---
# Le token du bot est récupéré d'une variable d'environnement sur Render pour des raisons de sécurité.
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
# L'ID du serveur est également récupéré d'une variable d'environnement.
GUILD_ID = os.environ.get("GUILD_ID")

if not TOKEN:
    print("Erreur : Le token du bot (DISCORD_BOT_TOKEN) n'a pas été trouvé dans les variables d'environnement.")
    exit()

# Convertir l'ID du serveur en entier, si disponible
try:
    if GUILD_ID:
        GUILD_ID = int(GUILD_ID)
    else:
        GUILD_ID = 0  # Valeur par défaut si l'ID n'est pas fourni
        print("Avertissement : L'ID du serveur (GUILD_ID) n'est pas défini dans les variables d'environnement.")
except (ValueError, TypeError):
    print("Erreur : L'ID du serveur (GUILD_ID) doit être un nombre entier.")
    exit()

PREFIX = "!"
RETRO_COLOR = 0x009EFF
EVENTS_MAX_PARTICIPANTS = 10  # Nombre maximum de participants pour les événements
EVENT_CLEANUP_DELAY = 10  # Délai en secondes pour la suppression des messages de confirmation

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Dictionnaire pour stocker les événements actifs en mémoire
# uuid -> { 'name': str, 'type': str, 'message': discord.Message, 'channel': discord.TextChannel,
#           'role': discord.Role, 'participants': dict, 'start_time': datetime.datetime,
#           'end_time': datetime.datetime, 'participant_term': str, 'running_task': asyncio.Task,
#           'start_scheduled': bool, 'max_participants': int }
active_events = {}

# --- Serveur web pour l'hébergement sur Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Poxel est en ligne et fonctionnel."

def run_flask_app():
    """ Lance le serveur web de Flask sur un port spécifié par l'environnement. """
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    
# --- Fonctions utilitaires ---

def get_event_by_name(name: str):
    """Recherche un événement par son nom insensible à la casse."""
    for event_id, event_data in active_events.items():
        if event_data['name'].lower() == name.lower():
            return event_id, event_data
    return None, None

def check_manage_roles(ctx):
    """Vérifie si l'utilisateur a la permission de gérer les rôles."""
    return ctx.author.guild_permissions.manage_roles

def create_retro_embed(title: str, description: str = "", fields: list = None):
    """Crée un embed avec un style rétro."""
    embed = discord.Embed(
        title=f"• {title} •",
        description=f"```fix\n{description}\n```" if description else None,
        color=RETRO_COLOR
    )
    if fields:
        for name, value in fields:
            embed.add_field(name=f"・ {name}", value=f"```fix\n{value}\n```", inline=False)
    
    embed.set_footer(text="Système Poxel V2.0 // Réinitialisation du noyau en cours...")
    return embed

async def send_retro_message(ctx, message: str, delay: int = EVENT_CLEANUP_DELAY):
    """Envoie un message rétro qui s'auto-supprime."""
    embed = create_retro_embed("Message Système", message)
    msg = await ctx.send(embed=embed)
    await msg.delete(delay=delay)

def get_countdown(end_time):
    """Retourne une chaîne de caractères pour le compte à rebours."""
    remaining_time = end_time - datetime.datetime.now()
    if remaining_time.total_seconds() < 0:
        return "Événement terminé."
    return humanize.precisedelta(remaining_time, format="%d, %H, %M, %S", suppress=["microseconds", "milliseconds"])

# --- Vues pour les boutons ---

class EventView(View):
    """Gère les interactions avec les boutons 'Rejoindre' et 'Quitter'."""
    def __init__(self, event_id: uuid.UUID):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.update_buttons()

    def update_buttons(self, is_full: bool = False):
        """Met à jour l'état des boutons."""
        self.clear_items()
        
        start_button = Button(
            label="Rejoindre",
            style=discord.ButtonStyle.green if not is_full else discord.ButtonStyle.gray,
            custom_id=f"start_{self.event_id}",
            disabled=is_full
        )
        quit_button = Button(
            label="Quitter",
            style=discord.ButtonStyle.red,
            custom_id=f"quit_{self.event_id}"
        )
        
        self.add_item(start_button)
        self.add_item(quit_button)
    
    @discord.ui.button(label="Rejoindre", style=discord.ButtonStyle.green, custom_id=None)
    async def join_button_callback(self, button, interaction: discord.Interaction):
        event = active_events.get(self.event_id)
        if not event:
            await interaction.response.send_message("Cet événement n'est plus actif.", ephemeral=True)
            return

        if interaction.user.id in event['participants']:
            await interaction.response.send_message("Vous êtes déjà inscrit !", ephemeral=True)
            return

        event['participants'][interaction.user.id] = {'discord_name': interaction.user.display_name, 'game_name': None}
        
        if len(event['participants']) >= event['max_participants']:
            await interaction.channel.send(f"**@everyone** Inscriptions fermées pour l'événement **{event['name']}** ! Nombre maximum de {event['participant_term']} atteint.")
            self.update_buttons(is_full=True)
            await interaction.message.edit(view=self)
            
        await interaction.response.send_modal(GameNameModal(self.event_id))

    @discord.ui.button(label="Quitter", style=discord.ButtonStyle.red, custom_id=None)
    async def quit_button_callback(self, button, interaction: discord.Interaction):
        event = active_events.get(self.event_id)
        if not event:
            await interaction.response.send_message("Cet événement n'est plus actif.", ephemeral=True)
            return
            
        if interaction.user.id not in event['participants']:
            await interaction.response.send_message("Vous n'êtes pas inscrit à cet événement.", ephemeral=True)
            return

        event['participants'].pop(interaction.user.id)
        
        if len(event['participants']) < event['max_participants']:
            if self.children[0].disabled:
                await interaction.channel.send(f"**@everyone** Inscriptions réouvertes pour l'événement **{event['name']}** !")
                self.update_buttons(is_full=False)
                await interaction.message.edit(view=self)
                
        await update_event_embed(event)
        await interaction.response.send_message("Vous vous êtes désinscrit de l'événement.", ephemeral=True)

class GameNameModal(Modal):
    """Modale pour entrer le pseudo en jeu."""
    def __init__(self, event_id: uuid.UUID):
        super().__init__(title="Votre pseudo en jeu")
        self.event_id = event_id
        self.add_item(InputText(label="Pseudo en jeu (facultatif)", style=discord.InputTextStyle.short, required=False))

    async def callback(self, interaction: discord.Interaction):
        event = active_events.get(self.event_id)
        if not event:
            await interaction.response.send_message("Cet événement n'est plus actif.", ephemeral=True)
            return
        
        game_name = self.children[0].value if self.children[0].value else None
        event['participants'][interaction.user.id]['game_name'] = game_name

        await update_event_embed(event)
        await interaction.response.send_message("Bienvenue dans la partie ! Vos informations ont été enregistrées.", ephemeral=True)

# --- Fonction de mise à jour des embeds ---

async def update_event_embed(event):
    """Met à jour l'embed de l'événement avec les dernières informations."""
    participants_list = "\n".join(
        f"{p['discord_name']} ({p['game_name']})" if p['game_name'] else f"{p['discord_name']}"
        for p in event['participants'].values()
    ) if event['participants'] else "Aucun inscrit pour le moment."

    fields = [
        ("Nom de l'événement", event['name']),
        ("Rôle temporaire", event['role'].mention),
        ("Salon d'attente", event['channel'].mention),
        (f"Liste des {event['participant_term']}", participants_list),
        ("Nombre d'inscrits", f"{len(event['participants'])} / {event['max_participants']}"),
    ]
    
    embed = create_retro_embed(f"Événement: {event['name']}", description=
        f"Le rôle {event['role'].mention} vous sera attribué une fois l'événement démarré. "
        f"Veuillez rejoindre le point de ralliement et patienter jusqu'à ce que vous soyez déplacé dans le salon {event['channel'].mention}."
        f"\n\nDébut prévu dans : {get_countdown(event['start_time'])}",
        fields=fields
    )

    try:
        await event['message'].edit(embed=embed)
    except discord.NotFound:
        # Gérer le cas où le message est supprimé manuellement
        pass

# --- Tâches d'arrière-plan ---

@tasks.loop(seconds=1)
async def event_countdown_task():
    """Tâche pour gérer le compte à rebours et démarrer/annuler les événements."""
    now = datetime.datetime.now()
    events_to_start = []
    events_to_end = []
    
    # Gérer les événements immédiats non démarrés
    for event_id, event in active_events.items():
        if not event['start_scheduled'] and now >= event['start_time']:
            events_to_start.append(event_id)
        
        if event['running_task'] is not None and now >= event['end_time']:
            events_to_end.append(event_id)
    
    for event_id in events_to_start:
        event = active_events[event_id]
        if len(event['participants']) == 0:
            await event['channel'].send(f"L'événement **{event['name']}** a été annulé par manque de participants.")
            del active_events[event_id]
            continue
            
        await start_event(event_id)
    
    for event_id in events_to_end:
        await end_event_logic(event_id)

async def start_event(event_id):
    """Démarre un événement."""
    event = active_events.get(event_id)
    if not event:
        return
    
    await event['channel'].send(f"**@everyone** L'événement **{event['name']}** a commencé !")
    
    # Attribuer les rôles aux participants
    for user_id in event['participants']:
        try:
            member = event['channel'].guild.get_member(user_id)
            if member:
                await member.add_roles(event['role'])
        except Exception as e:
            print(f"Erreur lors de l'attribution du rôle à {user_id}: {e}")

    # Supprimer les boutons et le message
    await event['message'].delete()

    # Planifier la fin de l'événement
    event['running_task'] = bot.loop.create_task(
        end_event_timer(event_id, event['end_time'] - datetime.datetime.now())
    )

async def end_event_timer(event_id, delay):
    """Attend la fin de l'événement puis appelle la fonction de fin."""
    try:
        await asyncio.sleep(delay.total_seconds())
    except asyncio.CancelledError:
        # La tâche a été annulée manuellement
        return
        
    await end_event_logic(event_id)

async def end_event_logic(event_id):
    """Gère la logique de fin d'événement."""
    event = active_events.get(event_id)
    if not event:
        return
        
    await event['channel'].send(f"**@everyone** L'événement **{event['name']}** est terminé. Merci à tous les {event['participant_term']} !")
    
    # Retirer les rôles aux participants
    for user_id in event['participants']:
        try:
            member = event['channel'].guild.get_member(user_id)
            if member:
                await member.remove_roles(event['role'])
        except Exception as e:
            print(f"Erreur lors du retrait du rôle de {user_id}: {e}")
            
    # Supprimer l'événement de la liste
    if event['running_task']:
        event['running_task'].cancel()
    del active_events[event_id]
    
# --- Commandes du bot ---

@bot.command(name="create_event")
@commands.check(check_manage_roles)
async def create_event(
    ctx,
    name: str,
    role: discord.Role,
    channel: discord.TextChannel,
    duration_minutes: int,
    start_in_minutes: int,
    participant_term: str,
    max_participants: int = EVENTS_MAX_PARTICIPANTS
):
    """
    Crée un événement immédiat.
    Syntaxe: !create_event "Nom de l'événement" @Rôle #Salon Durée(min) Début(min) Terme
    """
    event_id, _ = get_event_by_name(name)
    if event_id:
        await send_retro_message(ctx, f"Erreur: Un événement nommé **{name}** existe déjà. Veuillez en choisir un autre.")
        return

    start_time = datetime.datetime.now() + datetime.timedelta(minutes=start_in_minutes)
    end_time = start_time + datetime.timedelta(minutes=duration_minutes)

    event_id = uuid.uuid4()
    active_events[event_id] = {
        'name': name,
        'type': 'immédiat',
        'message': None,
        'channel': channel,
        'role': role,
        'participants': {},
        'start_time': start_time,
        'end_time': end_time,
        'participant_term': participant_term,
        'running_task': None,
        'start_scheduled': False,
        'max_participants': max_participants,
    }

    view = EventView(event_id)
    
    await update_event_embed(active_events[event_id])
    
    message = await ctx.send(f"**@everyone** Un nouvel événement a été créé : **{name}** !", embed=None, view=view)
    active_events[event_id]['message'] = message
    
    await send_retro_message(ctx, f"Événement **{name}** créé avec succès.", delay=30)
    
@bot.command(name="create_event_plan")
@commands.check(check_manage_roles)
async def create_event_plan(
    ctx,
    name: str,
    role: discord.Role,
    channel: discord.TextChannel,
    duration_minutes: int,
    start_date: str, # Format YYYY-MM-DD
    start_time_str: str, # Format HH:MM
    participant_term: str,
    max_participants: int = EVENTS_MAX_PARTICIPANTS
):
    """
    Crée un événement planifié.
    Syntaxe: !create_event_plan "Nom de l'événement" @Rôle #Salon Durée(min) YYYY-MM-DD HH:MM Terme
    """
    event_id, _ = get_event_by_name(name)
    if event_id:
        await send_retro_message(ctx, f"Erreur: Un événement nommé **{name}** existe déjà. Veuillez en choisir un autre.")
        return

    try:
        start_datetime = datetime.datetime.strptime(f"{start_date} {start_time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        await send_retro_message(ctx, "Erreur: Format de date/heure invalide. Utilisez `YYYY-MM-DD` et `HH:MM`.")
        return

    if start_datetime < datetime.datetime.now():
        await send_retro_message(ctx, "Erreur: L'heure de début doit être dans le futur.")
        return

    end_time = start_datetime + datetime.timedelta(minutes=duration_minutes)

    event_id = uuid.uuid4()
    active_events[event_id] = {
        'name': name,
        'type': 'planifié',
        'message': None,
        'channel': channel,
        'role': role,
        'participants': {},
        'start_time': start_datetime,
        'end_time': end_time,
        'participant_term': participant_term,
        'running_task': None,
        'start_scheduled': True,
        'max_participants': max_participants,
    }

    view = EventView(event_id)
    
    await update_event_embed(active_events[event_id])

    message = await ctx.send(f"**@everyone** Un événement a été planifié : **{name}** pour le {start_datetime.strftime('%Y-%m-%d à %H:%M')} !", embed=None, view=view)
    active_events[event_id]['message'] = message
    
    await send_retro_message(ctx, f"Événement **{name}** planifié avec succès.", delay=30)

@bot.command(name="ende_event")
@commands.check(check_manage_roles)
async def end_event_now(ctx, name: str):
    """
    Termine un événement immédiat en cours.
    Syntaxe: !ende_event "Nom de l'événement"
    """
    event_id, event_data = get_event_by_name(name)
    if not event_id or event_data['type'] != 'immédiat':
        await send_retro_message(ctx, f"Erreur: L'événement **{name}** n'existe pas ou n'est pas un événement immédiat.")
        return
        
    await end_event_logic(event_id)
    await send_retro_message(ctx, f"Événement **{name}** terminé avec succès.", delay=30)

@bot.command(name="ende_event_plan")
@commands.check(check_manage_roles)
async def end_event_plan_now(ctx, name: str):
    """
    Termine un événement planifié en cours.
    Syntaxe: !ende_event_plan "Nom de l'événement"
    """
    event_id, event_data = get_event_by_name(name)
    if not event_id or event_data['type'] != 'planifié':
        await send_retro_message(ctx, f"Erreur: L'événement **{name}** n'existe pas ou n'est pas un événement planifié.")
        return
    
    await end_event_logic(event_id)
    await send_retro_message(ctx, f"Événement **{name}** planifié terminé avec succès.", delay=30)
    
@bot.command(name="list_events")
async def list_events(ctx):
    """
    Affiche la liste des événements actifs.
    Syntaxe: !list_events
    """
    if not active_events:
        await send_retro_message(ctx, "Il n'y a aucun événement actif pour le moment.")
        return
        
    fields = []
    for event_id, event in active_events.items():
        fields.append((
            f"Nom de l'événement",
            f"Type: {event['type']}\n"
            f"Rôle: {event['role'].mention}\n"
            f"Salon: {event['channel'].mention}\n"
            f"Participants: {len(event['participants'])} / {event['max_participants']}\n"
            f"Heure de début: {event['start_time'].strftime('%Y-%m-%d %H:%M')}\n"
            f"Heure de fin: {event['end_time'].strftime('%Y-%m-%d %H:%M')}"
        ))
    
    embed = create_retro_embed("Liste des événements actifs", fields=fields)
    await ctx.send(embed=embed)

@bot.command(name="helpoxel")
async def helpoxel(ctx):
    """
    Affiche le manuel de Poxel.
    """
    help_text = (
        "**Manuel de Poxel**\n\n"
        "Voici la liste des commandes disponibles :\n"
        "`!helpoxel`: Affiche ce manuel.\n"
        "`!list_events`: Affiche les événements en cours.\n"
        "`!create_event`: Crée un événement immédiat.\n"
        "`!create_event_plan`: Crée un événement planifié.\n"
        "`!ende_event`: Termine un événement immédiat en cours.\n"
        "`!ende_event_plan`: Termine un événement planifié en cours.\n\n"
        "Pour plus de détails sur une commande, utilisez par exemple `!help_create_event`."
    )
    await send_retro_message(ctx, help_text, delay=60)
    
@bot.command(name="help_create_event")
async def help_create_event(ctx):
    """
    Manuel pour la commande !create_event.
    """
    help_text = (
        "**Manuel de Poxel : `!create_event`**\n\n"
        "Cette commande permet de créer un événement qui commencera sous peu.\n\n"
        "**Syntaxe :**\n"
        "`!create_event \"Nom de l'événement\" @Rôle #Salon Durée(min) Début(min) Terme [Max_participants]`\n\n"
        "**Exemple :**\n"
        "`!create_event \"Chasse au trésor\" @Explorateurs #salle-d-attente 60 5 aventuriers`\n"
        "L'événement 'Chasse au trésor' commencera dans 5 minutes, durera 60 minutes. Les participants auront le rôle @Explorateurs et seront appelés 'aventuriers'. Le salon d'attente est #salle-d-attente. Le nombre de participants est 10 par défaut."
    )
    await send_retro_message(ctx, help_text, delay=60)
    
@bot.command(name="help_create_event_plan")
async def help_create_event_plan(ctx):
    """
    Manuel pour la commande !create_event_plan.
    """
    help_text = (
        "**Manuel de Poxel : `!create_event_plan`**\n\n"
        "Cette commande permet de créer un événement qui commencera à une date et une heure précises.\n\n"
        "**Syntaxe :**\n"
        "`!create_event_plan \"Nom de l'événement\" @Rôle #Salon Durée(min) YYYY-MM-DD HH:MM Terme [Max_participants]`\n\n"
        "**Exemple :**\n"
        "`!create_event_plan \"Tournoi de l'épée\" @Chevaliers #salle-d-armes 90 2025-12-25 20:00 combattants`\n"
        "L'événement 'Tournoi de l'épée' commencera le 25 décembre 2025 à 20h00 et durera 90 minutes. Les participants auront le rôle @Chevaliers et seront appelés 'combattants'. Le salon d'attente est #salle-d-armes. Le nombre de participants est 10 par défaut."
    )
    await send_retro_message(ctx, help_text, delay=60)
    
@bot.event
async def on_ready():
    """
    Événement déclenché lorsque le bot est prêt.
    """
    print(f"Poxel est en ligne en tant que {bot.user.name} (ID: {bot.user.id})")
    # Lancer le serveur Flask dans un thread séparé
    threading.Thread(target=run_flask_app).start()
    event_countdown_task.start()
    
@bot.event
async def on_command_error(ctx, error):
    """
    Gère les erreurs de commande.
    """
    if isinstance(error, commands.MissingRequiredArgument):
        await send_retro_message(ctx, f"Erreur: Il manque un argument. Utilisez `!helpoxel` pour voir la syntaxe des commandes.", delay=30)
    elif isinstance(error, commands.MissingPermissions):
        await send_retro_message(ctx, f"Erreur: Vous n'avez pas la permission de `Gérer les rôles` pour utiliser cette commande.", delay=30)
    else:
        await send_retro_message(ctx, f"Une erreur s'est produite: {error}", delay=30)
        print(f"Erreur de commande: {error}")

bot.run(TOKEN)
