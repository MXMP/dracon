def Translit(srcstr):
    try:
        new_str = str(srcstr, 'utf-8')
    except:
        new_str = srcstr
    conversion = {
        '\u0410': 'A', '\u0430': 'a', '\u0411': 'B', '\u0431': 'b', '\u0412': 'V', '\u0432': 'v',
        '\u0413': 'G', '\u0433': 'g', '\u0414': 'D', '\u0434': 'd', '\u0415': 'E', '\u0435': 'e',
        '\u0401': 'Yo', '\u0451': 'yo', '\u0416': 'Zh', '\u0436': 'zh', '\u0417': 'Z', '\u0437': 'z',
        '\u0418': 'I', '\u0438': 'i', '\u0419': 'Y', '\u0439': 'y', '\u041a': 'K', '\u043a': 'k',
        '\u041b': 'L', '\u043b': 'l', '\u041c': 'M', '\u043c': 'm', '\u041d': 'N', '\u043d': 'n',
        '\u041e': 'O', '\u043e': 'o', '\u041f': 'P', '\u043f': 'p', '\u0420': 'R', '\u0440': 'r',
        '\u0421': 'S', '\u0441': 's', '\u0422': 'T', '\u0442': 't', '\u0423': 'U', '\u0443': 'u',
        '\u0424': 'F', '\u0444': 'f', '\u0425': 'H', '\u0445': 'h', '\u0426': 'Ts', '\u0446': 'ts',
        '\u0427': 'Ch', '\u0447': 'ch', '\u0428': 'Sh', '\u0448': 'sh', '\u0429': 'Sch', '\u0449': 'sch',
        '\u042a': '"', '\u044a': '"', '\u042b': 'Y', '\u044b': 'y', '\u042c': '\'', '\u044c': '\'',
        '\u042d': 'E', '\u044d': 'e', '\u042e': 'Yu', '\u044e': 'yu', '\u042f': 'Ya', '\u044f': 'ya',
        '\u2116': '#'
    }
    translitstring = []
    for c in new_str:
        translitstring.append(conversion.setdefault(c, c))
    return ''.join(translitstring).encode("utf-8")


# Пользовательская функция: Получение hex-значения 2-го октета IP-адреса
def fn_2oct(src):
    try:
        return hex(int(src.split('.')[1]))[2:].zfill(2)
    except:
        return ""


# Пользовательская функция: Получение hex-значения 3-го октета IP-адреса
def fn_3oct(src):
    try:
        return hex(int(src.split('.')[2]))[2:].zfill(2)
    except:
        return ""


# Пользовательская функция: Получение hex-значения 3-го октета IP-адреса, увеличенного на единичку
def fn_3op1(src):
    try:
        return hex(int(src.split('.')[2]) + 1)[2:].zfill(2)
    except:
        return ""


# Пользовательская функция: Получение hex-значения номера порта
def fn_xp(n):
    try:
        return hex(int(n))[2:].zfill(2)
    except:
        return ""


# Пользовательская функция: Получение транслитерированного значения поля custom до разделителя '|'
def fn_tr_cst1(src):
    return Translit(src.split('|')[0])


# Пользовательская функция: Получение транслитерированного значения поля custom после разделителя '|'
def fn_tr_cst2(src):
    return Translit(src.split('|')[1])


# Пользовательская функция: Транслитерация переданного значения
def fn_tr(src):
    return Translit(src)


# Пользовательская функция: получение части строки до разделителя '|' (без транслитерации)
def fn_split_before(src):
    return src.split('|')[0]


# Пользовательская функция: получение части строки после разделителя '|' (без транслитерации)
def fn_split_after(src):
    return src.split('|')[1]
