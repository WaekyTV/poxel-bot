import asyncio
import aiohttp
import discord
import os # Assurez-vous d'importer os si vous utilisez les variables d'environnement

# Assurez-vous que ces variables d'environnement sont définies sur Render
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
POXEL_BOT_ID = os.getenv('POXEL_BOT_ID') # Si vous utilisez un ID de bot spécifique

# Initialisez votre client Discord
intents = discord.Intents.default()
intents.message_content = True # Nécessaire pour accéder au contenu des messages
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    """Se déclenche lorsque le bot est connecté et prêt."""
    print(f'Connecté en tant que {client.user} (ID: {client.user.id})')
    print('Bot Discord Poxel est en ligne !')

@client.event
async def on_message(message):
    """Gère les messages entrants."""
    # Ne répondez pas à vous-même
    if message.author == client.user:
        return

    # Exemple de réponse simple
    if message.content.lower() == 'ping':
        await message.channel.send('Pong!')

    # Si vous voulez que le bot réponde uniquement aux mentions ou à des préfixes spécifiques
    # if client.user.mentioned_in(message) and message.mention_everyone is False:
    #     # Traitez le message quand le bot est mentionné
    #     pass

def run_discord_bot_thread_func():
    """
    Fonction pour exécuter le bot Discord dans un thread séparé.
    Cette fonction crée et gère sa propre boucle d'événements asyncio.
    """
    # Crée une nouvelle boucle d'événements pour ce thread
    loop = asyncio.new_event_loop()
    # Définit cette nouvelle boucle comme la boucle d'événements courante pour ce thread
    asyncio.set_event_loop(loop)

    try:
        # Exécute le client Discord dans cette boucle
        # Le token doit être défini comme une variable d'environnement sur Render
        loop.run_until_complete(client.start(DISCORD_BOT_TOKEN))
    except discord.LoginFailure:
        print("Échec de connexion : Le token du bot est invalide.")
    except Exception as e:
        print(f"Une erreur inattendue s'est produite lors de l'exécution du bot : {e}")
    finally:
        # Ferme la boucle d'événements une fois que le bot s'arrête
        loop.close()
        print("Boucle d'événements Discord fermée.")

# Pour exécuter cette fonction, vous devrez probablement la démarrer dans un thread
# Exemple (ne pas inclure dans le code du bot si c'est un script autonome pour Render):
# import threading
# discord_thread = threading.Thread(target=run_discord_bot_thread_func)
# discord_thread.start()
# discord_thread.join() # Si vous voulez attendre la fin du thread

