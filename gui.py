import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext
from tkinter import filedialog
from irc.bot import SingleServerIRCBot
from requests import get, Session

from threading import Thread, Event
import threading
from threading import Timer
import sys, os, datetime, pytz, re

from config import read_curl
from helper import path_resolver


EXE_PATH = path_resolver()
INI_FILE = 'config.ini'
SETTINGS_FILE = 'config.txt'
MOST_RECENT_DONOR_FILE = 'most_recent_donor.txt'
ecpay_donate_id_set = set()
opay_donate_id_set = set()
bot = None
stop_threads = False


class RepeatTimer(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)

class Bot(SingleServerIRCBot):
    def __init__(self, twitch_id, oauth, ecpay_id, opay_id, text_with_comment, text_without_comment, has_opay, has_ecpay):
        self.HOST = "irc.chat.twitch.tv"
        self.PORT = 6667
        self.USERNAME = twitch_id.lower()
        self.TOKEN = oauth
        self.CHANNEL = f"#{twitch_id}"
        self.ECPAYID = ecpay_id
        self.OPAYID = opay_id
        self.REFRESH_TIME = 5
        self.TEXT_WITH_COMMENT = text_with_comment
        self.TEXT_WITHOUT_COMMENT = text_without_comment
        self.is_connected = False
        self.session_ecpay = Session()
        self.session_opay = Session()
        self.has_opay = has_opay
        self.has_ecpay = has_ecpay
        self.opay_payload = ''

        super().__init__([(self.HOST, self.PORT, f"{self.TOKEN}")], self.USERNAME, self.USERNAME)

        self.event = Event()
        self.timer_thread = RepeatTimer(self.REFRESH_TIME, self.send_request_to_endpoint)
        self.timer_thread.daemon = True
        self.timer_thread.start()
    

    def send_request_to_endpoint(self):

        if self.has_ecpay:
            self._send_request_to_website('ecpay')
        if self.has_opay:
            self._send_request_to_website('opay')


    def _send_request_to_website(self, which_site):

        url = ''
        id_set = None

        if which_site == 'ecpay':
            url = f'https://payment.ecpay.com.tw/Broadcaster/CheckDonate/{self.ECPAYID}'
            id_set = ecpay_donate_id_set
            response = self.session_ecpay.post(url)
            if response.status_code != 200:
                add_text_to_the_end(text_area_log, f"未正確綠界伺服器得到資料回傳，回應代碼：{response.status_code}")
                return
            else:
                result = response.json()

        elif which_site == 'opay':
            url = f'https://payment.opay.tw/Broadcaster/CheckDonate/{self.OPAYID}'
            id_set = opay_donate_id_set
            payload = {'__RequestVerificationToken': self.opay_payload}
            headers = {
              'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
              'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
            }

            response = self.session_opay.post(url, headers=headers, data=payload)
            
            if response.status_code != 200:
                add_text_to_the_end(text_area_log, f"未正確從歐付寶伺服器得到資料回傳，回應代碼：{response.status_code}")
                self.opay_payload = self._get_opay_payload(self.OPAYID)
                return
            else:
                result = response.json()['lstDonate']

        for donate in result:
            if donate['donateid'] not in id_set:
                platform = "綠界" if which_site == 'ecpay' else "歐付寶"
                # send message
                if donate['msg'] is not None:
                    msg = self.TEXT_WITH_COMMENT.format(name=donate['name'], amount=donate['amount'], msg=donate['msg'])
                    msg_to_log = f"{donate['name']} 用{platform}斗內了 {donate['amount']} 元，並留言：{donate['msg']}"
                else:
                    msg = self.TEXT_WITHOUT_COMMENT.format(name=donate['name'], amount=donate['amount'], msg=donate['msg'])
                    msg_to_log = f"{donate['name']} 用{platform}斗內了 {donate['amount']} 元"
                
                self.send_message(msg)
                add_text_to_the_end(text_area_log, msg_to_log)
                id_set.add(donate['donateid'])

                write_donor_to_file(os.path.join(EXE_PATH, MOST_RECENT_DONOR_FILE), donate['name'], donate['amount'])

    def _get_opay_payload(self, opay_id):
        add_text_to_the_end(text_area_log, "重新取得歐付寶正確資料中...")
        token_ptn = '<input name="__RequestVerificationToken" type="hidden" value="(.*)"'
        header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'}
        r = self.session_opay.get(f'https://payment.opay.tw/Broadcaster/AlertBox/{opay_id}', headers=header)
        try:
            payload = re.search(token_ptn, r.content.decode()).group(1)
            add_text_to_the_end(text_area_log, "成功取得")
            return payload
        except:
            add_text_to_the_end(text_area_log, "取得失敗")
            return ""

    def send_message(self, message):
        self.connection.privmsg(self.CHANNEL, message)
        # print(f"HAN__BOT：{message}")

    def on_welcome(self, cxn, event):
        for req in ("membership", "tags", "commands"):
            cxn.cap("REQ", f":twitch.tv/{req}")

        cxn.join(self.CHANNEL)
        print('the bot is running')
        self.send_message("斗內聊天室通知機器人上線囉")
        add_text_to_the_end(text_area_log, "斗內聊天室通知機器人上線囉")

        for child in root.children.values():
            if isinstance(child, tk.Button) and child['text']=='啟動':
                child.configure(text='執行中')
                child['state'] = tk.constants.DISABLED

        self.is_connected = True

    def on_disconnect(self, cxn, event):
        # Bot has disconnected from the server
        print('the bot has been disconnected')
        add_text_to_the_end(text_area_log, "斗內聊天室通知機器人下班囉")
        for child in root.children.values():
            if isinstance(child, tk.Button)  and child['text']=='執行中':
                child.configure(text='啟動')
                child['state'] = tk.constants.NORMAL
        self.is_connected = False


