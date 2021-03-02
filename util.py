import re


class ValueRetainingRegexMatcher:
    '''This is a load of BS to just get around not using PEP 572'''
    def __init__(self, match_str):
        self.match_str = match_str


    def match(self, regex):
        self.retained = re.match(regex, self.match_str)
        return bool(self.retained)


    def search(self, regex):
        self.retained = re.search(regex, self.match_str)
        return bool(self.retained)


    def group(self, i):
        return self.retained.group(i)


def get_sheets_key(s):
    m = ValueRetainingRegexMatcher(s)
    if not s or not m.search(r'\/spreadsheets\/d\/(.+?)(?:\/|$)'):
        return s
        
    return m.group(1)


def dice_result_to_emoji_str(result):
    from micedice import DICE_FACE_EMOJIS
    '''Converts a list of d6 numbers to emojis, then joins by spaces.'''
    return " ".join([DICE_FACE_EMOJIS[_] for _ in result])


def explosion_diff_to_emoji_str(changes, operation):
    from dice import Operation
    emoji_map = {
        True: '💥' if operation == Operation.EXPLODE else '🔻',
        False: '▪️'
    }
    return " ".join([emoji_map[_] for _ in changes])


def render_dice_pool(pool, with_history=False):
    from dice import Operation
    from micedice import AXE_EMOJI

    if not with_history:
        return f'{dice_result_to_emoji_str(pool.current_result())}    ➡️    `{pool.num_successes()}!`'

    msg = ''
    for operation, result, successes, value, changes in pool.get_history():
        if operation == Operation.ROLL:
            msg += f'{dice_result_to_emoji_str(result)}    ➡️    `{successes}!`'
        else:
            breakdown_portion = f'{successes} + {value - successes} {AXE_EMOJI} = ' if value > successes else ''
            msg += f'''
{explosion_diff_to_emoji_str(changes, operation)}
{dice_result_to_emoji_str(result)}    ➡️    `{breakdown_portion}{value}!`'''
    return msg
