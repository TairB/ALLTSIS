#!/usr/bin/env python3
"""
phonebook.py — TSIS1
Приложение «Телефонная книга» на Python + PostgreSQL.
Таблицы: phonebook (контакты), phones (номера), groups (группы).
Запуск: python phonebook.py
"""

import csv, json, os, sys
import psycopg2, psycopg2.extras
from connect import get_connection


# =============================================================================
# BOOTSTRAP — выполняется один раз при каждом запуске программы.
# Читает schema.sql (создаёт таблицы) и procedures.sql (создаёт функции/процедуры).
# Использует IF NOT EXISTS / CREATE OR REPLACE — безопасно запускать повторно.
# =============================================================================

def bootstrap(conn):
    base = os.path.dirname(os.path.abspath(__file__))  # папка где лежит этот файл
    for fname in ("schema.sql", "procedures.sql"):
        path = os.path.join(base, fname)
        if not os.path.exists(path):
            print(f"[WARN] {fname} not found — skipping.")
            continue
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        with conn.cursor() as cur:   # FIX: курсор закрывается автоматически через with
            cur.execute(sql)
        conn.commit()
        print(f"[OK] {fname} loaded.")


# =============================================================================
# HELPERS — вспомогательные функции, используются в нескольких местах
# =============================================================================

# Базовый SQL для выборки контактов со всеми связанными данными.
# LEFT JOIN groups — подтягивает название группы (NULL если группы нет).
# LEFT JOIN phones — подтягивает все номера контакта.
# STRING_AGG — склеивает несколько номеров в одну строку: "+7... (mobile), +7... (work)"
# {where} и {order} — плейсхолдеры, подставляются в query_contacts()
CONTACT_SQL = """
    SELECT pb.id, pb.first_name, pb.last_name, pb.email, pb.birthday,
           g.name AS grp,
           STRING_AGG(ph.phone || ' (' || ph.type || ')', ', ' ORDER BY ph.type) AS phones_list
    FROM phonebook pb
    LEFT JOIN groups g  ON g.id = pb.group_id
    LEFT JOIN phones ph ON ph.contact_id = pb.id
    {where}
    GROUP BY pb.id, pb.first_name, pb.last_name, pb.email, pb.birthday, g.name
    {order}
"""

def query_contacts(conn, where="", order="ORDER BY pb.first_name", params=()):
    """Универсальная выборка контактов. RealDictCursor возвращает строки как словари."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(CONTACT_SQL.format(where=where, order=order), params)
        return cur.fetchall()

def print_contacts(rows):
    """Печатает список контактов в виде выровненной таблицы."""
    if not rows:
        print("  (no results)"); return
    print(f"  {'ID':>4}  {'First':<15}{'Last':<15}{'Email':<22}{'Birthday':<12}{'Group':<10}Phones")
    print("  " + "-" * 90)
    for r in rows:
        print(f"  {r['id']:>4}  {str(r['first_name'] or ''):<15}{str(r['last_name'] or ''):<15}"
              f"{str(r['email'] or ''):<22}{str(r['birthday'] or ''):<12}"
              f"{str(r['grp'] or ''):<10}{str(r['phones_list'] or '')}")

def get_groups(conn):
    """Возвращает все группы из таблицы groups: [(id, name), ...]"""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM groups ORDER BY name")
        return cur.fetchall()

def resolve_group(conn, name):
    """
    Ищет группу по имени (без учёта регистра через ILIKE).
    Если не найдена — создаёт новую и возвращает её id.
    RETURNING id — возвращает id только что вставленной строки.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM groups WHERE name ILIKE %s LIMIT 1", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("INSERT INTO groups (name) VALUES (%s) RETURNING id", (name,))
        gid = cur.fetchone()[0]
    conn.commit()
    return gid

