import hashlib
import os
import pyncm
import qrcode
import requests
from pyncm.apis.login import GetCurrentLoginStatus, WriteLoginInfo,LoginQrcodeUnikey,LoginQrcodeCheck
from pyncm import GetCurrentSession, LoadSessionFromString
from pyncm.apis.cloud import SetPublishCloudResource, SetUploadCloudInfo, SetUploadObject, GetNosToken, GetCheckCloudUpload
import time
from termcolor import colored, cprint
from pyncm.apis.login import (
            GetCurrentLoginStatus,
            WriteLoginInfo,
            LoginQrcodeUnikey,
            LoginQrcodeCheck,
        )
SESSION_FILE = ".cloud.key"


def print_qrcode(content):
    qr = qrcode.QRCode()
    qr.border = 5
    qr.add_data(content)
    qr.make()
    qr.print_ascii(out=None, tty=False, invert=False)


def dot_thingy():
    while True:
        yield '...'
        yield '.. '
        yield '.  '
dot = dot_thingy()

def login():
    try:
        # 尝试读取登陆凭证
        with open(SESSION_FILE) as K:
            pyncm.SetCurrentSession(LoadSessionFromString(K.read()))
            print("\t[+] 读取登录信息成功:[ ID: %s,  昵称: %s , 签名: %s , 最后登录IP: %s ]" %(
                colored(GetCurrentSession().login_info['content']['profile']['userId'], 'green'),
                colored(GetCurrentSession().login_info['content']['profile']['nickname'], 'green'),
                colored(GetCurrentSession().login_info['content']['profile']['signature'], 'green'),
                colored(GetCurrentSession().login_info['content']['profile']['lastLoginIP'], 'green')
            ))
            return True
    except FileNotFoundError:
        cprint("[>] 请进行扫码登录", 'yellow')
        def dot_thingy():
            while True:
                s = list('   ')
                while s.count('.') < len(s):
                    s[s.count('.')] = '.'
                    yield ''.join(s)

        dot = dot_thingy()

        # uuid = pyncm.login.LoginQrcodeUnikey()['unikey']
        uuid = LoginQrcodeUnikey()["unikey"]
        url = f'https://music.163.com/login?codekey={uuid}'
        print_qrcode(url)
        while True:
            rsp = LoginQrcodeCheck(uuid)
            if rsp['code'] == 803 or rsp['code'] == 800: break
            message = f"[!] 等待登录, 状态：{rsp['code']} -- {rsp['message']}"
            print(message, next(dot), end='\r')
            time.sleep(1)
        WriteLoginInfo(GetCurrentLoginStatus())
    except:
        cprint("[-] 登陆凭证已失效, 请重新登录!", 'red')
        os.remove(SESSION_FILE)
    if GetCurrentLoginStatus()['code'] == 200:
        with open(SESSION_FILE, 'w+') as K:
            K.write(pyncm.DumpSessionAsString(GetCurrentSession()))
        print('[+] 成功登录并保存了登录信息: [ ID: %s,  昵称: %s , 签名: %s , 最后登录IP: %s ]'%(
            colored(GetCurrentSession().login_info['content']['profile']['userId'], 'green'),
            colored(GetCurrentSession().login_info['content']['profile']['nickname'], 'green'),
            colored(GetCurrentSession().login_info['content']['profile']['signature'], 'green'),
            colored(GetCurrentSession().login_info['content']['profile']['lastLoginIP'], 'green'),
        ))
        return True
    else:
        cprint("[-] 未能成功登录! 请检查", 'red')
        return False


def md5sum(file):
    md5sum = hashlib.md5()
    with open(file,'rb') as f:
        while chunk := f.read():
            md5sum.update(chunk)
    return md5sum

