# -*- coding: utf-8 -*-
# --- INSTRUCTIONS POUR RENDER ---
# IMPORTANT : Ce code a été modifié pour inclure deux nouvelles commandes
# afin de gérer les événements planifiés.
# J'ai également ajouté une boucle de tâche en arrière-plan pour
# détecter et terminer automatiquement les événements expirés.

import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from datetime import datetime, timedelta
import asyncio
import os
import random
import re
import json
from dotenv import load_dotenv
import pytz # Import de la bibliothèque pour la gestion des fuseaux horaires
from typing import Optional
import threading # Pour démarrer le bot dans un thread séparé
from flask import Flask # Pour créer le serveur web minimal

# Import des bibliothèques Firebase
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Charger les variables d'environnement depuis le fichier .env (pour les tests locaux)
load_dotenv()

# Récupérer le token du bot depuis les variables d'environnement
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# --- Configuration Firebase ---
try:
    firebase_json_key = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY_JSON')
    if not firebase_json_key:
        # Tenter de charger le fichier local si la variable d'environnement n'est pas définie
        with open('serviceAccountKey.json') as f:
            service_account_info = json.load(f)
    else:
        service_account_info = json.loads(firebase_json_key)
    
    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialisé avec succès.")
except Exception as e:
    print(f"Erreur lors de l'initialisation de Firebase Admin SDK: {e}")
    print("Assure-toi que la variable d'environnement 'FIREBASE_SERVICE_ACCOUNT_KEY_JSON' est bien configurée ou que 'serviceAccountKey.json' est présent.")
    exit()

# Définir le préfixe de commande et les intents nécessaires
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True
intents.presences = True

# Initialiser le bot
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Fonctions Utilitaires ---

# Définir le fuseau horaire de Paris
PARIS_TIMEZONE = pytz.timezone('Europe/Paris')

def parse_duration(duration_str: str) -> int:
    """
    Parse une chaîne de durée (ex: "2h", "30m") en secondes.
    """
    total_seconds = 0
    matches = re.findall(r'(\d+)([hms])', duration_str.lower())

    if not matches:
        raise ValueError("Format de durée invalide. Utilisez '2h', '30m' ou une combinaison.")

    for value, unit in matches:
        value = int(value)
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
    return total_seconds

NEON_BLUE = 0x009EFF
NEON_RED = 0xFF073A
NEON_GREEN = 0x39FF14

def create_retro_embed(title, description="", color=NEON_BLUE):
    """Crée un embed avec un style simple."""
    embed = discord.Embed(
        title=f"{title.upper()}",
        description=description,
        color=color
    )
    embed.set_author(name="Poxel OS", icon_url="https://placehold.co/64x64/009eff/ffffff?text=P")
    embed.set_footer(text="Système d'événements Poxel")
    return embed

async def get_participant_info(guild: discord.Guild, participants_data: list) -> str:
    """
    Récupère les pseudos Discord et les pseudos en jeu des participants.
    """
    participant_list = []
    for p_data in participants_data:
        member = guild.get_member(p_data['user_id'])
        if member:
            alias = p_data.get('alias', '')
            participant_list.append(f"**{member.display_name}** ({alias})" if alias else f"**{member.display_name}**")
    if not participant_list:
        return "Aucun participant"
    return "\n".join(participant_list)


# --- Classes de vues et de boutons pour l'interaction utilisateur ---

