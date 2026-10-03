"""Russian → Latin transliteration shared by segment ids and voice folder names."""

_TR = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo","ж":"zh","з":"z","и":"i","й":"y",
       "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
       "х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya"}

def translit(name: str) -> str:
    out = []
    for ch in name:
        t = _TR.get(ch.lower())
        out.append(ch if t is None else (t.capitalize() if ch.isupper() else t))
    return "".join(out)
