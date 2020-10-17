import sys
import os
import json
import random
import re
import argparse
import asyncio
import yaml
import discord

from sheets import load_sheets, check_valid_skill
import rollbuild


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
ROLL_REGEX = re.compile(r'\!roll (\d{1,2})(?:\s?[Oo][Bb]\s?(\d))?(?:(?: for )?(.+))?')
RATING_REGEX = re.compile(r'\!(rating|progress)(?: (.+))? (.+)')
FORCE_REGEX = re.compile(r'\!force ((?:\d+,?\s*)*\d+)')

USER_ID_REGEX = re.compile(r'<@!(\d+)>')

# Catch-all regex. Doesn't look at args.
# User attempted to use a command with bad syntax, or needs help.
USAGE_REGEX = re.compile(r'\!(:?help|usage|roll|rating|progress)')

# Aliases for commands. Shortcuts. Alternates.
ALIASES = {}

USE_CUSTOM_EMOJIS = config['use_custom_emojis']
USE_SHEETS = config['use_google_sheets']

# Translates a d6 --> MG d6
# Default the emojis to just words for display purposes
SNAKE_EMOJI = 'snakes'
SWORDS_EMOJI = 'swords'
AXE_EMOJI = 'axes'

EMOJI_MAP = {}
if USE_CUSTOM_EMOJIS:
    SNAKE_EMOJI = config['snake_emoji']
    SWORDS_EMOJI = config['swords_emoji']
    AXE_EMOJI = config['axe_emoji']
    EMOJI_MAP = {
        1: SNAKE_EMOJI,
        2: SNAKE_EMOJI,
        3: SNAKE_EMOJI,
        4: SWORDS_EMOJI,
        5: SWORDS_EMOJI,
        6: AXE_EMOJI
    }
else:
    EMOJI_MAP = {
        1: ':one:',
        2: ':two:',
        3: ':three:',
        4: ':four:',
        5: ':five:',
        6: ':six:'
    }


