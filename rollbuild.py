from decimal import Decimal, ROUND_HALF_UP
import asyncio
import random
import dicepool
from util import to_emoji_str

# Cache for roll "builders". Key is the concat of a user ID and a channel ID (for now).
ROLL_CACHE_BY_REQUEST = {}
ROLL_CACHE_BY_MESSAGE = {}

# mapping of emoji to numeric value
NUM_MAP = {'0️⃣': 0, '1️⃣': 1, '2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5, '6️⃣': 6, '7️⃣': 7}


async def is_roll(message):
    return message.id in ROLL_CACHE_BY_MESSAGE


async def owns_roll(user, message):
    return message.id in ROLL_CACHE_BY_MESSAGE and ROLL_CACHE_BY_MESSAGE[message.id].owner.id == user.id


async def start_roll(user, channel):
    key = str(user.id) + "_" + str(channel.id)
    if key in ROLL_CACHE_BY_REQUEST:
        await ROLL_CACHE_BY_REQUEST[key].cancel()
    
    message = await channel.send(f'{user.mention}\'s roll: Initializing...')
    roll = RollBuilder(user, message)
    ROLL_CACHE_BY_MESSAGE[message.id] = roll
    ROLL_CACHE_BY_REQUEST[key] = roll
    await roll.next()


async def next(reaction):
    roll = ROLL_CACHE_BY_MESSAGE[reaction.message.id]
    await roll.next(reaction=reaction)


def unregister(roll):
    del ROLL_CACHE_BY_MESSAGE[roll.message.id]
    key = str(roll.owner.id) + "_" + str(roll.message.channel.id)
    del ROLL_CACHE_BY_REQUEST[key]



class RollBuilder():
    def __init__(self, owner, message):
        self.owner = owner
        self.message = message
        self.has_skill = None
        self.is_mousy = None
        self.using_skill = None
        self.skill_level = 0
        self.using_nature = None
        self.nature_level = 0
        self.using_luck = None
        self.tapping_nature = None
        self.with_gear = None
        self.helpers = 0
        self.persona = 0
        self.trait = 0
        self.with_tax = None
        self.is_wise = None
        self.tooltip = None
        self.tooltip_enabled = False
        self.pool = dicepool.DicePool()
        self.result = []
        self.setting_options = True
        self.lock = asyncio.Lock()

        # These are the linear steps to building a roll. As each gets executed, they'll get popped off the list.
        self.steps = [
            self._ask_has_skill, 
            self._ask_skill_level, 
            self._ask_mousy_nature, 
            self._ask_nature_level, 
            self._ask_roll_strategy, 
            self._ask_gear_bonus, 
            self._ask_num_helpers,
            self._ask_nature_boost,
            self._ask_persona_bonus, 
            self._ask_relevant_trait, 
            self._ask_trait_help_or_hurt, 
            self._confirm_roll,
            self._roll_and_ask_wise, 
            self._nudge_roll_until_done
        ]


    def _render_message(self, prompt, show_details=True):
        msg = f'{self.owner.mention} is rolling dice...'

        if show_details:
            msg += '```'

            if self.using_luck:
                msg += '\n------------------------------------------\n'
            
            if self.using_skill:
                msg += f'Using their trained skill! +{self.skill_level}'
            elif self.using_nature and self.is_mousy:
                msg += f'Leaning into their mousy nature! +{self.nature_level}'
            elif self.using_nature and not self.is_mousy:
                msg += f'Going against their mousy nature! +{self.nature_level} (tax)'
            elif self.using_luck:
                msg += f'Attempting to try, and with luck, succeed! +{self.skill_level} (health or wisdom)'

            if self.with_gear:
                msg += '\nUsing the right tool for the job! +1'
            if self.helpers > 0:
                msg += f'\nWith some helping hands! +{self.helpers}'

            if self.using_luck:
                msg += '\n------------------------------------------'
                msg += '\n            HALVED DUE TO LUCK\n'

            if self.tapping_nature:
                msg += f'\nTaps into their mouseness for a heroic boost! +{self.nature_level} (tax)'
            if self.persona > 0:
                msg += f'\nBustling with raw talent! +{self.persona}'

            if self.trait > 0:
                msg += f'\nFinding their traits to be helpful! +1'
            elif self.trait < 0:
                msg += f'\nFinding their traits to be harmful! -1 (gain a check)'

            msg += f'\n\nTotal pool: {self._crunch(consider_luck=True)}```'

        if prompt:
            msg += f'\n>>> **{prompt}**'

        return msg

    
    def _crunch(self, consider_luck=False):
        total = 0
        if self.using_skill:
            total += self.skill_level
        elif self.using_nature and self.is_mousy:
            total += self.nature_level
        elif self.using_nature and not self.is_mousy:
            total += self.nature_level
        elif self.using_luck:
            total += self.skill_level
        
        if self.with_gear:
            total += 1

        if self.helpers > 0:
            total += self.helpers

        if consider_luck and self.using_luck:
            total = int(Decimal(total / 2).to_integral_value(rounding=ROUND_HALF_UP))

        if self.tapping_nature:
            total += self.nature_level

        if self.persona > 0:
            total += self.persona

        if self.trait > 0:
            total += 1
        elif self.trait < 0:
            total -= 1

        return total


    def to_emoji_str(self, result):
        from micedice import EMOJI_MAP
        '''Converts a list of d6 numbers to emojis, then joins by spaces.'''
        return " ".join([EMOJI_MAP[_] for _ in result])


    async def cancel(self):
        await self.message.edit(content=f'{self.owner.mention} cancelled their roll.')
        await self.message.clear_reactions()
        unregister(self)

    async def finish(self):
        end_index = self.message.content.find('\n>>> **Nudge the result?')
        if end_index:
            msg = self.message.content[:end_index]
            await self.message.edit(content=msg)
        await self.message.clear_reactions()
        unregister(self)


    async def new_options(self, *args):
        self.setting_options = True
        await self.message.clear_reactions()
        for emoji in args:
            await self.message.add_reaction(emoji)
        await self.message.add_reaction('❌')
        self.setting_options = False


    async def _ask_has_skill(self, reaction):
        await self.message.edit(content=self._render_message('Do you have the required skill?', show_details=False))
        await self.new_options('👍', '👎')


    async def _ask_skill_level(self, reaction):
        self.has_skill = reaction.emoji == '👍'
        prompt = 'What is your skill level?' if self.has_skill else 'What is your base attribute level?'
        self.tooltip = 'For physical tests, this is health. Otherwise, this is wisdom.' if not self.has_skill else None
        await self.message.edit(content=self._render_message(prompt, show_details=False))
        options = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣']
        if not self.has_skill:
            options += ['ℹ️']
        await self.new_options(*options)


    async def _ask_mousy_nature(self, reaction):
        self.skill_level = NUM_MAP[reaction.emoji]
        self.tooltip = 'Escaping, climbing, hiding, and foraging are all "mousy" things.'
        await self.message.edit(content=self._render_message('Is the skill of a mousy nature?', show_details=False))
        await self.new_options('👍', '👎', 'ℹ️')


    async def _ask_nature_level(self, reaction):
        self.is_mousy =  reaction.emoji == '👍'
        await self.message.edit(content=self._render_message('What is your nature level?', show_details=False))
        await self.new_options('1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣')


    async def _ask_roll_strategy(self, reaction):
        self.nature_level = NUM_MAP[reaction.emoji]
        msg = 'How would you like to roll?\n'

        options = []
        if self.has_skill:
            options += ['🎯']
            msg += f'\n  🎯 - Use your specified skill (+{self.skill_level} 🎲)'
        else:
            options += ['🍀']
            msg += f'\n  🍀 - Use beginner\'s luck (+{self.skill_level} 🎲, pool halved ⚠️)'

        if self.is_mousy:
            msg += f'\n  🐭 - Act within your mousy nature (+{self.nature_level} 🎲)'
            options += ['🐭']
        elif not self.is_mousy and not self.has_skill:
            msg += f'\n  🐭 - Act against your mousy nature (+{self.nature_level} 🎲)'
            options += ['🐭']

        skill_help = 'If you have the specified skill, using it will count towards training your skill\'s success and failure progress.'
        luck_help = '''If you lack the skill, you can use "beginner\'s luck", which uses your base attribute in place of the required skill, \
at the cost of halving your dice pool (⚠️ excluding nature tapping, and persona dice). Choosing "beginner\'s luck" \
allows you to make progress towards learning the skill properly for future use.'''
        nature_help = '''It is also possible to use nature, instead, in some cases. Acting within your mousy nature will let you use \
your nature skill in place of the required skill, with no penalty. If you don't have the skill, you can act against your nature. \
This will let you use your nature skill instead of beginner's luck, but at a cost (tax), and does not train the skill. Use this wisely!'''
        
        portions = {'🎯': skill_help, '🍀': luck_help, '🐭': nature_help}
        includes = [portions[option] for option in options]
        spacer = '\n\n'

        options += ['ℹ️']
        self.tooltip = f'''This is the big decision!\n\n{spacer.join(includes)}'''

        await self.message.edit(content=self._render_message(msg, show_details=False))
        await self.new_options(*options)


    async def _ask_gear_bonus(self, reaction):
        self.using_skill = reaction.emoji == '🎯' 
        self.using_nature = reaction.emoji == '🐭'
        self.using_luck = reaction.emoji == '🍀'
        self.tooltip = 'Gear is a loose term for any tool or equipment that may help you. Lobby your GM!'
        await self.message.edit(content=self._render_message('Do you have appropriate gear (+1 🎲)?'))
        await self.new_options('👍', '👎', 'ℹ️')


    async def _ask_num_helpers(self, reaction):
        self.with_gear = reaction.emoji =='👍'
        self.tooltip = '''Any other player may assist (except in some cases) your test with a relevant skill. Doing so, however, will also \
potentially rope them into the consequences of failure. A mouse may offer assistance risk-free if they have a relevant wise, too.'''
        await self.message.edit(content=self._render_message('How many helpers do you have? (+1 🎲 each)'))
        await self.new_options('0️⃣', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', 'ℹ️')


    async def _ask_nature_boost(self, reaction):
        self.helpers = NUM_MAP[reaction.emoji]
        self.tooltip = '''Tapping nature will give you a big boost for making checks, but at a cost. Unless the test is within your mousy \
nature, doing this will immediately tax your nature by 1. In return, you get to add a number of dice to your pool equal to your nature skill. \
But beware! Failing the roll will further tax your nature by the margin of failure!'''
        await self.message.edit(content=self._render_message(f'Tap nature for a boost (-1 🎭 , -1 ⚖️ , +{self.nature_level} 🎲)?'))
        await self.new_options('👍', '👎', 'ℹ️')


    async def _ask_persona_bonus(self, reaction):
        self.tapping_nature = reaction.emoji == '👍'
        await self.message.edit(content=self._render_message('Would you like to use any persona points to gain bonus dice (-1 🎭 , +1 🎲 each)?'))
        await self.new_options('0️⃣', '1️⃣', '2️⃣', '3️⃣')


    async def _ask_relevant_trait(self, reaction):
        self.persona = NUM_MAP[reaction.emoji]
        await self.message.edit(content=self._render_message('Do you a relevant trait?'))
        await self.new_options('👍', '👎')


    async def _ask_trait_help_or_hurt(self, reaction):
        has_trait = reaction.emoji =='👍'

        # if no trait, skip the next question, and feed neutral as the response
        if not has_trait:
            self.steps.pop(0)
            reaction.emoji = '😐'
            self.tooltip = None
            self.tooltip_enabled = False
            return await self._confirm_roll(reaction)

        self.tooltip = '''Checks ☑️ are really important, and are effectively your "action economy" during the open-ended player turn. If you\'re 
likely to make the test handily, or fail no matter what, consider hampering your own roll this way for some easy checks!'''
        await self.message.edit(content=self._render_message('Would you like that trait to help you (+1 🎲), or hamper you (-1 🎲 , +1 ☑️)?'))
        await self.new_options('😊', '😐', '😩', 'ℹ️')


    async def _confirm_roll(self, reaction):
        if reaction.emoji == '😊':
            self.trait = 1
        elif reaction.emoji == '😐':
            self.trait = 0
        elif reaction.emoji == '😩':
            self.trait = -1

        await self.message.edit(content=self._render_message('Confirm the above looks correct. Click 🎲 when ready to roll, or ❌ to cancel.'))
        await self.new_options('🎲')


    async def _roll_and_ask_wise(self, reaction):
        self.pool.add_dice(self._crunch(consider_luck=True))
        self.pool.roll()

        msg = f'''{self._render_message(None)}
{self.owner.mention} rolls the dice!
{to_emoji_str(self.pool.current_result())}    ➡️    **{self.pool.num_successes()}**!

>>> **Are you wise?**

*Lobby your GM for a wise's relevance!*'''
        await self.message.edit(content=msg)
        await self.new_options('👍', '👎')


    async def _nudge_roll_until_done(self, reaction):
        if self.is_wise == None:
            self.is_wise = reaction.emoji == '👍'
        exploded = reaction.emoji == '💥'
        reroll_one = reaction.emoji == '🔮'
        reroll_all = reaction.emoji == '🎭'
        
        msg = self._render_message(None)
        msg += f'\n{self.owner.mention} rolls the dice!\n{to_emoji_str(self.pool.current_result())}    ➡️    **{self.pool.num_successes()}**!'

        if exploded:
            msg += f'\n\n{self.owner.mention} rolls a new die for each axe ({self.pool.num_can_explode()})!'
            self.pool.explode()
        elif reroll_one:
            msg += f'\n\n{self.owner.mention} re-rolls a snake!'
            self.pool.reroll_one()
        elif reroll_all:
            msg += f'\n\n{self.owner.mention} re-rolls all snakes ({self.pool.num_can_reroll()})!'
            self.pool.reroll_all()
        
        if exploded or reroll_one or reroll_all:
            msg += f'\n\n{self.to_emoji_str(self.pool.current_result())}    ➡️    **{self.pool.num_successes()}**!'
        
        msg += '\n\n>>> **Nudge the result?'
        msg += '\n\n  🏁 - Finish!'
        
        options = ['🏁']
        if self.pool.can_explode():
            msg += f'\n  💥 - Re-roll all ({self.pool.num_can_explode()}) axes (-1 fate)!'
            options += ['💥']
        if self.is_wise and self.pool.num_can_reroll():
            msg += '\n  🔮 - Re-roll one snake! (-1 fate)'
            msg += '\n  🎭 - Re-roll all snakes! (-1 persona)'
            options += ['🔮', '🎭']
        options += ['❓']
        msg += '''**

*Exploding axes will re-roll them for additional possible successes. Any die that lands on a six at any time is eligible to be exploded. \
Re-rolling snakes is only possible if that particular die has not already been re-rolled, though.*'''
        
        await self.message.edit(content=msg)
        await self.new_options(*options)


    async def next(self, reaction=None):
        # Cancel button - close out the builder
        
        async with self.lock:
            if reaction and reaction.emoji == '❌':
                await self.cancel()
                return

            # Finish button - Finalize the builder
            if reaction and reaction.emoji == '🏁':
                await self.finish()
                return


            if reaction and reaction.emoji == 'ℹ️':
                if not self.tooltip_enabled:
                    self.tooltip_enabled = True
                    content_with_tooltip = self.message.content + f'\n\nℹ️ *{self.tooltip}*\n'
                    await self.message.edit(content=content_with_tooltip)
                return


            # Query button - Audit the roll history with a DM
            if reaction and reaction.emoji == '❓':
                msg = f'Transparent roll log for https://discordapp.com/channels/\
{reaction.message.channel.guild.id}/\
{reaction.message.channel.id}/\
{reaction.message.id}'
                msg += "\n```" + "\n".join([str(_) for _ in self.pool.result_history]) + "```"
                await self.message.channel.send(msg)
                return

            self.tooltip = None
            self.tooltip_enabled = False
            await self.steps[0](reaction)
            
            if len(self.steps) > 1:
                self.steps.pop(0)

