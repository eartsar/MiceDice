import os.path
import gspread
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


def check_valid_skill(skill):
    return skill in PROGRESSIONS


def load_sheets(creds_path, sheet_url, player_discord_ids):
    '''Given a sheets URL, and a list of player discord IDs, return a
    dictionary of discord_id --> GoogleBackedSheet object'''
    print("  Loading google sheets for players...")
    player_discord_ids = [str(_) for _ in player_discord_ids]
    # Authenticate to google sheets, get creds
    credentials = ServiceAccountCredentials.from_json_keyfile_name(creds_path, SCOPES)
    # Make the gspread client. This makes getting values easy.
    gc = gspread.authorize(credentials)
    worksheets = gc.open_by_url(sheet_url).worksheets()
    sheets = {}
    for sheet in worksheets:
        discord_id = sheet.acell(DISCORD_ID_CELL).value
        if discord_id in player_discord_ids:
            discord_id = int(discord_id)
            sheets[discord_id] = GoogleBackedSheet(sheet)
            print(f"    Loaded google sheet for {discord_id}.")
    return sheets


def access(data, cell):
    col = ord(cell[0]) - ord('A')
    row = int(cell[1:]) - 1
    return data[row][col]

def access_try_int(data, cell):
    # Convert to an int if possible. If not, return as-is
    val = access(data, cell)
    try:
        val = int(val)
    except:
        if val:
            val = val.lower()
    return val


class GoogleBackedSheet():
    def __init__(self, sheet):
        self.sheet = sheet
        self.sync()


    def sync(self):
        '''Pulls all data from a sheet to local cache'''
        data = self.sheet.get_all_values()

        # do translations
        self.player = access(data, CHARACTER_INDEX['player'])
        self.name = access(data, CHARACTER_INDEX['name'])
        self.home = access(data, CHARACTER_INDEX['home'])
        self.age = access(data, CHARACTER_INDEX['age'])
        self.fur = access(data, CHARACTER_INDEX['fur'])
        self.rank = access(data, CHARACTER_INDEX['rank'])
        self.specialty = access(data, CHARACTER_INDEX['specialty'])
        self.cloak = access(data, CHARACTER_INDEX['cloak'])
        self.weapon = access(data, CHARACTER_INDEX['weapon'])

        for base in BASE_STATS:
            val = {
                'rating': access_try_int(data, CHARACTER_INDEX[base]['rating']),
                'success': access_try_int(data, CHARACTER_INDEX[base]['success']),
                'fail': access_try_int(data, CHARACTER_INDEX[base]['fail'])
            }
            setattr(self, base, val)

        # Initialize bare skills, then populate from sheet
        for skill in SKILL_LIST:
            setattr(self, skill, { 'rating': None, 'success': 0, 'fail': 0 })

        for skill in CHARACTER_INDEX['skills']:
            name = access(data, skill['name']).lower()
            # Missing skill in sheet, empty space
            if not name:
                continue
            # Skill with bad name in sheet, big deal
            if name not in SKILL_LIST:
                raise Exception(f'{name} is not a real skill.')
            val = {
                'rating': access_try_int(data, skill['rating']),
                'success': access_try_int(data, skill['success']),
                'fail': access_try_int(data, skill['fail']),
            }
            setattr(self, name, val)


    def get_success(self, key):
        return self._get_skill_subvalue(key, 'success')

    def get_fail(self, key):
        return self._get_skill_subvalue(key, 'fail')

    def get_rating(self, key):
        return self._get_skill_subvalue(key, 'rating')

    def _get_skill_subvalue(self, key, subvalue):
        return getattr(self, key)[subvalue] if hasattr(self, key) else None