def start_server(bot):
    bot.start()

def on_closing():
    root.destroy()
    sys.exit()

def update_config_ini(filename):
    with open(os.path.join(EXE_PATH, INI_FILE), "w", encoding='utf-8') as f:
        f.write(filename)

def add_text_to_the_end(textarea, text):
    now = datetime.datetime.now()
    format_data = "%H:%M:%S"
    now = now.strftime(format_data)
    textarea.configure(state ='normal')
    textarea.insert("end", f"[{now}] {text}\n")
    textarea.configure(state ='disabled')
    textarea.yview(tk.END) # 將 textarea滑到最下方

def load_config_file():
    filename = filedialog.askopenfilename(
        initialdir = EXE_PATH,
        title = "載入設定檔",
        filetypes = (("Text files", "*.txt*"),))

    if not filename:
        print('無選擇檔案')
    else:
        load_config(config_filepath=filename)

def save_as_config_file():

    new_file_path = filedialog.asksaveasfilename(
        initialdir = EXE_PATH,
        title = "另存設定檔",
        filetypes=(("Text", '*.txt'),),
        defaultextension = (("Text", '*.txt'),))

    if not new_file_path:
        print('無選擇檔案')
    else:
        text_to_save = f'''ecpay_id:{input_field_ecpay_id.get()}
opay_id:{input_field_opay_id.get()}
twitch_id:{input_field_twitch_id.get()}
twitch_oauth:{input_field_twitch_oauth.get()}
text_with_comment:{input_field_text_with_comment.get("1.0", tk.END).strip()}
text_without_comment:{input_field_text_without_comment.get("1.0", tk.END).strip()}'''

        with open(new_file_path, 'w', encoding='UTF-8') as f:
            f.write(text_to_save)

        root.title("圖奇斗內聊天室通知" + f' - {os.path.basename(new_file_path)}')
        update_config_ini(new_file_path)


def activate_bot():
    global bot
    has_ecpay = check_ecpay.get()
    has_opay = check_opay.get()
    ecpay_id = input_field_ecpay_id.get()
    opay_id = input_field_opay_id.get()
    twitch_id = input_field_twitch_id.get()
    twitch_oauth = input_field_twitch_oauth.get()
    text_with_comment = input_field_text_with_comment.get("1.0", tk.END).strip()
    text_without_comment = input_field_text_without_comment.get("1.0", tk.END).strip()


    if has_ecpay and ecpay_id == '':
        messagebox.showerror(title="填寫不完整", message="請輸入綠界ID。取得方式：...")
        return
    
    if has_opay and opay_id == '':
        messagebox.showerror(title="填寫不完整", message="請輸入歐付寶ID。取得方式：...")
        return

    if twitch_id == '':
        messagebox.showerror(title="填寫不完整", message="請輸入Twitch帳號")
        return

    if twitch_oauth == '':
        messagebox.showerror(title="填寫不完整", message="請輸入Twitch OAuth。取得方式：...")
        return

    if text_with_comment == '':
        messagebox.showerror(title="填寫不完整", message="請輸入收到斗內時要傳到聊天室的訊息內容。可使用的變數：斗內者 \{name\} / 斗內金額 \{amount\} / 斗內者留言 \{msg\}")
        return

    if text_without_comment == '':
        messagebox.showerror(title="填寫不完整", message="請輸入收到斗內時要傳到聊天室的訊息內容。可使用的變數：斗內者 \{name\} / 斗內金額 \{amount\}")
        return

    if not has_ecpay and not has_opay:
        messagebox.showerror(title="填寫不完整", message="請至少勾選綠界或歐付寶，並輸入ID")
        return

    if bot is not None and bot.is_connected:
        pass
    else:
        try:
            bot = Bot(twitch_id, twitch_oauth, ecpay_id, opay_id, text_with_comment, text_without_comment, has_opay, has_ecpay)
        except:
            messagebox.showerror(title="錯誤", message="讀取opay.txt有誤")
            return
        bot_server_thread = threading.Thread(target=start_server, args=(bot,))
        bot_server_thread.daemon = True
        bot_server_thread.start()


