import random

# Cache for roll "builds". Key is the concat of a user ID and a channel ID (for now).
ROLL_CACHE_BY_REQUEST = {}
ROLL_CACHE_BY_MESSAGE = {}


async def is_roll(message):
    return message.id in ROLL_CACHE_BY_MESSAGE


async def owns_roll(user, message):
    return message.id in ROLL_CACHE_BY_MESSAGE and ROLL_CACHE_BY_MESSAGE[message.id].owner.id == user.id


async def start_roll(user, channel):
    key = str(user.id) + "_" + str(channel.id)
    if key in ROLL_CACHE_BY_REQUEST:
        await channel.send(f'{user.mention} - You already have a roll in progress!')
        return
    
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
        '''STATES:
        0 - have skill?
        1 - mousy nature?
        2 - roll strategy decision
        3 - gear?
        4 - helpers?
        5 - persona?
        6 - trait?
        '''
        self.owner = owner
        self.message = message
        self.state = 0
        self.has_skill = None
        self.is_mousy = None
        self.using_skill = None
        self.skill_level = 0
        self.using_nature = None
        self.nature_level = 0
        self.using_luck = None
        self.adding_nature = None
        self.with_gear = None
        self.helpers = 0
        self.persona = 0
        self.trait = 0
        self.with_tax = None
        self.result = []


    def _render_message(self, prompt, show_details=True):
        msg = f'{self.owner.mention} is rolling dice...'

        if show_details:
            total = 0
            msg += '```'
            if self.using_skill:
                msg += f'Using their trained skill! +{self.skill_level}'
                total += self.skill_level
            elif self.using_nature and self.is_mousy:
                msg += f'Leaning into their mousy nature! +{self.nature_level}'
                total += self.nature_level
            elif self.using_nature and not self.is_mousy:
                msg += f'Going against their mousy nature! +{self.nature_level} (with tax)'
                total += self.nature_level
            elif self.using_luck:
                msg += f'Attempting to try, and with luck, succeed! +{self.skill_level} (base attribute)'
                total += self.skill_level
            
            if self.with_gear:
                msg += '\nUsing the right tool for the job! +1'
                total += 1

            if self.helpers > 0:
                msg += f'\nWith some helping hands! +{self.helpers}'
                total += self.helpers

            if self.persona > 0:
                msg += f'\nBustling with raw talent! +{self.persona}'
                total += self.persona

            if self.trait > 0:
                msg += f'\nFinding their traits to be helpful! +1'
                total += 1
            elif self.trait < 0:
                msg += f'\nFinding their traits to be harmful! -1 (gain a check)'
                total -= 1

            msg += f'\n\nTotal pool: {total}'
            if self.using_luck:
                total = total // 2
            
            if self.using_luck:
                msg += f' --> {total} (beginner\'s luck)'
            msg += '```'

        if prompt:
            msg += f'\n>>> {prompt}'
        return msg

    
    def _crunch(self):
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

        if self.persona > 0:
            total += self.persona

        if self.trait > 0:
            total += 1
        elif self.trait < 0:
            total -= 1

        if self.using_luck:
            total = total // 2
        return total


    def to_emoji_str(self, result):
        from micedice import EMOJI_MAP
        '''Converts a list of d6 numbers to emojis, then joins by spaces.'''
        return " ".join([EMOJI_MAP[_] for _ in result])


    async def next(self, reaction=None):
        number_map = {'0️⃣': 0, '1️⃣': 1, '2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5, '6️⃣': 6}

        if reaction and reaction.emoji == '❌':
            await self.message.edit(content=f'{self.owner.mention} cancelled their roll.')
            await self.message.clear_reactions()
            unregister(self)
            return

        if reaction and reaction.emoji == '🏁':
            end_index = self.message.content.find('\n>>> Nudge the result?')
            if end_index:
                msg = self.message.content[:end_index]
                await self.message.edit(content=msg)
            await self.message.clear_reactions()
            unregister(self)
            return

        if self.state == 0:
            await self.message.edit(content=self._render_message('Do you have an appropriate skill?', show_details=False))
            await self.message.clear_reactions()
            await self.message.add_reaction('👍')
            await self.message.add_reaction('👎')
            await self.message.add_reaction('❌')
            self.state += 1
            return


        if not reaction:
            return

        elif self.state == 1:
            self.has_skill = reaction.emoji == '👍'
            prompt = 'What is your skill level?' if self.has_skill else 'What is your base attribute level (health or wisdom)?'
            await self.message.edit(content=self._render_message(prompt, show_details=False))
            await self.message.clear_reactions()
            await self.message.add_reaction('1️⃣')
            await self.message.add_reaction('2️⃣')
            await self.message.add_reaction('3️⃣')
            await self.message.add_reaction('4️⃣')
            await self.message.add_reaction('5️⃣')
            await self.message.add_reaction('6️⃣')
            await self.message.add_reaction('❌')
        elif self.state == 2:
            self.skill_level = number_map[reaction.emoji]
            await self.message.edit(content=self._render_message('Is the skill of a mousy nature?', show_details=False))
            await self.message.clear_reactions()
            await self.message.add_reaction('👍')
            await self.message.add_reaction('👎')
            await self.message.add_reaction('❌')
        elif self.state == 3:
            self.is_mousy =  reaction.emoji == '👍'
            await self.message.edit(content=self._render_message('What is your nature level?', show_details=False))
            await self.message.clear_reactions()
            await self.message.add_reaction('1️⃣')
            await self.message.add_reaction('2️⃣')
            await self.message.add_reaction('3️⃣')
            await self.message.add_reaction('4️⃣')
            await self.message.add_reaction('5️⃣')
            await self.message.add_reaction('6️⃣')
            await self.message.add_reaction('❌')
        elif self.state == 4:
            self.nature_level = number_map[reaction.emoji]
            msg = 'How would you like to roll?'

            if self.has_skill:
                msg += f'\n  🎯 - Use your trained skill **+{self.skill_level}** *(trains skill)*'
            else:
                msg += f'\n  🍀 - Use beginner\'s luck **+{self.skill_level}** *(dice pool halved, start training skill)*'

            if self.is_mousy:
                msg += f'\n  🐭 - Work with your mousy nature **+{self.nature_level}** *(doesn\'t train skill)*'
            else:
                msg += f'\n  🐭 - Work against your mousy nature **+{self.nature_level}** *(doesn\'t train skill, failure taxes nature!)*'

            await self.message.clear_reactions()
            await self.message.edit(content=self._render_message(msg, show_details=False))
            if self.has_skill:
                await self.message.add_reaction('🎯')
            else:
                await self.message.add_reaction('🍀')
            await self.message.add_reaction('🐭')
            await self.message.add_reaction('❌')
        elif self.state == 5:
            self.using_skill = reaction.emoji == '🎯' 
            self.using_nature = reaction.emoji == '🐭'
            self.using_luck = reaction.emoji == '🍀'
            await self.message.edit(content=self._render_message('Tap nature for a boost (-1 persona 🎭, +X 🎲 equal to nature, tax)?'))
            await self.message.clear_reactions()
            await self.message.add_reaction('👍')
            await self.message.add_reaction('👎')
            await self.message.add_reaction('❌')
        elif self.state == 6:
            self.tap_nature = reaction.emoji == '👍'
            await self.message.edit(content=self._render_message('Do you have appropriate gear (+1 🎲)?'))
            await self.message.clear_reactions()
            await self.message.add_reaction('👍')
            await self.message.add_reaction('👎')
            await self.message.add_reaction('❌')
        elif self.state == 7:
            self.with_gear = reaction.emoji =='👍'
            await self.message.edit(content=self._render_message('How many helpers do you have? (+1 🎲 each)'))
            await self.message.clear_reactions()
            await self.message.add_reaction('0️⃣')
            await self.message.add_reaction('1️⃣')
            await self.message.add_reaction('2️⃣')
            await self.message.add_reaction('3️⃣')
            await self.message.add_reaction('4️⃣')
            await self.message.add_reaction('5️⃣')
            await self.message.add_reaction('6️⃣')
            await self.message.add_reaction('❌')
        elif self.state == 8:
            self.helpers = number_map[reaction.emoji]
            await self.message.edit(content=self._render_message('How many bonus 🎲 dice (-1 persona 🎭 each) will you take?'))
            await self.message.clear_reactions()
            await self.message.add_reaction('0️⃣')
            await self.message.add_reaction('1️⃣')
            await self.message.add_reaction('2️⃣')
            await self.message.add_reaction('3️⃣')
            await self.message.add_reaction('❌')
        elif self.state == 9:
            self.persona = number_map[reaction.emoji]
            await self.message.edit(content=self._render_message('Do you a relevant trait?'))
            await self.message.clear_reactions()
            await self.message.add_reaction('👍')
            await self.message.add_reaction('👎')
            await self.message.add_reaction('❌')
        elif self.state == 10:
            has_trait = reaction.emoji =='👍'

            if not has_trait:
                self.state += 1
                reaction.emoji = '😐'
                return await self.next(reaction)
            
            await self.message.edit(content=self._render_message('Is a trait helping you (+1 🎲), or hurting you?'))
            await self.message.clear_reactions()
            await self.message.add_reaction('😊')
            await self.message.add_reaction('😐')
            await self.message.add_reaction('😩')
            await self.message.add_reaction('❌')
        elif self.state == 11:
            if reaction.emoji == '😊':
                self.trait = 1
            elif reaction.emoji == '😐':
                self.trait = 0
            elif reaction.emoji == '😩':
                self.trait = -1

            self.result = sorted([random.randint(1, 6) for i in range(self._crunch())])
            self.new_axes = len([_ for _ in self.result if _ == 6])
            self.rerolled = False
            successes = len([_ for _ in self.result if _ >= 4])

            msg = self._render_message(None)
            msg += f'\n{self.owner.mention} rolls the dice!\n{self.to_emoji_str(self.result)}    ➡️    **{successes}**!\n> Are you wise?'
            await self.message.edit(content=msg)
            await self.message.clear_reactions()
            await self.message.add_reaction('👍')
            await self.message.add_reaction('👎')
            await self.message.add_reaction('❌')
        elif self.state >= 12:
            exploded = False
            reroll_one = False
            reroll_all = False
            if self.state == 11:
                self.is_wise = reaction.emoji == '👍'
            elif self.state > 11:
                exploded = reaction.emoji == '💥'
                reroll_one = reaction.emoji == '🔮'
                reroll_all = reaction.emoji == '🎭'
            successes = len([_ for _ in self.result if _ >= 4])
            
            msg = self._render_message(None)
            msg += f'\n{self.owner.mention} rolls the dice!\n{self.to_emoji_str(self.result)}    ➡️    **{successes}**!'

            snakes = [_ for _ in self.result if _ < 4]
            if exploded:
                new_dice = sorted([random.randint(1, 6) for i in range(self.new_axes)])
                self.new_axes = len([_ for _ in new_dice if _ == 6])
                new_result = sorted(self.result + new_dice)
                self.result = new_result
                msg += f'\n\n{self.owner.mention} rolls a new die for each axe ({len(new_dice)})!'
                msg += f'\n  ...and gets {self.to_emoji_str(new_dice)}, for a new result of...'
                msg += f'\n\n{self.to_emoji_str(self.result)}    ➡️    **{successes}**!'
            if reroll_one:
                self.rerolled = True
                new_dice = [random.randint(1, 6)]
                new_result = sorted(self.result[1:] + new_dice)
                self.result = new_result
                self.new_axes += len([_ for _ in new_dice if _ == 6])
                msg += f'\n\n{self.owner.mention} re-rolls a snake!'
                msg += f'\n  ...and gets {self.to_emoji_str(new_dice)}, for a new result of...'
                msg += f'\n\n{self.to_emoji_str(self.result)}    ➡️    **{successes}**!'
            if reroll_all:
                self.rerolled = True
                new_dice = [random.randint(1, 6) for i in range(len(snakes))]
                new_result = sorted(self.result[len(snakes):] + new_dice)
                self.result = new_result
                self.new_axes += len([_ for _ in new_dice if _ == 6])
                msg += f'\n\n{self.owner.mention} re-rolls all snakes ({len(snakes)})!'
                msg += f'\n  ...and gets {self.to_emoji_str(new_dice)}, for a new result of...'
                msg += f'\n\n{self.to_emoji_str(self.result)}    ➡️    **{successes}**!'
            msg += '\n>>> Nudge the result?'
            msg += '\n  🏁 - Finish!'
            if self.new_axes > 0:
                msg += f'\n  💥 - Re-roll all ({self.new_axes}) axes (-1 fate)!'
            if self.is_wise and not self.rerolled and len(snakes) > 0:
                msg += '\n  🔮 - Re-roll one snake! (-1 fate)'
                msg += '\n  🎭 - Re-roll all snakes! (-1 persona)'
            await self.message.edit(content=msg)
            await self.message.clear_reactions()
            await self.message.add_reaction('🏁')
            if self.new_axes > 0:
                await self.message.add_reaction('💥')
            if self.is_wise and not self.rerolled and len(snakes) > 0:
                await self.message.add_reaction('🔮')
                await self.message.add_reaction('🎭')
            await self.message.add_reaction('❌')
        
        
        if self.state <= 12:
            self.state += 1
        