def call_proc(conn, sql, params, silent=False):
    """
    Универсальный вызов хранимой процедуры (CALL ...).
    silent=True — не печатать [OK], используется при массовом импорте.
    conn.rollback() — откатывает транзакцию при ошибке PostgreSQL.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
        if not silent:
            print("[OK] Done.")
    except psycopg2.Error as e:
        conn.rollback()
        print(f"[ERROR] {e.pgerror or e}")

def pick_phone_type():
    """Предлагает выбрать тип телефона. Возвращает строку 'mobile'/'home'/'work'."""
    return {"1": "mobile", "2": "home", "3": "work"}.get(
        input("  Type: 1)mobile  2)home  3)work  [Enter=mobile]: ").strip(), "mobile"
    )


# =============================================================================
# CRUD — создание, обновление, удаление контактов
# =============================================================================

def add_contact(conn):
    """
    Как пользоваться:
      1. Введите имя (обязательно) и фамилию (можно пустое — нажмите Enter).
      2. Введите телефон в формате +77... (обязательно, должен быть уникальным).
      3. Email и дата рождения — необязательны, просто нажмите Enter.
      4. Выберите группу из списка или введите новое название (создастся автоматически).
      5. Выберите тип номера: 1/2/3 или Enter для mobile.
    INSERT ... ON CONFLICT (phone) DO NOTHING — защита от дублей по номеру телефона.
    """
    print("\n-- Add new contact --")
    fn    = input("  First name          : ").strip()
    ln    = input("  Last name           : ").strip()
    phone = input("  Phone (+77...)      : ").strip()
    email = input("  Email (or Enter)    : ").strip() or None
    bday  = input("  Birthday YYYY-MM-DD : ").strip() or None

    if not fn or not phone:
        print("[ERROR] First name and phone are required."); return

    print("\n  Available groups:", ", ".join(n for _, n in get_groups(conn)))
    grp   = input("  Group name (or Enter to skip): ").strip()
    ptype = pick_phone_type()
    gid   = resolve_group(conn, grp) if grp else None

    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO phonebook (first_name,last_name,phone,email,birthday,group_id) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (phone) DO NOTHING RETURNING id",
                (fn, ln or None, phone, email, bday, gid))
            res = cur.fetchone()

        if not res:
            # fetchone() вернул None — телефон уже существует, INSERT был отброшен
            print("[INFO] A contact with this phone already exists.")
            conn.rollback(); return

        conn.commit()

        # Добавляем номер в таблицу phones через процедуру add_phone()
        with conn.cursor() as cur:
            cur.execute("CALL add_phone(%s,%s,%s)", (fn, phone, ptype))
        conn.commit()
        print(f"[OK] Contact '{fn}' added.")
    except psycopg2.Error as e:
        conn.rollback(); print(f"[ERROR] {e.pgerror or e}")


def update_contact(conn):
    """
    Как пользоваться:
      1. Введите имя для поиска (можно частичное, регистр не важен).
      2. Программа покажет найденные контакты с их ID.
      3. Введите ID контакта который хотите изменить.
      4. Выберите поле: 1)имя 2)фамилия 3)email 4)дата рождения.
      5. Введите новое значение.
    Поле выбирается из словаря (field_map) — SQL-инъекция невозможна.
    """
    print("\n-- Update contact --")
    search = input("  First name to search: ").strip()
    if not search:
        print("[ERROR] Search query cannot be empty."); return   # FIX: валидация пустого ввода

    rows = query_contacts(conn, "WHERE pb.first_name ILIKE %s", params=(f"%{search}%",))
    if not rows:
        print("[INFO] No contact found."); return

    for r in rows:
        print(f"  ID:{r['id']}  {r['first_name']} {r['last_name'] or ''}  "
              f"email:{r['email'] or '—'}  bday:{r['birthday'] or '—'}")

    try:
        cid = int(input("  Enter ID to update: ").strip())
    except ValueError:
        print("[ERROR] Invalid ID."); return

    # field_map — безопасный способ передать имя колонки (не от пользователя напрямую)
    field = {"1": "first_name", "2": "last_name", "3": "email", "4": "birthday"}.get(
        input("  What to change? 1)First  2)Last  3)Email  4)Birthday: ").strip()
    )
    if not field:
        print("[ERROR] Invalid choice."); return

    val = input(f"  New value for '{field}': ").strip()
    if not val:
        print("[ERROR] Value cannot be empty."); return

    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE phonebook SET {field}=%s WHERE id=%s", (val, cid))
        conn.commit(); print("[OK] Contact updated.")
    except psycopg2.Error as e:
        conn.rollback(); print(f"[ERROR] {e.pgerror or e}")


def delete_contact(conn):
    """
    Как пользоваться:
      1. Выберите как искать: 1 = по имени, 2 = по номеру телефона.
      2. Введите значение (можно частичное).
      3. Программа покажет все совпадения — проверьте перед удалением.
      4. Введите 'y' для подтверждения, или Enter/любой другой символ для отмены.
    ON DELETE CASCADE в schema.sql — при удалении контакта автоматически
    удаляются все его номера из таблицы phones.
    cur.rowcount — количество фактически удалённых строк.
    """
    print("\n-- Delete contact --")
    field = {"1": "first_name", "2": "phone"}.get(
        input("  Delete by: 1)First name  2)Phone: ").strip()
    )
    if not field:
        print("[ERROR] Invalid choice."); return

    val = input("  Enter value: ").strip()
    if not val:
        print("[ERROR] Value cannot be empty."); return

    # Сначала показываем что будет удалено (preview)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT id,first_name,last_name,phone FROM phonebook WHERE {field} ILIKE %s",
            (val,))
        rows = cur.fetchall()

    if not rows:
        print("[INFO] No contact found."); return

    print(f"\n  About to delete {len(rows)} contact(s):")
    for r in rows:
        print(f"    ID:{r['id']}  {r['first_name']} {r['last_name'] or ''}  {r['phone'] or '—'}")

    if input("\n  Confirm deletion? [y/N]: ").strip().lower() != "y":
        print("[INFO] Cancelled."); return

    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM phonebook WHERE {field} ILIKE %s", (val,))
        n = cur.rowcount
    conn.commit(); print(f"[OK] Deleted {n} contact(s).")


# =============================================================================
# SEARCH & VIEW — поиск и просмотр
# =============================================================================

def search_all(conn):
    """
    Как пользоваться:
      Введите любой фрагмент: имя, фамилию, email или номер телефона.
      Поиск ведётся по всем полям сразу через DB-функцию search_contacts().
      Функция определена в procedures.sql — делает JOIN с таблицей phones.
    """
    p = input("\n  Search (name / email / phone): ").strip()
    if not p:
        print("[ERROR] Query cannot be empty."); return
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM search_contacts(%s)", (p,))
        rows = cur.fetchall()
    print(f"\n  Found {len(rows)} contact(s):")
    print_contacts(rows)

def filter_group(conn):
    """
    Как пользоваться:
      Программа выведет список групп с их ID.
      Введите числовой ID нужной группы.
      Отобразятся только контакты из этой группы.
    """
    groups = get_groups(conn)
    if not groups:
        print("  No groups found."); return
    print("\n  Available groups:")
    for gid, gn in groups:
        print(f"    {gid}. {gn}")
    try:
        gid = int(input("  Enter group ID: ").strip())
    except ValueError:
        print("[ERROR] Invalid input."); return
    rows = query_contacts(conn, where="WHERE pb.group_id=%s", params=(gid,))
    print(f"\n  Found {len(rows)} contact(s):")
    print_contacts(rows)

def search_email(conn):
    """
    Как пользоваться:
      Введите фрагмент email, например 'gmail' или '@mail'.
      ILIKE '%fragment%' — поиск вхождения без учёта регистра.
    """
    p = input("\n  Email fragment (e.g. 'gmail'): ").strip()
    if not p:
        print("[ERROR] Cannot be empty."); return
    rows = query_contacts(conn, where="WHERE pb.email ILIKE %s", params=(f"%{p}%",))
    print(f"\n  Found {len(rows)} contact(s):")
    print_contacts(rows)

def sort_contacts(conn):
    """
    Как пользоваться:
      Выберите поле для сортировки: 1=имя, 2=дата рождения, 3=ID (дата добавления).
      NULLS LAST — контакты без значения в этом поле идут в конец списка.
      Поле берётся из словаря — SQL-инъекция невозможна.
    """
    order_map = {"1": "pb.first_name", "2": "pb.birthday", "3": "pb.id"}
    field = order_map.get(
        input("\n  Sort by: 1)Name  2)Birthday  3)Date added [1]: ").strip(),
        "pb.first_name"   # default если нажать Enter или ввести неверное значение
    )
    print_contacts(query_contacts(conn, order=f"ORDER BY {field} NULLS LAST"))

def browse_paginated(conn):
    """
    Как пользоваться:
      Введите количество записей на страницу (по умолчанию 5, просто нажмите Enter).
      Навигация: N — следующая страница, P — предыдущая, Q — выход в меню.
      Использует DB-функцию get_contacts_paginated(page, size) из procedures.sql.
      LIMIT size OFFSET (page-1)*size — выбирает нужный кусок данных.
    """
    try:
        size = int(input("\n  Contacts per page [5]: ").strip() or "5")
    except ValueError:
        size = 5

    page = 1
    while True:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM get_contacts_paginated(%s,%s)", (page, size))
            rows = cur.fetchall()

        if not rows and page == 1:
            print("  (phonebook is empty)"); return

        # FIX: если зашли на следующую страницу а она пустая — конец списка
        if not rows:
            print("  ── end of list ──"); return

        print(f"\n  ── Page {page} ──")
        print(f"  {'ID':>4}  {'First':<20}{'Last':<20}{'Phone':<20}")
        print("  " + "-" * 66)
        for r in rows:
            print(f"  {r['id']:>4}  {str(r['first_name']):<20}"
                  f"{str(r['last_name'] or ''):<20}{str(r['phone']):<20}")

        if len(rows) < size:
            print("  ── end of list ──"); return

        nav = input("\n  [N]ext / [P]rev / [Q]uit: ").strip().lower()
        if nav == "n":
            page += 1
        elif nav == "p":
            page = max(1, page - 1)   # max(1, ...) — не уйти ниже первой страницы
        else:
            return

def show_groups(conn):
    """
    Показывает все группы и количество контактов в каждой.
    COUNT(pb.id) — считает строки. LEFT JOIN — включает группы с 0 контактов.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT g.name, COUNT(pb.id) AS total
            FROM groups g
            LEFT JOIN phonebook pb ON pb.group_id = g.id
            GROUP BY g.name ORDER BY g.name
        """)
        rows = cur.fetchall()
    if not rows:
        print("  (no groups)"); return
    print(f"\n  {'Group':<20}{'Contacts':>8}")
    print("  " + "-" * 30)
    for name, total in rows:
        print(f"  {name:<20}{total:>8}")


# =============================================================================
# IMPORT / EXPORT
# =============================================================================

def export_json(conn):
    """
    Как пользоваться:
      Введите имя файла или нажмите Enter (сохранится как export.json).
      Экспортирует все контакты с группами и всеми телефонными номерами.
      json.dump(ensure_ascii=False) — кириллица сохраняется нормально.
      indent=2 — красивое форматирование JSON с отступами.
    """
    path = input("\n  Output filename [export.json]: ").strip() or "export.json"
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT pb.id, pb.first_name, pb.last_name, pb.email,
                   pb.birthday::TEXT AS birthday, g.name AS group_name
            FROM phonebook pb
            LEFT JOIN groups g ON g.id = pb.group_id
            ORDER BY pb.id
        """)
        contacts = [dict(r) for r in cur.fetchall()]
    # FIX: открываем отдельный курсор — нельзя переиспользовать закрытый
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur2:
        for c in contacts:
            cur2.execute("SELECT phone,type FROM phones WHERE contact_id=%s ORDER BY type", (c["id"],))
            c["phones"] = [dict(p) for p in cur2.fetchall()]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(contacts, f, ensure_ascii=False, indent=2)
    print(f"[OK] Exported {len(contacts)} contact(s) to '{path}'.")