def upload_one(path):
    fname = os.path.basename(path)
    fext = path.split('.')[-1]
    '''Parsing file names'''
    fsize = os.stat(path).st_size
    md5 = md5sum(path).hexdigest()
    print('\t\t[>] Checking file ( MD5: %s)'%colored(md5, 'green'))
    cresult = GetCheckCloudUpload(md5)
    songId = cresult['songId']
    '''网盘资源发布 4 步走：
    1.拿到上传令牌 - 需要文件名，MD5，文件大小'''
    try:
        token = GetNosToken(fname, md5, fsize, fext)['result']
        if cresult['needUpload']:
            print('\t\t[+] %s 需要继续上传 ( %s B )' % (fname, fsize))
            '''2. 若文件未曾上传完毕，则完成其上传'''
            upload_result = SetUploadObject(
                open(path, 'rb'),
                md5, fsize, token['objectKey'], token['token']
            )
        print(f'''\t\t[!] 歌曲基本信息 =>    
        \t\t    ID  :   {songId}
        \t\t    MD5 :   {md5}
        \t\t    NAME:   {fname}''')
        submit_result = SetUploadCloudInfo(token['resourceId'], songId, md5, fname, fname,
                                           '佚名',
                                           bitrate=1000)
        SetPublishCloudResource(submit_result['songId'])
        return None
    except Exception as e:
        return str(e)


def upload_from_local():
    assert login(),"[-] 登陆失败"
    target = input('\t[<] 输入文件\文件夹路径: ')
    # is a dir
    if os.path.isdir(target):
        if os.path.exists(target):
            suffixs = input("\t[<] 输入要上传的音乐文件的后缀, 以逗号分割. 例如：.mp3,.flac,.ape: ").replace(' ', '').split(',')
            files = os.walk(target)
            music_file = []
            for root, dirs, filelist in files:
                for name in filelist:
                    file = os.path.join(root, name)
                    if os.path.splitext(file)[-1] in suffixs:
                        music_file.append(file)
            print("\t[>] 共检索到 %s 个文件. "%colored(len(music_file), 'green'))
            for file in music_file:
                res = upload_one(file)
                if None == res:
                    print("\t\t[+] 上传成功 => %s" % colored(file, "green"))
                else:
                    print("\t\t[-] 上传失败 => %s, Error => %s." % (colored(file, "red"), colored(res, "red")))

            print("\t[+] 上传完毕, 请登录云盘检测.")
        else:
            cprint("\t[-] %s 路径不存在, 请检查后重试."%target)
    else:
        print("\t[->] 开始上传: %s ."%colored(target, 'green'))
        upload_one(target)

def upload_from_cloud():
    assert login(), "[-] 登陆失败"
    try:
        url = input('\t[<] 输入音乐url路径: ')
        music_name = input('\t[<] 输入音乐名称：')
        res = requests.get(url)
        with open(music_name, 'wb') as f:
            f.write(res.content)
            f.close()
        print("\t[->] 开始上传: %s ." % colored(url, 'green'))
        target = os.getcwd() + "/" + music_name
        res = upload_one(target)
        if None == res:
            print("\t\t[+] 上传成功 => %s" % colored(music_name, "green"))
        else:
            print("\t\t[-] 上传失败 => %s, Error => %s." % (colored(music_name, "red"), colored(res, "red")))
        os.remove(target)
    except Exception as e:
        cprint("[-] 下载音频文件失败, 请检测后再继续.", 'red')




def select_action():
    while True:
        print("[1] 本地上传(选择本地音乐文件进行上传).")
        print("[2] 云端上传(根据URL下载音乐文件进行上传).")
        print("[3] 注销账户(方便切换账户操作).")
        print("[4] 退出程序(不会删除凭据方便下次使用).")
        action = input("[>] 请选择操作: ")
        if action == '1':
            upload_from_local()
        elif action == '2':
            upload_from_cloud()
        elif action == '3':
            try:
                os.remove(SESSION_FILE)
            except:
                return
            print("[>] 注销成功...")
        elif action == '4':
            print("[>] 正在退出...")
            break
        else:
            print("[!] 输入错误, 请重新输入")

if __name__ == '__main__':
    select_action()

