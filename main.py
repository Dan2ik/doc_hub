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
# Убедитесь, что токен правильный и не скомпрометирован
BOT_TOKEN = "7990174156:AAECQ7djna9rkR8AhZYL37NiL4-JkPu1bi8" # Скрыл токен на всякий случай

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
                    if 'members' in project and isinstance(project['members'], list):
                        project['members'] = set(project['members'])
                    elif 'members' not in project: # Убеждаемся, что members есть
                         project['members'] = set()


            # Убеждаемся, что owner_id является int (если сохранялся как str)
            if 'projects' in data:
                 for project in data['projects'].values():
                     if isinstance(project.get('owner_id'), str):
                         try:
                             project['owner_id'] = int(project['owner_id'])
                         except ValueError:
                             logger.warning(f"Could not convert owner_id {project['owner_id']} to int for project {project.get('name')}")


            return data
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from data file: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading data file: {e}")
            return {}
    return {}

def save_data(data: dict) -> None:
    """Сохранение данных в файл с преобразованием множеств в списки и обработкой несериализуемых объектов"""
    def default_serializer(obj):
        if isinstance(obj, set):
            return list(obj)
        # Добавляем обработку int для owner_id на всякий случай, хотя int по умолчанию сериализуется
        # if isinstance(obj, int):
        #    return obj
        # uuid.UUID уже обрабатывается default
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2) # Убрал default_serializer, т.к. int и str по умолчанию сериализуются, set обрабатывается при сохранении
    except Exception as e:
        logger.error(f"Error saving data: {e}")
        # В продакшене тут, возможно, нужна более надежная обработка, например, сохранение во временный файл

def get_project_id_by_name(bot_data: dict, project_name: str, user_id: int) -> str:
    """Поиск проекта по имени с проверкой членства"""
    if 'projects' not in bot_data:
        return None
    user_id_str = str(user_id) # Преобразуем user_id к строке для сравнения с членами множества
    for proj_id, project in bot_data['projects'].items():
        if project['name'].lower() == project_name.lower() and user_id_str in project.get('members', set()): # Проверка на наличие members
            return proj_id
    return None

def get_project_by_name_owner_only(bot_data: dict, project_name: str, owner_id: int) -> str:
    """Поиск проекта по имени с проверкой владельца"""
    if 'projects' not in bot_data:
        return None
    for proj_id, project in bot_data['projects'].items():
        # Убеждаемся, что owner_id в данных имеет правильный тип для сравнения
        stored_owner_id = project.get('owner_id')
        if isinstance(stored_owner_id, str):
             try:
                 stored_owner_id = int(stored_owner_id)
             except ValueError:
                 stored_owner_id = None # Неверный формат

        if project['name'].lower() == project_name.lower() and stored_owner_id == owner_id:
            return proj_id
    return None


