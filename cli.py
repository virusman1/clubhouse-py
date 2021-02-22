"""
cli.py

Sample CLI Clubhouse Client

RTC: For voice communication
"""

import os
import sys
import threading
import configparser
import keyboard
from rich.table import Table
from rich.console import Console
from clubhouse.clubhouse import Clubhouse

# Set some global variables
try:
    import agorartc
    RTC = agorartc.createRtcEngineBridge()
    eventHandler = agorartc.RtcEngineEventHandlerBase()
    RTC.initEventHandler(eventHandler)
    # 0xFFFFFFFE will exclude Chinese servers from Agora's servers.
    RTC.initialize(Clubhouse.AGORA_KEY, None, agorartc.AREA_CODE_GLOB & 0xFFFFFFFE)
    # Enhance voice quality
    if RTC.setAudioProfile(
            agorartc.AUDIO_PROFILE_MUSIC_HIGH_QUALITY_STEREO,
            agorartc.AUDIO_SCENARIO_GAME_STREAMING
        ) < 0:
        print("[-] Failed to set the high quality audio profile")
except ImportError:
    RTC = None

def set_interval(interval):
    """ (int) -> decorator

    set_interval decorator
    """
    def decorator(func):
        def wrap(*args, **kwargs):
            stopped = threading.Event()
            def loop():
                while not stopped.wait(interval):
                    ret = func(*args, **kwargs)
                    if not ret:
                        break
            thread = threading.Thread(target=loop)
            thread.daemon = True
            thread.start()
            return stopped
        return wrap
    return decorator

def write_config(user_id, user_token, user_device,username,name, filename='setting.ini'):
    """ (str, str, str, str) -> bool

    Write Config. return True on successful file write
    """
    config = configparser.ConfigParser()
    config["Account"] = {
        "user_device": user_device,
        "user_id": user_id,
        "name": name,
        "username": username,
        "user_token": user_token,
    }
    with open(filename, 'w') as config_file:
        config.write(config_file)
    return True

def read_config(filename='setting.ini'):
    """ (str) -> dict of str

    Read Config
    """
    config = configparser.ConfigParser()
    config.read(filename)
    if "Account" in config:
        return dict(config['Account'])
    return dict()

def process_onboarding(client):
    """ (Clubhouse) -> NoneType

    This is to process the initial setup for the first time user.
    """
    print("=" * 30)
    print("Welcome to Clubhouse!\n")
    print("The registration is not yet complete.")
    print("Finish the process by entering your legal name and your username.")
    print("WARNING: THIS FEATURE IS PURELY EXPERIMENTAL.")
    print("         YOU CAN GET BANNED FOR REGISTERING FROM THE CLI ACCOUNT.")
    print("=" * 30)

    while True:
        user_realname = input("[.] Enter your legal name (John Smith): ")
        user_username = input("[.] Enter your username (elonmusk1234): ")

        user_realname_split = user_realname.split(" ")

        if len(user_realname_split) != 2:
            print("[-] Please enter your legal name properly.")
            continue

        if not (user_realname_split[0].isalpha() and
                user_realname_split[1].isalpha()):
            print("[-] Your legal name is supposed to be written in alphabets only.")
            continue

        if len(user_username) > 16:
            print("[-] Your username exceeds above 16 characters.")
            continue

        if not user_username.isalnum():
            print("[-] Your username is supposed to be in alphanumerics only.")
            continue

        client.update_name(user_realname)
        result = client.update_username(user_username)
        if not result['success']:
            print(f"[-] You failed to update your username. ({result})")
            continue

        result = client.check_waitlist_status()
        if not result['success']:
            print("[-] Your registration failed.")
            print(f"    It's better to sign up from a real device. ({result})")
            continue

        print("[-] Registration Complete!")
        print("    Try registering by real device if this process pops again.")
        break

def print_channel_list(client, max_limit=100):
    """ (Clubhouse) -> NoneType

    Print list of channels
    """
    # Get channels and print out
    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.")
    table.add_column("Option")
    table.add_column("channel_name", style="cyan", justify="right")
    table.add_column("speaker_count")
    table.add_column("topic")
    channels = client.get_channels()['channels']
    i = 0
    for channel in channels:
        i += 1
        if i > max_limit:
            break
        _option = ""
        _option += "\xEE\x85\x84" if channel['is_social_mode'] or channel['is_private'] else ""
        table.add_row(
            str(i),
            str(_option),
            str(channel['channel']),
            str(int(channel['num_speakers'])),
            str(channel['topic']),
            
        )
    console.print(table)

