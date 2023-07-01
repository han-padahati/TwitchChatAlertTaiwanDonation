import re

def read_curl(txt_path):
    payload = ''
    cookie = ''
    with open(txt_path, 'r') as f:
        for line in f.readlines():
            if '--data-raw' in line:
                payload = line
            if 'cookie:' in line:
                cookie = line
    

    payload_ptn = re.compile("'(.*)'")
    try:
        captured_payload = re.search(payload_ptn ,payload).group(1)
    except:
        raise ValueError("opay.txt內容格式有誤")

    cookie_ptn = re.compile("cookie: (.*)'")
    try:
        captured_cookie = re.search(cookie_ptn ,cookie).group(1)
    except:
        raise ValueError("opay.txt內容格式有誤")
    


    return (captured_payload, captured_cookie)


if __name__ == '__main__':
    r = read_curl('opay.txt')
    print(r)