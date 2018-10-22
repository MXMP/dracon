#!/usr/local/bin/python3

import dfunc
import hashlib
import logging
import re
import socket
import sys
import time
from logging.handlers import RotatingFileHandler
from math import ceil

import psycopg2
import pymysql

from daemon import Daemon
from dconfig import dev_types, ports_types, mags_list, cf_path, fw_path, fw_names, commands, helpinfo
from dconfig import devices_query, ports_query
from dconfig import interface_ip, port, cycle_int, sleep_def, sleep_int, log_file, log_size, log_backupcount
from dconfig import mysql_addr, mysql_user, mysql_pass, mysql_base
from dconfig import mysql_addr_w, mysql_user_w, mysql_pass_w, mysql_base_w, mysql_ctbl_w, mysql_ttbl_w
from dconfig import postgresql_addr, postgresql_user, postgresql_pass, postgresql_base, use_postgresql

# Настройка системы логирования сообщений
log_handler = RotatingFileHandler(log_file, maxBytes=log_size, backupCount=log_backupcount)
log_formatter = logging.Formatter('%(asctime)s Dracon [%(process)d]: %(message)s')
log_handler.setFormatter(log_formatter)
logger = logging.getLogger()
logger.addHandler(log_handler)
logger.setLevel(logging.DEBUG)


def md5(src):
    """
    Функция для вычисления MD5 хеш-суммы.

    :param src:
    :return:
    """

    md5hash = hashlib.md5()
    md5hash.update(src.encode('utf-8'))
    return md5hash.hexdigest()


def md5size(src):
    """
    Функция для определения MD5 хеш-суммы и размера блока данных.

    :param src:
    :return:
    """

    # Сортируем и склеиваем блоки данных
    data = ''.join([src[i] for i in sorted(src.keys())])
    # Возвращаем длину и значение MD5 блока данных
    return md5(data), len(data)


def get_dttm():
    """
    Функция для получения даты и времени в двух форматах.

    :return:
    """

    # Получаем дату в формате unix timestamp
    dttm = int(time.time())
    # Возвращаем дату и в unix timestamp и в читабельном формате
    return dttm, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(dttm))


def get_fw_file_name(sw):
    """
    Функция для определения имени файла ПО.

    :param sw:
    :return:
    """

    # Если для данной модели есть запись возвращаем соответствующее имя файла
    if sw in list(fw_names.keys()):
        return fw_names[sw]
    # А если нет, то возвращаем несуществующее имя
    else:
        return 'no_such_file'


def get_sw_info(ip, devices):
    """
    Функция получения информации об устройстве.

    :param ip:
    :param devices:
    :return:
    """

    # Значения модели, адреса и пользовательского поля по умолчанию
    dtype = 'n/a'
    custom = 'n/a'
    # Проверяем, есть ли IP устройства в словаре и есть ли соответствующий ID в словаре типов
    if ip in devices:
        if devices[ip]['dtype'] in dev_types:
            # Получаем имя устройства по его типу
            dtype = dev_types[devices[ip]['dtype']]
        # Получаем адрес и пользовательское поле
        custom = devices[ip]['custom']
    return dtype, custom


def prepare_ports(ports_tmp):
    """
    Функция для подготовки словаря портов.

    :param ports_tmp:
    :return:
    """

    # Создаем словарь для хранения результатов и его ключи
    ports = {}
    for line in ports_tmp:
        ports[line[0]] = {}
    # Перебираем весь список с результатами MySQL-запроса. Результаты добавляем во временный словарь
    for line in ports_tmp:
        try:
            ports[line[0]].update({int(line[1]): {'ptype': line[2], 'comment': line[3]}})
        except:
            ports[line[0]].update({0: {'ptype': 0, 'comment': ''}})
    # Помещаем в словарь портов пустой словарь для коммутатора с неизвестным IP
    ports.update({None: {}})
    # Словарь будет иметь вид {IP:{port:{'ptype':value, 'comment':value},...}}.
    return ports


def get_data_from_db():
    """
    Функция для получения списка устройств из базы MySQL.

    :return:
    """

    # Значения данных по умолчанию
    devices_data = [('0.0.0.0', 0, '')]
    ports_data = [('0.0.0.0', 0, 0, '')]
    # Пробуем подключиться к базе данных PostgreSQL либо MySQL. Используем таймаут в 2 секунды
    try:
        if use_postgresql:
            db_conn = psycopg2.connect(host=postgresql_addr, user=postgresql_user, password=postgresql_pass,
                                       dbname=postgresql_base, connect_timeout=2)
        else:
            db_conn = pymysql.connect(host=mysql_addr, user=mysql_user, passwd=mysql_pass, db=mysql_base,
                                      connect_timeout=2, use_unicode=True, charset='utf8')
    # Если возникла ошибка при подключении, сообщаем об этом в лог и возвращаем 'пустые' данные
    except psycopg2.Error as p_err:
        logger.info("ERROR: PostgreSQL Error (%s): %s", postgresql_addr, p_err.args)
        return devices_data, ports_data
    except pymysql.Error as m_err:
        logger.info("ERROR: MySQL Error (%s): %s", mysql_addr, m_err.args[1])
        return devices_data, ports_data
    # Если ошибок не было, сообщаем в лог об успешном подключении и создаем 'курсор'
    else:
        if use_postgresql:
            logger.info("INFO: Connection to PostgreSQL Server '%s' established", postgresql_addr)
        else:
            logger.info("INFO: Connection to MySQL Server '%s' established", mysql_addr)
        db_cr = db_conn.cursor()
        # Пробуем выполнить запрос к базе и получить все данные из 'курсора' (списоки устройств и портов)
        try:
            db_cr.execute(devices_query)
            devices_data = db_cr.fetchall()
            db_cr.execute(ports_query)
            ports_data = db_cr.fetchall()
        # Если возникла ошибка при выполнении запроса, сообщаем об этом в лог и возвращаем 'пустые' данные
        except psycopg2.Error as p_err:
            logger.info("ERROR: PostgreSQL Query failed: %s", p_err.args)
            return devices_data, ports_data
        except pymysql.Error as m_err:
            logger.info("ERROR: MySQL Query failed: %s", m_err.args[1])
            return devices_data, ports_data
        # Если ошибок не возникло, сообщаем в лог об успешном подключении
        else:
            if use_postgresql:
                logger.info("INFO: PostgreSQL Query OK. %s rows found for devices and %s for ports", len(devices_data),
                            len(ports_data))
            else:
                logger.info("INFO: MySQL Query OK. %s rows found for devices and %s for ports", len(devices_data),
                            len(ports_data))
        # Закрываем подключение
        finally:
            db_conn.close()
    # Возвращаем списки портов и устройств
    return devices_data, ports_data


