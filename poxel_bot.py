# -*- coding: utf-8 -*-
import os
import asyncio
import json
from datetime import datetime, timedelta
import random

import discord
from discord.ext import commands, tasks
from discord import ui, app_commands, Embed, Interaction, ButtonStyle, HTTPException, NotFound

# Pour le serveur web Flask
from flask import Flask
from threading import Thread

# Pour la base de données Firebase Firestore
import firebase_admin
from firebase_admin import credentials, firestore

# --- Configuration et Initialisation ---

# Serveur web Flask pour le maintien en vie sur Render
app = Flask(__name__)

@app.route('/')
def home():
    """Point de terminaison simple pour vérifier que le serveur est actif."""
    return "Poxel Bot est actif !"

def run_flask_server():
    """Fonction pour lancer le serveur Flask."""
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# Lancer le serveur Flask dans un thread séparé
flask_thread = Thread(target=run_flask_server)
flask_thread.start()

# Variables d'environnement
# Assurez-vous d'avoir un fichier .env ou de configurer vos variables d'environnement sur Render.
# DISCORD_TOKEN = Votre token Discord
# FIREBASE_CREDENTIALS = La clé JSON de votre compte de service Firebase
# GIF_URL = URL d'un GIF rétro pour les embeds
# Pour des raisons de sécurité, nous lisons les clés depuis l'environnement.
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
FIREBASE_CREDENTIALS_JSON_STRING = os.getenv('FIREBASE_CREDENTIALS')
GIF_URL = os.getenv('GIF_URL', 'https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYzFlajVsaHgyd2l0YXc5NWdwN3Z5a201M2ZlMGZkYWJjb3F3ZzVtNiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LvtL8l1i0qR0B9bC2E/giphy.gif') # Exemple de GIF rétro

# Initialisation de Firebase
try:
    if FIREBASE_CREDENTIALS_JSON_STRING is None:
        print("Erreur d'initialisation de Firebase : La variable d'environnement 'FIREBASE_CREDENTIALS' est manquante ou vide.")
        exit()

    if not firebase_admin._apps:
        # CORRECTION ICI : On parse la chaîne JSON en un dictionnaire.
        cred = credentials.Certificate(json.loads(FIREBASE_CREDENTIALS_JSON_STRING))
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Erreur d'initialisation de Firebase : {e}")
    exit()

# Initialisation du bot Discord
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Classes de Boutons et de Modals pour l'interface utilisateur ---

class EventModal(ui.Modal, title="Inscription à l'événement"):
    """Fenêtre modale pour demander le pseudo du participant."""
    pseudo = ui.TextInput(label="Votre pseudo en jeu", style=discord.TextStyle.short, min_length=1, max_length=32)

    def __init__(self, bot, event_name, event_data, event_message):
        super().__init__()
        self.bot = bot
        self.event_name = event_name
        self.event_data = event_data
        self.event_message = event_message

    async def on_submit(self, interaction: Interaction):
        """Action lorsque le modal est soumis."""
        user_id = str(interaction.user.id)
        pseudo = self.pseudo.value

        # Ajoute le participant à la liste
        self.event_data['participants'][user_id] = pseudo
        doc_ref = db.collection('events').document(self.event_name)
        await interaction.response.send_message(f"Inscription réussie, {interaction.user.mention} ! Votre pseudo en jeu est `{pseudo}`.", ephemeral=True, delete_after=120)

        # Mise à jour de la base de données
        await doc_ref.set(self.event_data)

        # Met à jour l'embed de l'événement
        await self.bot.get_cog("EventManager").update_event_embed(self.event_data, self.event_message)

