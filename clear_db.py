import sqlite3
import os

def clear_database():
    """Очистка базы данных (удаление всех записей из таблицы users)"""
    try:
        conn = sqlite3.connect('solarium_bot.db')
        cursor = conn.cursor()
        
        # Проверяем существование таблицы users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            print("Таблица users не существует в базе данных.")
            return
        
        # Удаляем все записи из таблицы users
        cursor.execute('DELETE FROM users')
        conn.commit()
        print("Все данные из таблицы users успешно удалены.")
        
    except sqlite3.Error as e:
        print(f"Ошибка при очистке базы данных: {e}")
    finally:
        if conn:
            conn.close()

def delete_database_file():
    """Полное удаление файла базы данных"""
    try:
        if os.path.exists('solarium_bot.db'):
            os.remove('solarium_bot.db')
            print("Файл базы данных solarium_bot.db успешно удален.")
        else:
            print("Файл базы данных solarium_bot.db не существует.")
    except Exception as e:
        print(f"Ошибка при удалении файла базы данных: {e}")

if __name__ == '__main__':
    print("Выберите действие:")
    print("1 - Очистить таблицу users (удалить все записи)")
    print("2 - Полностью удалить файл базы данных")
    print("3 - Отмена")
    
    choice = input("Ваш выбор (1/2/3): ").strip()
    
    if choice == '1':
        clear_database()
    elif choice == '2':
        delete_database_file()
    elif choice == '3':
        print("Отмена операции.")
    else:
        print("Неверный выбор.")