# 30 max is beyond reasonable, and is spammy enough
# https://forums.burningwheel.com/t/maximum-of-dice/8561/6
MAXIMUM_NUMBER_OF_DICE = 30


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

    This is basically a hack, but I wrote this quickly in a night, sue me.
    '''

    def __init__(self):
        '''Load the saved roll results from the server-backed file json file.'''
        super().__init__()
        self.saved_results = {}
        self.forced_values = []

        print("Initializing MiceDice...")
        self.sheets = {}


    async def on_ready(self):
        potential_players = [_.id for _ in self.get_guild(SERVER_ID).members]
        self.sheets = load_sheets(GOOGLE_CREDS_JSON, GOOGLE_SHEETS_URL, potential_players) if USE_SHEETS else {}
        print('MiceDice bot ready to play!')


    async def on_message(self, message):
        # Bot ignores itself. This is how you avoid learning.
        if message.author == self.user:
            return

        if message.content.startswith('!'):
            if message.content in ALIASES:
                message.content = ALIASES[message.content]

            m = ValueRetainingRegexMatcher(message.content)
            if m.match(ROLL_BUILD_REGEX):
                await rollbuild.start_roll(message.author, message.channel)
            elif m.match(ROLL_REGEX):
                num_dice = m.group(1)
                obstacle = m.group(2)
                reason = m.group(3)
                await self.roll(message, num_dice, obstacle, reason)
            elif m.match(FORCE_REGEX):
                values = m.group(1)
                await self.force(message, values)
            elif m.match(RATING_REGEX) and USE_SHEETS:
                progress = m.group(1) == 'progress'
                who = m.group(2)
                if who: 
                    uid_matcher = ValueRetainingRegexMatcher(who)
                    if uid_matcher.match(USER_ID_REGEX):
                        user = discord.utils.get(message.guild.members, id=int(uid_matcher.group(1)))
                        who = user.display_name if user else discord.utils.escape_mentions(who)
                skill = m.group(3)
                await self.check_rating(message, who, skill, progress)
            elif m.match(USAGE_REGEX):
                await self.usage(message)
            # else is a quiet no-op


    async def on_reaction_add(self, reaction, user):
        if user == self.user:
            return
        
        if reaction.message.author.id == self.user.id and await rollbuild.is_roll(reaction.message) and await rollbuild.owns_roll(user, reaction.message):
            await rollbuild.next(reaction)


    async def _render_rating(self, player, skill, progress):
        sheet = self.sheets[player.id]
        sheet.sync()
        rating = sheet.get_rating(skill)

        if not rating:
            return f'{player.display_name}\'s {skill} rating: **Not yet learing!**'
        
        msg = f'{player.display_name}\'s {skill} rating: **{"Learning!" if rating == "x" else rating}**'
        if progress:
            success = sheet.get_success(skill)
            fail = sheet.get_fail(skill)
            if rating == 'x':
                # Learning...
                nature = sheet.get_rating('nature')
                mani = sheet.get_rating('manipulator')
                msg += ' -- [progress: ' + '✓' * (fail + success) + ' ' + '◯ ' * (nature - fail - success) + ']'
            else:
                msg += ' -- [*fail*: ' + '✓' * fail + ' ' + '◯ ' * (rating - fail - 1) + \
                        ' | *success*: ' + '✓' * success + ' ' + '◯ ' * (rating - success) + ']'
        return msg


    async def check_rating(self, message, who, skill, progress=False):
        if not check_valid_skill(skill):
            await message.channel.send(f'{skill} is not a valid skill.')
            return

        # GM case, default behavior (check everyone)
        if GM_ROLE in [_.name for _ in message.author.roles] and not who:
            players = [member for member in message.channel.members if member.id in self.sheets]
            msg = f'GM is checking everyone\'s **{skill}** ratings...\n>>> '
            for player in players:
                msg += await self._render_rating(player, skill, progress)
            await message.channel.send(msg)
            return

        # Find person specified, otherwise make it the person sending the query
        if who:
            who = discord.utils.find(lambda m: who in [m.name, m.nick, m.id], message.channel.members)
            if not who:
                await message.channel.send(f'Could not find player "**{who}**".')
                return
        else:
            who = self.message.author

        if who.id not in self.sheets:
            await message.channel.send(f'**{who.display_name}** has no character sheet.')
            return
        
        msg = await self._render_rating(who, skill, progress)
        await message.channel.send(msg)


    async def force(self, message, values):
        if not GM_ROLE in [_.name for _ in message.author.roles]:
            return
        self.forced_values = [int(_) for _ in values.replace(',', ' ').split()]
        await message.channel.send('Forcing values: ' + str(self.forced_values))


    async def roll(self, message, num_dice, obstacle, reason):
        '''!roll <#> [Ob #] [for <reason>]'''
        try:
            num_dice = int(num_dice)
        except:
            await message.channel.send("Rolls must be with made with a valid number of dice!")
            return

        if obstacle:
            try:
                obstacle = int(obstacle)
            except:
                await message.channel.send("Roll obstacles must have a valid difficulty!")
                return

        if num_dice < 1 or num_dice > MAXIMUM_NUMBER_OF_DICE:
            await message.channel.send("Rolls must be with an *appropriate* number of dice!")
            return

        # roll dice
        result = sorted([random.randint(1, 6) for i in range(num_dice)])

        # used forced values, potentially
        if self.forced_values and GM_ROLE in [_.name for _ in message.author.roles]:
            result = self.forced_values + result
            result = result[:num_dice]
            result = sorted(result)
            self.forced_values = []
        
        roll_str = f"**{message.author.mention}** is rolling **{num_dice}** dice"
        reason_str = f'**for {reason}**' if reason else ''
        dice_result_str = await self.resolve_dice_result_str(result, obstacle=obstacle)
        
        await message.channel.send(f'{roll_str} {reason_str}\n>>> {dice_result_str}')


    async def usage(self, message):
        '''!help'''
        await message.channel.send(
                f'```Usage:\n'
                f'\t!roll\n'
                f'\t!roll <dice> [Ob <req>] [for <reason>]\n'
                f'```'
        )


    async def to_emoji_str(self, result):
        '''Converts a list of d6 numbers to emojis, then joins by spaces.'''
        return " ".join([EMOJI_MAP[_] for _ in result])


    async def fetch_result_details(self, key):
        if key not in self.saved_results:
            return

        results = self.saved_results[key]['results']
        reason = self.saved_results[key]['reason']
        obstacle = self.saved_results[key]['obstacle']
        return results, obstacle, reason


    async def resolve_dice_result_str(self, result, obstacle=None, tagged=None):
        result_str = await self.to_emoji_str(result)
        success_str = ''
        if obstacle:
            success = len([_ for _ in result if _ >= 4]) >= obstacle
            emoji = ':tada:' if success else ':skull:'
            success_str = f'\t[**(Ob {obstacle}) {emoji}**]'

        return f"{result_str} {success_str}"


def main():
    client = MiceDice()
    client.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
