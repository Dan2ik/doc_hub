import logging
import uuid
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен вашего бота (ЗАМЕНИТЕ НА ВАШ НОВЫЙ ТОКЕН!)
BOT_TOKEN = "7990174156:AAECQ7djna9rkR8AhZYL37NiL4-JkPu1bi8"


# --- Вспомогательные функции ---

def get_project_id_by_name(bot_data, project_name, user_id):
    if 'projects' not in bot_data:
        return None
    for proj_id, project in bot_data['projects'].items():
        if project['name'].lower() == project_name.lower() and user_id in project['members']:
            return proj_id
    return None


def get_project_by_name_owner_only(bot_data, project_name, owner_id):
    if 'projects' not in bot_data:
        return None
    for proj_id, project in bot_data['projects'].items():
        if project['name'].lower() == project_name.lower() and project['owner_id'] == owner_id:
            return proj_id
    return None


# --- Обработчики команд ---

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    welcome_message = rf"Привет, {user.mention_html()}! Я твой бот для версионирования документов." \
                      rf"\n\nВот инструкция по использованию:"

    await update.message.reply_html(welcome_message)

    instructions = (
        "Сначала отправьте мне документ (файл). Затем используйте команды:\n"
        "/newproject <название_проекта> - Создать новый проект из последнего отправленного документа.\n"
        "/commit <название_проекта> [описание_изменений] - Сохранить последнюю отправленную версию документа в существующий проект.\n"
        "/listprojects - Показать список ваших проектов и проектов, где вы участник.\n"
        "/versions <название_проекта> - Показать все версии документа в проекте.\n"
        "/get <название_проекта> [номер_версии] - Получить конкретную версию документа (если номер не указан - последнюю).\n"
        "/addmember <название_проекта> <user_id или @username> - Добавить пользователя в проект (только владелец).\n"
        "/removemember <название_проекта> <user_id или @username> - Удалить пользователя из проекта (только владелец).\n"
        "/members <название_проекта> - Показать участников проекта.\n\n"
        "Важно: для команд /newproject и /commit сначала отправьте файл боту, он запомнит его.\n\n"
        "Вы также можете использовать команду /help в любой момент для повторного вызова этой инструкции."
    )
    await update.message.reply_text(instructions)


async def help_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        "Сначала отправьте мне документ (файл). Затем используйте команды:\n"
        "/newproject <название_проекта> - Создать новый проект из последнего отправленного документа.\n"
        "/commit <название_проекта> [описание_изменений] - Сохранить последнюю отправленную версию документа в существующий проект.\n"
        "/listprojects - Показать список ваших проектов и проектов, где вы участник.\n"
        "/versions <название_проекта> - Показать все версии документа в проекте.\n"
        "/get <название_проекта> [номер_версии] - Получить конкретную версию документа (если номер не указан - последнюю).\n"
        "/addmember <название_проекта> <user_id или @username> - Добавить пользователя в проект (только владелец).\n"
        "/removemember <название_проекта> <user_id или @username> - Удалить пользователя из проекта (только владелец).\n"
        "/members <название_проекта> - Показать участников проекта.\n\n"
        "Важно: для команд /newproject и /commit сначала отправьте файл боту, он запомнит его."
    )


