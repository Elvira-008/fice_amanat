import html
from datetime import datetime
from urllib.parse import quote

from database import get_all_students_list, get_classes_summary, get_parents_summary, get_recent_attendance, get_teachers


def page(title, body):
    return f"""
    <!doctype html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{esc(title)}</title>
        <link rel="stylesheet" href="/static/styles.css">
    </head>
    <body><main>{body}</main></body>
    </html>
    """


def esc(value):
    return html.escape(str(value or ""))


def url_value(value):
    return quote(str(value or ""), safe="")


def status_label(status):
    return "Пришел" if status == "keldi" else "Ушел"


def students_rows(class_names=None, can_manage=False):
    allowed_classes = set(class_names or [])
    rows = []
    for name, class_name, photo_path, parent_name, parent_code in get_all_students_list():
        if allowed_classes and class_name not in allowed_classes:
            continue
        actions = f"""
            <td class="actions">
                <a class="btn light" href="/edit/{url_value(name)}">Изменить</a>
                <form class="inline-form" action="/delete/{url_value(name)}" method="post" onsubmit="return confirm('Удалить ученика?')"><button class="btn red" type="submit">Удалить</button></form>
            </td>
        """ if can_manage else ""
        rows.append(f"""
        <tr>
            <td><img class="photo" src="/{esc(photo_path)}" alt=""></td>
            <td>{esc(name)}</td>
            <td>{esc(class_name)}</td>
            <td>{esc(parent_name)}<br><span class="muted">Пароль: {esc(parent_code)}</span></td>
            {actions}
        </tr>
        """)
    if not rows:
        colspan = 5 if can_manage else 4
        return f"<tr><td colspan='{colspan}' class='muted'>Пока учеников нет</td></tr>"
    return "".join(rows)


def attendance_rows():
    rows = []
    for name, class_name, status, timestamp, parent_name, parent_code in get_recent_attendance(30):
        rows.append(f"""
        <tr>
            <td>{esc(name)}</td>
            <td>{esc(class_name)}</td>
            <td>{status_label(status)}</td>
            <td>{esc(timestamp)}</td>
            <td>{esc(parent_name)} <span class="muted">({esc(parent_code)})</span></td>
        </tr>
        """)
    if not rows:
        return "<tr><td colspan='5' class='muted'>Отчетов пока нет</td></tr>"
    return "".join(rows)


def home_dashboard(class_names=None):
    allowed_classes = set(class_names or [])
    students = [row for row in get_all_students_list() if not allowed_classes or row[1] in allowed_classes]
    students_count = len(students)
    recent = get_recent_attendance(200)
    if allowed_classes:
        recent = [row for row in recent if row[1] in allowed_classes]
    today = datetime.now().strftime("%Y-%m-%d")
    today_in = sum(
        1
        for _, _, status, timestamp, _, _ in recent
        if status == "keldi" and str(timestamp).startswith(today)
    )
    today_out = sum(
        1
        for _, _, status, timestamp, _, _ in recent
        if status == "ketti" and str(timestamp).startswith(today)
    )

    return f"""
        <div class="grid home-stats">
            <div class="stat green" data-icon="ID">
                <strong>{students_count}</strong>
                <span class="muted">Ученики в базе</span>
                <div class="trend">
                    <svg viewBox="0 0 120 50"><path d="M5 39 L34 29 L55 15 L78 22 L110 4" fill="none" stroke="#22c55e" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="110" cy="4" r="6" fill="#22c55e"/></svg>
                </div>
                <span class="pill"><b>{students_count}</b> всего</span>
            </div>
            <div class="stat blue" data-icon="IN">
                <strong>{today_in}</strong>
                <span class="muted">Сегодня пришли</span>
                <div class="trend">
                    <svg viewBox="0 0 120 50"><path d="M6 39 L34 25 L60 13 L85 21 L111 4" fill="none" stroke="#2563eb" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="111" cy="4" r="6" fill="#2563eb"/></svg>
                </div>
                <span class="pill"><b>{today_in}</b> за сегодня</span>
            </div>
            <div class="stat red" data-icon="OUT">
                <strong>{today_out}</strong>
                <span class="muted">Сегодня ушли</span>
                <div class="trend">
                    <svg viewBox="0 0 120 50"><path d="M8 29 L42 29 L76 29 L112 29" fill="none" stroke="#ef4444" stroke-width="5" stroke-linecap="round"/><circle cx="42" cy="29" r="5" fill="#ef4444"/><circle cx="76" cy="29" r="5" fill="#ef4444"/></svg>
                </div>
                <span class="pill"><b>{today_out}</b> за сегодня</span>
            </div>
        </div>
    """


