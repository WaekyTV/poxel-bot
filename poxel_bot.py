# -*- coding: utf-8 -*-
# --- INSTRUCTIONS POUR RENDER ---
# IMPORTANT : Ce code a été modifié pour fonctionner en tant que "Web Service"
# sur Render. Un serveur web minimal est démarré en parallèle du bot Discord
# pour écouter sur un port et éviter l'erreur de "timeout".
# Assurez-vous que les bibliothèques 'flask', 'pytz', 'discord.py' et 'firebase_admin'
# sont bien dans votre fichier 'requirements.txt'.

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
        raise ValueError("La variable d'environnement 'FIREBASE_SERVICE_ACCOUNT_KEY_JSON' n'est pas définie sur Render.")
    
    service_account_info = json.loads(firebase_json_key)
    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialisé avec succès.")
except Exception as e:
    print(f"Erreur lors de l'initialisation de Firebase Admin SDK: {e}")
    print("Assure-toi que la variable d'environnement 'FIREBASE_SERVICE_ACCOUNT_KEY_JSON' est bien configurée sur Render.")
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

# Modèle pour le formulaire d'inscription
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
        """
        Gère la soumission du formulaire d'inscription.
        """
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
        
        # Vérifier si l'utilisateur est déjà inscrit
        is_already_in = any(p['user_id'] == user.id for p in participants_list)
        if is_already_in:
            await interaction.followup.send("Vous êtes déjà inscrit à cet événement.", ephemeral=True)
            return

        # Vérifier si l'événement est plein ou a déjà commencé
        now = datetime.now(PARIS_TIMEZONE)
        start_time = event_data.get('start_time')
        
        if (max_participants and len(participants_list) >= max_participants) or \
           (start_time and start_time.astimezone(PARIS_TIMEZONE) <= now):
            await interaction.followup.send("Désolé, les inscriptions sont fermées.", ephemeral=True)
            return
        
        # Ajouter l'utilisateur
        try:
            await user.add_roles(role, reason=f"Participation à l'événement {event_name}")
            
            new_participant_data = {'user_id': user.id, 'alias': alias}
            await asyncio.to_thread(event_ref.update, {'participants': firestore.ArrayUnion([new_participant_data])})
            
            await interaction.followup.send(f"Vous avez rejoint l'événement **'{event_name}'** !", ephemeral=True)
            
            # Annoncer la nouvelle inscription
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
        
        # Mettre à jour l'embed après l'interaction
        updated_event_doc = await asyncio.to_thread(event_ref.get)
        if updated_event_doc.exists:
            await self.update_event_message(interaction, updated_event_doc.to_dict())

    async def update_event_message(self, interaction: discord.Interaction, event_data: dict):
        """Mise à jour de l'embed principal de l'événement."""
        guild = interaction.guild
        participants = event_data.get('participants', [])
        max_participants = event_data.get('max_participants')
        participant_label = event_data.get('participant_label', 'participants')
        
        try:
            original_message = interaction.message
            if original_message:
                embed = original_message.embeds[0]
                
                # Mettre à jour le champ des participants
                participant_names = await get_participant_info(guild, participants)
                
                # Chercher le champ "Participants" par son nom
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
                
                # Vérifier si les inscriptions sont complètes et envoyer un message
                if max_participants and len(participants) == max_participants and not event_data.get('registrations_closed'):
                    channel_waiting = guild.get_channel(event_data.get('channel_waiting_id'))
                    if channel_waiting:
                        await channel_waiting.send(f"@everyone Les inscriptions pour l'événement **'{event_data.get('name', 'Nom inconnu')}'** sont complètes !")
                        await asyncio.to_thread(db.collection('events').document(self.event_firestore_id).update, {'registrations_closed': True})
                
                # Gérer l'état du bouton
                view = EventButtons(self.event_firestore_id)
                if max_participants and len(participants) >= max_participants:
                    view.children[0].label = "Inscriptions fermées"
                    view.children[0].style = discord.ButtonStyle.grey
                    view.children[0].disabled = True
                
                await original_message.edit(embed=embed, view=view)
        except discord.NotFound:
            print(f"Erreur : Le message original de l'événement {event_data.get('name', 'nom inconnu')} n'a pas été trouvé. Il a peut-être été supprimé.")
        except Exception as e:
            print(f"Erreur lors de la mise à jour du message de l'événement : {e}")


