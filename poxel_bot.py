import discord
import asyncio
import os
import json
import re
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, firestore
from discord.ext import commands
import pytz # Import du module pour la gestion des fuseaux horaires

# Initialisation de Firebase
try:
    firebase_config = json.loads(os.getenv('__firebase_config'))
    cred = credentials.Certificate(firebase_config)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Erreur d'initialisation de Firebase: {e}. Le bot ne fonctionnera pas correctement.")
    db = None

# Configuration du bot Discord
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Constantes pour les collections Firestore
APP_ID = os.getenv('__app_id', 'default-app-id')
COLLECTION_PATH = f"artifacts/{APP_ID}/public/data/events"

# Définition du fuseau horaire local (pour la France)
timezone_local = pytz.timezone('Europe/Paris')

# --- Classes de Boutons (Views) ---
class ParticipateButton(discord.ui.View):
    """
    Vue contenant les boutons pour participer et quitter un événement.
    Gère la désactivation et le changement de label du bouton d'inscription
    lorsque la limite de participants est atteinte.
    """
    def __init__(self, event_id: str, participant_limit: int):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.participant_limit = participant_limit

    def update_button_state(self, participants_count: int):
        """
        Met à jour l'état du bouton 'start' en fonction du nombre de participants.
        """
        participate_button = discord.utils.get(self.children, custom_id="participate_button")
        if not participate_button:
            return

        if self.participant_limit > 0 and participants_count >= self.participant_limit:
            participate_button.label = "Inscription fermée"
            participate_button.style = discord.ButtonStyle.gray
            participate_button.disabled = True
        else:
            participate_button.label = "start"
            participate_button.style = discord.ButtonStyle.green
            participate_button.disabled = False
            

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        """Gère les erreurs lors de l'interaction avec le bouton."""
        print(f"Une erreur est survenue dans ParticipateButton: {error}")
        await interaction.response.send_message("Une erreur s'est produite lors de l'action. Veuillez réessayer plus tard.", ephemeral=True)

    @discord.ui.button(label="start", style=discord.ButtonStyle.green, custom_id="participate_button")
    async def participate_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback pour l'action de participer."""
        if not db:
            await interaction.response.send_message("Le bot n'est pas connecté à la base de données.", ephemeral=True)
            return

        events_ref = db.collection(COLLECTION_PATH)
        event_doc = events_ref.document(self.event_id).get()

        if not event_doc.exists:
            await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            return
        
        event_data = event_doc.to_dict()
        user_id = str(interaction.user.id)
        
        participants = event_data.get('participants', [])
        
        if user_id in participants:
            await interaction.response.send_message("Vous êtes déjà inscrit pour cet événement.", ephemeral=True)
            return
        
        if self.participant_limit > 0 and len(participants) >= self.participant_limit:
            await interaction.response.send_message("Désolé, la limite de participants a été atteinte.", ephemeral=True)
            return

        participants.append(user_id)
        events_ref.document(self.event_id).update({'participants': participants})
        await interaction.response.send_message("Vous êtes maintenant inscrit !", ephemeral=True)
        
        # Mise à jour de l'embed pour afficher le nouveau nombre de participants
        embed = interaction.message.embeds[0]
        participants_field = embed.fields[-1]
        participants_field.value = f"{len(participants)}/{self.participant_limit}" if self.participant_limit > 0 else f"{len(participants)}"
        
        # Mise à jour de l'état du bouton
        self.update_button_state(len(participants))
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="quit", style=discord.ButtonStyle.red, custom_id="leave_button")
    async def leave_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback pour l'action de quitter."""
        if not db:
            await interaction.response.send_message("Le bot n'est pas connecté à la base de données.", ephemeral=True)
            return

        events_ref = db.collection(COLLECTION_PATH)
        event_doc = events_ref.document(self.event_id).get()

        if not event_doc.exists:
            await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True)
            return
        
        event_data = event_doc.to_dict()
        user_id = str(interaction.user.id)
        
        participants = event_data.get('participants', [])
        
        if user_id not in participants:
            await interaction.response.send_message("Vous n'êtes pas inscrit à cet événement.", ephemeral=True)
            return
        
        participants.remove(user_id)
        events_ref.document(self.event_id).update({'participants': participants})
        await interaction.response.send_message("Vous avez quitté l'événement.", ephemeral=True)
        
        # Mise à jour de l'embed pour afficher le nouveau nombre de participants
        embed = interaction.message.embeds[0]
        participants_field = embed.fields[-1]
        participants_field.value = f"{len(participants)}/{self.participant_limit}" if self.participant_limit > 0 else f"{len(participants)}"
        
        # Mise à jour de l'état du bouton
        self.update_button_state(len(participants))
        await interaction.message.edit(embed=embed, view=self)

