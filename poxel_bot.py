import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import datetime
import asyncio
import os
import json

# Importation et configuration de Flask pour l'hébergement
from flask import Flask
from threading import Thread

# Configuration du bot
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

# --- DATABASE (MAQUETTE) ---
# En production, il faudrait utiliser le SDK Firebase pour une base de données réelle.
# Ici, nous simulons la persistance des données dans un fichier JSON.
DATABASE_FILE = 'events.json'

def load_events():
    """Charge les données des événements depuis le fichier de la base de données."""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {"events": {}, "contests": {}}

def save_events(data):
    """Sauvegarde les données des événements dans le fichier de la base de données."""
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Variable globale pour la base de données (simulée)
db = load_events()

# --- FLASK SERVER POUR LA PERSISTANCE (RENDER) ---
# Ceci est nécessaire pour que le bot reste en ligne sur des services comme Render.
# Uptime Robot pinge cette URL pour éviter que l'application ne se mette en veille.
app = Flask(__name__)

@app.route('/')
def home():
    return "Poxel Bot is running!"

def run_flask():
    """Démarre le serveur Flask."""
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

# --- CLASSES DE BOUTONS ET DE VUES ---

class EventButtonsView(View):
    """
    Vue contenant les boutons d'inscription et de désinscription pour un événement.
    Les boutons sont gérés de manière dynamique.
    """
    def __init__(self, bot, event_name, event_data, timeout=None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.event_name = event_name
        self.event_data = event_data
        self.max_participants = self.event_data['max_participants']
        self.current_participants = len(self.event_data['participants'])

        # Mise à jour de l'état des boutons au chargement
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
        
        if user.id in [p['id'] for p in self.event_data['participants']]:
            await interaction.response.send_message("Vous êtes déjà inscrit à cet événement !", ephemeral=True)
            return

        # Ouverture de la modale pour le pseudo
        modal = ParticipantModal(self, event_name)
        await interaction.response.send_modal(modal)

    async def on_quit_click(self, interaction: discord.Interaction):
        """Gère la désinscription d'un utilisateur."""
        user_id = interaction.user.id
        event_name = self.event_name
        
        if user_id not in [p['id'] for p in self.event_data['participants']]:
            await interaction.response.send_message("Vous n'êtes pas inscrit à cet événement.", ephemeral=True)
            return
            
        # Suppression du participant
        self.event_data['participants'] = [p for p in self.event_data['participants'] if p['id'] != user_id]
        save_events(db)
        
        self.current_participants = len(self.event_data['participants'])
        self.update_buttons()
        
        # Mise à jour de l'embed
        await update_event_embed(self.bot, event_name)
        await interaction.response.send_message("Vous vous êtes désinscrit de l'événement.", ephemeral=True)

    async def on_list_click(self, interaction: discord.Interaction):
        """Affiche la liste des événements en cours."""
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
        user = interaction.user
        game_pseudo = self.game_pseudo.value
        
        # Enregistrement du participant
        self.view.event_data['participants'].append({
            "id": user.id,
            "name": user.display_name,
            "pseudo": game_pseudo
        })
        save_events(db)
        
        self.view.current_participants = len(self.view.event_data['participants'])
        self.view.update_buttons()

        # Mise à jour de l'embed
        await update_event_embed(self.view.bot, self.event_name)
        await interaction.response.send_message(f"Vous avez été inscrit à l'événement `{self.event_name}` avec le pseudo `{game_pseudo}`.", ephemeral=True)


# --- FONCTIONS UTILES ---

def format_time_left(end_time_str):
    """
    Formate le temps restant avant le début ou la fin de l'événement.
    """
    end_time = datetime.datetime.fromisoformat(end_time_str)
    now = datetime.datetime.now()
    delta = end_time - now
    
    if delta.total_seconds() < 0:
        return f"FINI IL Y A {abs(int(delta.total_seconds() // 60))} minutes"
        
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
            description="""
            Rejoignez-nous pour un événement spécial !
            """,
            color=NEON_PURPLE
        )
        embed.add_field(name="POINT DE RALLIEMENT", value=f"<#{event['waiting_channel_id']}>", inline=True)
        embed.add_field(name="RÔLE ATTRIBUÉ", value=f"<@&{event['role_id']}>", inline=True)
        
        # Gestion du temps
        start_time = datetime.datetime.fromisoformat(event['start_time'])
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
        
        # Ajout du GIF rétro
        # Remplacer cette URL par l'URL de votre GIF
        embed.set_image(url="https://i.imgur.com/uCgE04g.gif") 
        
        await message.edit(embed=embed)
        
    except discord.NotFound:
        # Le message a été supprimé, il faut nettoyer la base de données
        del db['events'][event_name]
        save_events(db)
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'embed pour {event_name}: {e}")