class EventButtons(View):
    def __init__(self, event_firestore_id):
        super().__init__(timeout=None)
        self.event_firestore_id = event_firestore_id
        
        # Ajout du bouton "START" (qui ouvre le modal d'inscription)
        join_button = Button(
            label="START", 
            style=discord.ButtonStyle.green, 
            custom_id=f"join_event_{self.event_firestore_id}"
        )
        join_button.callback = self.handle_join
        self.add_item(join_button)

        # Ajout du bouton "QUIT"
        quit_button = Button(
            label="QUIT", 
            style=discord.ButtonStyle.red, 
            custom_id=f"quit_event_{self.event_firestore_id}"
        )
        quit_button.callback = self.handle_quit
        self.add_item(quit_button)

    async def handle_join(self, interaction: discord.Interaction):
        """Ouvre le modal pour l'inscription."""
        await interaction.response.send_modal(AliasModal(self.event_firestore_id))

    async def handle_quit(self, interaction: discord.Interaction):
        """Gère le clic sur le bouton 'QUIT'."""
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
            # Récupérer l'entrée du participant à supprimer
            participant_to_remove = next((p for p in participants_list if p['user_id'] == user.id), None)
            
            if role:
                await user.remove_roles(role, reason=f"Quitte l'événement {event_name}")
            
            # Supprimer l'entrée du participant
            await asyncio.to_thread(event_ref.update, {'participants': firestore.ArrayRemove([participant_to_remove])})
            
            await interaction.response.send_message(f"Vous avez quitté l'événement **'{event_name}'**.", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour vous retirer ce rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue lors de votre désinscription : `{e}`", ephemeral=True)
            return
        
        # Mettre à jour l'embed après le désistement
        updated_event_doc = await asyncio.to_thread(event_ref.get)
        if updated_event_doc.exists:
            await AliasModal(self.event_firestore_id).update_event_message(interaction, updated_event_doc.to_dict())


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

    # Retirer les rôles des participants
    for p_data in participants_list:
        member = guild.get_member(p_data['user_id'])
        if member and role:
            try:
                await member.remove_roles(role, reason=f"Fin de l'événement {event_name}")
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour retirer le rôle {role.name} à {member.display_name}")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle à {member.display_name}: {e}")
    
    # Mettre à jour le message de l'événement s'il existe
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
            embed = event_message.embeds[0]
            embed.color = 0x8B0000
            embed.description = f"**Événement terminé.**"
            embed.clear_fields()
            
            participants_names = await get_participant_info(guild, participants_list)
            
            embed.add_field(name=f"Participants finaux ({len(participants_list)}/{event_data.get('max_participants', 'N/A')} {event_data.get('participant_label', 'participants')})", value=participants_names, inline=False)
            await event_message.edit(content=f"@everyone L'événement **'{event_name}'** est maintenant terminé.", embed=embed, view=None)
        except Exception as e:
            print(f"Erreur lors de la mise à jour du message de l'événement : {e}")
    else:
        # Si le message n'est pas trouvé, envoie un message de confirmation
        if context_channel:
            try:
                await context_channel.send(f"L'événement **'{event_name}'** a été terminé, mais le message original a été supprimé. Les rôles ont été retirés aux participants.", delete_after=60)
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour envoyer un message dans le canal {context_channel.name}.")
            except Exception as e:
                print(f"Erreur lors de l'envoi du message de confirmation : {e}")
        
    # Suppression de l'événement de Firestore.
    await asyncio.to_thread(event_ref.delete)
    print(f"Événement '{event_name}' (ID: {event_doc_id}) supprimé de Firestore.")