class AliasModal(discord.ui.Modal, title='Inscription à l\'événement'):
    def __init__(self, event_firestore_id: str):
        super().__init__()
        self.event_firestore_id = event_firestore_id

    alias_input = discord.ui.TextInput(
        label="Votre pseudo en jeu (optionnel)",
        style=discord.TextStyle.short,
        placeholder="Ex: PoxelBot2025",
        required=False,
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        alias = self.alias_input.value
        user = interaction.user
        event_ref = db.collection('events').document(self.event_firestore_id)
        
        event_doc = await asyncio.to_thread(event_ref.get)
        
        if not event_doc.exists:
            await interaction.followup.send("Cet événement n'existe plus ou a été terminé.", ephemeral=True)
            return

        event_data = event_doc.to_dict()
        event_name = event_data.get('name', 'Nom inconnu')
        guild = interaction.guild
        role_id = event_data.get('role_id')
        role = guild.get_role(role_id) if role_id else None

        if not role:
            await interaction.followup.send("Le rôle associé à cet événement n'a pas été trouvé.", ephemeral=True)
            return

        participants_list = event_data.get('participants', [])
        max_participants = event_data.get('max_participants')
        
        is_already_in = any(p['user_id'] == user.id for p in participants_list)
        if is_already_in:
            await interaction.followup.send("Vous êtes déjà inscrit à cet événement.", ephemeral=True)
            return

        now = datetime.now(PARIS_TIMEZONE)
        start_time = event_data.get('start_time')
        
        if (max_participants and len(participants_list) >= max_participants) or \
           (start_time and start_time.astimezone(PARIS_TIMEZONE) <= now):
            await interaction.followup.send("Désolé, les inscriptions sont fermées.", ephemeral=True)
            return
        
        try:
            await user.add_roles(role, reason=f"Participation à l'événement {event_name}")
            
            new_participant_data = {'user_id': user.id, 'alias': alias}
            await asyncio.to_thread(event_ref.update, {'participants': firestore.ArrayUnion([new_participant_data])})
            
            await interaction.followup.send(f"Vous avez rejoint l'événement **'{event_name}'** !", ephemeral=True)
            
            channel_waiting_id = event_data.get('channel_waiting_id')
            if channel_waiting_id:
                channel_waiting = guild.get_channel(channel_waiting_id)
                if channel_waiting:
                    pseudo_msg = f"({alias})" if alias else ""
                    await channel_waiting.send(f"Bienvenue dans la partie **{user.display_name}** {pseudo_msg} !")
            
        except discord.Forbidden:
            await interaction.followup.send("Je n'ai pas les permissions nécessaires pour vous donner ce rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Une erreur est survenue lors de votre inscription : `{e}`", ephemeral=True)
            return
        
        updated_event_doc = await asyncio.to_thread(event_ref.get)
        if updated_event_doc.exists:
            await self.update_event_message(interaction, updated_event_doc.to_dict())

    async def update_event_message(self, interaction: discord.Interaction, event_data: dict):
        guild = interaction.guild
        participants = event_data.get('participants', [])
        max_participants = event_data.get('max_participants')
        participant_label = event_data.get('participant_label', 'participants')
        
        try:
            original_message = interaction.message
            if original_message:
                embed = original_message.embeds[0]
                
                participant_names = await get_participant_info(guild, participants)
                
                participants_field_index = -1
                for i, field in enumerate(embed.fields):
                    if "Participants" in field.name:
                        participants_field_index = i
                        break

                if participants_field_index != -1:
                    embed.set_field_at(
                        index=participants_field_index,
                        name=f"Participants ({len(participants)}/{max_participants} {participant_label})",
                        value=participant_names,
                        inline=False
                    )
                
                is_full = max_participants and len(participants) >= max_participants
                if is_full and not event_data.get('registrations_closed'):
                    channel_waiting = guild.get_channel(event_data.get('channel_waiting_id'))
                    if channel_waiting:
                        await channel_waiting.send(f"@everyone Les inscriptions pour l'événement **'{event_data.get('name', 'Nom inconnu')}'** sont complètes !")
                        await asyncio.to_thread(db.collection('events').document(self.event_firestore_id).update, {'registrations_closed': True})
                elif not is_full and event_data.get('registrations_closed'):
                    await asyncio.to_thread(db.collection('events').document(self.event_firestore_id).update, {'registrations_closed': False})

                view = EventButtons(self.event_firestore_id, is_full=is_full)
                await original_message.edit(embed=embed, view=view)
        except discord.NotFound:
            print(f"Erreur : Le message original de l'événement {event_data.get('name', 'nom inconnu')} n'a pas été trouvé. Il a peut-être été supprimé.")
        except Exception as e:
            print(f"Erreur lors de la mise à jour du message de l'événement : {e}")


class EventButtons(View):
    def __init__(self, event_firestore_id: str, is_full: bool = False):
        super().__init__(timeout=None)
        self.event_firestore_id = event_firestore_id
        
        join_button_style = discord.ButtonStyle.gray if is_full else discord.ButtonStyle.primary
        join_button_label = "Inscriptions fermées" if is_full else "START"

        join_button = Button(
            label=join_button_label, 
            style=join_button_style, 
            custom_id=f"join_event_{self.event_firestore_id}",
            disabled=False
        )
        join_button.callback = self.handle_join
        self.add_item(join_button)

        quit_button = Button(
            label="QUIT", 
            style=discord.ButtonStyle.red, 
            custom_id=f"quit_event_{self.event_firestore_id}"
        )
        quit_button.callback = self.handle_quit
        self.add_item(quit_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        event_ref = db.collection('events').document(self.event_firestore_id)
        event_doc = await asyncio.to_thread(event_ref.get)
        
        if not event_doc.exists:
            await interaction.response.send_message("Cet événement n'existe plus ou a été terminé.", ephemeral=True)
            return False
            
        event_data = event_doc.to_dict()
        participants_list = event_data.get('participants', [])
        max_participants = event_data.get('max_participants')
        
        if interaction.custom_id.startswith("join_event_"):
            if event_data.get('registrations_closed') or (max_participants and len(participants_list) >= max_participants):
                await interaction.response.send_message("Désolé, les inscriptions sont fermées.", ephemeral=True)
                return False
        
        return True

    async def handle_join(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AliasModal(self.event_firestore_id))

    async def handle_quit(self, interaction: discord.Interaction):
        user = interaction.user
        event_ref = db.collection('events').document(self.event_firestore_id)
        event_doc = await asyncio.to_thread(event_ref.get)
        
        if not event_doc.exists:
            await interaction.response.send_message("Cet événement n'existe plus ou a été terminé.", ephemeral=True)
            return

        event_data = event_doc.to_dict()
        event_name = event_data.get('name', 'Nom inconnu')
        guild = interaction.guild
        role_id = event_data.get('role_id')
        role = guild.get_role(role_id) if role_id else None

        participants_list = event_data.get('participants', [])
        
        is_in_event = any(p['user_id'] == user.id for p in participants_list)
        if not is_in_event:
            await interaction.response.send_message("Vous ne participez pas à cet événement.", ephemeral=True)
            return

        try:
            participant_to_remove = next((p for p in participants_list if p['user_id'] == user.id), None)
            
            if role:
                await user.remove_roles(role, reason=f"Quitte l'événement {event_name}")
            
            await asyncio.to_thread(event_ref.update, {'participants': firestore.ArrayRemove([participant_to_remove])})
            
            await interaction.response.send_message(f"Vous avez quitté l'événement **'{event_name}'**.", ephemeral=True)
            
            updated_event_doc = await asyncio.to_thread(event_ref.get)
            if updated_event_doc.exists:
                updated_data = updated_event_doc.to_dict()
                max_participants = updated_data.get('max_participants')
                current_participants_count = len(updated_data.get('participants', []))
                channel_waiting_id = updated_data.get('channel_waiting_id')

                if updated_data.get('registrations_closed') and max_participants is not None and current_participants_count < max_participants:
                    await asyncio.to_thread(event_ref.update, {'registrations_closed': False})
                    if channel_waiting_id:
                        channel_waiting = guild.get_channel(channel_waiting_id)
                        if channel_waiting:
                            await channel_waiting.send(f"@everyone Une place s'est libérée pour l'événement **'{event_name}'** ! Inscriptions réouvertes !")
            
                await AliasModal(self.event_firestore_id).update_event_message(interaction, updated_data)


        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour vous retirer ce rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue lors de votre désinscription : `{e}`", ephemeral=True)
            return
        

# --- Tâche de gestion des événements ---

async def _end_event(event_doc_id: str, context_channel: Optional[discord.TextChannel] = None):
    """
    Fonction interne pour terminer un événement, retirer les rôles et nettoyer.
    """
    event_ref = db.collection('events').document(event_doc_id)
    event_doc = await asyncio.to_thread(event_ref.get)

    if not event_doc.exists:
        print(f"Tentative de terminer un événement non existant dans Firestore : {event_doc_id}")
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild_id = event_data.get('guild_id')
    guild = bot.get_guild(guild_id) if guild_id else None
    
    if not guild:
        print(f"Guilde non trouvée pour l'événement {event_name} (ID: {event_doc_id}). Suppression de l'événement.")
        await asyncio.to_thread(event_ref.delete)
        return

    role_id = event_data.get('role_id')
    role = guild.get_role(role_id) if role_id else None
    channel_waiting_id = event_data.get('channel_waiting_id')
    channel_waiting = guild.get_channel(channel_waiting_id) if channel_waiting_id else None
    
    participants_list = event_data.get('participants', [])

    for p_data in participants_list:
        member = guild.get_member(p_data['user_id'])
        if member and role:
            try:
                await member.remove_roles(role, reason=f"Fin de l'événement {event_name}")
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour retirer le rôle {role.name} à {member.display_name}")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle à {member.display_name}: {e}")
    
    event_message = None
    try:
        message_id = event_data.get('message_id')
        if channel_waiting and message_id:
            event_message = await channel_waiting.fetch_message(message_id)
    except discord.NotFound:
        print(f"Erreur : Message de l'événement {event_name} non trouvé. Il a peut-être été supprimé.")
    except Exception as e:
        print(f"Erreur lors de la récupération du message de l'événement : {e}")
    
    if event_message:
        try:
            embed = create_retro_embed(f"ÉVÉNEMENT TERMINÉ : {event_name}", color=NEON_RED)
            
            participants_names = await get_participant_info(guild, participants_list)
            
            embed.add_field(name=f"Participants finaux ({len(participants_list)}/{event_data.get('max_participants', 'N/A')} {event_data.get('participant_label', 'participants')})", value=participants_names, inline=False)
            
            if channel_waiting:
                await channel_waiting.send(f"@everyone L'événement **'{event_name}'** est maintenant terminé. Merci à tous d'avoir participé !", delete_after=60)
            
            await event_message.edit(content=f"L'événement **'{event_name}'** est maintenant terminé.", embed=embed, view=None)
        except Exception as e:
            print(f"Erreur lors de la mise à jour du message de l'événement : {e}")
    else:
        if context_channel:
            try:
                await context_channel.send(f"L'événement **'{event_name}'** a été terminé, mais le message original a été supprimé. Les rôles ont été retirés aux participants.", delete_after=60)
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour envoyer un message dans le canal {context_channel.name}.")
            except Exception as e:
                print(f"Erreur lors de l'envoi du message de confirmation : {e}")
        
    await asyncio.to_thread(event_ref.delete)
    print(f"Événement '{event_name}' (ID: {event_doc_id}) supprimé de Firestore.")


@tasks.loop(seconds=60) # Vérifie les événements toutes les 60 secondes
async def check_for_expired_events():
    """Tâche en arrière-plan pour vérifier et terminer les événements expirés."""
    events_ref = db.collection('events')
    now = datetime.now(PARIS_TIMEZONE)
    
    active_events_docs = await asyncio.to_thread(events_ref.stream)
    
    for doc in active_events_docs:
        event_data = doc.to_dict()
        event_end_time = event_data.get('end_time')
        
        # Si la date de fin de l'événement est passée, on le termine
        if event_end_time and event_end_time.astimezone(PARIS_TIMEZONE) < now:
            print(f"Événement '{event_data.get('name', doc.id)}' expiré. Fin de l'événement...")
            await _end_event(doc.id)


@bot.event
async def on_ready():
    """Se déclenche lorsque le bot est connecté à Discord."""
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Prêt à gérer les événements !')
    # Démarre la boucle de vérification des événements
    check_for_expired_events.start()
    await setup_views()

@bot.event
async def on_command_error(ctx, error):
    """Gère les erreurs de commande."""
    try:
        await ctx.message.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        print(f"Erreur lors de la suppression du message de commande : {e}")

    if isinstance(error, commands.MissingRequiredArgument):
        msg = await ctx.send(f"Il manque un argument pour cette commande. Utilisation correcte : `!helpoxel {ctx.command}`.", delete_after=60)
    elif isinstance(error, commands.BadArgument):
        msg = await ctx.send(f"Argument invalide. Veuillez vérifier le format de vos arguments dans le manuel `!helpoxel {ctx.command}`.", delete_after=60)
    elif isinstance(error, commands.MissingPermissions):
        msg = await ctx.send("Vous n'avez pas les permissions nécessaires pour exécuter cette commande (Gérer les rôles).", delete_after=60)
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Erreur de commande : {error}")
        msg = await ctx.send(f"Une erreur inattendue s'est produite : `{error}`", delete_after=60)
    
    if 'msg' in locals():
        try:
            await asyncio.sleep(60)
            await msg.delete()
        except discord.NotFound:
            pass


@bot.command(name='helpoxel')
async def help_command(ctx, *, command_name: str = None):
    """Affiche le manuel d'aide de Poxel pour une commande spécifique."""
    
    try:
        await ctx.message.delete()
    except discord.NotFound:
        pass
    
    if command_name is None:
        embed = create_retro_embed("MANUEL DE POXEL")
        embed.description = "Je suis Poxel, votre assistant pour gérer les événements sur Discord. Pour plus de détails sur une commande, tapez `!helpoxel <nom_de_la_commande>`."

        commands_info = {
            "create_event": "Crée un événement immédiat.",
            "create_event_plan": "Crée un événement planifié.",
            "end_event": "Termine un événement en cours manuellement.",
            "list_events": "Affiche tous les événements actifs."
        }
        for name, desc in commands_info.items():
            embed.add_field(name=f"**!{name}**", value=desc, inline=False)
        
        msg = await ctx.send(embed=embed, delete_after=180)
        return

    command = bot.get_command(command_name)
    if command is None:
        msg = await ctx.send(f"La commande `!{command_name}` n'existe pas.", delete_after=60)
        return
    
    embed = create_retro_embed(f"MANUEL DE LA COMMANDE `!{command.name.upper()}`")
    embed.description = command.help

    if command.name == 'create_event':
        embed.add_field(name="Exemple", value="`!create_event @Joueur 1h30m #salon-attente #salon-prive 10 joueurs Partie de Donjons`", inline=False)
    elif command.name == 'create_event_plan':
        embed.add_field(name="Exemple", value="`!create_event_plan @Role 2h 25/12/2025 21h00 #salon-attente #salon-prive 10 joueurs Événement de Noël`", inline=False)
    elif command.name == 'end_event':
        embed.add_field(name="Exemple", value="`!end_event Ma Super Partie`", inline=False)
    elif command.name == 'list_events':
        embed.add_field(name="Exemple", value="`!list_events`", inline=False)

    msg = await ctx.send(embed=embed, delete_after=180)


@bot.command(name='create_event')
@commands.has_permissions(manage_roles=True)
async def create_event(
    ctx, 
    role: discord.Role,
    duration: str,
    channel_waiting: discord.TextChannel,
    channel_priv: discord.TextChannel,
    max_participants: int,
    participant_label: str,
    *,
    event_name: str
):
    """
    Crée un événement immédiat avec des paramètres spécifiques.
    Utilisation: `!create_event @rôle durée(ex: 2h) #salon-attente #salon-privé max_participants label nom_de_l_événement`
    """
    try:
        await ctx.message.delete()
    except discord.NotFound:
        pass

    try:
        duration_seconds = parse_duration(duration)
        now = datetime.now(PARIS_TIMEZONE)
        end_time = now + timedelta(seconds=duration_seconds)
        
        event_firestore_id = f"event_{ctx.guild.id}_{random.randint(1000, 9999)}_{now.timestamp()}"

        event_data = {
            'name': event_name,
            'role_id': role.id,
            'duration': duration,
            'start_time': now,
            'end_time': end_time,
            'channel_waiting_id': channel_waiting.id,
            'channel_priv_id': channel_priv.id,
            'guild_id': ctx.guild.id,
            'max_participants': max_participants,
            'participant_label': participant_label,
            'participants': [],
            'registrations_closed': False,
            'has_started': True, # C'est un événement immédiat, il est donc déjà "commencé"
        }

        embed = create_retro_embed(f"NOUVEL ÉVÉNEMENT : {event_name}")
        embed.description = f"Préparez-vous à une partie épique de {event_name} !"
        embed.add_field(name="Rôle requis", value=role.mention, inline=False)
        
        start_timestamp = int(now.timestamp())
        end_timestamp = int(end_time.timestamp())
        embed.add_field(name="Début / Fin", value=f"Début : <t:{start_timestamp}:f> (maintenant)\nFin : <t:{end_timestamp}:f> (se termine <t:{end_timestamp}:R>)", inline=False)
        
        embed.add_field(name="Salon d'attente", value=channel_waiting.mention, inline=True)
        embed.add_field(name="Salon de jeu", value=channel_priv.mention, inline=True)
        
        embed.add_field(
            name=f"Participants ({len(event_data['participants'])}/{max_participants} {participant_label})",
            value="Aucun participant",
            inline=False
        )

        is_full = max_participants and len(event_data['participants']) >= max_participants
        view = EventButtons(event_firestore_id, is_full=is_full)
        
        event_message = await channel_waiting.send(
            content=f"**Un nouvel événement a été lancé ! Rejoignez-le en cliquant sur le bouton ci-dessous !**",
            embed=embed,
            view=view
        )
        
        event_data['message_id'] = event_message.id
        await asyncio.to_thread(db.collection('events').document(event_firestore_id).set, event_data)
        
    except ValueError as ve:
        await ctx.send(f"Erreur : {ve}", delete_after=60)
    except Exception as e:
        await ctx.send(f"Une erreur est survenue lors de la création de l'événement : `{e}`", delete_after=60)
        print(f"Erreur de création d'événement : {e}")


@bot.command(name='create_event_plan')
@commands.has_permissions(manage_roles=True)
async def create_event_plan(
    ctx, 
    role: discord.Role,
    duration: str,
    date: str,
    heure: str,
    channel_waiting: discord.TextChannel,
    channel_priv: discord.TextChannel,
    max_participants: int,
    participant_label: str,
    *,
    event_name: str
):
    """
    Crée un événement planifié.
    Utilisation: `!create_event_plan @rôle durée(ex: 2h) DD/MM/YYYY HH:MM #salon-attente #salon-privé max_participants label nom_de_l_événement`
    """
    try:
        await ctx.message.delete()
    except discord.NotFound:
        pass

    try:
        duration_seconds = parse_duration(duration)
        start_time_str = f"{date} {heure}"
        # Parse la date/heure de l'utilisateur
        start_time_naive = datetime.strptime(start_time_str, '%d/%m/%Y %H:%M')
        # Met l'heure dans le fuseau horaire de Paris
        start_time_paris = PARIS_TIMEZONE.localize(start_time_naive)
        
        end_time_paris = start_time_paris + timedelta(seconds=duration_seconds)
        
        now = datetime.now(PARIS_TIMEZONE)
        
        if start_time_paris < now:
            await ctx.send("Waeky, l'heure de début de l'événement est dans le passé. Veuillez fournir une heure future.", delete_after=60)
            return

        event_firestore_id = f"event_{ctx.guild.id}_{random.randint(1000, 9999)}_{now.timestamp()}"

        event_data = {
            'name': event_name,
            'role_id': role.id,
            'duration': duration,
            'start_time': start_time_paris,
            'end_time': end_time_paris,
            'channel_waiting_id': channel_waiting.id,
            'channel_priv_id': channel_priv.id,
            'guild_id': ctx.guild.id,
            'max_participants': max_participants,
            'participant_label': participant_label,
            'participants': [],
            'registrations_closed': False,
            'has_started': False,
        }

        embed = create_retro_embed(f"ÉVÉNEMENT PLANIFIÉ : {event_name}")
        embed.description = f"Préparez-vous à une partie épique de {event_name} !"
        embed.add_field(name="Rôle requis", value=role.mention, inline=False)
        
        start_timestamp = int(start_time_paris.timestamp())
        end_timestamp = int(end_time_paris.timestamp())
        embed.add_field(name="Début / Fin", value=f"Début : <t:{start_timestamp}:f> (dans <t:{start_timestamp}:R>)\nFin : <t:{end_timestamp}:f> (se termine <t:{end_timestamp}:R>)", inline=False)
        
        embed.add_field(name="Salon d'attente", value=channel_waiting.mention, inline=True)
        embed.add_field(name="Salon de jeu", value=channel_priv.mention, inline=True)
        
        embed.add_field(
            name=f"Participants ({len(event_data['participants'])}/{max_participants} {participant_label})",
            value="Aucun participant",
            inline=False
        )
        
        is_full = max_participants and len(event_data['participants']) >= max_participants
        view = EventButtons(event_firestore_id, is_full=is_full)
        
        event_message = await channel_waiting.send(
            content=f"**Un nouvel événement planifié a été lancé ! Rejoignez-le en cliquant sur le bouton ci-dessous !**",
            embed=embed,
            view=view
        )
        
        event_data['message_id'] = event_message.id
        await asyncio.to_thread(db.collection('events').document(event_firestore_id).set, event_data)
        
    except ValueError as ve:
        await ctx.send(f"Erreur : {ve}", delete_after=60)
    except Exception as e:
        await ctx.send(f"Une erreur est survenue lors de la création de l'événement : `{e}`", delete_after=60)
        print(f"Erreur de création d'événement planifié : {e}")

@bot.command(name='end_event')
@commands.has_permissions(manage_roles=True)
async def end_event_command(ctx, *, event_name: str):
    """
    Termine manuellement un événement en cours.
    Utilisation : `!end_event Nom de l'événement`
    """
    try:
        await ctx.message.delete()
    except discord.NotFound:
        pass

    events_ref = db.collection('events').where('name', '==', event_name)
    event_docs = await asyncio.to_thread(events_ref.stream)
    
    event_doc_to_end = None
    for doc in event_docs:
        event_doc_to_end = doc
        break
        
    if event_doc_to_end:
        await ctx.send(f"Terminaison de l'événement **'{event_name}'** en cours...")
        await _end_event(event_doc_to_end.id, ctx.channel)
    else:
        await ctx.send(f"L'événement **'{event_name}'** n'a pas été trouvé.", delete_after=60)


@bot.command(name='list_events')
@commands.has_permissions(manage_roles=True)
async def list_events_command(ctx):
    """
    Affiche tous les événements actifs avec leurs détails.
    Utilisation: `!list_events`
    """
    try:
        await ctx.message.delete()
    except discord.NotFound:
        pass
    
    events_ref = db.collection('events')
    active_events_docs = await asyncio.to_thread(events_ref.stream)
    
    active_events = []
    for doc in active_events_docs:
        active_events.append(doc.to_dict())
        
    if not active_events:
        await ctx.send("Il n'y a pas d'événements en cours pour le moment.")
        return

    embed = create_retro_embed("ÉVÉNEMENTS ACTIFS")

    for event_data in active_events:
        name = event_data.get('name', 'Nom inconnu')
        start_time = event_data.get('start_time')
        end_time = event_data.get('end_time')
        
        start_timestamp = int(start_time.timestamp())
        end_timestamp = int(end_time.timestamp())
        
        participants_count = len(event_data.get('participants', []))
        max_participants = event_data.get('max_participants', 'N/A')
        participant_label = event_data.get('participant_label', 'participants')
        
        value = (
            f"**Début :** <t:{start_timestamp}:f>\n"
            f"**Fin :** <t:{end_timestamp}:f>\n"
            f"**Participants :** {participants_count}/{max_participants} {participant_label}\n"
            f"**Salon d'attente :** <#{event_data.get('channel_waiting_id')}>"
        )
        embed.add_field(name=f"**- {name}**", value=value, inline=False)
        
    await ctx.send(embed=embed)


# --- Fonctions pour le serveur web ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Poxel bot is running!"

def run_flask_app():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

def start_bot_in_thread():
    bot.run(BOT_TOKEN)

# --- Démarrage du Bot et du serveur web ---
if __name__ == '__main__':
    bot_thread = threading.Thread(target=start_bot_in_thread)
    bot_thread.start()
    
    run_flask_app()
