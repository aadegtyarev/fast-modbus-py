import serial
import time
import argparse

# Отдельные байты для команд
BROADCAST_ADDRESS = 0xFD
EXTENDED_FUNCTION_CODE = 0x46
START_SCAN_SUBCOMMAND = 0x01
CONTINUE_SCAN_SUBCOMMAND = 0x02
END_SCAN_SUBCOMMAND = 0x04
RESPONSE_SUBCOMMAND = 0x03  # Субкоманда ответа на сканирование

# Список допустимых скоростей, отсортированных по убыванию
BAUD_RATES = [115200, 57600, 38400, 19200, 9600, 4800, 2400, 1200]


# Функция для вычисления контрольной суммы
def calculate_crc(data):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if ((crc & 1) != 0):
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

# Функция для создания команды с контрольной суммой
def create_command(broadcast, function_code, subcommand):
    command = bytes([broadcast, function_code, subcommand])
    crc = calculate_crc(command)
    command += crc.to_bytes(2, 'little')  # Контрольная сумма в little-endian
    return command

# Функция для отправки команды и получения ответа
def send_command(ser, command):
    ser.write(command)
    time.sleep(0.1)  # Ждем ответ
    response = ser.read(ser.inWaiting())
    # Фильтруем ответ, удаляя лишние байты 0xFF в начале
    response = bytes(b for b in response if b != 0xFF)
    return response

# Функция для преобразования массива байтов в массив строк в шестнадцатеричном формате
def bytes_to_hex_array(byte_array):
    return [f"0x{byte:02X}" for byte in byte_array[:-2]]  # Исключаем два последних байта

# Функция для вычисления контрольной суммы ответа
def calculate_response_crc(response):
    return calculate_crc(response[:-2])  # Исключаем последние два байта (контрольную сумму)

def parse_and_print_response(hex_array, device_counter=[0]):
    # Проверка, что третий байт ответа равен RESPONSE_SUBCOMMAND
    if int(hex_array[2], 16) != RESPONSE_SUBCOMMAND:
        print("Некорректный ответ, игнорируем его.")
        return

    # Проверяем размер списка hex_array
    if len(hex_array) != 8:
        print("Неверный размер ответа для разбора серийнного номера и модбас адреса.")
        return

    # Извлечение серийный номер устройства в формате big endian
    serial_number_bytes = [int(hex_str, 16) for hex_str in hex_array[3:7]]  # Изменено с 4 до 7
    serial_number = int.from_bytes(serial_number_bytes, 'big')

    # Извлечение модбас адрес
    modbus_address = int(hex_array[7], 16)  # Изменено с 8 на 7

    # Увеличиваем счетчик устройств
    device_counter[0] += 1

    # Выводим заголовок таблицы
    if device_counter[0] == 1:
        print("| #    | Serial         | Slave ID   |")
        print("|------|----------------|------------|")

    # Выводим информацию в табличном формате
    print(f"| {device_counter[0]:<4} | {serial_number:<14} | {modbus_address:<10} |")

# Функция для обработки ответа
def process_response(response, debug=False):
    # Проверка на пустой ответ
    if response is None or len(response) == 0:
        print("Сканирование завершено.")
        return True  # Возвращаем True, чтобы остановить цикл

    # Проверка контрольной суммы ответа
    received_crc = int.from_bytes(response[-2:], 'little')  # Получаем контрольную сумму из ответа
    calculated_crc = calculate_response_crc(response)  # Вычисляем контрольную сумму от данных ответа

    if received_crc != calculated_crc:
        print("Ошибка контрольной суммы ответа.")
        print("Целиком ответ устройства (без контрольной суммы):", bytes_to_hex_array(response))
        return False  # Возвращаем False, чтобы продолжить цикл

    # Проверка наличия широковещательного адреса, команды работы с расширенными функциями и субкоманды ответа на сканирование
    if (response[0] == BROADCAST_ADDRESS and response[1] == EXTENDED_FUNCTION_CODE and
            (response[2] == RESPONSE_SUBCOMMAND or response[2] == END_SCAN_SUBCOMMAND)):
        # Проверка, что ответ содержит функцию конца сканирования
        if response[2] == END_SCAN_SUBCOMMAND:
            print("Сканирование завершено.")
            return True  # Возвращаем True, чтобы остановить цикл
        else:
            # Преобразуем байты в строки в шестнадцатеричном формате и выводим их
            hex_array = bytes_to_hex_array(response)
            if debug:
                print("Ответ устройства:", hex_array)
            # Разбор и вывод ответа устройства
            parse_and_print_response(hex_array)
            return False  # Возвращаем False, чтобы продолжить цикл
    else:
        print("Получен некорректный ответ, игнорируем его.")
        return False  # Возвращаем False, чтобы продолжить цикл

# Главная функция
def main():
    # Обработка аргументов командной строки
    parser = argparse.ArgumentParser(description='Сканирование устройств.')
    parser.add_argument('--serial-port', default='/dev/ttyACM0', help='Порт для подключения к устройству (по умолчанию /dev/ttyACM0)')
    parser.add_argument('--debug', action='store_true', help='Включить режим отладки.')
    args = parser.parse_args()

    # Используем значения из аргументов командной строки
    SERIAL_PORT = args.serial_port

    # Последовательное сканирование на различных скоростях
    for baud_rate in BAUD_RATES:
        print(f"Сканирую шину на скорости {baud_rate} бод...")
        try:
            # Открываем последовательный порт с текущей скоростью
            ser = serial.Serial(SERIAL_PORT, baud_rate, timeout=1)

            # Создаем команду начала сканирования
            start_scan_command = create_command(BROADCAST_ADDRESS, EXTENDED_FUNCTION_CODE, START_SCAN_SUBCOMMAND)

            # Начинаем сканирование
            response = send_command(ser, start_scan_command)
            if not process_response(response, debug=args.debug):
                # Если сканирование не завершено, продолжаем
                while True:
                    continue_scan_command = create_command(BROADCAST_ADDRESS, EXTENDED_FUNCTION_CODE, CONTINUE_SCAN_SUBCOMMAND)
                    response = send_command(ser, continue_scan_command)
                    if process_response(response, debug=args.debug):
                        break  # Выходим из цикла, если сканирование завершено

            # Закрываем последовательный порт
            ser.close()
        except serial.SerialException as e:
            print(f"Ошибка открытия порта с скоростью {baud_rate} бод: {e}")

if __name__ == "__main__":
    main()
