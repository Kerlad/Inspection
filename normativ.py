import os
import pandas as pd
import time
import sys
from ftplib import FTP, error_perm, all_errors
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
    finished = pyqtSignal(object, object)
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
            self.finished.emit(result[0], result[1])
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    VIDEO_EXTENSIONS = {'.mov', '.avi', '.mp4', '.mpeg', '.MP4', '.MOV', '.AVI', '.MPEG', '.mkv', '.MKV'}

    def __init__(self):
        super().__init__()

        # Создаем файлы конфигурации, если отсутствуют
        if not os.path.exists('inspection_path.txt'):
            with open('inspection_path.txt', 'w', encoding='utf-8') as p:
                p.write('Укажите путь')
        if not os.path.exists('inspection_month.txt'):
            with open('inspection_month.txt', 'w', encoding='utf-8') as m:
                m.write('месяц год')
        if not os.path.exists('ftp_credentials.txt'):
            with open('ftp_credentials.txt', 'w', encoding='utf-8') as f:
                f.write('login
password')

        path = self.read_file_with_encoding("inspection_path.txt")
        month = self.read_file_with_encoding("inspection_month.txt")

        ftp_login = ''
        ftp_password = ''
        try:
            with open("ftp_credentials.txt", encoding='utf-8') as f:
                creds = f.read().split('
')
                ftp_login = creds[0] if len(creds) > 0 else ''
                ftp_password = creds[1] if len(creds) > 1 else ''
        except Exception:
            pass

        self.setWindowTitle("Проверка нормативов и оперативных проверок")

        # Поля ввода
        self.line_edit_month = QLineEdit(month)
        self.line_edit_path = QLineEdit(path)
        self.line_edit_ftp_login = QLineEdit(ftp_login)
        self.line_edit_ftp_password = QLineEdit(ftp_password)
        self.line_edit_ftp_password.setEchoMode(QLineEdit.EchoMode.Password)

        # Кнопка обзора
        self.button_browse = QPushButton("📁 Обзор")
        self.button_browse.setMaximumWidth(100)
        self.button_browse.clicked.connect(self.browse_folder)

        # Выбор источника
        self.combo_source_type = QComboBox()
        self.combo_source_type.addItems(["Локальная папка", "FTP сервер"])
        self.combo_source_type.currentIndexChanged.connect(self.update_path_label)

        # Прогресс
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        # Кнопки действий
        self.button_check = QPushButton("Проверить")
        self.button_check.clicked.connect(self.start_check)

        self.button_save_month = QPushButton("Сохранить месяц")
        self.button_save_month.clicked.connect(self.save_month)

        self.button_save_path = QPushButton("Сохранить путь")
        self.button_save_path.clicked.connect(self.save_path)

        self.button_save_ftp = QPushButton("Сохранить учетные данные FTP")
        self.button_save_ftp.clicked.connect(self.save_ftp_credentials)

        # Подписи
        self.label = QLabel()
        self.path_label = QLabel("Введите путь до папки с нормативами:")

        # Компоновка
        container = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Введите месяц и год (например: май 2024):"))
        layout.addWidget(self.line_edit_month)
        layout.addWidget(self.button_save_month)

        layout.addWidget(QLabel("Выберите тип источника:"))
        layout.addWidget(self.combo_source_type)

        layout.addWidget(self.path_label)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.line_edit_path)
        path_layout.addWidget(self.button_browse)
        layout.addLayout(path_layout)
        layout.addWidget(self.button_save_path)

        layout.addWidget(QLabel("FTP Логин:"))
        layout.addWidget(self.line_edit_ftp_login)
        layout.addWidget(QLabel("FTP Пароль:"))
        layout.addWidget(self.line_edit_ftp_password)
        layout.addWidget(self.button_save_ftp)

        layout.addWidget(self.button_check)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.label)

        container.setLayout(layout)
        self.setFixedSize(QSize(600, 550))
        self.setCentralWidget(container)

        self.worker_thread = None

    def read_file_with_encoding(self, file_path: str) -> str:
        encodings = ['utf-8', 'cp1251', 'windows-1251']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                    _ = content.encode('utf-8', errors='strict')
                    return content
            except (UnicodeDecodeError, UnicodeEncodeError, FileNotFoundError):
                continue
        return ''

    def browse_folder(self):
        if self.combo_source_type.currentText() == "FTP сервер":
            QMessageBox.information(
                self,
                "Информация",
                "Для FTP сервера введите URL вручную в формате:
ftp://host:port/путь/к/папке"
            )
            return
        folder_path = QFileDialog.getExistingDirectory(self, "Выберите папку с нормативами", "")
        if folder_path:
            self.line_edit_path.setText(folder_path)

    def update_path_label(self):
        if self.combo_source_type.currentText() == "FTP сервер":
            self.path_label.setText("Введите FTP URL (например: ftp://10.23.236.225:8021/…):")
            self.button_browse.setEnabled(False)
        else:
            self.path_label.setText("Введите путь до папки с нормативами:")
            self.button_browse.setEnabled(True)

    def save_month(self):
        with open("inspection_month.txt", "w", encoding='utf-8') as m:
            m.write(self.line_edit_month.text())
        QMessageBox.information(self, "Успех", "Месяц сохранен!")

    def save_path(self):
        with open("inspection_path.txt", "w", encoding='utf-8') as p:
            p.write(self.line_edit_path.text())
        QMessageBox.information(self, "Успех", "Путь сохранен!")

    def save_ftp_credentials(self):
        with open("ftp_credentials.txt", "w", encoding='utf-8') as f:
            f.write(f"{self.line_edit_ftp_login.text()}
{self.line_edit_ftp_password.text()}")
        QMessageBox.information(self, "Успех", "Учетные данные FTP сохранены!")

    def start_check(self):
        path = self.line_edit_path.text().strip()
        month = self.line_edit_month.text().strip()

        if not path or path == 'Укажите путь':
            QMessageBox.warning(self, "Ошибка", "Укажите путь к папке или FTP URL!")
            return
        if not month or month == 'месяц год':
            QMessageBox.warning(self, "Ошибка", "Укажите месяц и год!")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.button_check.setEnabled(False)
        self.label.setText("Выполняется проверка...")

        if self.combo_source_type.currentText() == "FTP сервер":
            self.worker_thread = WorkerThread(
                self.process_ftp,
                path,
                month,
                self.line_edit_ftp_login.text(),
                self.line_edit_ftp_password.text()
            )
        else:
            self.worker_thread = WorkerThread(self.process_local, path, month)

        self.worker_thread.finished.connect(self.on_task_finished)
        self.worker_thread.error.connect(self.on_task_error)
        self.worker_thread.progress.connect(self.progress_bar.setValue)
        self.worker_thread.start()

    def on_task_finished(self, df_check, df_normativ):
        month = self.line_edit_month.text().strip()
        output_file = f"{os.getcwd()}{os.sep}Проверки {month}.xlsx"
        try:
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df_check.to_excel(writer, sheet_name='Оперативные', index=False)
                df_normativ.to_excel(writer, sheet_name='Нормативы', index=False)
            finish = time.time()
            res = finish - start
            self.label.setText(f"Выполнено за {round(res, 2)} секунд!
Сохранено в:
{output_file}")
            QMessageBox.information(self, "Готово", f"Проверка завершена!
Файл сохранен: {output_file}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка сохранения файла: {str(e)}")
        self.progress_bar.setVisible(False)
        self.button_check.setEnabled(True)

    def on_task_error(self, error_msg):
        QMessageBox.critical(self, "Ошибка", f"Ошибка при выполнении: {error_msg}")
        self.progress_bar.setVisible(False)
        self.button_check.setEnabled(True)
        self.label.setText("")

    # ============ ЛОКАЛЬНЫЙ РЕЖИМ ============
    def process_local(self, path, month, progress_callback=None):
        check_data = []
        normativ_data = []

        if progress_callback:
            progress_callback(5)

        with os.scandir(path) as ech_entries:
            ech_list = [entry for entry in ech_entries if entry.is_dir()]

        total_ech = max(1, len(ech_list))

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(self.process_ech_local, ech.path, ech.name): ech.name
                for ech in ech_list
            }
            for idx, future in enumerate(as_completed(futures)):
                try:
                    ech_check_data, ech_normativ_data = future.result()
                    check_data.extend(ech_check_data)
                    normativ_data.extend(ech_normativ_data)
                except Exception as e:
                    print(f"Ошибка обработки ЭЧ: {e}")
                if progress_callback:
                    progress_callback(5 + int(90 * (idx + 1) / total_ech))

        df_check = pd.DataFrame(check_data, columns=["ЭЧ", "Руководитель", "Норматив", "Где проводились", "Наличие видео ОП"])
        df_normativ = pd.DataFrame(normativ_data, columns=["ЭЧ", "Руководитель", "Норматив", "Наличие материалов"])

        if progress_callback:
            progress_callback(100)
        return (df_check, df_normativ)

    def process_ech_local(self, ech_path, ech_name):
        check_data = []
        normativ_data = []
        try:
            with os.scandir(ech_path) as person_entries:
                for person in person_entries:
                    if not person.is_dir():
                        continue
                    person_path = person.path
                    with os.scandir(person_path) as normativ_entries:
                        for normativ in normativ_entries:
                            if not normativ.is_dir():
                                continue
                            normativ_path = normativ.path
                            if 'оперативные проверки' in normativ.name.lower():
                                check_count = 0
                                with os.scandir(normativ_path) as check_entries:
                                    for check in check_entries:
                                        if not check.is_dir() or check.name == '01.08 ЭЧК-№':
                                            continue
                                        has_video = self.has_video_files_local(check.path)
                                        check_data.append([ech_name, person.name, normativ.name, check.name, 1 if has_video else 0])
                                        check_count += 1
                                while check_count < 3:
                                    check_data.append([ech_name, person.name, normativ.name, '!!!Нет проверки', 0])
                                    check_count += 1
                                if check_count < 4 and 'ЭЧ ' not in person.name and 'ЭЧ-% ' not in person.name:
                                    check_data.append([ech_name, person.name, normativ.name, 'Нет проверки', 0])
                            else:
                                has_materials = len(os.listdir(normativ_path)) > 0
                                normativ_data.append([ech_name, person.name, normativ.name, 1 if has_materials else 0])
        except Exception as e:
            print(f"Ошибка обработки {ech_name}: {e}")
        return (check_data, normativ_data)

    def has_video_files_local(self, folder_path):
        try:
            with os.scandir(folder_path) as entries:
                for entry in entries:
                    if entry.is_file() and os.path.splitext(entry.name)[1] in self.VIDEO_EXTENSIONS:
                        return True
        except Exception:
            pass
        return False

    # ============ FTP РЕЖИМ ============
    def parse_ftp_url_with_cyrillic(self, ftp_url: str):
        ftp_url = ftp_url.strip()
        if not ftp_url.startswith('ftp://'):
            raise ValueError("URL должен начинаться с ftp://")
        rest = ftp_url[6:]
        if '/' in rest:
            host_port, path = rest.split('/', 1)
            path = '/' + path
        else:
            host_port = rest
            path = '/'
        if ':' in host_port:
            host, port_str = host_port.rsplit(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                port = 21
        else:
            host = host_port
            port = 21
        try:
            decoded_path = unquote(path, encoding='cp1251', errors='strict')
        except Exception:
            decoded_path = path
        parts = [p for p in decoded_path.split('/') if p]
        normalized_path = '/' + '/'.join(parts) if parts else '/'
        return host, port, normalized_path

    def process_ftp(self, ftp_url, month, ftp_login, ftp_password, progress_callback=None):
        try:
            host, port, ftp_path = self.parse_ftp_url_with_cyrillic(ftp_url)
            if not host:
                raise ValueError("Некорректный FTP URL!")

            ftp = FTP()
            ftp.connect(host, port, timeout=30)
            ftp.login(ftp_login, ftp_password)
            ftp.encoding = 'cp1251'  # критично для Serv-U и кириллицы

            if progress_callback:
                progress_callback(5)

            # Пошаговая навигация по пути
            if ftp_path != '/':
                parts = [p for p in ftp_path.split('/') if p]
                for part in parts:
                    try:
                        ftp.cwd(part)
                    except all_errors:
                        # fallback: ищем через LIST
                        items = []
                        ftp.retrlines('LIST', items.append)
                        found = False
                        for item in items:
                            cols = item.split()
                            if len(cols) >= 9 and cols[0].startswith('d'):
                                folder_name = ' '.join(cols[8:])
                                if folder_name.lower() == part.lower() or folder_name == part:
                                    ftp.cwd(folder_name)
                                    found = True
                                    break
                        if not found:
                            raise ValueError(f"Не удалось найти папку: {part}")

            base_path = ftp.pwd()
            check_data = []
            normativ_data = []

            ech_list = self.get_ftp_folders(ftp)
            total_ech = max(1, len(ech_list))

            for idx, ech_name in enumerate(ech_list):
                try:
                    ech_path = f"{base_path}/{ech_name}".replace('//', '/')
                    ftp.cwd(ech_path)

                    person_list = self.get_ftp_folders(ftp)
                    for person_name in person_list:
                        person_path = f"{ech_path}/{person_name}".replace('//', '/')
                        ftp.cwd(person_path)

                        normativ_list = self.get_ftp_folders(ftp)
                        for normativ_name in normativ_list:
                            normativ_path = f"{person_path}/{normativ_name}".replace('//', '/')
                            ftp.cwd(normativ_path)

                            if 'оперативные проверки' in normativ_name.lower():
                                check_count = 0
                                check_list = [f for f in self.get_ftp_folders(ftp) if f != '01.08 ЭЧК-№']
                                for check_name in check_list:
                                    check_path = f"{normativ_path}/{check_name}".replace('//', '/')
                                    has_video = self.has_video_files_ftp(ftp, check_path)
                                    check_data.append([ech_name, person_name, normativ_name, check_name, 1 if has_video else 0])
                                    check_count += 1
                                while check_count < 3:
                                    check_data.append([ech_name, person_name, normativ_name, '!!!Нет проверки', 0])
                                    check_count += 1
                                if check_count < 4 and 'ЭЧ ' not in person_name and 'ЭЧ-% ' not in person_name:
                                    check_data.append([ech_name, person_name, normativ_name, 'Нет проверки', 0])
                            else:
                                files = self.get_ftp_files(ftp, normativ_path)
                                has_materials = len(files) > 0
                                normativ_data.append([ech_name, person_name, normativ_name, 1 if has_materials else 0])

                            ftp.cwd(person_path)
                        ftp.cwd(ech_path)
                    ftp.cwd(base_path)
                except Exception as e:
                    print(f"Ошибка обработки {ech_name}: {e}")

                if progress_callback:
                    progress_callback(5 + int(90 * (idx + 1) / total_ech))

            ftp.quit()

            df_check = pd.DataFrame(check_data, columns=["ЭЧ", "Руководитель", "Норматив", "Где проводились", "Наличие видео ОП"])
            df_normativ = pd.DataFrame(normativ_data, columns=["ЭЧ", "Руководитель", "Норматив", "Наличие материалов"])

            if progress_callback:
                progress_callback(100)
            return (df_check, df_normativ)

        except Exception as e:
            raise Exception(f"Ошибка FTP: {str(e)}")

    def get_ftp_folders(self, ftp: FTP):
        items = []
        ftp.retrlines('LIST', items.append)
        folders = []
        for item in items:
            parts = item.split()
            if len(parts) >= 9 and parts[0].startswith('d'):
                folder_name = ' '.join(parts[8:])
                folders.append(folder_name)
        return folders

    def get_ftp_files(self, ftp: FTP, path: str):
        ftp.cwd(path)
        items = []
        ftp.retrlines('LIST', items.append)
        files = []
        for item in items:
            parts = item.split()
            if len(parts) >= 9 and not parts[0].startswith('d'):
                filename = ' '.join(parts[8:])
                files.append(filename)
        return files

    def has_video_files_ftp(self, ftp: FTP, folder_path: str):
        try:
            files = self.get_ftp_files(ftp, folder_path)
            for filename in files:
                if os.path.splitext(filename)[1] in self.VIDEO_EXTENSIONS:
                    return True
        except Exception:
            pass
        return False

app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.exec()