class EventButtons(ui.View):
    """Vue contenant les boutons d'inscription et de désinscription."""
    def __init__(self, bot, event_name, event_data):
        super().__init__(timeout=None)
        self.bot = bot
        self.event_name = event_name
        self.event_data = event_data
        self.max_participants = int(self.event_data['max_participants'])

    def update_buttons(self):
        """Met à jour l'état des boutons en fonction du nombre de participants."""
        current_participants = len(self.event_data['participants'])
        start_button = self.children[0]
        
        if current_participants >= self.max_participants:
            start_button.disabled = True
            start_button.label = "INSCRIPTION CLOS"
            start_button.style = ButtonStyle.gray
        else:
            start_button.disabled = False
            start_button.label = "START"
            start_button.style = ButtonStyle.green

    @ui.button(label="START", style=ButtonStyle.green, custom_id="start_event")
    async def start_button(self, interaction: Interaction, button: ui.Button):
        """Bouton pour s'inscrire à l'événement."""
        user_id = str(interaction.user.id)

        if user_id in self.event_data['participants']:
            await interaction.response.send_message("Vous êtes déjà inscrit !", ephemeral=True, delete_after=120)
            return
        
        if len(self.event_data['participants']) >= self.max_participants:
            await interaction.response.send_message("Le nombre maximum de participants est atteint.", ephemeral=True, delete_after=120)
            return

        modal = EventModal(self.bot, self.event_name, self.event_data, interaction.message)
        await interaction.response.send_modal(modal)

    @ui.button(label="QUIT", style=ButtonStyle.red, custom_id="quit_event")
    async def quit_button(self, interaction: Interaction, button: ui.Button):
        """Bouton pour se désinscrire de l'événement."""
        user_id = str(interaction.user.id)
        if user_id not in self.event_data['participants']:
            await interaction.response.send_message("Vous n'êtes pas inscrit à cet événement.", ephemeral=True, delete_after=120)
            return
        
        # Supprime le participant
        del self.event_data['participants'][user_id]
        doc_ref = db.collection('events').document(self.event_name)
        await doc_ref.set(self.event_data)
        
        await interaction.response.send_message("Vous vous êtes désinscrit de l'événement.", ephemeral=True, delete_after=120)
        
        # Met à jour l'embed de l'événement
        await self.bot.get_cog("EventManager").update_event_embed(self.event_data, interaction.message)


# --- Cogs du Bot ---

