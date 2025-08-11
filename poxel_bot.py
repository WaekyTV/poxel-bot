# Fichier: bot.py

import os
import asyncio
from datetime import datetime, timedelta
import pytz

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

# --- Serveur Flask pour le ping Uptime Robot ---
# Ceci est nécessaire pour que Render garde le bot en vie.
app = Flask(__name__)

@app.route('/')
def home():
    """Un simple endpoint pour que le robot Uptime puisse pinguer."""
    return "Le bot Discord est en vie !"

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
        prefix = "depuis "
    else:
        prefix = "dans "
    
    hours, remainder = divmod(int(td.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0:
        parts.append(f"{seconds}s")
    
    return prefix + " ".join(parts) if parts else "maintenant"

async def update_event_message(event_data, view_to_remove=False):
    """
    Met à jour le message d'embed de l'événement.
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
    start_time = event_data['start_time'].replace(tzinfo=pytz.utc)
    end_time = event_data['end_time'].replace(tzinfo=pytz.utc)
    
    # Gestion du cas où l'événement est terminé ou annulé
    if view_to_remove:
        if now >= end_time:
            embed = discord.Embed(
                title=f"**Événement terminé :** {event_data['event_title']}",
                description="Cet événement est maintenant terminé. Merci à tous les participants !",
                color=discord.Color.dark_grey()
            )
        else: # Cas d'annulation
            embed = discord.Embed(
                title=f"**Événement annulé :** {event_data['event_title']}",
                description="Cet événement a été annulé car le nombre de participants requis n'a pas été atteint.",
                color=discord.Color.red()
            )
        
        embed.add_field(name="Participants", value=f"{len(event_data['participants'])}/{event_data['participant_limit']}", inline=True)
        await message.edit(embed=embed, view=None)
        return
        
    # Cas normal, l'événement est en cours ou à venir
    embed_description = (
        f"En participant à cet événement, le rôle `<@&{event_data['role_id']}>` vous sera attribué au démarrage de l'événement.\n"
        f"Veuillez rejoindre le **Point de ralliement** <#{event_data['waiting_room_channel_id']}> et attendre que l'événement commence.\n"
        f"Une fois l'événement démarré, vous serez déplacé dans un autre salon."
    )
    
    embed = discord.Embed(
        title=f"**NEW EVENT :** {event_data['event_title']}",
        description=embed_description,
        color=discord.Color.blue()
    )
    
    if now < start_time:
        embed.add_field(name="Démarre dans", value=format_timedelta(start_time - now), inline=True)
    elif now < end_time:
        embed.add_field(name="Fini dans", value=format_timedelta(end_time - now), inline=True)
    else:
        embed.add_field(name="Terminé il y a", value=format_timedelta(now - end_time), inline=True)
        embed.color = discord.Color.dark_grey()
        
    embed.add_field(name="Participants", value=f"{len(event_data['participants'])}/{event_data['participant_limit']}", inline=True)
    
    # Afficher la liste des participants avec leurs pseudos
    participant_mentions = []
    for uid, nickname in event_data['participants'].items():
        if nickname:
            participant_mentions.append(f"<@{uid}> ({nickname})")
        else:
            participant_mentions.append(f"<@{uid}>")
            
    embed.add_field(name="Participants inscrits", value=", ".join(participant_mentions) if participant_mentions else "Aucun", inline=False)
    
    # Crée une nouvelle vue pour mettre à jour les boutons
    new_view = EventButtonsView(event_id=event_data['message_id'], event_data=event_data)
    
    await message.edit(embed=embed, view=new_view)

# --- Classes pour les boutons interactifs et la modale ---

class GameNameModal(discord.ui.Modal):
    """Modale pour demander le pseudo en jeu du participant."""
    def __init__(self, event_id: str, event_data: dict, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.event_id = event_id
        self.event_data = event_data
        
        # Ajout du champ de texte pour le pseudo
        self.add_item(discord.ui.TextInput(
            label="Votre pseudo en jeu",
            placeholder="Entrez votre pseudo (laissez vide si non applicable)",
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
            await interaction.response.send_message(f"Vous êtes déjà inscrit à cet événement.", ephemeral=True)
            return

        # Vérifie si le nombre de participants est sur le point d'atteindre la limite
        is_about_to_be_full = len(data['participants']) + 1 >= data['participant_limit']
        
        if len(data['participants']) >= data['participant_limit']:
            await interaction.response.send_message(f"Désolé, le nombre maximum de participants a été atteint.", ephemeral=True)
            return
        
        # Ajoute le participant et son pseudo à la liste dans Firebase
        data['participants'][str(member.id)] = game_nickname
        doc_ref.update({'participants': data['participants']})
        
        # Met à jour le message d'embed et la vue
        await update_event_message(data)
        
        message_to_user = (
            f"Vous avez rejoint l'événement **{data['event_title']}** ! "
            f"Votre pseudo en jeu, '{game_nickname}', a bien été enregistré. "
            f"Vous recevrez le rôle et une notification lorsque l'événement démarrera."
        ) if game_nickname else (
            f"Vous avez rejoint l'événement **{data['event_title']}** ! "
            f"Vous recevrez le rôle et une notification lorsque l'événement démarrera."
        )

        await interaction.response.send_message(message_to_user, ephemeral=True)
        
        # Si le nombre de participants atteint la limite, envoie une notification
        if is_about_to_be_full:
            announcement_channel = bot.get_channel(int(data['announcement_channel_id']))
            await announcement_channel.send(f"@everyone | **Inscription fermée** pour l'événement **{data['event_title']}** car la limite de participants a été atteinte.")


class EventButtonsView(discord.ui.View):
    def __init__(self, event_id: str, event_data: dict):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.event_data = event_data
        
        # Logique pour désactiver le bouton si l'inscription est fermée
        is_full = len(event_data['participants']) >= event_data['participant_limit']
        
        join_button = discord.ui.Button(
            label="Inscription fermée" if is_full else "Start",
            style=discord.ButtonStyle.red if is_full else discord.ButtonStyle.green,
            emoji="⛔" if is_full else "🏃‍♂️",
            custom_id="join_event",
            disabled=is_full
        )
        self.add_item(join_button)
        
        leave_button = discord.ui.Button(
            label="Quit",
            style=discord.ButtonStyle.red,
            emoji="🚪",
            custom_id="leave_event",
            disabled=False
        )
        self.add_item(leave_button)

    @discord.ui.button(custom_id="join_event")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback pour le bouton 'Start' qui ouvre une modale."""
        # Envoie la modale pour demander le pseudo en jeu
        modal = GameNameModal(title="Entrez votre pseudo en jeu", event_id=self.event_id, event_data=self.event_data)
        await interaction.response.send_modal(modal)

    @discord.ui.button(custom_id="leave_event")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback pour le bouton 'Quit'."""
        member = interaction.user
        doc_ref = db.collection('events').document(self.event_id)
        doc = doc_ref.get()
        data = doc.to_dict()
        
        if str(member.id) not in data['participants']:
            await interaction.response.send_message(f"Vous n'êtes pas inscrit à cet événement.", ephemeral=True)
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
            
        # Met à jour le message d'embed et la vue
        await update_event_message(data)
        await interaction.response.send_message(f"Vous vous êtes désisté de l'événement.", ephemeral=True)

        # Si la liste était pleine et qu'elle a maintenant de la place, envoie une notification
        if was_full and len(data['participants']) < data['participant_limit']:
            announcement_channel = bot.get_channel(int(data['announcement_channel_id']))
            await announcement_channel.send(f"@everyone | **Inscription ouverte** pour l'événement **{data['event_title']}** suite à un désistement !")

# --- Événements du bot ---
@bot.event
async def on_ready():
    """Se déclenche lorsque le bot est prêt."""
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Le bot est prêt à démarrer...')
    # Démarre la tâche de vérification des événements
    if db:
        update_events_loop.start()
        
# --- Commandes du bot ---
@bot.command(name='create_event')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, start_time_str: str, duration: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, participant_limit: int, *, event_title: str):
    """
    Crée un nouvel événement avec des paramètres détaillés.
    Syntaxe: !create_event <heure_début> <durée_event> <@rôle> <#salon_annonce> <#salle_attente> <nombre_max_participants> <titre_event>
    Exemple: !create_event 20:00 2h30m @Participants #annonces #salle-attente 10 Soirée Gaming!
    """
    if not db:
        await ctx.send("Erreur: La base de données n'est pas connectée. Veuillez vérifier les identifiants Firebase.")
        return

    # Analyse l'heure de début et la durée
    start_time = parse_time(start_time_str)
    event_duration = parse_duration(duration)
    
    if not start_time:
        await ctx.send("Format d'heure de début invalide. Utilisez le format 'HH:MM'.")
        return
        
    if not event_duration:
        await ctx.send("Format de durée invalide. Utilisez le format '1h30m' (heures, minutes, secondes).")
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
        'participants': {}, # La liste des participants est désormais un dictionnaire { 'user_id': 'nickname' }
        'has_started': False,
        'message_id': ''
    }

    # Crée un embed initial
    embed_description = (
        f"En participant à cet événement, le rôle `{role.mention}` vous sera attribué au démarrage de l'événement.\n"
        f"Veuillez rejoindre le **Point de ralliement** {waiting_room_channel.mention} et attendre que l'événement commence.\n"
        f"Une fois l'événement démarré, vous serez déplacé dans un autre salon."
    )
    
    embed = discord.Embed(
        title=f"**NEW EVENT :** {event_title}",
        description=embed_description,
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Démarre dans", value="mise à jour...", inline=True)
    embed.add_field(name="Durée", value=duration, inline=True)
    embed.add_field(name="Participants", value=f"0/{participant_limit}", inline=True)
    embed.add_field(name="Participants inscrits", value="Aucun", inline=False)
    
    # Le message est envoyé avec une view (les boutons)
    view = EventButtonsView(event_id="placeholder", event_data=event_data) # Placeholder ID
    event_message = await announcement_channel.send(f"**Rejoignez l'événement !**", embed=embed, view=view)
    
    # Met à jour l'ID du message dans la base de données et dans la view
    event_data['message_id'] = str(event_message.id)
    doc_ref = db.collection('events').document(str(event_message.id))
    doc_ref.set(event_data)
    
    # Envoi le message à @everyone après la création de l'événement
    await announcement_channel.send(f"@everyone | Nouvel événement créé : **{event_title}**\n**Les inscriptions sont ouvertes !** Rejoignez l'événement en cliquant sur le bouton ci-dessus pour vous inscrire et obtenir le rôle.")
    
    await ctx.send(f"Événement créé! ID de l'événement: `{event_message.id}`")

@bot.command(name='list_events')
async def list_events(ctx):
    """
    Affiche la liste de tous les événements actifs.
    """
    if not db:
        await ctx.send("Erreur: La base de données n'est pas connectée.")
        return

    events_ref = db.collection('events')
    docs = events_ref.stream()
    
    active_events = []
    for doc in docs:
        event_data = doc.to_dict()
        start_time = event_data['start_time'].replace(tzinfo=pytz.utc)
        end_time = event_data['end_time'].replace(tzinfo=pytz.utc)
        now = datetime.now(pytz.utc)
        
        if now < start_time:
            time_str = f"Démarre {format_timedelta(start_time - now)}"
        elif now < end_time:
            time_str = f"Fini {format_timedelta(end_time - now)}"
        else:
            time_str = f"Terminé {format_timedelta(now - end_time)}"
        
        active_events.append({
            'id': doc.id,
            'event_title': event_data.get('event_title', 'Pas de description'),
            'participants_count': len(event_data['participants']),
            'participant_limit': event_data.get('participant_limit', 'Non défini'),
            'time_status': time_str
        })
        
    if not active_events:
        await ctx.send("Il n'y a aucun événement actif pour le moment.")
    else:
        embed = discord.Embed(title="Événements Actifs", color=discord.Color.blue())
        for event in active_events:
            embed.add_field(
                name=f"ID: {event['id']} ({event['event_title']})",
                value=f"Participants: {event['participants_count']}/{event['participant_limit']}\nStatut: {event['time_status']}",
                inline=False
            )
        await ctx.send(embed=embed)


@bot.command(name='end_event')
@commands.has_permissions(manage_roles=True)
async def end_event(ctx, event_id: str):
    """
    Termine manuellement un événement et supprime les rôles.
    Syntaxe: !end_event <ID_de_l'événement>
    """
    if not db:
        await ctx.send("Erreur: La base de données n'est pas connectée. Veuillez vérifier les identifiants Firebase.")
        return

    doc_ref = db.collection('events').document(event_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        await ctx.send("Cet événement n'existe pas.")
        return

    data = doc.to_dict()
    guild = bot.get_guild(int(data['guild_id']))
    role = guild.get_role(int(data['role_id']))
    
    if role:
        for participant_id in data['participants'].keys():
            member = guild.get_member(int(participant_id))
            if member:
                await member.remove_roles(role)
    
    doc_ref.delete()
    await ctx.send(f"L'événement `{event_id}` a été terminé et les rôles ont été supprimés.")


# --- Tâche de fond pour vérifier les événements ---
@tasks.loop(minutes=1)
async def update_events_loop():
    """
    Met à jour les messages d'événements, gère ceux qui sont terminés et démarre ceux qui débutent.
    """
    if not db:
        return
        
    print("Mise à jour des événements en cours...")
    events_ref = db.collection('events')
    docs = events_ref.stream()
    
    for doc in docs:
        event_data = doc.to_dict()
        event_id = doc.id
        now = datetime.now(pytz.utc)
        start_time = event_data['start_time'].replace(tzinfo=pytz.utc)
        end_time = event_data['end_time'].replace(tzinfo=pytz.utc)
        
        # Gère le démarrage de l'événement et la vérification des participants
        if not event_data.get('has_started', False) and now >= start_time:
            # Vérifie si le nombre de participants est suffisant pour démarrer l'événement
            if len(event_data['participants']) < event_data['participant_limit'] and event_data['participant_limit'] > 0:
                print(f"Annulation de l'événement {event_id} - pas assez de participants.")
                
                guild = bot.get_guild(int(event_data['guild_id']))
                announcement_channel = guild.get_channel(int(event_data['announcement_channel_id']))
                
                # Met à jour le message d'annonce pour indiquer l'annulation et retire les boutons
                await update_event_message(event_data, view_to_remove=True)
                
                # Envoie une annonce d'annulation au serveur
                await announcement_channel.send(
                    f"@everyone | L'événement **{event_data['event_title']}** a été annulé car il n'y a pas assez de participants inscrits "
                    f"({len(event_data['participants'])}/{event_data['participant_limit']})."
                )
                
                # Supprime l'événement de la base de données
                doc.reference.delete()
                continue # Passe à l'événement suivant
            
            # Si le nombre de participants est suffisant (ou s'il n'y a pas de limite), on démarre l'événement
            event_data['has_started'] = True
            doc.reference.update({'has_started': True})
            
            guild = bot.get_guild(int(event_data['guild_id']))
            role = guild.get_role(int(event_data['role_id']))
            waiting_room_channel = guild.get_channel(int(event_data['waiting_room_channel_id']))
            announcement_channel = guild.get_channel(int(event_data['announcement_channel_id']))
            
            # Annonce le démarrage de l'événement et retire le message initial
            try:
                message = await announcement_channel.fetch_message(int(event_data['message_id']))
                await message.delete()
            except discord.NotFound:
                print(f"Message de l'événement {event_data['message_id']} non trouvé lors du démarrage.")
            
            # ANNONCE LA FIN DES INSCRIPTIONS ET LE DÉMARRAGE AU SERVEUR ENTIER
            await announcement_channel.send(
                f"@everyone | L'événement **{event_data['event_title']}** a démarré ! Les inscriptions sont closes."
            )
            
            for participant_id in event_data['participants'].keys():
                member = guild.get_member(int(participant_id))
                if member and role:
                    try:
                        await member.add_roles(role)
                        # ENVOIE UN MESSAGE PRIVÉ À CHAQUE PARTICIPANT
                        await member.send(
                            f"L'événement **{event_data['event_title']}** a démarré ! "
                            f"Le rôle {role.mention} vous a été attribué.\n"
                            f"Veuillez rejoindre le **Point de ralliement** {waiting_room_channel.mention} et attendre d'être déplacé."
                        )
                    except discord.Forbidden:
                        print(f"Permissions insuffisantes pour attribuer le rôle ou envoyer un DM au membre {member.name}.")
                        
        # Met à jour le message d'embed de l'événement (uniquement si l'événement n'a pas encore démarré)
        elif not event_data.get('has_started', False):
            await update_event_message(event_data)
        
        # Vérifie si l'événement est terminé
        if now >= end_time:
            guild = bot.get_guild(int(event_data['guild_id']))
            role = guild.get_role(int(event_data['role_id']))
            announcement_channel = guild.get_channel(int(event_data['announcement_channel_id']))

            # Met à jour le message d'annonce pour indiquer la fin de l'événement et retire les boutons
            await update_event_message(event_data, view_to_remove=True)

            # ANNONCE LA FIN DE L'ÉVÉNEMENT ET REMERCIE LES PARTICIPANTS
            await announcement_channel.send(
                f"@everyone | L'événement **{event_data['event_title']}** est terminé ! Merci à tous les participants."
            )
            
            if role:
                for participant_id in event_data['participants'].keys():
                    member = guild.get_member(int(participant_id))
                    if member:
                        print(f"Suppression du rôle '{role.name}' pour le membre '{member.name}'.")
                        try:
                            await member.remove_roles(role)
                        except discord.Forbidden:
                            print("Erreur: Permissions insuffisantes pour supprimer le rôle.")
            
            # Supprime l'événement de la base de données
            doc.reference.delete()
            print(f"Événement `{event_id}` expiré et supprimé.")


# --- Point d'entrée principal ---
# Exécute à la fois le bot Discord et le serveur Flask
async def main():
    """Point d'entrée pour exécuter le bot et le serveur Flask."""
    discord_token = os.environ.get('DISCORD_BOT_TOKEN')
    if not discord_token:
        print("Erreur: La variable d'environnement 'DISCORD_BOT_TOKEN' n'est pas définie.")
        return

    # Crée un objet pour le processus Flask
    server_process = asyncio.create_task(asyncio.to_thread(lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))))
    
    # Démarre le bot Discord
    await bot.start(discord_token)
    
    # Attend la fin du serveur Flask (ne devrait pas se produire en temps normal)
    await server_process

if __name__ == '__main__':
    asyncio.run(main())