# --- Fonctions de création d'événement (aide) ---
async def create_event_core(ctx, event_name: str, description: str, start_time: datetime, duration: timedelta, role: discord.Role, announcement_channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, participant_limit: int):
    """
    Fonction principale pour créer et stocker un événement dans Firebase.
    """
    if not db:
        await ctx.send("Le bot n'est pas connecté à la base de données.")
        return

    end_time = start_time + duration
    
    # Crée un document temporaire pour obtenir l'ID
    temp_doc_ref = db.collection(COLLECTION_PATH).document()
    doc_id = temp_doc_ref.id

    new_event = {
        'name': event_name,
        'description': description,
        'announcement_channel_id': announcement_channel.id,
        'waiting_room_channel_id': waiting_room_channel.id,
        'start_time': start_time,
        'end_time': end_time,
        'role_id': role.id,
        'participant_limit': participant_limit,
        'participants': [],
        'start_announced': False,
        'end_announced': False,
        'message_id': None, # Sera mis à jour après l'envoi
        'guild_id': ctx.guild.id
    }
    
    # Création de l'embed avec le message détaillé
    embed = discord.Embed(title=f"Nouvel événement : {event_name}", description=f"**CLIQUEZ SUR LE BOUTON POUR PARTICIPER !**\n\n{description}", color=discord.Color.blue())
    embed.add_field(name="Rôle à obtenir", value=role.mention, inline=False)
    embed.add_field(name="Salon d'annonce", value=announcement_channel.mention, inline=True)
    embed.add_field(name="Salle d'attente", value=waiting_room_channel.mention, inline=True)
    
    # Ajout du champ pour le minuteur dynamique
    embed.add_field(name="Début dans", value="Actualisation...", inline=False)

    if participant_limit > 0:
        embed.add_field(name="Limite de participants", value=participant_limit, inline=True)
        embed.add_field(name="Participants", value="0/"+str(participant_limit), inline=True)
    else:
        embed.add_field(name="Participants", value="0", inline=True)
        
    embed.add_field(name="Fin", value=f"<t:{int(end_time.timestamp())}:f> (<t:{int(end_time.timestamp())}:R>)", inline=False)
    embed.set_footer(text="En cliquant sur 'start', vous obtiendrez le rôle au début de l'événement. Vous pouvez quitter à tout moment en cliquant sur 'quit'.")
    
    # Envoi du message et mise à jour de l'ID du message dans la base de données
    message = await ctx.send(embed=embed, view=ParticipateButton(doc_id, participant_limit))
    new_event['message_id'] = message.id
    
    # Enregistre le document avec le message_id
    temp_doc_ref.set(new_event)
    await ctx.send(f"L'événement '{event_name}' a été créé avec succès et est maintenant suivi.")

# --- Boucle de vérification automatique (toutes les 1 seconde) ---
async def update_events_loop():
    """
    Cette boucle vérifie les événements toutes les secondes et gère leur cycle de vie.
    """
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            if db:
                events_ref = db.collection(COLLECTION_PATH)
                docs = events_ref.stream()
                
                now = datetime.now(timezone.utc)
                
                for doc in docs:
                    event = doc.to_dict()
                    event_id = doc.id
                    
                    # Convertit les timestamps Firestore en objets datetime conscients du fuseau horaire
                    start_time = event['start_time'].replace(tzinfo=timezone.utc)
                    end_time = event['end_time'].replace(tzinfo=timezone.utc)
                    
                    # Logique pour le début de l'événement
                    if now >= start_time and not event.get('start_announced', False):
                        announcement_channel = bot.get_channel(event['announcement_channel_id'])
                        if announcement_channel:
                            role = discord.utils.get(announcement_channel.guild.roles, id=event['role_id'])
                            if role:
                                for user_id in event.get('participants', []):
                                    member = announcement_channel.guild.get_member(int(user_id))
                                    if member:
                                        await member.add_roles(role)
                            
                            await announcement_channel.send(f"@everyone L'événement **{event['name']}** est sur le point de commencer !")
                            events_ref.document(event_id).update({'start_announced': True})
                            
                    # Logique pour la fin de l'événement
                    if now >= end_time and not event.get('end_announced', False):
                        announcement_channel = bot.get_channel(event['announcement_channel_id'])

                        if announcement_channel:
                            role = discord.utils.get(announcement_channel.guild.roles, id=event['role_id'])
                            if role:
                                for user_id in event.get('participants', []):
                                    member = announcement_channel.guild.get_member(int(user_id))
                                    if member:
                                        await member.remove_roles(role)

                            await announcement_channel.send(f"L'événement **{event['name']}** est maintenant terminé. Merci à tous d'avoir participé !")
                            events_ref.document(event_id).update({'end_announced': True})
                        
                        # Suppression de l'événement de la base de données
                        events_ref.document(event_id).delete()

        except Exception as e:
            print(f"Une erreur est survenue dans la boucle de vérification : {e}")

        await asyncio.sleep(1) # Actualisation toutes les secondes

