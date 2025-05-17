import logging
import uuid
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен вашего бота
BOT_TOKEN = "7990174156:AAECQ7djna9rkR8AhZYL37NiL4-JkPu1bi8"
DATA_FILE = "bot_data.json"

# --- Вспомогательные функции ---

def load_data() -> dict:
    """Загрузка сохраненных данных из файла с обработкой ошибок"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)

            # Преобразуем списки обратно в множества
            if 'projects' in data:
                for project in data['projects'].values():
                    if 'members' in project:
                        project['members'] = set(project['members'])

            return data
        except json.JSONDecodeError:
            print("Ошибка: файл данных содержит некорректные данные JSON.")
            return {}
    return {}

def save_data(data: dict) -> None:
    """Сохранение данных в файл с преобразованием множеств в списки и обработкой несериализуемых объектов"""
    def default_serializer(obj):
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, (datetime, uuid.UUID)):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=default_serializer)
    except Exception as e:
        logger.error(f"Error saving data: {e}")
        raise

def get_project_id_by_name(bot_data: dict, project_name: str, user_id: int) -> str:
    """Поиск проекта по имени с проверкой членства"""
    if 'projects' not in bot_data:
        return None
    for proj_id, project in bot_data['projects'].items():
        if project['name'].lower() == project_name.lower() and str(user_id) in project['members']:  # Исправлено: приведение к строке
            return proj_id
    return None

def get_project_by_name_owner_only(bot_data: dict, project_name: str, owner_id: int) -> str:
    """Поиск проекта по имени с проверкой владельца"""
    if 'projects' not in bot_data:
        return None
    for proj_id, project in bot_data['projects'].items():
        if project['name'].lower() == project_name.lower() and project['owner_id'] == owner_id:
            return proj_id
    return None


async def resolve_user_id(context: CallbackContext, username: str) -> int:
    """Попытка разрешить username в user_id"""
    if not username.startswith('@'):
        return None

    try:
        username = username[1:]  # Удаляем @
        logger.info(f"Trying to resolve username: @{username}")

        # Попробуем сначала get_chat (для пользователей, начавших диалог с ботом)
        try:
            user = await context.bot.get_chat(f"@{username}")
            logger.info(f"Successfully resolved @{username} to ID {user.id}")
            return user.id
        except Exception as e:
            logger.warning(f"get_chat failed for @{username}, trying alternative methods: {e}")

        # Альтернативный метод через get_users
        try:
            user = await context.bot.get_user_profile_photos(username)
            if user and user.total_count > 0:
                return user.user_id
        except Exception as e:
            logger.warning(f"get_user_profile_photos failed for @{username}: {e}")

        logger.error(f"All methods failed to resolve @{username}")
        return None

    except Exception as e:
        logger.error(f"Critical error resolving username @{username}: {e}")
        return None
# --- Обработчики команд ---

async def start(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    username = f"@{user.username}" if user.username else "❌ Не указан"

    welcome_message = (
        f"🔍 <b>Ваши данные:</b>\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"👤 <b>Username:</b> {username}\n"
        f"📛 <b>Имя:</b> {user.full_name}\n\n"
        "Выберите действие:"
    )

    keyboard = [
        [InlineKeyboardButton("Показать инструкцию", callback_data='show_help')],
        [InlineKeyboardButton("Мои проекты", callback_data='list_projects')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(welcome_message, reply_markup=reply_markup)


async def help_command(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /help"""
    print(
        "Отправка инструкции"
    )
    instructions = (
        "📚 Инструкция по использованию:\n\n"
        "1. Сначала отправьте мне документ (файл).\n"
        "2. Затем используйте команды:\n\n"
        "📂 Проекты:\n"
        "/newproject <название> - Создать новый проект\n"
        "/listprojects - Список ваших проектов\n"
        "/members <проект> - Участники проекта\n\n"
        "🔄 Версии:\n"
        "/commit <проект> [описание] - Сохранить новую версию\n"
        "/versions <проект> - Все версии проекта\n"
        "/get <проект> [версия] - Получить версию\n\n"
        "👥 Управление доступом:\n"
        "/addmember <проект> <user> - Добавить участника\n"
        "/removemember <проект> <user> - Удалить участника\n\n"
        "Для команд /newproject и /commit сначала отправьте файл боту."
    )

    keyboard = [
        [InlineKeyboardButton("Создать проект", callback_data='new_project')],
        [InlineKeyboardButton("Мои проекты", callback_data='list_projects')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message is not None:
        await update.message.reply_text(instructions, reply_markup=reply_markup)

    else:
        print("No message found in the update")


async def handle_document(update: Update, context: CallbackContext) -> None:
    """Обработка загруженных документов"""
    user_id = update.effective_user.id
    context.user_data['last_file_id'] = update.message.document.file_id
    context.user_data['last_file_name'] = update.message.document.file_name
    context.user_data['last_file_caption'] = update.message.caption or ""

    logger.info(
        f"User {user_id} uploaded file {update.message.document.file_name} with id {update.message.document.file_id}")

    keyboard = [
        [
            InlineKeyboardButton("Создать новый проект", callback_data='new_project'),
            InlineKeyboardButton("Обновить существующий", callback_data='commit_project')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Файл '{update.message.document.file_name}' получен. Выберите действие:",
        reply_markup=reply_markup
    )

async def new_project(update: Update, context: CallbackContext) -> None:
    """Создание нового проекта"""
    user_id = update.effective_user.id

    # Если это callback от кнопки
    if update.callback_query:
        await update.callback_query.answer()
        if 'last_file_id' not in context.user_data:
            await update.callback_query.edit_message_text(
                "Сначала отправьте документ, который хотите добавить в новый проект."
            )
            return

        await update.callback_query.edit_message_text(
            "Введите название нового проекта:"
        )
        context.user_data['awaiting_project_name'] = True
        context.user_data['action'] = 'new_project'
        return

    # Если это обычная команда
    if 'last_file_id' not in context.user_data:
        await update.message.reply_text("Сначала отправьте документ, который хотите добавить в новый проект.")
        return

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите название проекта: /newproject <название_проекта>")
        return

    project_name = " ".join(context.args)
    await _create_project(update, context, project_name)

async def _create_project(update: Update, context: CallbackContext, project_name: str) -> None:
    try:
        """Внутренняя функция создания проекта"""
        user_id = update.effective_user.id

        if not project_name or project_name.strip() == "":
            if update.callback_query:
                await update.callback_query.edit_message_text("Название проекта не может быть пустым.")
            else:
                await update.message.reply_text("Название проекта не может быть пустым.")
            return

        if 'projects' not in context.bot_data:
            context.bot_data['projects'] = {}

        # Проверка на существующий проект
        for proj_data in context.bot_data['projects'].values():
            if proj_data['name'].lower() == project_name.lower() and proj_data['owner_id'] == user_id:
                if update.callback_query:
                    await update.callback_query.edit_message_text(
                        f"Проект с названием '{project_name}' уже существует у вас.")
                else:
                    await update.message.reply_text(f"Проект с названием '{project_name}' уже существует у вас.")
                return

        project_id = str(uuid.uuid4())
        new_version_num = 1

        initial_caption = context.user_data.get(
            'last_file_caption') or f"Initial version by {update.effective_user.full_name}"

        context.bot_data['projects'][project_id] = {
            "name": project_name,
            "owner_id": user_id,
            "members": {str(user_id)},  # Сохраняем как строку для JSON
            "versions": [{
                "file_id": context.user_data['last_file_id'],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "uploader_id": user_id,
                "uploader_name": update.effective_user.full_name,
                "version_num": new_version_num,
                "caption": initial_caption,
                "file_name": context.user_data.get('last_file_name', 'document')
            }],
            "next_version_num": new_version_num + 1
        }

        # Очистка временных данных
        for key in ['last_file_id', 'last_file_caption', 'last_file_name', 'awaiting_project_name', 'action']:
            if key in context.user_data:
                del context.user_data[key]

        # Сохранение данных
        save_data(context.bot_data)

        message_text = f"✅ Проект '{project_name}' создан. Первая версия документа добавлена."

        if update.callback_query:
            await update.callback_query.edit_message_text(message_text)
        else:
            await update.message.reply_text(message_text)

        logger.info(f"User {user_id} created project '{project_name}' (ID: {project_id})")
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        await update.message.reply_text("Произошла ошибка при создании проекта. Пожалуйста, попробуйте позже.")

async def commit_version(update: Update, context: CallbackContext) -> None:
    """Добавление новой версии в проект"""
    user_id = update.effective_user.id

    # Если это callback от кнопки
    if update.callback_query:
        await update.callback_query.answer()
        if 'last_file_id' not in context.user_data:
            await update.callback_query.edit_message_text(
                "Сначала отправьте документ, который хотите закоммитить."
            )
            return

        # Получаем список проектов пользователя
        user_projects = []
        if 'projects' in context.bot_data:
            for proj_id, project in context.bot_data['projects'].items():
                if user_id in project['members']:
                    user_projects.append(project['name'])

        if not user_projects:
            await update.callback_query.edit_message_text("У вас нет проектов для обновления.")
            return

        # Создаем кнопки для выбора проекта
        keyboard = []
        for project in user_projects[:10]:  # Ограничим количество кнопок
            keyboard.append([InlineKeyboardButton(project, callback_data=f'commit_to:{project}')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            "Выберите проект для обновления:",
            reply_markup=reply_markup
        )
        return

    # Если это обычная команда
    if 'last_file_id' not in context.user_data:
        await update.message.reply_text("Сначала отправьте документ, который хотите закоммитить.")
        return

    if not context.args:
        await update.message.reply_text("Укажите название проекта: /commit <название_проекта> [описание]")
        return

    project_name_arg = context.args[0]
    commit_message_from_args = " ".join(context.args[1:])
    commit_message_from_caption = context.user_data.get('last_file_caption')

    commit_message = (
        commit_message_from_args if commit_message_from_args else
        commit_message_from_caption if commit_message_from_caption else
        f"Update by {update.effective_user.full_name}"
    )

    await _add_version_to_project(update, context, project_name_arg, commit_message)

async def _add_version_to_project(update: Update, context: CallbackContext, project_name: str,
                                  commit_message: str) -> None:
    """Внутренняя функция добавления версии в проект"""
    user_id = update.effective_user.id
    project_id = get_project_id_by_name(context.bot_data, project_name, user_id)

    if not project_id:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                f"Проект '{project_name}' не найден или у вас нет к нему доступа.")
        else:
            await update.message.reply_text(f"Проект '{project_name}' не найден или у вас нет к нему доступа.")
        return

    project = context.bot_data['projects'][project_id]

    if str(user_id) not in project['members']:
        if update.callback_query:
            await update.callback_query.edit_message_text(f"Вы не являетесь участником проекта '{project['name']}'.")
        else:
            await update.message.reply_text(f"Вы не являетесь участником проекта '{project['name']}'.")
        return

    new_version_num = project["next_version_num"]
    project['versions'].append({
        "file_id": context.user_data['last_file_id'],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "uploader_id": user_id,
        "uploader_name": update.effective_user.full_name,
        "version_num": new_version_num,
        "caption": commit_message,
        "file_name": context.user_data.get('last_file_name', 'document')
    })
    project["next_version_num"] += 1

    # Очистка временных данных
    for key in ['last_file_id', 'last_file_caption', 'last_file_name']:
        if key in context.user_data:
            del context.user_data[key]

    # Сохранение данных
    save_data(context.bot_data)

    message_text = f"✅ Новая версия ({new_version_num}) документа добавлена в проект '{project['name']}'."

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text)
    else:
        await update.message.reply_text(message_text)

    logger.info(f"User {user_id} committed version {new_version_num} to project '{project['name']}' (ID: {project_id})")

async def list_projects(update: Update, context: CallbackContext) -> None:
    """Список проектов пользователя"""
    user_id = update.effective_user.id

    # Если это callback от кнопки
    if update.callback_query:
        await update.callback_query.answer()

    if 'projects' not in context.bot_data or not context.bot_data['projects']:
        message = "Пока нет ни одного проекта."
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return

    user_projects = []
    for proj_id, project in context.bot_data['projects'].items():
        if str(user_id) in project['members']:
            role = "👑" if project['owner_id'] == user_id else "👥"
            user_projects.append(f"{role} {project['name']} (версий: {len(project['versions'])})")

    if not user_projects:
        message = "Вы не состоите ни в одном проекте."
    else:
        message = "📂 Ваши проекты:\n\n" + "\n".join(user_projects)

        # Добавляем кнопки для каждого проекта
        keyboard = []
        for proj_id, project in context.bot_data['projects'].items():
            if str(user_id) in project['members']:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{project['name']} ({len(project['versions'])})",
                        callback_data=f"project_details:{proj_id}"
                    )
                ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)
        return

    if update.callback_query:
        await update.callback_query.edit_message_text(message)
    else:
        await update.message.reply_text(message)

