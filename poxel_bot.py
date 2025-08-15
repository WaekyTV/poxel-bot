# coding=utf-8
import os
import discord
import asyncio
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, firestore
from discord.ui import Button, View, Modal
from discord.ext import commands
import threading
from flask import Flask

# --- Configuration et Initialisation ---
# Vous devez remplacer ces valeurs par les vôtres.
# Le token de votre bot Discord. Il est recommandé d'utiliser une variable d'environnement.
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "VOTRE_TOKEN_ICI")
# Les identifiants de Firebase. Il est recommandé de charger cela à partir d'un fichier JSON sécurisé.
FIREBASE_CREDENTIALS_PATH = "path/to/votre_firebase_credentials.json"
# Le GIF pour l'embed rétro.
RETRO_GIF_URL = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3h2aDVkYnF5M3Q3em5tMTh6bTlwZm56d3QyM3gyY29sOGE5ZnN1MyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3ornjQM7zD1yI2B7eY/giphy.gif"

# Initialisation de Flask
app = Flask(__name__)

@app.route('/')
def home():
    """Route de base pour le health check de Render."""
    return "Poxel est en ligne et fonctionne !"

# Fonction pour exécuter l'application Flask
def run_flask_app():
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    print(f"Flask server running on port {port}")

# Initialisation de Firebase (commenté pour un fonctionnement sans Firebase, mais vous devrez le décommenter)
# try:
#     cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
#     firebase_admin.initialize_app(cred)
#     db = firestore.client()
#     print("Firebase initialisé.")
# except FileNotFoundError:
#     print("Fichier de credentials Firebase non trouvé. Le bot fonctionnera avec une base de données en mémoire.")
#     db = None

# Création d'un client Discord avec toutes les intentions
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Base de données en mémoire pour les événements. Simule le stockage Firebase.
events = {}

# --- Fonctions Utilitaires ---

def get_current_time_paris():
    """Retourne l'heure actuelle au format UTC pour la gestion des fuseaux horaires."""
    return datetime.now(timezone.utc)

def format_duration(td):
    """Formate un objet timedelta en chaîne de caractères lisible."""
    seconds = int(td.total_seconds())
    periods = [
        ('jours', 60*60*24),
        ('heures', 60*60),
        ('minutes', 60),
        ('secondes', 1)
    ]
    parts = []
    for period_name, period_seconds in periods:
        if seconds > period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            parts.append(f"{period_value} {period_name}")
    return ", ".join(parts) if parts else "0 secondes"

async def update_event_embed(event_name):
    """
    Tâche en arrière-plan pour mettre à jour l'embed de l'événement en temps réel.
    """
    event = events.get(event_name)
    if not event:
        return

    while event['active']:
        now = get_current_time_paris()
        # Le bot se met en veille pour une microseconde, comme demandé.
        # En pratique, une mise à jour par seconde est plus raisonnable pour l'API Discord.
        await asyncio.sleep(1)

        event = events.get(event_name)
        if not event or not event['active']:
            break

        participants_list = "\n".join(
            [f"• {p['pseudo']} ({bot.get_user(p['id'])})" for p in event['participants']]
        ) or "Aucun participant pour le moment."

        description_text = ""
        footer_text = ""
        color = 0x027afa # Couleur néon bleu

        # Temps restant avant l'événement
        if now < event['start_time']:
            time_left = event['start_time'] - now
            if time_left.total_seconds() > 0:
                description_text = f"**Début dans :** {format_duration(time_left)}\n"
                footer_text = f"Inscriptions : {len(event['participants'])}/{event['max_participants']}"
        # L'événement est en cours
        elif now < event['end_time']:
            time_left = event['end_time'] - now
            if time_left.total_seconds() > 0:
                description_text = f"**Fin dans :** {format_duration(time_left)}\n"
                footer_text = f"Participants : {len(event['participants'])}"
                color = 0x6441a5 # Couleur néon violet
        # L'événement est terminé
        else:
            time_since_end = now - event['end_time']
            description_text = f"**Statut :** FINI IL Y A {format_duration(time_since_end)}\n"
            footer_text = f"Participants : {len(event['participants'])}"
            event['active'] = False # Désactiver la mise à jour
            color = 0x6441a5

        embed = discord.Embed(
            title=f"NEW EVENT: {event_name}",
            description=description_text,
            color=color
        )
        embed.set_thumbnail(url=RETRO_GIF_URL)
        embed.add_field(name="Participants", value=participants_list, inline=False)
        embed.set_footer(text=footer_text)
        
        try:
            message = await event['announcement_channel'].fetch_message(event['announcement_message_id'])
            await message.edit(embed=embed, view=event['view'])
        except discord.NotFound:
            print(f"Le message pour l'événement {event_name} a été supprimé. Arrêt de la mise à jour.")
            event['active'] = False

