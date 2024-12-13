import logging
import os
import json
import re
import requests
from dotenv import load_dotenv
from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler
)
from typing import Dict
from collections import defaultdict, Counter

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')

if not TELEGRAM_TOKEN or not OPENWEATHER_API_KEY:
    raise ValueError("Пожалуйста, установите TELEGRAM_TOKEN и OPENWEATHER_API_KEY в .env файле.")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

LANGUAGE_FILES_PATH = os.path.join(os.getcwd(), 'languages')
IMAGES_PATH = os.path.join(os.getcwd(), 'images')

SUPPORTED_LANGUAGES = ['ru', 'en', 'es']

user_settings: Dict[int, Dict] = {}


def load_languages() -> Dict[str, Dict]:
    languages = {}
    for lang in SUPPORTED_LANGUAGES:
        try:
            with open(os.path.join(LANGUAGE_FILES_PATH, f"{lang}.json"), 'r', encoding='utf-8') as file:
                languages[lang] = json.load(file)
        except FileNotFoundError:
            logger.error(f"Файл языка для '{lang}' не найден.")
    return languages


LANGUAGES = load_languages()


def get_user_setting(user_id: int) -> Dict:
    return user_settings.get(user_id, {'language': 'ru'})


def set_user_setting(user_id: int, setting_key: str, value):
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id][setting_key] = value


def get_weather_emoji(weather_id: int) -> str:
    if 200 <= weather_id < 300:
        return "⛈️"
    elif 300 <= weather_id < 400:
        return "🌦️"
    elif 500 <= weather_id < 600:
        return "🌧️"
    elif 600 <= weather_id < 700:
        return "❄️"
    elif 700 <= weather_id < 800:
        return "🌫️"
    elif weather_id == 800:
        return "☀️"
    elif 800 < weather_id < 900:
        return "☁️"
    else:
        return "🌈"


def get_weather_image(weather_id: int) -> str:
    if 200 <= weather_id < 300:
        return 'thunderstorm.png'
    elif 300 <= weather_id < 400:
        return 'drizzle.png'
    elif 500 <= weather_id < 600:
        return 'rain.png'
    elif 600 <= weather_id < 700:
        return 'snow.png'
    elif 700 <= weather_id < 800:
        return 'mist.png'
    elif weather_id == 800:
        return 'clear.png'
    elif 800 < weather_id < 900:
        return 'clouds.png'
    else:
        return 'default.png'


WEATHER, FORECAST, LOCATION = range(3)


def get_language_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Русский", callback_data='ru')],
        [InlineKeyboardButton("English", callback_data='en')],
        [InlineKeyboardButton("Español", callback_data='es')]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    language = get_user_setting(user_id)['language']
    welcome_message = LANGUAGES.get(language, LANGUAGES['ru']).get('welcome', LANGUAGES['ru']['welcome']).format(
        name=user.first_name)
    await update.message.reply_text(welcome_message, reply_markup=ForceReply(selective=True))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    help_text = LANGUAGES.get(language, LANGUAGES['ru']).get('help', LANGUAGES['ru']['help'])
    await update.message.reply_text(help_text)


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    choose_language_text = LANGUAGES.get(language, LANGUAGES['ru']).get('choose_language', 'Please choose a language:')
    await update.message.reply_text(choose_language_text, reply_markup=get_language_keyboard())


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = query.data
    user_id = query.from_user.id
    if lang in LANGUAGES:
        set_user_setting(user_id, 'language', lang)
        language_name = {
            'ru': 'Русский',
            'en': 'English',
            'es': 'Español'
        }.get(lang, lang)
        success_message = LANGUAGES.get(lang, LANGUAGES['ru']).get('set_language_success',
                                                                   LANGUAGES['ru']['set_language_success']).format(
            language=language_name)
        await query.edit_message_text(success_message)
    else:
        language = get_user_setting(user_id)['language']
        invalid_message = LANGUAGES.get(language, LANGUAGES['ru']).get('invalid_language',
                                                                       LANGUAGES['ru']['invalid_language'])
        await query.edit_message_text(invalid_message)


def validate_city_name(city: str) -> bool:
    pattern = re.compile(r"^(?!\s)(?!.*\s$)(?!.*\s{2})[A-Za-zА-Яа-яЁё\-]{2,}(?:\s[A-Za-zА-Яа-яЁё\-]{2,})*$")
    return bool(pattern.match(city))


