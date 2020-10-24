def clean_sheets_url(url):
    if not url:
        return url
    index = url.find('/edit?')
    if index != -1:
        return url[:index]
    return url


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
        banked_axes = value - successes
        if operation == Operation.ROLL:
            msg += f'{dice_result_to_emoji_str(result)}    ➡️    `{successes}!`'
        else:
            breakdown_portion = f'{successes} + {value - successes} {AXE_EMOJI} = ' if value > successes else ''
            msg += f'''
{explosion_diff_to_emoji_str(changes, operation)}
{dice_result_to_emoji_str(result)}    ➡️    `{breakdown_portion}{value}!`'''
    return msg