def role_picker_view():
    return """
        <div class="home-shell">
            <section class="hero">
                <div class="shield">ID</div>
                <h1>School Face ID</h1>
                <p>Камера, ученики, родители и отчеты в одном месте.</p>
                <div class="hero-line"></div>
            </section>
            <div class="grid nav-grid">
                <a class="nav-card blue" data-icon="ID" href="/teacher-login">
                    <strong>Мугалим / Кызматкер</strong>
                    <span>Ученики, камера жана жалпы отчет</span>
                </a>
                <a class="nav-card purple" data-icon="ADM" href="/admin-login">
                    <strong>Админ</strong>
                    <span>Системаны толук башкаруу</span>
                </a>
                <a class="nav-card orange" data-icon="PAR" href="/parent">
                    <strong>Родитель</strong>
                    <span>Балаңыздын келүү-кетүү отчету</span>
                </a>
            </div>
            <div class="home-footer">
                <b>Face ID School System</b><br>
                Безопасность · Точность · Удобство
            </div>
            <div class="decor-dots left"></div>
            <div class="decor-dots right"></div>
        </div>
    """


def teacher_login_view(error=False):
    error_html = '<p class="error">Пароль туура эмес</p>' if error else ""
    return f"""
        <div class="top"><a class="btn light" href="/">Артка</a></div>
        <h1>Мугалим кирүүсү</h1>
        <div class="panel">
            {error_html}
            <form action="/teacher-login" method="post">
                <label>Логин</label>
                <input name="login" placeholder="Логин учителя" required autofocus>
                <label>Пароль</label>
                <input type="password" name="password" placeholder="Пароль" required>
                <button class="btn" type="submit">Кирүү</button>
            </form>
        </div>
    """


def teacher_classes_view(login, class_names):
    cards = [f"""
        <a class="nav-card blue" data-icon="CLS" href="/teacher-select-class?class_name={url_value(name)}">
            <strong>{esc(name)}</strong><span>Открыть класс</span>
        </a>
    """ for name in class_names]
    if not cards:
        cards.append("<div class='panel muted'>Администратор пока не закрепил за вами классы.</div>")
    return f"""
        <div class="top"><a class="btn light" href="/teacher-logout">Выйти</a></div>
        <h1>Учитель: {esc(login)}</h1>
        <p class="muted">Выберите класс, с которым хотите работать.</p>
        <div class="grid nav-grid">{''.join(cards)}</div>
    """


def unified_login_view(error=False):
    error_html = '<p class="error">Неверный логин или пароль</p>' if error else ""
    return f"""
        <div class="login-shell">
            <section class="hero login-hero">
                <div class="shield">ID</div>
                <h1>School Face ID</h1>
                <p>Введите логин и пароль для входа.</p>
                <div class="hero-line"></div>
            </section>
            <div class="panel unified-login-panel">
                {error_html}
                <form action="/login" method="post">
                    <label>Логин</label>
                    <input name="login" placeholder="Введите логин" required autofocus>
                    <label>Пароль</label>
                    <input type="password" name="password" placeholder="Введите пароль" required>
                    <button class="btn" type="submit">Войти</button>
                </form>
            </div>
        </div>
    """


