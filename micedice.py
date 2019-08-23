import sys
import os
import json
import random
import re
import argparse
import asyncio
import yaml
import discord


parser = argparse.ArgumentParser(description='Run the MiceDice bot.')
parser.add_argument('--config', type=str, required=True, 
                    help='The path to the configuration yml.')
args = parser.parse_args()

# Load the config file
config = {}
with open(args.config, 'r') as f:
    config = yaml.safe_load(f)

BOT_TOKEN = config['bot_token']
SNAKE_EMOJI = config['snake_emoji']
SWORDS_EMOJI = config['swords_emoji']
AXE_EMOJI = config['axe_emoji']
GM_ROLE = config['gm_role']

# Only the best persistence engine for my bot... a json file
SAVED_ROLLS_JSON = config['saved_rolls_path']

# Meh, I'll just use regexes to parse commands. Easy enough.
ROLL_REGEX = re.compile(r'\!roll (\d{1,2})(?:\s?[Oo][Bb]\s?(\d))?(?:(?: for )?(.+))?')
NUDGE_REGEX = re.compile(r'\!(?:nudge|reroll) (explode|one|all)')
LAST_REGEX = re.compile(r'\!last')
# Catch-all regex. Doesn't look at args.
# User attempted to use a command with bad syntax, or needs help.
USAGE_REGEX = re.compile(r'\!(:?help|usage|roll|nudge)')

# Aliases for commands. Shortcuts. Alternates.
ALIASES = {
    '!explode': '!nudge explode'
}

# Translates a d6 --> MG d6
EMOJI_MAP = {
    1: SNAKE_EMOJI, 
    2: SNAKE_EMOJI, 
    3: SNAKE_EMOJI, 
    4: SWORDS_EMOJI, 
    5: SWORDS_EMOJI, 
    6: AXE_EMOJI, 
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

        # Create the file (empty json) if it doesn't exist yet
        if os.path.isfile(SAVED_ROLLS_JSON):
            # Load the file into the saved rolls
            temp = {}
            with open(SAVED_ROLLS_JSON, 'r') as f:
                temp = json.load(f)
                for key in temp:
                    # ints aren't JSON keys, they persist as strings
                    # re-convert them to ints on load
                    self.saved_results[int(key)] = temp[key]
                print(f"Rolls loaded from {SAVED_ROLLS_JSON}")


    async def on_ready(self):
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
            elif m.match(NUDGE_REGEX):
                method = m.group(1)
                await self.nudge(message, method)
            elif m.match(LAST_REGEX):
                await self.last(message)
            elif m.match(USAGE_REGEX):
                await self.usage(message)
            # else is a quiet no-op


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
        
        roll_str = f"**{message.author.mention}** is rolling **{num_dice}** dice"
        reason_str = f'**for {reason}**' if reason else ''
        dice_result_str = await self.resolve_dice_result_str(result, obstacle=obstacle)
        
        await message.channel.send(f'{roll_str} {reason_str}\n>>> {dice_result_str}')
        await self.persist(key=message.author.id, results=result, obstacle=obstacle, reason=reason)


    async def nudge(self, message, method):
        '''!nudge <one|all|explode>'''
        # User must have results to nudge.
        if message.author.id not in self.saved_results:
            await message.channel.send(f"**{message.author.mention}** hasn't rolled before!")
            return
        
        key = message.author.id
        result, obstacle, reason = await self.fetch_result_details(key)
        nudge_str = None
        
        if method == 'one':
            if result[0] > 3:
                return await message.channel.send(f"**{message.author.mention}** has no failures to re-roll!")
            nudge_str, result = await self.nudge_one(message, result)
        
        elif method == 'all':
            if result[0] > 3:
                return await message.channel.send(f"**{message.author.mention}** has no failures to re-roll!")
            nudge_str, result = await self.nudge_all(message, result)
        
        elif method == 'explode':
            if result[-1] != 6:
                return await message.channel.send(f"**{message.author.mention}** has no {AXE_EMOJI} to explode!")
            result = await self.nudge_explode(message, result)
        
        else:
            return await self.usage(message)

        # Print and persist
        dice_result_str = await self.resolve_dice_result_str(result, obstacle)
        send_str = f'{nudge_str}\n>>> {dice_result_str}'
        await message.channel.send(send_str)
        await self.persist(key=key, results=result, obstacle=obstacle, reason=reason)


    async def nudge_one(self, message, result):
        '''# Grab the lowest die, re-roll it, re-order, persist'''
        result[0] = random.randint(1, 6)
        rerolled_str = EMOJI_MAP[result[0]]
        result = sorted(result)
        nudge_str = (
                f"**{message.author.mention}** re-rolls one of their {SNAKE_EMOJI}...\n"
                f"\t\t...and it's a {rerolled_str}!"
        )
        return nudge_str, result


    async def nudge_all(self, message, result):
        '''Grab all snakes, reroll into new list, merge upper slice, re-order, persist'''
        snakes = [_ for _ in result if _ < 4]
        rerolled_results = sorted([random.randint(1, 6) for snake in snakes])
        rerolled_str = await self.to_emoji_str(rerolled_results)
        result = sorted(result[len(snakes):] + rerolled_results)
        nudge_str = (
                f"**{message.author.mention}** re-rolls {len(snakes)} of their {SNAKE_EMOJI}...\n"
                f"\t\t...and gets {rerolled_str}!"
        )
        return nudge_str, result


    async def nudge_explode(self, message, result):
        '''Explosions are fun. For each axe, roll a new die.
        In this implementation, we'll make sure to show each step, since it cascades.

        Due to discord setting a max message size, and the large nature of emoijs
        this function will stagger sending messages, as the cascade resolves.

        TODO: This is a kludge. Clean this up.'''
        initial_axes = result.count(6)
        build = f"**{message.author.mention}** explodes {initial_axes} of their {AXE_EMOJI}!\n "
        await message.channel.send(build)
        await asyncio.sleep(1)
        level = 0
        previous = result
        total_added_results = []
        while True:
            added = sorted([random.randint(1, 6) for i in range(previous.count(6))])
            added_str = await self.to_emoji_str(added)
            total_added_results = sorted(total_added_results + added)
            build = ('\t\t' * level) + '...and gets ' + added_str
            previous = added
            level += 1
            if added.count(6) > 0:
                build += '... and explodes some more!\n'
                await message.channel.send(build)
                await asyncio.sleep(1)
            else:
                await message.channel.send(build)
                await asyncio.sleep(1)
                break
        result = sorted(result + total_added_results)
        return result


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
                f'\t!nudge <explode|one|all>\n'
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
        
        with open(SAVED_ROLLS_JSON, 'w') as f:
            json.dump(self.saved_results, f)
            print("New roll persisted to file.")


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