@tasks.loop(minutes=1)
async def update_event_messages():
    """Tâche en arrière-plan pour vérifier et mettre à jour les événements."""
    print("Mise à jour des événements en cours...")
    events_ref = db.collection('events')
    now = datetime.now(PARIS_TIMEZONE)
    
    active_events_docs = await asyncio.to_thread(events_ref.stream)
    
    for doc in active_events_docs:
        event_data = doc.to_dict()
        event_end_time = event_data.get('end_time')
        event_start_time = event_data.get('start_time')
        
        if event_end_time and event_end_time.astimezone(PARIS_TIMEZONE) < now:
            print(f"Événement '{event_data.get('name', doc.id)}' expiré. Fin de l'événement...")
            await _end_event(doc.id)
            continue
        
        # Logique pour le début de l'événement
        if event_start_time and event_start_time.astimezone(PARIS_TIMEZONE) <= now and not event_data.get('has_started'):
            print(f"Événement '{event_data.get('name', doc.id)}' a commencé.")
            guild = bot.get_guild(event_data.get('guild_id'))
            if guild:
                channel_waiting = guild.get_channel(event_data.get('channel_waiting_id'))
                if channel_waiting:
                    await channel_waiting.send(f"@everyone L'événement **'{event_data.get('name', 'Nom inconnu')}'** a commencé ! Bonne partie !")
            
            # Mettre à jour l'état de l'événement dans Firestore
            await asyncio.to_thread(doc.reference.update, {'has_started': True})
            
            # Mettre à jour le message de l'événement (description et suppression des boutons)
            try:
                message_id = event_data.get('message_id')
                if channel_waiting and message_id:
                    event_message = await channel_waiting.fetch_message(message_id)
                    embed = event_message.embeds[0]
                    embed.color = discord.Color.green()
                    embed.description = f"**L'événement a commencé !** Il se terminera <t:{int(event_end_time.timestamp())}:R>."
                    
                    # Supprimer les boutons
                    await event_message.edit(embed=embed, view=None)
            except discord.NotFound:
                print(f"Le message de l'événement {event_data.get('name')} n'a pas été trouvé pour la mise à jour de début.")
            except Exception as e:
                print(f"Erreur lors de la mise à jour du message de début d'événement : {e}")

        # Mise à jour du timer pour les événements en cours ou à venir
        try:
            message_id = event_data.get('message_id')
            guild = bot.get_guild(event_data.get('guild_id'))
            if guild:
                channel_waiting = guild.get_channel(event_data.get('channel_waiting_id'))
                if channel_waiting and message_id:
                    event_message = await channel_waiting.fetch_message(message_id)
                    embed = event_message.embeds[0]

                    # Mettre à jour le champ du timer
                    start_time_timestamp = int(event_start_time.timestamp())
                    end_time_timestamp = int(event_end_time.timestamp())
                    
                    if now < event_start_time.astimezone(PARIS_TIMEZONE):
                        # Avant le début de l'événement
                        timer_value = f"Début : <t:{start_time_timestamp}:f> (dans <t:{start_time_timestamp}:R>)"
                    else:
                        # Après le début de l'événement
                        timer_value = f"Fin : <t:{end_time_stamp}:f> (dans <t:{end_time_stamp}:R>)"

                    # Trouver le champ 'Début' ou 'Fin' et le mettre à jour
                    for i, field in enumerate(embed.fields):
                        if field.name.startswith("Début") or field.name.startswith("Fin"):
                            embed.set_field_at(i, name="Début / Fin", value=timer_value, inline=False)
                            break
                    
                    await event_message.edit(embed=embed)

        except discord.NotFound:
            print(f"Message de l'événement {event_data.get('name', 'nom inconnu')} introuvable lors de la mise à jour du timer.")
            continue
        except Exception as e:
            print(f"Erreur lors de la mise à jour du timer pour l'événement {event_data.get('name', 'nom inconnu')} : {e}")