def home_view(role="teacher", class_names=None):
    class_names = list(class_names or [])
    role_label = "Администратор · полный доступ" if role == "admin" else f"Учитель · классы {esc(', '.join(class_names))}"
    logout_url = "/admin-logout" if role == "admin" else "/teacher-logout"
    admin_cards = ""
    switch_class = '<a class="btn light class-switch" href="/teacher-classes">Сменить класс</a>' if role == "teacher" else ""
    corner_content = switch_class if role == "teacher" else '<div class="notify">!</div><div class="avatar">ID</div>'
    return f"""
        <div class="home-shell">
            <div class="home-top">
                {corner_content}
            </div>
            <section class="hero">
                <div class="shield">ID</div>
                <h1>School Face ID</h1>
                <p>{'Управление системой и отчетами.' if role == 'admin' else 'Посещаемость учеников вашего класса.'}</p>
                <p><b>{role_label}</b></p>
                <div class="hero-line"></div>
            </section>
            <div class="grid nav-grid nav-grid-teacher">
                {'' if role == 'teacher' else '''
                <a class="nav-card green" data-icon="ID" href="/students"><strong>Ученики</strong><span>Просмотр и управление учениками</span></a>
                <a class="nav-card blue" data-icon="CAM" href="/camera"><strong>Камера</strong><span>Распознавание в реальном времени</span></a>
                '''}
                <a class="nav-card purple" data-icon="LOG" href="/list">
                    <strong>Общий отчет</strong>
                    <span>Приход, уход и данные родителей</span>
                </a>
                {admin_cards}
            </div>
    """ + home_dashboard(class_names if role == "teacher" else []) + f"""
            <div class="top" style="margin-top:16px;">
                <a class="btn light" href="{logout_url}">Выйти</a>
            </div>
            <div class="home-footer">
                <b>Face ID School System</b><br>
                Безопасность · Точность · Удобство
            </div>
            <div class="decor-dots left"></div>
            <div class="decor-dots right"></div>
        </div>
    """


def list_view(class_names=None):
    allowed_classes = set(class_names or [])
    cards = []
    summaries = {row[0]: row[1:] for row in get_classes_summary()}
    class_rows = (
        [(name, *summaries.get(name, (0, 0, 0))) for name in class_names]
        if class_names else [(name, *values) for name, values in summaries.items()]
    )
    for class_name, students_count, arrived, left in class_rows:
        cards.append(f"""
            <a class="nav-card blue" data-icon="CLS" href="/list/{url_value(class_name)}">
                <strong>{esc(class_name or 'Без класса')}</strong>
                <span>Учеников: {students_count} · Пришли: {arrived} · Ушли: {left}</span>
            </a>
        """)
    if not cards:
        cards.append("<div class='panel muted'>Классы пока не добавлены</div>")
    if not class_names:
        table_rows = []
        for class_name, students_count, arrived, left in class_rows:
            table_rows.append(f"""
                <tr><td><b>{esc(class_name or 'Без класса')}</b></td><td>{students_count}</td>
                <td>{arrived}</td><td>{left}</td>
                <td><a class="btn" href="/list/{url_value(class_name)}">Открыть отчет</a></td></tr>
            """)
        if not table_rows:
            table_rows.append("<tr><td colspan='5' class='muted'>Классы пока не добавлены</td></tr>")
        content = """
            <table><thead><tr><th>Класс</th><th>Учеников</th><th>Пришли сегодня</th><th>Ушли сегодня</th><th>Действие</th></tr></thead>
            <tbody>""" + "".join(table_rows) + """</tbody></table>
        """
    else:
        content = '<div class="grid nav-grid">' + "".join(cards) + "</div>"
    return """
        <form class="inline-form clear-attendance-form" action="/clear-attendance" method="post" onsubmit="return confirm('Очистить журнал посещаемости?')">
            <button class="btn red" type="submit">Очистить журнал</button>
        </form>
        <div class="top">
            <a class="btn light" href="/">Назад</a>
            <a class="btn green" href="/students">Ученики</a>
        </div>
        <h1>Общий отчет</h1>
        <p class="muted">Выберите класс, чтобы посмотреть его отчет.</p>
        """ + content + """
    """