# --- Classes de l'Interface Utilisateur ---

class InscriptionModal(Modal, title="Inscription"):
    """
    Fenêtre modale pour demander le pseudonyme du participant.
    """
    pseudo = discord.ui.TextInput(
        label="Votre pseudonyme en jeu",
        placeholder="Ex: Poxel",
        min_length=1,
        max_length=32
    )

    def __init__(self, event_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_name = event_name

    async def on_submit(self, interaction: discord.Interaction):
        event = events.get(self.event_name)
        if not event:
            await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            return

        pseudo = self.pseudo.value
        user = interaction.user
        
        # Vérifier si l'utilisateur est déjà inscrit
        if any(p['id'] == user.id for p in event['participants']):
             await interaction.response.send_message("Vous êtes déjà inscrit !", ephemeral=True)
             return

        # Gérer la logique d'inscription
        event['participants'].append({
            'id': user.id,
            'pseudo': pseudo
        })

        if len(event['participants']) >= event['max_participants']:
            event['view'].get_item(label="START").disabled = True
            event['view'].get_item(label="START").label = "INSCRIPTION CLOS"
            await event['announcement_channel'].send(f"@everyone Les inscriptions pour l'événement '{self.event_name}' sont closes !")

        await interaction.response.send_message(f"Vous êtes inscrit à l'événement '{self.event_name}' avec le pseudonyme **{pseudo}** !", ephemeral=True)

class EventView(View):
    """
    Vue contenant les boutons pour les interactions avec l'événement.
    """
    def __init__(self, event_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_name = event_name
        
        # Bouton START
        start_button = Button(label="START", style=discord.ButtonStyle.green)
        start_button.callback = self.start_callback
        self.add_item(start_button)

        # Bouton QUIT
        quit_button = Button(label="QUIT", style=discord.ButtonStyle.red)
        quit_button.callback = self.quit_callback
        self.add_item(quit_button)
        
        # Bouton MENU (pour l'instant, c'est juste un placeholder)
        menu_button = Button(label="MENU", style=discord.ButtonStyle.secondary)
        menu_button.callback = self.menu_callback
        self.add_item(menu_button)

    async def start_callback(self, interaction: discord.Interaction):
        """
        Gère le clic sur le bouton START. Ouvre la modal d'inscription.
        """
        modal = InscriptionModal(self.event_name)
        await interaction.response.send_modal(modal)

    async def quit_callback(self, interaction: discord.Interaction):
        """
        Gère le clic sur le bouton QUIT.
        """
        event = events.get(self.event_name)
        if not event:
            await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            return

        # Supprimer le participant de la liste
        original_participants_count = len(event['participants'])
        event['participants'] = [p for p in event['participants'] if p['id'] != interaction.user.id]
        
        if len(event['participants']) < original_participants_count:
            # Réouverture des inscriptions si la limite était atteinte
            if len(event['participants']) < event['max_participants'] and self.get_item(label="START").disabled:
                self.get_item(label="START").disabled = False
                self.get_item(label="START").label = "START"
                await event['announcement_channel'].send(f"@everyone Les inscriptions pour l'événement '{self.event_name}' sont réouvertes !")
            
            await interaction.response.send_message(f"Vous vous êtes désisté de l'événement '{self.event_name}'.", ephemeral=True)
        else:
            await interaction.response.send_message("Vous n'étiez pas inscrit à cet événement.", ephemeral=True)


    async def menu_callback(self, interaction: discord.Interaction):
        """
        Gère le clic sur le bouton MENU. Affiche la liste des événements actifs.
        """
        active_events = [f"• {name}" for name in events.keys()]
        message = "\n".join(active_events) or "Aucun événement actif pour le moment."
        await interaction.response.send_message(f"**Événements actifs :**\n{message}", ephemeral=True)

# --- Commandes du Bot ---

@bot.event
async def on_ready():
    """
    Action à l'initialisation du bot.
    """
    print(f"{bot.user} est en ligne !")
    # Lancement des tâches de mise à jour pour les événements existants
    for name, event in events.items():
        if event['active']:
            bot.loop.create_task(update_event_embed(name))


@bot.command(name="create_event", description="Crée un événement en temps réel.")
async def create_event(ctx, heure_debut: str, duree: str, role: discord.Role, salon_annonce: discord.TextChannel, salon_attente: discord.TextChannel, max_participants: int, nom_event: str):
    """
    !create_event [heure de début (HH:MM)] [durée (HH:MM:SS)] @[rôle] #[salon d'annonce] #[salon d'attente] [nombre de participants] "[nom de l'event]"
    """
    try:
        # Parsing de l'heure et de la durée
        start_time_str = f"{datetime.now().date()} {heure_debut}"
        start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
        
        duration_parts = [int(p) for p in duree.split(':')]
        duration_delta = timedelta(hours=duration_parts[0], minutes=duration_parts[1], seconds=duration_parts[2])
        end_time = start_time + duration_delta

        now = get_current_time_paris().replace(tzinfo=None) # Utiliser un fuseau horaire neutre pour la comparaison
        
        if start_time < now:
            await ctx.send("Erreur : l'heure de début doit être ultérieure à l'heure actuelle.", ephemeral=True)
            return

    except (ValueError, IndexError):
        await ctx.send("Erreur de format. Exemple : `!create_event 15:30 01:30:00 @Role #annonces #attente 10 \"Mon événement\"`", ephemeral=True)
        return

    # Vérifier si l'événement existe déjà
    if nom_event in events:
        await ctx.send(f"Erreur : Un événement avec le nom '{nom_event}' existe déjà.", ephemeral=True)
        return

    # Création de l'embed
    embed = discord.Embed(
        title=f"NEW EVENT: {nom_event}",
        description=f"Un nouvel événement a été créé ! Soyez les premiers à vous inscrire !",
        color=0x027afa
    )
    embed.set_thumbnail(url=RETRO_GIF_URL)
    embed.add_field(name="Détails", value=f"Heure de début : `{start_time.strftime('%H:%M')}`\nDurée : `{duree}`\nSalon d'attente : {salon_attente.mention}\nRôle requis : {role.mention}\nParticipants max : `{max_participants}`", inline=False)
    embed.set_footer(text=f"Inscriptions : 0/{max_participants}")

    # Création des boutons et envoi du message
    view = EventView(nom_event, timeout=None)
    announcement_message = await salon_annonce.send(content="@everyone", embed=embed, view=view)
    
    # Stockage des informations de l'événement
    events[nom_event] = {
        'name': nom_event,
        'start_time': start_time.replace(tzinfo=timezone.utc),
        'end_time': end_time.replace(tzinfo=timezone.utc),
        'role': role,
        'announcement_channel': salon_annonce,
        'announcement_message_id': announcement_message.id,
        'waiting_channel': salon_attente,
        'max_participants': max_participants,
        'participants': [],
        'active': True,
        'view': view
    }

    # Lancement de la tâche de mise à jour en arrière-plan
    bot.loop.create_task(update_event_embed(nom_event))
    await ctx.send(f"L'événement '{nom_event}' a été créé avec succès !", ephemeral=True)


@bot.command(name="end_event", description="Ferme un événement manuellement.")
async def end_event(ctx, nom_event: str):
    """
    !end_event "[nom de l'event]"
    """
    event = events.get(nom_event)
    if not event:
        await ctx.send(f"Erreur : L'événement '{nom_event}' n'existe pas.", ephemeral=True)
        return
    
    event['active'] = False
    
    try:
        # Enlever les rôles aux participants et supprimer l'embed
        message = await event['announcement_channel'].fetch_message(event['announcement_message_id'])
        await message.delete()

        # Envoi du message de remerciement
        await event['announcement_channel'].send(f"@everyone L'événement '{nom_event}' est maintenant terminé. Merci à tous les participants !")

    except discord.NotFound:
        print(f"Le message d'annonce pour l'événement {nom_event} a déjà été supprimé.")
    
    # Retrait de l'événement de la base de données
    del events[nom_event]

    await ctx.send(f"L'événement '{nom_event}' a été clôturé.", ephemeral=True)
    
@bot.command(name="helpoxel", description="Affiche les commandes d'aide.")
async def helpoxel(ctx, commande: str = None):
    """
    !helpoxel ou !helpoxel [commande]
    """
    if commande:
        # Affiche l'aide pour une commande spécifique
        help_text = "Détails de la commande..." # À personnaliser
        await ctx.send(help_text, ephemeral=True)
    else:
        # Affiche un embed avec la liste des commandes
        embed = discord.Embed(
            title="MANUEL DE POXEL",
            description="Liste des commandes disponibles pour le bot Poxel.",
            color=0x027afa
        )
        embed.add_field(name="!create_event", value="Crée un événement en temps réel.", inline=False)
        embed.add_field(name="!end_event", value="Ferme un événement manuellement.", inline=False)
        embed.add_field(name="!helpoxel", value="Affiche ce manuel.", inline=False)
        # Vous pouvez ajouter d'autres commandes ici
        await ctx.send(embed=embed, ephemeral=True)

# Lancer l'application Flask dans un thread séparé
flask_thread = threading.Thread(target=run_flask_app)
flask_thread.daemon = True # Le thread se termine lorsque le programme principal se termine
flask_thread.start()

# Exécuter le bot
# Assurez-vous que le token est correctement configuré.
bot.run(DISCORD_BOT_TOKEN)
