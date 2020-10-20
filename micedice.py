import sys
import os
import json
import random
import re
import argparse
import asyncio
import yaml
import discord

from sheets import SheetManager
from rolling import RollerManager


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
GM_ROLE = config['gm_role']

# Experimental Google Sheets integration
GOOGLE_CREDS_JSON = config['google_service_account_creds']
GOOGLE_SHEETS_URL = config['google_sheets_url']

# Meh, I'll just use regexes to parse commands. Easy enough.
ROLL_BUILD_REGEX = re.compile(r'^\!roll$')
ROLL_REGEX = re.compile(r'\!roll (\d+)(?:\s?[Oo][Bb]\s?(\d))?(?: for ?(.+))?')
RATING_REGEX = re.compile(r'\!(rating|progress)(?: (.+))? (.+)')

USER_ID_REGEX = re.compile(r'<@!(\d+)>')

# Catch-all regex. Doesn't look at args.
# User attempted to use a command with bad syntax, or needs help.
USAGE_REGEX = re.compile(r'\!(:?help|usage|roll|rating|progress)')

# Aliases for commands. Shortcuts. Alternates.
ALIASES = {}

USE_EMOJIS = True
USE_SHEETS = config['use_google_sheets']

# Translates a d6 --> MG d6
# Default the emojis to just words for display purposes
SNAKE_EMOJI = '🐍'
SWORDS_EMOJI = '⚔️'
AXE_EMOJI = '🪓'

DICE_FACE_EMOJI = {}
if USE_EMOJIS:
    DICE_FACE_EMOJI = {
        0: '❓',
        1: SNAKE_EMOJI,
        2: SNAKE_EMOJI,
        3: SNAKE_EMOJI,
        4: SWORDS_EMOJI,
        5: SWORDS_EMOJI,
        6: AXE_EMOJI
    }
else:
    DICE_FACE_EMOJI = {
        0: '0️⃣',
        1: '1️⃣',
        2: '2️⃣',
        3: '3️⃣',
        4: '4️⃣',
        5: '5️⃣',
        6: '6️⃣'
    }


class ValueRetainingRegexMatcher:
    '''This is a load of BS to just get around not using PEP 572'''
    def __init__(self, match_str):
        self.match_str = match_str

    def match(self, regex):
        self.retained = re.match(regex, self.match_str)
        return bool(self.retained)

    def group(self, i):
        return self.retained.group(i)



class MiceDice(discord.Client):
    '''The MiceDice discort bot client.

    This is basically a hack, but I've put a few hours into this code by now
    so I can't use the "I did it in a night" excuse as a crutch anymore.'''

    def __init__(self):
        super().__init__()
        self.roller = RollerManager()
        self.sheets = SheetManager(GOOGLE_CREDS_JSON, GOOGLE_SHEETS_URL, self.get_guild(SERVER_ID))


    async def on_ready(self):
        print("Initializing MiceDice...")
        if USE_SHEETS:
            print("  Loading google sheets for players...")
            await self.sheets.load()
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
        m = ValueRetainingRegexMatcher(message.content)
        
        if m.match(ROLL_BUILD_REGEX):
            await self.roller.create(message.author, message.channel)
        elif m.match(ROLL_REGEX):
            num_dice = int(m.group(1)) if m.group(1) else None
            obstacle = int(m.group(2)) if m.group(2) else None
            reason = m.group(3)
            await self.roller.create(message.author, message.channel, num_dice=num_dice, obstacle=obstacle, reason=reason)
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


    async def usage(self, message):
        '''!help'''
        await message.channel.send(
                f'```Usage:\n'
                f'\t!roll\n'
                f'\t!roll <dice> [Ob <req>] [for <reason>]\n'
                f'```'
        )


def main():
    client = MiceDice()
    client.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