def class_report_view(class_name, report_rows, show_class_list=True):
    rows = []
    for name, _, status, timestamp, parent_name, parent_code in report_rows:
        rows.append(f"""
            <tr><td>{esc(name)}</td><td>{status_label(status)}</td><td>{esc(timestamp)}</td>
            <td>{esc(parent_name)} <span class="muted">({esc(parent_code)})</span></td></tr>
        """)
    if not rows:
        rows.append("<tr><td colspan='4' class='muted'>Отчетов для этого класса пока нет</td></tr>")
    back_url = "/list" if show_class_list else "/"
    back_text = "Назад к классам" if show_class_list else "На главную"
    return f"""
        <div class="top"><a class="btn light" href="{back_url}">{back_text}</a></div>
        <h1>Отчет класса {esc(class_name)}</h1>
        <table><thead><tr><th>Ученик</th><th>Статус</th><th>Дата и время</th><th>Родитель</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table>
    """


def teacher_report_view(class_name, report_rows):
    rows = []
    for name, _, report_date, arrived_at, left_at, parent_name, parent_code in report_rows:
        rows.append(f"""
            <tr>
                <td>{esc(name)}</td>
                <td>{esc(report_date)}</td>
                <td>{esc(arrived_at or '—')}</td>
                <td>{esc(left_at or '—')}</td>
            </tr>
        """)
    if not rows:
        rows.append("<tr><td colspan='4' class='muted'>В этом классе пока нет учеников</td></tr>")
    return f"""
        <div class="top">
            <a class="btn light" href="/teacher-classes">Сменить класс</a>
        </div>
        <h1>Общий отчет · {esc(class_name)}</h1>
        <p class="muted">Посещаемость учеников по датам.</p>
        <table>
            <thead><tr><th>Ученик</th><th>Дата</th><th>Пришел</th><th>Ушел</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    """


def students_view(class_names=None, is_admin=False):
    class_names = list(class_names or [])
    title = "Все ученики" if is_admin else f"Ученики класса {esc(class_names[0])}" if class_names else "Ученики"
    class_field = """
                <label>Класс</label>
                <input name="class_name" required placeholder="Например: 11А">
    """ if is_admin else """
                <label>Класс</label>
                <select name="class_name" required>
    """ + "".join(f'<option value="{esc(name)}">{esc(name)}</option>' for name in class_names) + """
                </select>
    """
    action_header = "<th>Действие</th>" if is_admin else ""
    add_form = """
        <dialog id="addStudentDialog" class="student-dialog">
            <div class="student-dialog-head">
                <h2>Добавить ученика</h2>
                <button class="dialog-close" type="button" aria-label="Закрыть" onclick="document.getElementById('addStudentDialog').close()">×</button>
            </div>
            <form action="/add" method="post" enctype="multipart/form-data">
                <label>Имя ученика</label>
                <input name="name" required placeholder="Например: Иван Иванов">
                """ + class_field + """
                <label>Родитель</label>
                <input name="parent_name" required placeholder="Имя родителя">
                <label>Пароль родителя для входа</label>
                <input name="parent_code" required placeholder="Например: parent_ivanov">
                <label>Фото ученика</label>
                <input type="file" name="photo" accept="image/*" required>
                <button class="btn green" type="submit">Добавить в базу</button>
            </form>
        </dialog>
    """ if is_admin else ""
    add_button = """
        <button class="btn green add-student-corner" type="button" onclick="document.getElementById('addStudentDialog').showModal()">
            Добавить ученика
        </button>
    """ if is_admin else ""
    return """
        <div class="top">
            <a class="btn light" href="/">Назад</a>
        </div>
        <div class="students-heading">
            <h1>""" + title + """</h1>
            """ + add_button + """
        </div>
        <table>
            <thead><tr><th>Фото</th><th>Имя</th><th>Класс</th><th>Родитель и пароль</th>""" + action_header + """</tr></thead>
            <tbody>""" + students_rows(class_names, is_admin) + """</tbody>
        </table>
        """ + add_form + """
    """