def put_config_to_my_sql(direction, cfg, target, name, switch, ip, m5d, cfg_type):
    """
    Функция размещения полученной конфигурации в базе MySQL.

    :param direction:
    :param cfg:
    :param target:
    :param name:
    :param switch:
    :param ip:
    :param m5d:
    :param cfg_type:
    :return:
    """

    # Сортируем и склеиваем блоки данных
    cfg = ''.join([cfg[i] for i in sorted(cfg.keys())])
    # Формируем данные для размещения их в базе
    mysql_query = "INSERT INTO {0}.{1} ({1}.timestamp, {1}.ip, {1}.target, {1}.direction," \
                  " {1}.switch, {1}.name, {1}.hash) VALUES ".format(mysql_base_w, mysql_ttbl_w)
    mysql_query += "('{0}', INET_ATON('{1}'), INET_ATON('{2}'), '{3}', '{4}', '{5}', '{6}');".format(get_dttm()[0], ip,
                                                                                                     target, direction,
                                                                                                     switch, name, m5d)
    # Пробуем подключиться к базе данных MySQL. Используем таймаут в 2 секунды
    try:
        db_conn = pymysql.connect(host=mysql_addr_w, user=mysql_user_w, passwd=mysql_pass_w, db=mysql_base_w,
                                  connect_timeout=2, use_unicode=True, charset='utf8', autocommit=True)
    # Если возникла ошибка при подключении, сообщаем об этом в лог
    except pymysql.Error as err:
        logger.info("ERROR: MySQL Error (%s): %s", mysql_addr_w, err.args[1])
    # Если ошибок не было, создаем 'курсор'
    else:
        mysql_cr = db_conn.cursor()
        # Пробуем записать в базу информацию об операции
        try:
            mysql_cr.execute(mysql_query)
        # При ошибке выполнения запроса сообщаем в лог о проблеме
        except pymysql.Error as err:
            logger.info("ERROR: MySQL Query Error: %s", err.args[1])
        else:
            # Помещать в базу данных следует только саму конфигурацию, потому что бэкапы там уже есть,
            # а ПО не должно быть вообще
            if cfg_type == 'config':
                # Пробуем выполнить запрос к базе и подсчитать кол-во уникальных записей для hash
                try:
                    mysql_cr.execute(
                        "SELECT COUNT(*) FROM {0}.{1} WHERE {1}.hash='{2}'".format(mysql_base_w, mysql_ctbl_w, m5d))
                # При ошибке выполнения запроса сообщаем в лог о проблеме
                except pymysql.Error as err:
                    logger.info("ERROR: MySQL Query Error: %s", err.args[1])
                else:
                    hash_count = mysql_cr.fetchall()[0][0]
                    # Определяем, является ли данный hash уникальным
                    unique_hash = (hash_count == 0)
                    # Если hash уникален (еще не встречался), записываем конфиг в базу
                    if unique_hash:
                        try:
                            mysql_cr.execute(
                                "INSERT INTO {0}.{1} ({1}.hash, {1}.config) VALUES ('{2}', '{3}');".format(mysql_base_w,
                                                                                                           mysql_ctbl_w,
                                                                                                           m5d, cfg))
                        # При ошибке выполнения запроса сообщаем в лог о проблеме
                        except pymysql.Error as err:
                            logger.info("ERROR: MySQL Query Error: %s", err.args[1])
                        # Либо сообщаем об успешной операции записи
                        else:
                            logger.info("INFO: Succesfully sent %s bytes to MySQL for '%s' ('%s'). Request from %s",
                                        len(cfg), target, switch, ip)
        finally:
            db_conn.close()


def get_last_config_from_my_sql(target):
    """
    Функция получения последней конфигурации из базы MySQL.

    :param target:
    :return:
    """

    # По умолчанию конфиг пустой
    last_conf = ''
    try:
        # Пробуем подключиться к базе данных MySQL. Используем таймаут в 2 секунды
        db_conn = pymysql.connect(host=mysql_addr_w, user=mysql_user_w, passwd=mysql_pass_w, db=mysql_base_w,
                                  connect_timeout=2, use_unicode=True, charset='utf8')
        db_conn.autocommit(True)
    except pymysql.Error as err:
        # Если возникла ошибка при подключении, сообщаем об этом в лог
        logger.info("ERROR: MySQL Error (%s): %s", mysql_addr_w, err.args[1])
    else:
        # Если ошибок не было, создаем 'курсор'
        mysql_cr = db_conn.cursor()
        try:
            mysql_cr.execute(
                "SELECT config FROM {0}.{1} JOIN {0}.{2} ON {1}.hash={2}.hash WHERE {1}.target=INET_ATON('{3}') AND"
                " {1}.direction='up' ORDER BY {1}.timestamp DESC LIMIT 1;".format(mysql_base_w, mysql_ttbl_w,
                                                                                  mysql_ctbl_w, target))
        except pymysql.Error as err:
            # При ошибке сообщаем в лог
            logger.info("ERROR: MySQL Query Error: %s", err.args[1])
        else:
            data = mysql_cr.fetchall()
            if len(data):
                last_conf = data[0][0]
        finally:
            db_conn.close()
    return last_conf


