# Fichier: bot.py

import os
import asyncio
from datetime import datetime, timedelta
import pytz
import random

import discord
from discord.ext import commands, tasks
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask

# --- Initialisation de Firebase et du bot ---
# 1. Obtenez les identifiants de votre compte de service Firebase.
#    - Allez dans la console Firebase -> Paramètres du projet -> Comptes de service.
#    - Générez une nouvelle clé privée et téléchargez le fichier JSON.
# 2. Sauvegardez le contenu du fichier JSON dans une variable d'environnement sur Render.
#    Appelez la variable FIREBASE_SERVICE_ACCOUNT_KEY_JSON.
#    Pour cela, copiez le contenu du JSON, puis définissez la variable d'environnement avec cette valeur.

# Vérifie si la variable d'environnement existe
firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY_JSON')
if firebase_creds_json:
    # Sauvegarde temporairement les identifiants dans un fichier pour firebase_admin
    with open('firebase_creds.json', 'w') as f:
        f.write(firebase_creds_json)

    # Initialise l'application Firebase
    cred = credentials.Certificate('firebase_creds.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase a été initialisé avec succès.")
else:
    print("Erreur: La variable d'environnement 'FIREBASE_SERVICE_ACCOUNT_KEY_JSON' n'est pas définie.")
    print("Le bot ne pourra pas se connecter à Firebase.")
    db = None

# Configure l'intention du bot pour les membres, les messages et les réactions
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Initialise le bot avec le préfixe de commande '!'
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Dictionnaire pour stocker les informations d'aide sur les commandes ---
# Ceci facilite la gestion de la commande !helpoxel
COMMANDS_HELP = {
    'helpoxel': {
        'description': "Affiche les commandes disponibles ou l'aide pour une commande spécifique.",
        'syntax': "!helpoxel [nom_de_la_commande]",
        'example': "!helpoxel create_event"
    },
    'create_event': {
        'description': "Crée un nouvel événement et ajoute des participants si nécessaire.",
        'syntax': "!create_event <heure_début> <durée> <@rôle> <#salon_annonce> <#salle_attente> <limite_participants> <nom_participants> <description>",
        'example': "!create_event 20:00 2h30m @Participants #annonces #salle-attente 10 10 pixels Soirée Gaming!"
    },
    'create_event_plan': {
        'description': "Crée un événement planifié pour une date et une heure futures, et ajoute des participants si nécessaire.",
        'syntax': "!create_event_plan <date> <heure_début> <durée> <@rôle> <#salon_annonce> <#salle_attente> <limite_participants> <nom_participants> <description>",
        'example': "!create_event_plan 2025-12-25 20:00 2h30m @Participants #annonces #salle-attente 10 10 pixels Soirée de Noël"
    },
    'list_events': {
        'description': "Affiche la liste de tous les événements actifs.",
        'syntax': "!list_events",
        'example': "!list_events"
    },
    'end_event': {
        'description': "Termine manuellement un événement et supprime les rôles. Fonctionne pour les événements immédiats, planifiés et les concours.",
        'syntax': "!end_event <ID_de_l'événement>",
        'example': "!end_event 123456789012345678"
    },
    'create_contest': {
        'description': "Crée un concours avec une date limite et un prix à gagner.",
        'syntax': "!create_contest <date_limite> <heure_limite> <limite_participants> <#salon_annonce> <titre_event> <prix>",
        'example': "!create_contest 2025-12-25 20:00 100 #annonces Gagnez un jeu! Jeu vidéo"
    },
    'raffle_event': {
        'description': "Effectue un tirage au sort parmi les participants d'un événement ou d'un concours et annonce un gagnant.",
        'syntax': "!raffle_event <ID_de_l'événement>",
        'example': "!raffle_event 123456789012345678"
    },
    'test_permissions': {
        'description': "Vérifie si vous avez les permissions nécessaires pour créer des événements.",
        'syntax': "!test_permissions",
        'example': "!test_permissions"
    }
}

# --- Serveur Flask pour le ping Uptime Robot ---
# Ceci est nécessaire pour que Render garde le bot en vie.
app = Flask(__name__)

@app.route('/')
def home():
    """Un simple endpoint pour que le robot Uptime puisse pinguer."""
    return "Le bot Discord est en vie !"
    
# URL d'un GIF d'animation 8-bit pour les embeds
PIXEL_ART_GIF_URL = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExd3N0ZDR2eWdzNnIzbWk0djZicTNrZTRtb3VkYjE0bW9yMnR0ZGg3ayZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/kFfMhJ5wM5uG7hD12A/giphy.gif"

# Liste pour le nettoyage automatique des messages
messages_to_clean = []
# Délai en secondes avant de supprimer un message
CLEANUP_DELAY_SECONDS = 120 # 2 minutes

# --- Fonctions utilitaires ---
def parse_duration(duration_str):
    """
    Analyse une chaîne de temps (ex: '1h30m15s') et la convertit en timedelta.
    Retourne un objet timedelta ou None en cas d'erreur.
    """
    total_seconds = 0
    current_number = ""
    for char in duration_str:
        if char.isdigit():
            current_number += char
        else:
            if current_number:
                value = int(current_number)
                if char == 'h':
                    total_seconds += value * 3600
                elif char == 'm':
                    total_seconds += value * 60
                elif char == 's':
                    total_seconds += value
                current_number = ""
    return timedelta(seconds=total_seconds) if total_seconds > 0 else None

def parse_time(time_str):
    """
    Analyse une chaîne d'heure (ex: 'HH:MM') et la combine avec la date du jour.
    """
    try:
        now = datetime.now(pytz.utc)
        time_parts = datetime.strptime(time_str, '%H:%M').time()
        event_time = now.replace(hour=time_parts.hour, minute=time_parts.minute, second=0, microsecond=0)
        # Si l'heure est déjà passée aujourd'hui, on reporte l'événement au lendemain
        if event_time < now:
            event_time += timedelta(days=1)
        return event_time
    except ValueError:
        return None

def format_timedelta(td):
    """Formate un timedelta en une chaîne lisible."""
    if td.total_seconds() < 0:
        td = abs(td)
        prefix = "FINI IL Y A : "
    else:
        prefix = "DEMARRE DANS : "
    
    hours, remainder = divmod(int(td.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}H")
    if minutes > 0:
        parts.append(f"{minutes}M")
    if seconds > 0:
        parts.append(f"{seconds}S")
    
    return prefix + " ".join(parts) if parts else "MAINTENANT !"

async def update_event_message(event_data, view_to_remove=False):
    """
    Met à jour le message d'embed de l'événement avec un style 8-bit.
    Si view_to_remove est True, les boutons sont retirés.
    """
    guild = bot.get_guild(int(event_data['guild_id']))
    if not guild: return
    
    channel = guild.get_channel(int(event_data['announcement_channel_id']))
    if not channel: return

    try:
        message = await channel.fetch_message(int(event_data['message_id']))
    except discord.NotFound:
        print(f"Message de l'événement {event_data['message_id']} non trouvé, impossible de mettre à jour.")
        return

    now = datetime.now(pytz.utc)
    
    # Gestion du cas où l'événement est terminé ou annulé
    if view_to_remove:
        embed_title = f"**{event_data['event_title']}**"
        
        # Cas d'un concours terminé
        if event_data.get('type') == 'contest':
            embed_title = f"**GAME OVER | CONCOURS TERMINE**"
            embed = discord.Embed(
                title=embed_title,
                description="Le concours est terminé. Merci aux joueurs !",
                color=discord.Color.dark_grey()
            )
            winner_id = event_data.get('winner_id')
            if winner_id:
                embed.add_field(name="WINNER", value=f"<@{winner_id}>", inline=True)
            else:
                embed.add_field(name="RESULTAT", value="AUCUN GAGNANT TIRE.", inline=True)
        # Cas d'un événement terminé
        elif now >= event_data['end_time'].replace(tzinfo=pytz.utc):
            embed_title = f"**GAME OVER | EVENEMENT TERMINE**"
            embed = discord.Embed(
                title=embed_title,
                description="L'événement est terminé. Merci aux participants !",
                color=discord.Color.dark_grey()
            )
        else: # Cas d'annulation
            embed_title = f"**EVENEMENT ANNULE**"
            embed = discord.Embed(
                title=embed_title,
                description="Annulé. Pas assez de participants.",
                color=discord.Color.red()
            )
        
        embed.add_field(name="JOUEURS", value=f"{len(event_data['participants'])}/{event_data['participant_limit']}", inline=True)
        await message.edit(embed=embed, view=None)
        return
        
    # Cas normal, l'événement/concours est en cours ou à venir
    # Utilisation des couleurs rétro-futuristes néon
    if event_data.get('type') == 'contest':
        embed_color = discord.Color(0x027afa)  # Bleu néon pour les concours
        embed_title = f"**NOUVEAU JEU ! CONCOURS :** {event_data['event_title'].upper()}"
    else:
        embed_color = discord.Color(0x6441a5)  # Violet pour les événements
        embed_title = f"**NOUVELLE PARTIE ! EVENEMENT :** {event_data['event_title'].upper()}"
    
    embed = discord.Embed(
        title=embed_title,
        description="",
        color=embed_color
    )
    
    # --- AJOUT DU GIF ---
    embed.set_image(url=PIXEL_ART_GIF_URL)
    
    # Logique pour les concours
    if event_data.get('type') == 'contest':
        embed.description = (
            f"**PRIX :** {event_data.get('prize', 'NON SPECIFIE')}\n"
            f"CLIQUEZ SUR LE BOUTON POUR VOUS INSCRIRE !"
        )
        
        deadline_time = event_data['deadline_time'].replace(tzinfo=pytz.utc)
        if now < deadline_time:
            embed.add_field(name="FIN DU CONCOURS DANS", value=format_timedelta(deadline_time - now), inline=True)
        else:
            embed.add_field(name="CONCOURS TERMINE IL Y A", value=format_timedelta(now - deadline_time), inline=True)
            embed.color = discord.Color.dark_grey()
    
    # Logique pour les événements
    else:
        start_time = event_data['start_time'].replace(tzinfo=pytz.utc)
        end_time = event_data['end_time'].replace(tzinfo=pytz.utc)
        embed.description = (
            f"BIENVENUE JOUEUR !\n"
            f"ROLE ATTRIBUE AU DEMARRAGE : <@&{event_data['role_id']}>\n"
            f"POINT DE RALLIEMENT : <#{event_data['waiting_room_channel_id']}>\n"
            f"DEPLACEMENT AUTOMATIQUE A L'HEURE DE DEBUT !\n"
            f"PARTICIPANTS REQUIS : {event_data.get('participant_group_name', 'NON SPECIFIE').upper()}"
        )
    
        if now < start_time:
            embed.add_field(name="DEMARRAGE DANS", value=format_timedelta(start_time - now), inline=True)
        elif now < end_time:
            embed.add_field(name="FIN DANS", value=format_timedelta(end_time - now), inline=True)
        else:
            embed.add_field(name="TERMINE IL Y A", value=format_timedelta(now - end_time), inline=True)
            embed.color = discord.Color.dark_grey()
        
    embed.add_field(name="JOUEURS", value=f"{len(event_data['participants'])}/{event_data['participant_limit']}", inline=True)
    
    # Afficher la liste des participants avec leurs pseudos
    participant_mentions = []
    for uid, nickname in event_data['participants'].items():
        if nickname:
            participant_mentions.append(f"<@{uid}> ({nickname})")
        else:
            participant_mentions.append(f"<@{uid}>")
            
    embed.add_field(name="LISTE DES JOUEURS", value=", ".join(participant_mentions) if participant_mentions else "AUCUN JOUEUR INSCRIT", inline=False)
    
    # Crée une nouvelle view pour mettre à jour les boutons
    new_view = EventButtonsView(event_id=event_data['message_id'], event_data=event_data)
    
    await message.edit(embed=embed, view=new_view)

# --- Classes pour les boutons interactifs et la modale ---

class GameNameModal(discord.ui.Modal):
    """Modale pour demander le pseudo en jeu du participant, avec un style 8-bit."""
    def __init__(self, event_id: str, event_data: dict, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.event_id = event_id
        self.event_data = event_data
        
        # Ajout du champ de texte pour le pseudo
        self.add_item(discord.ui.TextInput(
            label="PSEUDO JEU",
            placeholder="ENTREZ VOTRE PSEUDO (LAISSER VIDE SI NON APPLICABLE)",
            required=False,
            max_length=50
        ))

    async def on_submit(self, interaction: discord.Interaction):
        """
        Gère la soumission de la modale.
        Ajoute le participant et son pseudo (si fourni) à l'événement.
        """
        member = interaction.user
        game_nickname = self.children[0].value.strip()

        doc_ref = db.collection('events').document(self.event_id)
        doc = doc_ref.get()
        data = doc.to_dict()

        if str(member.id) in data['participants']:
            await interaction.response.send_message(f"VOUS ETES DEJA INSCRIT A CETTE PARTIE.", ephemeral=True)
            return

        # Vérifie si le nombre de participants est sur le point d'atteindre la limite
        is_about_to_be_full = len(data['participants']) + 1 >= data['participant_limit']
        
        if len(data['participants']) >= data['participant_limit']:
            await interaction.response.send_message(f"DESOLE, LA SALLE DE JEUX EST COMPLETE.", ephemeral=True)
            return
        
        # Ajoute le participant et son pseudo à la liste dans Firebase
        data['participants'][str(member.id)] = game_nickname
        doc_ref.update({'participants': data['participants']})
        
        # Met à jour le message d'embed et la view
        await update_event_message(data)
        
        message_to_user = (
            f"BIENVENUE DANS LA PARTIE **{data['event_title'].upper()}** !\n"
            f"VOTRE PSEUDO '{game_nickname.upper()}' EST ENREGISTRE."
        ) if game_nickname else (
            f"BIENVENUE DANS LA PARTIE **{data['event_title'].upper()}** !"
        )

        await interaction.response.send_message(message_to_user, ephemeral=True)
        
        # Si le nombre de participants atteint la limite, envoie une notification
        if is_about_to_be_full:
            announcement_channel = bot.get_channel(int(data['announcement_channel_id']))
            await announcement_channel.send(f"@everyone | **SALLE DE JEU COMPLETE** pour l'événement **{data['event_title'].upper()}**")


class EventButtonsView(discord.ui.View):
    def __init__(self, event_id: str, event_data: dict):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.event_data = event_data
        
        # Logique pour désactiver le bouton si l'inscription est fermée
        is_full = len(event_data['participants']) >= event_data['participant_limit']
        
        # Les concours n'ont pas de rôle, on adapte donc le texte du bouton
        button_label = "start" if not is_full else "COMPLET"

        join_button = discord.ui.Button(
            label=button_label,
            style=discord.ButtonStyle.red if is_full else discord.ButtonStyle.green,
            emoji="🕹️" if not is_full else "⛔",
            custom_id="join_event",
            disabled=is_full
        )
        self.add_item(join_button)
        
        leave_button = discord.ui.Button(
            label="quit",
            style=discord.ButtonStyle.red,
            emoji="🚪",
            custom_id="leave_event",
            disabled=False
        )
        self.add_item(leave_button)

    @discord.ui.button(custom_id="join_event")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback pour le bouton 'Start' qui ouvre une modale."""
        member = interaction.user
        doc_ref = db.collection('events').document(self.event_id)
        doc = doc_ref.get()
        data = doc.to_dict()
        
        if str(member.id) in data['participants']:
            await interaction.response.send_message(f"VOUS ETES DEJA INSCRIT.", ephemeral=True)
            return

        # Vérifie si le nombre de participants est sur le point d'atteindre la limite
        is_about_to_be_full = len(data['participants']) + 1 >= data['participant_limit']
        
        if len(data['participants']) >= data['participant_limit']:
            await interaction.response.send_message(f"DESOLE, LA SALLE DE JEUX EST COMPLETE.", ephemeral=True)
            return

        # Ajoute le participant sans pseudo pour les concours
        if data.get('type') == 'contest':
            data['participants'][str(member.id)] = ""
            doc_ref.update({'participants': data['participants']})
            await interaction.response.send_message(f"VOUS AVEZ REJOINT LE CONCOURS !", ephemeral=True)
        else:
            # Envoie la modale pour demander le pseudo en jeu pour les événements
            modal = GameNameModal(title="ENTREZ VOTRE PSEUDO", event_id=self.event_id, event_data=self.event_data)
            await interaction.response.send_modal(modal)

        await update_event_message(data)

    @discord.ui.button(custom_id="leave_event")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback pour le bouton 'Quit'."""
        member = interaction.user
        doc_ref = db.collection('events').document(self.event_id)
        doc = doc_ref.get()
        data = doc.to_dict()
        
        if str(member.id) not in data['participants']:
            await interaction.response.send_message(f"VOUS N'ETES PAS INSCRIT A CETTE PARTIE.", ephemeral=True)
            return
            
        # Vérifie si la liste était pleine avant que le participant ne parte
        was_full = len(data['participants']) == data['participant_limit']
        
        # Supprime le participant de la liste dans Firebase
        del data['participants'][str(member.id)]
        doc_ref.update({'participants': data['participants']})

        # Retire le rôle si l'événement a déjà commencé
        if data.get('has_started', False):
            role = interaction.guild.get_role(int(data['role_id']))
            if role:
                await member.remove_roles(role)
            
        # Met à jour le message d'embed et la view
        await update_event_message(data)
        await interaction.response.send_message(f"VOUS AVEZ QUITTER LA PARTIE.", ephemeral=True)

        # Si la liste était pleine et qu'elle a maintenant de la place, envoie une notification
        if was_full and len(data['participants']) < data['participant_limit']:
            announcement_channel = bot.get_channel(int(data['announcement_channel_id']))
            await announcement_channel.send(f"@everyone | **PLACE LIBRE** pour l'événement **{data['event_title'].upper()}** !")

# --- Événements du bot ---
@bot.event
async def on_ready():
    """Se déclenche lorsque le bot est prêt."""
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Le bot est prêt à démarrer...')
    # Démarre la tâche de vérification des événements
    if db:
        update_events_loop.start()
        cleanup_messages_loop.start()

@bot.event
async def on_command_error(ctx, error):
    """Gère les erreurs de commande et envoie un message privé à l'utilisateur."""
    print(f"Erreur de commande détectée: {error}")
    message = None
    if isinstance(error, commands.MissingPermissions):
        message = await ctx.send("ERREUR DE PERMISSIONS : Vous devez avoir la permission `Gérer les rôles` pour utiliser cette commande.")
    elif isinstance(error, commands.BadArgument):
        # Explique l'erreur et redirige l'utilisateur vers la commande d'aide
        message = await ctx.send(
            f"ERREUR DE SYNTAXE : L'un des arguments que vous avez fournis est incorrect. "
            f"Veuillez vérifier la syntaxe de la commande avec `!helpoxel {ctx.command.name}`."
        )
    elif isinstance(error, commands.CommandNotFound):
        # Ne pas envoyer de message pour les commandes non trouvées pour ne pas spammer
        return
    elif isinstance(error, discord.ext.commands.errors.CommandInvokeError) and isinstance(error.original, discord.errors.HTTPException):
        # Gestion spécifique des erreurs de formulaire
        message = await ctx.send(
            f"ERREUR D'API : Il y a un problème technique avec les données envoyées à Discord. "
            f"Le message d'erreur d'origine est: `{error.original}`. "
            f"Veuillez signaler cette erreur à un administrateur."
        )
    else:
        message = await ctx.send(f"UNE ERREUR INCONNUE S'EST PRODUITE : `{error}`. VEUILLEZ CONTACTER UN ADMINISTRATEUR.")
        
    if message:
        # Ajoute le message d'erreur à la liste pour le nettoyage
        messages_to_clean.append({
            'message': message,
            'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
        })

# --- Commandes du bot ---
@bot.command(name='helpoxel', aliases=['h'])
async def helpoxel_command(ctx, command_name: str = None):
    """
    Affiche les commandes disponibles ou l'aide pour une commande spécifique.
    """
    print(f"Commande !helpoxel reçue de {ctx.author} dans le salon {ctx.channel}.")
    if command_name:
        # Cherche de l'aide pour une commande spécifique
        command_info = COMMANDS_HELP.get(command_name.lower())
        if command_info:
            embed = discord.Embed(
                title=f"MANUEL DE POXEL | AIDE COMMANDE : !{command_name.upper()}",
                description=command_info['description'],
                color=discord.Color(0x6441a5)  # Violet néon
            )
            embed.add_field(name="SYNTAXE", value=f"`{command_info['syntax']}`", inline=False)
            embed.add_field(name="EXEMPLE", value=f"`{command_info['example']}`", inline=False)
            response = await ctx.send(embed=embed)
        else:
            response = await ctx.send(f"COMMANDE `!{command_name}` NON RECONNUE. UTILISEZ `!HELPPOXEL`.")
    else:
        # Affiche la liste de toutes les commandes
        embed = discord.Embed(
            title="MANUEL DE POXEL | LISTE DES COMMANDES",
            description="UTILISEZ `!HELPPOXEL <COMMANDE>` POUR PLUS D'INFO.",
            color=discord.Color(0x6441a5) # Violet néon
        )
        for cmd, info in COMMANDS_HELP.items():
            embed.add_field(name=f"!{cmd.upper()}", value=info['description'], inline=False)
        response = await ctx.send(embed=embed)

    # Ajoute le message à la liste pour le nettoyage
    messages_to_clean.append({
        'message': response,
        'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
    })

@bot.command(name='create_event')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, start_time_str: str, duration: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, participant_limit: int, participant_group_name: str, *, event_title: str):
    """
    Crée un nouvel événement et ajoute des participants si nécessaire.
    Syntaxe: !create_event <heure_début> <durée_event> <@rôle> <#salon_annonce> <#salle_attente> <nombre_max_participants> <nom_des_participants> <description>
    Exemple: !create_event 20:00 2h30m @Participants #annonces #salle-attente 10 10 pixels Soirée Gaming!
    """
    print(f"Commande !create_event reçue de {ctx.author} avec les arguments: {ctx.args}")
    if not db:
        await ctx.send("ERREUR SYSTEME : BASE DE DONNEES NON CONNECTEE.")
        return

    # --- NOUVEAU: Vérification de l'existence d'un événement avec le même titre ---
    async with ctx.typing():
        docs = db.collection('events').where('event_title', '==', event_title).get()
        if len(docs) > 0:
            response = await ctx.send(f"ERREUR : Un événement nommé `{event_title}` existe déjà. Veuillez utiliser un autre nom ou fermer l'événement existant avec `!end_event`.")
            messages_to_clean.append({
                'message': response,
                'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
            })
            return

    # Analyse l'heure de début et la durée
    start_time = parse_time(start_time_str)
    event_duration = parse_duration(duration)
    
    if not start_time:
        response = await ctx.send("ERREUR. FORMAT HEURE INVALIDE. UTILISEZ 'HH:MM'.")
        messages_to_clean.append({
            'message': response,
            'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
        })
        return
        
    if not event_duration:
        response = await ctx.send("ERREUR. FORMAT DUREE INVALIDE. UTILISEZ '1h30m'.")
        messages_to_clean.append({
            'message': response,
            'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
        })
        return
    
    # --- NOUVEAU : Vérification de l'heure de début ---
    now = datetime.now(pytz.utc)
    if start_time < now:
        response = await ctx.send(f"ERREUR : L'heure de début ({start_time.strftime('%H:%M')}) ne peut pas être dans le passé. Veuillez choisir une heure future.")
        messages_to_clean.append({
            'message': response,
            'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
        })
        return

    end_time = start_time + event_duration
    
    # Crée un dictionnaire pour les données de l'événement
    event_data = {
        'event_title': event_title,
        'start_time': start_time,
        'end_time': end_time,
        'role_id': str(role.id),
        'guild_id': str(ctx.guild.id),
        'announcement_channel_id': str(announcement_channel.id),
        'waiting_room_channel_id': str(waiting_room_channel.id),
        'participant_limit': participant_limit,
        'participants': {},
        'has_started': False,
        'message_id': '',
        'type': 'immediate',
        'participant_group_name': participant_group_name
    }

    # Crée un embed initial au style 8-bit
    embed_description = (
        f"BIENVENUE JOUEUR !\n"
        f"ROLE ATTRIBUE AU DEMARRAGE : {role.mention}\n"
        f"POINT DE RALLIEMENT : {waiting_room_channel.mention}\n"
        f"DEPLACEMENT AUTOMATIQUE A L'HEURE DE DEBUT !\n"
        f"PARTICIPANTS REQUIS : {participant_group_name.upper()}"
    )
    
    embed = discord.Embed(
        title=f"**NOUVELLE PARTIE ! EVENEMENT :** {event_title.upper()}",
        description=embed_description,
        color=discord.Color(0x6441a5) # Violet néon
    )
    
    # --- AJOUT DU GIF ---
    embed.set_image(url=PIXEL_ART_GIF_URL)
    
    embed.add_field(name="DEMARRAGE DANS", value="MISE A JOUR...", inline=True)
    embed.add_field(name="DUREE", value=duration.upper(), inline=True)
    embed.add_field(name="JOUEURS", value=f"0/{participant_limit}", inline=True)
    
    embed.add_field(name="LISTE DES JOUEURS", value="AUCUN JOUEUR INSCRIT", inline=False)
    
    # Le message est envoyé avec une view (les boutons)
    view = EventButtonsView(event_id="placeholder", event_data=event_data) # Placeholder ID
    event_message = await announcement_channel.send(f"**PRET POUR JOUER ?**", embed=embed, view=view)
    
    # Met à jour l'ID du message dans la base de données et dans la view
    event_data['message_id'] = str(event_message.id)
    doc_ref = db.collection('events').document(str(event_message.id))
    doc_ref.set(event_data)
    
    # Envoi le message à @everyone après la création de l'événement
    await announcement_channel.send(f"@everyone | NOUVEL EVENEMENT CREE : **{event_title.upper()}**\n**CLIQUEZ SUR LE BOUTON POUR start !**")
    
    response = await ctx.send(f"PARTIE LANCEE ! ID DE L'EVENEMENT : `{event_message.id}`")
    # Ajoute le message à la liste pour le nettoyage
    messages_to_clean.append({
        'message': response,
        'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
    })

@bot.command(name='create_event_plan')
@commands.has_permissions(manage_roles=True)
async def create_event_plan(ctx, date_str: str, start_time_str: str, duration: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, participant_limit: int, participant_group_name: str, *, event_title: str):
    """
    Crée un événement planifié pour une date et une heure futures, et ajoute des participants si nécessaire.
    Syntaxe: !create_event_plan <date> <heure_début> <durée> <@rôle> <#salon_annonce> <#salle_attente> <limite_participants> <nom_participants> <description>
    Exemple: !create_event_plan 2025-12-25 20:00 2h30m @Participants #annonces #salle-attente 10 10 pixels Soirée de Noël
    """
    print(f"Commande !create_event_plan reçue de {ctx.author} avec les arguments: {ctx.args}")
    if not db:
        await ctx.send("ERREUR SYSTEME : BASE DE DONNEES NON CONNECTEE.")
        return

    # --- NOUVEAU: Vérification de l'existence d'un événement avec le même titre ---
    async with ctx.typing():
        docs = db.collection('events').where('event_title', '==', event_title).get()
        if len(docs) > 0:
            response = await ctx.send(f"ERREUR : Un événement nommé `{event_title}` existe déjà. Veuillez utiliser un autre nom ou fermer l'événement existant avec `!end_event`.")
            messages_to_clean.append({
                'message': response,
                'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
            })
            return
    
    try:
        # Combine la date et l'heure en un seul objet datetime
        start_datetime_str = f"{date_str} {start_time_str}"
        start_time = datetime.strptime(start_datetime_str, '%Y-%m-%d %H:%M').replace(tzinfo=pytz.utc)
    except ValueError:
        response = await ctx.send("ERREUR. FORMAT DATE OU HEURE INVALIDE. UTILISEZ 'AAAA-MM-JJ HH:MM'.")
        messages_to_clean.append({
            'message': response,
            'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
        })
        return
        
    event_duration = parse_duration(duration)
    if not event_duration:
        response = await ctx.send("ERREUR. FORMAT DUREE INVALIDE. UTILISEZ '1h30m'.")
        messages_to_clean.append({
            'message': response,
            'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
        })
        return
    
    # --- NOUVEAU : Vérification de l'heure de début ---
    now = datetime.now(pytz.utc)
    if start_time < now:
        response = await ctx.send(f"ERREUR : La date et l'heure de début ({start_time.strftime('%d-%m-%Y %H:%M')}) ne peuvent pas être dans le passé. Veuillez choisir une date future.")
        messages_to_clean.append({
            'message': response,
            'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
        })
        return
        
    end_time = start_time + event_duration
    
    # Crée un dictionnaire pour les données de l'événement
    event_data = {
        'event_title': event_title,
        'start_time': start_time,
        'end_time': end_time,
        'role_id': str(role.id),
        'guild_id': str(ctx.guild.id),
        'announcement_channel_id': str(announcement_channel.id),
        'waiting_room_channel_id': str(waiting_room_channel.id),
        'participant_limit': participant_limit,
        'participants': {},
        'has_started': False,
        'message_id': '',
        'type': 'planned',
        'participant_group_name': participant_group_name
    }
    
    # Crée un embed initial au style 8-bit
    embed_description = (
        f"BIENVENUE JOUEUR !\n"
        f"ROLE ATTRIBUE AU DEMARRAGE : {role.mention}\n"
        f"POINT DE RALLIEMENT : {waiting_room_channel.mention}\n"
        f"DEPLACEMENT AUTOMATIQUE A L'HEURE DE DEBUT !\n"
        f"PARTICIPANTS REQUIS : {participant_group_name.upper()}"
    )

    embed = discord.Embed(
        title=f"**NOUVELLE PARTIE ! EVENEMENT :** {event_title.upper()}",
        description=embed_description,
        color=discord.Color(0x6441a5) # Violet néon
    )
    
    # --- AJOUT DU GIF ---
    embed.set_image(url=PIXEL_ART_GIF_URL)
    
    embed.add_field(name="DATE", value=start_time.strftime('%d/%m/%Y'), inline=True)
    embed.add_field(name="HEURE", value=start_time.strftime('%H:%M'), inline=True)
    embed.add_field(name="JOUEURS", value=f"0/{participant_limit}", inline=True)
    
    embed.add_field(name="LISTE DES JOUEURS", value="AUCUN JOUEUR INSCRIT", inline=False)
    
    view = EventButtonsView(event_id="placeholder", event_data=event_data)
    event_message = await announcement_channel.send(f"**PRET POUR JOUER ?**", embed=embed, view=view)
    
    event_data['message_id'] = str(event_message.id)
    doc_ref = db.collection('events').document(str(event_message.id))
    doc_ref.set(event_data)

    await announcement_channel.send(f"@everyone | NOUVEL EVENEMENT PLANIFIE : **{event_title.upper()}**\n**CLIQUEZ SUR LE BOUTON POUR start !**")
    
    response = await ctx.send(f"PARTIE PLANIFIEE ! ID DE L'EVENEMENT : `{event_message.id}`")
    # Ajoute le message à la liste pour le nettoyage
    messages_to_clean.append({
        'message': response,
        'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
    })

@bot.command(name='list_events')
@commands.has_permissions(manage_roles=True)
async def list_events(ctx):
    """
    Affiche la liste de tous les événements actifs avec leurs IDs.
    """
    print(f"Commande !list_events reçue de {ctx.author}.")
    if not db:
        await ctx.send("ERREUR SYSTEME : BASE DE DONNEES NON CONNECTEE.")
        return
        
    docs = db.collection('events').stream()
    
    events_list = []
    for doc in docs:
        event = doc.to_dict()
        if datetime.now(pytz.utc) < event['end_time'].replace(tzinfo=pytz.utc):
            events_list.append(event)
    
    if not events_list:
        response = await ctx.send("AUCUNE PARTIE EN COURS.")
    else:
        description = ""
        for event in events_list:
            event_type = "CONCOURS" if event.get('type') == 'contest' else "EVENEMENT"
            description += f"**{event_type} :** `{event['event_title'].upper()}`\n"
            description += f"ID : `{event['message_id']}`\n"
            description += f"DATE : {event['start_time'].strftime('%d/%m/%Y %H:%M')}\n"
            description += "----------------------------------------\n"
            
        embed = discord.Embed(
            title="LISTE DES PARTIES ACTIVES",
            description=description,
            color=discord.Color(0x6441a5) # Violet néon
        )
        # --- AJOUT DU GIF ---
        embed.set_image(url=PIXEL_ART_GIF_URL)
        response = await ctx.send(embed=embed)
    
    # Ajoute le message à la liste pour le nettoyage
    messages_to_clean.append({
        'message': response,
        'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
    })

@bot.command(name='end_event')
@commands.has_permissions(manage_roles=True)
async def end_event(ctx, event_id: str):
    """
    Termine manuellement un événement et supprime les rôles.
    """
    print(f"Commande !end_event reçue de {ctx.author} pour l'ID {event_id}.")
    if not db:
        await ctx.send("ERREUR SYSTEME : BASE DE DONNEES NON CONNECTEE.")
        return
        
    doc_ref = db.collection('events').document(event_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        await ctx.send("PARTIE INEXISTANTE.")
        return
    
    event_data = doc.to_dict()
    
    # Retire le rôle à tous les participants
    role_id = event_data.get('role_id')
    if role_id:
        role = ctx.guild.get_role(int(role_id))
        for user_id in event_data['participants']:
            member = ctx.guild.get_member(int(user_id))
            if member and role:
                await member.remove_roles(role)
    
    # Met à jour le message pour indiquer que l'événement est terminé
    event_data['end_time'] = datetime.now(pytz.utc)
    await update_event_message(event_data, view_to_remove=True)
    
    # Supprime l'événement de la base de données
    doc_ref.delete()
    
    response = await ctx.send(f"LA PARTIE AVEC L'ID `{event_id}` EST TERMINEE. ROLES RETIRES.")
    # Ajoute le message à la liste pour le nettoyage
    messages_to_clean.append({
        'message': response,
        'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
    })

@bot.command(name='create_contest')
@commands.has_permissions(manage_roles=True)
async def create_contest(ctx, deadline_date_str: str, deadline_time_str: str, participant_limit: int, announcement_channel: discord.TextChannel, event_title: str, *, prize: str):
    """
    Crée un concours.
    Syntaxe: !create_contest <date_limite> <heure_limite> <limite_participants> <#salon_annonce> <titre_event> <prix>
    Exemple: !create_contest 2025-12-25 20:00 100 #annonces Gagnez un jeu! Jeu vidéo
    """
    print(f"Commande !create_contest reçue de {ctx.author} avec les arguments: {ctx.args}")
    if not db:
        await ctx.send("ERREUR SYSTEME : BASE DE DONNEES NON CONNECTEE.")
        return

    # --- NOUVEAU: Vérification de l'existence d'un événement avec le même titre ---
    async with ctx.typing():
        docs = db.collection('events').where('event_title', '==', event_title).get()
        if len(docs) > 0:
            response = await ctx.send(f"ERREUR : Un concours nommé `{event_title}` existe déjà. Veuillez utiliser un autre nom ou fermer l'événement existant avec `!end_event`.")
            messages_to_clean.append({
                'message': response,
                'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
            })
            return
        
    try:
        deadline_datetime_str = f"{deadline_date_str} {deadline_time_str}"
        deadline_time = datetime.strptime(deadline_datetime_str, '%Y-%m-%d %H:%M').replace(tzinfo=pytz.utc)
    except ValueError:
        response = await ctx.send("ERREUR. FORMAT DATE OU HEURE INVALIDE. UTILISEZ 'AAAA-MM-JJ HH:MM'.")
        messages_to_clean.append({
            'message': response,
            'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
        })
        return
    
    # --- NOUVEAU : Vérification de l'heure limite ---
    now = datetime.now(pytz.utc)
    if deadline_time < now:
        response = await ctx.send(f"ERREUR : L'heure limite ({deadline_time.strftime('%d-%m-%Y %H:%M')}) ne peut pas être dans le passé. Veuillez choisir une date future.")
        messages_to_clean.append({
            'message': response,
            'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
        })
        return
        
    event_data = {
        'event_title': event_title,
        'deadline_time': deadline_time,
        'participant_limit': participant_limit,
        'guild_id': str(ctx.guild.id),
        'announcement_channel_id': str(announcement_channel.id),
        'participants': {},
        'message_id': '',
        'type': 'contest',
        'prize': prize
    }
    
    embed_description = (
        f"**PRIX :** {prize.upper()}\n"
        f"CLIQUEZ SUR LE BOUTON POUR VOUS INSCRIRE !"
    )
    
    embed = discord.Embed(
        title=f"**NOUVEAU JEU ! CONCOURS :** {event_title.upper()}",
        description=embed_description,
        color=discord.Color(0x027afa) # Bleu néon pour les concours
    )
    
    # --- AJOUT DU GIF ---
    embed.set_image(url=PIXEL_ART_GIF_URL)
    
    embed.add_field(name="FIN DU CONCOURS LE", value=deadline_time.strftime('%d/%m/%Y'), inline=True)
    embed.add_field(name="A L'HEURE", value=deadline_time.strftime('%H:%M'), inline=True)
    embed.add_field(name="JOUEURS", value=f"0/{participant_limit}", inline=True)
    embed.add_field(name="LISTE DES JOUEURS", value="AUCUN JOUEUR INSCRIT", inline=False)
    
    view = EventButtonsView(event_id="placeholder", event_data=event_data)
    event_message = await announcement_channel.send(f"**PREPAREZ-VOUS POUR LE CONCOURS !**", embed=embed, view=view)
    
    event_data['message_id'] = str(event_message.id)
    doc_ref = db.collection('events').document(str(event_message.id))
    doc_ref.set(event_data)
    
    await announcement_channel.send(f"@everyone | NOUVEAU CONCOURS CREE : **{event_title.upper()}**\n**CLIQUEZ SUR LE BOUTON POUR PARTICIPER !**")

    response = await ctx.send(f"CONCOURS LANCE ! ID DE L'EVENEMENT : `{event_message.id}`")
    # Ajoute le message à la liste pour le nettoyage
    messages_to_clean.append({
        'message': response,
        'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
    })
    
@bot.command(name='raffle_event')
@commands.has_permissions(manage_roles=True)
async def raffle_event(ctx, event_id: str):
    """
    Effectue un tirage au sort parmi les participants d'un événement ou d'un concours et annonce un gagnant.
    """
    print(f"Commande !raffle_event reçue de {ctx.author} pour l'ID {event_id}.")
    if not db:
        await ctx.send("ERREUR SYSTEME : BASE DE DONNEES NON CONNECTEE.")
        return
        
    doc_ref = db.collection('events').document(event_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        await ctx.send("PARTIE INEXISTANTE.")
        return
        
    event_data = doc.to_dict()
    participants_ids = list(event_data['participants'].keys())
    
    if not participants_ids:
        await ctx.send("AUCUN JOUEUR N'EST INSCRIT. LE TIRAGE EST ANNULE.")
        return
        
    winner_id = random.choice(participants_ids)
    event_data['winner_id'] = winner_id
    
    # Met à jour le message pour indiquer le gagnant et le statut terminé
    await update_event_message(event_data, view_to_remove=True)

    response = await ctx.send(f"FELICITATIONS A <@{winner_id}> POUR AVOIR GAGNE LA PARTIE `{event_data['event_title'].upper()}` ! ")
    # Ajoute le message à la liste pour le nettoyage
    messages_to_clean.append({
        'message': response,
        'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
    })

@bot.command(name='test_permissions')
@commands.has_permissions(manage_roles=True)
async def test_permissions(ctx):
    """Vérifie si l'utilisateur a les permissions requises pour les commandes d'événements."""
    response = await ctx.send("FELICITATIONS ! VOUS AVEZ LES PERMISSIONS NECESSAIRES POUR UTILISER LES COMMANDES D'EVENEMENT.")
    # Ajoute le message à la liste pour le nettoyage
    messages_to_clean.append({
        'message': response,
        'delete_after': datetime.now() + timedelta(seconds=CLEANUP_DELAY_SECONDS)
    })

# --- Tâches en boucle ---
@tasks.loop(seconds=30)
async def update_events_loop():
    """Vérifie et met à jour l'état des événements toutes les 30 secondes."""
    if not db:
        return
        
    docs = db.collection('events').stream()
    now = datetime.now(pytz.utc)
    
    async def process_event(event_data, event_id):
        guild = bot.get_guild(int(event_data['guild_id']))
        if not guild: return
        
        channel = guild.get_channel(int(event_data['announcement_channel_id']))
        if not channel: return
        
        # Logique pour les événements immédiats et planifiés
        if event_data.get('type') != 'contest':
            start_time = event_data['start_time'].replace(tzinfo=pytz.utc)
            end_time = event_data['end_time'].replace(tzinfo=pytz.utc)
            
            # Début de l'événement
            if not event_data.get('has_started') and now >= start_time:
                event_data['has_started'] = True
                db.collection('events').document(event_id).update({'has_started': True})
                
                # Attribue le rôle aux participants
                role = guild.get_role(int(event_data['role_id']))
                for user_id in event_data['participants']:
                    member = guild.get_member(int(user_id))
                    if member and role:
                        await member.add_roles(role)
                
                await channel.send(f"@everyone | **LA PARTIE A COMMENCE !** `{event_data['event_title'].upper()}` est en cours. Les participants ont reçu leur rôle. Direction le salon {guild.get_channel(int(event_data['waiting_room_channel_id'])).mention} !")

            # Fin de l'événement
            if now >= end_time:
                # Retire le rôle et supprime l'événement de la BDD
                role = guild.get_role(int(event_data['role_id']))
                if role:
                    for user_id in event_data['participants']:
                        member = guild.get_member(int(user_id))
                        if member:
                            await member.remove_roles(role)

                await update_event_message(event_data, view_to_remove=True)
                db.collection('events').document(event_id).delete()
        
        # Logique pour les concours
        else:
            deadline_time = event_data['deadline_time'].replace(tzinfo=pytz.utc)
            if now >= deadline_time and not event_data.get('raffle_done', False):
                # Le tirage au sort n'est pas automatique, on met juste à jour l'embed
                event_data['raffle_done'] = True
                await update_event_message(event_data, view_to_remove=True)
                db.collection('events').document(event_id).update({'raffle_done': True})
                await channel.send(f"@everyone | **FIN DES PARTICIPATIONS** pour le concours `{event_data['event_title'].upper()}`. Un modérateur lancera le tirage au sort avec `!raffle_event {event_id}`.")
                
        # Met à jour l'embed de l'événement
        await update_event_message(event_data)

    for doc in docs:
        event_data = doc.to_dict()
        event_id = doc.id
        await process_event(event_data, event_id)

@tasks.loop(seconds=60) # Vérifie toutes les minutes
async def cleanup_messages_loop():
    """Supprime les messages obsolètes."""
    now = datetime.now()
    to_delete = []
    for msg_info in messages_to_clean:
        if now >= msg_info['delete_after']:
            try:
                await msg_info['message'].delete()
            except discord.NotFound:
                pass  # Le message a peut-être déjà été supprimé
            to_delete.append(msg_info)
    
    # Supprime les messages de la liste après la suppression
    for msg_info in to_delete:
        messages_to_clean.remove(msg_info)

# --- Exécution du bot ---
if __name__ == '__main__':
    # Initialise le serveur web sur un thread séparé
    def run_flask():
        app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))
        
    async def main():
        # Démarre le serveur Flask
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, run_flask)
        
        # Démarre le bot
        token = os.environ.get('DISCORD_BOT_TOKEN')
        if not token:
            print("Erreur: Le token du bot Discord 'DISCORD_BOT_TOKEN' n'est pas défini.")
        else:
            await bot.start(token)
            
    # Lance le bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot arrêté.")
