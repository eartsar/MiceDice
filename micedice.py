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

# Only the best persistence engine for my bot... a json file
SAVED_ROLLS_JSON = config['saved_rolls_path']

# Experimental Google Sheets integration
GOOGLE_CREDS_JSON = config['google_service_account_creds']
GOOGLE_SHEETS_URL = config['google_sheets_url']

# Meh, I'll just use regexes to parse commands. Easy enough.
ROLL_REGEX = re.compile(r'\!roll (\d{1,2})(?:\s?[Oo][Bb]\s?(\d))?(?:(?: for )?(.+))?')
NUDGE_REGEX = re.compile(r'\!(reroll|explode) ?(\d|all)?')
LAST_REGEX = re.compile(r'\!last')
RATING_REGEX = re.compile(r'\!(rating|progress)(?: (.+))? (.+)')
FORCE_REGEX = re.compile(r'\!force ((?:\d+,?\s*)*\d+)')

USER_ID_REGEX = re.compile(r'<@!(\d+)>')

# Catch-all regex. Doesn't look at args.
# User attempted to use a command with bad syntax, or needs help.
USAGE_REGEX = re.compile(r'\!(:?help|usage|roll|reroll|explode|last|rating|progress)')

# Aliases for commands. Shortcuts. Alternates.
ALIASES = {}

