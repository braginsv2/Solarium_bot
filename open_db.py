import sqlite3
from tabulate import tabulate

def print_all_users():
    """Выводит всех пользователей из базы данных в терминал"""
    try:
        conn = sqlite3.connect('solarium_bot.db')
        cursor = conn.cursor()
        
        # Проверяем существование таблицы users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            print("Таблица users не существует в базе данных.")
            return
        
        # Получаем все записи из таблицы users
        cursor.execute('SELECT * FROM users')
        users = cursor.fetchall()
        
        # Получаем названия столбцов
        cursor.execute('PRAGMA table_info(users)')
        columns = [column[1] for column in cursor.fetchall()]
        
        if not users:
            print("В базе данных нет записей.")
            return
            
        # Выводим данные в виде красивой таблицы
        print("\nСодержимое базы данных:")
        print(tabulate(users, headers=columns, tablefmt="grid"))
        
        print(f"\nВсего записей: {len(users)}")
        
    except sqlite3.Error as e:
        print(f"Ошибка при чтении базы данных: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print_all_users()