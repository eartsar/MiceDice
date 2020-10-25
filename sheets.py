import os.path
import asyncio
import functools 

import pygsheets
from asgiref.sync import sync_to_async

from cells import sheet_index


CHARACTER_INDEX = sheet_index['character']


# Necessary permissions to interact with google sheets.
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

BASE_STATS = ['nature', 'health', 'will', 'circles', 'resources']
SKILL_LIST = ['administrator', 'apiarist', 'archivist', 'armorer', 'baker', 'boatcrafter',
                'brewer', 'carpenter', 'cartographer', 'cook', 'fighter', 'glazier', 'haggler',
                'harvester', 'healer', 'hunter', 'insectrist', 'instructor', 'laborer',
                'loremouse', 'manipulator', 'militarist', 'miller', 'orator', 'pathfinder', 
                'persuader', 'potter', 'scientist', 'scout', 'smith', 'stonemason',
                'survivalist', 'weather watcher', 'weaver']
PROGRESSIONS = BASE_STATS + SKILL_LIST


def with_profile(fn):
    '''This decorator does a few things.

    First, it will see if there's a loaded profile. If there is none, it will attempt to load the
    last used profile, if one exists. If no profile can be loaded, it will send a message back to the
    channel instructing the user to register a profile before using the command.

    The sheet associated with the profile will pull its data, and be sent to the wrapped function.

    This is only meant to decorate SheetManager methods that require an active sheets profile.
    Requires user and channel as first two positions args of the wrapped function.'''
    from functools import wraps
    @wraps(fn)
    async def wrapper(self, user, channel, *args, **kwargs):
        if user.id not in self.sheets_cache:
            key = await self.db_manager.get_current(user)
            if key:
                await self.use_profile(user, key)

        # Don't bother running
        if user.id not in self.sheets_cache:
            return await channel.send(f'{user.mention} - No profile selected. Select with `!profile select`.')
        sheet = self.sheets_cache[user.id]
        await sheet.pull()
        return await fn(self, user, channel, sheet=sheet, *args, **kwargs)
    return wrapper



class SheetManager():
    def __init__(self, creds_path, db_manager):
        self.creds_path = creds_path
        self.db_manager = db_manager
        self.sheets_cache = {}
        self.profile_selector_cache_by_message = {}
        self.profile_selector_cache_by_request = {}
        self.lock = asyncio.Lock()


    async def initialize(self):
        async with self.lock:
            # Just test the authentication to google services via service account
            print("  Authenticating to google web services...")
            await self.get_gc()
            print("  Done.")


    def _generate_request_key(self, user, channel):
        return str(user.id) + "_" + str(channel.id)


    async def uncache_profile_selector(self, profile_selector):
        async with self.lock:
            key = self._generate_request_key(profile_selector.owner, profile_selector.message)
            del self.profile_selector_cache_by_message[profile_selector.message.id]
            del self.profile_selector_cache_by_request[key]


    async def cache_profile_selector(self, profile_selector):
        async with self.lock:
            key = self._generate_request_key(profile_selector.owner, profile_selector.message)
            self.profile_selector_cache_by_message[profile_selector.message.id] = profile_selector
            self.profile_selector_cache_by_request[key] = profile_selector
    

    async def get_gc(self):
        return await sync_to_async(pygsheets.authorize)(service_file=self.creds_path)


    async def handle_event(self, user, reaction):
        # If not a "roll" message, bail
        if reaction.message.id in self.profile_selector_cache_by_message:
            # If the reaction is from the owner, and a valid option, interpet it. Otherwise, purge.
            profile_selector = self.profile_selector_cache_by_message[reaction.message.id]
            if profile_selector.owner.id == user.id and reaction.count > 1:
                await profile_selector.select(reaction=reaction)
            else:
                await reaction.remove(user)
        
    
    async def register_profile(self, channel, user, key):
        was_added = await self.db_manager.add_profile(user, key)
        msg = 'Profile registered' if was_added else 'A profile already exists with that key'
        await channel.send(f'{user.mention} - {msg}.')


    async def unregister_profile(self, channel, user, key):
        was_deleted = await self.db_manager.delete_profile(user, key)
        msg = 'Profile unregistered' if was_deleted else 'No profile found with that key'
        await channel.send(f'{user.mention} - {msg}.')


    async def use_profile(self, user, key):
        sheet = self.sheets_cache[user.id] if user.id in self.sheets_cache else GoogleBackedSheet(self, key)
        await self.db_manager.update_current(user, key)
        self.sheets_cache[user.id] = sheet


    async def initiate_choose_profile(self, user, channel):
        key = self._generate_request_key(user, channel)
        if key in self.profile_selector_cache_by_request:
            await self.profile_selector_cache_by_request[key].cancel()
        
        profile_selector = ProfileSelector(self, user, channel)
        await profile_selector.initialize()
        await self.cache_profile_selector(profile_selector)
        profile_keys = await self.db_manager._get_profile_keys(user)
        if not profile_keys:
            profile_selector.message.edit(f'{user.mention} - No profiles registered. Register with `!profile register <url|key>`.')
        await profile_selector.offer_profiles(profile_keys)
        

    @with_profile
    async def display(self, user, channel, sheet=None):
        to_render = '\n'.join([await sheet._render_rating(skill) for skill in PROGRESSIONS if sheet.get_rating(skill)])
        msg = f'''```
 {'='*(len(sheet.name) + 2)}
| {sheet.name} |
==============================================
SKILL                 SUCCESS      FAIL
----------------------------------------------
{to_render}
==============================================
```'''
        return await channel.send(f'{user.mention} - Your current profile:\n{msg}')        



