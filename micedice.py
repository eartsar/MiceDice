import sys
import os
import json
import random
import re
import argparse
import yaml
import discord


parser = argparse.ArgumentParser(description='Run the MiceDice bot.')
parser.add_argument('--config', type=str, required=True, 
                    help='The path to the configuration yml.')
args = parser.parse_args()

# Load the config file, start the client
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
ROLL_REGEX = re.compile(r'\!roll (\d{1,2})((:? for )?(.+))?')
NUDGE_REGEX = re.compile(r'\!(:?nudge|reroll) (explode|one|all)')
LAST_REGEX = re.compile(r'\!last')
HELP_REGEX = re.compile(r'\!(:?help|usage)')

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

            if ROLL_REGEX.match(message.content):
                await self.roll(message)
            elif NUDGE_REGEX.match(message.content):
                await self.nudge(message)
            elif LAST_REGEX.match(message.content):
                await self.last(message)
            elif HELP_REGEX.match(message.content):
                await self.usage(message)
            # else is a quiet no-op


    async def roll(self, message):
        '''!roll <#> [for <reason>]'''
        m = ROLL_REGEX.match(message.content)

        if not m or len(m.groups()) != 4:
            await self.usage(message)
            return

        num = int(m.group(1))
        reason = m.group(2)

        if num < 1 or num > 15:
            await message.channel.send("Rolls must be with 1~15 dice.")
            return

        # roll dice
        result = []
        for i in range(num):
            result.append(random.randint(1, 6))
        result = sorted(result)
        result_str = " ".join(await self.render(result))

        await message.channel.send(
                f"**{message.author.mention}** is rolling **{num}** dice **for {reason}**\n"
                f"> {result_str}"
                if reason else
                f"**{message.author.mention}** is rolling **{num}** dice\n"
                f"> {result_str}"
        )
        await self.persist(key=message.author.id, results=result)


    async def nudge(self, message):
        '''!nudge <one|all|explode>'''
        m = NUDGE_REGEX.match(message.content)
        method = m.group(2)

        # User must have results to nudge.
        if message.author.id not in self.saved_results:
            await message.channel.send(f"**{message.author.mention}** hasn't rolled before!")
            return
        
        result = self.saved_results[message.author.id]
        if method == 'one':
            # Needs a snake to re-roll
            if result[0] > 3:
                await message.channel.send(f"**{message.author.mention}** has no failures to re-roll!")
                return

            # Grab the lowest die, re-roll it, re-order, persist
            new = random.randint(1, 6)
            result[0] = new
            new_result = sorted(result)
            new_str = EMOJI_MAP[new]
            new_result_str = " ".join(await self.render(new_result))
            await message.channel.send(
                    f"**{message.author.mention}** re-rolls one of their {SNAKE_EMOJI}...\n"
                    f"\t\t...and it's a {new_str}!\n"
                    f"> {new_result_str}"
            )
            await self.persist(key=message.author.id, results=new_result)
        elif method == 'all':
            # Needs a snake to re-roll
            if result[0] > 3:
                await message.channel.send(f"**{message.author.mention}** has no failures to re-roll!")
                return

            # Grab all snakes, reroll into new list, merge upper slice, re-order, persist
            snakes = [_ for _ in result if _ < 4]
            num_snakes = len(snakes)
            new = []
            for snake in snakes:
                new.append(random.randint(1, 6))
            new = sorted(new)
            new_str = " ".join(await self.render(new))
            new_result = sorted(result[len(snakes):] + new)
            new_result_str = " ".join(await self.render(new_result))
            await message.channel.send(
                    f"**{message.author.mention}** re-rolls {num_snakes} of their {SNAKE_EMOJI}...\n"
                    f"\t\t...and gets {new_str}!\n"
                    f"> {new_result_str}"
            )
            await self.persist(key=message.author.id, results=new_result)
        elif method == 'explode':
            # Needs an axe to re-roll
            if result[-1] != 6:
                await message.channel.send(f"**{message.author.mention}** has no {AXE_EMOJI} to explode!")
                return

            # Create new list with new rolls, one for each axe, merge, re-order, persist
            axes = [_ for _ in result if _ == 6]
            num_axes = len(axes)
            new = []
            for axe in axes:
                new.append(random.randint(1, 6))
            new = sorted(new)
            new_str = " ".join(await self.render(new))
            new_result = sorted(result + new)
            new_result_str = " ".join(await self.render(new_result))
            await message.channel.send(
                    f"**{message.author.mention}** explodes {num_axes} of their {AXE_EMOJI}!\n"
                    f"\t\t...and gets {new_str}!\n"
                    f"> {new_result_str}"
            )
            await self.persist(key=message.author.id, results=new_result)


    async def last(self, message):
        if GM_ROLE in [_.name for _ in message.author.roles]:
            build = "**Here is everyone's past roll:**\n"
            saved = set([_ for _ in self.saved_results.keys()])
            present = set([_.id for _ in message.channel.members])
            saved_present = present.intersection(saved)
            for key in saved_present:
                build += "> " + self.get_user(key).display_name + ": " + " ".join(await self.render(self.saved_results[key])) + "\n"
            await message.channel.send(build)
        elif message.author.id not in self.saved_results:
            await message.channel.send(f"**{message.author.mention}** hasn't rolled before!")
        else:
            result = self.saved_results[message.author.id]
            result_str = await self.render(result)
            result_str = " ".join(result_str)
            await message.channel.send(
                    f'**{message.author.mention}\'s last roll:**\n'
                    f'> {result_str}'
            )


    async def usage(self, message):
        '''!help'''
        m = NUDGE_REGEX.match(message.content)
        await message.channel.send(
                f'**Usage:**```'
                f'\t!roll <#> [for <reason>]\n'
                f'\t!nudge <explode|one|all>\n'
                f'\t!last'
                f'```'
        )


    async def render(self, result):
        '''Converts a list of numbers (d6) to proper emojis.'''
        return [EMOJI_MAP[_] for _ in result]


    async def persist(self, key=None, results=None):
        '''Replace the JSON file with saved results dict.'''
        if key and results:
            self.saved_results[key] = results
        with open(SAVED_ROLLS_JSON, 'w') as f:
            json.dump(self.saved_results, f)
            print("New roll persisted to file.")


def main():
    client = MiceDice()
    client.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