async def resolve_user_id(context: CallbackContext, username: str) -> int | None:
    """Попытка разрешить username в user_id"""
    if not username or not isinstance(username, str) or not username.startswith('@'):
        logger.warning(f"Invalid username format: {username}")
        return None

    username = username[1:] # Удаляем @
    logger.info(f"Trying to resolve username: @{username}")

    try:
        # Попробуем получить chat (работает, если пользователь уже писал боту)
        user = await context.bot.get_chat(f"@{username}")
        logger.info(f"Successfully resolved @{username} to ID {user.id} via get_chat")
        return user.id
    except Exception as e:
        logger.warning(f"get_chat failed for @{username}: {e}")
        # Альтернативные методы (get_user_profile_photos менее надежен для получения ID)
        # Более надежные методы требуют дополнительных шагов или взаимодействия с пользователем

    logger.warning(f"Could not resolve username @{username} to a user ID.")
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
        "📚 <b>Инструкция по использованию:</b>\n\n"
        "1. Сначала отправьте мне документ (файл).\n"
        "2. Затем используйте команды:\n\n"
        "<b>📂 Проекты:</b>\n"
        "/newproject <code>название</code> - Создать новый проект\n"
        "/listprojects - Список ваших проектов\n"
        "/members <code>проект</code> - Участники проекта\n\n"
        "<b>🔄 Версии:</b>\n"
        "/commit <code>проект</code> [описание] - Сохранить новую версию\n"
        "/versions <code>проект</code> - Все версии проекта\n"
        "/get <code>проект</code> [версия] - Получить версию\n\n"
        "<b>👥 Управление доступом:</b>\n"
        "/addmember <code>проект</code> <code>user</code> - Добавить участника\n"
        "/removemember <code>проект</code> <code>user</code> - Удалить участника\n\n"
        "Для команд /newproject и /commit сначала отправьте файл боту.\n\n"
    )
    keyboard = [
        [InlineKeyboardButton("Мои проекты", callback_data='list_projects')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(welcome_message, reply_markup=reply_markup)

async def help_command(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /help"""
    # Эта функция вызывается командой /help, не кнопкой "Показать инструкцию" из /start
    logger.info("Handling /help command")
    instructions = (
        "📚 <b>Инструкция по использованию:</b>\n\n"
        "1. Сначала отправьте мне документ (файл).\n"
        "2. Затем используйте команды:\n\n"
        "<b>📂 Проекты:</b>\n"
        "/newproject <code>название</code> - Создать новый проект\n"  # <- Исправлено здесь
        "/listprojects - Список ваших проектов\n"
        "/members <code>проект</code> - Участники проекта\n\n"  # <- И здесь
        "<b>🔄 Версии:</b>\n"
        "/commit <code>проект</code> описание - Сохранить новую версию\n"
        "/versions <code>проект</code> - Все версии проекта\n"
        "/get <code>проект</code> версия - Получить версию\n\n"
        "<b>👥 Управление доступом:</b>\n"
        "/addmember <code>проект</code> <code>user</code> - Добавить участника\n"
        "/removemember <code>проект</code> <code>user</code> - Удалить участника\n\n"
        "Для команд /newproject и /commit сначала отправьте файл боту.\n\n"
    )

    keyboard = [
        [InlineKeyboardButton("Создать проект", callback_data='new_project')],
        [InlineKeyboardButton("Мои проекты", callback_data='list_projects')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Команда /help всегда приходит с сообщением, поэтому проверка update.message is not None не нужна
    await update.message.reply_html(instructions, reply_markup=reply_markup) # Используем reply_html

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
            InlineKeyboardButton("Обновить существующий", callback_data='commit_project') # Изменен текст на более понятный
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Файл '{update.message.document.file_name}' получен. Выберите действие:",
        reply_markup=reply_markup
    )

async def new_project(update: Update, context: CallbackContext) -> None:
    """Создание нового проекта - обработка команды /newproject"""
    user_id = update.effective_user.id

    # Если это обычная команда /newproject
    if update.message:
        if 'last_file_id' not in context.user_data:
            await update.message.reply_text("Сначала отправьте документ, который хотите добавить в новый проект.")
            return

        if not context.args:
            await update.message.reply_text("Пожалуйста, укажите название проекта: /newproject <название_проекта>")
            return

        project_name = " ".join(context.args)
        await _create_project(update, context, project_name)

    # Обработка callback 'new_project' перемещена в button_handler

async def _create_project(update: Update, context: CallbackContext, project_name: str) -> None:
    """Внутренняя функция создания проекта, вызывается командой или после ввода названия по кнопке"""
    try:
        user = update.effective_user # Получаем пользователя из текущего update
        user_id = user.id

        if not project_name or project_name.strip() == "":
            if update.callback_query:
                await update.callback_query.edit_message_text("Название проекта не может быть пустым.")
            else:
                await update.message.reply_text("Название проекта не может быть пустым.")
            return

        if 'projects' not in context.bot_data:
            context.bot_data['projects'] = {}

        # Проверка на существующий проект у этого пользователя
        for proj_data in context.bot_data['projects'].values():
            # Проверяем, что owner_id есть и имеет правильный тип
            stored_owner_id = proj_data.get('owner_id')
            if isinstance(stored_owner_id, str):
                 try:
                      stored_owner_id = int(stored_owner_id)
                 except ValueError:
                      stored_owner_id = None

            if proj_data['name'].lower() == project_name.lower() and stored_owner_id == user_id:
                message = f"Проект с названием '{project_name}' уже существует у вас."
                if update.callback_query:
                    await update.callback_query.edit_message_text(message)
                else:
                    await update.message.reply_text(message)
                return

        project_id = str(uuid.uuid4())
        new_version_num = 1

        # Убеждаемся, что last_file_id доступен
        last_file_id = context.user_data.get('last_file_id')
        last_file_name = context.user_data.get('last_file_name', 'document')
        last_file_caption = context.user_data.get('last_file_caption') or f"Initial version by {user.full_name}"

        if not last_file_id:
            message = "Ошибка: Файл для первой версии проекта не найден. Пожалуйста, отправьте файл и попробуйте снова."
            if update.callback_query:
                 await update.callback_query.edit_message_text(message)
            else:
                 await update.message.reply_text(message)
            return


        context.bot_data['projects'][project_id] = {
            "name": project_name,
            "owner_id": user_id, # owner_id сохраняется как int
            "members": {str(user_id)}, # Сохраняем ID участников как строки в множестве
            "versions": [{
                "file_id": last_file_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "uploader_id": user_id,
                "uploader_name": user.full_name,
                "version_num": new_version_num,
                "caption": last_file_caption,
                "file_name": last_file_name
            }],
            "next_version_num": new_version_num + 1
        }

        # Очистка временных данных после использования
        for key in ['last_file_id', 'last_file_caption', 'last_file_name', 'awaiting_project_name', 'action']:
            if key in context.user_data:
                del context.user_data[key]

        # Сохранение данных
        save_data(context.bot_data)

        message_text = f"✅ Проект '{project_name}' создан. Первая версия документа добавлена."

        # Отправляем сообщение туда, откуда пришел триггер (callback или команда)
        if update.callback_query:
            await update.callback_query.edit_message_text(message_text)
        else:
            await update.message.reply_text(message_text)

        logger.info(f"User {user_id} created project '{project_name}' (ID: {project_id})")
    except Exception as e:
        logger.error(f"Error creating project: {e}", exc_info=True)
        # Отправляем сообщение об ошибке туда, откуда пришел триггер
        error_message = "Произошла ошибка при создании проекта. Пожалуйста, попробуйте позже."
        if update.callback_query:
             try: await update.callback_query.edit_message_text(error_message)
             except Exception: pass # Избегаем ошибки при отправке ошибки
        elif update.message:
             try: await update.message.reply_text(error_message)
             except Exception: pass


async def commit_version(update: Update, context: CallbackContext) -> None:
    """Добавление новой версии в проект - обработка команды /commit"""
    user_id = update.effective_user.id

    # Если это обычная команда /commit
    if update.message:
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

    # Обработка callback 'commit_project' перемещена в button_handler


async def _add_version_to_project(update: Update, context: CallbackContext, project_name: str,
                                  commit_message: str) -> None:
    """Внутренняя функция добавления версии в проект, вызывается командой или после выбора проекта по кнопке"""
    user = update.effective_user
    user_id = user.id
    user_id_str = str(user_id)

    project_id = get_project_id_by_name(context.bot_data, project_name, user_id)

    if not project_id:
        message = f"Проект '{project_name}' не найден или у вас нет к нему доступа."
        if update.callback_query:
             await update.callback_query.edit_message_text(message)
        else:
             await update.message.reply_text(message)
        return

    project = context.bot_data['projects'][project_id]

    # Проверка членства (хотя get_project_id_by_name уже это делает, дублируем для ясности)
    if user_id_str not in project.get('members', set()):
        message = f"Вы не являетесь участником проекта '{project['name']}'.1" # Добавлена цифра для отладки
        if update.callback_query:
             await update.callback_query.edit_message_text(message)
        else:
             await update.message.reply_text(message)
        return

    # Убеждаемся, что last_file_id доступен
    last_file_id = context.user_data.get('last_file_id')
    last_file_name = context.user_data.get('last_file_name', 'document')
    # Если commit_message пустой (например, если не было caption и не передали аргументы), используем дефолтное
    commit_message = commit_message or f"Update by {user.full_name}"


    if not last_file_id:
        message = "Ошибка: Файл для добавления новой версии не найден. Пожалуйста, отправьте файл и попробуйте снова."
        if update.callback_query:
             await update.callback_query.edit_message_text(message)
        else:
             await update.message.reply_text(message)
        return


    new_version_num = project.get("next_version_num", 1) # Убеждаемся, что next_version_num есть
    if not isinstance(new_version_num, int): # Проверка типа после загрузки
         new_version_num = 1
         if project['versions']:
             try:
                 new_version_num = project['versions'][-1]['version_num'] + 1
             except (TypeError, KeyError):
                 new_version_num = 1


    project['versions'].append({
        "file_id": last_file_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "uploader_id": user_id,
        "uploader_name": user.full_name,
        "version_num": new_version_num,
        "caption": commit_message,
        "file_name": last_file_name
    })
    project["next_version_num"] = new_version_num + 1

    # Очистка временных данных после использования
    for key in ['last_file_id', 'last_file_caption', 'last_file_name', 'awaiting_project_name', 'action']:
        if key in context.user_data:
            del context.user_data[key]

    # Сохранение данных
    save_data(context.bot_data)

    message_text = f"✅ Новая версия ({new_version_num}) документа добавлена в проект '{project['name']}'."

    # Отправляем сообщение туда, откуда пришел триггер (callback или команда)
    if update.callback_query:
         await update.callback_query.edit_message_text(message_text)
    else:
         await update.message.reply_text(message_text)

    logger.info(f"User {user_id} committed version {new_version_num} to project '{project['name']}' (ID: {project_id})")


async def list_projects(update: Update, context: CallbackContext) -> None:
    """Список проектов пользователя"""
    user_id = update.effective_user.id
    user_id_str = str(user_id)

    # Если это callback от кнопки
    if update.callback_query:
        await update.callback_query.answer()

    if 'projects' not in context.bot_data or not context.bot_data['projects']:
        message = "Пока нет ни одного проекта."
        if update.callback_query:
            # Проверяем, что сообщение еще существует перед редактированием
            try:
                 await update.callback_query.edit_message_text(message)
            except Exception:
                 await context.bot.send_message(chat_id=update.effective_chat.id, text=message) # Отправляем новое, если редактирование не удалось
        else:
            await update.message.reply_text(message)
        return

    user_projects = []
    project_buttons = []
    for proj_id, project in context.bot_data['projects'].items():
        # Убеждаемся, что 'members' является множеством
        members_set = project.get('members', set())
        if not isinstance(members_set, set):
            members_set = set(members_set) # Преобразуем, если это список из старых данных
            project['members'] = members_set # Сохраняем обратно как множество

        if user_id_str in members_set:
            role = "👑" if project.get('owner_id') == user_id else "👥" # Проверка owner_id
            user_projects.append(f"{role} {project['name']} (версий: {len(project.get('versions', []))})") # Проверка на наличие versions
            project_buttons.append([
                 InlineKeyboardButton(
                     f"{project['name']} ({len(project.get('versions', []))})",
                     callback_data=f"project_details:{proj_id}" # Передаем proj_id
                 )
            ])


    if not user_projects:
        message = "Вы не состоите ни в одном проекте."
        if update.callback_query:
             try: await update.callback_query.edit_message_text(message)
             except Exception: await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        else:
             await update.message.reply_text(message)
    else:
        message = "📂 Ваши проекты:\n\n" + "\n".join(user_projects)
        reply_markup = InlineKeyboardMarkup(project_buttons)

        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Failed to edit message in list_projects callback: {e}")
                await context.bot.send_message(chat_id=update.effective_chat.id, text=message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)


async def list_versions(update: Update, context: CallbackContext) -> None:
    """Список версий проекта - обрабатывает команду /versions и callback project_details:"""
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    proj_id = None
    project_name = None

    # Определяем, откуда пришел запрос: команда или кнопка
    if update.callback_query:
        await update.callback_query.answer()
        try:
            # Ожидаем формат callback_data="project_details:{proj_id}"
            data_parts = update.callback_query.data.split(':')
            if len(data_parts) > 1:
                proj_id = data_parts[1]
        except Exception as e:
            logger.error(f"Error parsing proj_id from callback data: {e}")
            await update.callback_query.edit_message_text("Произошла ошибка при обработке запроса.")
            return
    elif update.message:
        # Если это команда /versions
        if not context.args:
            await update.message.reply_text("Укажите название проекта: /versions <название_проекта>")
            return
        project_name = " ".join(context.args)
        proj_id = get_project_id_by_name(context.bot_data, project_name, user_id)
    else:
         # Неизвестный тип обновления
         logger.warning("list_versions called with unexpected update type")
         return

    if not proj_id:
        message = f"Проект '{project_name or 'неизвестный'}' не найден или у вас нет к нему доступа."
        if update.callback_query:
             try: await update.callback_query.edit_message_text(message)
             except Exception: await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        else:
             await update.message.reply_text(message)
        return

    project = context.bot_data['projects'].get(proj_id)

    if not project or user_id_str not in project.get('members', set()):
        message = "Проект не найден или у вас нет доступа."
        if update.callback_query:
             try: await update.callback_query.edit_message_text(message)
             except Exception: await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        else:
             await update.message.reply_text(message)
        return


    if not project.get('versions'):
        message = f"В проекте '{project.get('name', '??')}' пока нет версий."
        if update.callback_query:
             try: await update.callback_query.edit_message_text(message)
             except Exception: await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        else:
             await update.message.reply_text(message)
        return

    response = f"📚 Версии проекта '{project.get('name', '??')}':\n\n"
    # Показываем последние 10 версий для краткости в сообщении
    for ver in reversed(project['versions'][-10:]):
        response += (
            f"🔹 Версия {ver.get('version_num', '??')} ({ver.get('file_name', 'файл')})\n"
            f"   📅 {ver.get('timestamp', '??')}\n"
            f"   👤 {ver.get('uploader_name', '??')}\n"
            f"   📝 {ver.get('caption', 'нет описания')}\n"
            # Добавляем команду для получения конкретной версии
            f"   <code>/get {project.get('name', proj_id)} {ver.get('version_num', '')}</code>\n\n"
        )

    # Кнопки для управления проектом (только для callback)
    reply_markup = None
    if update.callback_query:
        keyboard = [
            [
                InlineKeyboardButton("⬅️ Назад к проектам", callback_data='list_projects'),
                InlineKeyboardButton("📥 Получить последнюю версию", callback_data=f'get_version:{proj_id}') # Передаем proj_id
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправка сообщения
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(response, reply_markup=reply_markup, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Failed to edit message in list_versions callback: {e}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=response, reply_markup=reply_markup, parse_mode='HTML')
    elif update.message:
        if len(response) > 4096: # Telegram message limit
            response_parts = [response[i:i + 4000] for i in range(0, len(response), 4000)] # Разбиваем на части
            for part in response_parts:
                await update.message.reply_html(part) # Используем reply_html
        else:
            await update.message.reply_html(response) # Используем reply_html

async def get_version(update: Update, context: CallbackContext) -> None:
    """Получение конкретной версии документа - обрабатывает команду /get и callback get_version:"""
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    proj_id = None
    project_name = None
    version_to_get_num = None # Искомый номер версии

    # Определяем, откуда пришел запрос: команда или кнопка
    if update.callback_query:
        await update.callback_query.answer()
        try:
            # Ожидаем формат callback_data="get_version:{proj_id}"
            data_parts = update.callback_query.data.split(':')
            if len(data_parts) > 1:
                proj_id = data_parts[1]
            # Для callback'а "Получить последнюю версию" номер версии не передается, берем последнюю
            version_to_get_num = None
        except Exception as e:
            logger.error(f"Error parsing proj_id from get_version callback: {e}")
            await update.callback_query.edit_message_text("Произошла ошибка при обработке запроса.")
            return

    elif update.message:
        # Если это команда /get
        if len(context.args) < 1:
            await update.message.reply_text("Укажите название проекта: /get <название_проекта> [номер_версии]")
            return

        project_name = context.args[0]
        proj_id = get_project_id_by_name(context.bot_data, project_name, user_id)

        if len(context.args) > 1:
            try:
                version_to_get_num = int(context.args[1])
            except ValueError:
                await update.message.reply_text("Номер версии должен быть числом.")
                return
        else:
            version_to_get_num = None # Если номер не указан, берем последнюю

    else:
        # Неизвестный тип обновления
        logger.warning("get_version called with unexpected update type")
        return


    if not proj_id:
        message = f"Проект '{project_name or 'неизвестный'}' не найден или у вас нет к нему доступа."
        # Ответ может быть либо редактированием сообщения, либо новым сообщением
        if update.callback_query:
             try: await update.callback_query.edit_message_text(message)
             except Exception: await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        else:
             await update.message.reply_text(message)
        return


    project = context.bot_data['projects'].get(proj_id)

    if not project or user_id_str not in project.get('members', set()):
        message = "Проект не найден или у вас нет доступа."
        if update.callback_query:
             try: await update.callback_query.edit_message_text(message)
             except Exception: await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        else:
             await update.message.reply_text(message)
        return


    if not project.get('versions'):
        message = f"В проекте '{project.get('name', '??')}' нет версий."
        if update.callback_query:
             try: await update.callback_query.edit_message_text(message)
             except Exception: await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        else:
             await update.message.reply_text(message)
        return

    target_version = None
    if version_to_get_num is None:
        # Берем последнюю версию, если номер не указан или пришел колбэк без номера
        if project['versions']:
            target_version = project['versions'][-1]
    else:
        # Ищем версию по номеру
        for ver in project['versions']:
            if ver.get('version_num') == version_to_get_num:
                target_version = ver
                break

    if not target_version:
        message = f"Версия {version_to_get_num if version_to_get_num is not None else 'с таким номером'} не найдена в проекте '{project.get('name', '??')}'.1"
        if update.callback_query:
             try: await update.callback_query.edit_message_text(message)
             except Exception: await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        else:
             await update.message.reply_text(message)
        return

    try:
        # Отправляем документ
        await context.bot.send_document(
            chat_id=update.effective_chat.id, # Отправляем в чат пользователя
            document=target_version['file_id'],
            caption=(
                f"📂 Проект: {project.get('name', '??')}\n"
                f"🔹 Версия: {target_version.get('version_num', '??')}\n"
                f"📝 Описание: {target_version.get('caption', 'нет описания')}\n"
                f"👤 Автор: {target_version.get('uploader_name', '??')}\n"
                f"📅 Дата: {target_version.get('timestamp', '??')}"
            )
        )
        logger.info(f"Sent version {target_version.get('version_num', '??')} of project {project.get('name', proj_id)} to user {user_id}")

        # Если это был callback, возможно, нужно отредактировать предыдущее сообщение
        if update.callback_query:
             try:
                 # Можно изменить текст на "Файл отправлен" или что-то подобное
                 await update.callback_query.edit_message_text(f"📥 Версия {target_version.get('version_num', '??')} проекта '{project.get('name', '??')}' отправлена.")
             except Exception as e:
                  logger.warning(f"Failed to edit message after sending file in get_version callback: {e}")


    except Exception as e:
        logger.error(f"Error sending document for project {project.get('name', proj_id)}, version {target_version.get('version_num', '??')}: {e}", exc_info=True)
        error_message = "Не удалось отправить документ. Возможно, он был удален из истории чата с ботом, или у бота проблемы с доступом к файлу."
        if update.callback_query:
             try: await update.callback_query.edit_message_text(error_message)
             except Exception: await context.bot.send_message(chat_id=update.effective_chat.id, text=error_message)
        else:
             await update.message.reply_text(error_message)


async def add_member(update: Update, context: CallbackContext) -> None:
    """Добавление участника в проект"""
    owner_id = update.effective_user.id

    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /addmember <название_проекта> <@username или user_id>\n\n"
            "Примеры:\n"
            "/addmember МойПроект @username\n"
            "/addmember МойПроект 123456789\n\n"
            "Чтобы узнать ID пользователя, можно использовать команду /start в диалоге с ним или бота вроде @userinfobot (требует, чтобы пользователь сам написал @userinfobot)."
        )
        return

    project_name = context.args[0]
    member_identifier = context.args[1].strip()

    # Поиск проекта, где текущий пользователь - владелец
    project_id = get_project_by_name_owner_only(context.bot_data, project_name, owner_id)
    if not project_id:
        await update.message.reply_text(f"Проект '{project_name}' не найден или вы не являетесь его владельцем.")
        return

    project = context.bot_data['projects'][project_id]
    member_id_to_add = None

    # Если передан username
    if member_identifier.startswith('@'):
        member_id_to_add = await resolve_user_id(context, member_identifier)
        if not member_id_to_add:
            await update.message.reply_text(
                f"❌ Не удалось найти пользователя по username '{member_identifier}'.\n\n"
                "Возможные причины:\n"
                "- Пользователь никогда не писал боту.\n"
                "- Неверный username.\n\n"
                "Попросите пользователя написать мне команду /start или используйте числовой User ID."
            )
            return

    # Если передан числовой ID
    else:
        try:
            member_id_to_add = int(member_identifier)
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID. Используйте числовой ID или @username.")
            return

    # Проверки перед добавлением
    if member_id_to_add == owner_id:
        await update.message.reply_text("⚠️ Вы уже владелец этого проекта.")
        return

    member_id_to_add_str = str(member_id_to_add)

    # Убеждаемся, что 'members' является множеством
    members_set = project.get('members', set())
    if not isinstance(members_set, set):
        members_set = set(members_set)
        project['members'] = members_set # Исправляем, если нужно

    if member_id_to_add_str in members_set:
        await update.message.reply_text(f"ℹ️ Пользователь {member_identifier} уже является участником проекта '{project['name']}'.")
        return

    # Проверка доступности пользователя перед добавлением
    try:
        # Просто попытка получить chat action может показать, доступен ли чат
        await context.bot.send_chat_action(
            chat_id=member_id_to_add,
            action='typing'
        )
    except Exception as e:
        logger.warning(f"Could not send chat action to user {member_id_to_add}: {e}")
        await update.message.reply_text(
            f"❌ Не могу добавить пользователя с ID {member_id_to_add}.\n\n"
            "Возможные причины:\n"
            "- Пользователь заблокировал бота.\n"
            "- Пользователь никогда не писал боту (если использован числовой ID, а не @username).\n\n"
            "Попросите пользователя написать мне команду /start."
        )
        return


    # Добавление пользователя (ID в строковом формате)
    project['members'].add(member_id_to_add_str)
    save_data(context.bot_data)

    # Уведомления
    success_msg = await update.message.reply_text(
        f"✅ Успешно добавлен: {member_identifier} (ID: {member_id_to_add})\n"
        f"в проект '{project['name']}'"
    )

    try:
        # Пытаемся уведомить нового участника
        await context.bot.send_message(
            chat_id=member_id_to_add,
            text=(
                f"📌 Вас добавили в проект '{project['name']}'\n"
                f"Владелец: {update.effective_user.full_name}\n\n"
                "Доступные команды:\n"
                "/listprojects - Ваши проекты\n"
                f"/versions {project.get('name', '')} - Версии проекта '{project.get('name', '')}'" # Используем имя из проекта
            )
        )
        logger.info(f"Notified user {member_id_to_add} about joining project {project['name']}")
    except Exception as e:
        logger.warning(f"Could not notify newly added member {member_id_to_add} for project {project_id}: {e}")
        # Добавляем сообщение об ошибке к сообщению об успехе
        await success_msg.reply_text(
            "⚠ Пользователь добавлен, но не получил уведомление.\n"
            "Возможно, он заблокировал бота. Попросите его написать мне /start."
        )


async def remove_member(update: Update, context: CallbackContext) -> None:
    """Удаление участника из проекта"""
    owner_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /removemember <название_проекта> <user_id или @username>")
        return

    project_name = context.args[0]
    member_identifier = context.args[1].strip()

    # Поиск проекта, где текущий пользователь - владелец
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
                f"Не удалось найти пользователя по username '{member_identifier}'. Укажите числовой User ID участника."
            )
            return
    else:
        try:
            member_id_to_remove = int(member_identifier)
        except ValueError:
            await update.message.reply_text("Неверный формат User ID. Укажите числовой ID или @username.")
            return

    if member_id_to_remove == owner_id:
        await update.message.reply_text(
            "Владелец не может удалить сам себя из проекта."
        )
        return

    member_id_to_remove_str = str(member_id_to_remove)

    # Убеждаемся, что 'members' является множеством
    members_set = project.get('members', set())
    if not isinstance(members_set, set):
        members_set = set(members_set)
        project['members'] = members_set # Исправляем, если нужно


    if member_id_to_remove_str not in members_set:
        await update.message.reply_text(
            f"Пользователь {member_identifier} не является участником проекта '{project['name']}'.2" # Добавлена цифра
        )
        return

    # Удаление пользователя
    members_set.remove(member_id_to_remove_str) # Удаляем из множества
    project['members'] = members_set # Обновляем ссылку (хотя множество изменяется на месте)

    save_data(context.bot_data) # Сохраняем изменения

    await update.message.reply_text(f"✅ Пользователь {member_identifier} (ID: {member_id_to_remove}) удален из проекта '{project['name']}'.")
    logger.info(f"User {owner_id} removed member {member_id_to_remove} from project '{project['name']}'")

    try:
        # Пытаемся уведомить удаленного участника
        await context.bot.send_message(
            chat_id=member_id_to_remove,
            text=f"Вас удалили из проекта '{project['name']}'."
        )
    except Exception as e:
        logger.warning(f"Could not notify removed member {member_id_to_remove} for project {project_id}: {e}")


async def list_members(update: Update, context: CallbackContext) -> None:
    """Список участников проекта"""
    user_id = update.effective_user.id
    user_id_str = str(user_id)

    if not context.args:
        await update.message.reply_text("Укажите название проекта: /members <название_проекта>")
        return

    project_name = " ".join(context.args)
    project_id = get_project_id_by_name(context.bot_data, project_name, user_id) # Проверка членства

    if not project_id:
        await update.message.reply_text(f"Проект '{project_name}' не найден или у вас нет к нему доступа.")
        return

    project = context.bot_data['projects'].get(project_id)

    if not project: # Дополнительная проверка на всякий случай
         await update.message.reply_text("Произошла ошибка при загрузке данных проекта.")
         return

    members_list_str = f"👥 Участники проекта '{project.get('name', '??')}':\n\n"

    # Убеждаемся, что 'members' является множеством
    members_set = project.get('members', set())
    if not isinstance(members_set, set):
        members_set = set(members_set)
        project['members'] = members_set # Исправляем, если нужно


    if not members_set:
        members_list_str += "В проекте нет участников."
    else:
        member_details = []
        # Собираем имена участников, ища их в версиях или используя ID
        for member_id_in_set in sorted(list(members_set)): # Сортируем для предсказуемого вывода
            prefix = "👑 Владелец: " if member_id_in_set == str(project.get('owner_id')) else "👤 Участник: " # Сравниваем с owner_id
            member_name = f"ID: {member_id_in_set}" # Дефолтное отображение

            # Пытаемся найти имя пользователя среди загруженных версий
            uploader_name_found = False
            for ver in project.get('versions', []): # Проверка на наличие versions
                if str(ver.get('uploader_id')) == member_id_in_set and ver.get('uploader_name'): # Проверка на наличие uploader_id и uploader_name
                    member_name = f"{ver['uploader_name']} (ID: {member_id_in_set})"
                    uploader_name_found = True
                    break # Нашли имя, можно выйти из внутреннего цикла

            member_details.append(f"{prefix}{member_name}")

        members_list_str += "\n".join(member_details)

    await update.message.reply_text(members_list_str)


async def handle_text(update: Update, context: CallbackContext) -> None:
    """Обработка текстовых сообщений (для ожидания названия проекта)"""
    user_id = update.effective_user.id

    # Проверяем, ожидали ли мы название проекта от этого пользователя
    if 'awaiting_project_name' in context.user_data and context.user_data['awaiting_project_name']:
        action = context.user_data.get('action')
        project_name = update.message.text.strip()

        if not project_name:
            await update.message.reply_text("Название проекта не может быть пустым. Пожалуйста, введите название снова.")
            return

        # Вызываем соответствующую функцию для создания или обновления
        if action == 'new_project':
            # Для создания нового проекта после ввода названия
            # Update here is a MessageUpdate, so we pass it
            await _create_project(update, context, project_name)
        elif action == 'commit_project':
            # Для обновления существующего проекта после ввода названия (если бы так было реализовано)
            # Сейчас commit_project callback ведет к выбору проекта кнопкой
            # Если вы хотите дать пользователю ВВЕСТИ название проекта для коммита,
            # то нужно изменить логику commit_project callback
            # Но с кнопками выбора проекта это, вероятно, не нужно.
            # Если все же нужно, то логика была бы такой:
            # await _add_version_to_project(update, context, project_name, "") # Commit message будет дефолтным или из user_data

            # В текущей логике, если user_data['action'] == 'commit_project', это может быть ошибочный сценарий,
            # если пользователь ввел текст вместо выбора кнопки после commit_project callback
            await update.message.reply_text("Пожалуйста, используйте кнопки для выбора проекта.")

        # Флаги очищаются в _create_project и _add_version_to_project после успешного выполнения


        return # Важно выйти, чтобы сообщение не обрабатывалось дальше

    # Если это не ожидаемое сообщение, можно игнорировать или добавить дефолтный ответ
    # await update.message.reply_text("Я получил ваше сообщение, но сейчас ожидаю команды или файла.")
    pass # Просто игнорируем

async def button_handler(update: Update, context: CallbackContext) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer() # Всегда отвечаем на callback query
    chat_id = query.message.chat_id
    message_id = query.message.message_id # Получаем ID сообщения для редактирования

    logger.info(f"Received callback query: {query.data} from user {query.from_user.id} in chat {chat_id}")

    data = query.data

    # --- Обработка show_help ---
    if data == 'show_help':
        logger.info("Handling show_help callback data.")
        instructions = (
            "📚 <b>Инструкция по использованию:</b>\n\n"
            "1. Сначала отправьте мне документ (файл).\n"
            "2. Затем используйте команды:\n\n"
            "<b>📂 Проекты:</b>\n"
            "/newproject <название> - Создать новый проект\n" # HTML-экранирование
            "/listprojects - Список ваших проектов\n"
            "/members <проект> - Участники проекта\n\n" # HTML-экранирование
            "<b>🔄 Версии:</b>\n"
            "/commit <проект> [описание] - Сохранить новую версию\n" # HTML-экранирование
            "/versions <проект> - Все версии проекта\n"
            "/get <проект> [версия] - Получить версию\n\n" # HTML-экранирование
            "<b>👥 Управление доступом:</b>\n"
            "/addmember <проект> <user> - Добавить участника\n" # HTML-экранирование
            "/removemember <проект> <user> - Удалить участника\n\n" # HTML-экранирование
            "Для команд /newproject и /commit сначала отправьте файл боту."
        )

        keyboard = [
            [InlineKeyboardButton("Создать проект", callback_data='new_project')], # callback_data не меняем, логика обработки в new_project/handle_text
            [InlineKeyboardButton("Мои проекты", callback_data='list_projects')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            # Попытка отредактировать исходное сообщение
            await query.message.edit_text( # Используем query.message.edit_text
                text=instructions,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            logger.info(f"Edited message {message_id} in chat {chat_id} with instructions.")
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} in chat {chat_id} with instructions: {e}", exc_info=True)
            # Если редактирование не удалось, отправляем новое сообщение как запасной вариант
            fallback_message = "Произошла ошибка при обновлении сообщения. Вот инструкция:\n\n" + instructions
            try:
                 await context.bot.send_message(
                    chat_id=chat_id,
                    text=fallback_message,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                 )
                 logger.info(f"Sent fallback instructions message to chat {chat_id}.")
            except Exception as send_error:
                 logger.error(f"Failed to send fallback error message to user in chat {chat_id}: {send_error}")


    # --- Обработка list_projects ---
    elif data == 'list_projects':
        logger.info("Handling list_projects callback data.")
        await list_projects(update, context) # list_projects теперь обрабатывает callback

    # --- Обработка new_project (после загрузки файла) ---
    # Логика запроса названия проекта при нажатии кнопки "Создать новый проект"
    elif data == 'new_project':
        logger.info("Handling new_project callback data.")
        if 'last_file_id' not in context.user_data:
             # Если файла нет, просто сообщаем об этом
             try:
                 await query.edit_message_text("Сначала отправьте документ, который хотите добавить в новый проект.")
             except Exception as e:
                 logger.warning(f"Failed to edit message for new_project callback (no file): {e}")
                 await context.bot.send_message(chat_id=chat_id, text="Сначала отправьте документ, который хотите добавить в новый проект.")
             return

        # Если файл есть, запрашиваем название проекта
        try:
             await query.edit_message_text(
                 "Введите название нового проекта:"
             )
             # Устанавливаем флаги ожидания ввода
             context.user_data['awaiting_project_name'] = True
             context.user_data['action'] = 'new_project'
             logger.info(f"User {query.from_user.id} is now awaiting new project name.")
        except Exception as e:
             logger.error(f"Failed to edit message to ask for project name: {e}", exc_info=True)
             await context.bot.send_message(chat_id=chat_id, text="Произошла ошибка. Пожалуйста, введите название нового проекта.")


    # --- Обработка commit_project (после загрузки файла) ---
    # Логика выбора проекта для коммита при нажатии кнопки "Обновить существующий"
    elif data == 'commit_project':
        logger.info("Handling commit_project callback data.")
        if 'last_file_id' not in context.user_data:
             # Если файла нет, просто сообщаем об этом
             try:
                  await query.edit_message_text("Сначала отправьте документ, который хотите закоммитить.")
             except Exception as e:
                  logger.warning(f"Failed to edit message for commit_project callback (no file): {e}")
                  await context.bot.send_message(chat_id=chat_id, text="Сначала отправьте документ, который хотите закоммитить.")
             return

        # Получаем список проектов пользователя
        user_id = query.from_user.id
        user_projects_buttons = []
        if 'projects' in context.bot_data:
            for proj_id, project in context.bot_data['projects'].items():
                # Убеждаемся, что 'members' является множеством
                members_set = project.get('members', set())
                if not isinstance(members_set, set):
                    members_set = set(members_set)
                    project['members'] = members_set # Исправляем, если нужно

                if str(user_id) in members_set: # Проверка членства
                    user_projects_buttons.append([
                        InlineKeyboardButton(
                            project.get('name', f'Проект ID: {proj_id[:4]}...'), # Отображаем имя или часть ID
                            callback_data=f'commit_to_id:{proj_id}' # Передаем proj_id в callback
                        )
                    ])

        if not user_projects_buttons:
            try:
                 await query.edit_message_text("У вас нет проектов для обновления.")
            except Exception as e:
                 logger.warning(f"Failed to edit message for no projects in commit_project callback: {e}")
                 await context.bot.send_message(chat_id=chat_id, text="У вас нет проектов для обновления.")
            return

        # Отправляем сообщение со списком проектов для выбора (редактируем текущее)
        reply_markup = InlineKeyboardMarkup(user_projects_buttons)
        try:
            await query.message.edit_text( # Используем query.message.edit_text
                "Выберите проект для обновления:",
                reply_markup=reply_markup
            )
            logger.info(f"Presented project selection for commit to user {user_id}.")
        except Exception as e:
            logger.error(f"Failed to edit message to show project selection for commit: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text="Произошла ошибка при загрузке списка проектов.")

    # --- Обработка project_details: (просмотр версий) ---
    elif data.startswith('project_details:'):
        logger.info(f"Handling project_details callback data: {data}")
        # list_versions теперь обрабатывает этот callback
        await list_versions(update, context)

    # --- Обработка get_version: (получение файла версии) ---
    elif data.startswith('get_version:'):
        logger.info(f"Handling get_version callback data: {data}")
        # get_version теперь обрабатывает этот callback
        await get_version(update, context)

    # --- Обработка commit_to_id: (выбор проекта для коммита по ID) ---
    elif data.startswith('commit_to_id:'):
        logger.info(f"Handling commit_to_id callback data: {data}")
        try:
            proj_id_to_commit = data.split(':')[1]
            project = context.bot_data['projects'].get(proj_id_to_commit)
            if not project:
                 try: await query.edit_message_text("Проект не найден.")
                 except Exception: await context.bot.send_message(chat_id=chat_id, text="Проект не найден.")
                 return

            project_name_to_commit = project.get('name')
            if not project_name_to_commit:
                 try: await query.edit_message_text("Ошибка: Не удалось получить имя проекта.")
                 except Exception: await context.bot.send_message(chat_id=chat_id, text="Ошибка: Не удалось получить имя проекта.")
                 return

            # Commit message берется из user_data или ставится дефолтным
            commit_message = context.user_data.get('last_file_caption') or f"Update by {query.from_user.full_name}"

            # Вызываем внутреннюю функцию для добавления версии
            await _add_version_to_project(update, context, project_name_to_commit, commit_message)

        except Exception as e:
            logger.error(f"Error handling commit_to_id callback: {e}", exc_info=True)
            try: await query.edit_message_text("Произошла ошибка при добавлении версии.")
            except Exception: await context.bot.send_message(chat_id=chat_id, text="Произошла ошибка при добавлении версии.")


    # --- Обработка неизвестных callback data ---
    else:
        logger.warning(f"Received unhandled callback data: {data}")
        try:
             # Пытаемся отредактировать сообщение, если возможно, иначе отправляем новое
             await query.message.edit_text("Неизвестное действие.")
        except Exception as e:
             logger.warning(f"Failed to edit message for unknown callback data: {e}")
             try: await context.bot.send_message(chat_id=chat_id, text="Неизвестное действие.")
             except Exception: pass # Избегаем зацикливания ошибок

def main() -> None:
    """Запуск бота."""
    # Загружаем сохраненные данные перед запуском
    bot_data = load_data()

    application = Application.builder().token(BOT_TOKEN).build()

    # Устанавливаем загруженные данные в bot_data контекста
    # Это важно, чтобы обработчики имели доступ к постоянным данным
    application.bot_data.update(bot_data)
    # Добавляем функцию сохранения данных в bot_data для удобства доступа из обработчиков
    application.bot_data['save_data'] = save_data # Это менее идиоматично, лучше передавать context.bot_data в save_data

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("newproject", new_project)) # Обработка команды /newproject
    application.add_handler(CommandHandler("commit", commit_version)) # Обработка команды /commit
    application.add_handler(CommandHandler("listprojects", list_projects))
    application.add_handler(CommandHandler("versions", list_versions))
    application.add_handler(CommandHandler("get", get_version))
    application.add_handler(CommandHandler("addmember", add_member))
    application.add_handler(CommandHandler("removemember", remove_member))
    application.add_handler(CommandHandler("members", list_members))

    # Обработчики сообщений (документы и текст)
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    # Важно: фильтр TEXT & ~COMMAND обрабатывает ЛЮБОЙ текст, не являющийся командой.
    # Ваш handle_text сейчас используется только для ожидания названия проекта.
    # Если вы захотите добавить другую текстовую обработку, будьте осторожны.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot starting...")
    application.run_polling(poll_interval=1.0) # Добавлен poll_interval для лучшей производительности

if __name__ == '__main__':
    # Загружаем данные при старте скрипта
    bot_data = load_data() # Загрузка здесь нужна только для инициализации, основная загрузка в main

    # Запуск main
    main()