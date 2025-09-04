from fabric import Connection
import invoke

SSH_CONFIG = """
Host mac
     Hostname 10.0.0.2
     User user
     IdentityFile ~/.ssh/mac_key
"""

PATH = "/opt/homebrew/bin:/opt/homebrew/sbin:/opt/homebrew/opt/openjdk/bin:/usr/local/bin:/System/Cryptexes/App/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin:/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/local/bin:/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/bin:/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/appleinternal/bin:/Library/Apple/usr/bin:/Users/user/Library/Android/sdk/tools:/Users/user/Library/Android/sdk/platform-tools"

SERIAL = 'ANDROID_DEVICE_ID_7'

def run_instrumentation_task_ssh(con: Connection, task: str, serial: str, args: dict):
    """Run an instrumentation task via SSH and return a promise of the resul
    """

    args["task"] = task
    arguments = sum([['-e', k, v] for k,v in args.items()], [])
    cmd = (['adb', 'shell', 'am', 'instrument'] +
           arguments +
           ['-e', 'deviceType', 'g20',
            "-w", "com.example.adextractauto.test/androidx.test.runner.AndroidJUnitRunner"])

    return con.run(" ".join(cmd),
                    env={"ANDROID_SERIAL": serial,
                         "PATH": PATH,
                         "ANDROID_HOME": "/Users/user/Library/Android/sdk"},
                    asynchronous=True)

def install_esim(con: Connection, phonenumber):
    return run_instrumentation_task_ssh(con,
                          "installESIM",
                          SERIAL,
                          {"phonenumber" : phonenumber})

def remove_esim(con: Connection, phonenumber):
    return run_instrumentation_task_ssh(con,
                          "removeESIM",
                          SERIAL,
                          {"phonenumber" : phonenumber})

def retrieve_code(con: Connection, platform: str):
    t = run_instrumentation_task_ssh(con,
                                     "retrieveSMSCode",
                                     SERIAL,
                                     {'platform': platform}).join()
    if "FAILURES!!!" in t.stdout:
        try:
            # extract code
            code = t.stdout.split(">>>>")[1].split("<<<<")[0]
            return code
        except IndexError:
            raise RuntimeError("Failed to extract code.")
    else:
        raise RuntimeError("Failed to extract code.")

def retrieve_code_google(con: Connection):
    return retrieve_code(con, "Google")

def retrieve_code_apple(con: Connection):
    return retrieve_code(con, "Apple")