class ProfileSelector():
    def __init__(self, manager, owner, channel):
        self.manager = manager
        self.owner = owner
        self.channel = channel
        self.profile_choices = {}
        self.lock = asyncio.Lock()


    async def initialize(self):
        self.message = await self.channel.send(f'{self.owner.mention} - Initializing...')


    async def offer_profiles(self, profiles):
        nums = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        
        profiles = profiles[:5]
        for i in range(len(profiles)):
            self.profile_choices[nums[i]] = profiles[i]
        
        choices = '\n'.join(['> ' + nums[i] + '  -  `' + profiles[i] + '`' for i in range(len(profiles))])
        msg = f'{self.owner.mention} - Select a profile\n\n{choices}'
        await self.message.edit(content=msg)
        await self.message.clear_reactions()
        for emoji in nums[:len(profiles)]:
            await self.message.add_reaction(emoji)
        await self.message.add_reaction('❌')


    async def cancel(self):
        await self.message.edit(content=f'{self.owner.mention} - Profile select cancelled.')
        await self.message.clear_reactions()
        await self.manager.uncache_profile_selector(self)


    async def select(self, reaction=None):
        # Lock prevents responses from interrupting previous runs while finishing
        # work, like loading emoji options for a particular question.
        async with self.lock:
            # Assess the response to the previous prompt.
            # Cancel button - close out the builder.
            if reaction and reaction.emoji == '❌':
                print('blah')
                await self.cancel()
                return
            else:
                await self.message.edit(content=f'{self.owner.mention} - Using profile `{self.profile_choices[reaction.emoji]}`')
                await self.manager.use_profile(self.owner, self.profile_choices[reaction.emoji])
                await self.message.clear_reactions()
                await self.manager.uncache_profile_selector(self)





class GoogleBackedSheet():
    def __init__(self, manager, google_sheet_key):
        self.manager = manager
        self.google_sheet_key = google_sheet_key


    async def access_sheet(self):
        gc = await self.manager.get_gc()
        spreadsheet = await sync_to_async(gc.open_by_key)(self.google_sheet_key)
        worksheet = await sync_to_async(spreadsheet.worksheet_by_title)('Character Sheet')
        return worksheet


    async def pull(self):
        '''Pulls all data from a sheet to local cache'''
        sheet = await self.access_sheet()
        data = await sync_to_async(sheet.get_all_values)()

        # do translations
        self.player = self._access(data, CHARACTER_INDEX['player'])
        self.name = self._access(data, CHARACTER_INDEX['name'])
        self.home = self._access(data, CHARACTER_INDEX['home'])
        self.age = self._access(data, CHARACTER_INDEX['age'])
        self.fur = self._access(data, CHARACTER_INDEX['fur'])
        self.rank = self._access(data, CHARACTER_INDEX['rank'])
        self.specialty = self._access(data, CHARACTER_INDEX['specialty'])
        self.cloak = self._access(data, CHARACTER_INDEX['cloak'])
        self.weapon = self._access(data, CHARACTER_INDEX['weapon'])
        self.skills = {}

        for base in BASE_STATS:
            val = {
                'rating': self._access_try_int(data, CHARACTER_INDEX[base]['rating']),
                'success': self._access_try_int(data, CHARACTER_INDEX[base]['success']),
                'fail': self._access_try_int(data, CHARACTER_INDEX[base]['fail'])
            }
            self.skills[base] = val
            

        # Initialize bare skills, then populate from sheet
        for skill in SKILL_LIST:
            self.skills[skill] = { 'rating': None, 'success': 0, 'fail': 0 }

        for skill in CHARACTER_INDEX['skills']:
            name = self._access(data, skill['name']).lower()
            # Missing skill in sheet, empty space
            if not name:
                continue
            # Skill with bad name in sheet, big deal
            if name not in SKILL_LIST:
                continue
            val = {
                'rating': self._access_try_int(data, skill['rating']),
                'success': self._access_try_int(data, skill['success']),
                'fail': self._access_try_int(data, skill['fail']),
            }
            self.skills[name] = val


    def get_success(self, key):
        return self._get_skill_subvalue(key, 'success')


    def get_fail(self, key):
        return self._get_skill_subvalue(key, 'fail')


    def get_rating(self, key):
        return self._get_skill_subvalue(key, 'rating')


    def check_valid_skill(self, skill):
        return skill in PROGRESSIONS


    def _get_skill_subvalue(self, key, subvalue):
        return self.skills[key][subvalue] if key in self.skills else None


    def _access(self, data, cell):
        col = ord(cell[0]) - ord('A')
        row = int(cell[1:]) - 1
        return data[row][col]


    def _access_try_int(self, data, cell):
        # Convert to an int if possible. If not, return as-is
        val = self._access(data, cell)
        try:
            val = int(val)
        except:
            if val:
                val = val.lower()
        return val


    async def _render_rating(self, skill):
        if skill not in self.skills:
            return
        
        values = self.skills[skill]
        use_luck = self.get_rating(skill) == 'x'
        success_fill = self.get_success(skill)
        success_empty = self.get_rating(skill) - self.get_success(skill) if not use_luck else 7 - self.get_success(skill)
        fail_fill = self.get_fail(skill) if not use_luck else 0
        fail_empty = self.get_rating(skill) - self.get_fail(skill) - 1 if not use_luck else 0

        skill_portion = f"{skill.title()}: {self.get_rating(skill) if not use_luck else '*'}"
        success_portion = f"{'✓'*success_fill + '◯'*success_empty}"
        fail_portion = f"{'✓'*fail_fill + '◯'*fail_empty}"
        progress_portion = f"[ {success_portion}{' '*(10 - len(success_portion))} | {fail_portion}{' '*(9 - len(fail_portion))} ]"
        return f"{skill_portion}{' '*(20 - len(skill_portion))}{progress_portion}"