async def handle_document(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    context.user_data['last_file_id'] = update.message.document.file_id
    context.user_data['last_file_name'] = update.message.document.file_name
    context.user_data['last_file_caption'] = update.message.caption or ""

    logger.info(
        f"User {user_id} uploaded file {update.message.document.file_name} with id {update.message.document.file_id}")
    await update.message.reply_text(
        f"Файл '{update.message.document.file_name}' получен. Теперь вы можете:\n"
        f"- Создать новый проект: /newproject <название_проекта>\n"
        f"- Обновить существующий: /commit <название_проекта> [описание]"
    )


async def new_project(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if 'last_file_id' not in context.user_data:
        await update.message.reply_text("Сначала отправьте документ, который хотите добавить в новый проект.")
        return

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите название проекта: /newproject <название_проекта>")
        return

    project_name = " ".join(context.args)

    if 'projects' not in context.bot_data:
        context.bot_data['projects'] = {}

    for proj_data in context.bot_data['projects'].values():
        if proj_data['name'].lower() == project_name.lower() and proj_data['owner_id'] == user_id:
            await update.message.reply_text(f"Проект с названием '{project_name}' уже существует у вас.")
            return

    project_id = str(uuid.uuid4())
    new_version_num = 1

    initial_caption = context.user_data.get(
        'last_file_caption') or f"Initial version by {update.effective_user.full_name}"

    context.bot_data['projects'][project_id] = {
        "name": project_name,
        "owner_id": user_id,
        "members": {user_id},
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

    del context.user_data['last_file_id']
    if 'last_file_caption' in context.user_data:
        del context.user_data['last_file_caption']
    if 'last_file_name' in context.user_data:
        del context.user_data['last_file_name']

    await update.message.reply_text(
        f"Проект '{project_name}' (ID: {project_id[:8]}) создан. Первая версия документа добавлена.")
    logger.info(f"User {user_id} created project '{project_name}' (ID: {project_id})")


async def commit_version(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if 'last_file_id' not in context.user_data:
        await update.message.reply_text("Сначала отправьте документ, который хотите закоммитить.")
        return

    if not context.args:
        await update.message.reply_text("Укажите название проекта: /commit <название_проекта> [описание]")
        return

    project_name_arg = context.args[0]
    commit_message_from_args = " ".join(context.args[1:])
    commit_message_from_caption = context.user_data.get('last_file_caption')

    if commit_message_from_args:
        commit_message = commit_message_from_args
    elif commit_message_from_caption:
        commit_message = commit_message_from_caption
    else:
        commit_message = f"Update by {update.effective_user.full_name}"

    project_id = get_project_id_by_name(context.bot_data, project_name_arg, user_id)

    if not project_id:
        await update.message.reply_text(f"Проект '{project_name_arg}' не найден или у вас нет к нему доступа.")
        return

    project = context.bot_data['projects'][project_id]

    if user_id not in project['members']:
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

    del context.user_data['last_file_id']
    if 'last_file_caption' in context.user_data:
        del context.user_data['last_file_caption']
    if 'last_file_name' in context.user_data:
        del context.user_data['last_file_name']

    await update.message.reply_text(
        f"Новая версия ({new_version_num}) документа добавлена в проект '{project['name']}'.")
    logger.info(f"User {user_id} committed version {new_version_num} to project '{project['name']}' (ID: {project_id})")


async def list_projects(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if 'projects' not in context.bot_data or not context.bot_data['projects']:
        await update.message.reply_text("Пока нет ни одного проекта.")
        return

    user_projects = []
    for proj_id, project in context.bot_data['projects'].items():
        if user_id in project['members']:
            role = "(Владелец)" if project['owner_id'] == user_id else "(Участник)"
            user_projects.append(f"- {project['name']} {role} (ID: {proj_id[:8]})")

    if not user_projects:
        await update.message.reply_text("Вы не состоите ни в одном проекте.")
    else:
        await update.message.reply_text("Ваши проекты и проекты с вашим участием:\n" + "\n".join(user_projects))


async def list_versions(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
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
    user_id = update.effective_user.id
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
            caption=f"Проект: {project['name']}\nВерсия: {target_version['version_num']}\nФайл: {target_version['file_name']}\nОписание: {target_version['caption']}\nОт: {target_version['timestamp']}"
        )
        logger.info(f"Sent version {target_version['version_num']} of project {project['name']} to user {user_id}")
    except Exception as e:
        logger.error(f"Error sending document for project {project_id}, version {target_version['version_num']}: {e}")
        await update.message.reply_text(
            "Не удалось отправить документ. Возможно, он был удален из истории чата с ботом, или у бота проблемы с доступом к файлу.")


async def add_member(update: Update, context: CallbackContext) -> None:
    owner_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /addmember <название_проекта> <user_id или @username>")
        return

    project_name = context.args[0]
    member_identifier = context.args[1]

    project_id = get_project_by_name_owner_only(context.bot_data, project_name, owner_id)
    if not project_id:
        await update.message.reply_text(f"Проект '{project_name}' не найден или вы не являетесь его владельцем.")
        return

    project = context.bot_data['projects'][project_id]

    member_id_to_add = None
    if member_identifier.startswith('@'):
        await update.message.reply_text(
            f"Для добавления по @username ({member_identifier}) этот пользователь должен был ранее написать боту. "
            "Надежнее указать его числовой User ID."
        )
        return
    else:
        try:
            member_id_to_add = int(member_identifier)
        except ValueError:
            await update.message.reply_text("Неверный формат User ID. Укажите числовой ID.")
            return

    if member_id_to_add == owner_id:
        await update.message.reply_text("Вы уже являетесь владельцем и участником этого проекта.")
        return

    if member_id_to_add in project['members']:
        await update.message.reply_text(
            f"Пользователь {member_id_to_add} уже является участником проекта '{project['name']}'.")
        return

    project['members'].add(member_id_to_add)
    await update.message.reply_text(f"Пользователь {member_id_to_add} добавлен в проект '{project['name']}'.")
    logger.info(f"User {owner_id} added member {member_id_to_add} to project '{project['name']}'")

    try:
        await context.bot.send_message(
            chat_id=member_id_to_add,
            text=f"Вас добавили в проект '{project['name']}' (владелец: {update.effective_user.full_name})."
                 f"\nИспользуйте /listprojects, чтобы увидеть его."
        )
    except Exception as e:
        logger.warning(f"Could not notify new member {member_id_to_add} for project {project_id}: {e}")


async def remove_member(update: Update, context: CallbackContext) -> None:
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
        await update.message.reply_text(
            "Для удаления по @username, пожалуйста, используйте числовой User ID участника.")
        return
    else:
        try:
            member_id_to_remove = int(member_identifier)
        except ValueError:
            await update.message.reply_text("Неверный формат User ID. Укажите числовой ID.")
            return

    if member_id_to_remove == owner_id:
        await update.message.reply_text(
            "Владелец не может удалить сам себя из проекта. Если хотите передать права или удалить проект, это потребует других команд (пока не реализовано).")
        return

    if member_id_to_remove not in project['members']:
        await update.message.reply_text(
            f"Пользователь {member_id_to_remove} не является участником проекта '{project['name']}'.")
        return

    project['members'].remove(member_id_to_remove)
    await update.message.reply_text(f"Пользователь {member_id_to_remove} удален из проекта '{project['name']}'.")
    logger.info(f"User {owner_id} removed member {member_id_to_remove} from project '{project['name']}'")

    try:
        await context.bot.send_message(
            chat_id=member_id_to_remove,
            text=f"Вас удалили из проекта '{project['name']}'."
        )
    except Exception as e:
        logger.warning(f"Could not notify removed member {member_id_to_remove} for project {project_id}: {e}")


async def list_members(update: Update, context: CallbackContext) -> None:
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
    members_list_str = f"Участники проекта '{project['name']}':\n"

    member_details = []
    for member_id_in_set in project['members']:
        prefix = "(Владелец) " if member_id_in_set == project['owner_id'] else ""
        member_name = f"ID: {member_id_in_set}"

        uploader_found = False
        for ver in project['versions']:
            if ver['uploader_id'] == member_id_in_set:
                member_name = f"{ver['uploader_name']} (ID: {member_id_in_set})"
                uploader_found = True
                break

        member_details.append(f"- {prefix}{member_name}")

    if not member_details:
        members_list_str += "В проекте нет участников (это ошибка, свяжитесь с администратором)."
    else:
        members_list_str += "\n".join(sorted(member_details))

    await update.message.reply_text(members_list_str)


def main() -> None:
    """Запуск бота."""
    application = Application.builder().token(BOT_TOKEN).build()

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

    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot started...")
    application.run_polling()


if __name__ == '__main__':
    main()