def import_json(conn):
    """
    Как пользоваться:
      Введите путь к JSON файлу или нажмите Enter (читает export.json).
      Для каждого дубликата (по имени) программа спросит: s=пропустить, o=перезаписать.
      json.load() — читает файл и преобразует в список Python-словарей.
    """
    path = input("\n  JSON file [export.json]: ").strip() or "export.json"
    if not os.path.exists(path):
        print(f"[ERROR] File not found: {path}"); return

    with open(path, encoding="utf-8") as f:
        contacts = json.load(f)

    ins = upd = skip = 0
    for c in contacts:
        fn = str(c.get("first_name", "")).strip()
        if not fn:
            skip += 1; continue

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM phonebook WHERE first_name ILIKE %s LIMIT 1", (fn,))
            ex = cur.fetchone()

        if ex:
            ans = input(f"  '{fn}' already exists. [s]kip / [o]verwrite: ").strip().lower()
            if ans != "o":
                skip += 1; continue
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE phonebook SET last_name=%s, email=%s, birthday=%s WHERE id=%s",
                    (c.get("last_name"), c.get("email"), c.get("birthday"), ex[0]))
            conn.commit(); upd += 1
        else:
            gid = resolve_group(conn, c["group_name"]) if c.get("group_name") else None
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO phonebook (first_name,last_name,email,birthday,group_id) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (fn, c.get("last_name"), c.get("email"), c.get("birthday"), gid))
            conn.commit(); ins += 1
            # Добавляем телефоны из списка "phones" через процедуру, silent=True — не мусорим в вывод
            for ph in c.get("phones", []):
                if ph.get("phone"):
                    call_proc(conn, "CALL add_phone(%s,%s,%s)",
                              (fn, ph["phone"], ph.get("type", "mobile")), silent=True)

    print(f"[JSON] Done — inserted:{ins}  updated:{upd}  skipped:{skip}")

