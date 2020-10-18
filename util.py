def to_emoji_str(result):
    from micedice import EMOJI_MAP
    '''Converts a list of d6 numbers to emojis, then joins by spaces.'''
    return " ".join([EMOJI_MAP[_] for _ in result])