# --- Commandes du bot ---

async def _create_event_handler(ctx, role: discord.Role, duration: str, start_time: str, channel_waiting: discord.TextChannel, channel_private: discord.TextChannel, max_participants: int, participant_label: str, event_name: str, start_date: str = None):
    """Fonction interne pour gérer la création d'un événement."""
    
    # Supprimer le message de la commande
    try:
        await ctx.message.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        print(f"Erreur lors de la suppression du message de commande : {e}")
    
    events_ref = db.collection('events')
    existing_event = await asyncio.to_thread(events_ref.where(filter=firestore.FieldFilter('name', '==', event_name)).get)
    if existing_event:
        msg = await ctx.send(f"⚠️ Un événement nommé '{event_name}' existe déjà.", delete_after=60)
        try:
            await asyncio.sleep(60)
            await msg.delete()
        except discord.NotFound:
            pass
        return

    try:
        duration_seconds = parse_duration(duration)
        if duration_seconds <= 0:
            raise ValueError("La durée doit être positive.")
        
        now_paris = datetime.now(PARIS_TIMEZONE)
        
        if start_date:
            start_datetime = PARIS_TIMEZONE.localize(datetime.strptime(f"{start_date} {start_time}", "%d/%m/%Y %Hh%M"))
        else:
            start_datetime = PARIS_TIMEZONE.localize(datetime.strptime(start_time, "%Hh%M")).replace(year=now_paris.year, month=now_paris.month, day=now_paris.day)
            
            if start_datetime < now_paris:
                start_datetime += timedelta(days=1)
        
        end_datetime = start_datetime + timedelta(seconds=duration_seconds)

    except (ValueError, IndexError, TypeError) as e:
        msg = await ctx.send(f"❌ Erreur de format des arguments. {e}\nUtilisation correcte : `!helpoxel {ctx.command}`", delete_after=60)
        try:
            await asyncio.sleep(60)
            await msg.delete()
        except discord.NotFound:
            pass
        return

    temp_message = await ctx.send("Création de l'événement en cours...")

    event_data_firestore = {
        'name': event_name,
        'role_id': role.id,
        'channel_waiting_id': channel_waiting.id,
        'channel_private_id': channel_private.id,
        'end_time': end_datetime,
        'start_time': start_datetime,
        'max_participants': max_participants,
        'participant_label': participant_label,
        'participants': [],
        'message_id': temp_message.id,
        'guild_id': ctx.guild.id,
        'has_started': False,
        'registrations_closed': False
    }
    doc_ref = db.collection('events').document()
    await asyncio.to_thread(doc_ref.set, event_data_firestore)
    event_firestore_id = doc_ref.id

    view = EventButtons(event_firestore_id)
    
    embed = create_retro_embed(f"NOUVEL ÉVÉNEMENT : {event_name}")
    embed.description = (
        f"**Le rôle** {role.mention} **vous sera attribué une fois inscrit.** "
        f"Veuillez rejoindre le **point de ralliement** et patienter d’être déplacé dans le **salon privé**."
    )
    
    embed.add_field(name="Point de ralliement", value=channel_waiting.mention, inline=True)
    embed.add_field(name="Salon privé", value=channel_private.mention, inline=True)
    embed.add_field(name="Début / Fin", value=f"Début : <t:{int(start_datetime.timestamp())}:f> (dans <t:{int(start_datetime.timestamp())}:R>)", inline=False)
    embed.add_field(name=f"Participants (0/{max_participants} {participant_label})", value="Aucun participant", inline=False)

    await temp_message.edit(content=f"@everyone Un nouvel événement a été créé : **{event_name}** !", embed=embed, view=view)
    
    msg_confirm = await ctx.send(f"L'événement **'{event_name}'** a été créé avec succès.", delete_after=60)
    try:
        await asyncio.sleep(60)
        await msg_confirm.delete()
    except discord.NotFound:
        pass