def import_csv(conn):
    """
    Как пользоваться:
      Введите путь к CSV файлу или нажмите Enter (читает contacts.csv).
      Ожидаемые колонки: first_name, last_name, phone, phone_type, email, birthday, group
      Если телефон уже есть — строка обновляется (upsert), не дублируется.
      csv.DictReader — первая строка CSV становится названиями колонок-ключей.
      xmax=0 — PostgreSQL трюк: True если строка вставлена, False если обновлена.
    """
    path = input("\n  CSV file [contacts.csv]: ").strip() or "contacts.csv"
    if not os.path.exists(path):
        print(f"[ERROR] File not found: {path}"); return

    ins = upd = skip = 0
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            fn    = row.get("first_name", "").strip()
            phone = row.get("phone", "").strip()

            if not fn:
                print(f"  [SKIP] Row {i}: missing first_name."); skip += 1; continue

            # FIX: resolve_group внутри try — чтобы ошибка БД не крашила весь импорт
            phone_val = phone if phone else None

            try:
                grp_name = row.get("group", "").strip()
                gid = resolve_group(conn, grp_name) if grp_name else None
                with conn.cursor() as cur:
                    if phone_val:
                        # Upsert: если телефон уже есть — обновляем остальные поля
                        cur.execute(
                            "INSERT INTO phonebook (first_name,last_name,phone,email,birthday,group_id) "
                            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (phone) DO UPDATE "
                            "SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, "
                            "email=EXCLUDED.email, birthday=EXCLUDED.birthday, group_id=EXCLUDED.group_id "
                            "RETURNING (xmax=0)",
                            (fn, row.get("last_name") or None, phone_val,
                             row.get("email") or None, row.get("birthday") or None, gid))
                    else:
                        # Нет телефона — вставляем без конфликт-проверки
                        cur.execute(
                            "INSERT INTO phonebook (first_name,last_name,email,birthday,group_id) "
                            "VALUES (%s,%s,%s,%s,%s) RETURNING (xmax=0)",
                            (fn, row.get("last_name") or None,
                             row.get("email") or None, row.get("birthday") or None, gid))
                    res = cur.fetchone()
                conn.commit()

                if res and res[0]: ins += 1
                else: upd += 1

                if phone_val:
                    ptype = row.get("phone_type", "mobile") or "mobile"
                    # silent=True — не печатать [OK] для каждого номера при массовом импорте
                    call_proc(conn, "CALL add_phone(%s,%s,%s)",
                              (fn, phone_val, ptype), silent=True)

            except psycopg2.Error as e:
                conn.rollback()
                print(f"  [ERROR] Row {i}: {e.pgerror or e}"); skip += 1

    print(f"[CSV] Done — inserted:{ins}  updated:{upd}  skipped:{skip}")


