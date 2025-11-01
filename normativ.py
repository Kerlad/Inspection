import os
import pandas as pd
import time
import sys
from ftplib import FTP
from urllib.parse import urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtCore import QSize, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QMessageBox,
    QFileDialog,
    QProgressBar
)

start = time.time()

class WorkerThread(QThread):
    """Рабочий поток для выполнения длительных операций без замораживания GUI"""
    finished = pyqtSignal(object, list, str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs, progress_callback=self.progress.emit)
            self.finished.emit(result[0], result[1], result[2])
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Если нет файлов с путем - создаем пустые
        if not os.path.exists('path.txt'):
            with open('path.txt', 'w', encoding='utf-8') as p:
                p.write('Укажите путь')
        
        if not os.path.exists('list_ech.txt'):
            with open('list_ech.txt', 'w', encoding='utf-8') as p:
                p.write('Укажите путь')
        
        if not os.path.exists('ftp_credentials.txt'):
            with open('ftp_credentials.txt', 'w', encoding='utf-8') as f:
                f.write('login/npassword')
        
        list_ech = self.read_file_with_encoding("list_ech.txt")
        path = self.read_file_with_encoding("path.txt")
        
        with open("ftp_credentials.txt", encoding='utf-8') as f:
            creds = f.read().split('
')
            ftp_login = creds[0] if len(creds) > 0 else ''
            ftp_password = creds[1] if len(creds) > 1 else ''
        
        self.setWindowTitle("Проверка наличия отчетов")
        
        # Поля ввода
        self.line_edit_1 = QLineEdit(list_ech)
        self.line_edit_2 = QLineEdit(path)
        self.line_edit_ftp_login = QLineEdit(ftp_login)
        self.line_edit_ftp_password = QLineEdit(ftp_password)
        self.line_edit_ftp_password.setEchoMode(QLineEdit.EchoMode.Password)
        
        # Кнопки обзора
        self.button_browse_list = QPushButton("📁 Обзор")
        self.button_browse_list.setMaximumWidth(100)
        self.button_browse_list.clicked.connect(self.browse_list_file)
        
        self.button_browse_path = QPushButton("📁 Обзор")
        self.button_browse_path.setMaximumWidth(100)
        self.button_browse_path.clicked.connect(self.browse_folder)
        
        # Выбор типа источника
        self.combo_source_type = QComboBox()
        self.combo_source_type.addItems(["Локальная папка", "FTP сервер"])
        self.combo_source_type.currentIndexChanged.connect(self.update_path_label)
        
        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        # Кнопки действий
        self.button = QPushButton("Проверить")
        self.button.clicked.connect(self.create_table)
        
        self.button_save_1 = QPushButton("Сохранить список")
        self.button_save_1.clicked.connect(self.Save_list)
        
        self.button_save_2 = QPushButton("Сохранить путь")
        self.button_save_2.clicked.connect(self.Save_path)
        
        self.button_save_ftp = QPushButton("Сохранить учетные данные FTP")
        self.button_save_ftp.clicked.connect(self.Save_ftp_credentials)
        
        self.label = QLabel()
        self.path_label = QLabel("Введите путь до проверяемой папки:")
        
        # Компоновка
        container = QWidget()
        layout = QVBoxLayout()
        
        # Блок списка подразделений
        layout.addWidget(QLabel("Введите список структурных подразделений через запятую с пробелом:"))
        
        list_layout = QHBoxLayout()
        list_layout.addWidget(self.line_edit_1)
        list_layout.addWidget(self.button_browse_list)
        layout.addLayout(list_layout)
        
        layout.addWidget(self.button_save_1)
        
        # Блок выбора типа источника
        layout.addWidget(QLabel("Выберите тип источника:"))
        layout.addWidget(self.combo_source_type)
        
        # Блок пути
        layout.addWidget(self.path_label)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.line_edit_2)
        path_layout.addWidget(self.button_browse_path)
        layout.addLayout(path_layout)
        
        layout.addWidget(self.button_save_2)
        
        # Блок FTP данных
        layout.addWidget(QLabel("FTP Логин:"))
        layout.addWidget(self.line_edit_ftp_login)
        
        layout.addWidget(QLabel("FTP Пароль:"))
        layout.addWidget(self.line_edit_ftp_password)
        layout.addWidget(self.button_save_ftp)
        
        # Кнопка проверки и результат
        layout.addWidget(self.button)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.label)
        
        container.setLayout(layout)
        self.setFixedSize(QSize(600, 650))
        self.setCentralWidget(container)
        
        self.worker_thread = None
    
    def read_file_with_encoding(self, file_path):
        """Чтение файла с автоматическим определением кодировки"""
        encodings = ['utf-8', 'windows-1251', 'cp1251']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                    content.encode('utf-8')
                    return content
            except (UnicodeDecodeError, UnicodeEncodeError, FileNotFoundError):
                continue
        
        return ''
    
    def browse_list_file(self):
        """Открыть диалог выбора файла со списком подразделений"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл со списком подразделений",
            "",
            "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            content = self.read_file_with_encoding(file_path)
            if content:
                self.line_edit_1.setText(content)
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось прочитать файл. Проверьте кодировку.")
    
    def browse_folder(self):
        """Открыть диалог выбора папки"""
        if self.combo_source_type.currentText() == "FTP сервер":
            QMessageBox.information(
                self,
                "Информация",
                "Для FTP сервера введите URL вручную в формате:
ftp://example.com:8021/path/to/folder"
            )
            return
        
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для проверки",
            ""
        )
        if folder_path:
            self.line_edit_2.setText(folder_path)
    
    def update_path_label(self):
        """Обновить подсказку для поля пути"""
        if self.combo_source_type.currentText() == "FTP сервер":
            self.path_label.setText("Введите FTP URL (например: ftp://example.com:8021/path/to/folder):")
            self.button_browse_path.setEnabled(False)
        else:
            self.path_label.setText("Введите путь до проверяемой папки:")
            self.button_browse_path.setEnabled(True)
    
    def Save_list(self):
        with open("list_ech.txt", "w", encoding='utf-8') as l_ech:
            l_ech.write(self.line_edit_1.text())
        QMessageBox.information(self, "Успех", "Список подразделений сохранен!")
    
    def Save_path(self):
        with open("path.txt", "w", encoding='utf-8') as p:
            p.write(self.line_edit_2.text())
        QMessageBox.information(self, "Успех", "Путь сохранен!")
    
    def Save_ftp_credentials(self):
        with open("ftp_credentials.txt", "w", encoding='utf-8') as f:
            f.write(f"{self.line_edit_ftp_login.text()}
{self.line_edit_ftp_password.text()}")
        QMessageBox.information(self, "Успех", "Учетные данные FTP сохранены!")
    
    def create_table(self):
        path = self.line_edit_2.text()
        list_ech_text = self.line_edit_1.text()
        
        if not list_ech_text or list_ech_text == 'Укажите путь':
            QMessageBox.warning(self, "Ошибка", "Укажите список подразделений!")
            return
        
        if not path or path == 'Укажите путь':
            QMessageBox.warning(self, "Ошибка", "Укажите путь к папке или FTP URL!")
            return
        
        list_ech_text = list_ech_text.strip()
        list_ech = tuple([item.strip() for item in list_ech_text.split(", ")])
        
        # Показываем прогресс бар и блокируем кнопку
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.button.setEnabled(False)
        self.label.setText("Выполняется проверка...")
        
        # Запускаем в отдельном потоке
        if self.combo_source_type.currentText() == "FTP сервер":
            self.worker_thread = WorkerThread(
                self.create_table_ftp_threaded,
                path, 
                list_ech,
                self.line_edit_ftp_login.text(),
                self.line_edit_ftp_password.text()
            )
        else:
            self.worker_thread = WorkerThread(self.create_table_local_threaded, path, list_ech)
        
        self.worker_thread.finished.connect(self.on_task_finished)
        self.worker_thread.error.connect(self.on_task_error)
        self.worker_thread.progress.connect(self.progress_bar.setValue)
        self.worker_thread.start()
    
    def on_task_finished(self, df_check, reports, path):
        """Обработка завершения задачи"""
        self.Excel_write(df_check, reports, path)
        self.progress_bar.setVisible(False)
        self.button.setEnabled(True)
    
    def on_task_error(self, error_msg):
        """Обработка ошибки"""
        QMessageBox.critical(self, "Ошибка", f"Ошибка при выполнении: {error_msg}")
        self.progress_bar.setVisible(False)
        self.button.setEnabled(True)
        self.label.setText("")
    
    def parse_ftp_url_with_cyrillic(self, ftp_url):
        """Парсинг FTP URL с поддержкой кириллицы и URL-кодирования"""
        # Убираем лишние пробелы
        ftp_url = ftp_url.strip()
        
        # Извлекаем компоненты вручную для лучшего контроля
        if not ftp_url.startswith('ftp://'):
            raise ValueError("URL должен начинаться с ftp://")
        
        # Удаляем префикс ftp://
        rest = ftp_url[6:]
        
        # Разделяем хост:порт и путь
        if '/' in rest:
            host_port, path = rest.split('/', 1)
            path = '/' + path
        else:
            host_port = rest
            path = '/'
        
        # Парсим хост и порт
        if ':' in host_port:
            host, port_str = host_port.rsplit(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                port = 21
        else:
            host = host_port
            port = 21
        
        # Декодируем путь из URL-кодировки (если он закодирован)
        try:
            # Пробуем декодировать как URL-encoded с cp1251
            decoded_path = unquote(path, encoding='cp1251', errors='strict')
        except:
            # Если не получилось, оставляем как есть
            decoded_path = path
        
        # Нормализуем путь: удаляем двойные слеши, кроме начального
        parts = [p for p in decoded_path.split('/') if p]
        normalized_path = '/' + '/'.join(parts) if parts else '/'
        
        return host, port, normalized_path
    
    def create_table_local_threaded(self, path, list_ech, progress_callback=None):
        """Оптимизированная логика для локальных папок с многопоточностью"""
        reports = []
        
        # Быстрое сканирование директорий
        with os.scandir(path) as entries:
            reports = [entry.name for entry in entries if entry.is_dir()]
        
        if not reports:
            reports.append(path.split("\\")[-1] if "\\" in path else path.split("/")[-1])
        
        # Создаем словарь для быстрого доступа
        result_dict = {name: {report: 0 for report in reports} for name in list_ech}
        
        if progress_callback:
            progress_callback(10)
        
        if len(reports) == 1:
            # Оптимизация: одна итерация по файлам
            with os.scandir(path) as entries:
                files = [entry.name for entry in entries if entry.is_file()]
            
            for name in list_ech:
                for filename in files:
                    if self.check_filename_match(filename, name):
                        result_dict[name][reports[0]] = 1
        else:
            # Многопоточная обработка подпапок
            separator = "\\" if "\\" in path else "/"
            total_reports = len(reports)
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(self.scan_folder, f"{path}{separator}{report}", list_ech): report 
                    for report in reports
                }
                
                for idx, future in enumerate(as_completed(futures)):
                    report = futures[future]
                    try:
                        matches = future.result()
                        for name in matches:
                            result_dict[name][report] = 1
                    except:
                        pass
                    
                    if progress_callback:
                        progress_callback(10 + int(80 * (idx + 1) / total_reports))
        
        # Конвертируем в DataFrame
        df_check = pd.DataFrame(result_dict).T
        df_check.columns = reports
        
        if progress_callback:
            progress_callback(95)
        
        return (df_check, reports, path)
    
    def scan_folder(self, folder_path, list_ech):
        """Сканирование одной папки (для многопоточности)"""
        matches = set()
        try:
            with os.scandir(folder_path) as entries:
                files = [entry.name for entry in entries if entry.is_file()]
            
            for name in list_ech:
                for filename in files:
                    if self.check_filename_match(filename, name):
                        matches.add(name)
                        break
        except:
            pass
        
        return matches
    
    def check_filename_match(self, filename, name):
        """Проверка соответствия имени файла"""
        file_name_parts = filename.split()
        file_name_base = filename.split(".")[0] if "." in filename else filename
        return (file_name_parts and file_name_parts[0] == name) or file_name_base == name
    
    def create_table_ftp_threaded(self, ftp_url, list_ech, ftp_login, ftp_password, progress_callback=None):
        """Оптимизированная логика для FTP с правильной обработкой кириллических путей"""
        try:
            # Используем улучшенный парсинг с поддержкой кириллицы
            host, port, ftp_path = self.parse_ftp_url_with_cyrillic(ftp_url)
            
            if not host:
                raise ValueError("Некорректный FTP URL!")
            
            # Подключаемся к FTP
            ftp = FTP()
            ftp.connect(host, port, timeout=30)
            ftp.login(ftp_login, ftp_password)
            
            # КРИТИЧЕСКИ ВАЖНО: кодировка cp1251 для Serv-U FTP Server
            ftp.encoding = 'cp1251'
            
            if progress_callback:
                progress_callback(10)
            
            # Переходим в нужную директорию пошагово
            if ftp_path != '/':
                # Разбиваем путь на части
                path_parts = [p for p in ftp_path.split('/') if p]
                
                # Переходим по частям для избежания проблем с кодировкой
                current_path = '/'
                for part in path_parts:
                    try:
                        # Пробуем перейти в папку
                        ftp.cwd(part)
                        current_path = ftp.pwd()
                    except Exception as e:
                        # Если не получилось, пробуем найти папку через LIST
                        try:
                            items = []
                            ftp.retrlines('LIST', items.append)
                            
                            # Ищем папку с похожим именем
                            found = False
                            for item in items:
                                parts_list = item.split()
                                if len(parts_list) >= 9 and parts_list[0].startswith('d'):
                                    folder_name = ' '.join(parts_list[8:])
                                    if folder_name.lower() == part.lower() or folder_name == part:
                                        ftp.cwd(folder_name)
                                        current_path = ftp.pwd()
                                        found = True
                                        break
                            
                            if not found:
                                raise ValueError(f"Не удалось найти папку: {part}")
                        except Exception as inner_e:
                            raise ValueError(f"Ошибка навигации в папку '{part}': {inner_e}")
            
            # Получаем список подпапок в текущей директории
            items = []
            ftp.retrlines('LIST', items.append)
            
            reports = []
            for item in items:
                parts = item.split()
                if len(parts) >= 9 and parts[0].startswith('d'):
                    folder_name = ' '.join(parts[8:])
                    reports.append(folder_name)
            
            if not reports:
                # Если нет подпапок, работаем с текущей директорией
                reports.append(ftp.pwd().split('/')[-1] or 'root')
            
            # Создаем словарь для результатов
            result_dict = {name: {report: 0 for report in reports} for name in list_ech}
            
            if progress_callback:
                progress_callback(20)
            
            base_path = ftp.pwd()
            total_reports = len(reports)
            
            for idx, report in enumerate(reports):
                try:
                    # Переходим в подпапку
                    ftp.cwd(report)
                    
                    files = []
                    ftp.retrlines('LIST', files.append)
                    
                    # Извлекаем только имена файлов (не папок)
                    filenames = []
                    for file_line in files:
                        file_parts = file_line.split()
                        if len(file_parts) >= 9 and not file_parts[0].startswith('d'):
                            filename = ' '.join(file_parts[8:])
                            filenames.append(filename)
                    
                    # Проверяем совпадения
                    for name in list_ech:
                        for filename in filenames:
                            if self.check_filename_match(filename, name):
                                result_dict[name][report] = 1
                                break
                    
                    # Возвращаемся в базовую директорию
                    ftp.cwd(base_path)
                except Exception as e:
                    print(f"Ошибка обработки папки '{report}': {e}")
                    try:
                        ftp.cwd(base_path)
                    except:
                        pass
                
                if progress_callback:
                    progress_callback(20 + int(70 * (idx + 1) / total_reports))
            
            ftp.quit()
            
            # Конвертируем в DataFrame
            df_check = pd.DataFrame(result_dict).T
            df_check.columns = reports
            
            if progress_callback:
                progress_callback(95)
            
            return (df_check, reports, os.getcwd())
        
        except Exception as e:
            raise Exception(f"Ошибка FTP: {str(e)}")
    
    def Excel_write(self, df_check, reports, path):
        """Оптимизированное сохранение результата в Excel"""
        df_check = df_check.fillna(0)
        
        if os.path.isdir(path):
            separator = "\\" if "\\" in path else "/"
            output_file = f"{path}{separator}Контроль.xlsx"
        else:
            output_file = f"{os.getcwd()}{os.sep}Контроль.xlsx"
        
        from openpyxl import Workbook
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Наличие"
        
        # Добавляем заголовки
        ws.append([''] + list(df_check.columns))
        
        # Добавляем данные построчно
        for idx in df_check.index:
            row = [str(idx)] + [int(df_check.at[idx, col]) if pd.notna(df_check.at[idx, col]) else 0 
                                for col in df_check.columns]
            ws.append(row)
        
        wb.save(output_file)
        
        finish = time.time()
        res = finish - start
        
        self.label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.label.setText(f"Выполнено за {round(res, 2)} секунд!
Сохранено в:
{output_file}")
        
        QMessageBox.information(self, "Готово", f"Проверка завершена!
Файл сохранен: {output_file}")


app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.exec()