@bot.command(name='create_event')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, role: discord.Role, duration: str, start_time: str, channel_waiting: discord.TextChannel, channel_private: discord.TextChannel, max_participants: int, participant_label: str, *, event_name: str):
    """Crée un événement qui démarre à une heure précise (aujourd'hui ou demain)."""
    await _create_event_handler(ctx, role=role, duration=duration, start_time=start_time, channel_waiting=channel_waiting, channel_private=channel_private, max_participants=max_participants, participant_label=participant_label, event_name=event_name)

@bot.command(name='create_event_plan')
@commands.has_permissions(manage_roles=True)
async def create_event_plan(ctx, role: discord.Role, duration: str, start_date: str, start_time: str, channel_waiting: discord.TextChannel, channel_private: discord.TextChannel, max_participants: int, participant_label: str, *, event_name: str):
    """Crée un événement planifié à une date et une heure précises."""
    await _create_event_handler(ctx, role=role, duration=duration, start_date=start_date, start_time=start_time, channel_waiting=channel_waiting, channel_private=channel_private, max_participants=max_participants, participant_label=participant_label, event_name=event_name)

@bot.command(name='end_event')
@commands.has_permissions(manage_roles=True)
async def end_event_command(ctx, *, event_name: str):
    """Termine manuellement un événement et retire les rôles."""
    try:
        await ctx.message.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        print(f"Erreur lors de la suppression du message de commande : {e}")

    events_ref = db.collection('events')
    existing_event_docs = await asyncio.to_thread(events_ref.where(filter=firestore.FieldFilter('name', '==', event_name)).get)

    if not existing_event_docs:
        msg = await ctx.send(f"L'événement **'{event_name}'** n'existe pas ou est déjà terminé.", delete_after=60)
        try:
            await asyncio.sleep(60)
            await msg.delete()
        except discord.NotFound:
            pass
        return

    event_doc_id = existing_event_docs[0].id
    
    msg = await ctx.send(f"L'événement **'{event_name}'** est en cours de fermeture...", delete_after=60)
    await _end_event(event_doc_id, context_channel=ctx.channel)
    try:
        await asyncio.sleep(60)
        await msg.delete()
    except discord.NotFound:
        pass


@bot.command(name='list_events')
async def list_events(ctx):
    """Affiche tous les événements actifs avec leurs détails."""
    try:
        await ctx.message.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        print(f"Erreur lors de la suppression du message de commande : {e}")

    events_ref = db.collection('events')
    active_events_docs = await asyncio.to_thread(events_ref.stream)

    events_list = []
    for doc in active_events_docs:
        events_list.append(doc.to_dict())

    if not events_list:
        msg = await ctx.send("Aucun événement actif pour le moment.", delete_after=60)
        try:
            await asyncio.sleep(60)
            await msg.delete()
        except discord.NotFound:
            pass
        return

    embed = create_retro_embed("LISTE DES ÉVÉNEMENTS ACTIFS")

    for data in events_list:
        guild_id = data.get('guild_id')
        guild = bot.get_guild(guild_id) if guild_id else None
        
        if not guild:
            continue
            
        role = guild.get_role(data.get('role_id'))
        channel_waiting = guild.get_channel(data.get('channel_waiting_id'))
        channel_private = guild.get_channel(data.get('channel_private_id'))
        
        participants_data = data.get('participants', [])
        participants_count = len(participants_data)
        
        participants_names = await get_participant_info(guild, participants_data)
        
        end_time_stamp = int(data['end_time'].timestamp()) if data.get('end_time') else 'N/A'
        start_time_stamp = int(data['start_time'].timestamp()) if data.get('start_time') else 'N/A'
        
        
        embed.add_field(
            name=f"🎮 {data.get('name', 'Événement sans nom')}",
            value=(
                f"**Rôle :** {role.mention if role else 'Introuvable'}\n"
                f"**Point de ralliement :** {channel_waiting.mention if channel_waiting else 'Introuvable'}\n"
                f"**Salon privé :** {channel_private.mention if channel_private else 'Introuvable'}\n"
                f"**Participants ({participants_count}/{data.get('max_participants', 'N/A')} {data.get('participant_label', 'participants')}) :**\n{participants_names}\n"
                f"**Début :** <t:{start_time_stamp}:f> (se termine <t:{end_time_stamp}:R>)"
            ),
            inline=False
        )

    msg = await ctx.send(embed=embed, delete_after=300)
    try:
        await asyncio.sleep(300)
        await msg.delete()
    except discord.NotFound:
        pass