class EventManager(commands.Cog):
    """Cog principal pour la gestion des événements et des concours."""
    def __init__(self, bot):
        self.bot = bot
        self.active_events = {}  # Cache en mémoire des événements actifs
        self.event_checker.start()
        self.contest_checker.start()
        
    def cog_unload(self):
        """Arrête les tâches en boucle lors du déchargement du cog."""
        self.event_checker.cancel()
        self.contest_checker.cancel()

    async def get_event_embed(self, event_data, title_prefix="NEW EVENT:"):
        """Crée et retourne un embed stylisé pour un événement."""
        event_name = event_data['name']
        start_time_str = event_data['start_time']
        duration_minutes = event_data['duration_minutes']
        max_participants = event_data['max_participants']
        participants = event_data['participants']
        announcement_channel_id = event_data['announcement_channel']
        waiting_room_channel_id = event_data['waiting_room_channel']
        status = event_data['status']
        
        start_time = datetime.fromisoformat(start_time_str)
        end_time = start_time + timedelta(minutes=duration_minutes)
        now = datetime.now()

        # Calcul du temps restant
        if status == 'created' and now < start_time:
            time_left = start_time - now
            time_string = f"Démarre dans {time_left.days}j {time_left.seconds // 3600}h {(time_left.seconds % 3600) // 60}m {time_left.seconds % 60}s"
            color = 0x6441a5
        elif status == 'started' and now < end_time:
            time_left = end_time - now
            time_string = f"Fini dans {time_left.days}j {time_left.seconds // 3600}h {(time_left.seconds % 3600) // 60}m {time_left.seconds % 60}s"
            color = 0x027afa
        elif status == 'ended':
            time_since_end = now - end_time
            time_string = f"FINI IL Y A {time_since_end.days}j {time_since_end.seconds // 3600}h {(time_since_end.seconds % 3600) // 60}m {time_since_end.seconds % 60}s"
            color = 0x808080
        else:
            time_string = "Statut indéfini"
            color = 0x808080
            
        # Création de la liste des participants
        participants_list = ""
        if participants:
            for user_id, pseudo in participants.items():
                participants_list += f"<@{user_id}> ({pseudo})\n"
        else:
            participants_list = "Aucun participant pour l'instant..."

        embed = Embed(title=f"{title_prefix} {event_name}", color=color)
        embed.set_image(url=GIF_URL)
        embed.add_field(name="Détails de l'événement", value=f"""
- **Heure de début :** `{start_time.strftime('%Y-%m-%d %H:%M')}`
- **Durée :** `{duration_minutes} minutes`
- **Participants :** `{len(participants)}/{max_participants}`
- **Temps restant :** `{time_string}`
        """, inline=False)
        
        waiting_room = self.bot.get_channel(waiting_room_channel_id)
        embed.add_field(name="POINT DE RALLIEMENT", value=waiting_room.mention if waiting_room else "Salon introuvable", inline=False)
        
        embed.add_field(name="Participants inscrits", value=participants_list if participants_list else "Aucun participant pour l'instant.", inline=False)
        
        return embed

    async def update_event_embed(self, event_data, event_message):
        """Met à jour un embed d'événement existant avec les nouvelles données."""
        try:
            embed = await self.get_event_embed(event_data)
            view = EventButtons(self.bot, event_data['name'], event_data)
            view.update_buttons()
            await event_message.edit(embed=embed, view=view)
        except (HTTPException, NotFound) as e:
            print(f"Impossible de mettre à jour l'embed de l'événement {event_data['name']}: {e}")

    @commands.command(name='create_event', help="Crée un événement pour le jour même.")
    @commands.has_permissions(administrator=True)
    async def create_event(self, ctx, start_time_str, duration_str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, max_participants: int, event_participants: str, *, event_name: str):
        """Crée un événement pour le jour même."""
        try:
            now = datetime.now(tz=None)
            today_date = now.strftime('%Y-%m-%d')
            full_start_time_str = f"{today_date} {start_time_str}"
            start_time = datetime.strptime(full_start_time_str, '%Y-%m-%d %Hh%M')
            
            if start_time < now:
                await ctx.send("L'heure de début ne peut pas être dans le passé.", delete_after=120)
                return

            event_ref = db.collection('events').document(event_name)
            event_doc = await event_ref.get()
            if event_doc.exists:
                await ctx.send(f"Un événement avec le nom '{event_name}' existe déjà.", delete_after=120)
                return

            duration_minutes = int(duration_str.replace('min', '').replace('h', '')) # Simple parsing

            event_data = {
                'name': event_name,
                'start_time': start_time.isoformat(),
                'duration_minutes': duration_minutes,
                'role_id': role.id,
                'announcement_channel': announcement_channel.id,
                'waiting_room_channel': waiting_room_channel.id,
                'max_participants': max_participants,
                'participants': {},
                'status': 'created',
                'message_id': None
            }

            embed = await self.get_event_embed(event_data)
            view = EventButtons(self.bot, event_name, event_data)
            
            announcement_msg = await announcement_channel.send("@everyone", embed=embed, view=view)
            event_data['message_id'] = announcement_msg.id
            
            await event_ref.set(event_data)
            await ctx.send(f"L'événement '{event_name}' a été créé et annoncé. ", delete_after=120)
            await ctx.message.delete()
        except Exception as e:
            await ctx.send(f"Erreur lors de la création de l'événement : {e}", delete_after=120)

    @commands.command(name='create_event_plan', help="Planifie un événement pour une date future.")
    @commands.has_permissions(administrator=True)
    async def create_event_plan(self, ctx, date_str, start_time_str, duration_str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, max_participants: int, event_participants: str, *, event_name: str):
        """Planifie un événement pour une date future."""
        # Logique similaire à create_event, mais avec une gestion de date
        # Ici, j'ai simplifié, mais une gestion robuste des dates est nécessaire (ex: dateutil)
        try:
            full_start_time_str = f"{date_str} {start_time_str}"
            start_time = datetime.strptime(full_start_time_str, '%Y-%m-%d %Hh%M')
            now = datetime.now()

            if start_time < now:
                await ctx.send("L'événement ne peut pas être planifié dans le passé.", delete_after=120)
                return
            
            event_ref = db.collection('events').document(event_name)
            event_doc = await event_ref.get()
            if event_doc.exists:
                await ctx.send(f"Un événement avec le nom '{event_name}' existe déjà.", delete_after=120)
                return
            
            duration_minutes = int(duration_str.replace('min', '').replace('h', ''))

            event_data = {
                'name': event_name,
                'start_time': start_time.isoformat(),
                'duration_minutes': duration_minutes,
                'role_id': role.id,
                'announcement_channel': announcement_channel.id,
                'waiting_room_channel': waiting_room_channel.id,
                'max_participants': max_participants,
                'participants': {},
                'status': 'created',
                'message_id': None
            }
            
            embed = await self.get_event_embed(event_data)
            view = EventButtons(self.bot, event_name, event_data)

            announcement_msg = await announcement_channel.send("@everyone", embed=embed, view=view)
            event_data['message_id'] = announcement_msg.id
            
            await event_ref.set(event_data)
            await ctx.send(f"L'événement '{event_name}' a été planifié pour le {start_time.strftime('%Y-%m-%d')}.", delete_after=120)
            await ctx.message.delete()
        except Exception as e:
            await ctx.send(f"Erreur lors de la planification de l'événement : {e}", delete_after=120)

    @commands.command(name='end_event', help="Termine un événement manuellement.")
    @commands.has_permissions(administrator=True)
    async def end_event(self, ctx, *, event_name: str):
        """Termine un événement manuellement."""
        doc_ref = db.collection('events').document(event_name)
        doc = await doc_ref.get()
        
        if not doc.exists:
            await ctx.send(f"L'événement '{event_name}' n'existe pas.", delete_after=120)
            return

        event_data = doc.to_dict()
        event_data['status'] = 'ended'
        await doc_ref.set(event_data)
        
        # Logique de fin d'événement (suppression de rôles, etc.)
        await self.end_event_process(event_data)
        await ctx.send(f"L'événement '{event_name}' a été terminé manuellement.", delete_after=120)
        await ctx.message.delete()

    @commands.command(name='tirage', help="Effectue un tirage au sort parmi les participants.")
    @commands.has_permissions(administrator=True)
    async def tirage(self, ctx, *, event_name: str):
        """Effectue un tirage au sort parmi les participants d'un événement."""
        doc_ref = db.collection('events').document(event_name)
        doc = await doc_ref.get()
        
        if not doc.exists:
            await ctx.send(f"L'événement '{event_name}' n'existe pas.", delete_after=120)
            return

        event_data = doc.to_dict()
        participants = list(event_data['participants'].keys())
        
        if not participants:
            await ctx.send("Il n'y a pas de participants pour ce tirage.", delete_after=120)
            return
            
        winner_id = random.choice(participants)
        winner = self.bot.get_user(int(winner_id))
        
        embed = Embed(
            title=f"🎉 Tirage au sort pour l'événement '{event_name}' 🎉",
            description=f"Le grand gagnant est... {winner.mention} !",
            color=0x027afa
        )
        await ctx.send(embed=embed)
        await ctx.message.delete()

    @commands.command(name='concours', help="Crée un concours.")
    @commands.has_permissions(administrator=True)
    async def concours(self, ctx, end_date_str, *, contest_name: str):
        """Crée un concours avec une date de fin et effectue un tirage au sort."""
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            now = datetime.now()

            if end_date < now:
                await ctx.send("La date de fin ne peut pas être dans le passé.", delete_after=120)
                return

            contest_ref = db.collection('contests').document(contest_name)
            contest_doc = await contest_ref.get()
            if contest_doc.exists:
                await ctx.send(f"Un concours avec le nom '{contest_name}' existe déjà.", delete_after=120)
                return

            contest_data = {
                'name': contest_name,
                'end_date': end_date.isoformat(),
                'participants': [],
                'status': 'created'
            }

            # TODO: Implémenter l'ajout de participants au concours
            # Pour l'instant, le bot va juste annoncer le concours.
            
            await contest_ref.set(contest_data)
            await ctx.send(f"@everyone Un nouveau concours a été créé : **'{contest_name}'** ! Fin des inscriptions le **{end_date.strftime('%Y-%m-%d')}**.")
            await ctx.message.delete()

        except Exception as e:
            await ctx.send(f"Erreur lors de la création du concours : {e}", delete_after=120)

    @commands.command(name='helpoxel', help="Affiche l'aide sur les commandes.")
    async def help_command(self, ctx, *, command_name: str = None):
        """Affiche l'aide détaillée pour une commande spécifique ou la liste complète."""
        await ctx.message.delete()
        if command_name:
            command = self.bot.get_command(command_name)
            if not command:
                msg = await ctx.send(f"La commande '{command_name}' n'existe pas.", delete_after=120)
            else:
                embed = Embed(
                    title=f"Aide pour la commande `{command.name}`",
                    description=command.help,
                    color=0x027afa
                )
                embed.add_field(name="Syntaxe", value=f"`{bot.command_prefix}{command.name} {command.signature}`", inline=False)
                msg = await ctx.send(embed=embed, delete_after=120)
        else:
            embed = Embed(
                title="MANUEL DE POXEL",
                description="Voici la liste des commandes disponibles :",
                color=0x6441a5
            )
            for command in self.bot.commands:
                if not command.hidden:
                    embed.add_field(name=f"`!{command.name}`", value=command.help or "Pas de description.", inline=True)
            msg = await ctx.send(embed=embed, delete_after=120)
    
    @commands.command(name='check_admin_rights', help="Vérifie si vous avez les droits d'administration sur le bot.")
    @commands.has_permissions(administrator=True)
    async def check_admin_rights(self, ctx):
        """Vérifie si l'utilisateur a les droits d'administration."""
        msg = await ctx.send("Vous avez les droits d'administration sur Poxel.", delete_after=120)
        await ctx.message.delete()

    @check_admin_rights.error
    async def check_admin_rights_error(self, ctx, error):
        """Gère l'erreur de permission pour la commande de vérification."""
        if isinstance(error, commands.MissingPermissions):
            msg = await ctx.send("Vous n'avez pas les droits d'administration pour utiliser Poxel.", delete_after=120)
            await ctx.message.delete()

    async def end_event_process(self, event_data):
        """Processus de fin d'événement."""
        event_name = event_data['name']
        role_id = event_data['role_id']
        participants = event_data['participants']
        message_id = event_data['message_id']
        announcement_channel_id = event_data['announcement_channel']
        
        announcement_channel = self.bot.get_channel(announcement_channel_id)
        if not announcement_channel:
            return
        
        # Retirer le rôle à tous les participants
        role = announcement_channel.guild.get_role(role_id)
        if role:
            for user_id in participants.keys():
                member = announcement_channel.guild.get_member(int(user_id))
                if member:
                    try:
                        await member.remove_roles(role)
                    except HTTPException:
                        pass # Gérer si le bot n'a pas les droits
        
        # Supprimer le message d'embed
        try:
            message_to_delete = await announcement_channel.fetch_message(message_id)
            await message_to_delete.delete()
        except (HTTPException, NotFound):
            pass

        # Annonce de fin d'événement
        await announcement_channel.send(f"@everyone L'événement **'{event_name}'** est terminé. Merci à tous les participants !")

        # Supprimer l'événement de la base de données
        await db.collection('events').document(event_name).delete()


    # Tâche en arrière-plan pour gérer les événements en temps réel
    @tasks.loop(seconds=15)
    async def event_checker(self):
        """Vérifie l'état de tous les événements actifs et planifiés."""
        docs = db.collection('events').where('status', 'in', ['created', 'started']).stream()
        now = datetime.now()
        
        async for doc in docs:
            event_data = doc.to_dict()
            event_name = doc.id
            start_time = datetime.fromisoformat(event_data['start_time'])
            duration_minutes = event_data['duration_minutes']
            end_time = start_time + timedelta(minutes=duration_minutes)
            
            message_id = event_data.get('message_id')
            announcement_channel_id = event_data.get('announcement_channel')
            if not message_id or not announcement_channel_id:
                continue

            announcement_channel = self.bot.get_channel(announcement_channel_id)
            if not announcement_channel:
                continue
            
            try:
                event_message = await announcement_channel.fetch_message(message_id)
                # Met à jour l'embed en temps réel
                await self.update_event_embed(event_data, event_message)
            except (HTTPException, NotFound):
                # Le message a peut-être été supprimé, on le recrée
                # Pour éviter cela, l'embed ne devrait être supprimé qu'à la fin
                pass

            # Gestion des phases d'événement
            if event_data['status'] == 'created':
                # Rappel 30 minutes avant
                if start_time - now <= timedelta(minutes=30) and 'reminded_30' not in event_data:
                    await announcement_channel.send(f"@everyone Rappel : l'événement **'{event_name}'** démarre dans moins de 30 minutes. Dernières inscriptions !")
                    event_data['reminded_30'] = True
                    db.collection('events').document(event_name).set(event_data)
                
                # Début de l'événement
                if now >= start_time:
                    event_data['status'] = 'started'
                    db.collection('events').document(event_name).set(event_data)
                    
                    role = announcement_channel.guild.get_role(event_data['role_id'])
                    participants = event_data['participants']
                    
                    # Attribution des rôles et envoi des DMs
                    for user_id in participants.keys():
                        member = announcement_channel.guild.get_member(int(user_id))
                        if member and role:
                            try:
                                await member.add_roles(role)
                                await member.send(f"Félicitations, vous êtes inscrit à l'événement '{event_name}' ! Le rôle '{role.name}' vous a été attribué. Rendez-vous dans le salon {announcement_channel.guild.get_channel(event_data['waiting_room_channel']).mention} pour commencer.")
                            except HTTPException:
                                pass

                    # Annonce du début de l'événement
                    await announcement_channel.send(f"@everyone L'événement **'{event_name}'** a commencé ! Rendez-vous dans le salon <#{event_data['waiting_room_channel']}>.")
                    # L'embed ne sera pas supprimé ici, il se mettra à jour pour afficher le temps restant avant la fin.

            elif event_data['status'] == 'started' and now >= end_time:
                # Fin de l'événement
                event_data['status'] = 'ended'
                db.collection('events').document(event_name).set(event_data)
                await self.end_event_process(event_data)

    # Tâche en arrière-plan pour gérer les concours
    @tasks.loop(minutes=10)
    async def contest_checker(self):
        """Vérifie la fin des concours et effectue les tirages."""
        # Logique pour les concours
        pass # À implémenter

    @event_checker.before_loop
    async def before_event_checker(self):
        await self.bot.wait_until_ready()

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user.name}')
    await bot.add_cog(EventManager(bot))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("Vous n'avez pas la permission d'utiliser cette commande.", delete_after=120)
    else:
        print(f"Erreur de commande : {error}")
        await ctx.send(f"Une erreur est survenue : {error}", delete_after=120)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