def deactivate_bot():
    global bot
    if bot.is_connected:
        bot.disconnect()

def load_config(config_filepath='default'):

    if config_filepath == 'default':
        with open(os.path.join(EXE_PATH, INI_FILE), 'r') as f:
            ini_file = f.read()
        config_filepath = os.path.join(EXE_PATH, ini_file)

    try:
        with open(config_filepath, "r", encoding="utf-8") as file:
            lines = file.readlines()

        settings = {}
        for line in lines:
            elms = line.strip().split(":")
            settings[elms[0]] = ''.join(elms[1:])

        if 'opay_id' in settings and settings.get("opay_id", "") != '':
            check_opay.set(1)
        else:
            check_opay.set(0)
        input_field_opay_id.delete(0, tk.END)
        input_field_opay_id.insert(0, settings.get("opay_id", ""))

        if 'ecpay_id' in settings and settings.get("ecpay_id", "") != '':
            check_ecpay.set(1)
        else:
            check_ecpay.set(0)

        input_field_ecpay_id.delete(0, tk.END)
        input_field_ecpay_id.insert(0, settings.get("ecpay_id", ""))

        input_field_twitch_id.delete(0, tk.END)
        input_field_twitch_id.insert(0, settings.get("twitch_id", ""))

        input_field_twitch_oauth.delete(0, tk.END)
        input_field_twitch_oauth.insert(0, settings.get("twitch_oauth", ""))

        input_field_text_without_comment.delete('1.0', tk.END)
        input_field_text_without_comment.insert('1.0', settings.get("text_without_comment", ""))

        input_field_text_with_comment.delete('1.0', tk.END)
        input_field_text_with_comment.insert('1.0', settings.get("text_with_comment", ""))

        root.title("圖奇斗內聊天室通知" + f' - {os.path.basename(config_filepath)}')
        update_config_ini(config_filepath)

    except FileNotFoundError:
        pass

def write_donor_to_file(filepath, donor, amount):
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"{donor}: {amount}")

# Create the main root
root = tk.Tk()
root.title("圖奇斗內聊天室通知")
root.geometry("550x400")
root.resizable(True, True)

check_ecpay = tk.IntVar()
check_btn_ecpay_id = tk.Checkbutton(root, text='綠界ID', variable=check_ecpay).grid(row=0, sticky=tk.E)
input_field_ecpay_id = tk.Entry(root, width=40)
input_field_ecpay_id.grid(row=0, column=1)

check_opay = tk.IntVar()
check_btn_opay_id = tk.Checkbutton(root, text='歐付寶ID', variable=check_opay).grid(row=1, sticky=tk.E)
input_field_opay_id = tk.Entry(root, width=40)
input_field_opay_id.grid(row=1, column=1)

label2 = tk.Label(root, text="Twitch帳號").grid(row=2, sticky=tk.E)
input_field_twitch_id = tk.Entry(root, width=40)
input_field_twitch_id.grid(row=2, column=1)

label3 = tk.Label(root, text="Twitch OAuth").grid(row=3, sticky=tk.E)
input_field_twitch_oauth = tk.Entry(root, width=40)
input_field_twitch_oauth.grid(row=3, column=1)

label4 = tk.Label(root, text="通知文字(無留言)").grid(row=4, sticky=tk.E)
input_field_text_without_comment = tk.Text(root, width=40, height=3)
input_field_text_without_comment.grid(row=4, column=1)

label5 = tk.Label(root, text="通知文字(有留言)").grid(row=5, sticky=tk.E)
input_field_text_with_comment = tk.Text(root, width=40, height=3)
input_field_text_with_comment.grid(row=5, column=1)

# Create a button to update the labels
button_activate = tk.Button(root, text="啟動", command=activate_bot, width=8).grid(row=6, column=0)
button_deactivate = tk.Button(root, text="關閉", command=deactivate_bot, width=8).grid(row=6, column=1, sticky=tk.W)

label_log = tk.Label(root, text="紀錄").grid(row=7, column=0, pady = (10, 0), padx=5, sticky=tk.W)
text_area_log = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=75, heigh=12)
text_area_log.grid(row=8, column=0, columnspan=6, padx=5)

# 載入初始設定檔
load_config()

root.protocol("WM_DELETE_root", on_closing)

# 設定Menu bar
menubar = tk.Menu(root)
filemenu = tk.Menu(menubar, tearoff=0)
filemenu.add_command(label="儲存設定檔", command=save_as_config_file)
filemenu.add_command(label="載入設定檔", command=load_config_file)
menubar.add_cascade(label='設定檔', menu=filemenu)
root.config(menu=menubar)

# 設定icon
# small_icon = tk.PhotoImage(file="icon_16.png")
# large_icon = tk.PhotoImage(file="icon_32.png")
# root.iconphoto(False, large_icon, small_icon)

# Run the main loop
root.mainloop()