# --- Événements du Bot ---

@bot.event
async def on_ready():
    """Se déclenche lorsque le bot est connecté à Discord."""
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Prêt à gérer les événements !')
    update_event_messages.start()

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
        try:
            await asyncio.sleep(60)
            await msg.delete()
        except discord.NotFound:
            pass
    elif isinstance(error, commands.BadArgument):
        msg = await ctx.send(f"Argument invalide. Veuillez vérifier le format de vos arguments dans le manuel `!helpoxel {ctx.command}`.", delete_after=60)
        try:
            await asyncio.sleep(60)
            await msg.delete()
        except discord.NotFound:
            pass
    elif isinstance(error, commands.MissingPermissions):
        msg = await ctx.send("Vous n'avez pas les permissions nécessaires pour exécuter cette commande (Gérer les rôles).", delete_after=60)
        try:
            await asyncio.sleep(60)
            await msg.delete()
        except discord.NotFound:
            pass
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Erreur de commande : {error}")
        msg = await ctx.send(f"Une erreur inattendue s'est produite : `{error}`", delete_after=60)
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
    except Exception as e:
        print(f"Erreur lors de la suppression du message de commande : {e}")
    
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
        try:
            await asyncio.sleep(180)
            await msg.delete()
        except discord.NotFound:
            pass
        return

    command = bot.get_command(command_name)
    if command is None:
        msg = await ctx.send(f"La commande `!{command_name}` n'existe pas.", delete_after=60)
        try:
            await asyncio.sleep(60)
            await msg.delete()
        except discord.NotFound:
            pass
        return
    
    embed = create_retro_embed(f"MANUEL DE LA COMMANDE `!{command.name.upper()}`")
    embed.description = command.help

    if command.name == 'create_event':
        embed.add_field(name="Exemple", value="`!create_event @Joueur 1h30m 21h15 #salon-attente #salon-prive 10 joueurs Partie de Donjons`", inline=False)
    elif command.name == 'create_event_plan':
        embed.add_field(name="Exemple", value="`!create_event_plan @Role 2h 25/12/2025 21h00 #salon-attente #salon-prive 10 joueurs Événement de Noël`", inline=False)
    elif command.name == 'end_event':
        embed.add_field(name="Exemple", value="`!end_event Ma Super Partie`", inline=False)
    elif command.name == 'list_events':
        embed.add_field(name="Exemple", value="`!list_events`", inline=False)

    msg = await ctx.send(embed=embed, delete_after=180)
    try:
        await asyncio.sleep(180)
        await msg.delete()
    except discord.NotFound:
        pass


# --- Fonctions pour le serveur web ---
# (Ajoutées pour permettre au bot de fonctionner en tant que Web Service)
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
    # Démarrer le bot dans un thread pour ne pas bloquer le serveur Flask
    bot_thread = threading.Thread(target=start_bot_in_thread)
    bot_thread.start()
    
    # Démarrer le serveur Flask dans le thread principal
    run_flask_app()