def get_weather(city: str, language: str = 'ru') -> Dict:
    try:
        url = 'http://api.openweathermap.org/data/2.5/weather'
        params = {
            'q': city,
            'appid': OPENWEATHER_API_KEY,
            'units': 'metric',
            'lang': language
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Ошибка при запросе погоды: {e}")
        return {'cod': 'error', 'message': str(e)}


def get_forecast(city: str, language: str = 'ru') -> Dict:
    try:
        url = 'http://api.openweathermap.org/data/2.5/forecast'
        params = {
            'q': city,
            'appid': OPENWEATHER_API_KEY,
            'units': 'metric',
            'lang': language
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Ошибка при запросе прогноза погоды: {e}")
        return {'cod': 'error', 'message': str(e)}


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    please_enter_city = LANGUAGES.get(language, LANGUAGES['ru']).get('please_enter_city',
                                                                     LANGUAGES['ru']['please_enter_city'])
    await update.message.reply_text(
        please_enter_city,
        reply_markup=ForceReply(selective=True)
    )
    return WEATHER


async def forecast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    please_enter_city = LANGUAGES.get(language, LANGUAGES['ru']).get('please_enter_city',
                                                                     LANGUAGES['ru']['please_enter_city'])
    await update.message.reply_text(
        please_enter_city,
        reply_markup=ForceReply(selective=True)
    )
    return FORECAST


async def location_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    send_location_text = LANGUAGES.get(language, LANGUAGES['ru']).get('send_location', 'Please send your location.')
    await update.message.reply_text(send_location_text, reply_markup=ForceReply(selective=True))
    return LOCATION


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    location = update.message.location
    if location:
        try:
            url = 'http://api.openweathermap.org/geo/1.0/reverse'
            params = {
                'lat': location.latitude,
                'lon': location.longitude,
                'limit': 1,
                'appid': OPENWEATHER_API_KEY
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            geo_data = response.json()
            if geo_data:
                city = geo_data[0]['name']
                weather_data = get_weather(city, language)
                if weather_data.get('cod') in [200, "200"]:
                    name = weather_data['name']
                    country = weather_data['sys']['country']
                    weather_desc = weather_data['weather'][0]['description']
                    temp = weather_data['main']['temp']
                    feels_like = weather_data['main']['feels_like']
                    humidity = weather_data['main']['humidity']
                    wind_speed = weather_data['wind']['speed']
                    weather_id = weather_data['weather'][0]['id']
                    emoji = get_weather_emoji(weather_id)

                    image_file = get_weather_image(weather_id)
                    image_path = os.path.join(IMAGES_PATH, image_file)

                    response_message = (
                        f"{emoji} *Погода в {name}, {country}:*\n"
                        f"• 🌡️ *Температура:* {temp}°C (ощущается как {feels_like}°C)\n"
                        f"• 💧 *Влажность:* {humidity}%\n"
                        f"• 💨 *Скорость ветра:* {wind_speed} м/с\n"
                        f"• 🌥️ *Описание:* {weather_desc.capitalize()}\n"
                    )

                    if os.path.exists(image_path):
                        with open(image_path, 'rb') as photo:
                            await update.message.reply_photo(
                                photo=photo,
                                caption=response_message,
                                parse_mode='Markdown'
                            )
                    else:
                        await update.message.reply_text(response_message, parse_mode='Markdown')
                else:
                    not_found_message = LANGUAGES.get(language, LANGUAGES['ru']).get('weather_not_found',
                                                                                     LANGUAGES['ru'][
                                                                                         'weather_not_found']).format(
                        city=city)
                    await update.message.reply_text(not_found_message)
            else:
                weather_not_found_msg = LANGUAGES.get(language, LANGUAGES['ru']).get('weather_not_found',
                                                                                     'Не удалось определить город по вашей геолокации.').format(
                    city='неизвестно')
                await update.message.reply_text(weather_not_found_msg)
        except requests.RequestException as e:
            logger.error(f"Ошибка при обратном геокодировании: {e}")
            api_error_msg = LANGUAGES.get(language, LANGUAGES['ru']).get('api_error',
                                                                         'Произошла ошибка при получении данных. Пожалуйста, попробуйте позже.')
            await update.message.reply_text(api_error_msg)
    else:
        invalid_location_msg = LANGUAGES.get(language, LANGUAGES['ru']).get('invalid_location',
                                                                            'Неверная геолокация. Пожалуйста, попробуйте снова.')
        await update.message.reply_text(invalid_location_msg)
    return ConversationHandler.END


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    about_text = LANGUAGES.get(language, LANGUAGES['ru']).get('about', 'Информация о боте недоступна.')
    await update.message.reply_text(about_text)


async def handle_weather(update: Update, context: ContextTypes.DEFAULT_TYPE, is_forecast: bool) -> int:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    city = update.message.text.strip()

    if not validate_city_name(city):
        invalid_city_msg = LANGUAGES.get(language, LANGUAGES['ru']).get('invalid_city',
                                                                        'Неверное название города. Пожалуйста, попробуйте снова.')
        await update.message.reply_text(invalid_city_msg)
        return ConversationHandler.END

    if is_forecast:
        data = get_forecast(city, language)
        not_found_message = LANGUAGES.get(language, LANGUAGES['ru']).get('forecast_not_found',
                                                                         LANGUAGES['ru']['forecast_not_found']).format(
            city=city)
    else:
        data = get_weather(city, language)
        not_found_message = LANGUAGES.get(language, LANGUAGES['ru']).get('weather_not_found',
                                                                         LANGUAGES['ru']['weather_not_found']).format(
            city=city)

    if data.get('cod') not in [200, "200"]:
        if data.get('cod') == 'error':
            api_error_msg = LANGUAGES.get(language, LANGUAGES['ru']).get('api_error',
                                                                         'Произошла ошибка при получении данных. Пожалуйста, попробуйте позже.')
            await update.message.reply_text(api_error_msg)
        else:
            await update.message.reply_text(not_found_message)
        return ConversationHandler.END

    try:
        if is_forecast:
            city_name = data['city']['name']
            country = data['city']['country']
            forecast_list = data['list']
            message = f"📅 *Прогноз погоды в {city_name}, {country} на неделю:*\n\n"

            daily_forecast = defaultdict(list)
            for entry in forecast_list:
                date = entry['dt_txt'].split(' ')[0]
                daily_forecast[date].append(entry)

            for date, entries in daily_forecast.items():
                temps = [e['main']['temp'] for e in entries]
                descriptions = [e['weather'][0]['description'] for e in entries]
                weather_ids = [e['weather'][0]['id'] for e in entries]

                description = Counter(descriptions).most_common(1)[0][0]
                weather_id = Counter(weather_ids).most_common(1)[0][0]
                emoji = get_weather_emoji(weather_id)

                temp_min = min(temps)
                temp_max = max(temps)

                message += f"*{date}:* {emoji} {description.capitalize()}\n"
                message += f"• 🌡️ *Температура:* {temp_min}°C - {temp_max}°C\n\n"

            await update.message.reply_text(message, parse_mode='Markdown')

        else:
            name = data['name']
            country = data['sys']['country']
            weather_desc = data['weather'][0]['description']
            temp = data['main']['temp']
            feels_like = data['main']['feels_like']
            humidity = data['main']['humidity']
            wind_speed = data['wind']['speed']
            weather_id = data['weather'][0]['id']
            emoji = get_weather_emoji(weather_id)

            image_file = get_weather_image(weather_id)
            image_path = os.path.join(IMAGES_PATH, image_file)

            response_message = (
                f"{emoji} *Погода в {name}, {country}:*\n"
                f"• 🌡️ *Температура:* {temp}°C (ощущается как {feels_like}°C)\n"
                f"• 💧 *Влажность:* {humidity}%\n"
                f"• 💨 *Скорость ветра:* {wind_speed} м/с\n"
                f"• 🌥️ *Описание:* {weather_desc.capitalize()}\n"
            )

            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=response_message,
                        parse_mode='Markdown'
                    )
            else:
                await update.message.reply_text(response_message, parse_mode='Markdown')

    except KeyError as e:
        logger.error(f"Ошибка обработки данных погоды: {e}")
        processing_error_msg = LANGUAGES.get(language, LANGUAGES['ru']).get('processing_error',
                                                                            'Произошла ошибка при обработке данных погоды.')
        await update.message.reply_text(processing_error_msg)

    return ConversationHandler.END


async def handle_weather_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_weather(update, context, is_forecast=False)


async def handle_forecast_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_weather(update, context, is_forecast=True)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    invalid_msg = LANGUAGES.get(language, LANGUAGES['ru']).get('invalid_command', LANGUAGES['ru']['invalid_command'])
    await update.message.reply_text(invalid_msg)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    language = get_user_setting(user_id)['language']
    cancel_msg = LANGUAGES.get(language, LANGUAGES['ru']).get('cancel', 'Действие отменено.')
    await update.message.reply_text(cancel_msg)
    return ConversationHandler.END


def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    weather_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('weather', weather_command)],
        states={
            WEATHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weather_response)]
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )

    forecast_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('forecast', forecast_command)],
        states={
            FORECAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_forecast_response)]
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )

    location_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('location', location_command)],
        states={
            LOCATION: [MessageHandler(filters.LOCATION & ~filters.COMMAND, handle_location)]
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("setlanguage", set_language))
    application.add_handler(CallbackQueryHandler(language_callback, pattern='^(ru|en|es)$'))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(weather_conv_handler)
    application.add_handler(forecast_conv_handler)
    application.add_handler(location_conv_handler)
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.run_polling()


if __name__ == '__main__':
    main()