def edit_student_view(student):
    name, class_name, photo_path, parent_name, parent_code, _ = student
    return f"""
        <div class="top">
            <a class="btn light" href="/students">Назад</a>
            <a class="btn" href="/camera">Камера</a>
        </div>
        <h1>Изменить ученика</h1>
        <div class="panel">
            <form action="/edit/{url_value(name)}" method="post" enctype="multipart/form-data">
                <label>Имя ученика</label>
                <input name="name" value="{esc(name)}" required>
                <label>Класс</label>
                <input name="class_name" value="{esc(class_name)}" required>
                <label>Родитель</label>
                <input name="parent_name" value="{esc(parent_name)}" required>
                <label>Код родителя для входа</label>
                <input name="parent_code" value="{esc(parent_code)}" required>
                <label>Новое фото ученика</label>
                <input type="file" name="photo" accept="image/*">
                <div class="edit-photo">
                    <img class="photo" src="/{esc(photo_path)}" alt="">
                    <span class="muted">Если фото не выбрать, останется старое.</span>
                </div>
                <button class="btn green" type="submit">Сохранить</button>
            </form>
        </div>
    """


def parent_login_view(name="", code=""):
    return f"""
        <div class="top"><a class="btn light" href="/">Назад</a></div>
        <h1>Кабинет родителя</h1>
        <div class="panel">
            <form action="/parent" method="get">
                <label>Имя родителя</label>
                <input name="name" value="{esc(name)}" placeholder="Введите имя родителя" required>
                <label>Код родителя</label>
                <input name="code" value="{esc(code)}" placeholder="Введите код родителя" required>
                <button class="btn" type="submit">Войти и показать отчет</button>
            </form>
        </div>
    """


def parent_report_view(rows):
    return f"""
        <div class="top">
            <a class="btn light" href="/">Назад</a>
        </div>
        <h1>Отчет ребенка</h1>
        <table>
            <thead><tr><th>Ученик</th><th>Класс</th><th>Статус</th><th>Время</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    """


def camera_view(status="keldi", camera_index=0):
    status_text = "Приход" if status == "keldi" else "Уход"
    return f"""
        <div class="top">
            <a class="btn light" href="/">Назад</a>
            <a class="btn green" href="/students">Ученики</a>
            <a class="btn purple" href="/list">Общий отчет</a>
        </div>
        <h1>Мониторинг Face ID — Режим: {status_text}</h1>
        <div class="camera-container" style="margin-bottom: 20px; text-align: center;">
            <img src="/video_feed?status={status}&camera_index={camera_index}" 
                 alt="Видеопоток" 
                 style="width: 100%; max-width: 640px; border-radius: 8px; background: #000; border: 3px solid #3b82f6;">
        </div>
        <div class="actions" style="display: flex; gap: 10px; justify-content: center;">
            <a class="btn" href="/camera?status={status}&camera_index={camera_index}">Перезапустить камеру</a>
            <a class="btn blue" href="/camera?status={'ketti' if status == 'keldi' else 'keldi'}&camera_index={camera_index}">
                Переключить на {'Уход' if status == 'keldi' else 'Приход'}
            </a>
        </div>
    """


def admin_classes_view():
    rows = []
    for class_name, students_count, arrived, left in get_classes_summary():
        rows.append(f"""
            <tr>
                <td><b>{esc(class_name or 'Без класса')}</b></td>
                <td>{students_count}</td>
                <td>{arrived}</td>
                <td>{left}</td>
                <td><a class="btn" href="/list/{url_value(class_name)}">Открыть отчет</a></td>
            </tr>
        """)
    if not rows:
        rows.append("<tr><td colspan='5' class='muted'>Классы пока не добавлены</td></tr>")
    return """
        <div class="top"><a class="btn light" href="/">Назад</a><a class="btn green" href="/students">Ученики</a><a class="btn purple" href="/list">Общий отчет</a></div>
        <h1>Классы</h1>
        <p class="muted">Сводка посещаемости, разделенная по классам.</p>
        <table><thead><tr><th>Класс</th><th>Учеников</th><th>Пришли сегодня</th><th>Ушли сегодня</th><th>Отчет</th></tr></thead>
        <tbody>""" + "".join(rows) + """</tbody></table>
    """