def chat_main(client):
    """ (Clubhouse) -> NoneType

    Main function for chat
    """
    max_limit = 100
    channel_speaker_permission = False
    _wait_func = None
    _ping_func = None

    def _request_speaker_permission(client, channel_name, user_id):
        """ (str) -> bool

        Raise hands for permissions
        """
        if not channel_speaker_permission:
            client.audience_reply(channel_name, True, False)
            _wait_func = _wait_speaker_permission(client, channel_name, user_id)
            print("[/] You've raised your hand. Wait for the moderator to give you the permission.")

    @set_interval(30)
    def _ping_keep_alive(client, channel_name):
        """ (str) -> bool

        Continue to ping alive every 30 seconds.
        """
        client.active_ping(channel_name)
        return True

    @set_interval(10)
    def _wait_speaker_permission(client, channel_name, user_id):
        """ (str) -> bool

        Function that runs when you've requested for a voice permission.
        """
        # Get some random users from the channel.
        _channel_info = client.get_channel(channel_name)
        if _channel_info['success']:
            for _user in _channel_info['users']:
                if _user['user_id'] != user_id:
                    user_id = _user['user_id']
                    break
            # Check if the moderator allowed your request.
            res_inv = client.accept_speaker_invite(channel_name, user_id)
            if res_inv['success']:
                print("[-] Now you have a speaker permission.")
                print("    Please re-join this channel to activate a permission.")
                return False
        return True

    while True:
        # Choose which channel to enter.
        # Join the talk on success.
        user_id = client.HEADERS.get("CH-UserID")
        print_channel_list(client, max_limit)
        channel_name = input("[.] Enter channel_name: ")

        if str(channel_name) == "Exit":
            break

        channel_info = client.join_channel(channel_name)
        if not channel_info['success']:
            # Check if this channel_name was taken from the link
            channel_info = client.join_channel(channel_name, "link", "e30=")
            if not channel_info['success']:
                print(f"[-] Error while joining the channel ({channel_info['error_message']})")
                continue

        # List currently available users (TOP 20 only.)
        # Also, check for the current user's speaker permission.
        channel_speaker_permission = False
        console = Console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("No.")
        table.add_column("user_id", style="cyan", justify="right")
        table.add_column("username")
        table.add_column("name")
        table.add_column("is_speaker")
        table.add_column("is_moderator")
        users = channel_info['users']
        i = 0
        for user in users:
            i += 1
            if i > max_limit:
                break
            table.add_row(
                str(i),
                str(user['user_id']),
                str(user['name']),
                str(user['username']),
                str(user['is_speaker']),
                str(user['is_moderator']),
            )
            # Check if the user is the speaker
            if user['user_id'] == int(user_id):
                channel_speaker_permission = bool(user['is_speaker'])
        console.print(table)

        # Check for the voice level.
        if RTC:
            token = channel_info['token']
            RTC.joinChannel(token, channel_name, "", int(user_id))
        else:
            print("[!] Agora SDK is not installed.")
            print("    You may not speak or listen to the conversation.")

        # Activate pinging
        client.active_ping(channel_name)
        _ping_func = _ping_keep_alive(client, channel_name)
        _wait_func = None

        # Add raise_hands key bindings for speaker permission
        # Sorry for the bad quality
        if not channel_speaker_permission:

            if sys.platform == "darwin": # OSX
                _hotkey = "9"
            elif sys.platform == "win32": # Windows
                _hotkey = "ctrl+shift+h"

            print(f"[*] Press [{_hotkey}] to raise your hands for the speaker permission.")
            keyboard.add_hotkey(
                _hotkey,
                _request_speaker_permission,
                args=(client, channel_name, user_id)
            )

        input("[*] Press [Enter] to quit conversation.\n")
        keyboard.unhook_all()

        # Safely leave the channel upon quitting the channel.
        if _ping_func:
            _ping_func.set()
        if _wait_func:
            _wait_func.set()
        if RTC:
            RTC.leaveChannel()
        client.leave_channel(channel_name)

def user_authentication(client):
    """ (Clubhouse) -> NoneType

    Just for authenticating the user.
    """

    result = None
    while True:
        user_phone_number = input("[.] Please enter your phone number. (+818043217654) > ")
        result = client.start_phone_number_auth(user_phone_number)
        if not result['success']:
            print(f"[-] Error occured during authentication. ({result['error_message']})")
            continue
        break

    result = None
    while True:
        verification_code = input("[.] Please enter the SMS verification code (1234, 0000, ...) > ")
        result = client.complete_phone_number_auth(user_phone_number, verification_code)
        if not result['success']:
            print(f"[-] Error occured during authentication. ({result['error_message']})")
            continue
        break

    print(result)
    user_id = result['user_profile']['user_id']
    user_token = result['auth_token']
    user_device = client.HEADERS.get("CH-DeviceId")
    username = result['user_profile']['username']
    name = result['user_profile']['name']
    write_config(user_id, user_token, user_device, username,name)

    print("[.] Writing configuration file complete.")

    if result['is_waitlisted']:
        print("[!] You're still on the waitlist. Find your friends to get yourself in.")
        return

    # Authenticate user first and start doing something
    client = Clubhouse(
        user_id=user_id,
        user_token=user_token,
        user_device=user_device
    )
    if result['is_onboarding']:
        process_onboarding(client)

    return