# --- BOT Poxel ---
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

@bot.event
async def on_ready():
    """
    Événement qui se déclenche lorsque le bot est prêt et connecté à Discord.
    """
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    print("------")
    # Lancement de la tâche planifiée de vérification des événements
    check_events.start()
    
# --- GESTION DES COMMANDES ---

@bot.command(name="create_event")
async def create_event(ctx, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, game_participants_str: str, event_name: str):
    """
    Crée un événement pour le jour même.
    Syntaxe: !create_event 21h30 1h @role #annonce #salle 10 "pseudonyme" "nom_evenement"
    """
    # Vérification des droits d'administration (exemple simple)
    if not ctx.message.author.guild_permissions.administrator:
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
        return

    # Vérification de l'unicité de l'événement
    if event_name in db['events']:
        await ctx.send(f"Un événement nommé `{event_name}` existe déjà. Veuillez en terminer l'ancien ou choisir un autre nom.", delete_after=120)
        return

    # Parsing de l'heure et de la durée
    try:
        now = datetime.datetime.now()
        start_hour, start_minute = map(int, start_time_str.split('h'))
        start_time = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)

        duration_unit = duration_str[-3:].lower() # 'min' ou 'h'
        duration_value = int(duration_str[:-3])

        if duration_unit == 'min':
            duration = datetime.timedelta(minutes=duration_value)
        elif duration_unit == 'h':
            duration = datetime.timedelta(hours=duration_value)
        else:
            await ctx.send("Le format de durée doit être 'Xmin' ou 'Xh'.", delete_after=120)
            return

        # Validation de l'heure de début
        if start_time < now:
            await ctx.send("L'heure de début de l'événement est déjà passée. Veuillez choisir une heure future.", delete_after=120)
            return

    except (ValueError, IndexError):
        await ctx.send("Erreur de format pour l'heure ou la durée. Utilisez le format 'HHhMM' et 'Xmin'/'Xh'.", delete_after=120)
        return

    # Création des données de l'événement
    event_data = {
        "start_time": start_time.isoformat(),
        "end_time": (start_time + duration).isoformat(),
        "role_id": role.id,
        "announcement_channel_id": announcement_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "participants": [],
        "is_started": False,
        "message_id": None
    }
    
    # Création et envoi de l'embed
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
    
    # Ajout de l'image et du footer
    embed.set_footer(text="Style 8-bit futuriste, néon")
    embed.set_image(url="https://i.imgur.com/uCgE04g.gif")
    
    # Envoi du message avec les boutons
    view = EventButtonsView(bot, event_name, event_data)
    message = await announcement_channel.send(content="@everyone", embed=embed, view=view)
    
    # Enregistrement du message ID pour les futures mises à jour
    event_data['message_id'] = message.id
    db['events'][event_name] = event_data
    save_events(db)

    await ctx.send("L'événement a été créé avec succès !", delete_after=120)
    await ctx.message.delete(delay=120)