# =============================================================================
# STORED PROCEDURES — прямые вызовы хранимых процедур из procedures.sql
# =============================================================================

def add_phone(conn):
    """
    Как пользоваться:
      Введите имя существующего контакта (поиск без учёта регистра).
      Введите новый номер телефона.
      Выберите тип: 1)mobile 2)home 3)work.
      Вызывает процедуру add_phone() из procedures.sql.
      Один контакт может иметь несколько номеров разных типов.
    """
    name  = input("\n  Contact first name: ").strip()
    phone = input("  Phone number (+77...): ").strip()
    if not name or not phone:
        print("[ERROR] Name and phone are required."); return
    call_proc(conn, "CALL add_phone(%s,%s,%s)", (name, phone, pick_phone_type()))

def move_group(conn):
    """
    Как пользоваться:
      Введите имя существующего контакта.
      Введите название группы — существующей или новой (создастся автоматически).
      Вызывает процедуру move_to_group() из procedures.sql.
    """
    name = input("\n  Contact first name: ").strip()
    if not name:
        print("[ERROR] Name is required."); return
    print("  Existing groups:", ", ".join(n for _, n in get_groups(conn)))
    grp = input("  Target group name: ").strip()
    if not grp:
        print("[ERROR] Group name is required."); return
    call_proc(conn, "CALL move_to_group(%s,%s)", (name, grp))