def invite(client,num_invites):
    if num_invites == 0:
        print("Not have Invite")
        print("=" * 30)
        return
    numberPhone = input("[.] Enter Phone number for invite: ")

    if str(numberPhone) == "Exit":
        return

    _res = client.invite_to_app(None,numberPhone,"Hello")
    print(_res)

    print("=" * 30)
    
    return

def inviteWaitlist(client):
    _res  =  client.get_actionable_notifications()
    print("[!] Let them in : " + str(_res['count']))
    if _res['count'] == 0:
        print("=" * 30)
        return

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.")
    table.add_column("Noti_id", style="cyan", justify="right")
    table.add_column("user_id")
    table.add_column("username")
    table.add_column("type")
    table.add_column("name")

    users = _res['notifications']
    i = 0
    for user in users:
        i += 1
        if i > _res['count']:
            break
        table.add_row(
            str(i),
            str(user['actionable_notification_id']),
            str(user['user_profile']['user_id']),
            str(user['user_profile']['username']),
            str(user['type']),
            str(user['user_profile']['name']),
        )

    console.print(table)

    user_id = input("[.] Enter No. for invite: ")

    if str(user_id) == "Exit":
        return
    _res = client.invite_from_waitlist(int(users[int(user_id)  - 1]['user_profile']['user_id']))
    print(_res)

    _res = client.ignore_actionable_notification(int(users[int(user_id)  - 1]['actionable_notification_id']))
    print(_res)

    print("=" * 30)
    
    return

def Suggested_follows_all(client):

    _res = client.get_suggested_follows_all()
    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.")
    table.add_column("user_id")
    table.add_column("username")
    table.add_column("name")
    table.add_column("bio")

    users = _res['users']

    i = 0
    for user in users:
        i += 1
        if i > _res['count']:
            break
        table.add_row(
            str(i),
            str(user['user_id']),
            str(user['username']),
            str(user['name']),
            str(user['bio']),
        )

    console.print(table)

    print("=" * 30)
    return

    

def addFollow(client):
    user_id = input("[.] Enter user_id for Follow: ")

    if str(user_id) == "Exit":
        return

    _res = client.follow(user_id)

    print(_res)

    print("=" * 30)
    return

def getFollowing(client):
    user_id = input("[.] Enter user_id for get Following: ")

    if str(user_id) == "Exit":
        return

    _res = client.get_following(user_id, page_size=50, page=1)

    users = _res['users']

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.")
    table.add_column("user_id", style="cyan", justify="right")
    table.add_column("name")
    table.add_column("username")
    table.add_column("twitter")

    i = 0
    for user in users:
        i += 1

        _topic = ""
        _channel = ""

        if i > int(len(users)):
            break
        table.add_row(
            str(i),
            str(user['user_id']),
            str(user['name']),
            str(user['username']),
            str(user['twitter']),
        )

    console.print(table)
    print("=" * 30)

    return

def searchUsers(client):

    query = input("[.] Search User : ")

    if str(query) == "Exit":
        return

    _res = client.search_users(query,False,False,False)

    users = _res['users']

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.")
    table.add_column("user_id", style="cyan", justify="right")
    table.add_column("name")
    table.add_column("username")

    i = 0
    for user in users:
        i += 1

        _topic = ""
        _channel = ""

        if i > int(len(users)):
            break
        table.add_row(
            str(i),
            str(user['user_id']),
            str(user['name']),
            str(user['username']),
        )

    console.print(table)
    print("=" * 30)

    return

def getFollowers(client):
    user_id = input("[.] Enter user_id for get Followers: ")

    if str(user_id) == "Exit":
        print("=" * 30)
        return

    _res = client.get_followers(user_id, page_size=50, page=1)

    users = _res['users']

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.")
    table.add_column("user_id", style="cyan", justify="right")
    table.add_column("name")
    table.add_column("username")
    table.add_column("twitter")

    i = 0
    for user in users:
        i += 1

        _topic = ""
        _channel = ""

        if i > int(len(users)):
            break
        table.add_row(
            str(i),
            str(user['user_id']),
            str(user['name']),
            str(user['username']),
            str(user['twitter']),
        )

    console.print(table)
    print("=" * 30)

    return

def getProfile(client):
    _res = client.get_profile(user_id);
    print(_res)
    return

