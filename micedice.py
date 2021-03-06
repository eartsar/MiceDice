import re
import argparse
import yaml
import discord

from sheets import SheetManager
from rolling import RollerManager
from persist import DatabaseManager


parser = argparse.ArgumentParser(description='Run the MiceDice bot.')
parser.add_argument('--config', type=str, required=True, 
                    help='The path to the configuration yml.')
args = parser.parse_args()

# Load the config file
config = {}
with open(args.config, 'r') as f:
    config = yaml.safe_load(f)

BOT_TOKEN = config['bot_token']
SERVER_ID = config['server_id']

DB_FILE_PATH = config['sqlite3_database_path']


# Experimental Google Sheets integration
GOOGLE_CREDS_JSON = config['google_service_account_creds']
GOOGLE_SHEETS_URL = config['google_sheets_url']

# Meh, I'll just use regexes to parse commands. Easy enough.
ROLL_BUILD_REGEX = re.compile(r'^\!roll$')
ROLL_REGEX = re.compile(r'\!roll (\d+)(?:\s?[Oo][Bb]\s?(\d))?(?: for ?(.+))?')
PROFILE_REGEX = re.compile(r'\!profile (register|select|unregister|display)(?:\s(.+))?')
RATING_REGEX = re.compile(r'\!(rating|progress)(?: (.+))? (.+)')

USER_ID_REGEX = re.compile(r'<@!(\d+)>')

# Catch-all regex. Doesn't look at args.
# User attempted to use a command with bad syntax, or needs help.
USAGE_REGEX = re.compile(r'\!(:?help|usage|roll|rating|progress)')

# Aliases for commands. Shortcuts. Alternates.
ALIASES = {}

USE_ICON_EMOJIS = config['use_icon_emojis']
USE_SHEETS = config['use_google_sheets']

# Translates a d6 --> MG d6
# Default the emojis to just words for display purposes
SNAKE_EMOJI = '🐍'
SWORDS_EMOJI = '⚔️'
AXE_EMOJI = '🪓'

DICE_FACE_EMOJIS = {}
if USE_ICON_EMOJIS:
    DICE_FACE_EMOJIS = {
        0: '❓',
        1: SNAKE_EMOJI,
        2: SNAKE_EMOJI,
        3: SNAKE_EMOJI,
        4: SWORDS_EMOJI,
        5: SWORDS_EMOJI,
        6: AXE_EMOJI
    }
else:
    DICE_FACE_EMOJIS = {
        0: '0️⃣',
        1: '1️⃣',
        2: '2️⃣',
        3: '3️⃣',
        4: '4️⃣',
        5: '5️⃣',
        6: '6️⃣'
    }


class MiceDice(discord.Client):
    '''The MiceDice discort bot client.

    This is basically a hack, but I've put a few hours into this code by now
    so I can't use the "I did it in a night" excuse as a crutch anymore.'''

    def __init__(self):
        super().__init__()
        self.db = DatabaseManager(DB_FILE_PATH)
        self.roller = RollerManager()
        self.sheets = SheetManager(GOOGLE_CREDS_JSON, self.db)


    async def on_ready(self):
        print("Initializing MiceDice...")
        await self.db.initialize()
        await self.sheets.initialize()
        print('MiceDice bot ready to play!')


    async def on_message(self, message):
        # Bot ignores itself. This is how you avoid the singularity.
        if message.author == self.user:
            return

        # Ignore anything that doesn't start with the magic token
        if not message.content.startswith('!'):
            return

        # Handle alises
        if message.content in ALIASES:
            message.content = ALIASES[message.content]

        # Match against the right command, grab args, and go
        from util import ValueRetainingRegexMatcher
        m = ValueRetainingRegexMatcher(message.content)
        
        if m.match(ROLL_BUILD_REGEX):
            await self.roller.create(message.author, message.channel)
        elif m.match(ROLL_REGEX):
            num_dice = int(m.group(1)) if m.group(1) else None
            obstacle = int(m.group(2)) if m.group(2) else None
            reason = m.group(3)
            await self.roller.create(message.author, message.channel, num_dice=num_dice, obstacle=obstacle, reason=reason)
        elif m.match(PROFILE_REGEX):
            from util import get_sheets_key
            await message.edit(suppress=True)
            operation = m.group(1)
            key = get_sheets_key(m.group(2))
            if operation == 'register' and key:
                await self.sheets.register_profile(message.channel, message.author, key)
            elif operation == 'unregister' and key:
                await self.sheets.unregister_profile(message.channel, message.author, key)
            elif operation == 'select':
                await self.sheets.initiate_choose_profile(message.author, message.channel)
            elif operation == 'display':
                await self.sheets.display(message.author, message.channel)

            
        elif m.match(RATING_REGEX) and USE_SHEETS:
            progress = m.group(1) == 'progress'
            skill = m.group(2)
            sheet = await self.sheets.get_sheet(message.author)
            await sheet.check_rating(skill, message.channel, message.author, progress=progress)
        elif m.match(USAGE_REGEX):
            await self.usage(message)


    async def on_reaction_add(self, reaction, user):
        # If the reaction was from this bot, ignore i
        if user == self.user:
            return
        
        # If the reaction was to a "roll build" comment, and the reactor is the owner of it...
        if reaction.message.author.id == self.user.id:
            await self.roller.handle_event(user, reaction)
            await self.sheets.handle_event(user, reaction)


    async def usage(self, message):
        '''!help'''
        await message.channel.send('''```Usage:
    !roll
    !roll <dice> [Ob <req>] [for <reason>]
    !profile select
    !profile register <url>
    !profile unregister <url>
    !profile display```''')


def main():
    client = MiceDice()
    client.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