# --- Boucle pour le minuteur dynamique ---
async def update_embed_timers_loop():
    """
    Cette boucle met à jour le minuteur dans les embeds d'événements actifs toutes les secondes.
    """
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            if db:
                events_ref = db.collection(COLLECTION_PATH)
                docs = events_ref.stream()
                
                now = datetime.now(timezone.utc)

                for doc in docs:
                    event = doc.to_dict()
                    event_id = doc.id
                    
                    # Convertit les timestamps Firestore en objets datetime conscients du fuseau horaire
                    start_time = event['start_time'].replace(tzinfo=timezone.utc)
                    end_time = event['end_time'].replace(tzinfo=timezone.utc)
                    message_id = event['message_id']
                    channel_id = event['announcement_channel_id']
                    
                    if not message_id or not channel_id:
                        continue

                    channel = bot.get_channel(channel_id)
                    if not channel:
                        continue

                    try:
                        message = await channel.fetch_message(message_id)
                        embed = message.embeds[0]
                        view = ParticipateButton(event_id, event['participant_limit'])
                        view.update_button_state(len(event.get('participants', [])))
                        
                        # Calcule le temps restant ou la durée écoulée
                        if now < start_time:
                            time_diff = start_time - now
                            days, seconds = time_diff.days, time_diff.seconds
                            hours = seconds // 3600
                            minutes = (seconds % 3600) // 60
                            seconds = seconds % 60
                            countdown_str = f"{days}j, {hours}h, {minutes}m, {seconds}s"
                            
                            embed.set_field_at(3, name="Début dans", value=countdown_str, inline=False)
                        else:
                            time_diff = now - start_time
                            days, seconds = time_diff.days, time_diff.seconds
                            hours = seconds // 3600
                            minutes = (seconds % 3600) // 60
                            seconds = seconds % 60
                            duration_str = f"{days}j, {hours}h, {minutes}m, {seconds}s"
                            
                            embed.set_field_at(3, name="Durée en cours", value=duration_str, inline=False)
                        
                        await message.edit(embed=embed, view=view)

                    except discord.NotFound:
                        print(f"Le message avec l'ID {message_id} n'a pas été trouvé. Il sera ignoré.")
                        continue
                    except IndexError:
                        print(f"L'embed du message {message_id} n'a pas la bonne structure.")
                        continue
                    
        except Exception as e:
            print(f"Une erreur est survenue dans la boucle de minuteur : {e}")

        await asyncio.sleep(1) # Actualisation toutes les secondes

# --- Commandes du Bot ---
@bot.command(name='create_event')
async def create_event(ctx, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, participant_limit: int, event_name: str, *, description: str):
    """
    Crée un événement avec une heure de début, une durée, un rôle, 2 salons, une limite de participants, un nom et une description.
    Exemple: !create_event 20:17 1h30m @Rôle #salon_annonce #salle_attente 15 "Nom de l'événement" "Description de l'événement."
    """
    # Parsing de la durée
    match = re.match(r'(?:(\d+)h)?(?:(\d+)m)?', duration_str)
    if not match:
        await ctx.send("Format de durée invalide. Utilisez '30m' ou '1h30m'.")
        return
    
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    duration = timedelta(hours=hours, minutes=minutes)
    if duration.total_seconds() <= 0:
        await ctx.send("La durée doit être supérieure à zéro.")
        return

    # Parsing de l'heure de début
    now_local = datetime.now(timezone_local)
    try:
        start_time_local_naive = datetime.strptime(start_time_str, '%H:%M').replace(year=now_local.year, month=now_local.month, day=now_local.day)
        start_time_local = timezone_local.localize(start_time_local_naive)
    except ValueError:
        await ctx.send("Format d'heure de début invalide. Utilisez 'HH:MM'.")
        return
    
    if start_time_local < now_local:
        start_time_local += timedelta(days=1)
        
    start_time_utc = start_time_local.astimezone(timezone.utc)
    
    await create_event_core(ctx, event_name, description, start_time_utc, duration, role, announcement_channel, waiting_room_channel, participant_limit)