def getOnlineFriends(client):
    _res = client.get_online_friends()
    # print(_res)
    users = _res['users']

    print("[!] Online Friends : " + str(len(users)))

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.")
    table.add_column("user_id", style="cyan", justify="right")
    table.add_column("name")
    table.add_column("username")
    table.add_column("active")
    table.add_column("topic")
    table.add_column("channel", style="cyan", justify="right")

    i = 0
    for user in users:
        i += 1

        _topic = ""
        _channel = ""

        if i > int(len(users)):
            break

        if len(user) > 5:
            _topic = user['topic']
            _channel = user['channel']

        table.add_row(
            str(i),
            str(user['user_id']),
            str(user['name']),
            str(user['username']),
            str(user['last_active_minutes']),
            str(_topic),
            str(_channel),
        )

    console.print(table)
    print("=" * 30)

    return

def nameSetting(client):
    print("[1] Update Username")
    print("[2] Update Name")
    print("[3] Update Display name")
    print("[Eixt] back to main menu")    
    print("=" * 30)
    _menu = int(input("[.] Enter Menu [1-3]: "))

    if str(_menu) == "Exit":
        print("=" * 30)
        return

    if _menu ==  1:
        _input = input("[.] Enter Username : ")
        if str(_input) == "Exit":
            print("=" * 30)
            return
        _res = client.update_username(str(_input))
    elif _menu ==  2:
        _input = input("[.] Enter Name : ")
        if str(_input) == "Exit":
            print("=" * 30)
            return
        res = client.update_name(str(_input))
    elif _menu ==  3:
        _input = input("[.] Enter Display : ")
        if str(_input) == "Exit":
            print("=" * 30)
            return
        res = client.update_displayname(str(_input))
    
    print(res)

    print("=" * 30)
    return

def menu(client,num_invites):
    while True:
        print("[1] Room Chat")
        print("[2] Search Users")
        print("[3] View Following")
        print("[4] View Followers")
        print("[5] Follow")
        print("[6] Invite to App")
        print("[7] Invite From Waitlist")
        print("[8] Suggested follows all")
        print("[9] Name Setting")

        print("=" * 30)
        _menu = int(input("[.] Enter Menu [1-9]: "))

        if _menu ==  1:
            chat_main(client)
        elif _menu ==  2:
            searchUsers(client)
        elif _menu ==  3:
            getFollowing(client)
        elif _menu ==  4:
            getFollowers(client)
        elif _menu ==  5:
            addFollow(client)
        elif _menu ==  6:
            invite(client,num_invites)
        elif _menu ==  7:
            inviteWaitlist(client)
        elif _menu ==  8:
            Suggested_follows_all(client)  
        elif _menu ==  9:
            nameSetting(client)              

    return

def noTi(client,actionable_notifications_count):
    _res  =  client.get_notifications()
    print("[!] notifications : " + str(_res['count']))

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.")
    table.add_column("Noti_id", style="cyan", justify="right")
    table.add_column("user_id", style="cyan", justify="right")
    table.add_column("username")
    table.add_column("type")
    table.add_column("name")
    table.add_column("message")
    
    users = _res['notifications']
    i = 0
    for user in users:
        i += 1
        if i > int(_res['count']):
            break
        table.add_row(
            str(i),
            str(user['notification_id']),
            str(user['user_profile']['user_id']),
            str(user['user_profile']['username']),
            str(user['type']),
            str(user['user_profile']['name']),
            str(user['message']),
        )

    console.print(table)
    print("=" * 30)

    return

def main():
    """
    Initialize required configurations, start with some basic stuff.
    """
    # Initialize configuration
    client = None
    user_config = read_config()
    user_id = user_config.get('user_id')
    user_token = user_config.get('user_token')
    user_device = user_config.get('user_device')
    name = user_config.get('name')
    username = user_config.get('username')

    # Check if user is authenticated
    if user_id and user_token and user_device:
        client = Clubhouse(
            user_id=user_id,
            user_token=user_token,
            user_device=user_device
        )

        # Check if user is still on the waitlist
        _check = client.check_waitlist_status()
        if _check['is_waitlisted']:
            print("[!] You're still on the waitlist. Find your friends to get yourself in.")
            return

        # Check if user has not signed up yet.
        _check = client.me()
        if not _check['user_profile'].get("username"):
            process_onboarding(client)

        _res = client.me()
        # print(_res)
        num_invites = _res['num_invites']
        print("=" * 30)
        print("Club House Command V1")
        print("=" * 30)
        print("[!] ID : " + user_id)
        print("[!] name : " + name)
        print("[!] username : @" + username)
        print("[!] invites : " + str(num_invites))
        print("=" * 30)
        noTi(client,_res['actionable_notifications_count'])
        getOnlineFriends(client)
        menu(client,num_invites)
        # chat_main(client)

    else:
        client = Clubhouse()
        user_authentication(client)
        main()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Remove dump files on exit.
        file_list = os.listdir(".")
        for _file in file_list:
            if _file.endswith(".dmp"):
                os.remove(_file)