def tftp_prepdata(tftpdata, ip):
    """
    Функция для определения типа передачи, режима передачи, имени файла, номера блока, IP-адреса цели, типа данных и
    самих данных.

    Структура пакета при запросе:
        тип_пакета(2 байта)
        имя_файла(ASCII-строка)
        конец_строки(#00)
        режим_передачи(ASCII-строка)
        конец_строки(#00)
    Пример: 0x0001 + hexstr('config.cfg') + 0x00 + hexstr('octet') + 0x00

    Структура пакета при подтверждении блока:
        тип_пакета(2 байта)
        номер_блока(2 байта)
    Пример: 0x0004 + 0x0001

    :param tftpdata:
    :param ip: ip-адрес хоста, с которого пришел запрос
    :return:
    """

    # Перечисляем в словаре возможные значения типов пакета
    # При этом обрабатывать будем только RRQ (чтение) и ACK (подтверждение приема)
    actions = {1: 'RRQ', 2: 'WRQ', 3: 'DATA', 4: 'ACK', 5: 'ERR', 6: 'ERR2'}

    # Символ конца строки
    end_string_char = chr(0).encode('utf-8')

    # Определяем значения переменных
    tftp_type = 'UNK'
    transfer = 'unknown'
    tftp_filename = 'unknown'
    tftp_block = -1
    target_ip = ip
    data_type = 'config'
    data_upl = ''

    # Работаем только с блоками размером более 4 байт
    if len(tftpdata) >= 4:
        # Если полученный тип пакета присутствует в списке, получаем из списка соответствующее значение
        if tftpdata[1] in actions:
            tftp_type = actions[tftpdata[1]]
        # Если тип запроса RRQ (чтение) или запись (WRQ) и указатель на конец строки присутствует и
        # находится не в начале данных:
        if ((tftp_type == 'RRQ') | (tftp_type == 'WRQ')) & (tftpdata[2:].find(end_string_char) != -1):
            # Пропускаем 2 знака, остаток разбиваем по символу конца строки и получаем имя файла ('левая' часть от
            # деления)
            name_tmp = (tftpdata[2:].split(end_string_char)[0]).decode('utf-8')
            # Пропускаем 2 знака, остаток разбиваем по символу конца строки и получаем режим передачи ('правая' часть
            # деления)
            transfer = (tftpdata[2:].split(end_string_char)[1]).decode('utf-8')
            # Если в запрошенном файле присутствует символ '@', разбиваем имя на две части
            if '@' in name_tmp:
                name_tmp = name_tmp.split('@')
                # IP-адресом считаем левую часть, а именем файла - правую часть
                if len(name_tmp[0]) > 0:
                    target_ip = name_tmp[0]
                if len(name_tmp[1]) > 0:
                    tftp_filename = name_tmp[1]
            else:
                # Если '@' не присутствует, то имя файла не преобразовываем
                tftp_filename = name_tmp

        # Если тип запроса ACK или DATA и в данных есть еще хотя бы два байта,
        # получаем номер блока из 3 и 4 символа (2 и 3 позиции)
        if ((tftp_type == 'ACK') | (tftp_type == 'DATA')) & (len(tftpdata) >= 3):
            tftp_block = tftpdata[2] * 256 + tftpdata[3]

        # Если тип запроса RRQ или WRQ, номер блока будет нулевым, что означает начало данных
        if (tftp_type == 'RRQ') | (tftp_type == 'WRQ'):
            tftp_block = 0

        # Если в типе передачи есть указатель на конец строки, получаем из данных тип передачи,
        # убирая символы с кодом '0'
        if transfer.find(chr(0)) != -1:
            transfer = transfer.replace(chr(0), '')

        # Если запрошенное имя равно 'firmware', считаем, что у нас запросили ПО и указываем это в типе данных
        if tftp_filename == 'firmware':
            data_type = 'firmware'

        # Если запрошенное имя равно 'backup', считаем, что у нас запросили последнюю конфигурацию для конкретного IP,
        # и указываем это в типе данных
        if tftp_filename == 'backup':
            data_type = 'backup'

        # Если тип запроса DATA и в данных есть еще хотя бы два байта, получаем данные
        # (обрезать ethernet-трейлер не надо, этим занимаются другие уровни)
        if (tftp_type == 'DATA') & (len(tftpdata) >= 3):
            data_upl = tftpdata[4:]

    return tftp_type, transfer, tftp_filename, tftp_block, target_ip, data_type, data_upl


def p_stat(ports):
    """
    Функция, возвращающая список с типами портов и их диапазоном.

    :param ports:
    :return:
    """

    def get_range(ports_gr):
        """
        Функция получения диапазона портов.

        :param ports_gr:
        :return:
        """
        # Получаем список ключей из словаря. При этом удаляем дубликаты (list(set())) и сортируем список
        _range = sorted(list(set(ports_gr.keys())))
        # Получаем два временных списка с ключами. Ключи - это номера портов. Первй список будет преобразован
        # в диапазон, а второй возвращен без преобразования
        p_range = list(_range)
        full_p_range = list(_range)
        # Перебираем основной список, получая индекс элемента (i) и сам элемент (a)
        for i, a in enumerate(_range):
            # Обрабатываем все элементы кроме минимального и максимального
            # Если слева и справа от текущего номера идут последовательно,
            # заменяем текущий элемент (который означает номер порта) на '*'
            if (a > min(_range)) & (a < max(_range)):
                if (a == _range[i - 1] + 1) & (a == _range[i + 1] - 1):
                    p_range[i] = '*'
        # Из списка получаем строку, где элементы разделены запятыми, а '*' и ',-' заменены на '-'
        p_range = ','.join(str(n) for n in p_range).replace('*,', '-').replace(',-', '-')
        # Удаляем двойные символы '-', заменяя их на одинарные
        while p_range.find('--') != -1:
            p_range = p_range.replace('--', '-')
        return {'range': p_range, 'list': full_p_range}

    # 1 - абонентский порт, 2 - магистральный, 3 - сломанный, 4 - VIP-клиент, 5 - вход
    # 6 - нестандартный, 7 - оборудование, 8 - вход (патчкорд), 9 - магистраль (патчкорд)
    # Создаем результирующий словарь
    res_dict = {}
    # Проходим по всему списку типов (перебираем ключи)
    for pt in list(ports_types.keys()):
        # Получаем временный словарь из переданного функции
        ports_tmp = dict(ports)
        # Перебираем основной словарь. 'p' - номер порта. Задача: оставить порты только нужного типа
        for p in ports:
            # Если тип порта для основного словаря не равен определенному типу, удаляем соответствующий элемент
            # во временном словаре
            if ports[p]['ptype'] != pt:
                del ports_tmp[p]
        res_dict[ports_types[pt]] = get_range(ports_tmp)
    ports_tmp = dict(ports)
    # Получаем диапазон и список вообще всех портов
    res_dict['all'] = get_range(ports_tmp)
    # Во временном списке оставляем порты с типом 2, 5, 8 и 9
    for p in ports:
        if int(ports[p]['ptype']) not in mags_list:
            del ports_tmp[p]
    # Получаем диапазон и список магистральных портов
    res_dict['mags'] = get_range(ports_tmp)
    return res_dict