# =============================================================================
# MENU — главное меню программы
# =============================================================================

MENU = """
╔══════════════════════════════════════════════╗
║         📒  PhoneBook — TSIS1                ║
╠══════════════════════════════════════════════╣
║  Contacts                                    ║
║   1. Add new contact                         ║
║   2. Update contact                          ║
║   3. Delete contact                          ║
║  Search & View                               ║
║   4. Search (name / email / phone)           ║
║   5. Filter by group                         ║
║   6. Search by email                         ║
║   7. Sort contacts                           ║
║   8. Browse paginated                        ║
║   9. Show groups & count                     ║
║  Import / Export                             ║
║  10. Import from CSV                         ║
║  11. Export to JSON                          ║
║  12. Import from JSON                        ║
║  Manage                                      ║
║  13. Add phone to contact                    ║
║  14. Move contact to group                   ║
║   0. Exit                                    ║
╚══════════════════════════════════════════════╝"""

# Словарь: номер пункта → функция. Чище чем длинный if/elif.
ACTIONS = {
    "1": add_contact,     "2": update_contact,   "3": delete_contact,
    "4": search_all,      "5": filter_group,      "6": search_email,
    "7": sort_contacts,   "8": browse_paginated,  "9": show_groups,
    "10": import_csv,     "11": export_json,      "12": import_json,
    "13": add_phone,      "14": move_group,
}

def main():
    """
    Точка входа. Подключается к БД, запускает bootstrap, затем цикл меню.
    sys.exit(1) — выход с кодом ошибки если нет подключения к БД.
    conn.close() — корректно закрывает соединение при выходе.
    """
    print("Connecting to PostgreSQL ...")
    try:
        conn = get_connection()
    except Exception:
        sys.exit(1)

    bootstrap(conn)

    while True:
        print(MENU)
        choice = input("  Your choice: ").strip()
        if choice == "0":
            print("Goodbye!"); break
        elif choice in ACTIONS:
            ACTIONS[choice](conn)
        else:
            print("[ERROR] Unknown option, try again.")

    conn.close()


if __name__ == "__main__":
    main()