USE_CUSTOM_EMOJIS = config['use_custom_emojis']
USE_SHEETS = config['use_google_sheets']
USE_PERSIST = config['use_persist']

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

    The client has a dictionary of the last rolls for all users that use it.
    These get persisted after any new roll, or nudge roll, is performed.
    The persisted rolls are backed by a json file sitting on the server.

    Rolls are always persisted in ascending order, and persist the number value.
    '''

    def __init__(self):
        '''Load the saved roll results from the server-backed file json file.'''
        super().__init__()
        self.saved_results = {}
        self.forced_values = []

        print("Initializing MiceDice...")
        # Create the file (empty json) if it doesn't exist yet
        if os.path.isfile(SAVED_ROLLS_JSON) and USE_PERSIST:
            # Load the file into the saved rolls
            temp = {}
            with open(SAVED_ROLLS_JSON, 'r') as f:
                temp = json.load(f)
                for key in temp:
                    # ints aren't JSON keys, they persist as strings
                    # re-convert them to ints on load
                    self.saved_results[int(key)] = temp[key]
                print(f"  Rolls loaded from {SAVED_ROLLS_JSON}.")
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
            if m.match(ROLL_REGEX):
                num_dice = m.group(1)
                obstacle = m.group(2)
                reason = m.group(3)
                await self.roll(message, num_dice, obstacle, reason)
            elif m.match(FORCE_REGEX):
                values = m.group(1)
                await self.force(message, values)
            elif m.match(NUDGE_REGEX):
                method = m.group(1)
                num_dice = m.group(2)
                num_dice = num_dice if num_dice else 1
                await self.nudge(message, method, num_dice)
            elif m.match(LAST_REGEX):
                await self.last(message)
            elif m.match(RATING_REGEX):
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
        if self.forced_values:
            result = self.forced_values + result
            result = result[:num_dice]
            result = sorted(result)
            self.forced_values = []
        
        roll_str = f"**{message.author.mention}** is rolling **{num_dice}** dice"
        reason_str = f'**for {reason}**' if reason else ''
        dice_result_str = await self.resolve_dice_result_str(result, obstacle=obstacle)
        
        await message.channel.send(f'{roll_str} {reason_str}\n>>> {dice_result_str}')
        await self.persist(key=message.author.id, results=result, obstacle=obstacle, reason=reason)


    async def nudge(self, message, method, num_dice):
        '''!reroll <dice>, !explode <dice>'''
        # User must have results to nudge.
        if message.author.id not in self.saved_results:
            await message.channel.send(f"**{message.author.mention}** hasn't rolled before!")
            return
        
        key = message.author.id
        result, obstacle, reason = await self.fetch_result_details(key)
        nudge_str = None

        if num_dice == 'all':
            num_dice = len(result)

        try:
            num_dice = int(num_dice)
        except Exception:
            return await self.usage(message)
        
        if method == 'explode':
            axes = [_ for _ in result if _ == 6]
            if len(axes) == 0:
                return await message.channel.send(f"**{message.author.mention}** doesn't have any {AXE_EMOJI} to explode!")
            num_dice = len(axes) if num_dice >= len(axes) else num_dice
            nudge_str, result = await self.explode(message, result, num_dice)
        elif method == 'reroll':
            snakes = [_ for _ in result if _ < 4]
            if len(snakes) == 0:
                return await message.channel.send(f"**{message.author.mention}** doesn't have any {SNAKE_EMOJI} to re-roll!")
            num_dice = len(snakes) if num_dice >= len(snakes) else num_dice
            nudge_str, result = await self.reroll(message, result, num_dice)
        else:
            return

        # Print and persist
        dice_result_str = await self.resolve_dice_result_str(result, obstacle)
        send_str = f'{nudge_str}\n>>> {dice_result_str}'
        await message.channel.send(send_str)
        await self.persist(key=key, results=result, obstacle=obstacle, reason=reason)


    async def reroll(self, message, result, num_dice):
        '''# Grab the lowest die, re-roll it, re-order, persist'''
        result = [random.randint(1, 6) for die in range(num_dice)] + result[num_dice:]
        rerolled_str = await self.to_emoji_str(result[:num_dice])
        result = sorted(result)
        nudge_str = (
                f"**{message.author.mention}** re-rolls {num_dice} {SNAKE_EMOJI}...\n"
                f"\t\t...and gets {rerolled_str}!"
        )
        return nudge_str, result


    async def explode(self, message, result, num_dice):
        '''Explode a certain number of axes, and add the new results.'''
        result = [random.randint(1, 6) for die in range(num_dice)] + result
        rerolled_str = await self.to_emoji_str(result[:num_dice])
        result = sorted(result)
        nudge_str = (
                f"**{message.author.mention}** explodes {num_dice} {AXE_EMOJI}...\n"
                f"\t\t...and gets {rerolled_str}!"
        )
        return nudge_str, result


    async def last(self, message):
        if GM_ROLE in [_.name for _ in message.author.roles]:
            # Get results for all present users in the channel
            saved_ids = set([_ for _ in self.saved_results.keys()])
            present_ids = set([_.id for _ in message.channel.members])
            result_lines = []
            for key in present_ids.intersection(saved_ids):
                name = self.get_user(key).display_name
                result, obstacle, reason = await self.fetch_result_details(key)
                dice_result_str = await self.resolve_dice_result_str(result, obstacle)
                result_lines.append(f'{name}: {dice_result_str}')
            result_lines_str = '\n'.join(result_lines)
            await message.channel.send(f"**Here is everyone's past roll:**\n>>> {result_lines_str}")
        
        elif message.author.id not in self.saved_results:
            await message.channel.send(f"**{message.author.mention}** hasn't rolled before!")
        
        else:
            result, obstacle, reason = await self.fetch_result_details(message.author.id)
            dice_result_str = await self.resolve_dice_result_str(result, obstacle)
            await message.channel.send(
                    f'**{message.author.mention}\'s last roll:**\n'
                    f'> {dice_result_str}'
            )


    async def usage(self, message):
        '''!help'''
        m = NUDGE_REGEX.match(message.content)
        await message.channel.send(
                f'```Usage:\n'
                f'\t!roll <dice> [Ob <req>] [for <reason>]\n'
                f'\t!reroll <quantity>\n'
                f'\t!explode <quantity>\n'
                f'\t!last'
                f'```'
        )


    async def to_emoji_str(self, result):
        '''Converts a list of d6 numbers to emojis, then joins by spaces.'''
        return " ".join([EMOJI_MAP[_] for _ in result])


    async def persist(self, key, results, reason=None, obstacle=None):
        '''Replace the JSON file with saved results dict.'''
        

        data = {
            'results': results,
            'reason': reason,
            'obstacle': obstacle
        }
        self.saved_results[key] = data
        if USE_PERSIST:
            with open(SAVED_ROLLS_JSON, 'w') as f:
                json.dump(self.saved_results, f)
                print(f"New roll persisted to file. ({str(key)} --> {str(results)})")


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