def get_data(ip, target, fname, sw, custom, ports, transfer, data_type):
    """
    Функция подготовки данных.

    :param ip:
    :param target:
    :param fname:
    :param sw:
    :param custom:
    :param ports:
    :param transfer:
    :param data_type:
    :return:
    """

    # Определяем размер блока данных и объявляем переменную для хранения данных
    # TODO: вынести в конфиг размер блока (или в константы)
    block_size = 512
    data = ''
    # Работаем, если запрошено ПО и имя файла указано
    if (data_type == 'firmware') & (get_fw_file_name(sw) != 'no_such_file'):
        # Если тип передачи 'octet' (без изменений)...
        if transfer == 'octet':
            try:
                # ... пытаемся открыть файл
                fw_file = open(fw_path + get_fw_file_name(sw), 'r')
            except:
                # Если не удалось - помещаем сообщение об ошибке в данные и пишем об этом в лог
                data = "# ERROR: Can't open file %s%s" % (fw_path, get_fw_file_name(sw))
                logger.info("ERROR: Can't open file '%s%s'!", fw_path, get_fw_file_name(sw))
            else:
                # Если все хорошо - читаем файл
                data = fw_file.read()
                fw_file.close()
        else:
            # Если тип передачи отличен от 'octet', помещаем в данные сообщение об необходимости изменить тип
            data = "# Please, set transfer type to 'octet' (-i)!"

    # Получаем данные, если запрошен backup последней конфигурации
    if data_type == 'backup':
        data = get_last_config_from_my_sql(target)

    # Работаем, если запрошена конфигурация и устройство определено
    if (data_type == 'config') & (target is not None):
        # Если имя файла (которое является и командой) присутствует в наборе списков команд:
        if fname in list(commands.keys()):
            try:
                cf_file = open(cf_path + sw, 'rt')
                cf_data = cf_file.read().split(':::')
                cf_file.close()
                cf_data = dict(cf_data[i:i + 2] for i in range(1, len(cf_data), 2))
            except:
                cf_data = ''
                logger.info("ERROR: Can't open file '%s%s' or this file is incorrect!", cf_path, sw)

            # Получаем диапазоны и списки портов в зависимости от их статуса
            p_stats = p_stat(ports)
            # Шаблон для поиска конструкций вида [ss#1]
            reg_x = re.compile(r"(\[(?P<k>[a-zA-Z]+)\#(?P<v>\d+)\])")
            # Шаблон для поиска конструкций вида [ss]
            reg_nx = re.compile(r"(\[(?P<val>\S+)\])", re.IGNORECASE | re.DOTALL)
            # Шаблон для поиска конструкций вида {function_name#param}
            reg_fn = re.compile(r"(\{([a-zA-Z_0-9]+)\#([^\t\n\r\f\v\{\}]*)\})")

            # Перебираем все команды внутри списка для данной команды
            for cmd in commands[fname]:
                if cmd in cf_data:
                    # Находим для команды (имени файла) соответствующий блок, разбираем его на строки
                    # и перебираем их все
                    for cf_line in cf_data[cmd].split("\n"):
                        # Получаем копию текущей строки, которую модернизируем при наличии в ней шаблонов
                        new_cf_line = cf_line

                        # Заменяем зарезервированные слова на значения соответствующих переменных
                        new_cf_line = new_cf_line.replace('{$target}', target)
                        new_cf_line = new_cf_line.replace('{$datetime}', get_dttm()[1])

                        # Здесь выражение вида "config ports [ss#1] state enable" разбирается
                        # на список кортежей вида [('[ss#1]', 'ss', '1')]
                        # Индекс [0] указывает на исходное значение в строке, [1] - на имя списка и
                        # [2] - на _значение_ (не индекс!) внутри списка
                        # Если замена или вызов функции были неудачными, то строка
                        # "комментируется" - добавляется символ '#'
                        for p_list in reg_x.findall(new_cf_line):
                            p_check = p_list[0]
                            try:
                                # Если искомое значение присутствует внутри найденного списка, запоминаем это значение
                                if int(p_list[2]) in p_stats[p_list[1]]['list']:
                                    p_check = p_list[2]
                            except:
                                new_cf_line = "#" + new_cf_line
                            # Заменяем шаблон на диапазон портов (если он был распознан) или
                            # на сам шаблон (то есть ничего не поменяется)
                            new_cf_line = new_cf_line.replace(p_list[0], p_check)

                        # Разбираем выражение вида "config ports [ss] state enable"
                        # на список кортежей [('[ss]','ss'),..]. В большинстве случаев в списке будет один элемент.
                        for p_range in reg_nx.findall(new_cf_line):
                            p_check = p_range[0]
                            try:
                                # Если у диапазона ненулевая длина, запоминаем его значение, иначе "комментируем строку"
                                if len(p_stats[p_range[1]]['range']) > 0:
                                    p_check = p_stats[p_range[1]]['range']
                                else:
                                    new_cf_line = "#" + new_cf_line
                            except:
                                new_cf_line = "#" + new_cf_line
                            # Заменяем шаблон на диапазон портов (если он был распознан) или на
                            # сам шаблон (то есть ничего не поменяется)
                            new_cf_line = new_cf_line.replace(p_range[0], p_check)

                        # Разбираем строку для поиска пользовательских функций по шаблону {fn#1}.
                        # Сначала выполняем проверку на 'comment'
                        for fn_list in reg_fn.findall(new_cf_line):
                            if fn_list[1][0:8] == 'comment':
                                try:
                                    new_cf_line = new_cf_line.replace(fn_list[0], ports[int(fn_list[2])]['comment'])
                                except:
                                    new_cf_line = "#" + new_cf_line

                        # Аналогично проверяем все остальные шаблоны {fn#1}, уже для поиска функций
                        for fn_list in reg_fn.findall(new_cf_line):
                            # Проверяем, начинается ли пользовательская функция на 'fn_'
                            if fn_list[1][0:3] == 'fn_':
                                # Определяем параметр пользовательской функции. Если используются зарезервированные
                                # слова, работаем с ними, иначе получаем параметр из запроса.
                                fn_param = fn_list[2]
                                if fn_list[2] == 'custom':
                                    fn_param = custom
                                try:
                                    # Пробуем применить пользовательскую функцию. Имя функции получаем из шаблона.
                                    # Сами функции хранятся в модуле dfunc.
                                    new_cf_line = new_cf_line.replace(fn_list[0], getattr(dfunc, fn_list[1])(fn_param))
                                except:
                                    new_cf_line = "#" + new_cf_line

                        data += new_cf_line + "\n"

    # Получаем контрольную сумму для данных
    m5d = md5(data)

    # Если цель не определена и запрошена "Справка", возвращаем краткую справку
    if (target is None) & (fname == 'help'):
        data = helpinfo

    # Получаем количество блоков
    data_items = ceil(len(data) / block_size)

    # Разбиваем данные на блоки, нумеруя их
    data_list = {i + 1: data[x: x + block_size] for i, x in enumerate(range(0, len(data), block_size))}
    # Если ожидаем больше, чем получили, добавляем пустой элемент
    if data_items > len(data_list):
        data_list[len(data_list) + 1] = ''
    # Вставляем первый элемент, где указываем общее количество блоков
    data_list[0] = data_items

    # Примечание №1: Последним блоком данных при передаче считается блок меньше 512 символов.
    # Если же общая длина блоков кратна 512 символам, то последний блок никак не отличается от других
    # Для этого и добавляется блок, имеющий нулевую длину
    # Примечание №2: Минимальный ethernet-фрейма равен 60 байтам. Но здесь беспокоиться об этом не нужно.
    # При длине блока меньше 14 Python или сама ОС при передаче UDP-датаграмы заполнит недостающие байты нулями
    return data_list, m5d