async def list_versions(update: Update, context: CallbackContext) -> None:
    """Список версий проекта"""
    user_id = update.effective_user.id

    # Если это callback от кнопки
    if update.callback_query:
        await update.callback_query.answer()
        # Ожидаем формат callback_data="project_details:{proj_id}"
        try:
            proj_id = update.callback_query.data.split(':')[1]
            project = context.bot_data['projects'].get(proj_id)

            if not project or str(user_id) not in project['members']:
                await update.callback_query.edit_message_text("Проект не найден или у вас нет доступа.")
                return

            response = f"📚 Версии проекта '{project['name']}':\n\n"
            for ver in reversed(project['versions'][-10:]):  # Показываем последние 10 версий
                response += (
                    f"🔹 Версия {ver['version_num']} ({ver['file_name']})\n"
                    f"   📅 {ver['timestamp']}\n"
                    f"   👤 {ver['uploader_name']}\n"
                    f"   📝 {ver['caption']}\n\n"
                )

            # Кнопки для управления проектом
            keyboard = [
                [
                    InlineKeyboardButton("⬅️ Назад", callback_data='list_projects'),
                    InlineKeyboardButton("📥 Получить версию", callback_data=f'get_version:{proj_id}')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.callback_query.edit_message_text(response, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in list_versions callback: {e}")
            await update.callback_query.edit_message_text("Произошла ошибка при обработке запроса.")
        return

    # Если это обычная команда
    if not context.args:
        await update.message.reply_text("Укажите название проекта: /versions <название_проекта>")
        return

    project_name = " ".join(context.args)
    project_id = get_project_id_by_name(context.bot_data, project_name, user_id)

    if not project_id:
        await update.message.reply_text(f"Проект '{project_name}' не найден или у вас нет к нему доступа.")
        return

    project = context.bot_data['projects'][project_id]
    if not project['versions']:
        await update.message.reply_text(f"В проекте '{project['name']}' пока нет версий.")
        return

    response = f"Версии документа в проекте '{project['name']}':\n"
    for ver in reversed(project['versions']):
        response += (f"  Версия {ver['version_num']} ({ver['file_name']}) от {ver['timestamp']}\n"
                     f"    Загрузил: {ver['uploader_name']}\n"
                     f"    Описание: {ver['caption']}\n"
                     f"    [/get {project['name']} {ver['version_num']}]\n\n")

    if len(response) > 4096:
        response_parts = [response[i:i + 4000] for i in range(0, len(response), 4000)]
        for part in response_parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(response)

async def get_version(update: Update, context: CallbackContext) -> None:
    """Получение конкретной версии документа"""
    user_id = update.effective_user.id

    # Если это callback от кнопки
    if update.callback_query:
        await update.callback_query.answer()
        # Ожидаем формат callback_data="get_version:{proj_id}"
        try:
            proj_id = update.callback_query.data.split(':')[1]
            project = context.bot_data['projects'].get(proj_id)

            if not project or str(user_id) not in project['members']:
                await update.callback_query.edit_message_text("Проект не найден или у вас нет доступа.")
                return

            if not project['versions']:
                await update.callback_query.edit_message_text("В проекте нет версий.")
                return

            # Получаем последнюю версию
            target_version = project['versions'][-1]

            try:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=target_version['file_id'],
                    caption=(
                        f"📂 Проект: {project['name']}\n"
                        f"🔹 Версия: {target_version['version_num']}\n"
                        f"📝 Описание: {target_version['caption']}\n"
                        f"👤 Автор: {target_version['uploader_name']}\n"
                        f"📅 Дата: {target_version['timestamp']}"
                    )
                )
                logger.info(
                    f"Sent version {target_version['version_num']} of project {project['name']} to user {user_id}")
            except Exception as e:
                logger.error(
                    f"Error sending document for project {proj_id}, version {target_version['version_num']}: {e}")
                await update.callback_query.edit_message_text(
                    "Не удалось отправить документ. Возможно, он был удален из истории чата с ботом."
                )
        except Exception as e:
            logger.error(f"Error in get_version callback: {e}")
            await update.callback_query.edit_message_text("Произошла ошибка при обработке запроса.")
        return

    # Если это обычная команда
    if not context.args:
        await update.message.reply_text("Укажите название проекта: /get <название_проекта> [номер_версии]")
        return

    project_name = context.args[0]
    version_to_get = None
    if len(context.args) > 1:
        try:
            version_to_get = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Номер версии должен быть числом.")
            return

    project_id = get_project_id_by_name(context.bot_data, project_name, user_id)
    if not project_id:
        await update.message.reply_text(f"Проект '{project_name}' не найден или у вас нет к нему доступа.")
        return

    project = context.bot_data['projects'][project_id]
    if not project['versions']:
        await update.message.reply_text(f"В проекте '{project['name']}' нет версий.")
        return

    target_version = None
    if version_to_get is None:
        if project['versions']:
            target_version = project['versions'][-1]
    else:
        for ver in project['versions']:
            if ver['version_num'] == version_to_get:
                target_version = ver
                break

    if not target_version:
        await update.message.reply_text(
            f"Версия {version_to_get if version_to_get is not None else 'с таким номером'} не найдена в проекте '{project['name']}'.")
        return

    try:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=target_version['file_id'],
            caption=(
                f"Проект: {project['name']}\n"
                f"Версия: {target_version['version_num']}\n"
                f"Файл: {target_version['file_name']}\n"
                f"Описание: {target_version['caption']}\n"
                f"От: {target_version['timestamp']}"
            )
        )
        logger.info(f"Sent version {target_version['version_num']} of project {project['name']} to user {user_id}")
    except Exception as e:
        logger.error(f"Error sending document for project {project_id}, version {target_version['version_num']}: {e}")
        await update.message.reply_text(
            "Не удалось отправить документ. Возможно, он был удален из истории чата с ботом, или у бота проблемы с доступом к файлу.")


async def add_member(update: Update, context: CallbackContext) -> None:
    """Добавление участника в проект с поиском ID через @userinfobot"""
    owner_id = update.effective_user.id

    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /addmember <название_проекта> <@username или user_id>\n\n"
            "Примеры:\n"
            "/addmember МойПроект @username\n"
            "/addmember МойПроект 123456789"
        )
        return

    project_name = context.args[0]
    member_identifier = context.args[1]

    # Поиск проекта
    project_id = get_project_by_name_owner_only(context.bot_data, project_name, owner_id)
    if not project_id:
        await update.message.reply_text(f"Проект '{project_name}' не найден или вы не владелец")
        return

    project = context.bot_data['projects'][project_id]
    member_id_to_add = None

    # Если передан username
    if member_identifier.startswith('@'):
        username = member_identifier[1:].strip().lower()
        logger.info(f"Поиск ID для @{username} через @userinfobot")

        try:
            # 1. Отправляем запрос к @userinfobot
            await context.bot.send_message(
                chat_id="@userinfobot",
                text=f"/start {username}"
            )

            # 2. Ждем ответ от @userinfobot (этот код требует доработки для реального использования)
            # В реальном боте нужно:
            # - Сохранять запросы
            # - Обрабатывать ответы от @userinfobot
            # - Извлекать ID из ответа

            # Эмуляция получения ID (в реальном коде нужно заменить на обработку ответа)
            member_id_to_add = await get_user_id_from_userinfobot(username)

            if not member_id_to_add:
                raise Exception("Не удалось получить ID от @userinfobot")

        except Exception as e:
            logger.error(f"Ошибка получения ID для @{username}: {e}")
            await update.message.reply_text(
                f"❌ Не удалось найти ID для @{username}\n\n"
                "Решение:\n"
                "1. Попросите пользователя:\n"
                "   - Написать мне /start\n"
                "   - Или предоставить ID через @userinfobot\n"
                "2. Проверьте правильность username\n"
                "3. Используйте числовой ID (/addmember проект 123456789)"
            )
            return

    # Если передан числовой ID
    else:
        try:
            member_id_to_add = int(member_identifier)
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID. Используйте числовой ID или @username")
            return

    # Проверки перед добавлением
    if member_id_to_add == owner_id:
        await update.message.reply_text("⚠️ Вы уже владелец этого проекта")
        return

    if str(member_id_to_add) in project['members']:
        await update.message.reply_text(f"ℹ️ Пользователь уже в проекте '{project['name']}'")
        return

    # Проверка доступности пользователя
    try:
        await context.bot.send_chat_action(
            chat_id=member_id_to_add,
            action='typing'
        )
    except Exception as e:
        logger.error(f"Нет доступа к пользователю {member_id_to_add}: {e}")
        await update.message.reply_text(
            f"❌ Не могу связаться с пользователем {member_id_to_add}\n"
            "Попросите его:\n"
            "1. Написать мне /start\n"
            "2. Разблокировать меня, если был блок"
        )
        return

    # Добавление пользователя
    project['members'].add(str(member_id_to_add))
    save_data(context.bot_data)

    # Уведомления
    success_msg = await update.message.reply_text(
        f"✅ Успешно добавлен: {member_identifier} (ID: {member_id_to_add})\n"
        f"в проект '{project['name']}'"
    )

    try:
        await context.bot.send_message(
            chat_id=member_id_to_add,
            text=(
                f"📌 Вас добавили в проект '{project['name']}'\n"
                f"Владелец: {update.effective_user.full_name}\n\n"
                "Доступные команды:\n"
                "/listprojects - Ваши проекты\n"
                f"/versions {project_name} - Версии проекта"
            )
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить пользователя: {e}")
        await success_msg.reply_text(
            "⚠ Пользователь добавлен, но не получил уведомление.\n"
            "Попросите его написать мне /start"
        )


async def get_user_id_from_userinfobot(username: str) -> int:
    """Функция для получения ID пользователя от @userinfobot"""
    # В реальной реализации нужно:
    # 1. Отправить запрос к @userinfobot
    # 2. Перехватить и разобрать ответ
    # 3. Извлечь ID пользователя

    # Это заглушка - в реальном коде нужно реализовать:
    # - Отправку команды /start @username боту @userinfobot
    # - Ожидание ответа от @userinfobot
    # - Парсинг ответа для извлечения ID

    # Временное решение - попробовать стандартные методы
    try:
        # Попробуем стандартный метод
        user = await context.bot.get_chat(f"@{username}")
        return user.id
    except:
        return None  # В реальном коде не должно быть заглушки

async def remove_member(update: Update, context: CallbackContext) -> None:
    """Удаление участника из проекта"""
    owner_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /removemember <название_проекта> <user_id или @username>")
        return

    project_name = context.args[0]
    member_identifier = context.args[1]

    project_id = get_project_by_name_owner_only(context.bot_data, project_name, owner_id)
    if not project_id:
        await update.message.reply_text(f"Проект '{project_name}' не найден или вы не являетесь его владельцем.")
        return

    project = context.bot_data['projects'][project_id]

    member_id_to_remove = None
    if member_identifier.startswith('@'):
        member_id_to_remove = await resolve_user_id(context, member_identifier)
        if not member_id_to_remove:
            await update.message.reply_text(
                "Не удалось найти пользователя по username. Укажите числовой User ID участника.")
            return
    else:
        try:
            member_id_to_remove = int(member_identifier)
        except ValueError:
            await update.message.reply_text("Неверный формат User ID. Укажите числовой ID.")
            return

    if member_id_to_remove == owner_id:
        await update.message.reply_text(
            "Владелец не может удалить сам себя из проекта.")
        return

    if str(member_id_to_remove) not in project['members']:
        await update.message.reply_text(
            f"Пользователь {member_id_to_remove} не является участником проекта '{project['name']}'.")
        return

    project['members'].remove(str(member_id_to_remove))
    save_data(context.bot_data)  # Сохраняем изменения

    await update.message.reply_text(f"✅ Пользователь {member_id_to_remove} удален из проекта '{project['name']}'.")
    logger.info(f"User {owner_id} removed member {member_id_to_remove} from project '{project['name']}'")

    try:
        await context.bot.send_message(
            chat_id=member_id_to_remove,
            text=f"Вас удалили из проекта '{project['name']}'."
        )
    except Exception as e:
        logger.warning(f"Could not notify removed member {member_id_to_remove} for project {project_id}: {e}")

async def list_members(update: Update, context: CallbackContext) -> None:
    """Список участников проекта"""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Укажите название проекта: /members <название_проекта>")
        return

    project_name = " ".join(context.args)
    project_id = get_project_id_by_name(context.bot_data, project_name, user_id)

    if not project_id:
        await update.message.reply_text(f"Проект '{project_name}' не найден или у вас нет к нему доступа.")
        return

    project = context.bot_data['projects'][project_id]
    members_list_str = f"👥 Участники проекта '{project['name']}':\n\n"

    member_details = []
    for member_id_in_set in project['members']:
        prefix = "👑 Владелец: " if member_id_in_set == str(project['owner_id']) else "👤 Участник: "
        member_name = f"ID: {member_id_in_set}"

        # Пытаемся найти имя пользователя среди загруженных версий
        for ver in project['versions']:
            if str(ver['uploader_id']) == member_id_in_set:
                member_name = f"{ver['uploader_name']} (ID: {member_id_in_set})"
                break

        member_details.append(f"{prefix}{member_name}")

    if not member_details:
        members_list_str += "В проекте нет участников."
    else:
        members_list_str += "\n".join(sorted(member_details))

    await update.message.reply_text(members_list_str)

async def handle_text(update: Update, context: CallbackContext) -> None:
    """Обработка текстовых сообщений (для ожидания названия проекта)"""
    user_id = update.effective_user.id

    if 'awaiting_project_name' in context.user_data and context.user_data['awaiting_project_name']:
        action = context.user_data.get('action')
        project_name = update.message.text.strip()

        if not project_name:
            await update.message.reply_text("Название проекта не может быть пустым. Пожалуйста, введите название снова.")
            return

        if action == 'new_project':
            await _create_project(update, context, project_name)
        elif action == 'commit_project':
            await _add_version_to_project(update, context, project_name, "")

        # Очищаем флаги
        context.user_data.pop('awaiting_project_name', None)
        context.user_data.pop('action', None)
        return

    # Если это не ожидаемое сообщение, просто игнорируем
    return
async def button_handler(update: Update, context: CallbackContext) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == 'show_help':
        instructions = (
            "📚 <b>Инструкция по использованию:</b>\n\n"
            "1. Сначала отправьте мне документ (файл).\n"
            "2. Затем используйте команды:\n\n"
            "<b>📂 Проекты:</b>\n"
            "/newproject <название> - Создать новый проект\n"
            "/listprojects - Список ваших проектов\n"
            "/members <проект> - Участники проекта\n\n"
            "<b>🔄 Версии:</b>\n"
            "/commit <проект> [описание] - Сохранить новую версию\n"
            "/versions <проект> - Все версии проекта\n"
            "/get <проект> [версия] - Получить версию\n\n"
            "<b>👥 Управление доступом:</b>\n"
            "/addmember <проект> <user> - Добавить участника\n"
            "/removemember <проект> <user> - Удалить участника\n\n"
            "Для команд /newproject и /commit сначала отправьте файл боту."
        )

        keyboard = [
            [InlineKeyboardButton("Создать проект", callback_data='new_project')],
            [InlineKeyboardButton("Мои проекты", callback_data='list_projects')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=instructions,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    elif data == 'list_projects':
        await list_projects(update, context)
    elif data == 'new_project':
        await new_project(update, context)
    elif data == 'commit_project':
        await commit_version(update, context)
    elif data.startswith('project_details:'):
        await list_versions(update, context)
    elif data.startswith('get_version:'):
        await get_version(update, context)
    elif data.startswith('commit_to:'):
        project_name = data.split(':')[1]
        await _add_version_to_project(update, context, project_name, "Обновление через кнопку")

def main() -> None:
    """Запуск бота."""
    # Загружаем сохраненные данные
    bot_data = load_data()

    application = Application.builder().token(BOT_TOKEN).build()

    # Устанавливаем загруженные данные
    application.bot_data.update(bot_data)

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("newproject", new_project))
    application.add_handler(CommandHandler("commit", commit_version))
    application.add_handler(CommandHandler("listprojects", list_projects))
    application.add_handler(CommandHandler("versions", list_versions))
    application.add_handler(CommandHandler("get", get_version))
    application.add_handler(CommandHandler("addmember", add_member))
    application.add_handler(CommandHandler("removemember", remove_member))
    application.add_handler(CommandHandler("members", list_members))

    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()