def admin_parents_view(class_names=None, is_admin=True):
    rows = []
    for parent_name, parent_code, _, children in get_parents_summary(class_names):
        rows.append(f"""
            <tr>
                <td><b>{esc(parent_name or 'Не указано')}</b></td>
                <td>{esc(parent_code)}</td>
                <td>{esc(children)}</td>
            </tr>
        """)
    if not rows:
        rows.append("<tr><td colspan='3' class='muted'>Родители пока не добавлены</td></tr>")
    return """
        <div class="top"><a class="btn light" href="/">Назад</a><a class="btn green" href="/students">Ученики</a></div>
        <h1>Родители</h1>
        <p class="muted">Логин родителя — его имя. Код доступа используется как пароль.</p>
        <table><thead><tr><th>Логин родителя</th><th>Пароль</th><th>Ученик и класс</th></tr></thead>
        <tbody>""" + "".join(rows) + """</tbody></table>
    """


def admin_class_report_view(class_name, attendance):
    rows = []
    for name, status, time_text in attendance:
        rows.append(f"<tr><td>{esc(name)}</td><td>{status_label(status)}</td><td>{esc(time_text)}</td></tr>")
    if not rows:
        rows.append("<tr><td colspan='3' class='muted'>Посещений пока нет</td></tr>")
    return f"""
        <div class="top"><a class="btn light" href="/admin/classes">Назад к классам</a><a class="btn purple" href="/list">Общий отчет</a></div>
        <h1>Отчет класса {esc(class_name)}</h1>
        <table><thead><tr><th>Ученик</th><th>Статус</th><th>Время</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table>
    """


def admin_teachers_view():
    rows = []
    for login, classes in get_teachers():
        rows.append(f"""
            <tr><td><b>{esc(login)}</b></td><td>{esc(', '.join(classes) or 'Не назначены')}</td>
            <td><form method="post" action="/admin/teachers/{url_value(login)}/delete" onsubmit="return confirm('Удалить аккаунт учителя?')"><button class="btn red">Удалить</button></form></td></tr>
        """)
    if not rows:
        rows.append("<tr><td colspan='3' class='muted'>Учителей пока нет</td></tr>")
    return """
        <div class="top"><a class="btn light" href="/">Назад</a></div>
        <h1>Аккаунты учителей</h1>
        <div class="panel"><h2>Добавить или обновить учителя</h2>
            <form method="post" action="/admin/teachers">
                <label>Логин</label><input name="login" required>
                <label>Пароль</label><input type="password" name="password" placeholder="Для существующего аккаунта можно оставить пустым">
                <label>Закрепленные классы</label>
                <div id="teacherClasses"><input name="class_names" required placeholder="Например: 7А"></div>
                <button class="btn light add-class-btn" type="button" onclick="addTeacherClass()">+ Добавить класс</button>
                <button class="btn green">Сохранить аккаунт</button>
            </form>
        </div>
        <table><thead><tr><th>Логин</th><th>Закрепленные классы</th><th>Действие</th></tr></thead><tbody>""" + "".join(rows) + """</tbody></table>
        <script>
            function addTeacherClass() {
                const input = document.createElement('input');
                input.name = 'class_names';
                input.placeholder = 'Еще один класс';
                input.required = true;
                document.getElementById('teacherClasses').appendChild(input);
                input.focus();
            }
        </script>
    """


def admin_login_view(error=False):
    error_html = '<p class="error">Пароль администратора неверный</p>' if error else ""
    return f"""
        <div class="top"><a class="btn light" href="/">Назад</a></div>
        <h1>Вход администратора</h1>
        <div class="panel">
            {error_html}
            <form action="/admin-login" method="post">
                <label>Пароль администратора</label>
                <input type="password" name="password" placeholder="Пароль" required autofocus>
                <button class="btn purple" type="submit">Войти</button>
            </form>
        </div>
    """