def main():
    logger.info("INFO: Daemon 'Dracon' started...")
    # Получаем начальные значение таймера перезапуска и таймера опроса сокета, равные текущему времени в unix timestamp
    timer = int(time.time())
    sltimer = int(time.time())
    # Устанавливаем паузу при опросе UDP-сокета по умолчанию
    sleeptime = sleep_def
    # Объявляем начальные значение для счетчиков запросов 'read' и 'write'
    tftp_rcnt = 0
    tftp_wcnt = 0

    # Получаем информацию о коммутаторах и их портах из базы данных
    devices_tmp, ports_tmp = get_data_from_db()
    # Получаем список портов
    ports = prepare_ports(ports_tmp)
    # Формируем словарь вида { ip : { type:val, custom:val } }
    try:
        devices = {item[0]: {'dtype': item[1], 'custom': item[2]} for item in list(devices_tmp)}
    except:
        devices = {'0.0.0.0': {'dtype': 0, 'custom': ''} for item in list(devices_tmp)}

    # Объявляем словарь для хранения данных и других параметров
    cfg_fw = {}

    # Объявляем словарь для хранения полученных данных с устройства. Сюда попадет конфигурация, которую
    # отправит коммутатор
    cfg_up = {}

    # Создаем сокет для tftp
    tftp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Пробуем открыть сокет и обрабатываем возможную ошибку
    try:
        tftp.bind((interface_ip, port))
    # При возникновении ошибки делаем запись в логе и завершаем работу
    except socket.error as err:
        logger.info("CRITICAL: Socket Error: %s Exiting...", err.args[1])
        sys.exit(2)
    # При отсутствии ошибки переводим сокет в режим non blocking
    else:
        tftp.setblocking(False)

    # Дальше работаем в бесконечном цикле
    while True:
        # Проверяем, прошло ли достаточно времени с момента предыдущего запроса
        if int(time.time()) - timer >= cycle_int:
            # Пишем в лог о количестве запросов за прошедшее время
            logger.info(f"INFO: Requests for {cycle_int} seconds:" +
                        f" RRQ (download) - {tftp_rcnt}, WRQ (upload) - {tftp_wcnt}")
            # Обнуляем счетчики и получаем новое значение таймера
            tftp_rcnt = 0
            tftp_wcnt = 0
            timer = int(time.time())

            # ВНИМАНИЕ! Это обход БАГА MySQL. В очень редких случаях MySQL может вернуть пустой список данных.
            # Возможно, это давно исправлено, но обход бага остался. :)
            # Получаем информацию о коммутаторах и их портах из базы данных
            devices_tmp, ports_tmp = get_data_from_db()
            # Если длина запроса составляет не менее 90% от длины предыдущего, то помещаем новый
            # список портов в основной список
            # Хоть мы и сравниваем словари разной структуры, но такое сравнение корректно, т.к. количество ключей
            # в 'ports' и строк в 'ports_tmp' одинаково
            if len(ports_tmp) > len(ports) * 0.9:
                ports = prepare_ports(ports_tmp)

            # Если длина запроса составляет не менее 90% от длины предыдущего, то помещаем новый список
            # устройств в основной список
            if len(devices_tmp) > len(devices) * 0.9:
                try:
                    devices = {item[0]: {'dtype': item[1], 'custom': item[2]} for item in list(devices_tmp)}
                except:
                    devices = {'0.0.0.0': {'dtype': 0, 'custom': ''} for item in list(devices_tmp)}

        # Пробуем получить данные с сокета (2 байта для типа передачи, 2 байта для номера блока и еще 512 для данных)
        try:
            tftpdata, tftpaddr = tftp.recvfrom(516)
        # Если данных нет возникнет ошибка
        except:
            # Проверяем, достаточно ли долго не обновлялась переменная (не поступали данные) и устанавливаем паузу
            # при опросе UDP-сокета по умолчанию
            if int(time.time()) - sltimer >= sleep_int:
                sleeptime = sleep_def
        # Если ошибки не возникло, значит данные получены. Приступаем к их обработке
        else:
            # IP-адрес удаленного хоста
            rem_ip = tftpaddr[0]
            # Порт удаленного хоста
            rem_port = tftpaddr[1]
            # Определяем тип передачи, режим передачи, имя файла, номер блока, IP коммутатора, для которого
            # запрошены данные, тип данных и сами данные (они есть при DATA-пакетах)
            tftp_type, transfer, tftp_filename, tftp_block, target_ip, data_type, data_upl = tftp_prepdata(tftpdata,
                                                                                                           tftpaddr[0])
            # Для общего случая определяем:
            # назначение - 'IP_отправителя:Port'
            dip = f"{rem_ip}:{rem_port}"
            # цель - 'IP_устройства (модель_устройства)'
            dev = "'%s' (%s)" % (target_ip, get_sw_info(target_ip, devices)[0])
            # В остальных случаях цель и модель попадают в словарь, с которым и ведется работа в дальнейшем.
            # То есть dev может переопределяться ниже

            if tftp_type in ['RRQ', 'WRQ', 'ACK', 'DATA']:
                # Если получен известный тип данных, уменьшаем паузу при опросе UDP-совера и получаем
                # новое значение таймера
                sleeptime = sleep_def / 1000
                sltimer = int(time.time())

            # Если пришел запрос на чтение, увеличиваем значение счетчика полученных запросов (R) и пишем в лог
            # о полученном запросе
            if tftp_type == 'RRQ':
                tftp_rcnt += 1
                logger.info(f"INFO: -->Request (RRQ) from {dip} for device {dev}. Requested file: '{tftp_filename}'")
                # Пример:
                # INFO: -->Request (RRQ) from 10.137.130.56:52843 for device '10.99.0.2' (DES-3200-28).
                # Requested file: 'cfg'

                # Можно запросить данные для произвольного устройства, но отдать - только для имеющегося.
                # Потому на выходе может быть только реальный IP
                # Если коммутатора с IP назначения нет в списке и запрошена конфигурация, вместо IP используем 'None'
                if (target_ip not in ports) & (data_type == 'config'):
                    target_ip = None
                # Если запрошено ПО, то данные о портах не нужны, но нужна модель устройства, поэтому не обнуляем IP

                # Получаем имя (модель), сеть и адрес удаленного устройства
                rem_dev, rem_cust = get_sw_info(target_ip, devices)
                # Если запрошена конфигурация, получаем данные в виде блоков и их MD5-сумму (от целой части без блоков)
                if data_type == 'config':
                    cfg_tmp, md5_tmp = get_data(rem_ip, target_ip, tftp_filename, rem_dev, rem_cust, ports[target_ip],
                                                transfer, data_type)
                # Если запрошено ПО или backup конфигурации, то проделываем то же самое,
                # но вместо портов передаем пустой список
                if (data_type == 'firmware') or (data_type == 'backup'):
                    cfg_tmp, md5_tmp = get_data(rem_ip, target_ip, tftp_filename, rem_dev, rem_cust, [], transfer,
                                                data_type)

                # Если для удаленного хоста данные уже определены, обновляем их. В противном случае - добавляем
                if rem_ip in list(cfg_fw.keys()):
                    cfg_fw[rem_ip].update({rem_port: {'data': cfg_tmp, 'type': data_type, 'md5': md5_tmp,
                                                      'file': tftp_filename, 'target': target_ip, 'switch': rem_dev}})
                else:
                    cfg_fw[rem_ip] = {
                        rem_port: {'data': cfg_tmp, 'type': data_type, 'md5': md5_tmp, 'file': tftp_filename,
                                   'target': target_ip, 'switch': rem_dev}}
            # На выходе получается словарь словарей вида
            # {
            #   IP :
            #       {
            #           Remote_Port :
            #               { 'data' : $val, 'md5' : $val, 'file' : $val, 'target' : $val, 'switch' : $val }
            #       }
            # }
            # Это нужно как для удобства получения информации, так и для одновременной передачи.
            # Для каждой сессии передачи в словаре хранится своя информация

            # Если пришло подтверждение передачи, проверяем, существуют ли данные для текущего соединения
            if (tftp_type == 'ACK') & (tftp_block in range(0, 65536)):
                try:
                    cfg_fw[rem_ip][rem_port]['data'][tftp_block]
                # Обрабатываем ситуацию, когда данных нет. Такая ситуация может быть, если пакет с RRQ
                # не попал на сервер:
                except:
                    logger.info(
                        "WARNING: Retrieved data (ACK) without request (RRQ) for %s for device %s for block %s!", dip,
                        dev, tftp_block)

            # Проверяем, существует ли данные для данного соединения. Если да - получаем количество блоков
            try:
                cfg_fw[rem_ip][rem_port]['data'][0]
            except:
                total_blocks = - 1
            else:
                total_blocks = cfg_fw[rem_ip][rem_port]['data'][0]

            # Если блок меньше общего количество блоков и ожидается передача, тогда начинаем передачу.
            # Если данных еще не существует, то условие не выполнится ( -1 < -1)
            if (tftp_block < total_blocks) & ((tftp_type == 'RRQ') | (tftp_type == 'ACK')):
                # Пробуем отправить данные
                try:
                    send_data = chr(0) + chr(3) + (lambda x: chr(x // 256) + chr(x % 256))(tftp_block + 1) + str(
                        cfg_fw[rem_ip][rem_port]['data'][tftp_block + 1])
                    tftp.sendto(send_data.encode('utf-8'), (rem_ip, rem_port))
                # Обрабатываем возможную ошибку сокета, делаем запись в логе и завершаем работу
                except socket.error as err:
                    logger.info("CRITICAL: Socket Error (DATA): %s. Exiting...", err.args[1])
                    sys.exit(2)
                else:
                    # Если тип 'RRQ', т.е. передача только начинается
                    if tftp_type == 'RRQ':
                        # IP-адрес и модель устройства
                        dev = "'%s' (%s)" % (cfg_fw[rem_ip][rem_port]['target'], cfg_fw[rem_ip][rem_port]['switch'])
                        # Имя передаваемого файла
                        fil = "'%s'" % (cfg_fw[rem_ip][rem_port]['file'])
                        # Если запрошено ПО определяем новое название файла
                        if cfg_fw[rem_ip][rem_port]['type'] == 'firmware':
                            fil = "'%s'" % (get_fw_file_name(cfg_fw[rem_ip][rem_port]['switch']))
                        # Контрольная хеш-сумма
                        m5d = cfg_fw[rem_ip][rem_port]['md5']
                        # Пишем в лог о старте передачи
                        logger.info("INFO: <--Sending data  to   %s for device %s. Prepared    file: %s, md5: %s", dip,
                                    dev, fil, m5d)
                    # Пример:
                    # INFO: <--Sending data  to   10.137.130.56:52843 for device '10.99.0.2' (DES-3200-28).
                    # Prepared    file: 'cfg', md5: c6c253ff4110f77b917901bb89d762df

                    # Обрабатываем ситуацию, когда мы получили подтверждение от предпоследнего блока и
                    # только что отправили последний
                    if tftp_block == total_blocks - 1:
                        # IP-адрес и модель устройства
                        dev = "'%s' (%s)" % (cfg_fw[rem_ip][rem_port]['target'], cfg_fw[rem_ip][rem_port]['switch'])
                        # Имя передаваемого файла
                        fil = "'%s'" % (cfg_fw[rem_ip][rem_port]['file'])
                        # Если запрошено ПО определяем новое название файла
                        if cfg_fw[rem_ip][rem_port]['type'] == 'firmware':
                            fil = "'%s'" % (get_fw_file_name(cfg_fw[rem_ip][rem_port]['switch']))
                        # Общее количество блоков
                        blk = str(tftp_block + 1)
                        # Получаем копию данных
                        tmp_dct = cfg_fw[rem_ip][rem_port]['data'].copy()
                        # Удаляем первый (нулевой) элемент с длиной словаря
                        tmp_dct.pop(0)
                        # Получаем MD5-сумму и размер полученных данных
                        m5d, fln = md5size(tmp_dct)
                        # Очищаем временный словарь
                        tmp_dct.clear()
                        # Пишем в лог об окончании передачи
                        logger.info(
                            "INFO: Successfully sent to  %s for device %s. Transferred file: %s. Size: %s, blocks: %s",
                            dip, dev, fil, fln, blk)
                    # Пример:
                    # INFO: Successfully sent to  10.137.130.56:52843 for device '10.99.0.2' (DES-3200-28).
                    # Transferred file: 'cfg', blocks: 1

            # Если получено подтверждение передачи последнего блока:
            if (tftp_block == total_blocks) & (tftp_type == 'ACK'):
                # Получаем копию данных
                tmp_dct = cfg_fw[rem_ip][rem_port]['data'].copy()
                # Удаляем первый (нулевой) элемент с длиной словаря
                tmp_dct.pop(0)
                # Цель
                tmp_tgt = cfg_fw[rem_ip][rem_port]['target']
                # Запрошенный файл
                tmp_fil = cfg_fw[rem_ip][rem_port]['file']
                # Модель коммутатора
                tmp_sw = cfg_fw[rem_ip][rem_port]['switch']
                # Контрольная сумма
                tmp_m5d = cfg_fw[rem_ip][rem_port]['md5']

                # Помещаем полученные данные в базу MySQL.
                # Параметры: таблица, данные, IP цели, имя файла, коммутатор, IP, хеш, тип передачи
                put_config_to_my_sql('down', tmp_dct, tmp_tgt, tmp_fil, tmp_sw, rem_ip, tmp_m5d,
                                     cfg_fw[rem_ip][rem_port]['type'])

                # Очищаем временный словарь
                tmp_dct.clear()
                # Удаляем данные из словаря, т.к. передача закончена и они больше не нужны
                del cfg_fw[rem_ip][rem_port]

            if tftp_type == 'WRQ':
                # Увеличиваем значение счетчика полученных запросов (W)
                tftp_wcnt += 1
                # Пишем в лог о полученном запросе
                logger.info("INFO: -->Offer (WRQ) from %s for device %s. Offered file: %s", dip, dev, tftp_filename)
                # Пример:
                # INFO: -->Offer (WRQ) from 10.137.130.56:57904 for device '10.99.0.2' (DES-3200-28).
                # Offered file: 'cfg'

                # Получаем имя (модель) удаленного устройства
                rem_dev = get_sw_info(target_ip, devices)[0]
                # Если для удаленного хоста данные уже определены, затираем их
                if rem_ip in list(cfg_up.keys()):
                    cfg_up[rem_ip].update(
                        {rem_port: {'cfg': {}, 'file': tftp_filename, 'target': target_ip, 'switch': rem_dev}})
                # Если же нет - добавляем
                else:
                    cfg_up[rem_ip] = {
                        rem_port: {'cfg': {}, 'file': tftp_filename, 'target': target_ip, 'switch': rem_dev}}
            # На выходе получается словарь вида [IP][Port]['cfg'|'file'|'target'|'switch']
            # Это нужно для удобства получения информации, но главное - для одновременной передачи
            # Для каждой сессии передачи в словаре хранится своя информация

            # Если ожидаем передачу и tftp_block в допустимом диапазоне
            if ((tftp_type == 'WRQ') | (tftp_type == 'DATA')) & (tftp_block in range(0, 65536)):
                # Проверяем, существуют ли данные для текущего соединения
                try:
                    cfg_up[rem_ip][rem_port]['cfg']
                # Обрабатываем ситуацию, когда данных нет. Такая ситуация может быть, если пакет с WRQ
                # не попал на сервер:
                except:
                    # Если тип передачи DATA, а данных нет, пишем в лог об ошибке
                    if tftp_type == 'DATA':
                        logger.info("WARNING: Transaction (DATA) without declaration (WRQ) for '%s'!", dip)
                # Данные получены, приступаем к обработке
                else:
                    # Если номер блока больше 128, значит размер файла превысил 64 КБ (512*128=65536).
                    # Такие данные в базу не попадут и будут удалены
                    if tftp_block > 128:
                        # Имя передаваемого файла
                        fil = "'%s'" % (cfg_up[rem_ip][rem_port]['file'])
                        # Определяем текст сообщения об ошибке
                        error_msg = 'Transferred file ' + fil + ' from ' + dip + ' is too large (greater than 64 KB)'
                        # Пробуем отправить сообщение об ошибке (диск заполнен)
                        try:
                            tftp.sendto(chr(0) + chr(5) + chr(0) + chr(3) + error_msg + chr(0), (rem_ip, rem_port))
                        # Если не получилось - не расстраиваемся :)
                        except:
                            pass
                        # Сообщаем об ошибке в лог
                        logger.info("ERROR: %s", error_msg)
                        # Удаляем весь блок данных из словаря
                        del cfg_up[rem_ip][rem_port]
                    else:
                        # Пробуем отправить подтверждение блока или начала передачи (ответ на WRQ, tftp_block равен 0)
                        try:
                            tftp.sendto(chr(0) + chr(4) + (lambda x: chr(x // 256) + chr(x % 256))(int(tftp_block)),
                                        (rem_ip, rem_port))
                        # Обрабатываем возможную ошибку сокета
                        except socket.error as err:
                            # При возникновении ошибки делаем запись в логе
                            logger.info("CRITICAL: Socket Error (ACK): %s. Exiting...", err.args[1])
                            # И завершаем работу
                            sys.exit(2)
                        else:
                            # Если получены сами данные, а не запрос:
                            if tftp_type == 'DATA':
                                # Обновляем конфигурацию для полученного блока в словаре
                                cfg_up[rem_ip][rem_port]['cfg'].update({tftp_block: data_upl})
                                # Если блок короче 512 байт, считаем его последним
                                if len(data_upl) < 512:
                                    # Данные
                                    tmp_dct = cfg_up[rem_ip][rem_port]['cfg']
                                    # Цель
                                    tmp_tgt = cfg_up[rem_ip][rem_port]['target']
                                    # Запрошенный файл
                                    tmp_fil = cfg_up[rem_ip][rem_port]['file']
                                    # Модель коммутатора
                                    tmp_sw = cfg_up[rem_ip][rem_port]['switch']
                                    # Количество блоков
                                    blk = len(cfg_up[rem_ip][rem_port]['cfg'])
                                    # Получаем MD5-сумму и размер полученных данных
                                    m5d, fln = md5size(cfg_up[rem_ip][rem_port]['cfg'])
                                    # Пишем в лог об окончании приема
                                    logger.info(
                                        "INFO: Recieved file  from %s for device '%s' (%s). Transferred file: '%s'."
                                        " Size: %s, blocks: %s, md5: %s", dip, tmp_tgt, tmp_sw, tmp_fil, fln, blk, m5d)
                                    # Пример:
                                    # INFO: Recieved file  from 10.137.130.56:57904 for device '10.99.0.2'
                                    # (DES-3200-28). Transferred file: 'cfg'. Size: 318, blocks: 1,
                                    # md5: c6c253ff4110f77b917901bb89d762df

                                    # Помещаем полученные данные в базу MySQL.
                                    # Параметры: таблица, данные, IP цели, имя файла, коммутатор, IP, хеш,
                                    # указание на необходимость записи в базу данных ('config')
                                    put_config_to_my_sql('up', tmp_dct, tmp_tgt, tmp_fil, tmp_sw, rem_ip, m5d, 'config')
                                    # Удаляем данные из словаря, т.к. передача закончена и они больше не нужны
                                    del cfg_up[rem_ip][rem_port]
        time.sleep(sleeptime)


class MyDaemon(Daemon):
    def run(self):
        main()


if __name__ == "__main__":
    daemon = MyDaemon('/var/run/dracon.pid', '/dev/null', log_file, log_file)
    if len(sys.argv) == 2:
        if 'start' == sys.argv[1]:
            daemon.start()
        elif 'faststart' == sys.argv[1]:
            daemon.start()
        elif 'stop' == sys.argv[1]:
            daemon.stop()
        elif 'restart' == sys.argv[1]:
            daemon.restart()
        else:
            print("Dracon: " + sys.argv[1] + " - unknown command")
            sys.exit(2)
        sys.exit(0)
    else:
        print("usage: %s start|stop|restart" % sys.argv[0])
        sys.exit(2)