@bot.command(name='create_event_plan')
async def create_event_plan(ctx, date_str: str, start_time_str: str, duration_str: str, role: discord.Role, announcement_channel: discord.TextChannel, waiting_room_channel: discord.TextChannel, participant_limit: int, event_name: str, *, description: str):
    """
    Crée un événement planifié avec une date, une heure de début, une durée, un rôle, 2 salons, une limite de participants, un nom et une description.
    Exemple: !create_event_plan 15/07/2025 20:17 1h30m @Rôle #salon_annonce #salle_attente 15 "Nom de l'événement" "Description de l'événement."
    """
    # Parsing de la durée
    match = re.match(r'(?:(\d+)h)?(?:(\d+)m)?', duration_str)
    if not match:
        await ctx.send("Format de durée invalide. Utilisez '30m' ou '1h30m'.")
        return
    
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    duration = timedelta(hours=hours, minutes=minutes)
    if duration.total_seconds() <= 0:
        await ctx.send("La durée doit être supérieure à zéro.")
        return

    # Parsing de la date et de l'heure de début
    try:
        event_date_naive = datetime.strptime(f'{date_str} {start_time_str}', '%d/%m/%Y %H:%M')
        start_time_local = timezone_local.localize(event_date_naive)
    except ValueError:
        await ctx.send("Format de date ou d'heure invalide. Utilisez 'JJ/MM/AAAA' et 'HH:MM'.")
        return
    
    start_time_utc = start_time_local.astimezone(timezone.utc)

    # Vérification que la date n'est pas dans le passé
    if start_time_utc < datetime.now(timezone.utc):
        await ctx.send("La date et l'heure de l'événement sont déjà passées. Veuillez planifier pour le futur.")
        return
    
    await create_event_core(ctx, event_name, description, start_time_utc, duration, role, announcement_channel, waiting_room_channel, participant_limit)

@bot.command(name='list_events')
async def list_events(ctx):
    if not db:
        await ctx.send("Le bot n'est pas connecté à la base de données.")
        return
    
    events_ref = db.collection(COLLECTION_PATH)
    docs = events_ref.stream()
    
    event_list = ""
    found_events = False
    for doc in docs:
        event = doc.to_dict()
        start_time_local = event['start_time'].astimezone(None)
        event_list += f"- **{event['name']}** (début : <t:{int(start_time_local.timestamp())}:f>, rôle: <@&{event['role_id']}>)\n"
        found_events = True
    
    if found_events:
        await ctx.send(f"Voici les événements actifs :\n{event_list}")
    else:
        await ctx.send("Il n'y a aucun événement actif.")

@bot.command(name='end_event')
async def end_event(ctx, *, event_name_to_end: str):
    if not db:
        await ctx.send("Le bot n'est pas connecté à la base de données.")
        return
    
    events_ref = db.collection(COLLECTION_PATH)
    # Recherche l'événement par son nom, comme demandé
    docs = events_ref.where('name', '==', event_name_to_end).stream()
    
    found_event = False
    for doc in docs:
        event_id = doc.id
        event_data = doc.to_dict()
        
        guild = bot.get_guild(event_data['guild_id'])
        if not guild:
            continue
            
        role = discord.utils.get(guild.roles, id=event_data['role_id'])
        if role:
            for user_id in event_data.get('participants', []):
                member = guild.get_member(int(user_id))
                if member:
                    await member.remove_roles(role)

        events_ref.document(event_id).delete()
        await ctx.send(f"L'événement '{event_name_to_end}' a été terminé manuellement.")
        found_event = True
        break
    
    if not found_event:
        await ctx.send(f"Aucun événement trouvé avec le nom '{event_name_to_end}'.")

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user}')
    # Démarre la boucle de vérification des événements et la boucle de minuteur
    bot.loop.create_task(update_events_loop())
    bot.loop.create_task(update_embed_timers_loop())

bot.run("YOUR_BOT_TOKEN")
