import os.path
import pygsheets
from oauth2client.service_account import ServiceAccountCredentials

from cells import sheet_index


CHARACTER_INDEX = sheet_index['character']


# Necessary permissions to interact with google sheets.
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

BASE_STATS = ['nature', 'will', 'health', 'circles', 'resources']
SKILL_LIST = ['administrator', 'apiarist', 'archivist', 'armorer', 'baker', 'boatcrafter',
                'brewer', 'carpenter', 'cartographer', 'cook', 'fighter', 'glazier', 'haggler',
                'harvester', 'healer', 'hunter', 'insectrist', 'instructor', 'laborer',
                'loremouse', 'manipulator', 'militarist', 'miller', 'orator', 'pathfinder', 
                'persuader', 'potter', 'scientist', 'scout', 'smith', 'stonemason',
                'survivalist', 'weather watcher', 'weaver']
PROGRESSIONS = BASE_STATS + SKILL_LIST

# The cell that contains the corresponding player's ID
DISCORD_ID_CELL = 'A1'



class SheetManager():
    def __init__(self, creds_path, sheet_url, guild):
        '''Given a sheets URL, and a list of player discord IDs, return a
        dictionary of discord_id --> GoogleBackedSheet object'''
        self.creds_path = creds_path
        self.sheet_url = sheet_url
        self.guild = guild
        self.sheets_cache = {}
    

    async def load(self):
        members = {_.id: _ for _ in self.guild.members}
        
        # Make the pygsheets client. This makes getting values easy
        gc = pygsheets.authorize(service_file=creds_path)
        worksheets = gc.open_by_url(sheet_url).worksheets()

        for sheet in worksheets:
            discord_id = sheet.cell(DISCORD_ID_CELL).value
            if discord_id in members:
                discord_id = int(discord_id)
                self.sheets_cache[discord_id] = GoogleBackedSheet(sheet, members[discord_id])
        print(f"    Loaded {len(self.sheets_cache.keys())} sheets.")


    async def get_sheet(self, user):
        return self.sheets_cache[user.id] if user.id in self.sheets_cache else None


class GoogleBackedSheet():
    def __init__(self, sheet, owner):
        self.sheet = sheet
        self.owner = owner
        self.sync()


    async def sync(self):
        '''Pulls all data from a sheet to local cache'''
        data = self.sheet.get_all_values()

        # do translations
        self.player = self.access(data, CHARACTER_INDEX['player'])
        self.name = self.access(data, CHARACTER_INDEX['name'])
        self.home = self.access(data, CHARACTER_INDEX['home'])
        self.age = self.access(data, CHARACTER_INDEX['age'])
        self.fur = self.access(data, CHARACTER_INDEX['fur'])
        self.rank = self.access(data, CHARACTER_INDEX['rank'])
        self.specialty = self.access(data, CHARACTER_INDEX['specialty'])
        self.cloak = self.access(data, CHARACTER_INDEX['cloak'])
        self.weapon = self.access(data, CHARACTER_INDEX['weapon'])

        for base in BASE_STATS:
            val = {
                'rating': self.access_try_int(data, CHARACTER_INDEX[base]['rating']),
                'success': self.access_try_int(data, CHARACTER_INDEX[base]['success']),
                'fail': self.access_try_int(data, CHARACTER_INDEX[base]['fail'])
            }
            setattr(self, base, val)

        # Initialize bare skills, then populate from sheet
        for skill in SKILL_LIST:
            setattr(self, skill, { 'rating': None, 'success': 0, 'fail': 0 })

        for skill in CHARACTER_INDEX['skills']:
            name = self.access(data, skill['name']).lower()
            # Missing skill in sheet, empty space
            if not name:
                continue
            # Skill with bad name in sheet, big deal
            if name not in SKILL_LIST:
                raise Exception(f'{name} is not a real skill.')
            val = {
                'rating': self.access_try_int(data, skill['rating']),
                'success': self.access_try_int(data, skill['success']),
                'fail': self.access_try_int(data, skill['fail']),
            }
            setattr(self, name, val)


    def get_success(self, key):
        return self._get_skill_subvalue(key, 'success')


    def get_fail(self, key):
        return self._get_skill_subvalue(key, 'fail')


    def get_rating(self, key):
        return self._get_skill_subvalue(key, 'rating')


    def check_valid_skill(self, skill):
        return skill in PROGRESSIONS


    def _get_skill_subvalue(self, key, subvalue):
        return getattr(self, key)[subvalue] if hasattr(self, key) else None


    def _access(self, data, cell):
        col = ord(cell[0]) - ord('A')
        row = int(cell[1:]) - 1
        return data[row][col]


    def _access_try_int(self, data, cell):
        # Convert to an int if possible. If not, return as-is
        val = self.access(data, cell)
        try:
            val = int(val)
        except:
            if val:
                val = val.lower()
        return val


    async def _render_rating(self, user, skill, progress):
        sheet = self.sheets[user.id]
        await sheet.sync()
        rating = sheet.get_rating(skill)

        if not rating:
            return f'{user.display_name}\'s {skill} rating: **Not yet learning!**'
        
        msg = f'{user.display_name}\'s {skill} rating: **{"Learning!" if rating == "x" else rating}**'
        if progress:
            success = sheet.get_success(skill)
            fail = sheet.get_fail(skill)
            if rating == 'x':
                msg += ' -- [progress: ' + '✓' * (fail + success) + ' ' + '◯ ' * (nature - fail - success) + ']'
            else:
                msg += ' -- [*fail*: ' + '✓' * fail + ' ' + '◯ ' * (rating - fail - 1) + \
                        ' | *success*: ' + '✓' * success + ' ' + '◯ ' * (rating - success) + ']'
        return msg


    async def check_rating(self, skill, channel, user, progress=False):
        if not check_valid_skill(skill):
            return await channel.send(f'{skill} is not a valid skill.')
        
        msg = await self._render_rating(user, skill, progress)
        await message.channel.send(msg)