@bot.command(name="create_event_plan")
async def create_event_plan(ctx, date_str: str, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_channel: discord.TextChannel, max_participants: int, game_participants_str: str, event_name: str):
    """
    Crée un événement planifié pour une date future.
    Identique à !create_event mais avec une date en plus.
    Syntaxe: !create_event_plan JJ/MM/AAAA 21h30 1h @role #annonce #salle 10 "pseudonyme" "nom_evenement"
    """
    # Vérification des droits d'administration (exemple simple)
    if not ctx.message.author.guild_permissions.administrator:
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
        return

    # Vérification de l'unicité de l'événement
    if event_name in db['events']:
        await ctx.send(f"Un événement nommé `{event_name}` existe déjà. Veuillez en terminer l'ancien ou choisir un autre nom.", delete_after=120)
        return

    # Parsing de la date, l'heure et la durée
    try:
        day, month, year = map(int, date_str.split('/'))
        start_hour, start_minute = map(int, start_time_str.split('h'))
        start_time = datetime.datetime(year, month, day, start_hour, start_minute)

        duration_unit = duration_str[-3:].lower()
        duration_value = int(duration_str[:-3])

        if duration_unit == 'min':
            duration = datetime.timedelta(minutes=duration_value)
        elif duration_unit == 'h':
            duration = datetime.timedelta(hours=duration_value)
        else:
            await ctx.send("Le format de durée doit être 'Xmin' ou 'Xh'.", delete_after=120)
            return

        if start_time < datetime.datetime.now():
            await ctx.send("La date et l'heure de l'événement sont déjà passées. Veuillez choisir une date future.", delete_after=120)
            return

    except (ValueError, IndexError):
        await ctx.send("Erreur de format pour la date, l'heure ou la durée. Utilisez le format 'JJ/MM/AAAA HHhMM' et 'Xmin'/'Xh'.", delete_after=120)
        return
        
    # Création des données de l'événement
    event_data = {
        "start_time": start_time.isoformat(),
        "end_time": (start_time + duration).isoformat(),
        "role_id": role.id,
        "announcement_channel_id": announcement_channel.id,
        "waiting_channel_id": waiting_channel.id,
        "max_participants": max_participants,
        "participants": [],
        "is_started": False,
        "message_id": None
    }
    
    # Création et envoi de l'embed
    embed = discord.Embed(
        title=f"NEW EVENT: {event_name}",
        description=f"""
        Rejoignez-nous pour un événement spécial, waeky !
        
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
    
    # Ajout de l'image et du footer
    embed.set_footer(text="Style 8-bit futuriste, néon")
    embed.set_image(url="https://i.imgur.com/uCgE04g.gif")
    
    # Envoi du message avec les boutons
    view = EventButtonsView(bot, event_name, event_data)
    message = await announcement_channel.send(content="@everyone", embed=embed, view=view)
    
    # Enregistrement du message ID pour les futures mises à jour
    event_data['message_id'] = message.id
    db['events'][event_name] = event_data
    save_events(db)

    await ctx.send("L'événement a été planifié avec succès !", delete_after=120)
    await ctx.message.delete(delay=120)

@bot.command(name="end_event")
async def end_event(ctx, event_name: str):
    """
    Termine un événement manuellement.
    """
    if not ctx.message.author.guild_permissions.administrator:
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
        return

    if event_name not in db['events']:
        await ctx.send(f"L'événement `{event_name}` n'existe pas.", delete_after=120)
        return
        
    event_data = db['events'][event_name]
    
    # Suppression du rôle pour tous les participants
    for participant in event_data['participants']:
        member = ctx.guild.get_member(participant['id'])
        if member:
            try:
                role = ctx.guild.get_role(event_data['role_id'])
                if role and role in member.roles:
                    await member.remove_roles(role)
            except Exception as e:
                print(f"Impossible de retirer le rôle du membre {member.id}: {e}")
                
    # Suppression de l'événement de la base de données
    del db['events'][event_name]
    save_events(db)
    
    # Envoi de la notification de fin
    channel = bot.get_channel(event_data['announcement_channel_id'])
    if channel:
        await channel.send(f"@everyone L'événement **{event_name}** est maintenant terminé. Merci à tous les participants !")
    
    await ctx.send(f"L'événement `{event_name}` a été terminé manuellement.", delete_after=120)
    await ctx.message.delete(delay=120)

@bot.command(name="tirage")
async def tirage(ctx, event_name: str):
    """
    Effectue un tirage au sort parmi les participants d'un événement.
    """
    if not ctx.message.author.guild_permissions.administrator:
        await ctx.send("Désolé, waeky, vous n'avez pas les droits nécessaires pour utiliser cette commande.", delete_after=120)
        return

    if event_name not in db['events']:
        await ctx.send(f"L'événement `{event_name}` n'existe pas.", delete_after=120)
        return
        
    event_data = db['events'][event_name]
    participants = event_data['participants']
    
    if not participants:
        await ctx.send(f"Il n'y a pas de participants pour le tirage au sort de l'événement `{event_name}`.", delete_after=120)
        return

    # Tirage au sort d'un gagnant aléatoire
    import random
    winner = random.choice(participants)
    
    await ctx.send(f"🎉 **Félicitations à <@{winner['id']}>** ! 🎉\nVous êtes le grand gagnant du tirage au sort pour l'événement `{event_name}`.")
    await ctx.message.delete(delay=120)

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

@tasks.loop(minutes=1)
async def check_events():
    """
    Boucle de vérification qui s'exécute toutes les minutes pour gérer les événements en temps réel.
    """
    events_to_delete = []
    
    for event_name, event_data in list(db['events'].items()):
        start_time = datetime.datetime.fromisoformat(event_data['start_time'])
        now = datetime.datetime.now()
        
        # Logique pour le rappel de 30 minutes avant le début
        if not event_data.get('reminded_30m') and (start_time - now).total_seconds() <= 30 * 60:
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if channel:
                await channel.send(f"@everyone ⏰ **RAPPEL:** L'événement **{event_name}** commence dans 30 minutes ! N'oubliez pas de vous inscrire.")
                event_data['reminded_30m'] = True
                save_events(db)
        
        # Logique pour le démarrage de l'événement
        if not event_data.get('is_started') and now >= start_time:
            # Vérification du nombre minimum de participants (ici, on prend 1 comme exemple)
            if len(event_data['participants']) < 1:
                channel = bot.get_channel(event_data['announcement_channel_id'])
                if channel:
                    await channel.send(f"@everyone ❌ **ANNULATION:** L'événement **{event_name}** a été annulé car le nombre de participants minimum n'a pas été atteint.")
                events_to_delete.append(event_name)
                continue
                
            event_data['is_started'] = True
            save_events(db)
            
            # Suppression de l'embed et de ses boutons
            channel = bot.get_channel(event_data['announcement_channel_id'])
            try:
                message = await channel.fetch_message(event_data['message_id'])
                await message.delete()
            except discord.NotFound:
                pass # Le message a déjà été supprimé
            
            # Envoi des notifications de démarrage
            for participant in event_data['participants']:
                member = bot.get_guild(channel.guild.id).get_member(participant['id'])
                if member:
                    # Attribution du rôle temporaire
                    role = member.guild.get_role(event_data['role_id'])
                    if role:
                        try:
                            await member.add_roles(role)
                        except Exception as e:
                            print(f"Impossible d'ajouter le rôle à {member.display_name}: {e}")
                            
                    # Envoi d'un message privé
                    await member.send(f"🎉 **Félicitations** ! L'événement `{event_name}` a démarré. Le rôle `{role.name}` vous a été attribué. Rendez-vous dans le salon <#{event_data['waiting_channel_id']}>.")
                    
            if channel:
                await channel.send(f"@everyone L'événement **{event_name}** a officiellement commencé ! Les inscriptions sont closes et le rôle a été attribué aux participants.")

        # Logique pour la fin de l'événement
        end_time = datetime.datetime.fromisoformat(event_data['end_time'])
        if now >= end_time and event_data.get('is_started'):
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if channel:
                await channel.send(f"@everyone L'événement **{event_name}** est maintenant terminé. Merci à tous les participants ! 🎉")
            
            # Suppression du rôle pour tous les participants
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
        
        # Mise à jour de l'embed en temps réel
        if not event_data.get('is_started'):
            await update_event_embed(bot, event_name)

    # Suppression des événements terminés de la base de données
    for event_name in events_to_delete:
        del db['events'][event_name]
        
    save_events(db)

# --- DÉMARRAGE DU BOT ET DU SERVEUR FLASK ---
if __name__ == "__main__":
    # Démarrage du serveur Flask dans un thread séparé
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Démarrage du bot Discord
    # Remplacez 'YOUR_BOT_TOKEN' par votre propre token Discord
    # Vous pouvez utiliser un fichier .env pour stocker votre token
    bot.run(os.environ.get('DISCORD_BOT_TOKEN'))
